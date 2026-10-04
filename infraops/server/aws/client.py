"""AWS client provider and mock environment seeder using moto."""

import json
import os
from pathlib import Path
from typing import Any, Dict

import boto3

from infraops.common.config import get_settings
from infraops.common.logging import setup_logger

logger = setup_logger("infraops.server.aws")

_mock_context = None
_seeded = False


def _ensure_mock_context():
    """Start global moto mock context if running in mock mode."""
    global _mock_context
    settings = get_settings()
    if settings.aws_mode == "mock" and _mock_context is None:
        os.environ["AWS_ACCESS_KEY_ID"] = "mock_access_key"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "mock_secret_key"
        os.environ["AWS_DEFAULT_REGION"] = settings.aws_region
        os.environ["MOTO_ALLOW_NONEXISTENT_REGION"] = "true"
        try:
            import moto

            _mock_context = moto.mock_aws()
            _mock_context.start()
            logger.info("Started moto mock_aws context in region %s", settings.aws_region)
        except Exception as e:
            logger.warning("Could not start moto mock context: %s", e)


def get_client(service_name: str):
    """Return a configured boto3 client for the specified AWS service."""
    _ensure_mock_context()
    settings = get_settings()
    return boto3.client(service_name, region_name=settings.aws_region)


def seed_mock_environment(force: bool = False) -> Dict[str, Any]:
    """Idempotently seed the mock AWS account with realistic infrastructure topology."""
    global _seeded
    if _seeded and not force:
        return {"status": "already_seeded"}

    _ensure_mock_context()
    settings = get_settings()
    region = settings.aws_region
    ec2 = get_client("ec2")
    iam = get_client("iam")
    s3 = get_client("s3")
    cw = get_client("cloudwatch")

    az1 = f"{region}a"
    az2 = f"{region}b"

    # 1. VPC and Subnets
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": ["infraops-vpc"]}])["Vpcs"]
    if vpcs:
        vpc_id = vpcs[0]["VpcId"]
    else:
        vpc_resp = ec2.create_vpc(
            CidrBlock="10.0.0.0/16",
            TagSpecifications=[
                {
                    "ResourceType": "vpc",
                    "Tags": [
                        {"Key": "Name", "Value": "infraops-vpc"},
                        {"Key": "Environment", "Value": "production"},
                    ],
                }
            ],
        )
        vpc_id = vpc_resp["Vpc"]["VpcId"]
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})

    # Subnets definition
    subnets_def = [
        {"cidr": "10.0.1.0/24", "az": az1, "type": "public", "name": "infraops-public-1"},
        {"cidr": "10.0.2.0/24", "az": az2, "type": "public", "name": "infraops-public-2"},
        {"cidr": "10.0.11.0/24", "az": az1, "type": "private", "name": "infraops-private-1"},
        {"cidr": "10.0.12.0/24", "az": az2, "type": "private", "name": "infraops-private-2"},
    ]
    created_subnets = {}
    for s_def in subnets_def:
        existing = ec2.describe_subnets(
            Filters=[
                {"Name": "vpc-id", "Values": [vpc_id]},
                {"Name": "cidr-block", "Values": [s_def["cidr"]]},
            ]
        )["Subnets"]
        if existing:
            created_subnets[s_def["name"]] = existing[0]["SubnetId"]
        else:
            sub = ec2.create_subnet(
                VpcId=vpc_id,
                CidrBlock=s_def["cidr"],
                AvailabilityZone=s_def["az"],
                TagSpecifications=[
                    {
                        "ResourceType": "subnet",
                        "Tags": [
                            {"Key": "Name", "Value": s_def["name"]},
                            {"Key": "Type", "Value": s_def["type"]},
                        ],
                    }
                ],
            )["Subnet"]
            created_subnets[s_def["name"]] = sub["SubnetId"]

    # 2. IGW and Route Tables
    igws = ec2.describe_internet_gateways(
        Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
    )["InternetGateways"]
    if igws:
        igw_id = igws[0]["InternetGatewayId"]
    else:
        igw = ec2.create_internet_gateway(
            TagSpecifications=[
                {
                    "ResourceType": "internet-gateway",
                    "Tags": [{"Key": "Name", "Value": "infraops-igw"}],
                }
            ]
        )["InternetGateway"]
        igw_id = igw["InternetGatewayId"]
        ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)

    # Public route table with route to IGW
    pub_rts = ec2.describe_route_tables(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "tag:Name", "Values": ["infraops-public-rt"]},
        ]
    )["RouteTables"]
    if pub_rts:
        pub_rt_id = pub_rts[0]["RouteTableId"]
    else:
        pub_rt = ec2.create_route_table(
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    "ResourceType": "route-table",
                    "Tags": [{"Key": "Name", "Value": "infraops-public-rt"}],
                }
            ],
        )["RouteTable"]
        pub_rt_id = pub_rt["RouteTableId"]
        ec2.create_route(RouteTableId=pub_rt_id, DestinationCidrBlock="0.0.0.0/0", GatewayId=igw_id)
        # Associate public subnets
        ec2.associate_route_table(
            RouteTableId=pub_rt_id, SubnetId=created_subnets["infraops-public-1"]
        )
        ec2.associate_route_table(
            RouteTableId=pub_rt_id, SubnetId=created_subnets["infraops-public-2"]
        )

    # 3. Security Groups
    sgs = ec2.describe_security_groups(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "group-name", "Values": ["infraops-sg"]},
        ]
    )["SecurityGroups"]
    if sgs:
        sg_id = sgs[0]["GroupId"]
    else:
        sg = ec2.create_security_group(
            GroupName="infraops-sg",
            Description="InfraOps main workload security group",
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [{"Key": "Name", "Value": "infraops-sg"}],
                }
            ],
        )
        sg_id = sg["GroupId"]
        # Allowlist ingress rules:
        # - Port 22 from admin CIDR only (secure)
        # - Port 8000 from VPC
        # - Port 443 public
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [
                        {"CidrIp": "203.0.113.50/32", "Description": "Admin Bastion Only"}
                    ],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 8000,
                    "ToPort": 8000,
                    "IpRanges": [{"CidrIp": "10.0.0.0/16", "Description": "Internal VPC"}],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTPS Public"}],
                },
            ],
        )

    # Secondary security group with intentional risk (for security audit check)
    risky_sgs = ec2.describe_security_groups(
        Filters=[
            {"Name": "vpc-id", "Values": [vpc_id]},
            {"Name": "group-name", "Values": ["risky-external-ssh-sg"]},
        ]
    )["SecurityGroups"]
    if not risky_sgs:
        risky_sg = ec2.create_security_group(
            GroupName="risky-external-ssh-sg",
            Description="Insecure legacy security group with 0.0.0.0/0 on port 22",
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [{"Key": "Name", "Value": "risky-external-ssh-sg"}],
                }
            ],
        )
        ec2.authorize_security_group_ingress(
            GroupId=risky_sg["GroupId"],
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Worldwide SSH"}],
                }
            ],
        )

    # 4. EC2 Instances
    instances_def = [
        {"name": "infraops-web-1", "subnet": "infraops-public-1", "tier": "web"},
        {"name": "infraops-web-2", "subnet": "infraops-public-2", "tier": "web"},
        {"name": "infraops-db-1", "subnet": "infraops-private-1", "tier": "db"},
    ]
    for inst in instances_def:
        existing = ec2.describe_instances(
            Filters=[
                {"Name": "tag:Name", "Values": [inst["name"]]},
                {"Name": "instance-state-name", "Values": ["pending", "running", "stopped"]},
            ]
        )
        if not existing["Reservations"]:
            ec2.run_instances(
                ImageId="ami-12345678",
                InstanceType="t3.micro",
                MinCount=1,
                MaxCount=1,
                SubnetId=created_subnets[inst["subnet"]],
                SecurityGroupIds=[sg_id],
                TagSpecifications=[
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": inst["name"]},
                            {"Key": "Environment", "Value": "production"},
                            {"Key": "Tier", "Value": inst["tier"]},
                        ],
                    }
                ],
            )

    # 5. S3 Buckets
    buckets = ["infraops-incident-reports", "infraops-log-archive"]
    for b in buckets:
        try:
            s3.create_bucket(
                Bucket=b,
                CreateBucketConfiguration={"LocationConstraint": region}
                if region != "us-east-1"
                else {},
            )
        except Exception:
            pass

        try:
            s3.put_bucket_versioning(Bucket=b, VersioningConfiguration={"Status": "Enabled"})
            s3.put_public_access_block(
                Bucket=b,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            )
        except Exception:
            pass

    # 6. IAM Roles and Policies
    role_name = "infraops-agent-role"
    assume_role_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    try:
        iam.get_role(RoleName=role_name)
    except Exception:
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy),
            Description="Role for InfraOps agent telemetry and log uploads",
        )

    # Attach least-privilege policy from terraform/iam_policies/agent_policy.json
    policy_path = Path("infra/terraform/iam_policies/agent_policy.json")
    if policy_path.is_file():
        doc = policy_path.read_text(encoding="utf-8")
        policy_name = "InfraOpsAgentLeastPrivilegePolicy"
        try:
            p_res = iam.create_policy(PolicyName=policy_name, PolicyDocument=doc)
            iam.attach_role_policy(RoleName=role_name, PolicyArn=p_res["Policy"]["Arn"])
        except Exception:
            pass

    # Add an over-permissive test role to demonstrate least-privilege auditing
    excessive_role_name = "overpermissive-legacy-admin-role"
    try:
        iam.get_role(RoleName=excessive_role_name)
    except Exception:
        iam.create_role(
            RoleName=excessive_role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy),
            Description="Legacy role carrying wildcard permissions",
        )
        wildcard_policy = {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}],
        }
        try:
            wp_res = iam.create_policy(
                PolicyName="WildcardAdminPolicy", PolicyDocument=json.dumps(wildcard_policy)
            )
            iam.attach_role_policy(RoleName=excessive_role_name, PolicyArn=wp_res["Policy"]["Arn"])
        except Exception:
            pass

    # 7. CloudWatch Alarms
    alarms = [
        {"name": "HighCPUAlarm", "metric": "CPUPercent", "threshold": 80.0},
        {"name": "HighMemoryAlarm", "metric": "MemPercent", "threshold": 85.0},
        {"name": "DiskSpaceAlarm", "metric": "DiskPercent", "threshold": 90.0},
    ]
    for a in alarms:
        try:
            cw.put_metric_alarm(
                AlarmName=a["name"],
                ComparisonOperator="GreaterThanThreshold",
                EvaluationPeriods=2,
                MetricName=a["metric"],
                Namespace="InfraOps/Host",
                Period=60,
                Statistic="Average",
                Threshold=a["threshold"],
                ActionsEnabled=False,
                AlarmDescription=f"Alarm when {a['metric']} exceeds {a['threshold']}%",
            )
        except Exception:
            pass

    _seeded = True
    logger.info(
        "Seeded mock AWS environment with VPC %s, 3 EC2 instances, S3, IAM, CloudWatch", vpc_id
    )
    return {"status": "seeded", "vpc_id": vpc_id, "subnets": created_subnets}
