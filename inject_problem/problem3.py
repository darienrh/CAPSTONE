#!/usr/bin/env python3
"""
Problem Injection Script - Slimmed Down
"""

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


def send_commands(tn, commands, delay=0.5):
    """Send multiple commands to device"""
    try:
        for cmd in commands:
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(delay)
            tn.read_very_eager()
        return True
    except:
        return False


def clear_and_enable(tn):
    """Clear line and get to enable mode"""
    tn.write(b'\x03')
    time.sleep(0.3)
    tn.write(b'enable\r\n')
    time.sleep(0.3)
    tn.read_very_eager()


def inject_shutdown(port, interface):
    """Shutdown an interface"""
    try:
        tn = telnetlib.Telnet('localhost', port, timeout=5)
        clear_and_enable(tn)
        
        commands = [
            "configure terminal",
            f"interface {interface}",
            "shutdown",
            "end",
        ]
        
        if send_commands(tn, commands):
            tn.close()
            return True
        tn.close()
        return False
    except:
        return False


def inject_eigrp_stub(port):
    """Configure EIGRP stub"""
    try:
        tn = telnetlib.Telnet('localhost', port, timeout=5)
        clear_and_enable(tn)
        
        commands = [
            "configure terminal",
            "router eigrp 1",
            "eigrp stub connected",
            "end",
        ]
        
        if send_commands(tn, commands):
            tn.close()
            return True
        tn.close()
        return False
    except:
        return False


def inject_eigrp_k_values(port):
    """Change EIGRP K-values"""
    try:
        tn = telnetlib.Telnet('localhost', port, timeout=5)
        clear_and_enable(tn)
        
        commands = [
            "configure terminal",
            "router eigrp 1",
            "metric weights 0 2 0 1 0 0",
            "end",
        ]
        
        if send_commands(tn, commands):
            tn.close()
            return True
        tn.close()
        return False
    except:
        return False


def inject_eigrp_passive(port, interface):
    """Configure EIGRP passive interface"""
    try:
        tn = telnetlib.Telnet('localhost', port, timeout=5)
        clear_and_enable(tn)
        
        commands = [
            "configure terminal",
            "router eigrp 1",
            f"passive-interface {interface}",
            "end",
        ]
        
        if send_commands(tn, commands):
            tn.close()
            return True
        tn.close()
        return False
    except:
        return False


def inject_eigrp_timers(port, interface):
    """Change EIGRP hello/hold timers"""
    try:
        tn = telnetlib.Telnet('localhost', port, timeout=5)
        clear_and_enable(tn)
        
        commands = [
            "configure terminal",
            f"interface {interface}",
            "ip hello-interval eigrp 1 1",
            "ip hold-time eigrp 1 3",
            "end",
        ]
        
        if send_commands(tn, commands):
            tn.close()
            return True
        tn.close()
        return False
    except:
        return False


def inject_ospf_stub(port):
    """Configure OSPF stub area"""
    try:
        tn = telnetlib.Telnet('localhost', port, timeout=5)
        clear_and_enable(tn)
        
        commands = [
            "configure terminal",
            "router ospf 10",
            "area 0 stub",
            "end",
        ]
        
        if send_commands(tn, commands):
            tn.close()
            return True
        tn.close()
        return False
    except:
        return False


def inject_ospf_passive(port, interface):
    """Configure OSPF passive interface"""
    try:
        tn = telnetlib.Telnet('localhost', port, timeout=5)
        clear_and_enable(tn)
        
        commands = [
            "configure terminal",
            "router ospf 10",
            f"passive-interface {interface}",
            "end",
        ]
        
        if send_commands(tn, commands):
            tn.close()
            return True
        tn.close()
        return False
    except:
        return False


