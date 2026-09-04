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

    prompt = PROMPT.format(
        prior=f"{prior.action} - {prior.reason}",
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
