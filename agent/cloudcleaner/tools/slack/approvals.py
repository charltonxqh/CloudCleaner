import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qs


def verify_slack_signature(headers, raw_body: bytes) -> bool:
    signing_secret = os.getenv("SLACK_SIGNING_SECRET")
    if not signing_secret:
        return False

    timestamp = headers.get("x-slack-request-timestamp")
    signature = headers.get("x-slack-signature")
    if not timestamp or not signature:
        return False

    try:
        request_time = int(timestamp)
    except ValueError:
        return False

    if abs(time.time() - request_time) > 60 * 5:
        return False

    base = b"v0:" + timestamp.encode("utf-8") + b":" + raw_body
    expected = "v0=" + hmac.new(
        signing_secret.encode("utf-8"), base, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_interaction(raw_body: bytes) -> dict:
    form = parse_qs(raw_body.decode("utf-8"))
    raw_payload = form.get("payload", [None])[0]
    if not raw_payload:
        raise ValueError("missing Slack interaction payload")

    payload = json.loads(raw_payload)
    actions = payload.get("actions") or []
    if not actions:
        raise ValueError("missing Slack action")

    action = actions[0]
    action_id = action.get("action_id")
    if action_id not in {"cloudcleaner_approve", "cloudcleaner_reject"}:
        raise ValueError("unknown Slack action")

    value = json.loads(action.get("value") or "{}")
    thread_id = value.get("thread_id")
    resource_id = value.get("resource_id")
    if not thread_id or not resource_id:
        raise ValueError("missing CloudCleaner thread or resource id")

    user = payload.get("user") or {}
    channel = payload.get("channel") or {}
    message = payload.get("message") or {}

    return {
        "decision": "approve" if action_id == "cloudcleaner_approve" else "reject",
        "thread_id": thread_id,
        "resource_id": resource_id,
        "approved_by": f"slack:{user.get('id', 'unknown')}",
        "user_name": user.get("username") or user.get("name") or user.get("id", "unknown"),
        "channel_id": channel.get("id"),
        "message_ts": message.get("ts"),
    }
