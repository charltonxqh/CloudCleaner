"""Resolve the data source at call time, not import time."""

import os

from cloudcleaner.schemas import GitHubEvidence


def _fixture() -> bool:
    return os.getenv("CLOUDCLEANER_PROVIDER", "aws").lower() == "fixture"


def list_ec2_instances():
    if _fixture():
        from cloudcleaner.fixtures.demo import list_ec2_instances as fn
    else:
        from cloudcleaner.tools.aws.inventory import list_ec2_instances as fn
    return fn()


def list_volumes(only_unattached: bool = False):
    if _fixture():
        from cloudcleaner.fixtures.demo import list_volumes as fn
    else:
        from cloudcleaner.tools.aws.volumes import list_volumes as fn
    return fn(only_unattached)


def list_elastic_ips():
    if _fixture():
        from cloudcleaner.fixtures.demo import list_elastic_ips as fn
    else:
        from cloudcleaner.tools.aws.addresses import list_elastic_ips as fn
    return fn()


def list_nat_gateways():
    if _fixture():
        from cloudcleaner.fixtures.demo import list_nat_gateways as fn
    else:
        from cloudcleaner.tools.aws.gateways import list_nat_gateways as fn
    return fn()


def list_load_balancers():
    if _fixture():
        from cloudcleaner.fixtures.demo import list_load_balancers as fn
    else:
        from cloudcleaner.tools.aws.loadbalancers import list_load_balancers as fn
    return fn()


def list_rds_instances():
    if _fixture():
        from cloudcleaner.fixtures.demo import list_rds_instances as fn
    else:
        from cloudcleaner.tools.aws.databases import list_rds_instances as fn
    return fn()


def list_cache_clusters():
    if _fixture():
        from cloudcleaner.fixtures.demo import list_cache_clusters as fn
    else:
        from cloudcleaner.tools.aws.caches import list_cache_clusters as fn
    return fn()


def list_snapshots(owned_by_self: bool = True):
    if _fixture():
        from cloudcleaner.fixtures.demo import list_snapshots as fn
    else:
        from cloudcleaner.tools.aws.volumes import list_snapshots as fn
    return fn(owned_by_self)


def healthy_target_count(target_group_arns: list[str]) -> int:
    if _fixture():
        from cloudcleaner.fixtures.demo import healthy_target_count as fn
    else:
        from cloudcleaner.tools.aws.loadbalancers import healthy_target_count as fn
    return fn(target_group_arns)


def get_usage_evidence(resource, days: int | None = None):
    """Dispatch to the idle signal that means something for this resource type."""
    from cloudcleaner.config import METRIC_WINDOW_DAYS
    from cloudcleaner.schemas import AWSEvidence

    days = days or METRIC_WINDOW_DAYS
    rid = resource.resource_id

    if resource.resource_type == "ec2":
        return get_ec2_usage_evidence(rid, days)

    module = "cloudcleaner.fixtures.demo" if _fixture() else "cloudcleaner.tools.aws.metrics"
    mod = __import__(module, fromlist=["x"])

    if resource.resource_type == "nat":
        return mod.get_nat_usage_evidence(rid, days)
    if resource.resource_type == "elb":
        return mod.get_elb_usage_evidence(rid, resource.instance_type, days)
    if resource.resource_type == "rds":
        return mod.get_rds_usage_evidence(rid, days)
    if resource.resource_type == "cache":
        return mod.get_cache_usage_evidence(rid, days)

    # EBS volumes, Elastic IPs and snapshots publish no usage metrics at all.
    # Absence of data is not evidence of idleness, so nothing is inferred here.
    return AWSEvidence(idle_days=resource.idle_days)


def get_ec2_usage_evidence(instance_id: str, days: int | None = None):
    from cloudcleaner.config import METRIC_WINDOW_DAYS
    days = days or METRIC_WINDOW_DAYS

    if _fixture():
        from cloudcleaner.fixtures.demo import get_ec2_usage_evidence as fn
    else:
        from cloudcleaner.tools.aws.metrics import get_ec2_usage_evidence as fn
    return fn(instance_id, days)
    
def get_github_evidence(repo: str | None = None) -> GitHubEvidence:
    if not repo:
        return GitHubEvidence()

    if _fixture():
        from cloudcleaner.fixtures.demo import get_github_evidence as fn
        return fn(repo)

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
