from datetime import datetime, timedelta, timezone

from cloudcleaner.tools.aws.client import get_cloudwatch_client
from cloudcleaner.schemas import AWSEvidence


def get_ec2_cpu_utilization(
    instance_id: str,
    days: int = 7,
) -> float | None:
    cloudwatch = get_cloudwatch_client()

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[
            {
                "Name": "InstanceId",
                "Value": instance_id,
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=3600,
        Statistics=["Average"],
    )

    datapoints = response["Datapoints"]

    if not datapoints:
        return None

    return sum(
        point["Average"]
        for point in datapoints
    ) / len(datapoints)
    
    
def get_ec2_network_bytes(
    instance_id: str,
    metric_name: str,
    days: int = 7,
) -> float | None:
    cloudwatch = get_cloudwatch_client()

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName=metric_name,
        Dimensions=[
            {
                "Name": "InstanceId",
                "Value": instance_id,
            }
        ],
        StartTime=start_time,
        EndTime=end_time,
        Period=3600,
        Statistics=["Sum"],
    )

    datapoints = response["Datapoints"]

    if not datapoints:
        return None

    return sum(
        point["Sum"]
        for point in datapoints
    )
    

def get_ec2_usage_evidence(
    instance_id: str,
    days: int = 7,
) -> AWSEvidence:
    return AWSEvidence(
        avg_cpu_percent=get_ec2_cpu_utilization(
            instance_id,
            days,
        ),
        network_in_bytes=get_ec2_network_bytes(
            instance_id,
            "NetworkIn",
            days,
        ),
        network_out_bytes=get_ec2_network_bytes(
            instance_id,
            "NetworkOut",
            days,
        ),
    )