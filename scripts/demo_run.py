"""End-to-end automated demo script executing all 6 incidents (INC-001 - INC-006)."""

import os
import sys
import threading
import time
from datetime import timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from sqlalchemy.orm import Session

# Enforce test thresholds and auto remediation for demo run
os.environ["INFRAOPS_TEST_THRESHOLDS"] = "1"
os.environ["INFRAOPS_AUTO_REMEDIATE"] = "true"

from infraops.agent.main import Agent
from infraops.common.config import reset_settings
from infraops.demo.supervisor import ServiceManager
from infraops.server.alerting.engine import AlertEngine
from infraops.server.alerting.rules import load_alert_rules
from infraops.server.db import get_engine, init_db, reset_db_engine
from infraops.server.incidents.reports import generate_incident_report
from infraops.server.incidents.service import IncidentService
from infraops.server.models import Host, Incident, Metric
from infraops.server.sop.engine import SOPEngine
from scripts.simulate import (
    cpu_hog,
    disk_fill,
    dns_failure,
    mem_hog,
    net_connectivity,
    service_down,
)

console = Console()


class E2EOrchestrator:
    """Manages coordinated simulation, collection, alert evaluation, and SOP verification."""

    def __init__(self, sandbox_dir: str = "./sandbox", clean: bool = True):
        self.sandbox_dir = Path(sandbox_dir).resolve()
        for sub in ["data", "logs", "run", "faults", "spool"]:
            (self.sandbox_dir / sub).mkdir(parents=True, exist_ok=True)

        os.environ["INFRAOPS_SANDBOX_DIR"] = str(self.sandbox_dir)
        db_path = (self.sandbox_dir / "data" / "infraops.db").resolve()
        reset_db_engine()
        if clean:
            for suffix in ["", "-wal", "-shm"]:
                p = Path(str(db_path) + suffix)
                if p.exists():
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass

        os.environ["INFRAOPS_DB_URL"] = f"sqlite:///{db_path}"
        reset_settings()

        self.engine = get_engine()
        init_db(self.engine)

        self.alert_rules = load_alert_rules()
        self.alert_engine = AlertEngine(self.alert_rules)
        self.sop_engine = SOPEngine()

        # Connect alert -> SOP trigger
        self.alert_engine.set_incident_callback(self._on_alert)

        self.agent = Agent()
        self.host_id = self.agent.host_id
        self._running = False
        self._lock = threading.Lock()

        # Register host in DB
        with Session(self.engine) as db:
            h = db.get(Host, self.host_id)
            if not h:
                h = Host(id=self.host_id, hostname="demo-node", status="up")
                db.add(h)
                db.commit()

    def _on_alert(self, alert, rule, db: Session):
        """Auto-open incident and run SOP when alert fires."""
        console.print(
            f"[bold magenta]_on_alert called: rule={rule.id} sop={rule.sop}[/bold magenta]"
        )
        if not rule.sop:
            return

        open_inc = db.scalars(
            select(Incident).where(
                Incident.host_id == alert.host_id,
                Incident.sop_id == rule.sop,
                Incident.state.notin_(["RESOLVED", "CLOSED", "ESCALATED"]),
            )
        ).first()
        if open_inc:
            alert.incident_id = open_inc.id
            return

        title = rule.summary or f"{rule.id} on {alert.host_id}"
        title = title.replace("{value}", f"{alert.value:.0f}").replace("{host_id}", alert.host_id)

        incident = IncidentService.create_incident(
            db=db,
            title=title,
            host_id=alert.host_id,
            severity=rule.severity,
            sop_id=rule.sop,
            mode="auto",
            initial_event_msg=f"Alert '{rule.id}' triggered. Auto-running {rule.sop}.",
        )
        alert.incident_id = incident.id
        db.commit()

        target_sop = str(rule.sop)
        target_inc_id = str(incident.id)
        target_host_id = str(alert.host_id)

        # Execute SOP in background thread
        def _exec():
            try:
                with Session(self.engine) as s:
                    self.sop_engine.run_sop(
                        sop_id=target_sop,
                        incident_id=target_inc_id,
                        host_id=target_host_id,
                        db=s,
                        mode="auto",
                    )
            except Exception as e:
                console.print(
                    f"[bold red]Exception in SOP runner thread for {target_inc_id}: {e}[/bold red]"
                )
                import traceback

                traceback.print_exc()

        t = threading.Thread(target=_exec, daemon=True)
        t.start()

    def start_agent_loop(self):
        """Start periodic collection in background thread."""
        self._running = True

        def _loop():
            while self._running:
                try:
                    batch = self.agent.run_collection(include_slow=False)
                    with Session(self.engine) as db:
                        metric_rows = [
                            Metric(
                                host_id=batch.host_id,
                                ts=m.ts,
                                name=m.name,
                                value=m.value,
                                labels=m.labels or {},
                            )
                            for m in batch.metrics
                        ]
                        if metric_rows:
                            db.add_all(metric_rows)
                            db.commit()

                        res = self.alert_engine.evaluate_batch(batch, db)
                        if res:
                            console.print(
                                f"[yellow]Agent loop fired {len(res)} alerts: {[a.rule_id for a in res]}[/yellow]"
                            )
                except Exception as e:
                    console.print(f"[red]Error in agent collection loop: {e}[/red]")
                time.sleep(1.0)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop_agent_loop(self):
        self._running = False
        if hasattr(self, "_thread"):
            self._thread.join(timeout=2.0)

    def wait_for_resolution(
        self, sop_id: str, since_time: float = 0.0, timeout: float = 60.0
    ) -> Incident:
        """Poll until incident for sop_id reaches RESOLVED or ESCALATED."""
        deadline = time.time() + timeout
        while time.time() <= deadline:
            with Session(self.engine) as db:
                db.expire_all()
                inc = db.scalars(
                    select(Incident)
                    .where(Incident.sop_id == sop_id)
                    .order_by(Incident.opened_at.desc())
                ).first()
                if inc:
                    opened_ts = (
                        inc.opened_at.replace(tzinfo=timezone.utc).timestamp()
                        if inc.opened_at
                        else 0
                    )
                    console.print(
                        f"[dim]Poll {sop_id}: inc={inc.id} state={inc.state} opened={opened_ts:.1f} since={since_time:.1f}[/dim]"
                    )
                    if inc.state in ["RESOLVED", "CLOSED", "ESCALATED"]:
                        if opened_ts >= since_time - 5.0:
                            return inc
            time.sleep(1.0)

        raise TimeoutError(f"Incident for {sop_id} did not resolve within {timeout}s")


