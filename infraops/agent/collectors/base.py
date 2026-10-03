"""Base collector interface for InfraOps agent."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class BaseCollector(ABC):
    """Abstract base class implemented by all metric and snapshot collectors."""

    name: str = "base"

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or {}

    @abstractmethod
    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        """Collect metrics, optional snapshot, and log events synchronously or via worker."""
        raise NotImplementedError
