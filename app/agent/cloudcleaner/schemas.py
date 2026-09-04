from typing import Literal

from pydantic import BaseModel, Field


class CloudResource(BaseModel):
    resource_id: str
    resource_type: str
    region: str

    name: str | None = None
    state: str | None = None
    
    instance_type: str | None = None
    launch_time: str | None = None

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