"""SOP runbook YAML schema definition, parsing, and validation."""

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field


class SOPStep(BaseModel):
    """Individual execution step within a Standard Operating Procedure."""

    id: str
    phase: Literal["investigate", "identify", "remediate", "verify"]
    name: str
    action: str = Field(..., description="Allowlisted action name")
    params: Dict[str, Any] = Field(default_factory=dict)
    store_as: Optional[str] = None
    risk: Literal["low", "medium", "high"] = "low"
    requires_approval_in_manual: bool = False


class EscalationConfig(BaseModel):
    """Escalation directives if automated remediation or verification fails."""

    if_failed: str


class SOPTrigger(BaseModel):
    """Trigger alert rule mapping for the SOP."""

    alert_rule: str


class SOPModel(BaseModel):
    """Complete Standard Operating Procedure definition."""

    id: str
    title: str
    severity_default: str = "P2"
    trigger: SOPTrigger
    owner: str = "L1"
    estimated_minutes: int = 5
    description: str
    steps: List[SOPStep]
    rollback_note: Optional[str] = None
    escalation: EscalationConfig
    references: List[str] = Field(default_factory=list)


def load_sop_file(file_path: str | Path) -> SOPModel:
    """Parse and validate a single SOP YAML file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"SOP file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid SOP format in {path}: expected YAML mapping")

    return SOPModel(**data)


def load_all_sops(sops_dir: str | Path = "sops") -> Dict[str, SOPModel]:
    """Scan and load all valid SOP files from directory, keyed by SOP id."""
    sdir = Path(sops_dir)
    if not sdir.is_dir():
        # Fallback relative to project root
        sdir = Path(__file__).resolve().parents[3] / "sops"

    sops: Dict[str, SOPModel] = {}
    if not sdir.exists():
        return sops

    for f in sdir.glob("*.yaml"):
        try:
            sop = load_sop_file(f)
            sops[sop.id] = sop
        except Exception as e:
            raise ValueError(f"Failed to load SOP from {f.name}: {e}") from e

    return sops
