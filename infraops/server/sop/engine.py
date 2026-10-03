"""SOP execution orchestrator, approval workflow, and escalation logic."""

import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from infraops.common.logging import setup_logger
from infraops.server.incidents.reports import generate_incident_report
from infraops.server.incidents.service import IncidentService
from infraops.server.models import Approval, Incident, SopRun
from infraops.server.sop.actions import execute_action
from infraops.server.sop.loader import SOPModel, load_all_sops
from infraops.server.sop.verify import (
    verify_http_endpoint,
    verify_metric_condition,
    verify_service_running,
)

logger = setup_logger("infraops.sop.engine")


class SOPEngine:
    """Orchestrates SOP execution lifecycle, step dispatches, approvals, and escalations."""

    def __init__(
        self, action_executor: Optional[Callable[[str, Dict[str, Any]], Any]] = None
    ) -> None:
        self.action_executor = action_executor or execute_action
        self._sops_cache = load_all_sops()

    def get_sop(self, sop_id: str) -> SOPModel:
        if sop_id not in self._sops_cache:
            self._sops_cache = load_all_sops()
        if sop_id not in self._sops_cache:
            raise ValueError(f"SOP '{sop_id}' not found in library")
        return self._sops_cache[sop_id]

    def _interpolate_params(
        self, params: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve {var.field} templates from stored context."""
        interpolated = {}
        pattern = re.compile(r"\{(\w+)\.(\w+)\}")

        for k, v in params.items():
            if isinstance(v, str):
                match = pattern.search(v)
                if match:
                    ctx_key, field = match.group(1), match.group(2)
                    if ctx_key in context and isinstance(context[ctx_key], dict):
                        resolved_val = context[ctx_key].get(field)
                        if resolved_val is not None:
                            interpolated[k] = pattern.sub(str(resolved_val), v)
                        else:
                            raise ValueError(
                                f"Unresolved template field '{field}' in context '{ctx_key}'"
                            )
                    else:
                        raise ValueError(f"Context key '{ctx_key}' not found for template '{v}'")
                else:
                    interpolated[k] = v
            else:
                interpolated[k] = v
        return interpolated

    def run_sop(
        self,
        sop_id: str,
        incident_id: str,
        host_id: str,
        db: Session,
        mode: str = "auto",
        max_retries: int = 2,
    ) -> bool:
        """Execute a full SOP run against an incident."""
        sop = self.get_sop(sop_id)
        incident = db.get(Incident, incident_id)
        if not incident:
            raise ValueError(f"Incident '{incident_id}' not found")

        sop_run = SopRun(
            incident_id=incident_id,
            sop_id=sop_id,
            state="running",
            started_at=datetime.now(timezone.utc),
            step_results={},
        )
        db.add(sop_run)
        db.commit()

        context: Dict[str, Any] = {}
        results: Dict[str, Any] = {}
        retries = 0
        success = False

        while retries <= max_retries:
            phase_status = self._execute_sop_steps(
                sop=sop,
                incident=incident,
                host_id=host_id,
                db=db,
                mode=mode,
                context=context,
                results=results,
            )

            if phase_status == "RESOLVED":
                success = True
                break
            elif phase_status == "PAUSED":
                # Manual approval required; stop execution and await user action
                sop_run.state = "paused"
                sop_run.step_results = results
                db.commit()
                return False
            else:
                # Verification failed -> retry remediation block if attempts remain
                retries += 1
                if retries <= max_retries:
                    logger.info(
                        "Verification failed for %s. Retrying remediation (attempt %s/%s)...",
                        incident_id,
                        retries,
                        max_retries,
                    )
                    IncidentService.record_event(
                        db=db,
                        incident_id=incident_id,
                        phase="verify",
                        actor="sop",
                        message=f"Verification failed on attempt {retries}; retrying remediation block",
                    )
                    IncidentService.transition_state(
                        db=db, incident_id=incident_id, new_state="REMEDIATING", actor="sop"
                    )
                else:
                    # Exceeded retries -> escalate
                    logger.warning(
                        "Verification permanently failed for %s. Escalating to L2.", incident_id
                    )
                    IncidentService.transition_state(
                        db=db,
                        incident_id=incident_id,
                        new_state="ESCALATED",
                        actor="sop",
                        message=sop.escalation.if_failed,
                    )
                    sop_run.state = "escalated"
                    sop_run.finished_at = datetime.now(timezone.utc)
                    sop_run.step_results = results
                    db.commit()
                    return False

        if success:
            sop_run.state = "completed"
            sop_run.finished_at = datetime.now(timezone.utc)
            sop_run.step_results = results
            db.commit()
            # Generate post-incident report
            try:
                generate_incident_report(incident_id, db)
            except Exception as e:
                logger.error("Failed to generate incident report: %s", e)
            return True

        return False

    def _execute_sop_steps(
        self,
        sop: SOPModel,
        incident: Incident,
        host_id: str,
        db: Session,
        mode: str,
        context: Dict[str, Any],
        results: Dict[str, Any],
    ) -> str:
        """Execute SOP steps grouped by lifecycle phase."""
        current_phase = ""

        for step in sop.steps:
            # Handle phase boundary state transition
            if step.phase != current_phase:
                current_phase = step.phase
                target_state = {
                    "investigate": "INVESTIGATING",
                    "identify": "IDENTIFIED",
                    "remediate": "REMEDIATING",
                    "verify": "VERIFYING",
                }.get(current_phase)

                if target_state and incident.state != target_state:
                    try:
                        IncidentService.transition_state(db, incident.id, target_state, actor="sop")
                    except Exception:
                        pass

            # Manual mode approval check
            if mode == "manual" and step.requires_approval_in_manual:
                approval = db.scalars(
                    select(Approval).where(
                        Approval.incident_id == incident.id,
                        Approval.step_id == step.id,
                    )
                ).first()

                if not approval:
                    # Request approval and pause
                    approval = Approval(
                        incident_id=incident.id,
                        step_id=step.id,
                        state="pending",
                        requested_at=datetime.now(timezone.utc),
                    )
                    db.add(approval)
                    IncidentService.record_event(
                        db=db,
                        incident_id=incident.id,
                        phase=step.phase,
                        actor="sop",
                        message=f"Paused: step '{step.name}' requires manual operator approval",
                    )
                    db.commit()
                    return "PAUSED"
                elif approval.state == "pending":
                    return "PAUSED"
                elif approval.state == "rejected":
                    IncidentService.record_event(
                        db=db,
                        incident_id=incident.id,
                        phase=step.phase,
                        actor="human",
                        message=f"Step '{step.name}' was rejected by operator. Escalating incident.",
                    )
                    IncidentService.transition_state(db, incident.id, "ESCALATED", actor="sop")
                    return "ESCALATED"

            # Execute step action or verification
            start_t = time.time()
            try:
                resolved_params = self._interpolate_params(step.params, context)

                if step.action == "verify_metric":
                    ok = verify_metric_condition(resolved_params, db, host_id)
                    output = "Condition met" if ok else "Condition not met within timeout"
                elif step.action == "verify_http":
                    ok = verify_http_endpoint(resolved_params)
                    output = "HTTP endpoint healthy" if ok else "HTTP endpoint unreachable"
                elif step.action == "verify_service":
                    ok = verify_service_running(resolved_params)
                    output = "Service alive" if ok else "Service stopped"
                else:
                    output = self.action_executor(step.action, resolved_params)
                    ok = output if isinstance(output, bool) else True

                duration_ms = round((time.time() - start_t) * 1000.0, 2)
                results[step.id] = {"ok": ok, "output": output, "duration_ms": duration_ms}

                if step.store_as:
                    context[step.store_as] = output

                IncidentService.record_event(
                    db=db,
                    incident_id=incident.id,
                    phase=step.phase,
                    actor="sop",
                    message=f"{step.name}: {output if isinstance(output, str) else 'Executed'}",
                    data={"step_id": step.id, "duration_ms": duration_ms},
                )

                if step.phase == "verify" and not ok:
                    return "VERIFY_FAILED"

            except Exception as e:
                duration_ms = round((time.time() - start_t) * 1000.0, 2)
                results[step.id] = {"ok": False, "error": str(e), "duration_ms": duration_ms}
                IncidentService.record_event(
                    db=db,
                    incident_id=incident.id,
                    phase=step.phase,
                    actor="sop",
                    message=f"Error executing step '{step.name}': {e}",
                )
                if step.phase == "verify":
                    return "VERIFY_FAILED"

        IncidentService.transition_state(
            db=db,
            incident_id=incident.id,
            new_state="RESOLVED",
            actor="sop",
            message=f"SOP {sop.id} completed successfully. All verifications passed.",
        )
        return "RESOLVED"
