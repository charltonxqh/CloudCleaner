import boto3

from cloudcleaner.config import AWS_REGION


def get_ec2_client():
    return boto3.client(
        "ec2",
        region_name=AWS_REGION,
    )


def get_cloudwatch_client():
    return boto3.client(
        "cloudwatch",
        region_name=AWS_REGION,
    )


def get_sts_client():
    return boto3.client(
        "sts",
        region_name=AWS_REGION,
    )