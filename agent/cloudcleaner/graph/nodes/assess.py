from cloudcleaner.config import AI_ENABLED, GROQ_MODEL
from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.policy.risk import classify_severity, rules_only_verdict

PROMPT = """You are CloudCleaner, a cloud lifecycle investigation agent.

Judge the evidence below and return one verdict:

- keep             evidence of recent or ongoing use
- stop             idle, but terminating would be premature
- retire           idle with no sign of use, and it is costing money
- investigate_more ONLY when the evidence genuinely contradicts itself or is absent

You are not the last line of defence. Nothing you recommend is executed blindly: stop actions
pass through deterministic policy checks, and retirement actions are expanded into an ordered
teardown plan before approval and execution. So do not hedge to be safe. "investigate_more"
on clear-cut waste is a wrong answer, not a cautious one.

Facts that matter:
- A stopped instance is NOT free. Attached EBS volumes and public IPv4 addresses keep billing.
- An unattached EBS volume or an unassociated Elastic IP has no function at all. It is pure waste.
- Absent CloudWatch metrics for a volume or an address is normal, not suspicious. Those
  resources do not emit CPU metrics.

A deterministic rules engine, which sees the same evidence, proposes: {prior}
Agree with it unless the evidence gives you a specific reason not to.
{memory}

Resource:
{resource}

AWS evidence:
{aws}

GitHub and CI/CD evidence:
{github}

Answer in one or two sentences, citing the numbers you used.
"""


def _model():
    from langchain_groq import ChatGroq
    return ChatGroq(model=GROQ_MODEL, temperature=0)


def _memory_note(resource_id: str) -> str:
    """What we already concluded about this resource, phrased for the prompt.

    Previous automated assessments are historical context. Explicit human
    approval or rejection is recorded separately and stated plainly.
    """
    from cloudcleaner.storage.repository import recall

    memory = recall(resource_id)
    if not memory:
        return ""

    lines = [f"\nYou have looked at this resource {memory['times_seen']} time(s) before."]

    if memory.get("human_decision") == "reject":
        decided_by = memory.get("human_decided_by") or "a human"
        lines.append(
            f"The previous proposed action was explicitly REJECTED by {decided_by} "
            f"on {memory['human_decided_at']}. Consider that governance decision, "
            "but re-evaluate the resource from the current evidence."
        )
    elif memory.get("human_decision") == "approve":
        decided_by = memory.get("human_decided_by") or "a human"
        lines.append(
            f"A previous proposed action was explicitly APPROVED by {decided_by} "
            f"on {memory['human_decided_at']}."
        )

    if memory.get("last_verdict"):
        lines.append(
            f"A previous automated assessment was '{memory['last_verdict']}': "
            f"{memory['last_reason']}. Treat this as historical context only; "
            "base the current verdict on the current evidence."
        )

    return "\n".join(lines)


def assess_node(state: CloudCleanerState):
    resource = state["resource"]
    aws = state["aws_evidence"]
    github = state["github_evidence"]

    severity = classify_severity(resource, aws)
    if not AI_ENABLED:
        rec = rules_only_verdict(resource, aws, github)
        saving = (resource.monthly_saving_if_stopped or 0.0) if rec.action == "stop" else \
            (resource.estimated_monthly_cost or 0.0) if rec.action == "retire" else 0.0
        rec.severity, rec.estimated_monthly_saving = severity, saving
        log.emit("assess", "decision", resource.resource_id, f"rules-only: {rec.action}")
        return {"recommendation": rec}

    from cloudcleaner.schemas import Recommendation

    prior = rules_only_verdict(resource, aws, github)

    memory = _memory_note(resource.resource_id)
    if memory:
        log.emit("assess", "check", resource.resource_id, "recalled prior decisions")

    prompt = PROMPT.format(
        prior=f"{prior.action} - {prior.reason}",
        memory=memory,
        resource=resource.model_dump_json(indent=2),
        aws=aws.model_dump_json(indent=2),
        github=github.model_dump_json(indent=2),
    )

    try:
        # json_schema, not the default tool-calling path: Groq's tool calling on
        # gpt-oss-20b fails on prompts this long, emitting a tool type of
        # "functions.Recommendation" or refusing tool choice outright. Measured
        # at 0/4 with tool calling and 4/4 with json_schema on the same inputs.
        rec = (
            _model()
            .with_structured_output(Recommendation, method="json_schema")
            .invoke(prompt)
        )
    except Exception as e:
        log.emit("assess", "error", resource.resource_id, f"llm failed: {e}; falling back to rules")
        rec = rules_only_verdict(resource, aws, github)

    saving = (resource.monthly_saving_if_stopped or 0.0) if rec.action == "stop" else \
        (resource.estimated_monthly_cost or 0.0) if rec.action == "retire" else 0.0
    rec.severity, rec.estimated_monthly_saving = severity, saving
    log.emit("assess", "decision", resource.resource_id,
             f"{rec.action} ({rec.confidence:.0%}) - {rec.reason}", severity=severity)

    return {"recommendation": rec}