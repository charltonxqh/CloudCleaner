import sys
from pathlib import Path

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from cloudcleaner.tools.aws.inventory import list_ec2_instances
from cloudcleaner.tools.aws.metrics import get_ec2_usage_evidence


def main():
    resources = list_ec2_instances()

    if not resources:
        print("No EC2 instances found. Metrics test skipped.")
        return

    resource = resources[0]

    print("Testing metrics for:", resource.resource_id)

    evidence = get_ec2_usage_evidence(
        resource.resource_id
    )

    print(evidence.model_dump())


if __name__ == "__main__":
    main()