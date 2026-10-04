"""S3 bucket querying, public access auditing, and incident report archiving module."""

from typing import Any, Dict, List, Optional

from infraops.server.aws.client import get_client, seed_mock_environment


def list_buckets() -> List[Dict[str, Any]]:
    """List S3 buckets enriched with versioning status and public access block security posture."""
    seed_mock_environment()
    s3 = get_client("s3")
    resp = s3.list_buckets()

    buckets = []
    for b in resp.get("Buckets", []):
        name = b.get("Name", "")

        # Get versioning status
        versioning_status = "Disabled"
        try:
            ver_resp = s3.get_bucket_versioning(Bucket=name)
            versioning_status = ver_resp.get("Status", "Disabled")
        except Exception:
            pass

        # Get public access block status
        public_access_block = {
            "block_public_acls": False,
            "ignore_public_acls": False,
            "block_public_policy": False,
            "restrict_public_buckets": False,
            "is_secure": False,
        }
        try:
            pab_resp = s3.get_public_access_block(Bucket=name)
            conf = pab_resp.get("PublicAccessBlockConfiguration", {})
            b_acls = conf.get("BlockPublicAcls", False)
            i_acls = conf.get("IgnorePublicAcls", False)
            b_pol = conf.get("BlockPublicPolicy", False)
            r_buck = conf.get("RestrictPublicBuckets", False)
            public_access_block = {
                "block_public_acls": b_acls,
                "ignore_public_acls": i_acls,
                "block_public_policy": b_pol,
                "restrict_public_buckets": r_buck,
                "is_secure": all([b_acls, i_acls, b_pol, r_buck]),
            }
        except Exception:
            pass

        # Count objects
        object_count = 0
        total_bytes = 0
        try:
            objs = s3.list_objects_v2(Bucket=name)
            object_count = objs.get("KeyCount", 0)
            for item in objs.get("Contents", []):
                total_bytes += item.get("Size", 0)
        except Exception:
            pass

        buckets.append(
            {
                "name": name,
                "creation_date": str(b.get("CreationDate", "")),
                "versioning": versioning_status,
                "versioning_enabled": versioning_status == "Enabled",
                "public_access_block": public_access_block,
                "object_count": object_count,
                "total_bytes": total_bytes,
            }
        )

    return buckets


def upload_incident_report(
    incident_id: str,
    content: str,
    bucket_name: str = "infraops-incident-reports",
) -> Dict[str, Any]:
    """Upload markdown incident report to S3 archive bucket."""
    seed_mock_environment()
    s3 = get_client("s3")
    key = f"{incident_id}/report.md"

    resp = s3.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType="text/markdown",
    )

    return {
        "bucket": bucket_name,
        "key": key,
        "version_id": resp.get("VersionId"),
        "status": "uploaded",
    }


def get_incident_report(
    incident_id: str,
    bucket_name: str = "infraops-incident-reports",
) -> Optional[str]:
    """Retrieve markdown incident report content from S3."""
    seed_mock_environment()
    s3 = get_client("s3")
    key = f"{incident_id}/report.md"

    try:
        resp = s3.get_object(Bucket=bucket_name, Key=key)
        return resp["Body"].read().decode("utf-8")
    except Exception:
        return None


def list_incident_reports(
    bucket_name: str = "infraops-incident-reports",
) -> List[Dict[str, Any]]:
    """List all incident reports stored in the S3 archive bucket."""
    seed_mock_environment()
    s3 = get_client("s3")

    reports = []
    try:
        resp = s3.list_objects_v2(Bucket=bucket_name)
        for obj in resp.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith("/report.md") or key.endswith(".md"):
                inc_id = key.split("/")[0] if "/" in key else key.replace(".md", "")
                reports.append(
                    {
                        "incident_id": inc_id,
                        "key": key,
                        "size_bytes": obj.get("Size", 0),
                        "last_modified": str(obj.get("LastModified", "")),
                    }
                )
    except Exception:
        pass

    return reports
