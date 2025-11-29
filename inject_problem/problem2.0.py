#!/usr/bin/env python3
"""
Inject multiple network problems:
- R1: Shutdown FastEthernet0/0
- R2: Configure EIGRP stub
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


def shutdown_interface(console_port, interface):
    """Shutdown an interface"""
    try:
        tn = telnetlib.Telnet('localhost', console_port, timeout=10)
        
        clear_line_and_reset(tn)
        
        commands = [
            "configure terminal",
            f"interface {interface}",
            "shutdown",
            "end",
            "write memory"
        ]
        
        for cmd in commands:
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(0.5)
            tn.read_very_eager()
        
        time.sleep(1)
        tn.close()
        time.sleep(0.5)
        return True
    except:
        return False


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
            "write memory"
        ]
        
        for cmd in commands:
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(0.5)
            tn.read_very_eager()
        
        time.sleep(1)
        tn.close()
        time.sleep(0.5)
        return True
    except:
        return False


def main():
    print("\nNetwork Problem Injection Tool")
    print("=" * 60)
    
    # Configuration
    GNS3_URL = "http://localhost:3080"
    USERNAME = "admin"
    PASSWORD = "qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS"
    
    R1 = "R1"
    R1_INTERFACE = "FastEthernet0/0"
    R2 = "R2"
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
        
        print(f"Found opened project\n")
        
        # Problem 1: Shutdown R1 interface
        print(f"Problem 1: Shutting down {R1_INTERFACE} on {R1}...")
        r1_port = get_console_port(GNS3_URL, project_id, R1, auth)
        
        if not r1_port:
            print(f"Device {R1} not found")
        elif shutdown_interface(r1_port, R1_INTERFACE):
            print(f"Success: {R1_INTERFACE} on {R1} shut down")
        else:
            print(f"Failed to shutdown interface on {R1}")
        
        print()
        
        # Problem 2: Configure EIGRP stub on R2
        print(f"Problem 2: Configuring EIGRP stub on {R2}...")
        r2_port = get_console_port(GNS3_URL, project_id, R2, auth)
        
        if not r2_port:
            print(f"Device {R2} not found")
        elif inject_eigrp_stub(r2_port, AS_NUMBER):
            print(f"Success: EIGRP stub configured on {R2}")
        else:
            print(f"Failed to configure EIGRP stub on {R2}")
        
        print("\n" + "=" * 60)
        print("Problem injection complete!")
        print("Run diagnostic_runner.py to detect and fix these issues")
        print("=" * 60)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()