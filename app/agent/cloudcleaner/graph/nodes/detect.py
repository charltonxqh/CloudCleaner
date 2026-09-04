from cloudcleaner.graph.state import CloudCleanerState
from cloudcleaner.tools.aws.inventory import list_ec2_instances


def detect_node(
    state: CloudCleanerState,
):
    resources = list_ec2_instances()

    if not resources:
        return {
            "error": "No EC2 instances found."
        }

    return {
        "resource": resources[0]
    }