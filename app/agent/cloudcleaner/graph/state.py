from typing import TypedDict

from cloudcleaner.schemas import (
    ApprovalDecision,
    AWSEvidence,
    CloudResource,
    GitHubEvidence,
    Recommendation,
)


class CloudCleanerState(TypedDict, total=False):
    resource: CloudResource

    aws_evidence: AWSEvidence
    github_evidence: GitHubEvidence

    recommendation: Recommendation

    approval: ApprovalDecision

    action_result: str
    verification_passed: bool

    error: str