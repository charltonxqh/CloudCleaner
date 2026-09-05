"""AWS Price List API helpers for on-demand EC2 and EBS pricing."""

import json
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError


_PRICE_API_REGION = "us-east-1"
_REGION_LOCATIONS = {
    "us-east-1": "US East (N. Virginia)",
}


@lru_cache(maxsize=1)
def _pricing_client():
    return boto3.client("pricing", region_name=_PRICE_API_REGION)


def _usd_price(response: dict, unit: str) -> float | None:
    for raw in response.get("PriceList", []):
        try:
            product = json.loads(raw)
            for term in product.get("terms", {}).get("OnDemand", {}).values():
                for dimension in term.get("priceDimensions", {}).values():
                    if dimension.get("unit") != unit:
                        continue
                    price = dimension.get("pricePerUnit", {}).get("USD")
                    if price is not None:
                        return float(price)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


@lru_cache(maxsize=None)
def get_ec2_hourly_price(instance_type: str, region: str) -> float | None:
    location = _REGION_LOCATIONS.get(region)
    if not instance_type or not location:
        return None

    try:
        response = _pricing_client().get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
            ],
            MaxResults=100,
        )
    except (BotoCoreError, ClientError):
        return None

    return _usd_price(response, "Hrs")


@lru_cache(maxsize=None)
def get_ebs_gb_month_price(volume_type: str, region: str) -> float | None:
    location = _REGION_LOCATIONS.get(region)
    if not volume_type or not location:
        return None

    try:
        response = _pricing_client().get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "volumeApiName", "Value": volume_type},
            ],
            MaxResults=100,
        )
    except (BotoCoreError, ClientError):
        return None

    return _usd_price(response, "GB-Mo")
