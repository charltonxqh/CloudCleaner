import argparse

import boto3

from cloudcleaner.config import AWS_REGION
from cloudcleaner.tools.aws.client import get_ec2_client


AMI_PARAMETER = (
    "/aws/service/ami-amazon-linux-latest/"
    "al2023-ami-kernel-default-x86_64"
)


def get_latest_amazon_linux_ami() -> str:
    ssm = boto3.client("ssm", region_name=AWS_REGION)

    response = ssm.get_parameter(
        Name=AMI_PARAMETER,
    )

    return response["Parameter"]["Value"]


def get_cloudcleaner_vpc(ec2) -> str:
    response = ec2.describe_vpcs(
        Filters=[
            {
                "Name": "tag:Project",
                "Values": ["CloudCleaner"],
            },
            {
                "Name": "tag:Environment",
                "Values": ["demo"],
            },
        ]
    )

    vpcs = response["Vpcs"]

    if not vpcs:
        raise RuntimeError(
            "CloudCleaner demo VPC not found."
        )

    return vpcs[0]["VpcId"]


def get_cloudcleaner_subnet(
    ec2,
    vpc_id: str,
) -> str:
    response = ec2.describe_subnets(
        Filters=[
            {
                "Name": "vpc-id",
                "Values": [vpc_id],
            },
            {
                "Name": "tag:Project",
                "Values": ["CloudCleaner"],
            },
            {
                "Name": "tag:Environment",
                "Values": ["demo"],
            },
        ]
    )

    subnets = response["Subnets"]

    if not subnets:
        raise RuntimeError(
            "CloudCleaner demo subnet not found."
        )

    return subnets[0]["SubnetId"]


def get_cloudcleaner_security_group(
    ec2,
    vpc_id: str,
) -> str:
    response = ec2.describe_security_groups(
        Filters=[
            {
                "Name": "vpc-id",
                "Values": [vpc_id],
            },
            {
                "Name": "group-name",
                "Values": ["cloudcleaner-demo-sg"],
            },
        ]
    )

    groups = response["SecurityGroups"]

    if not groups:
        raise RuntimeError(
            "CloudCleaner demo security group not found."
        )

    return groups[0]["GroupId"]


def create_demo_instance():
    ec2 = get_ec2_client()

    print("Resolving AWS resources...")

    ami_id = get_latest_amazon_linux_ami()
    vpc_id = get_cloudcleaner_vpc(ec2)

    subnet_id = get_cloudcleaner_subnet(
        ec2,
        vpc_id,
    )

    security_group_id = (
        get_cloudcleaner_security_group(
            ec2,
            vpc_id,
        )
    )

    print()
    print("Launch configuration:")
    print(f"Region:         {AWS_REGION}")
    print(f"AMI:            {ami_id}")
    print("Instance type:  t3.micro")
    print(f"VPC:            {vpc_id}")
    print(f"Subnet:         {subnet_id}")
    print(f"Security group: {security_group_id}")
    print()

    response = ec2.run_instances(
        ImageId=ami_id,
        InstanceType="t3.micro",
        MinCount=1,
        MaxCount=1,
        SubnetId=subnet_id,
        SecurityGroupIds=[security_group_id],
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {
                        "Key": "Name",
                        "Value": "cloudcleaner-demo",
                    },
                    {
                        "Key": "Project",
                        "Value": "CloudCleaner",
                    },
                    {
                        "Key": "Environment",
                        "Value": "preview",
                    },
                    {
                        "Key": "Owner",
                        "Value": "CloudCleaner-Team",
                    },
                    {
                        "Key": "Temporary",
                        "Value": "true",
                    },
                ],
            }
        ],
    )

    instance = response["Instances"][0]
    instance_id = instance["InstanceId"]

    print(
        f"Created demo EC2 instance: {instance_id}"
    )
    print(
        "Keep this instance only while testing CloudCleaner."
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--create",
        action="store_true",
        help="Actually create the EC2 demo instance.",
    )

    args = parser.parse_args()

    if not args.create:
        print(
            "No instance created."
        )
        print(
            "Run with --create when you are ready:"
        )
        print(
            "uv run python -m scripts.create_demo_ec2 --create"
        )
        return

    create_demo_instance()


if __name__ == "__main__":
    main()