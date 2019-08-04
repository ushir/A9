#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, sys, time, timeit, inspect, subprocess

import boto3
import botocore
import paramiko
import urllib.request
import urllib.error
import Manipulate_instance


def Get_dns_ip_info (ec2, inst):

    instid = inst['InstanceId']
   
    haveDNS = False
    maxDNSTries = 16
    sleepTime = 2
    while haveDNS == False and maxDNSTries > 0:
        time.sleep(sleepTime)
        rz=ec2.describe_instance_status(InstanceIds=[instid])
    
        if not bool(rz):
            continue
        if len(rz["InstanceStatuses"]) == 0:
            continue

        inststate = rz["InstanceStatuses"][0]["InstanceState"]
        state=inststate["Name"]
        if state != 'running':
            continue
            
        rz1 = ec2.describe_instances(InstanceIds=[instid])
        if len(rz1["Reservations"]) == 0:
            continue

        instanceInfo = rz1["Reservations"][0]["Instances"][0]
        dns_name = instanceInfo['PublicDnsName']
        ip_address = instanceInfo['PublicIpAddress']
        maxDNSTries -= 1
        if dns_name and ip_address:
            break
           
        if not dns_name:
            print('cannot get DNS Name for instance:' + instid)
            return

        print(instid + ' paramiko ssh connect to ' + dns_name + ' ip:' + ip_address)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    return (dns_name, ip_address)

#------
# Open SSH and connect to instance
def Openssh (inst, dns_name, ip_address, key_file):

    instid = inst['InstanceId']

    print(instid + ' paramiko ssh connect to ' + dns_name + 
                                            ' ip:' + ip_address)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
   
    # note this loop is not necessary, as the instance network is plumbed
    # however I keep it in, as  this is the first time we are reaching out 
    # to the instance this code will reveal any network issues unrelated 
    # to the aws instance
    tries = 1
    maxtries = 5
    sshloop = True
    while(sshloop):    
        try:
            ssh.connect(ip_address, username='ec2-user', 
                            key_filename=key_file)
            sshloop = False
            print(str(ip_address) +  ' ssh connection successful')
        except paramiko.ssh_exception.NoValidConnectionsError as e:
            print(instid + "tries: " + str(tries) + " " 
                            + str(e.errors) +  ' ssh attempted')
            time.sleep(10)
            tries += 1
            if tries == maxtries:
                raise
    return(ssh)

#------
# Install and start the Tomcat application
def Start_tomcat(ssh, ip_address):

    # Do tomcat6 install and start server
    # this is a AWS Linux server, install pending updates
    print('updating yum on ' + str(ip_address))
    stdin, stdout, stderr = ssh.exec_command("sudo yum -y update")
    stdin.flush()
   
    print('installing tomcat on ' + str(ip_address))
    stdin, stdout, stderr = ssh.exec_command(
                        "sudo yum -y install tomcat8 tomcat8-webapps")
    stdin.flush()
    data = stdout.read().splitlines()
    if data[-1].decode() == 'Complete!':
        print(ip_address + ' tomcat install successful on ' + str(ip_address))
    else:
        print(str(ip_address) + ' tomcat did NOT install')
        exit(1)
   
    print('starting tomcat on ' + str(ip_address))
    stdin, stdout, stderr = ssh.exec_command("sudo service tomcat8 start")
    stdin.flush()
    data = stdout.read().splitlines()
    #data is binary so convert to a string
    if 'OK' in data[-1].decode():
        print('tomcat start successful on ' + str(ip_address))
    else:
        print('could NOT start tomcat on ' + str(ip_address))
        return
   
#------
def Test_tomcat (ssh, inst, ip_address):

    instid = inst['InstanceId']
    print('getting tomcat status from ' + str(ip_address))
    stdin, stdout, stderr = ssh.exec_command("sudo service tomcat8 status")
    stdin.flush()
    data = stdout.read().splitlines()
    if 'running' in data[-1].decode():
        print('confirmed tomcat service is running on' + str(ip_address))
    else:
        print('could not determine if tomcat is running on ' + str(ip_address))

    print("testing Tomcat, connecting to http://" + str(ip_address) + ":8080")
    tries = 1
    maxtries = 5
    urlloop = True
    while(urlloop):
        try:       
            urloutput = urllib.request.urlopen(
                                "http://"+ip_address+":8080").read()
            urlloop = False
        except:
            print(str(instid) + " " + str(tries)  + ' urlopen attempted')
            time.sleep(10)
            tries += 1
            if tries == maxtries:
                print('ERROR: hit maxtries:' + str(maxtries) 
                    + ' urlopen ' + "http://" +ip_address + ":8080")
                raise
                 
    print("Successful connection to http://" + str(ip_address) +":8080")
    if 'Congratulations!' in urloutput.decode():
        print( str(ip_address) +  " successful connection to Tomcat")
    else:
        print("Connection to Tomcat failed, for instance " + str(ip_address)) 
    
#------

def Test_myapp (ssh, inst, ip_address, my_app_name):

    instid = inst['InstanceId']

    print("testing MyApp, connecting to http://" + str(ip_address) + ":8080/" + my_app_name)
    tries = 1
    maxtries = 5
    urlloop = True
    while(urlloop):
        try:       
            urloutput = urllib.request.urlopen(
                            "http://"+ip_address+":8080/"+my_app_name).read()
            urlloop = False
        except:
            print(str(instid) + " " + str(tries)  + ' urlopen attempted')
            time.sleep(10)
            tries += 1
            if tries == maxtries:
                print('ERROR: hit maxtries:' + str(maxtries) 
                    + ' urlopen ' + "http://" +ip_address + ":8080/" + my_app_name)
                raise
                 
    print("Successful connection to http://" + str(ip_address) +":8080/" + my_app_name)
    print ("urloutput:" + urloutput.decode())


