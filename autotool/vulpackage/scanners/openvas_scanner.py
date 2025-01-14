import os
import sys
import time
import json
from pprint import pprint

import xmltodict
from lxml import etree
from xml.etree import ElementTree
from gvm.connections import  TLSConnection
from gvm.protocols.latest import Gmp
from gvm.transforms import EtreeTransform
from gvm.xml import pretty_print
from dotenv import load_dotenv, find_dotenv
import xml.etree.ElementTree as ET
from .scanner import Scanner
from vulpackage.core.storage_service import StorageService

from io import BytesIO
load_dotenv(find_dotenv())

config = {
    'HOST_NAME': os.getenv('HOST_NAME'),
    'PORT': os.getenv('PORT'),
    'OPENVAS_USERNAME': os.getenv('OPENVAS_USERNAME'),
    'OPENVAS_PASSWORD': os.getenv('OPENVAS_PASSWORD'),
    'REPORT_FORMAT_ID': 'a994b278-1f62-11e1-96ac-406186ea4fc5',
    'SCAN_CONFIG_ID': 'daba56c8-73ec-11df-a475-002264764cea',
    'SCANNER_ID': '08b69003-5fc2-4037-a479-93b440211c73'
}

class OpenVASScanner(Scanner):

    name = 'OpenVAS'
    
    def __init__(self):
        connection = TLSConnection(hostname=config['HOST_NAME'],port=config['PORT'],certfile=None, cafile=None, keyfile=None,password=None,timeout=25 )
        transform = EtreeTransform()
        self.gmp = Gmp(connection, transform=transform)
        self.storage_service = StorageService()


        # Login
        try:
            self.gmp.authenticate(config['OPENVAS_USERNAME'], config['OPENVAS_PASSWORD'])
        except:
            print(f'[{self.name}] Not able to connect to the {self.name}: ', sys.exc_info())
            return


    

    def start(self, scan_name, target):
        print(f'[{self.name}] Starting Scan for Target: {target}')

        try:
            return self.scan(scan_name, target)
        except:
            print(f'[{self.name}] Not able to connect to the {self.name}: ', sys.exc_info()) 
            return False


    def scan(self, scan_name, target):
        print(f'[{self.name}] Scan Name: {scan_name}')

        address = self._get_address(target)

        # Creating Target
        target_response = self.gmp.create_target(name=scan_name, hosts=[address],port_list_id = '33d0cd82-57c6-11e1-8ed1-406186ea4fc5')
        # print('target_response')
        #pretty_print(target_response)
        target_id = target_response.get('id')

        if not target_id:
            print(f'[{self.name}] could not able to create target: ', target_response.get('status_text'))
            return False

        # target_id = '69ca3c65-af09-48b8-bb3a-59e2e6cccb96'

        print(f'[{self.name}] Target Created: {target_id}')

        scan_data = self.storage_service.get_by_name(scan_name)

        if not scan_data:
            scan_data = {
                'scan_name': scan_name, 
                'scan_id': '', 
                'target': target,
                'status': ''
            }
            self.storage_service.add(scan_data)

        scan_data['OPENVAS'] = {
            'openvas_id': target_id,
            'target_id': target_id,
            'scan_status': {
                'status': 'INPROGRESS'
            }
        }
        self.storage_service.update_by_name(scan_name, scan_data)

        time.sleep(4)
        self._create_task(scan_name)

        return scan_data


    def _create_task(self, scan_name):

        scan_data = self.storage_service.get_by_name(scan_name)
        openvas_id = scan_data['OPENVAS']['openvas_id']

        scan_config_id = config['SCAN_CONFIG_ID']
        scanner_id = config['SCANNER_ID']
        report_format_id = config['REPORT_FORMAT_ID']

        # Creating Task
        task_response = self.gmp.create_task(name=scan_name, config_id=scan_config_id, target_id=openvas_id, scanner_id=scanner_id)
        # print('task_response')
        # pretty_print(task_response)
        task_id = task_response.get('id')
        print(f'[{self.name}] Created Task:  with : {task_id}')
        # Starting Task
        start_task_response = self.gmp.start_task(task_id)
        # print('start_task_response')
        # pretty_print(start_task_response)
        report_id = start_task_response[0].text

        scan_data['OPENVAS']['report_id'] = report_id
        scan_data['OPENVAS']['report_format_id'] = report_format_id
        scan_data['OPENVAS']['scan_config_id'] = scan_config_id
        scan_data['OPENVAS']['scanner_id'] = scanner_id
        scan_data['OPENVAS']['task_id'] = task_id

        

        self.storage_service.update_by_name(scan_name, scan_data)

        return scan_data
    

    def get_scan_status(self, scan_name, scan_status_list=[]):

        if not self.is_valid_scan(scan_name):
            return False

        scan_data = self.storage_service.get_by_name(scan_name)
        scan_status = scan_data.get('OPENVAS', {}).get('scan_status', {})
        openvas_id = scan_data.get('OPENVAS', {})['openvas_id']
        target = scan_data['target']
        task_id=scan_data.get('OPENVAS', {})['task_id']

        print(f'[{self.name}] Getting Scan Status for Target: {target}')
        print(f'[{self.name}] Scan Name: {scan_name}')
        print(f'[{self.name}] Scan Id: {openvas_id}')

        try:
            scan_info = self.gmp.get_task(task_id)

            status=scan_info.xpath('task/status/text()')
            progress = scan_info.xpath('task/progress/text()')



        except:
            print(f'[{self.name}] Could not get the scan {openvas_id}: ', sys.exc_info())
            return False

        scan_status['status'] = 'COMPLETE' if status[0] == 'Done' else 'INPROGRESS' if status[0] == 'Running' else status[0]
        scan_status['progress']=progress[0]
        scan_data['OPENVAS']['scan_status'] = scan_status
        self.storage_service.update_by_name(scan_name, scan_data)

        if scan_status['status'] is 'COMPLETE':
            print(f'[{self.name}] Scan {scan_name} Completed')

        scan_status_list.append({
            'scanner': self.name,
            'status': f'{scan_status["status"]} {progress[0]}%'
        })
        return scan_status_list


    def get_scan_results(self, scan_name, oscan_results={}):

        if not self.is_valid_scan(scan_name):
            return False

        scan_data = self.storage_service.get_by_name(scan_name)

        # if scan_data.get('OPENVAS', {}).get('scan_status').get('status', None) != 'COMPLETE':
        #     print(f'[{self.name}] Scan is in progress')
        #     return False

        openvas_id = scan_data.get('OPENVAS', {})['openvas_id']
        report_id = scan_data.get('OPENVAS', {})['report_id']
        report_format_id = scan_data.get('OPENVAS', {})['report_format_id']

        try:
            report_response = self.gmp.get_report(report_id=report_id, report_format_id=report_format_id)
            # print('report_response')
            #pretty_print(report_response)
        except:
            print(f'[{self.name}] Could not get the scan {openvas_id}: ', sys.exc_info())
            return False

        self._process_results(report_response, oscan_results)

        return oscan_results
    

    def _process_results(self, report_response, oscan_results={}):
        report_response_str = ElementTree.tostring(report_response, encoding='unicode')
        report_response_dict = xmltodict.parse(report_response_str)
        
        report_results = report_response_dict.get('get_reports_response', {}).get('report', {}).get('report', {}).get('results', {}).get('result', [])
        
        # print(json.dumps(report_results, indent=2))
        # print('report_results', report_results)

        for vuln in report_results:
            name = vuln.get('name')
            #print('name: ', name)
            if oscan_results.get(name):
               # print('--- Duplicate name: ', name)
                continue
            nvt = vuln.get('nvt', {})
            scan_result = {}
            scan_result['name'] = name
            scan_result['severity'] = float(nvt.get('cvss_base', 0))
            scan_result['risk'] = vuln.get('threat')
            scan_result['cve_id'] = nvt.get('cve', 'N/A') if nvt.get('cve') != 'NOCVE' else 'N/A'
            scan_result['description'] = vuln.get('description')
            scan_result['solution'] = 'N/A'
            scan_result['reported_by'] = 'OpenVAS'
            oscan_results[name] = scan_result

        return oscan_results


    def is_valid_scan(self, scan_name):

        scan_data = self.storage_service.get_by_name(scan_name)
        if not scan_data:
            print(f'[{self.name}] Invalid Scan Name: {scan_name}')
            return False

        if not scan_data.get('OPENVAS'):
            print(f'[{self.name}] No Scan Details found for {scan_name}')
            return False

        return True


    def pause(self, scan_name):
        if not self.is_valid_scan(scan_name):
            return False

        scan = self.storage_service.get_by_name(scan_name)

        task_id = scan['OPENVAS']['task_id']

        response = self.gmp.stop_task(task_id)#GMP does not support pause

        print(f'[{self.name}]  scan paused ')
        return response


    def resume(self, scan_name):
        if not self.is_valid_scan(scan_name):
            return False

        scan = self.storage_service.get_by_name(scan_name)

        task_id = scan['OPENVAS']['task_id']

        response = self.gmp.resume_task(task_id)

        print(f'[{self.name}]  scan resumed ')
        
        return response


    def stop(self, scan_name):
        if not self.is_valid_scan(scan_name):
            return False

        scan = self.storage_service.get_by_name(scan_name)

        task_id = scan['OPENVAS']['task_id']

        response = self.gmp.stop_task(task_id)

        print(f'[{self.name}]  scan stopped ')
        
        return response


    def remove(self, scan_name):
        if not self.is_valid_scan(scan_name):
            return False

        scan = self.storage_service.get_by_name(scan_name)

        task_id = scan['OPENVAS']['task_id']

        response = self.gmp.delete_task(task_id,ultimate=False)

        print(f'[{self.name}]  scan removed ')
        
        return response
    
        
    def list_scans(self):


        self.tasks = self.gmp.get_tasks()
        task_names = self.tasks.xpath('task/name/text()')
        print("Available scan names from openvas")
        pretty_print(task_names)
        return task_names

    def start_sp(self,scan_name):
        if not self.is_valid_scan(scan_name):
            return False
        scan_data = self.storage_service.get_by_name(scan_name)
        print(f'[{self.name}] Starting Scan: {scan_name}')
        task_id = scan_data['OPENVAS']['task_id']
        start_task_response= self.gmp.start_task(task_id)
        print(f'[{self.name}] Task started')
        report_id = start_task_response[0].text

        scan_data['OPENVAS'] = {
            'report_id':  report_id,

            'scan_status': {
                'status': 'INPROGRESS'
            }
        }
        self.storage_service.update_by_name(scan_name, scan_data)
