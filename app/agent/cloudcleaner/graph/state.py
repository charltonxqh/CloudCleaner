from typing import TypedDict

from cloudcleaner.schemas import (
    Action,
    ApprovalDecision,
    AWSEvidence,
    CloudResource,
    ExecutionResult,
    GitHubEvidence,
    PolicyResult,
    Recommendation,
    ResourceContext,
    RollbackResult,
    VerificationResult,
)


class CloudCleanerState(TypedDict, total=False):
    # Detect / Investigate / Assess / Approval
    resource: CloudResource
    aws_evidence: AWSEvidence
    github_evidence: GitHubEvidence
    recommendation: Recommendation
    approval: ApprovalDecision

    # Safety / Actions / Evaluation
    resource_context: ResourceContext
    pending_action: Action
    policy_result: PolicyResult
    execution_results: list[ExecutionResult]
    verification_results: list[VerificationResult]
    rollback_results: list[RollbackResult]

    error: str
