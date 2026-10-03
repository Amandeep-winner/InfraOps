"""Unit tests for incident simulators and clean teardown validation."""

import time

import psutil

from infraops.common.config import reset_settings
from infraops.common.sandbox import get_sandbox_dir, is_sandbox_process
from scripts.simulate import (
    cpu_hog,
    disk_fill,
    dns_failure,
    mem_hog,
    net_connectivity,
    service_down,
)


def test_cpu_hog_lifecycle(temp_sandbox):
    """Verify CPU hog starts workers with sandbox marker and stops without orphans."""
    reset_settings()
    pids = cpu_hog.start_cpu_hog(num_workers=2)
    assert len(pids) == 2
    time.sleep(0.5)

    for pid in pids:
        assert psutil.pid_exists(pid)
        assert is_sandbox_process(pid)

    cpu_hog.stop_cpu_hog()
    time.sleep(0.5)

    for pid in pids:
        assert not psutil.pid_exists(pid)


def test_mem_hog_lifecycle_and_cap(temp_sandbox):
    """Verify memory hog starts within safe cap and stops cleanly."""
    reset_settings()
    cap_mb = 30
    pid = mem_hog.start_mem_hog(cap_mb=cap_mb)
    assert pid is not None
    time.sleep(0.5)

    assert psutil.pid_exists(pid)
    assert is_sandbox_process(pid)

    # Check RSS does not exceed cap by more than small python runtime overhead
    proc = psutil.Process(pid)
    rss_mb = proc.memory_info().rss / (1024 * 1024)
    assert rss_mb <= cap_mb + 100.0  # Safe cap check

    mem_hog.stop_mem_hog()
    time.sleep(0.5)
    assert not psutil.pid_exists(pid)


def test_disk_fill_lifecycle(temp_sandbox):
    """Verify disk fill creates dummy logs and cleanly deletes them on stop."""
    reset_settings()
    sandbox = get_sandbox_dir()
    data_dir = sandbox / "data"

    disk_fill.start_disk_fill(target_mb=6)
    files = list(data_dir.glob("sim_bloat_*.log"))
    assert len(files) == 3

    disk_fill.stop_disk_fill()
    remaining = list(data_dir.glob("sim_bloat_*.log"))
    assert len(remaining) == 0


def test_dns_failure_lifecycle(temp_sandbox):
    """Verify DNS failure simulator toggles fault flag correctly."""
    reset_settings()
    sandbox = get_sandbox_dir()
    flag = sandbox / "faults" / "dns_fail"

    assert not flag.exists()
    dns_failure.trigger_dns_failure()
    assert flag.exists()

    dns_failure.restore_dns()
    assert not flag.exists()


def test_service_down_lifecycle(temp_sandbox):
    """Verify service_down stops and restores demo service."""
    reset_settings()
    service_down.restore_service()
    time.sleep(0.5)
    mgr = service_down.ServiceManager("demo-service")
    assert mgr.is_running()

    service_down.trigger_service_down()
    time.sleep(0.5)
    assert not mgr.is_running()


def test_net_connectivity_lifecycle(temp_sandbox):
    """Verify net_connectivity stops and restores upstream dependency."""
    reset_settings()
    net_connectivity.restore_network()
    time.sleep(0.5)
    mgr = net_connectivity.ServiceManager("demo-upstream")
    assert mgr.is_running()

    net_connectivity.trigger_net_outage()
    time.sleep(0.5)
    assert not mgr.is_running()
