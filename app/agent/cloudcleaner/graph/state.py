from langchain.agents import AgentState as BaseAgentState

from cloudcleaner.schemas import (
    Action,
    ExecutionResult,
    PolicyResult,
    ResourceContext,
    RollbackResult,
    VerificationResult,
)


class CloudCleanerState(BaseAgentState):
    resource_context: ResourceContext | None
    pending_action: Action | None
    policy_result: PolicyResult | None
    execution_results: list[ExecutionResult]
    verification_results: list[VerificationResult]
    rollback_results: list[RollbackResult]
