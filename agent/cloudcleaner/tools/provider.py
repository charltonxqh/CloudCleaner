"""Resolve the data source at call time, not import time."""

import os

from cloudcleaner.schemas import CloudResource, GitHubEvidence


def _fixture() -> bool:
    return os.getenv("CLOUDCLEANER_PROVIDER", "aws").lower() == "fixture"


def _mcp() -> bool:
    from cloudcleaner.mcp.client import enabled
    return enabled()


def list_ec2_instances():
    if _fixture():
        from cloudcleaner.fixtures.demo import list_ec2_instances as fn
        return fn()

    if _mcp():
        from cloudcleaner.mcp.client import call_tool

        payload = call_tool("list_ec2_instances")
        return [
            CloudResource.model_validate(resource)
            for resource in payload.get("resources", [])
        ]

    from cloudcleaner.tools.aws.inventory import list_ec2_instances as fn
    return fn()


def list_volumes(only_unattached: bool = False):
    if _fixture():
        from cloudcleaner.fixtures.demo import list_volumes as fn
        return fn(only_unattached)

    if _mcp():
        from cloudcleaner.mcp.client import call_tool

        payload = call_tool(
            "list_volumes",
            {"only_unattached": only_unattached},
        )
        return [
            CloudResource.model_validate(resource)
            for resource in payload.get("resources", [])
        ]

    from cloudcleaner.tools.aws.volumes import list_volumes as fn
    return fn(only_unattached)


def list_elastic_ips():
    if _fixture():
        from cloudcleaner.fixtures.demo import list_elastic_ips as fn
        return fn()

    if _mcp():
        from cloudcleaner.mcp.client import call_tool

        payload = call_tool("list_elastic_ips")
        return [
            CloudResource.model_validate(resource)
            for resource in payload.get("resources", [])
        ]

    from cloudcleaner.tools.aws.addresses import list_elastic_ips as fn
    return fn()


def get_ec2_usage_evidence(instance_id: str, days: int | None = None):
    from cloudcleaner.config import METRIC_WINDOW_DAYS
    from cloudcleaner.schemas import AWSEvidence

    days = days or METRIC_WINDOW_DAYS

    if _fixture():
        from cloudcleaner.fixtures.demo import get_ec2_usage_evidence as fn
        return fn(instance_id, days)

    if _mcp():
        from cloudcleaner.mcp.client import call_tool

        payload = call_tool(
            "get_ec2_usage_evidence",
            {
                "instance_id": instance_id,
                "days": days,
            },
        )
        return AWSEvidence.model_validate(payload)

    from cloudcleaner.tools.aws.metrics import get_ec2_usage_evidence as fn
    return fn(instance_id, days)


def get_github_evidence(repo: str | None = None) -> GitHubEvidence:
    if not repo:
        return GitHubEvidence()

    if _fixture():
        from cloudcleaner.fixtures.demo import get_github_evidence as fn
        return fn(repo)

    if _mcp():
        from cloudcleaner.mcp.client import call_tool

        payload = call_tool(
            "get_github_evidence",
            {"repo": repo},
        )
        return GitHubEvidence.model_validate(payload)

    from github import GithubException
    from requests.exceptions import RequestException

    from cloudcleaner.tools.github.client import get_github_client
    from cloudcleaner.tools.github.commits import get_latest_commit_evidence
    from cloudcleaner.tools.github.pull_requests import get_latest_pr_evidence
    from cloudcleaner.tools.github.cicd import get_cicd_evidence

    github = get_github_client()

    try:
        github.get_repo(repo)
        commit_evidence = get_latest_commit_evidence(repo) or {}
        pr_evidence = get_latest_pr_evidence(repo) or {}
        cicd_evidence = get_cicd_evidence(repo) or {}
    except GithubException as exc:
        if exc.status == 404:
            return GitHubEvidence(repo=repo)
        raise
    except RequestException:
        return GitHubEvidence(repo=repo)

    return GitHubEvidence(
        repo=repo,
        **commit_evidence,
        **pr_evidence,
        **cicd_evidence,
    )