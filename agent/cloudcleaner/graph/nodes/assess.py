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

You are not the last line of defence. Nothing you recommend is executed: a human reviews the
full ordered plan and types the resource ID to approve it, and every volume is snapshotted
first. So do not hedge to be safe. "investigate_more" on clear-cut waste is a wrong answer,
not a cautious one.

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

    A human who kept something once should not be asked the same question every
    week, so a past decision is stated plainly and the model is told to weigh it.
    """
    from cloudcleaner.storage.repository import recall

    memory = recall(resource_id)
    if not memory:
        return ""

    lines = [f"\nYou have looked at this resource {memory['times_seen']} time(s) before."]

    if memory.get("human_decision") == "keep":
        lines.append(
            f"A human explicitly chose to KEEP it on {memory['human_decided_at']}. "
            "Do not recommend retiring it again unless the evidence has changed since then "
            "- say what changed if you do."
        )
    elif memory.get("human_decision") == "approve":
        lines.append("A human previously approved action on this resource.")

    if memory.get("last_verdict"):
        lines.append(f"Your last verdict was '{memory['last_verdict']}': {memory['last_reason']}")

    if (memory.get("times_kept") or 0) >= 2:
        lines.append(
            f"It has been kept {memory['times_kept']} times. Repeatedly re-proposing a "
            "retirement that keeps getting refused wastes the reviewer's attention."
        )

    return "\n".join(lines)


def assess_node(state: CloudCleanerState):
    resource = state["resource"]
    aws = state["aws_evidence"]
    github = state["github_evidence"]

    severity = classify_severity(resource, aws)
    saving = resource.estimated_monthly_cost or 0.0

    if not AI_ENABLED:
        rec = rules_only_verdict(resource, aws)
        rec.severity, rec.estimated_monthly_saving = severity, saving
        log.emit("assess", "decision", resource.resource_id, f"rules-only: {rec.action}")
        return {"recommendation": rec}

    from cloudcleaner.schemas import Recommendation

    prior = rules_only_verdict(resource, aws)

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
        rec = _model().with_structured_output(Recommendation).invoke(prompt)
    except Exception as e:
        log.emit("assess", "error", resource.resource_id, f"llm failed: {e}; falling back to rules")
        rec = rules_only_verdict(resource, aws)

    rec.severity, rec.estimated_monthly_saving = severity, saving
    log.emit("assess", "decision", resource.resource_id,
             f"{rec.action} ({rec.confidence:.0%}) - {rec.reason}", severity=severity)

    return {"recommendation": rec}
