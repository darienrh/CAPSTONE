#!/usr/bin/env python3
"""
Inject EIGRP stub misconfiguration problem
"""

import warnings
warnings.filterwarnings('ignore')

import telnetlib
import requests
from requests.auth import HTTPBasicAuth
import time
import sys


def get_console_port(gns3_url, project_id, device_name, auth):
    """Get console port for a device"""
    try:
        response = requests.get(
            f"{gns3_url}/v2/projects/{project_id}/nodes", 
            auth=auth
        )
        nodes = response.json()
        
        for node in nodes:
            if node['name'] == device_name:
                return node.get('console')
        return None
    except:
        return None


def clear_line_and_reset(tn):
    """Clear any partial commands and return to privileged exec mode"""
    for _ in range(10):
        tn.write(b'\x08')
        time.sleep(0.05)
    
    tn.write(b'\x03')
    time.sleep(0.3)
    tn.read_very_eager()
    
    tn.write(b'end\r\n')
    time.sleep(0.5)
    tn.read_very_eager()
    
    tn.write(b'enable\r\n')
    time.sleep(0.3)
    tn.read_very_eager()
    
    tn.write(b'\r\n')
    time.sleep(0.3)
    tn.read_very_eager()


def inject_eigrp_stub(console_port, as_number=1):
    """Configure EIGRP stub on a router"""
    try:
        tn = telnetlib.Telnet('localhost', console_port, timeout=10)
        
        clear_line_and_reset(tn)
        
        commands = [
            "configure terminal",
            f"router eigrp {as_number}",
            "eigrp stub connected",
            "end",
        ]
        
        for cmd in commands:
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(0.5)
            tn.read_very_eager()
        
        time.sleep(1)
        
        tn.close()
        return True
    except:
        return False


def main():
    # Configuration
    GNS3_URL = "http://localhost:3080"
    USERNAME = "admin"
    PASSWORD = "qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS"
    DEVICE = "R1"
    AS_NUMBER = 1
    
    auth = HTTPBasicAuth(USERNAME, PASSWORD)
    
    # Get opened project
    try:
        response = requests.get(f"{GNS3_URL}/v2/projects", auth=auth)
        projects = response.json()
        
        project_id = None
        for project in projects:
            if project['status'] == 'opened':
                project_id = project['project_id']
                break
        
        if not project_id:
            print("No opened project found")
            sys.exit(1)
        
        # Get console port
        console_port = get_console_port(GNS3_URL, project_id, DEVICE, auth)
        
        if not console_port:
            print(f"Device {DEVICE} not found")
            sys.exit(1)
        
        # Inject EIGRP stub configuration
        print(f"Injecting EIGRP stub configuration on {DEVICE}...")
        if inject_eigrp_stub(console_port, AS_NUMBER):
            print(f"EIGRP stub configured on {DEVICE}")
            print(f"This will cause neighbor adjacency issues if neighbor is not also stub")
        else:
            print("Failed to inject EIGRP stub configuration")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()