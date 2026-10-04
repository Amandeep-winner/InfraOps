"""IPv4 CIDR calculation, subnet splitting, and AWS reservation utilities."""

import ipaddress
from typing import Dict, List

from pydantic import BaseModel, Field


class CIDRInfo(BaseModel):
    """Structured representation of an IPv4 CIDR block."""

    cidr: str
    network_address: str
    broadcast_address: str
    netmask: str
    wildcard_mask: str
    prefixlen: int
    total_ips: int
    standard_usable_hosts: int
    aws_reserved_ips: int
    aws_usable_hosts: int
    aws_reserved_details: List[Dict[str, str]] = Field(default_factory=list)


def _calculate_wildcard_mask(netmask_str: str) -> str:
    """Calculate wildcard mask from dotted-decimal netmask."""
    octets = [255 - int(octet) for octet in netmask_str.split(".")]
    return ".".join(str(o) for o in octets)


def parse_cidr(cidr_str: str) -> CIDRInfo:
    """Parse and calculate network parameters and AWS host reservations for a CIDR block."""
    try:
        network = ipaddress.IPv4Network(cidr_str.strip(), strict=False)
    except Exception as e:
        raise ValueError(f"Invalid IPv4 CIDR string '{cidr_str}': {e}") from e

    prefix = network.prefixlen
    total_ips = network.num_addresses

    # Standard usable hosts: network and broadcast reserved for prefix <= 30
    if prefix <= 30:
        standard_usable = total_ips - 2
    elif prefix == 31:
        standard_usable = 2  # RFC 3021 point-to-point links
    else:
        standard_usable = 1  # Host address /32

    # AWS reservations: AWS reserves 5 IP addresses per subnet (/28 is smallest allowed AWS subnet)
    # 1. First IP: Network address
    # 2. Second IP: VPC router
    # 3. Third IP: AmazonProvidedDNS
    # 4. Fourth IP: Reserved for future use
    # 5. Last IP: Network broadcast address
    aws_reserved_details: List[Dict[str, str]] = []
    if prefix <= 28:
        aws_reserved_count = 5
        aws_usable = max(0, total_ips - 5)

        net_int = int(network.network_address)
        aws_reserved_details = [
            {"ip": str(ipaddress.IPv4Address(net_int)), "purpose": "Network Address"},
            {"ip": str(ipaddress.IPv4Address(net_int + 1)), "purpose": "VPC Router"},
            {"ip": str(ipaddress.IPv4Address(net_int + 2)), "purpose": "AmazonProvidedDNS"},
            {"ip": str(ipaddress.IPv4Address(net_int + 3)), "purpose": "Future AWS Use"},
            {"ip": str(network.broadcast_address), "purpose": "Network Broadcast Address"},
        ]
    else:
        # AWS does not support subnets smaller than /28
        aws_reserved_count = min(total_ips, 5)
        aws_usable = 0
        aws_reserved_details = [
            {
                "ip": str(network.network_address),
                "purpose": "Unsupported AWS subnet size (minimum allowed is /28)",
            }
        ]

    netmask = str(network.netmask)
    wildcard = _calculate_wildcard_mask(netmask)

    return CIDRInfo(
        cidr=str(network),
        network_address=str(network.network_address),
        broadcast_address=str(network.broadcast_address),
        netmask=netmask,
        wildcard_mask=wildcard,
        prefixlen=prefix,
        total_ips=total_ips,
        standard_usable_hosts=standard_usable,
        aws_reserved_ips=aws_reserved_count,
        aws_usable_hosts=aws_usable,
        aws_reserved_details=aws_reserved_details,
    )


def split_cidr(cidr_str: str, new_prefix: int) -> List[CIDRInfo]:
    """Divide a parent CIDR block into smaller subnets of length new_prefix."""
    try:
        network = ipaddress.IPv4Network(cidr_str.strip(), strict=False)
    except Exception as e:
        raise ValueError(f"Invalid IPv4 CIDR string '{cidr_str}': {e}") from e

    if not isinstance(new_prefix, int) or new_prefix < 0 or new_prefix > 32:
        raise ValueError(f"Target prefix must be an integer between 0 and 32, got {new_prefix}")

    if new_prefix < network.prefixlen:
        raise ValueError(
            f"Cannot split /{network.prefixlen} into larger /{new_prefix} block (new_prefix must be >= {network.prefixlen})"
        )

    # Prevent unreasonable combinatorial blowup
    if new_prefix - network.prefixlen > 12:
        raise ValueError(
            f"Splitting /{network.prefixlen} into /{new_prefix} would create {2 ** (new_prefix - network.prefixlen)} subnets. Maximum allowed subnet expansion is 4096 (12 prefix delta)."
        )

    subnets = list(network.subnets(new_prefix=new_prefix))
    return [parse_cidr(str(sub)) for sub in subnets]


def check_overlap(cidr1: str, cidr2: str) -> bool:
    """Return True if two IPv4 CIDR blocks overlap."""
    try:
        net1 = ipaddress.IPv4Network(cidr1.strip(), strict=False)
        net2 = ipaddress.IPv4Network(cidr2.strip(), strict=False)
    except Exception as e:
        raise ValueError(f"Invalid CIDR passed to check_overlap: {e}") from e

    return net1.overlaps(net2)


def validate_cidr(cidr_str: str) -> bool:
    """Check whether a string is a syntactically valid IPv4 CIDR."""
    try:
        ipaddress.IPv4Network(cidr_str.strip(), strict=False)
        return True
    except Exception:
        return False
