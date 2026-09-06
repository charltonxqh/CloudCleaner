"""ElastiCache clusters. No stop at all - a cache bills until it is deleted."""

from cloudcleaner.schemas import CloudResource
from cloudcleaner.tools.aws.client import get_elasticache_client
from cloudcleaner.tools.aws.cost import elasticache_cost


def list_cache_clusters() -> list[CloudResource]:
    ec = get_elasticache_client()

    out = []
    for page in ec.get_paginator("describe_cache_clusters").paginate():
        for cluster in page["CacheClusters"]:
            cid = cluster["CacheClusterId"]

            try:
                arn = cluster.get("ARN")
                tags = {
                    t["Key"]: t["Value"]
                    for t in ec.list_tags_for_resource(ResourceName=arn)["TagList"]
                } if arn else {}
            except Exception:
                tags = {}

            nodes = cluster.get("NumCacheNodes") or 1

            out.append(CloudResource(
                resource_id=cid,
                resource_type="cache",
                region="",
                name=tags.get("Name", cid),
                state=cluster.get("CacheClusterStatus"),
                instance_type=cluster.get("CacheNodeType"),
                engine=cluster.get("Engine"),
                node_count=nodes,
                launch_time=(
                    cluster["CacheClusterCreateTime"].isoformat()
                    if cluster.get("CacheClusterCreateTime") else None
                ),
                project=tags.get("Project"),
                environment=tags.get("Environment"),
                owner=tags.get("Owner"),
                estimated_monthly_cost=elasticache_cost(cluster.get("CacheNodeType"), nodes),
                billing_while_stopped=True,
                tags=tags,
            ))
    return out
