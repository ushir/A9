
import os
import time
import sys
import boto3
import botocore
import botocore.exceptions
from botocore.exceptions import ClientError
import json
#import boto.vpc

"""
Steps to launch instance:
    -   Get handle to ec2 client
    -   Get VPCid and Subnetid
    -   Provide AMI name, Instance type, Keypair name , Secutiry group, and Region name
    -   Keypair is not required to run instance, but is required to connect later
    -   Subnetid provides Availabilty Zone

"""

def Launch_instance(amiid='ami-0ec6517f6edbf8044',
                    instance_type='t2.micro',
                    keypair_name='awskp3',
                    security_group_name='Mysecuritygroup02',
                    cidr='0.0.0.0/0',
                    tag='ucscinst01',
                    user_data=None,
                    region='us-west-1'):
    
    # Create a connection to EC2 service and get vpc connection
    ec2=boto3.client('ec2',region_name=region)

    #get the 1st vpc and 1st subnet
    resp=ec2.describe_vpcs()
    vpcidtouse=resp['Vpcs'][0]['VpcId']
    subnetlist=ec2.describe_subnets(Filters=[ {'Name': 'vpc-id', 'Values': [vpcidtouse]} ])
    subnetid = subnetlist['Subnets'][0]['SubnetId']

    # Check to see if specified security group already exists.
    # If we get an InvalidGroup.NotFound error back from EC2,
    # it means that it doesn't exist and we need to create it.
    secgrpname = security_group_name
    bcreatedsecgrp = False
    try:
        secgrpfilter = [
            {
                'Name':'group-name', 'Values':[secgrpname]
            }
	    ]
        secgroups = ec2.describe_security_groups(
            Filters=secgrpfilter
        )
        if secgroups['SecurityGroups']:
            secgrptouse = secgroups["SecurityGroups"][0]
            secgrpid = secgrptouse['GroupId']
        else:
            secgrptouse = ec2.create_security_group(
                GroupName=secgrpname,Description='aws class open ssh,http,https',
                VpcId=vpcidtouse)
            secgrpid = secgrptouse['GroupId']
            bcreatedsecgrp = True
    except ClientError as e:
        print("%s " % e.response['Error']['Code'])
        raise

    if (bcreatedsecgrp == True):
        # Add a rule to the security group to authorize ssh traffic
        # on the specified port.
        #open ports 22, 80, 443, 8080, 
        portlist = [22, 80, 443, 8080]
        for port in portlist:
            try:
                ec2.authorize_security_group_ingress(
                    CidrIp='0.0.0.0/0',
                    FromPort=port,
                    GroupId=secgrpid,
                    IpProtocol='tcp',
                    ToPort=port)
            except:
                print("error opening port:" +  str(port))
                exit()

    try:
        secgrpidlist=[secgrpid]
        numinstances = 1
        resp = ec2.run_instances(
            ImageId=amiid, 
            InstanceType=instance_type,
            KeyName=keypair_name,
            SecurityGroupIds=secgrpidlist,
            SubnetId=subnetid,
            MaxCount=numinstances,
            MinCount=numinstances)
    except:
        print("exception:", sys.exc_info()[0])
        raise

    # The instance has been launched but it's not yet up and
    # running.  Let's wait for it's state to change to 'running'.
    print('waiting for instance')
    inst=resp["Instances"][0]
    instid=inst["InstanceId"]

    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instid])

    print('EC2 instance is running')
    return inst

def Terminate_instance (ec2, inst):

    instid = inst['InstanceId']

    #terminate ec2 instance
    print('will delete instance-id:' + instid)
    ec2.terminate_instances(InstanceIds=[instid])

    waiter = ec2.get_waiter('instance_terminated')
    waiter.wait(InstanceIds=[instid])
    print("EC2 instance is termniated")

def main():
    inst = launch_instance()
    ec2=boto3.client('ec2', region='us-west-1')
    input('press enter to stop and terminate instance')

    instid = inst["InstanceId"]
    resp=ec2.stop_instances(InstanceIds=[instid])
    print(json.dumps(resp,indent=2,separators=(',',':')))

    resp=ec2.terminate_instances(InstanceIds=[instid])
    print(json.dumps(resp,indent=2,separators=(',',':')))


if __name__ == "__main__":
    main()

