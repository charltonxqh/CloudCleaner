"""Deterministic guardrails. These run outside the LLM and cannot be argued with."""

from datetime import datetime, timedelta, timezone

from cloudcleaner.schemas import CloudResource

PROTECTED_ENVIRONMENTS = {"prod", "production", "live"}
PROTECTED_TAGS = {"DoNotDelete", "cloudcleaner:ignore", "Retain"}
MIN_AGE_DAYS = 7


def _age_days(resource: CloudResource) -> int | None:
    if not resource.launch_time:
        return None
    try:
        launched = datetime.fromisoformat(resource.launch_time.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - launched).days


def check(resource: CloudResource, allow_untagged: bool = False) -> list[str]:
    """Returns blocking reasons. Empty list means the resource may be acted on."""
    blocks = []

    env = (resource.environment or "").lower()
    if env in PROTECTED_ENVIRONMENTS:
        blocks.append(f"Environment={resource.environment} is protected")

    for tag in PROTECTED_TAGS:
        if tag in resource.tags:
            blocks.append(f"tagged {tag}")

    age = _age_days(resource)
    if age is not None and age < MIN_AGE_DAYS:
        blocks.append(f"only {age} days old, minimum is {MIN_AGE_DAYS}")

    if not allow_untagged and not resource.tags:
        blocks.append("no tags, ownership unknown")

    return blocks


def is_safe(resource: CloudResource, allow_untagged: bool = False) -> bool:
    return not check(resource, allow_untagged)
