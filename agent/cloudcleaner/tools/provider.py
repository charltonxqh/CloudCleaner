"""Resolve the data source at call time, not import time."""

import os


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


def get_ec2_usage_evidence(instance_id: str, days: int | None = None):
    from cloudcleaner.config import METRIC_WINDOW_DAYS
    days = days or METRIC_WINDOW_DAYS

    if _fixture():
        from cloudcleaner.fixtures.demo import get_ec2_usage_evidence as fn
    else:
        from cloudcleaner.tools.aws.metrics import get_ec2_usage_evidence as fn
    return fn(instance_id, days)
