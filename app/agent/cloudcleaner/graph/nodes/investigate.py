from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.schemas import AWSEvidence, GitHubEvidence
from cloudcleaner.tools.aws.metrics import get_ec2_usage_evidence


def investigate_node(state: CloudCleanerState):
    resource = state["resource"]
    
    aws_evidence = get_ec2_usage_evidence(
        resource.resource_id
    )

    github_evidence = GitHubEvidence(
        repo="company/shopping-app",
        latest_commit_at="2026-08-01T10:00:00Z",
        pr_number=184,
        pr_status="merged",
        branch="feature/payment",
        branch_exists=False,
        last_workflow_run_at="2026-08-01T10:30:00Z",
        scheduled_workflow_exists=False,
    )

    return {
        "aws_evidence": aws_evidence,
        "github_evidence": github_evidence,
    }