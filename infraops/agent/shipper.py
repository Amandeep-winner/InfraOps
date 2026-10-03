"""Agent data shipper with retry logic and offline disk spooling."""

import json
import platform
import socket
import time
import uuid
from pathlib import Path

import httpx

from infraops.common.logging import setup_logger
from infraops.common.schemas import HostRegisterRequest, IngestBatch

logger = setup_logger("infraops.agent.shipper")


class Shipper:
    """Delivers telemetry batches to the server, spooling to disk when offline."""

    def __init__(self, server_url: str, api_key: str, spool_dir: Path) -> None:
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.spool_dir = Path(spool_dir)
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }

    def register_host(self, host_id: str) -> bool:
        """Register host metadata with the central server."""
        url = f"{self.server_url}/api/v1/hosts/register"
        req = HostRegisterRequest(
            id=host_id,
            hostname=socket.gethostname(),
            ip="127.0.0.1",
            os=f"{platform.system()} {platform.release()}",
            kind="vm",
            tags={"arch": platform.machine()},
        )
        try:
            with httpx.Client(timeout=4.0) as client:
                res = client.post(url, headers=self.headers, json=req.model_dump())
                return res.status_code in [200, 201]
        except Exception as e:
            logger.warning("Failed to register host with server: %s", e)
            return False

    def _spool_to_disk(self, batch: IngestBatch) -> None:
        """Save failed batch to local spool directory."""
        filename = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.json"
        target = self.spool_dir / filename
        try:
            target.write_text(batch.model_dump_json(), encoding="utf-8")
            logger.info("Spopled metrics batch to %s", target.name)
        except Exception as e:
            logger.error("Failed to write to spool directory: %s", e)

    def _flush_spool(self) -> None:
        """Attempt to flush spooled batches to the server in chronological order."""
        spool_files = sorted(list(self.spool_dir.glob("*.json")))
        if not spool_files:
            return

        url = f"{self.server_url}/api/v1/ingest"
        with httpx.Client(timeout=4.0) as client:
            for sf in spool_files:
                try:
                    payload = json.loads(sf.read_text(encoding="utf-8"))
                    res = client.post(url, headers=self.headers, json=payload)
                    if res.status_code == 200:
                        sf.unlink(missing_ok=True)
                        logger.info("Flushed spooled batch %s to server", sf.name)
                    else:
                        break
                except Exception:
                    break

    def ship(self, batch: IngestBatch) -> bool:
        """Deliver batch to server; flush backlog first, spool if delivery fails."""
        self._flush_spool()

        url = f"{self.server_url}/api/v1/ingest"
        try:
            with httpx.Client(timeout=4.0) as client:
                res = client.post(url, headers=self.headers, json=batch.model_dump())
                if res.status_code == 200:
                    return True
                else:
                    logger.warning("Server returned HTTP %s on ingest", res.status_code)
                    self._spool_to_disk(batch)
                    return False
        except Exception as e:
            logger.warning("Ingest delivery failed (%s); spooling to disk", e)
            self._spool_to_disk(batch)
            return False
