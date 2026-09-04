import sys
from pathlib import Path

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

from cloudcleaner.tools.aws.client import get_sts_client


def main():
    sts = get_sts_client()

    response = sts.get_caller_identity()

    print("AWS connection successful")
    print("Account:", response["Account"])
    print("ARN:", response["Arn"])


if __name__ == "__main__":
    main()