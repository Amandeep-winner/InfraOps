"""Network and CIDR calculation NOC utility endpoints."""

import socket
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from infraops.server.netutils.cidr import parse_cidr, split_cidr
from infraops.server.security import verify_api_key

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(verify_api_key)])


@router.get("/cidr", response_model=Dict[str, Any])
def calculate_cidr(
    cidr: str = Query(..., description="IPv4 CIDR block (e.g. 10.0.0.0/16)"),
    new_prefix: Optional[int] = Query(
        None, description="Optional smaller prefix to split the block (e.g. 24)"
    ),
):
    """Compute network parameters, standard and AWS-usable host math, and optional subnet splitting."""
    try:
        info = parse_cidr(cidr)
        result: Dict[str, Any] = {"info": info.model_dump()}

        if new_prefix is not None:
            subnets = split_cidr(cidr, new_prefix)
            result["subnets"] = [s.model_dump() for s in subnets]
            result["subnet_count"] = len(subnets)

        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/dns", response_model=Dict[str, Any])
def lookup_dns(
    name: str = Query(..., description="Domain name or hostname to resolve (e.g. example.com)"),
):
    """Perform forward DNS lookup and measure round-trip resolution latency."""
    start = time.time()
    try:
        results = socket.getaddrinfo(name.strip(), None, family=socket.AF_INET)
        latency_ms = round((time.time() - start) * 1000.0, 2)
        ip_addresses = list({res[4][0] for res in results if res and res[4]})
        return {
            "name": name,
            "resolved": True,
            "ips": ip_addresses,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        latency_ms = round((time.time() - start) * 1000.0, 2)
        return {
            "name": name,
            "resolved": False,
            "error": str(e),
            "ips": [],
            "latency_ms": latency_ms,
        }


@router.get("/port", response_model=Dict[str, Any])
def check_port(
    host: str = Query(..., description="Host IP address or hostname"),
    port: int = Query(..., ge=1, le=65535, description="TCP port number"),
    timeout: float = Query(2.0, ge=0.1, le=10.0, description="Connection timeout in seconds"),
):
    """Check TCP port accessibility and measure connection latency."""
    start = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        latency_ms = round((time.time() - start) * 1000.0, 2)
        s.close()
        return {
            "host": host,
            "port": port,
            "open": True,
            "latency_ms": latency_ms,
            "status": "OPEN",
        }
    except socket.timeout:
        return {
            "host": host,
            "port": port,
            "open": False,
            "latency_ms": round(timeout * 1000.0, 2),
            "status": "TIMEOUT",
        }
    except ConnectionRefusedError:
        latency_ms = round((time.time() - start) * 1000.0, 2)
        return {
            "host": host,
            "port": port,
            "open": False,
            "latency_ms": latency_ms,
            "status": "REFUSED",
        }
    except Exception as e:
        latency_ms = round((time.time() - start) * 1000.0, 2)
        return {
            "host": host,
            "port": port,
            "open": False,
            "latency_ms": latency_ms,
            "status": f"ERROR: {e}",
        }
    finally:
        s.close()