#------
# Install My static  application
def Install_myapp(ssh, dns_name, ip_address, key_path, my_app_name, my_app_file):

    print("Installing app " + my_app_name + " at "  + str(ip_address))

    if os.path.exists(my_app_file) == False:
        print('cannot find App ' + my_app_file)
        print('current folder is:' + os.getcwd())
        exit(1)

    # Copy app from current directory to instance
    try:
        sftp = ssh.open_sftp()
        sftp.put(my_app_file, my_app_file)
        sftp.close()
    except:
        print('error copying app from local diretory to instance')

    # Copy app from local directory to Tomcat directory
    tomcat_path = "/usr/share/tomcat8/webapps"
    tomcat_apppath = "/usr/share/tomcat8/webapps/ROOT"
    tomcat_web_xml = "/usr/share/tomcat8/conf/web.xml"
    my_app_path = tomcat_path + "/" + my_app_name
    mkdir_command = "sudo mkdir " + my_app_path
    cp_command = "sudo cp " + my_app_file + " " + my_app_path + "/."
    # cp_command_1 = "sudo cp " + my_app_file + " " + my_app_path + "/index.html"
    cp_command_2 = "sudo cp " + my_app_file + " " + tomcat_apppath + "/."
    sed_command_1 = "sudo sed -i -e '1,/index.html/{s/index/MyPage/}' " + tomcat_web_xml

    print('Copying app to tomcat install using command ' + cp_command)
    stdin, stdout, stderr = ssh.exec_command(mkdir_command)
    stdin, stdout, stderr = ssh.exec_command(cp_command)
    # stdin, stdout, stderr = ssh.exec_command(cp_command_1)
    stdin, stdout, stderr = ssh.exec_command(cp_command_2)
    stdin, stdout, stderr = ssh.exec_command(sed_command_1)
    stdin.flush()
    # Need to restart tomcat due to installation on new index.html and modification to web.xml
    stdin, stdout, stderr = ssh.exec_command("sudo service tomcat8 restart")
    stdin.flush()
    data = stdout.read().splitlines()
    #data is binary so convert to a string
    if 'OK' in data[-1].decode():
        print('tomcat restart successful on ' + str(ip_address))
    else:
        print('could NOT restart tomcat on ' + str(ip_address))
        return
   
   
#------
def Close_ssh(ssh, ip_address):
    print('closing ssh connection to ', str(ip_address))
    ssh.close()

#------
def usage():
    print('usage: python autoinstall.py securityGroup sshKeyName sshKeyFolder')

#------
def Get_keypair(securitykey, keylocation):
    if os.path.isdir(keylocation) == False:
        print('cannot find key location folder:' + keylocation)
        exit(1)

    fullpath = os.path.join(keylocation, securitykey) + '.pem'
    if os.path.exists(fullpath) == False:
        print('cannot find keyfile:' + fullpath)
        print('current folder is:' + os.getcwd())
        exit(1)

    return(fullpath)

#------
def main():
    if len(sys.argv) != 4:
        usage()
        exit(1)

    print('Python version:' + ".".join(map(str, sys.version_info[:3])))
    print('Boto3 version:' + boto3.__version__)
    print('Paramiko version:' +  paramiko.__version__)
      
    securitygroup = sys.argv[1]
    securitykey = sys.argv[2]
    keylocation = sys.argv[3]

    key_path = Get_keypair(securitykey, keylocation)

    region = 'us-west-1'
    ami_west_id = 'ami-0ec6517f6edbf8044'
    my_app_name = "MyWebApp"
    my_app_file = "MyPage.html"
    ec2=boto3.client('ec2',region_name=region)
    inst1 = Manipulate_instance.Launch_instance(
                                amiid=ami_west_id,
                                security_group_name=securitygroup, 
                                keypair_name=securitykey,
                                region=region)
    dns_name, ip_addr = Get_dns_ip_info (ec2, inst1)
    ssh_inst1 = Openssh (inst1, dns_name, ip_addr, key_path)
    Start_tomcat (ssh_inst1, ip_addr)
    Test_tomcat (ssh_inst1, inst1, ip_addr)
    Install_myapp(ssh_inst1, dns_name, ip_addr, key_path, my_app_name, my_app_file)
    Test_myapp (ssh_inst1, inst1, ip_addr, my_app_name)
    Close_ssh (ssh_inst1, ip_addr)
    
    print('Now testing the same installation on us-east-1')
    region = 'us-east-1'
    # securitygroup = "awsclass01" needs to be in us-east-1
    securitykey = "awskp4-east"
    ami_east_id = 'ami-0080e4c5bc078760e'
    ec2_east=boto3.client('ec2',region_name=region)
    key_path = Get_keypair(securitykey, keylocation)
    inst2 = Manipulate_instance.Launch_instance(
                                amiid=ami_east_id,
                                security_group_name=securitygroup, 
                                keypair_name=securitykey,
                                region=region)
    dns_name2, ip_addr2 = Get_dns_ip_info (ec2_east, inst2)
    ssh_inst2 = Openssh (inst2, dns_name2, ip_addr2, key_path)
    Start_tomcat (ssh_inst2, ip_addr2)
    Test_tomcat (ssh_inst2, inst2, ip_addr2)
    Install_myapp(ssh_inst2, dns_name2, ip_addr2, key_path, my_app_name, my_app_file)
    Test_myapp (ssh_inst2, inst2, ip_addr2, my_app_name)
    Close_ssh (ssh_inst2, ip_addr2)

    Manipulate_instance.Terminate_instance (ec2, inst1)
    Manipulate_instance.Terminate_instance (ec2_east, inst2)

#------
if  __name__ =='__main__':
    main()

