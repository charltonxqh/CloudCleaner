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

    size_gb: int | None = None
    attached_to: str | None = None
    delete_on_termination: bool | None = None
    volume_ids: list[str] = Field(default_factory=list)
    public_ip: str | None = None

    idle_days: int | None = None
    estimated_monthly_cost: float | None = None
    billing_while_stopped: bool = False

    tags: dict[str, str] = Field(default_factory=dict)


class AWSEvidence(BaseModel):
    metric_window_days: int = 7
    avg_cpu_percent: float | None = None
    max_cpu_percent: float | None = None
    idle_days: int | None = None
    network_in_bytes: float | None = None
    network_out_bytes: float | None = None
    estimated_monthly_cost: float | None = None
    billing_while_stopped: bool = False


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
        "retire",
    ]

    reason: str

    confidence: float = Field(ge=0, le=1)

    severity: Literal["low", "medium", "high"] = "low"
    estimated_monthly_saving: float = 0.0


class ApprovalDecision(BaseModel):
    decision: Literal[
        "approve",
        "keep",
        "investigate_more",
    ]

    approved_resource_ids: list[str] = Field(default_factory=list)
    approved_by: str | None = None
    reason: str | None = None

class TeardownStep(BaseModel):
    order: int = 0
    action: str
    resource_id: str
    resource_type: str
    reason: str
    monthly_saving: float = 0.0
    reversible: bool = True
    depends_on: list[str] = Field(default_factory=list)


class RestoreRecipe(BaseModel):
    resource_id: str
    resource_type: str
    instance_type: str | None = None
    image_id: str | None = None
    availability_zone: str | None = None
    security_group_ids: list[str] = Field(default_factory=list)
    volume_snapshots: dict[str, str] = Field(default_factory=dict)
    public_ip: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    note: str = ""


class TeardownPlan(BaseModel):
    root_resource_id: str
    steps: list[TeardownStep] = Field(default_factory=list)
    restore: RestoreRecipe | None = None
    blocked: list[str] = Field(default_factory=list)

    @property
    def total_monthly_saving(self) -> float:
        return round(sum(s.monthly_saving for s in self.steps), 2)

    @property
    def irreversible_steps(self) -> list[TeardownStep]:
        return [s for s in self.steps if not s.reversible]
