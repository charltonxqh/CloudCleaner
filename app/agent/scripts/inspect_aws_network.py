from cloudcleaner.tools.aws.client import get_ec2_client


def main():
    ec2 = get_ec2_client()

    print("=== VPCs ===")

    vpcs = ec2.describe_vpcs()["Vpcs"]

    if not vpcs:
        print("No VPCs found.")
    else:
        for vpc in vpcs:
            print(
                f"VPC ID: {vpc['VpcId']} | "
                f"CIDR: {vpc['CidrBlock']} | "
                f"Default: {vpc['IsDefault']}"
            )

    print()
    print("=== Subnets ===")

    subnets = ec2.describe_subnets()["Subnets"]

    if not subnets:
        print("No subnets found.")
    else:
        for subnet in subnets:
            print(
                f"Subnet ID: {subnet['SubnetId']} | "
                f"VPC: {subnet['VpcId']} | "
                f"AZ: {subnet['AvailabilityZone']} | "
                f"CIDR: {subnet['CidrBlock']}"
            )

    print()
    print("=== Security Groups ===")

    groups = ec2.describe_security_groups()["SecurityGroups"]

    if not groups:
        print("No security groups found.")
    else:
        for group in groups:
            print(
                f"Group ID: {group['GroupId']} | "
                f"Name: {group['GroupName']} | "
                f"VPC: {group.get('VpcId')}"
            )


if __name__ == "__main__":
    main()