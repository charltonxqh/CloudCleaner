from cloudcleaner.tools.aws.client import get_sts_client


def main():
    sts = get_sts_client()

    response = sts.get_caller_identity()

    print("AWS connection successful")
    print("Account:", response["Account"])
    print("ARN:", response["Arn"])


if __name__ == "__main__":
    main()