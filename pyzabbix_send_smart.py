#!/usr/bin/python3
# -*- coding: utf-8 -*-

from subprocess import Popen, PIPE, STDOUT
from pyzabbix import ZabbixMetric, ZabbixSender
import re
import os
import json


def cmd_line(command, codepg):
	result = Popen(command, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT)
	result = result.stdout.read().decode(codepg).strip().split('\n')
	return result


def smart_parser(smart_out, disk, hostname):
	smart_attr = {'Model Family': 'model', 'Device Model': 'product', 'User Capacity': 'capacity', 'Product': 'product',
				  'Transport protocol': 'model','Rotation Rate': 'rotation_rate', '0x05': 'reallocated_sectors',
				  '0x09': 'power_on_hours', '0xc2': 'temperature', '0xc5': 'current_pending_sectors',
				  '0xc6': 'uncorrectable_sectors', '0xc7': 'crc_error', '0xbe': 'airflow_temperature',
				  '0xab': 'program_fail_count_chip', 'oxac': 'erase_fail_count', '0xbb': 'reported_uncorrectable_errors',
				  'Current Drive Temperature': 'temperature', 'SMART Health Status': 'health_status',
				  'Elements in grown defect list': 'elements_in_grown_def_list', 'verify': 'uncorrected_errors_verify',
				  'read': 'uncorrected_errors_read', 'write': 'uncorrected_errors_write'}
	
	metric = []
	split_symbol = ':'
	data_index = -1
	zabbix_key = 'info'
	
	for line in smart_out:
		if 'smart attributes' in line.strip().lower():
			split_symbol = ' '
			data_index = 9
		if '=== START OF READ SMART DATA SECTION ===' in line.strip():
			zabbix_key = 'attrib'
		param = line.split(split_symbol)[0].strip()
		if param in smart_attr:
			if zabbix_key == 'info':
				data = (line.split(':')[1].strip())
				data = (re.sub(r'\xa0', ' ', data))
			elif param == 'Current Drive Temperature':
				data = (re.sub(r'\s+', ' ', line).split(' ')[-2])
			else:
				data = (re.sub(r'\s+', ' ', line).split(' ')[data_index])
			if data.isdigit():
				data = int(data)
			zabbix_str = "smartctl.%s[%s,%s]" % (zabbix_key, disk, smart_attr[param])
			metric.append(ZabbixMetric(hostname, zabbix_str, data))
	return metric


def main():
	
	drive_list = []
	json_string = []
	smartctl_check = 'smartctl -f hex,id -A -i -H -lerror -d '
	metric = []
	zabbix_server = 'zabbix.saber3d.ru'
	
	if os.name == 'nt':
		hostname = os.environ['COMPUTERNAME'].lower() + '.' + os.environ['USERDNSDOMAIN'].lower()
		codepg = 'cp1251'
		smartctl_scan = r'c:\"Program Files"\smartmontools\bin\smartctl --scan'
		smartctl_check = 'c:\\"Program Files"\\smartmontools\\bin\\' + smartctl_check
	elif os.popen('uname').read().strip().lower() == 'vmkernel':
		hostname = os.uname()[1]
		codepg = 'utf8'
		smartctl_scan = "/usr/bin/esxcli storage core device list | /bin/grep -v -E '^ ' | /bin/grep -i ata | /usr/bin/awk '{print \"/dev/disks/\"$0}'"
		smartctl_check = r'/opt/smartmontools/' + smartctl_check
	else:
		hostname = os.uname()[1]
		codepg = 'utf8'
		smartctl_scan = "/usr/sbin/smartctl --scan | /bin/grep -i megaraid | /usr/bin/awk '{print $3}'"
		drive_type = cmd_line(smartctl_scan, codepg)
		for i in range(len(drive_type)):
			if drive_type[i] != '':
				drive_list.append(('/dev/bus/0 ' + drive_type[i]).split(' '))
				json_string.append({'{#DEVNAME}': drive_type[i].replace(',', '')})
		smartctl_scan = "/usr/bin/sg_map -i | /bin/grep -i -E 'ata|seagate' | awk '{print $1 (\" sat\")}'"
		smartctl_check = r'/usr/sbin/' + smartctl_check
	
	devices = cmd_line(smartctl_scan, codepg)
	#print(devices)
	
	# json for zabbix template
	for i in range(len(devices)):
		if devices[i] != '':
			drive_list.append((devices[i].split()[0] + ' sat').split(' '))
			json_string.append({'{#DEVNAME}': devices[i].split()[0]})
	
	json_dumps = json.dumps({"data": json_string})
	ZabbixSender(zabbix_server).send([ZabbixMetric(hostname, "HDD.discovery[{#DEVNAME}]", json_dumps)])
	
	# getting smart data
	for disk in drive_list:
		smart_out = cmd_line(smartctl_check + disk[1] + ' ' + disk[0], codepg)
		if 'megaraid' in disk[1]:
			metric += smart_parser(smart_out, disk[1].replace(',', ''), hostname)
		else:
			metric += smart_parser(smart_out, disk[0], hostname)
	#print(metric)
	
	# send data to zabbix
	ZabbixSender(zabbix_server).send(metric)
	

if __name__ == '__main__':
	main()
