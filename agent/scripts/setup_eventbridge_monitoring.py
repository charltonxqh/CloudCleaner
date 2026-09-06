"""Create an EventBridge scheduled API destination for CloudCleaner monitoring."""

import argparse
import json
import time

import boto3
from botocore.exceptions import ClientError


def _account_id(sts) -> str:
    return sts.get_caller_identity()["Account"]


def _ensure_connection(events, name: str, api_key: str) -> str:
    try:
        response = events.describe_connection(Name=name)
        arn = response["ConnectionArn"]
        events.update_connection(
            Name=name,
            AuthorizationType="API_KEY",
            AuthParameters={
                "ApiKeyAuthParameters": {
                    "ApiKeyName": "X-CloudCleaner-Monitor-Key",
                    "ApiKeyValue": api_key,
                }
            },
        )
        return arn
    except events.exceptions.ResourceNotFoundException:
        response = events.create_connection(
            Name=name,
            AuthorizationType="API_KEY",
            AuthParameters={
                "ApiKeyAuthParameters": {
                    "ApiKeyName": "X-CloudCleaner-Monitor-Key",
                    "ApiKeyValue": api_key,
                }
            },
            Description="Authentication for CloudCleaner monitoring endpoint",
        )
        return response["ConnectionArn"]


def _wait_for_connection(events, name: str, timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = events.describe_connection(Name=name)
        state = response.get("ConnectionState")
        if state == "AUTHORIZED":
            return
        if state == "DEAUTHORIZED":
            raise RuntimeError("EventBridge connection became DEAUTHORIZED")
        time.sleep(2)
    raise TimeoutError("EventBridge connection did not become AUTHORIZED in time")


def _ensure_destination(events, name: str, endpoint: str, connection_arn: str) -> str:
    try:
        response = events.describe_api_destination(Name=name)
        events.update_api_destination(
            Name=name,
            ConnectionArn=connection_arn,
            InvocationEndpoint=endpoint,
            HttpMethod="POST",
            InvocationRateLimitPerSecond=1,
            Description="CloudCleaner continuous monitoring trigger",
        )
        return response["ApiDestinationArn"]
    except events.exceptions.ResourceNotFoundException:
        response = events.create_api_destination(
            Name=name,
            ConnectionArn=connection_arn,
            InvocationEndpoint=endpoint,
            HttpMethod="POST",
            InvocationRateLimitPerSecond=1,
            Description="CloudCleaner continuous monitoring trigger",
        )
        return response["ApiDestinationArn"]


def _ensure_role(iam, account_id: str, name: str, destination_arn: str) -> str:
    assume_role_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "events.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }

    try:
        role = iam.get_role(RoleName=name)["Role"]
    except iam.exceptions.NoSuchEntityException:
        role = iam.create_role(
            RoleName=name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy),
            Description="Allows EventBridge to invoke CloudCleaner monitoring",
        )["Role"]

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "events:InvokeApiDestination",
                "Resource": destination_arn,
            }
        ],
    }

    iam.put_role_policy(
        RoleName=name,
        PolicyName="InvokeCloudCleanerMonitoring",
        PolicyDocument=json.dumps(policy),
    )
    return role["Arn"]


def _ensure_rule(
    events,
    name: str,
    rate_minutes: int,
    destination_arn: str,
    role_arn: str,
) -> str:
    response = events.put_rule(
        Name=name,
        ScheduleExpression=f"rate({rate_minutes} minutes)",
        State="ENABLED",
        Description="Runs CloudCleaner continuous monitoring",
    )
    rule_arn = response["RuleArn"]

    events.put_targets(
        Rule=name,
        Targets=[
            {
                "Id": "cloudcleaner-monitor",
                "Arn": destination_arn,
                "RoleArn": role_arn,
                "RetryPolicy": {
                    "MaximumEventAgeInSeconds": 3600,
                    "MaximumRetryAttempts": 2,
                },
            }
        ],
    )
    return rule_arn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--endpoint",
        required=True,
        help="Public HTTPS endpoint, e.g. https://example.com/monitor/run",
    )
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--rate-minutes", type=int, default=5)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--prefix", default="cloudcleaner-monitor")
    args = parser.parse_args()

    if not args.endpoint.startswith("https://"):
        raise SystemExit("--endpoint must use HTTPS")
    if args.rate_minutes < 1:
        raise SystemExit("--rate-minutes must be at least 1")

    session = boto3.Session(region_name=args.region)
    events = session.client("events")
    iam = session.client("iam")
    sts = session.client("sts")

    connection_name = f"{args.prefix}-connection"
    destination_name = f"{args.prefix}-destination"
    role_name = f"{args.prefix}-role"
    rule_name = f"{args.prefix}-schedule"

    connection_arn = _ensure_connection(events, connection_name, args.api_key)
    _wait_for_connection(events, connection_name)
    destination_arn = _ensure_destination(
        events,
        destination_name,
        args.endpoint,
        connection_arn,
    )
    role_arn = _ensure_role(
        iam,
        _account_id(sts),
        role_name,
        destination_arn,
    )
    rule_arn = _ensure_rule(
        events,
        rule_name,
        args.rate_minutes,
        destination_arn,
        role_arn,
    )

    print(
        json.dumps(
            {
                "connection_arn": connection_arn,
                "api_destination_arn": destination_arn,
                "role_arn": role_arn,
                "rule_arn": rule_arn,
                "schedule": f"rate({args.rate_minutes} minutes)",
                "endpoint": args.endpoint,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
