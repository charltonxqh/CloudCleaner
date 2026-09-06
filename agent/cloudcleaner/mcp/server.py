"""Read-only MCP server for CloudCleaner investigation tools."""

import os

from github import GithubException
from mcp.server import MCPServer
from requests.exceptions import RequestException

from cloudcleaner.schemas import GitHubEvidence
from cloudcleaner.tools.aws.addresses import list_elastic_ips as _list_elastic_ips
from cloudcleaner.tools.aws.inventory import list_ec2_instances as _list_ec2_instances
from cloudcleaner.tools.aws.metrics import get_ec2_usage_evidence as _get_ec2_usage_evidence
from cloudcleaner.tools.aws.volumes import list_volumes as _list_volumes
from cloudcleaner.tools.github.cicd import get_cicd_evidence
from cloudcleaner.tools.github.client import get_github_client
from cloudcleaner.tools.github.commits import get_latest_commit_evidence
from cloudcleaner.tools.github.pull_requests import get_latest_pr_evidence

mcp = MCPServer("CloudCleaner")


@mcp.tool()
def list_ec2_instances() -> dict:
    """List EC2 instances visible to CloudCleaner."""
    resources = _list_ec2_instances()
    return {
        "resources": [
            resource.model_dump(mode="json")
            for resource in resources
        ]
    }


@mcp.tool()
def list_volumes(only_unattached: bool = False) -> dict:
    """List EBS volumes visible to CloudCleaner."""
    resources = _list_volumes(only_unattached)
    return {
        "resources": [
            resource.model_dump(mode="json")
            for resource in resources
        ]
    }


@mcp.tool()
def list_elastic_ips() -> dict:
    """List Elastic IP addresses visible to CloudCleaner."""
    resources = _list_elastic_ips()
    return {
        "resources": [
            resource.model_dump(mode="json")
            for resource in resources
        ]
    }


@mcp.tool()
def get_ec2_usage_evidence(instance_id: str, days: int) -> dict:
    """Collect CloudWatch usage evidence for an EC2 instance."""
    evidence = _get_ec2_usage_evidence(instance_id, days)
    return evidence.model_dump(mode="json")


@mcp.tool()
def get_github_evidence(repo: str) -> dict:
    """Collect repository, commit, pull request, branch, and CI/CD evidence."""
    if not repo:
        return GitHubEvidence().model_dump(mode="json")

    github = get_github_client()

    try:
        github.get_repo(repo)
        commit_evidence = get_latest_commit_evidence(repo) or {}
        pr_evidence = get_latest_pr_evidence(repo) or {}
        cicd_evidence = get_cicd_evidence(repo) or {}
    except GithubException as exc:
        if exc.status == 404:
            return GitHubEvidence(repo=repo).model_dump(mode="json")
        raise
    except RequestException:
        return GitHubEvidence(repo=repo).model_dump(mode="json")

    return GitHubEvidence(
        repo=repo,
        **commit_evidence,
        **pr_evidence,
        **cicd_evidence,
    ).model_dump(mode="json")


def main():
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=int(os.getenv("CLOUDCLEANER_MCP_PORT", "8130")),
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()