from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.schemas import AWSEvidence, GitHubEvidence
from cloudcleaner.tools.provider import (
    get_github_evidence,
    get_usage_evidence,
    healthy_target_count,
)


def _signal_summary(aws: AWSEvidence) -> str:
    parts = []
    if aws.avg_cpu_percent is not None:
        parts.append(f"cpu avg={aws.avg_cpu_percent}%")
    if aws.connection_count is not None:
        parts.append(f"peak connections={aws.connection_count:,.0f}")
    if aws.request_count is not None:
        parts.append(f"requests={aws.request_count:,.0f}")
    if aws.bytes_processed is not None:
        parts.append(f"bytes={aws.bytes_processed:,.0f}")
    parts.append(f"idle_days={aws.idle_days}")

    source = f" via {aws.metric_source}" if aws.metric_source else ""
    return ", ".join(parts) + source


def investigate_node(state: CloudCleanerState):
    resource = state["resource"]
    rid = resource.resource_id

    log.emit("investigate", "check", rid,
             f"querying CloudWatch for {resource.resource_type}")

    # Every type is judged by the metric that means something for it. EBS
    # volumes, Elastic IPs and snapshots emit nothing; absence is not a signal.
    aws_evidence = get_usage_evidence(resource)

    aws_evidence.estimated_monthly_cost = resource.estimated_monthly_cost
    aws_evidence.billing_while_stopped = resource.billing_while_stopped

    if resource.resource_type == "elb" and resource.target_group_ids:
        try:
            healthy = healthy_target_count(resource.target_group_ids)
            log.emit("investigate", "finding", rid,
                     f"{healthy} healthy target(s) behind this balancer")
        except Exception as e:
            log.emit("investigate", "error", rid, f"target health unavailable: {e}")

    log.emit("investigate", "finding", rid, _signal_summary(aws_evidence))

    repo = resource.tags.get("Repo")
    github_evidence = get_github_evidence(repo)

    return {"aws_evidence": aws_evidence, "github_evidence": github_evidence}
