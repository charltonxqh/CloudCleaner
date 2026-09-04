from cloudcleaner.evidence.collector import log
from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.schemas import AWSEvidence, GitHubEvidence
from cloudcleaner.tools.provider import get_ec2_usage_evidence


def investigate_node(state: CloudCleanerState):
    resource = state["resource"]
    rid = resource.resource_id

    if resource.resource_type == "ec2":
        log.emit("investigate", "check", rid, "querying CloudWatch")
        aws_evidence = get_ec2_usage_evidence(rid)
    else:
        # EBS volumes and Elastic IPs emit no CPU metrics; absence is not a signal.
        aws_evidence = AWSEvidence(idle_days=resource.idle_days)

    aws_evidence.estimated_monthly_cost = resource.estimated_monthly_cost
    aws_evidence.billing_while_stopped = resource.billing_while_stopped

    log.emit("investigate", "finding", rid,
             f"cpu avg={aws_evidence.avg_cpu_percent} idle_days={aws_evidence.idle_days}")

    # TODO(github workstream): replace with tools/github/{branches,pull_requests}.py
    github_evidence = GitHubEvidence(repo=resource.tags.get("Repo"))

    return {"aws_evidence": aws_evidence, "github_evidence": github_evidence}