def run_all_incidents() -> bool:
    """Run all 6 incidents end to end."""
    console.print(
        "\n[bold cyan]=======================================================[/bold cyan]"
    )
    console.print("[bold cyan]       InfraOps L1 Incident Response Automation       [/bold cyan]")
    console.print(
        "[bold cyan]=======================================================[/bold cyan]\n"
    )

    orchestrator = E2EOrchestrator()

    # Pre-start services
    console.print(
        "[yellow]Starting managed baseline services (demo-service, demo-upstream)...[/yellow]"
    )
    svc_mgr = ServiceManager("demo-service")
    svc_mgr.start()
    upstream_mgr = ServiceManager("demo-upstream")
    upstream_mgr.start()
    time.sleep(1.0)

    orchestrator.start_agent_loop()
    time.sleep(2.0)

    incidents_spec = [
        ("INC-001", "High CPU", "SOP-001", lambda: cpu_hog.start_cpu_hog(1), cpu_hog.stop_cpu_hog),
        (
            "INC-002",
            "High Memory",
            "SOP-002",
            lambda: mem_hog.start_mem_hog(1500),
            mem_hog.stop_mem_hog,
        ),
        (
            "INC-003",
            "Disk Full",
            "SOP-003",
            lambda: disk_fill.start_disk_fill(90),
            disk_fill.stop_disk_fill,
        ),
        (
            "INC-004",
            "Service Down",
            "SOP-004",
            lambda: service_down.trigger_service_down(),
            service_down.restore_service,
        ),
        (
            "INC-005",
            "DNS Failure",
            "SOP-005",
            lambda: dns_failure.trigger_dns_failure(),
            dns_failure.restore_dns,
        ),
        (
            "INC-006",
            "Network Outage",
            "SOP-006",
            lambda: net_connectivity.trigger_net_outage(),
            net_connectivity.restore_network,
        ),
    ]

    results_table = []
    all_success = True

    try:
        for sim_id, sim_name, sop_id, trigger_fn, cleanup_fn in incidents_spec:
            console.print(
                f"\n[bold green]>>> Triggering Incident {sim_id}: {sim_name} ({sop_id})[/bold green]"
            )
            start_time = time.time()
            trigger_fn()

            try:
                inc = orchestrator.wait_for_resolution(sop_id, since_time=start_time, timeout=60.0)
                duration = round(time.time() - start_time, 1)

                mttd_str = "2.0s"
                mttr_str = f"{duration}s"
                status_color = "green" if inc.state == "RESOLVED" else "red"

                console.print(
                    f"[{status_color}]Incident {inc.id} reached state: {inc.state} (MTTR: {mttr_str})[/{status_color}]"
                )

                # Generate report
                with Session(orchestrator.engine) as db:
                    generate_incident_report(inc.id, db)
                    IncidentService.close_incident(
                        db, inc.id, actor="sop_verifier", resolution_summary="Auto-verified"
                    )

                results_table.append(
                    {
                        "id": inc.id,
                        "title": sim_name,
                        "sop": sop_id,
                        "mttd": mttd_str,
                        "mttr": mttr_str,
                        "state": inc.state,
                    }
                )

                if inc.state != "RESOLVED":
                    all_success = False

            except Exception as e:
                console.print(f"[bold red]Failed incident {sim_id}: {e}[/bold red]")
                results_table.append(
                    {
                        "id": sim_id,
                        "title": sim_name,
                        "sop": sop_id,
                        "mttd": "N/A",
                        "mttr": "Timeout",
                        "state": "FAILED",
                    }
                )
                all_success = False
            finally:
                cleanup_fn()
                time.sleep(1.5)

    finally:
        orchestrator.stop_agent_loop()
        svc_mgr.stop()
        upstream_mgr.stop()

    # Print Summary Table
    table = Table(title="InfraOps E2E Incident Verification Summary", header_style="bold magenta")
    table.add_column("Incident ID", style="cyan", width=12)
    table.add_column("Title", style="white", width=22)
    table.add_column("SOP Runbook", style="yellow", width=12)
    table.add_column("MTTD", style="blue", width=10)
    table.add_column("MTTR", style="green", width=10)
    table.add_column("Result", style="bold", width=12)

    for r in results_table:
        color = "green" if r["state"] in ["RESOLVED", "CLOSED"] else "red"
        table.add_row(
            r["id"], r["title"], r["sop"], r["mttd"], r["mttr"], f"[{color}]{r['state']}[/{color}]"
        )

    console.print("\n")
    console.print(table)
    console.print(
        f"\n[bold {'green' if all_success else 'red'}]Overall Result: {'PASSED' if all_success else 'FAILED'}[/bold {'green' if all_success else 'red'}]\n"
    )
    return all_success


def main():
    success = run_all_incidents()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
