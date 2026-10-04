"""Unit tests for CIDR calculation, subnet splitting, and AWS IP reservations."""

import pytest

from infraops.server.netutils.cidr import (
    check_overlap,
    parse_cidr,
    split_cidr,
    validate_cidr,
)


def test_parse_cidr_slash_24():
    """Verify /24 subnet calculation including AWS 5 reserved addresses."""
    res = parse_cidr("10.0.1.0/24")
    assert res.cidr == "10.0.1.0/24"
    assert res.network_address == "10.0.1.0"
    assert res.broadcast_address == "10.0.1.255"
    assert res.netmask == "255.255.255.0"
    assert res.wildcard_mask == "0.0.0.255"
    assert res.prefixlen == 24
    assert res.total_ips == 256
    assert res.standard_usable_hosts == 254
    assert res.aws_reserved_ips == 5
    assert res.aws_usable_hosts == 251

    # Verify AWS 5 reserved IP breakdown
    reserved_ips = [item["ip"] for item in res.aws_reserved_details]
    assert reserved_ips == [
        "10.0.1.0",  # Network
        "10.0.1.1",  # VPC Router
        "10.0.1.2",  # AmazonProvidedDNS
        "10.0.1.3",  # Future AWS use
        "10.0.1.255",  # Broadcast
    ]


def test_parse_cidr_slash_16():
    """Verify /16 VPC CIDR calculation."""
    res = parse_cidr("172.16.0.0/16")
    assert res.network_address == "172.16.0.0"
    assert res.broadcast_address == "172.16.255.255"
    assert res.netmask == "255.255.0.0"
    assert res.wildcard_mask == "0.0.255.255"
    assert res.total_ips == 65536
    assert res.standard_usable_hosts == 65534
    assert res.aws_usable_hosts == 65531


def test_parse_cidr_aws_limits():
    """Verify /28 is minimum AWS subnet (16 - 5 = 11 usable) and /29 is rejected by AWS."""
    # /28: 16 total, 5 reserved, 11 usable
    s28 = parse_cidr("192.168.1.0/28")
    assert s28.total_ips == 16
    assert s28.aws_usable_hosts == 11
    assert s28.aws_reserved_ips == 5

    # /29: 8 total, AWS does not allow /29 subnets
    s29 = parse_cidr("192.168.1.0/29")
    assert s29.total_ips == 8
    assert s29.aws_usable_hosts == 0


def test_split_cidr():
    """Verify splitting /24 into /26 yields 4 equal subnets."""
    subs = split_cidr("10.0.0.0/24", 26)
    assert len(subs) == 4
    assert [s.cidr for s in subs] == [
        "10.0.0.0/26",
        "10.0.0.64/26",
        "10.0.0.128/26",
        "10.0.0.192/26",
    ]
    for s in subs:
        assert s.total_ips == 64
        assert s.aws_usable_hosts == 59  # 64 - 5


def test_split_cidr_slash_16_to_slash_24():
    """Verify splitting /16 into /24 yields 256 subnets."""
    subs = split_cidr("10.0.0.0/16", 24)
    assert len(subs) == 256
    assert subs[0].cidr == "10.0.0.0/24"
    assert subs[255].cidr == "10.0.255.0/24"


def test_split_cidr_invalid_prefix():
    """Verify splitting into smaller or invalid prefix raises ValueError."""
    with pytest.raises(ValueError, match="Cannot split"):
        split_cidr("10.0.0.0/24", 20)

    with pytest.raises(ValueError, match="Target prefix must be"):
        split_cidr("10.0.0.0/24", 35)

    with pytest.raises(ValueError, match="Maximum allowed subnet expansion"):
        split_cidr("10.0.0.0/8", 24)  # 16-bit delta exceeds 12-bit safety cap


def test_check_overlap():
    """Verify network overlap detection."""
    # Complete overlap / subset
    assert check_overlap("10.0.0.0/16", "10.0.1.0/24") is True
    assert check_overlap("10.0.1.0/24", "10.0.0.0/16") is True

    # Partial / adjacent non-overlapping
    assert check_overlap("10.0.1.0/24", "10.0.2.0/24") is False
    assert check_overlap("192.168.1.0/24", "10.0.0.0/8") is False


def test_validate_cidr():
    """Verify CIDR validation."""
    assert validate_cidr("10.0.0.0/16") is True
    assert validate_cidr("192.168.1.1/32") is True
    assert validate_cidr("not-a-cidr") is False
    assert validate_cidr("999.999.999.999/24") is False
