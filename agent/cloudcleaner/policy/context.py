"""Translates DETECT/INVESTIGATE's data shapes (CloudResource, AWSEvidence,
GitHubEvidence) into the ResourceContext this workstream's policy engine
needs. Shared by graph/nodes/policy_check.py (first evaluation, before
approval) and graph/nodes/execute.py (defense-in-depth re-check right
before acting), so both stay consistent.
"""

from datetime import datetime, timezone

from cloudcleaner.schemas import AWSEvidence, CloudResource, GitHubEvidence, ResourceContext

# CPU below this threshold (as a %) counts as "no recent activity" when
# AWSEvidence doesn't give us a direct signal.
ACTIVITY_CPU_THRESHOLD_PERCENT = 5.0

# PR/branch statuses that mean "this is wrapped up, not still active."
_CLOSED_PR_STATUSES = {"merged", "closed"}


def _github_pr_open(github_evidence: GitHubEvidence | None) -> bool | None:
    if github_evidence is None or github_evidence.branch_exists is None:
        return None
    if not github_evidence.branch_exists:
        return False
    return github_evidence.pr_status not in _CLOSED_PR_STATUSES


def _age_days(launch_time: str | None) -> float | None:
    if not launch_time:
        return None
    try:
        launched = datetime.fromisoformat(launch_time.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max((datetime.now(timezone.utc) - launched).total_seconds() / 86400, 0.0)


def build_resource_context(
    resource: CloudResource,
    aws_evidence: AWSEvidence | None,
    github_evidence: GitHubEvidence | None = None,
) -> ResourceContext:
    tags = dict(resource.tags)
    if resource.owner and "Owner" not in tags:
        tags["Owner"] = resource.owner
    if resource.environment and "Environment" not in tags:
        tags["Environment"] = resource.environment

    recent_activity = None
    cost = None
    if aws_evidence is not None:
        cost = aws_evidence.estimated_monthly_cost
        if aws_evidence.avg_cpu_percent is not None:
            recent_activity = aws_evidence.avg_cpu_percent > ACTIVITY_CPU_THRESHOLD_PERCENT

    return ResourceContext(
        resource_id=resource.resource_id,
        resource_type=resource.resource_type,
        region=resource.region,
        tags=tags,
        state=resource.state or "unknown",
        estimated_monthly_cost_usd=cost,
        age_days=_age_days(resource.launch_time),
        last_state_change=resource.last_state_change,
        recent_activity=recent_activity,
        github_pr_open=_github_pr_open(github_evidence),
    )
