from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.schemas import AWSEvidence, GitHubEvidence


def investigate_node(state: CloudCleanerState):
    aws_evidence = AWSEvidence(
        avg_cpu_percent=1.2,
        network_in_bytes=1200,
        network_out_bytes=900,
        estimated_monthly_cost=60.0,
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