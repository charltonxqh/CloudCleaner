import sys
from pathlib import Path

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from cloudcleaner.tools.aws.inventory import list_ec2_instances


def main():
    resources = list_ec2_instances()

    print(
        f"Found {len(resources)} EC2 instance(s)\n"
    )

    for resource in resources:
        print(resource.model_dump())
        print()


if __name__ == "__main__":
    main()