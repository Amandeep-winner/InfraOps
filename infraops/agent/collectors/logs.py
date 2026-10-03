"""Log tail collector with regex pattern categorization and offset tracking."""

import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from infraops.agent.collectors.base import BaseCollector
from infraops.common.schemas import LogEvent, MetricPoint, SnapshotPayload


class LogCollector(BaseCollector):
    """Monitors log files, classifies events by regex, and maintains stream offsets."""

    name = "logs"

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        # Store file offsets and inodes: {file_path: (offset, inode)}
        self._offsets: Dict[str, Tuple[int, int]] = {}

    def _get_file_stat(self, path: Path) -> Tuple[int, int]:
        st = path.stat()
        return st.st_size, getattr(st, "st_ino", 0)

    def collect(self) -> Tuple[List[MetricPoint], Optional[SnapshotPayload], List[LogEvent]]:
        now = time.time()
        metrics: List[MetricPoint] = []
        events: List[LogEvent] = []

        files_config = self.config.get("files", [])
        for entry in files_config:
            file_path = entry.get("path")
            if not file_path:
                continue

            path = Path(file_path)
            optional = entry.get("optional", False)

            if not path.is_file():
                if not optional:
                    metrics.append(
                        MetricPoint(
                            name="log.errors_per_min",
                            value=0.0,
                            labels={"source": path.name},
                            ts=now,
                        )
                    )
                continue

            patterns = entry.get(
                "patterns", {"error": "ERROR|Traceback", "critical": "CRITICAL|OOM"}
            )
            error_regex = re.compile(patterns.get("error", "ERROR"))
            crit_regex = re.compile(patterns.get("critical", "CRITICAL"))

            error_count = 0
            crit_count = 0

            try:
                curr_size, curr_ino = self._get_file_stat(path)
                last_offset, last_ino = self._offsets.get(str(path), (0, curr_ino))

                # Check for log rotation (file truncated or inode changed)
                if curr_ino != last_ino or curr_size < last_offset:
                    last_offset = 0

                if curr_size > last_offset:
                    with path.open("r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_offset)
                        new_lines = f.readlines()
                        self._offsets[str(path)] = (f.tell(), curr_ino)

                    for line in new_lines:
                        line_clean = line.strip()
                        matched_crit = crit_regex.search(line_clean)
                        matched_err = error_regex.search(line_clean)

                        if matched_crit:
                            crit_count += 1
                            events.append(
                                LogEvent(
                                    source=path.name,
                                    level="CRITICAL",
                                    message=line_clean,
                                    matched_pattern=matched_crit.group(0),
                                    ts=now,
                                )
                            )
                        elif matched_err:
                            error_count += 1
                            events.append(
                                LogEvent(
                                    source=path.name,
                                    level="ERROR",
                                    message=line_clean,
                                    matched_pattern=matched_err.group(0),
                                    ts=now,
                                )
                            )
                else:
                    self._offsets[str(path)] = (last_offset, curr_ino)

            except Exception:
                pass

            metrics.append(
                MetricPoint(
                    name="log.errors_per_min",
                    value=float(error_count + crit_count),
                    labels={"source": path.name},
                    ts=now,
                )
            )
            metrics.append(
                MetricPoint(
                    name="log.critical_count",
                    value=float(crit_count),
                    labels={"source": path.name},
                    ts=now,
                )
            )

        return metrics, None, events
