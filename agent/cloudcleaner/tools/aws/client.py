import boto3

from cloudcleaner.config import AWS_ENDPOINT_URL, AWS_REGION


def _client(service: str):
    kwargs = {"region_name": AWS_REGION}
    if AWS_ENDPOINT_URL:
        kwargs["endpoint_url"] = AWS_ENDPOINT_URL
    return boto3.client(service, **kwargs)


def get_ec2_client():
    return _client("ec2")


def get_cloudwatch_client():
    return _client("cloudwatch")


def get_sts_client():
    return _client("sts")


def get_elbv2_client():
    return _client("elbv2")


def get_rds_client():
    return _client("rds")


def get_elasticache_client():
    return _client("elasticache")
