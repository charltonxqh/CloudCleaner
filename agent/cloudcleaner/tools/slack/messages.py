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


def send_approval_request(thread_id: str, payload: dict) -> dict | None:
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
        details.append(
            f"*Teardown:* {len(plan.get('steps', []))} steps, "
            f"{plan.get('irreversible_count', 0)} irreversible"
        )

    action_value = json.dumps({
        "thread_id": thread_id,
        "resource_id": resource["id"],
    })

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
                    "elements": [
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
                    ],
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
