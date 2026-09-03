from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.schemas import CloudResource


def detect_node(state: CloudCleanerState):
    resource = CloudResource(
        resource_id="i-demo123",
        resource_type="ec2",
        region="us-east-1",
        name="preview-pr-184",
        state="running",
        project="shopping-app",
        environment="preview",
        owner="platform-team",
        tags={
            "Temporary": "true",
            "GitHubRepo": "company/shopping-app",
            "GitHubPR": "184",
        },
    )

    return {
        "resource": resource,
    }