def inject_ospf_timers(port, interface):
    """Change OSPF timers"""
    try:
        tn = telnetlib.Telnet('localhost', port, timeout=5)
        clear_and_enable(tn)
        
        commands = [
            "configure terminal",
            f"interface {interface}",
            "ip ospf hello-interval 30",
            "ip ospf dead-interval 120",
            "end",
        ]
        
        if send_commands(tn, commands):
            tn.close()
            return True
        tn.close()
        return False
    except:
        return False


def inject_ospf_wrong_area(port, interface):
    """Configure wrong OSPF area"""
    try:
        tn = telnetlib.Telnet('localhost', port, timeout=5)
        clear_and_enable(tn)
        
        commands = [
            "configure terminal",
            f"interface {interface}",
            "ip ospf 10 area 1",
            "end",
        ]
        
        if send_commands(tn, commands):
            tn.close()
            return True
        tn.close()
        return False
    except:
        return False


def inject_ospf_dup_rid(port):
    """Configure duplicate OSPF router ID"""
    try:
        tn = telnetlib.Telnet('localhost', port, timeout=5)
        clear_and_enable(tn)
        
        commands = [
            "configure terminal",
            "router ospf 10",
            "router-id 1.1.1.1",
            "end",
        ]
        
        if send_commands(tn, commands):
            tn.close()
            return True
        tn.close()
        return False
    except:
        return False


def main():
    print("Starting problem injection...\n")
    
    # Configuration
    GNS3_URL = "http://localhost:3080"
    auth = HTTPBasicAuth("admin", "qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS")
    
    # Get project ID
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
            return
    except:
        print("Failed to connect to GNS3")
        return
    
    # Get console ports
    devices = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']
    ports = {}
    
    for device in devices:
        port = get_console_port(GNS3_URL, project_id, device, auth)
        if port:
            ports[device] = port
            print(f"Found {device} on port {port}")
    
    if not ports:
        print("No devices found")
        return
    
    print("\nInjecting problems...")
    injected = []
    
    # Inject problems based on device
    if 'R1' in ports:
        if inject_shutdown(ports['R1'], 'FastEthernet1/0'):
            injected.append("R1: FastEthernet1/0 shutdown")
        if inject_eigrp_passive(ports['R1'], 'FastEthernet2/0'):
            injected.append("R1: EIGRP passive interface FastEthernet2/0")
    
    if 'R2' in ports:
        if inject_eigrp_stub(ports['R2']):
            injected.append("R2: EIGRP stub configured")
        if inject_eigrp_timers(ports['R2'], 'FastEthernet0/0'):
            injected.append("R2: EIGRP non-default timers on FastEthernet0/0")
    
    if 'R3' in ports:
        if inject_eigrp_k_values(ports['R3']):
            injected.append("R3: EIGRP non-default K-values")
        if inject_shutdown(ports['R3'], 'FastEthernet0/0'):
            injected.append("R3: FastEthernet0/0 shutdown")
    
    if 'R4' in ports:
        if inject_shutdown(ports['R4'], 'FastEthernet0/0'):
            injected.append("R4: FastEthernet0/0 shutdown")
        if inject_ospf_timers(ports['R4'], 'Serial0/0'):
            injected.append("R4: OSPF non-default timers on Serial0/0")
    
    if 'R5' in ports:
        if inject_ospf_stub(ports['R5']):
            injected.append("R5: OSPF stub area")
        if inject_ospf_wrong_area(ports['R5'], 'Serial0/1'):
            injected.append("R5: OSPF wrong area on Serial0/1")
    
    if 'R6' in ports:
        if inject_ospf_passive(ports['R6'], 'FastEthernet0/0'):
            injected.append("R6: OSPF passive interface FastEthernet0/0")
        if inject_ospf_dup_rid(ports['R6']):
            injected.append("R6: OSPF duplicate router ID")
    
    # Results
    print("\n" + "="*50)
    print("INJECTED PROBLEMS:")
    for problem in injected:
        print(f"✓ {problem}")
    
    print(f"\nTotal: {len(injected)} problems injected")
    print("="*50)


if __name__ == "__main__":
    main()