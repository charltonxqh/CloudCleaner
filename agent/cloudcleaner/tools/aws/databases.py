"""RDS instances. Stopping one does not stop the bill, and AWS restarts it after 7 days."""

from cloudcleaner.schemas import CloudResource
from cloudcleaner.tools.aws.client import get_rds_client
from cloudcleaner.tools.aws.cost import rds_cost, rds_monthly_saving_if_stopped


def list_rds_instances() -> list[CloudResource]:
    rds = get_rds_client()

    out = []
    for page in rds.get_paginator("describe_db_instances").paginate():
        for db in page["DBInstances"]:
            tags = {t["Key"]: t["Value"] for t in (db.get("TagList") or [])}
            state = db["DBInstanceStatus"]
            storage_gb = db.get("AllocatedStorage")
            storage_type = db.get("StorageType")
            multi_az = bool(db.get("MultiAZ"))

            cost, residual = rds_cost(
                state, db.get("DBInstanceClass"), storage_gb, storage_type, 0.0, multi_az
            )
            stopped, _ = rds_cost(
                "stopped", db.get("DBInstanceClass"), storage_gb, storage_type, 0.0, multi_az
            )

            out.append(CloudResource(
                resource_id=db["DBInstanceIdentifier"],
                resource_type="rds",
                region="",
                name=db["DBInstanceIdentifier"],
                state=state,
                instance_type=db.get("DBInstanceClass"),
                engine=db.get("Engine"),
                size_gb=storage_gb,
                multi_az=multi_az,
                deletion_protection=bool(db.get("DeletionProtection")),
                vpc_id=(db.get("DBSubnetGroup") or {}).get("VpcId"),
                launch_time=(
                    db["InstanceCreateTime"].isoformat() if db.get("InstanceCreateTime") else None
                ),
                project=tags.get("Project"),
                environment=tags.get("Environment"),
                owner=tags.get("Owner"),
                estimated_monthly_cost=cost,
                monthly_cost_if_stopped=stopped,
                monthly_saving_if_stopped=rds_monthly_saving_if_stopped(
                    state, db.get("DBInstanceClass"), storage_gb, storage_type, 0.0, multi_az
                ),
                billing_while_stopped=residual,
                tags=tags,
            ))
    return out
