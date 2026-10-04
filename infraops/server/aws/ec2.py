"""EC2 instance querying and inspection module."""

from typing import Any, Dict, List, Optional

from infraops.server.aws.client import get_client, seed_mock_environment


def list_instances() -> List[Dict[str, Any]]:
    """List EC2 instances with tags, network bindings, and state."""
    seed_mock_environment()
    ec2 = get_client("ec2")
    resp = ec2.describe_instances()

    instances = []
    for res in resp.get("Reservations", []):
        for inst in res.get("Instances", []):
            tags = {t.get("Key"): t.get("Value") for t in inst.get("Tags", [])}
            name = tags.get("Name", inst.get("InstanceId"))
            instances.append(
                {
                    "instance_id": inst.get("InstanceId"),
                    "name": name,
                    "state": inst.get("State", {}).get("Name", "unknown"),
                    "instance_type": inst.get("InstanceType"),
                    "availability_zone": inst.get("Placement", {}).get("AvailabilityZone"),
                    "private_ip": inst.get("PrivateIpAddress"),
                    "public_ip": inst.get("PublicIpAddress"),
                    "subnet_id": inst.get("SubnetId"),
                    "vpc_id": inst.get("VpcId"),
                    "launch_time": str(inst.get("LaunchTime")),
                    "tags": tags,
                }
            )

    return instances


def get_instance(instance_id: str) -> Optional[Dict[str, Any]]:
    """Get single instance details by instance ID."""
    instances = list_instances()
    for inst in instances:
        if inst["instance_id"] == instance_id:
            return inst
    return None
