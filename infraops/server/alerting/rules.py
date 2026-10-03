"""Alert rule specification and validation."""

import os
from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel


class AlertRule(BaseModel):
    """Specification for an alerting rule."""

    id: str
    metric: Optional[str] = None
    op: Optional[Literal[">", ">=", "<", "<=", "=="]] = None
    threshold: Optional[float] = None
    for_seconds: float = 0.0
    resolve_after_seconds: float = 15.0
    severity: str = "P3"
    sop: Optional[str] = None
    summary: Optional[str] = None
    type: Literal["metric", "heartbeat"] = "metric"
    stale_after_seconds: Optional[float] = 30.0

    def evaluate_condition(self, value: float) -> bool:
        """Evaluate numeric operator against rule threshold."""
        if self.threshold is None or self.op is None:
            return False
        if self.op == ">":
            return value > self.threshold
        elif self.op == ">=":
            return value >= self.threshold
        elif self.op == "<":
            return value < self.threshold
        elif self.op == "<=":
            return value <= self.threshold
        elif self.op == "==":
            return abs(value - self.threshold) < 1e-6
        return False


def load_alert_rules(rules_path: Optional[str] = None) -> List[AlertRule]:
    """Load and validate alert rules from YAML file, respecting test threshold overrides."""
    use_test = os.environ.get("INFRAOPS_TEST_THRESHOLDS", "").lower() in ["1", "true", "yes"]

    if rules_path:
        target_path = Path(rules_path)
    elif use_test:
        target_path = Path("config/alert_rules.test.yaml")
    else:
        target_path = Path("config/alert_rules.yaml")

    if not target_path.is_file():
        # Fallback to test or default config relative to project root
        project_root = Path(__file__).resolve().parents[3]
        target_path = project_root / (
            "config/alert_rules.test.yaml" if use_test else "config/alert_rules.yaml"
        )

    if not target_path.is_file():
        raise FileNotFoundError(f"Alert rules file not found: {target_path}")

    with target_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    raw_rules = data.get("rules", [])
    rules = [AlertRule(**r) for r in raw_rules]
    return rules
