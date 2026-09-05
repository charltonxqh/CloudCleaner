import os

import boto3

from cloudcleaner.config import AWS_ENDPOINT_URL, AWS_REGION


def _ses_client():
    return boto3.client(
        "ses",
        region_name=AWS_REGION,
        endpoint_url=AWS_ENDPOINT_URL,
    )


def email_enabled() -> bool:
    return bool(os.getenv("SES_FROM_EMAIL"))


def send_owner_notification(
    to_email: str,
    resource,
    recommendation,
    plan=None,
) -> dict:
    from_email = os.getenv("SES_FROM_EMAIL")
    if not from_email:
        raise RuntimeError("SES_FROM_EMAIL is not configured")

    if not to_email:
        raise RuntimeError("resource owner email is not configured")

    resource_name = resource.name or resource.resource_id
    action = recommendation.action.upper()
    monthly_cost = resource.estimated_monthly_cost or 0.0
    saving = recommendation.estimated_monthly_saving or 0.0

    if plan:
        saving = plan.total_monthly_saving or saving

    lines = [
        "CloudCleaner identified a cloud resource that may no longer be required.",
        "",
        f"Resource: {resource.resource_id}",
        f"Name: {resource_name}",
        f"Type: {resource.resource_type}",
        f"Region: {resource.region}",
        f"Environment: {resource.environment or 'unknown'}",
        f"Recommended action: {action}",
        "",
        f"Current cost: ${monthly_cost:.2f}/month",
        f"Potential saving: ${saving:.2f}/month",
        "",
        "Reason:",
        recommendation.reason,
    ]

    if plan and plan.steps:
        lines.extend([
            "",
            "Proposed teardown:",
        ])

        for index, step in enumerate(plan.steps, start=1):
            irreversible = " [IRREVERSIBLE]" if not step.reversible else ""
            lines.append(
                f"{step.order or index}. {step.action} - "
                f"{step.resource_id}{irreversible}"
            )

    lines.extend([
        "",
        "A human reviewer is currently deciding whether to approve or reject this action.",
        "",
        "This notification was sent by CloudCleaner.",
    ])

    subject = f"CloudCleaner review required: {resource.resource_id}"
    body = "\n".join(lines)

    kwargs = {
        "Source": from_email,
        "Destination": {
            "ToAddresses": [to_email],
        },
        "Message": {
            "Subject": {
                "Data": subject,
                "Charset": "UTF-8",
            },
            "Body": {
                "Text": {
                    "Data": body,
                    "Charset": "UTF-8",
                },
            },
        },
    }

    reply_to = os.getenv("SES_REPLY_TO_EMAIL")
    if reply_to:
        kwargs["ReplyToAddresses"] = [reply_to]

    return _ses_client().send_email(**kwargs)