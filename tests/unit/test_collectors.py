"""Unit tests for agent metric collectors."""

import os

from infraops.agent.collectors.connectivity import ConnectivityCollector
from infraops.agent.collectors.cpu import CpuCollector
from infraops.agent.collectors.disk import DiskCollector
from infraops.agent.collectors.dns import DnsCollector
from infraops.agent.collectors.logs import LogCollector
from infraops.agent.collectors.memory import MemoryCollector
from infraops.agent.collectors.network import NetworkCollector
from infraops.agent.collectors.permissions import PermissionCollector
from infraops.agent.collectors.processes import ProcessCollector
from infraops.agent.collectors.services import ServiceCollector
from infraops.agent.collectors.ssh_security import SshSecurityCollector


def test_cpu_collector():
    collector = CpuCollector()
    metrics, snapshot, logs = collector.collect()
    assert len(metrics) >= 4
    metric_names = {m.name for m in metrics}
    assert "cpu.percent" in metric_names
    assert "cpu.count" in metric_names
    assert "cpu.load1" in metric_names
    assert snapshot is None
    assert logs == []


def test_memory_collector():
    collector = MemoryCollector()
    metrics, snapshot, logs = collector.collect()
    assert len(metrics) >= 4
    names = {m.name for m in metrics}
    assert "mem.percent" in names
    assert "mem.used_mb" in names
    assert "mem.available_mb" in names
    assert "swap.percent" in names


def test_disk_collector(tmp_path):
    # Setup virtual volume
    vol_dir = tmp_path / "sandbox_data"
    vol_dir.mkdir()
    test_file = vol_dir / "sample.bin"
    test_file.write_bytes(b"A" * (1024 * 1024))  # 1 MB

    cfg = {
        "paths": [str(tmp_path)],
        "virtual_volumes": [{"name": "test-vol", "path": str(vol_dir), "capacity_mb": 10}],
    }
    collector = DiskCollector(cfg)
    metrics, _, _ = collector.collect()
    names = {m.name for m in metrics}
    assert "disk.percent" in names
    assert "disk.vol.percent" in names

    vol_metric = next(m for m in metrics if m.name == "disk.vol.percent")
    assert vol_metric.labels.get("name") == "test-vol"
    assert vol_metric.value > 0.0


def test_network_collector():
    collector = NetworkCollector()
    metrics, _, _ = collector.collect()
    names = {m.name for m in metrics}
    assert "net.bytes_sent" in names
    assert "net.bytes_recv" in names
    assert "net.tcp_established" in names
    assert "net.tcp_listen" in names


def test_process_collector():
    collector = ProcessCollector({"top_n_processes": 3})
    metrics, snapshot, _ = collector.collect()
    names = {m.name for m in metrics}
    assert "proc.count" in names
    assert "proc.zombies" in names
    assert snapshot is not None
    assert "top_cpu" in snapshot.payload
    assert "top_mem" in snapshot.payload
    assert len(snapshot.payload["top_cpu"]) <= 3


def test_service_collector_pidfile(tmp_path):
    pidfile = tmp_path / "svc.pid"
    # Write current process PID so it appears running
    pidfile.write_text(str(os.getpid()))

    cfg = {
        "services": [
            {"name": "running_svc", "manager": "pidfile", "pidfile": str(pidfile)},
            {"name": "missing_svc", "manager": "pidfile", "pidfile": str(tmp_path / "none.pid")},
        ]
    }
    collector = ServiceCollector(cfg)
    metrics, snapshot, _ = collector.collect()

    m_running = next(m for m in metrics if m.labels.get("name") == "running_svc")
    m_missing = next(m for m in metrics if m.labels.get("name") == "missing_svc")
    assert m_running.value == 1.0
    assert m_missing.value == 0.0


def test_log_collector(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("INFO: started\n")

    cfg = {
        "files": [{"path": str(log_file), "patterns": {"error": "ERROR", "critical": "CRITICAL"}}]
    }
    collector = LogCollector(cfg)
    metrics, _, logs = collector.collect()
    assert len(logs) == 0

    # Append error lines
    with log_file.open("a") as f:
        f.write("ERROR: connection lost\n")
        f.write("CRITICAL: Out of memory\n")

    metrics2, _, logs2 = collector.collect()
    assert len(logs2) == 2
    err_metric = next(m for m in metrics2 if m.name == "log.errors_per_min")
    assert err_metric.value == 2.0


def test_dns_collector(tmp_path):
    fault_flag = tmp_path / "dns_fail"
    cfg = {"names": ["localhost"], "fault_flag": str(fault_flag)}

    collector = DnsCollector(cfg)
    metrics, _, _ = collector.collect()
    dns_up = next(m for m in metrics if m.name == "dns.up" and m.labels.get("name") == "localhost")
    assert dns_up.value == 1.0

    # Trigger fault
    fault_flag.write_text("1")
    collector2 = DnsCollector(cfg)
    metrics2, _, _ = collector2.collect()
    dns_up2 = next(
        m for m in metrics2 if m.name == "dns.up" and m.labels.get("name") == "localhost"
    )
    assert dns_up2.value == 0.0


def test_connectivity_collector():
    cfg = {
        "tcp_targets": [{"name": "loopback", "host": "127.0.0.1", "port": 9999}],
        "ports_expected_listening": [80],
    }
    collector = ConnectivityCollector(cfg)
    metrics, snapshot, _ = collector.collect()
    names = {m.name for m in metrics}
    assert "conn.tcp_up" in names
    assert "ports.expected_missing" in names
    assert snapshot is not None


def test_ssh_security_collector(tmp_path):
    cfg_file = tmp_path / "sshd_config"
    cfg_file.write_text("PermitRootLogin no\nPasswordAuthentication no\nPort 2222\n")

    auth_log = tmp_path / "auth.log"
    auth_log.write_text("Failed password for invalid user admin\nInvalid user test\n")

    collector = SshSecurityCollector({"sshd_config": str(cfg_file), "auth_log": str(auth_log)})
    metrics, snapshot, _ = collector.collect()
    failed_m = next(m for m in metrics if m.name == "ssh.failed_logins_5m")
    assert failed_m.value == 2.0
    root_m = next(m for m in metrics if m.name == "ssh.root_login_enabled")
    assert root_m.value == 0.0


def test_permission_collector(tmp_path):
    file1 = tmp_path / "test1"
    file1.write_text("hello")

    collector = PermissionCollector({"audit_paths": [str(file1)]})
    metrics, snapshot, _ = collector.collect()
    assert len(metrics) == 1
    assert snapshot is not None
