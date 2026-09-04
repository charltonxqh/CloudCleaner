from typing import TypedDict

from cloudcleaner.schemas import (
    ApprovalDecision,
    AWSEvidence,
    CloudResource,
    GitHubEvidence,
    Recommendation,
    TeardownPlan,
)


class CloudCleanerState(TypedDict, total=False):
    inventory: list[CloudResource]
    orphans: list[CloudResource]
    volumes: list[CloudResource]
    addresses: list[CloudResource]
    resource: CloudResource

    aws_evidence: AWSEvidence
    github_evidence: GitHubEvidence

    recommendation: Recommendation
    plan: TeardownPlan

    approval: ApprovalDecision

    action_results: list[dict]
    verification_passed: bool

    force_plan: bool
    run_id: str
    done_reason: str
    error: str
