from cloudcleaner.tools.aws.client import get_ec2_client


PROJECT_TAGS = [
    {"Key": "Project", "Value": "CloudCleaner"},
    {"Key": "Environment", "Value": "demo"},
    {"Key": "ManagedBy", "Value": "CloudCleaner"},
]


def tag_resource(ec2, resource_id: str, name: str):
    ec2.create_tags(
        Resources=[resource_id],
        Tags=[
            {"Key": "Name", "Value": name},
            *PROJECT_TAGS,
        ],
    )


def create_demo_network():
    ec2 = get_ec2_client()

    # --------------------------------------------------
    # 1. Create VPC
    # --------------------------------------------------

    print("Creating VPC...")

    vpc_response = ec2.create_vpc(
        CidrBlock="10.0.0.0/16"
    )

    vpc_id = vpc_response["Vpc"]["VpcId"]

    tag_resource(
        ec2,
        vpc_id,
        "cloudcleaner-demo-vpc",
    )

    print(f"VPC created: {vpc_id}")

    # Enable normal DNS behaviour inside the VPC
    ec2.modify_vpc_attribute(
        VpcId=vpc_id,
        EnableDnsSupport={"Value": True},
    )

    ec2.modify_vpc_attribute(
        VpcId=vpc_id,
        EnableDnsHostnames={"Value": True},
    )

    # --------------------------------------------------
    # 2. Create subnet
    # --------------------------------------------------

    print("Creating subnet...")

    subnet_response = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock="10.0.1.0/24",
    )

    subnet_id = subnet_response["Subnet"]["SubnetId"]

    tag_resource(
        ec2,
        subnet_id,
        "cloudcleaner-demo-subnet",
    )

    print(f"Subnet created: {subnet_id}")

    # --------------------------------------------------
    # 3. Create security group
    # --------------------------------------------------

    print("Creating security group...")

    sg_response = ec2.create_security_group(
        GroupName="cloudcleaner-demo-sg",
        Description="Security group for CloudCleaner demo EC2",
        VpcId=vpc_id,
    )

    security_group_id = sg_response["GroupId"]

    tag_resource(
        ec2,
        security_group_id,
        "cloudcleaner-demo-sg",
    )

    print(
        f"Security group created: {security_group_id}"
    )

    # We intentionally add NO inbound rules.
    # The demo EC2 does not need SSH or HTTP access.

    print()
    print("CloudCleaner demo network ready.")
    print()
    print(f"VPC ID:            {vpc_id}")
    print(f"Subnet ID:         {subnet_id}")
    print(f"Security Group ID: {security_group_id}")


if __name__ == "__main__":
    create_demo_network()