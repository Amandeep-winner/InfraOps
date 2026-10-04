"""End-to-end integration tests verifying automated detection, SOP execution, and resolution."""

import os
import time

import pytest

from infraops.common.config import reset_settings
from infraops.demo.supervisor import ServiceManager
from scripts.demo_run import E2EOrchestrator
from scripts.simulate import (
    cpu_hog,
    disk_fill,
    service_down,
)


@pytest.fixture(scope="function")
def orchestrator(temp_sandbox):
    """Fixture providing initialized E2EOrchestrator in an isolated temporary sandbox."""
    os.environ["INFRAOPS_TEST_THRESHOLDS"] = "1"
    os.environ["INFRAOPS_AUTO_REMEDIATE"] = "true"
    reset_settings()

    orch = E2EOrchestrator(sandbox_dir=temp_sandbox)
    # Start baseline demo services
    svc_mgr = ServiceManager("demo-service", sandbox_dir=temp_sandbox)
    svc_mgr.start()
    upstream_mgr = ServiceManager("demo-upstream", sandbox_dir=temp_sandbox)
    upstream_mgr.start()
    time.sleep(1.0)

    orch.start_agent_loop()
    time.sleep(1.5)

    yield orch

    orch.stop_agent_loop()
    svc_mgr.stop()
    upstream_mgr.stop()


@pytest.mark.slow
def test_inc_001_cpu_hog_e2e(orchestrator):
    """INC-001: High CPU -> high_cpu alert -> SOP-001 -> kills worker -> RESOLVED."""
    t0 = time.time()
    try:
        cpu_hog.start_cpu_hog(num_workers=1)
        inc = orchestrator.wait_for_resolution("SOP-001", since_time=t0, timeout=75.0)
        assert inc.state == "RESOLVED"
        assert inc.sop_id == "SOP-001"
    finally:
        cpu_hog.stop_cpu_hog()


@pytest.mark.slow
def test_inc_003_disk_full_e2e(orchestrator):
    """INC-003: Disk Full -> disk_full_vol alert -> SOP-003 -> cleans logs -> RESOLVED."""
    t0 = time.time()
    try:
        disk_fill.start_disk_fill(target_mb=90)
        inc = orchestrator.wait_for_resolution("SOP-003", since_time=t0, timeout=75.0)
        assert inc.state == "RESOLVED"
        assert inc.sop_id == "SOP-003"
    finally:
        disk_fill.stop_disk_fill()


@pytest.mark.slow
def test_inc_004_service_down_e2e(orchestrator):
    """INC-004: Service Down -> service_down alert -> SOP-004 -> restarts service -> RESOLVED."""
    t0 = time.time()
    try:
        service_down.trigger_service_down()
        inc = orchestrator.wait_for_resolution("SOP-004", since_time=t0, timeout=75.0)
        assert inc.state == "RESOLVED"
        assert inc.sop_id == "SOP-004"
    finally:
        service_down.restore_service()
