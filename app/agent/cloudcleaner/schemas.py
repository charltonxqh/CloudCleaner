"""Shared Pydantic models and data contracts used across the CloudCleaner
agent. Each section is owned by the workstream noted in its banner comment
so merges stay conflict-free — please keep additions scoped that way.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


# --- Detect / Investigate / Assess / Approval ---
# Owned by: graph/nodes/{detect,investigate,assess,approval}.py


class CloudResource(BaseModel):
    resource_id: str
    resource_type: str
    region: str

    name: str | None = None
    state: str | None = None

    project: str | None = None
    environment: str | None = None
    owner: str | None = None

    tags: dict[str, str] = Field(default_factory=dict)


class AWSEvidence(BaseModel):
    avg_cpu_percent: float | None = None
    network_in_bytes: float | None = None
    network_out_bytes: float | None = None
    estimated_monthly_cost: float | None = None


class GitHubEvidence(BaseModel):
    repo: str | None = None

    latest_commit_at: str | None = None

    pr_number: int | None = None
    pr_status: str | None = None

    branch: str | None = None
    branch_exists: bool | None = None

    last_workflow_run_at: str | None = None
    scheduled_workflow_exists: bool | None = None


class Recommendation(BaseModel):
    action: Literal[
        "keep",
        "investigate_more",
        "stop",
    ]

    reason: str

    confidence: float = Field(
        ge=0,
        le=1,
    )


class ApprovalDecision(BaseModel):
    decision: Literal[
        "approve",
        "keep",
        "investigate_more",
    ]

    approved_by: str | None = None
    reason: str | None = None


# --- Safety / Actions / Evaluation ---
# Owned by: policy/, tools/aws/actions.py, graph/nodes/{execute,verify,rollback}.py
#
# `ResourceContext` is the contract this workstream expects DETECT/INVESTIGATE
# to populate. `PolicyResult` is the contract the HUMAN APPROVAL node consumes.


class ActionType(str, Enum):
    STOP_INSTANCE = "stop_instance"
    START_INSTANCE = "start_instance"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    NEEDS_APPROVAL = "needs_approval"


class ExecutionStatus(str, Enum):
    EXECUTED = "executed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED_DRY_RUN = "skipped_dry_run"


class ResourceContext(BaseModel):
    """Minimal snapshot of a resource needed for policy evaluation.
    Populated upstream by DETECT/INVESTIGATE.
    """

    resource_id: str
    resource_type: str = "ec2_instance"
    region: str
    tags: dict[str, str] = Field(default_factory=dict)
    state: str
    estimated_monthly_cost_usd: float | None = None
    age_days: float | None = None
    last_state_change: datetime | None = None
    recent_activity: bool | None = None
    # True if evidence suggests the related GitHub branch/PR is still active
    # (branch exists and PR isn't merged/closed). None = no GitHub evidence
    # available, or this resource has no GitHub linkage at all.
    github_pr_open: bool | None = None


class Action(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    action_type: ActionType
    resource_id: str
    region: str
    reason: str
    requested_by: str = "cloudcleaner-agent"
    dry_run: bool = False
    force_override: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyViolation(BaseModel):
    rule: str
    message: str
    hard_block: bool


class RiskAssessment(BaseModel):
    action_id: str
    risk_score: int
    risk_level: RiskLevel
    reasons: list[str] = Field(default_factory=list)


class PolicyResult(BaseModel):
    action_id: str
    decision: PolicyDecision
    violations: list[PolicyViolation] = Field(default_factory=list)
    risk_assessment: RiskAssessment
    # How many separate human approvals are needed before EXECUTE may run.
    # 0 when decision is ALLOW (no approval needed) or BLOCK (approval can't
    # help - it's refused outright). Only meaningful when NEEDS_APPROVAL.
    required_approvals: int = 0


class ExecutionResult(BaseModel):
    action_id: str
    status: ExecutionStatus
    previous_state: str | None = None
    new_state: str | None = None
    error: str | None = None
    dry_run: bool = False
    idempotent_noop: bool = False
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VerificationResult(BaseModel):
    action_id: str
    expected_state: str
    actual_state: str
    verified: bool
    attempts: int
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RollbackResult(BaseModel):
    original_action_id: str
    rollback_action: Action
    rollback_execution: ExecutionResult
    rollback_verification: VerificationResult | None = None
    trigger_reason: str
    escalated: bool = False
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
