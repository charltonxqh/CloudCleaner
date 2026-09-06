import os
from functools import lru_cache

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
- Absent CloudWatch metrics for a volume, an address or a snapshot is normal, not suspicious.
  Those resources do not emit CPU metrics.
- CPU is the EC2 signal and only the EC2 signal. Judge every other type by the metric named
  in metric_source, which is the one AWS actually publishes for it:
    NAT gateway    BytesOutToDestination. It has no stopped state; it bills until deleted.
    Load balancer  RequestCount (or ActiveFlowCount). The hourly base rate is charged even
                   with zero requests and zero healthy targets.
    RDS instance   DatabaseConnections. A STOPPED database still bills for its allocated
                   storage, and AWS restarts it automatically 7 days after it was stopped,
                   so "stopped" is a bill with a timer on it, not a saving.
    ElastiCache    CurrConnections. There is no stopped state; it bills until deleted.
- A snapshot that backs an AMI cannot be deleted until that image is deregistered. Say so
  rather than recommending a delete that AWS would refuse.

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


# Groq currently exposes per-token pricing in model metadata for many hosted models.
# These published rates are only a fallback if that metadata is unavailable.
_FALLBACK_PRICING_PER_TOKEN = {
    "openai/gpt-oss-20b": {
        "input": 0.075 / 1_000_000,
        "cached_input": 0.037 / 1_000_000,
        "output": 0.30 / 1_000_000,
    },
    "openai/gpt-oss-120b": {
        "input": 0.15 / 1_000_000,
        "cached_input": 0.075 / 1_000_000,
        "output": 0.60 / 1_000_000,
    },
}


def _float_env(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


@lru_cache(maxsize=None)
def _pricing_for_model(model: str) -> tuple[dict[str, float] | None, str | None]:
    input_override = _float_env("GROQ_INPUT_PRICE_PER_1M")
    output_override = _float_env("GROQ_OUTPUT_PRICE_PER_1M")
    cached_override = _float_env("GROQ_CACHED_INPUT_PRICE_PER_1M")
    if input_override is not None and output_override is not None:
        return {
            "input": input_override / 1_000_000,
            "cached_input": (
                cached_override / 1_000_000
                if cached_override is not None
                else input_override / 1_000_000
            ),
            "output": output_override / 1_000_000,
        }, "env"

    try:
        from groq import Groq

        metadata = Groq().models.retrieve(model)
        raw = metadata.model_dump() if hasattr(metadata, "model_dump") else dict(metadata)
        pricing = raw.get("pricing") or {}
        prompt = pricing.get("prompt")
        completion = pricing.get("completion")
        cached = pricing.get("input_cache_read")

        if prompt is not None and completion is not None:
            prompt_rate = float(prompt)
            completion_rate = float(completion)
            cached_rate = float(cached) if cached is not None else prompt_rate
            return {
                "input": prompt_rate,
                "cached_input": cached_rate,
                "output": completion_rate,
            }, "groq_api"
    except Exception:
        pass

    fallback = _FALLBACK_PRICING_PER_TOKEN.get(model)
    return (fallback, "fallback") if fallback else (None, None)


def _usage_from_raw(raw) -> dict[str, int]:
    usage_metadata = getattr(raw, "usage_metadata", None) or {}
    response_metadata = getattr(raw, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or response_metadata.get("usage") or {}

    input_tokens = (
        usage_metadata.get("input_tokens")
        or token_usage.get("prompt_tokens")
        or 0
    )
    output_tokens = (
        usage_metadata.get("output_tokens")
        or token_usage.get("completion_tokens")
        or 0
    )
    total_tokens = (
        usage_metadata.get("total_tokens")
        or token_usage.get("total_tokens")
        or input_tokens + output_tokens
    )

    input_details = usage_metadata.get("input_token_details") or {}
    prompt_details = token_usage.get("prompt_tokens_details") or {}
    cached_tokens = (
        input_details.get("cache_read")
        or input_details.get("cached_tokens")
        or prompt_details.get("cached_tokens")
        or 0
    )

    return {
        "prompt_tokens": int(input_tokens or 0),
        "completion_tokens": int(output_tokens or 0),
        "total_tokens": int(total_tokens or 0),
        "cached_tokens": int(cached_tokens or 0),
    }


def _llm_cost(usage: dict[str, int], model: str) -> tuple[float | None, str | None]:
    pricing, source = _pricing_for_model(model)
    if pricing is None:
        return None, None

    prompt_tokens = usage["prompt_tokens"]
    cached_tokens = min(usage["cached_tokens"], prompt_tokens)
    uncached_tokens = prompt_tokens - cached_tokens

    cost = (
        uncached_tokens * pricing["input"]
        + cached_tokens * pricing["cached_input"]
        + usage["completion_tokens"] * pricing["output"]
    )
    return cost, source


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
        result = (
            _model()
            .with_structured_output(
                Recommendation,
                method="json_schema",
                include_raw=True,
            )
            .invoke(prompt)
        )
        rec = result.get("parsed")
        if rec is None:
            raise ValueError(result.get("parsing_error") or "structured response was not parsed")

        usage = _usage_from_raw(result.get("raw"))
        llm_cost_usd, pricing_source = _llm_cost(usage, GROQ_MODEL)
    except Exception as e:
        log.emit("assess", "error", resource.resource_id, f"llm failed: {e}; falling back to rules")
        rec = rules_only_verdict(resource, aws, github)
        usage = None
        llm_cost_usd = None
        pricing_source = None

    saving = (resource.monthly_saving_if_stopped or 0.0) if rec.action == "stop" else \
        (resource.estimated_monthly_cost or 0.0) if rec.action == "retire" else 0.0
    rec.severity, rec.estimated_monthly_saving = severity, saving
    log.emit("assess", "decision", resource.resource_id,
             f"{rec.action} ({rec.confidence:.0%}) - {rec.reason}",
             severity=severity,
             model=GROQ_MODEL if usage is not None else None,
             prompt_tokens=usage["prompt_tokens"] if usage is not None else None,
             completion_tokens=usage["completion_tokens"] if usage is not None else None,
             total_tokens=usage["total_tokens"] if usage is not None else None,
             cached_tokens=usage["cached_tokens"] if usage is not None else None,
             llm_cost_usd=llm_cost_usd,
             pricing_source=pricing_source)

    return {"recommendation": rec}