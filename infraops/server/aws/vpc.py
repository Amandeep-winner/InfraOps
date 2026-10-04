"""VPC, Subnet, and Security Group inspection with CIDR math and risk auditing."""

from typing import Any, Dict, List, Optional

from infraops.server.aws.client import get_client, seed_mock_environment
from infraops.server.netutils.cidr import parse_cidr


def list_vpcs() -> List[Dict[str, Any]]:
    """List VPCs with CIDR blocks, DNS attributes, and tags."""
    seed_mock_environment()
    ec2 = get_client("ec2")
    resp = ec2.describe_vpcs()

    vpcs = []
    for v in resp.get("Vpcs", []):
        tags = {t.get("Key"): t.get("Value") for t in v.get("Tags", [])}
        vpcs.append(
            {
                "vpc_id": v.get("VpcId"),
                "cidr_block": v.get("CidrBlock"),
                "state": v.get("State"),
                "is_default": v.get("IsDefault", False),
                "name": tags.get("Name", v.get("VpcId")),
                "tags": tags,
            }
        )
    return vpcs


def list_subnets(vpc_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List subnets enriched with total, standard usable, and AWS-usable host counts."""
    seed_mock_environment()
    ec2 = get_client("ec2")
    kwargs: Dict[str, Any] = {}
    if vpc_id:
        kwargs["Filters"] = [{"Name": "vpc-id", "Values": [vpc_id]}]
    resp = ec2.describe_subnets(**kwargs)

    subnets = []
    for s in resp.get("Subnets", []):
        cidr = s.get("CidrBlock", "")
        tags = {t.get("Key"): t.get("Value") for t in s.get("Tags", [])}

        cidr_info = None
        if cidr:
            try:
                cidr_info = parse_cidr(cidr)
            except Exception:
                pass

        subnets.append(
            {
                "subnet_id": s.get("SubnetId"),
                "vpc_id": s.get("VpcId"),
                "cidr_block": cidr,
                "availability_zone": s.get("AvailabilityZone"),
                "available_ip_count": s.get("AvailableIpAddressCount"),
                "name": tags.get("Name", s.get("SubnetId")),
                "type": tags.get("Type", "unknown"),
                "total_ips": cidr_info.total_ips if cidr_info else 0,
                "standard_usable_hosts": cidr_info.standard_usable_hosts if cidr_info else 0,
                "aws_usable_hosts": cidr_info.aws_usable_hosts if cidr_info else 0,
                "aws_reserved_ips": cidr_info.aws_reserved_ips if cidr_info else 5,
                "tags": tags,
            }
        )

    return subnets


def _analyze_sg_risks(permissions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect insecure security group ingress rules."""
    findings = []
    for perm in permissions:
        protocol = perm.get("IpProtocol", "")
        from_port = perm.get("FromPort")
        to_port = perm.get("ToPort")

        for ip_range in perm.get("IpRanges", []):
            cidr = ip_range.get("CidrIp", "")
            if cidr == "0.0.0.0/0":
                # Check for sensitive open ports
                if from_port == 22 or (
                    from_port is not None and to_port is not None and from_port <= 22 <= to_port
                ):
                    findings.append(
                        {
                            "severity": "CRITICAL",
                            "port": 22,
                            "protocol": protocol,
                            "cidr": cidr,
                            "message": "SSH port 22 is exposed to the entire internet (0.0.0.0/0)",
                        }
                    )
                elif from_port == 3389 or (
                    from_port is not None and to_port is not None and from_port <= 3389 <= to_port
                ):
                    findings.append(
                        {
                            "severity": "CRITICAL",
                            "port": 3389,
                            "protocol": protocol,
                            "cidr": cidr,
                            "message": "RDP port 3389 is exposed to the entire internet (0.0.0.0/0)",
                        }
                    )
                elif from_port is None and to_port is None and protocol in ["-1", "all"]:
                    findings.append(
                        {
                            "severity": "CRITICAL",
                            "port": "ALL",
                            "protocol": "ALL",
                            "cidr": cidr,
                            "message": "All ports and protocols are open to 0.0.0.0/0",
                        }
                    )
                elif from_port not in [80, 443]:
                    findings.append(
                        {
                            "severity": "WARNING",
                            "port": f"{from_port}-{to_port}"
                            if from_port != to_port
                            else str(from_port),
                            "protocol": protocol,
                            "cidr": cidr,
                            "message": f"Non-standard web port {from_port} exposed to 0.0.0.0/0",
                        }
                    )
    return findings


def list_security_groups(vpc_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List security groups with ingress/egress rules and security risk analysis."""
    seed_mock_environment()
    ec2 = get_client("ec2")
    kwargs: Dict[str, Any] = {}
    if vpc_id:
        kwargs["Filters"] = [{"Name": "vpc-id", "Values": [vpc_id]}]
    resp = ec2.describe_security_groups(**kwargs)

    groups = []
    for g in resp.get("SecurityGroups", []):
        ingress = g.get("IpPermissions", [])
        risks = _analyze_sg_risks(ingress)
        tags = {t.get("Key"): t.get("Value") for t in g.get("Tags", [])}

        groups.append(
            {
                "group_id": g.get("GroupId"),
                "group_name": g.get("GroupName"),
                "description": g.get("Description"),
                "vpc_id": g.get("VpcId"),
                "ingress_rules": ingress,
                "egress_rules": g.get("IpPermissionsEgress", []),
                "risk_findings": risks,
                "is_risky": len(risks) > 0,
                "tags": tags,
            }
        )

    return groups
