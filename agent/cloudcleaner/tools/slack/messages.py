import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN', '')}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as e:
        raise RuntimeError(f"Slack API request failed: {e}") from e

    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error', 'unknown_error')}")
    return data


def slack_enabled() -> bool:
    return bool(os.getenv("SLACK_BOT_TOKEN") and os.getenv("SLACK_CHANNEL_ID"))


def send_approval_request(
    thread_id: str,
    payload: dict,
    owner_email: str | None = None,
) -> dict | None:
    if not slack_enabled():
        return None

    resource = payload["resource"]
    recommendation = payload["recommendation"]
    plan = payload.get("plan")

    saving = recommendation.get("estimated_monthly_saving") or 0.0
    if recommendation.get("action") == "stop":
        saving = resource.get("monthly_saving_if_stopped") or saving
    elif plan:
        saving = plan.get("total_monthly_saving") or saving

    details = [
        f"*Resource:* `{resource['id']}`",
        f"*Action:* {recommendation['action'].upper()}",
        f"*Current cost:* ${resource.get('monthly_cost') or 0:.2f}/mo",
        f"*Estimated saving:* ${saving:.2f}/mo",
        f"*Reason:* {recommendation['reason']}",
    ]
    if plan:
        steps = plan.get("steps", [])
        step_lines = []

        for index, step in enumerate(steps, start=1):
            order = step.get("order") or index
            action = step.get("action") or "unknown_action"
            resource_id = step.get("resource_id") or ""
            irreversible = " ⚠ irreversible" if not step.get("reversible", True) else ""

            step_lines.append(
                f"{order}. `{action}` — `{resource_id}`{irreversible}"
            )

        if step_lines:
            details.append("*Teardown plan:*\n" + "\n".join(step_lines))
        else:
            details.append("*Teardown plan:* No teardown steps.")

        irreversible_count = plan.get("irreversible_count", 0)
        if irreversible_count:
            details.append(
                f"*Irreversible actions:* {irreversible_count}"
            )

    action_value = json.dumps({
        "thread_id": thread_id,
        "resource_id": resource["id"],
    })

    actions = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Approve"},
            "style": "primary",
            "action_id": "cloudcleaner_approve",
            "value": action_value,
        },
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Reject"},
            "style": "danger",
            "action_id": "cloudcleaner_reject",
            "value": action_value,
        },
    ]

    if owner_email:
        actions.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Email Owner"},
                "action_id": "cloudcleaner_email_owner",
                "value": action_value,
            }
        )

    return _post_json(
        "https://slack.com/api/chat.postMessage",
        {
            "channel": os.environ["SLACK_CHANNEL_ID"],
            "text": f"CloudCleaner approval required for {resource['id']}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*CloudCleaner approval required*\n" + "\n".join(details),
                    },
                },
                {
                    "type": "actions",
                    "elements": actions,
                },
            ],
        },
    )


def update_approval_message(channel: str, ts: str, text: str) -> dict | None:
    if not slack_enabled():
        return None
    return _post_json(
        "https://slack.com/api/chat.update",
        {
            "channel": channel,
            "ts": ts,
            "text": text,
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text},
                }
            ],
        },
    )


def send_notification_status(
    channel: str,
    thread_ts: str,
    text: str,
) -> dict | None:
    if not slack_enabled():
        return None

    return _post_json(
        "https://slack.com/api/chat.postMessage",
        {
            "channel": channel,
            "thread_ts": thread_ts,
            "text": text,
        },
    )