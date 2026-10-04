"""IAM role querying and least-privilege security auditing module."""

import json
from typing import Any, Dict, List
from urllib.parse import unquote

from infraops.server.aws.client import get_client, seed_mock_environment


def _parse_policy_doc(doc_raw: Any) -> Dict[str, Any]:
    """Parse policy document whether it is a string, URL-encoded string, or dict."""
    if isinstance(doc_raw, dict):
        return doc_raw
    if isinstance(doc_raw, str):
        try:
            return json.loads(doc_raw)
        except Exception:
            try:
                return json.loads(unquote(doc_raw))
            except Exception:
                return {}
    return {}


def _audit_policy_statements(policy_name: str, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scan IAM policy statements for wildcard actions or resources violating least privilege."""
    findings = []
    statements = doc.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]

    for stmt in statements:
        if stmt.get("Effect") != "Allow":
            continue

        actions = stmt.get("Action", [])
        if isinstance(actions, str):
            actions = [actions]

        resources = stmt.get("Resource", [])
        if isinstance(resources, str):
            resources = [resources]

        has_wildcard_action = "*" in actions
        has_wildcard_resource = "*" in resources

        if has_wildcard_action and has_wildcard_resource:
            findings.append(
                {
                    "severity": "CRITICAL",
                    "policy_name": policy_name,
                    "issue": "Wildcard administrator access",
                    "detail": "Statement allows Action: '*' across Resource: '*'",
                    "sid": stmt.get("Sid", "unnamed"),
                }
            )
        elif has_wildcard_action:
            findings.append(
                {
                    "severity": "HIGH",
                    "policy_name": policy_name,
                    "issue": "Unrestricted wildcard action",
                    "detail": "Statement allows Action: '*' across specific resources",
                    "sid": stmt.get("Sid", "unnamed"),
                }
            )
        elif has_wildcard_resource:
            has_condition = "Condition" in stmt
            findings.append(
                {
                    "severity": "INFO" if has_condition else "WARNING",
                    "policy_name": policy_name,
                    "issue": "Condition-scoped resource target"
                    if has_condition
                    else "Unscoped resource target",
                    "detail": f"Actions ({', '.join(actions[:3])}) apply to Resource: '*' (Condition: {has_condition})",
                    "sid": stmt.get("Sid", "unnamed"),
                }
            )

    return findings


def list_roles() -> List[Dict[str, Any]]:
    """List IAM roles enriched with attached policies and least-privilege audit findings."""
    seed_mock_environment()
    iam = get_client("iam")
    resp = iam.list_roles()

    roles = []
    for r in resp.get("Roles", []):
        role_name = r.get("RoleName", "")
        arn = r.get("Arn", "")

        # Skip AWS service-linked roles from deep scrutiny
        if "/aws-service-role/" in arn:
            continue

        # Fetch attached policies
        attached_policies = []
        role_findings = []

        try:
            p_resp = iam.list_attached_role_policies(RoleName=role_name)
            for p in p_resp.get("AttachedPolicies", []):
                p_arn = p.get("PolicyArn", "")
                p_name = p.get("PolicyName", "")

                policy_info: Dict[str, Any] = {"name": p_name, "arn": p_arn}
                try:
                    pol_detail = iam.get_policy(PolicyArn=p_arn)["Policy"]
                    default_ver = pol_detail.get("DefaultVersionId")
                    ver_resp = iam.get_policy_version(PolicyArn=p_arn, VersionId=default_ver)
                    doc = _parse_policy_doc(ver_resp["PolicyVersion"].get("Document", {}))
                    policy_findings = _audit_policy_statements(p_name, doc)
                    role_findings.extend(policy_findings)
                    policy_info["findings"] = policy_findings
                except Exception:
                    policy_info["findings"] = []

                attached_policies.append(policy_info)
        except Exception:
            pass

        # Fetch inline policies
        try:
            inline_resp = iam.list_role_policies(RoleName=role_name)
            for inline_name in inline_resp.get("PolicyNames", []):
                try:
                    inline_doc_resp = iam.get_role_policy(
                        RoleName=role_name, PolicyName=inline_name
                    )
                    doc = _parse_policy_doc(inline_doc_resp.get("PolicyDocument", {}))
                    inline_findings = _audit_policy_statements(inline_name, doc)
                    role_findings.extend(inline_findings)
                    attached_policies.append(
                        {
                            "name": inline_name,
                            "arn": f"inline:{inline_name}",
                            "findings": inline_findings,
                        }
                    )
                except Exception:
                    pass
        except Exception:
            pass

        roles.append(
            {
                "role_name": role_name,
                "arn": arn,
                "description": r.get("Description", ""),
                "create_date": str(r.get("CreateDate", "")),
                "attached_policies": attached_policies,
                "findings": role_findings,
                "is_least_privilege": not any(
                    f["severity"] in ["CRITICAL", "HIGH"] for f in role_findings
                ),
            }
        )

    return roles


def audit_least_privilege() -> Dict[str, Any]:
    """Perform aggregate least-privilege audit across all custom IAM roles."""
    roles = list_roles()
    total_roles = len(roles)
    compliant_roles = sum(1 for r in roles if r["is_least_privilege"])
    findings = [{"role_name": r["role_name"], "finding": f} for r in roles for f in r["findings"]]

    return {
        "total_roles": total_roles,
        "compliant_roles": compliant_roles,
        "non_compliant_roles": total_roles - compliant_roles,
        "compliance_score_percent": round(
            (compliant_roles / total_roles * 100.0) if total_roles > 0 else 100.0, 1
        ),
        "findings": findings,
    }
