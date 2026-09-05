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
    TeardownPlan,
    VerificationResult,
)


class CloudCleanerState(TypedDict, total=False):
    # Detect / Investigate / Assess / Approval
    inventory: list[CloudResource]
    orphans: list[CloudResource]
    volumes: list[CloudResource]
    addresses: list[CloudResource]
    resource: CloudResource

    aws_evidence: AWSEvidence
    github_evidence: GitHubEvidence
    recommendation: Recommendation

    approval: ApprovalDecision
    # How many times the approval node has run for this action. Used to
    # implement double-approval for prod (see routing.route_after_approval).
    approval_rounds: int

    # Safety / Actions / Evaluation
    resource_context: ResourceContext
    pending_action: Action
    policy_result: PolicyResult
    execution_results: list[ExecutionResult]
    verification_results: list[VerificationResult]
    rollback_results: list[RollbackResult]

    # Teardown planning
    plan: TeardownPlan
    action_results: list[dict]
    verification_passed: bool

    force_plan: bool
    run_id: str
    done_reason: str
    error: str
