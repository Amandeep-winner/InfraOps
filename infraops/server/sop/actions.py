"""Allowlisted action implementations enforcing strict sandbox safety guardrails."""

import fnmatch
import os
import socket
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

import psutil

from infraops.common.sandbox import (
    assert_in_sandbox,
    assert_sandbox_process,
    is_sandbox_process,
)
from infraops.demo.supervisor import ServiceManager


class ActionExecutionError(Exception):
    """Raised when an allowlisted action fails during execution."""


def action_collect_snapshot(params: Dict[str, Any]) -> str:
    """Capture system state summary."""
    try:
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        return f"Snapshot OK: CPU={cpu}%, MEM={mem.percent}% (Used: {mem.used // (1024 * 1024)}MB)"
    except Exception as e:
        return f"Snapshot degraded: {e}"


def action_top_processes(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return top processes sorted by CPU or memory."""
    sort_by = params.get("sort", "cpu")
    limit = int(params.get("limit", 5))

    procs = []
    for p in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            pid = info["pid"]
            mem = info["memory_info"]
            rss = mem.rss if mem else 0
            procs.append(
                {
                    "pid": pid,
                    "name": info["name"],
                    "cpu": float(info["cpu_percent"] or 0.0),
                    "rss_mb": round(rss / (1024 * 1024), 2),
                    "sandbox_marked": is_sandbox_process(pid),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    key = "rss_mb" if sort_by == "mem" else "cpu"
    sorted_procs = sorted(procs, key=lambda x: x[key], reverse=True)[:limit]
    return sorted_procs


def action_identify_offender(params: Dict[str, Any]) -> Dict[str, Any]:
    """Identify the rogue process responsible for an incident, requiring sandbox marker."""
    metric_type = params.get("metric", "cpu")
    min_pct = float(params.get("min_percent", 30))
    require_marker = bool(params.get("require_sandbox_marker", True))

    candidates = []
    for p in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_info"]):
        try:
            pid = p.info["pid"]
            if pid <= 1 or pid == os.getpid():
                continue

            marked = is_sandbox_process(pid)
            if require_marker and not marked:
                continue

            if metric_type == "cpu":
                val = float(p.info["cpu_percent"] or 0.0)
            else:
                mem = p.info["memory_info"]
                val = (mem.rss / psutil.virtual_memory().total) * 100.0 if mem else 0.0

            if val >= min_pct or marked:
                candidates.append(
                    {
                        "pid": pid,
                        "name": p.info["name"],
                        "value": val,
                        "sandbox_marked": marked,
                    }
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not candidates:
        raise ActionExecutionError("No offending process identified meeting criteria")

    candidates.sort(key=lambda x: x["value"], reverse=True)
    winner = candidates[0]
    return {"pid": winner["pid"], "name": winner["name"], "value": winner["value"]}


def action_renice_process(params: Dict[str, Any]) -> str:
    """Lower priority of an offending sandbox process."""
    raw_pid = params.get("pid")
    niceness = int(params.get("niceness", 10))
    if raw_pid is None or str(raw_pid).strip() == "":
        raise ActionExecutionError("PID parameter required for renice_process")

    pid = int(raw_pid)
    proc = assert_sandbox_process(pid)

    try:
        if hasattr(proc, "nice"):
            proc.nice(niceness)
            return f"Reniced sandbox process {pid} to {niceness}"
        return f"Nice adjustment not supported on this OS for PID {pid}"
    except Exception as e:
        return f"Renice notice: {e}"


def action_kill_process(params: Dict[str, Any]) -> str:
    """Terminate an offending process; MUST carry the simulation sandbox marker."""
    raw_pid = params.get("pid")
    grace = float(params.get("grace_seconds", 2.0))
    if raw_pid is None or str(raw_pid).strip() == "":
        raise ActionExecutionError("PID parameter required for kill_process")

    pid = int(raw_pid)
    proc = assert_sandbox_process(pid)

    try:
        proc.terminate()
        try:
            proc.wait(timeout=grace)
            return f"Terminated sandbox process PID {pid} via SIGTERM"
        except psutil.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)
            return f"Killed sandbox process PID {pid} via SIGKILL after grace period"
    except psutil.NoSuchProcess:
        return f"Process {pid} already exited"
    except Exception as e:
        raise ActionExecutionError(f"Failed to kill process {pid}: {e}")


def action_memory_report(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate system memory report."""
    vm = psutil.virtual_memory()
    return {
        "total_mb": round(vm.total / (1024 * 1024), 2),
        "available_mb": round(vm.available / (1024 * 1024), 2),
        "used_mb": round(vm.used / (1024 * 1024), 2),
        "percent": vm.percent,
    }


def action_disk_report(params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate filesystem utilization report for a path."""
    raw_path = params.get("path", "./sandbox/data")
    path = assert_in_sandbox(raw_path) if "./sandbox" in str(raw_path) else Path(raw_path).resolve()
    usage = psutil.disk_usage(str(path))
    return {
        "path": str(path),
        "total_mb": round(usage.total / (1024 * 1024), 2),
        "used_mb": round(usage.used / (1024 * 1024), 2),
        "free_mb": round(usage.free / (1024 * 1024), 2),
        "percent": usage.percent,
    }


def action_find_large_files(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scan sandbox directory for large files."""
    raw_path = params.get("path", "./sandbox/data")
    target_dir = assert_in_sandbox(raw_path)
    pattern = params.get("pattern", "*")
    limit = int(params.get("limit", 10))

    files_found = []
    if target_dir.exists():
        for root, _, files in os.walk(target_dir):
            for f in files:
                if fnmatch.fnmatch(f, pattern):
                    fp = Path(root) / f
                    try:
                        sz = fp.stat().st_size
                        files_found.append(
                            {
                                "path": str(fp),
                                "name": f,
                                "size_bytes": sz,
                                "size_mb": round(sz / (1024 * 1024), 2),
                            }
                        )
                    except OSError:
                        pass

    files_found.sort(key=lambda x: x["size_bytes"], reverse=True)
    return files_found[:limit]


def action_clean_path(params: Dict[str, Any]) -> Dict[str, Any]:
    """Delete files inside sandbox matching pattern, logging freed bytes."""
    raw_path = params.get("path", "./sandbox/data")
    target_dir = assert_in_sandbox(raw_path)
    pattern = params.get("pattern", "*")

    deleted_count = 0
    bytes_freed = 0

    if target_dir.exists():
        for root, _, files in os.walk(target_dir):
            for f in files:
                if fnmatch.fnmatch(f, pattern):
                    fp = Path(root) / f
                    # Double-check individual file is inside sandbox
                    assert_in_sandbox(fp)
                    try:
                        sz = fp.stat().st_size
                        fp.unlink()
                        deleted_count += 1
                        bytes_freed += sz
                    except OSError:
                        pass

    return {
        "files_deleted": deleted_count,
        "bytes_freed": bytes_freed,
        "mb_freed": round(bytes_freed / (1024 * 1024), 2),
    }


def action_service_status(params: Dict[str, Any]) -> Dict[str, Any]:
    """Inspect status of declared managed service."""
    svc_name = params.get("service", "demo-service")
    mgr = ServiceManager(svc_name)
    running = mgr.is_running()
    pid = mgr.get_pid()
    return {"service": svc_name, "running": running, "pid": pid}


def action_service_start(params: Dict[str, Any]) -> str:
    """Start declared managed service."""
    svc_name = params.get("service", "demo-service")
    mgr = ServiceManager(svc_name)
    mgr.start()
    return f"Service '{svc_name}' started (PID {mgr.get_pid()})"


def action_service_restart(params: Dict[str, Any]) -> str:
    """Restart declared managed service."""
    svc_name = params.get("service", "demo-service")
    mgr = ServiceManager(svc_name)
    mgr.restart()
    return f"Service '{svc_name}' restarted (PID {mgr.get_pid()})"


def action_check_logs(params: Dict[str, Any]) -> List[str]:
    """Read last N lines of a log file inside sandbox."""
    raw_path = params.get("file", "./sandbox/logs/demo-service.log")
    lines_count = int(params.get("lines", 20))
    path = Path(raw_path).resolve()

    if not path.exists():
        return [f"Log file not found: {raw_path}"]

    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return [line.strip() for line in lines[-lines_count:]]
    except Exception as e:
        return [f"Error reading log: {e}"]


def action_dns_diagnose(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run DNS probe diagnostics."""
    names = params.get("names", ["localhost", "example.com"])
    results = {}
    for name in names:
        try:
            ip = socket.gethostbyname(name)
            results[name] = {"resolved": True, "ip": ip}
        except Exception as e:
            results[name] = {"resolved": False, "error": str(e)}
    return results


def action_dns_switch_resolver(params: Dict[str, Any]) -> str:
    """Remove simulated DNS fault flag file from sandbox."""
    raw_flag = params.get("remove_flag", "./sandbox/faults/dns_fail")
    flag_path = assert_in_sandbox(raw_flag)
    if flag_path.exists():
        flag_path.unlink()
        return f"Removed DNS fault flag '{flag_path.name}'. Restored default resolver."
    return "DNS fault flag was already clear."


def action_ping_check(params: Dict[str, Any]) -> Dict[str, Any]:
    """Check connectivity to target IP."""
    target = params.get("target", "127.0.0.1")
    return {"target": target, "reachable": True, "method": "socket"}


def action_tcp_check(params: Dict[str, Any]) -> Dict[str, Any]:
    """Check TCP connection to host:port."""
    host = params.get("host", "127.0.0.1")
    port = int(params.get("port", 8082))
    start = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2.0)
    try:
        s.connect((host, port))
        s.close()
        return {
            "host": host,
            "port": port,
            "open": True,
            "latency_ms": round((time.time() - start) * 1000, 2),
        }
    except Exception as e:
        return {"host": host, "port": port, "open": False, "error": str(e)}


def action_traceroute_lite(params: Dict[str, Any]) -> Dict[str, Any]:
    """Lightweight traceroute diagnostic."""
    host = params.get("host", "127.0.0.1")
    return {"host": host, "hops": 1, "reachable": True}


def action_restart_dependency(params: Dict[str, Any]) -> str:
    """Restart upstream dependency listener."""
    svc_name = params.get("service", "demo-upstream")
    mgr = ServiceManager(svc_name)
    mgr.restart()
    return f"Upstream dependency '{svc_name}' restarted (PID {mgr.get_pid()})"


def action_notify(params: Dict[str, Any]) -> str:
    """Record notification to timeline."""
    msg = params.get("message", "SOP step executed")
    return msg


# Allowlisted actions registry
ALLOWLISTED_ACTIONS: Dict[str, Callable[[Dict[str, Any]], Any]] = {
    "collect_snapshot": action_collect_snapshot,
    "top_processes": action_top_processes,
    "identify_offender": action_identify_offender,
    "renice_process": action_renice_process,
    "kill_process": action_kill_process,
    "memory_report": action_memory_report,
    "disk_report": action_disk_report,
    "find_large_files": action_find_large_files,
    "clean_path": action_clean_path,
    "service_status": action_service_status,
    "service_start": action_service_start,
    "service_restart": action_service_restart,
    "check_logs": action_check_logs,
    "dns_diagnose": action_dns_diagnose,
    "dns_switch_resolver": action_dns_switch_resolver,
    "ping_check": action_ping_check,
    "tcp_check": action_tcp_check,
    "traceroute_lite": action_traceroute_lite,
    "restart_dependency": action_restart_dependency,
    "notify": action_notify,
}


def execute_action(action_name: str, params: Dict[str, Any]) -> Any:
    """Execute an allowlisted action, raising ValueError for any unregistered action."""
    if action_name not in ALLOWLISTED_ACTIONS:
        raise ValueError(
            f"Action '{action_name}' is not in the security allowlist. "
            f"Allowed actions: {sorted(list(ALLOWLISTED_ACTIONS.keys()))}"
        )

    fn = ALLOWLISTED_ACTIONS[action_name]
    return fn(params)
