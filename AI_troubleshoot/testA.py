#!/usr/bin/env python3

import telnetlib
import time
from config_parser import get_device_baseline, load_latest_stable_config

load_latest_stable_config()

print("="*60)
print("R2 BASELINE CHECK")
print("="*60)
r2_baseline = get_device_baseline('R2')
print(f"R2 Fa0/0: {r2_baseline.get('interfaces', {}).get('FastEthernet0/0', {})}")

print("\n" + "="*60)
print("R4 BASELINE CHECK")
print("="*60)
r4_baseline = get_device_baseline('R4')
r4_fa00 = r4_baseline.get('interfaces', {}).get('FastEthernet0/0', {})
print(f"R4 Fa0/0: {r4_fa00}")
print(f"  Has IP: {bool(r4_fa00.get('ip_address'))}")
print(f"  Shutdown: {r4_fa00.get('shutdown', False)}")

print("\n" + "="*60)
print("R5 OSPF BASELINE")
print("="*60)
r5_baseline = get_device_baseline('R5')
print(f"R5 OSPF: {r5_baseline.get('ospf', {})}")
print(f"  Stub areas: {r5_baseline.get('ospf', {}).get('stub_areas', [])}")

print("\n" + "="*60)
print("R6 OSPF BASELINE")
print("="*60)
r6_baseline = get_device_baseline('R6')
print(f"R6 OSPF: {r6_baseline.get('ospf', {})}")
print(f"  Router ID: {r6_baseline.get('ospf', {}).get('router_id')}")
print(f"  Passive intfs: {r6_baseline.get('ospf', {}).get('passive_interfaces', [])}")

print("\n" + "="*60)
print("LIVE R5 CONFIG CHECK")
print("="*60)
try:
    import requests
    from requests.auth import HTTPBasicAuth
    
    auth = HTTPBasicAuth("admin", "qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS")
    resp = requests.get("http://localhost:3080/v2/projects", auth=auth)
    projects = resp.json()
    
    for project in projects:
        if project['status'] == 'opened':
            resp = requests.get(f"http://localhost:3080/v2/projects/{project['project_id']}/nodes", auth=auth)
            nodes = resp.json()
            
            for node in nodes:
                if node['name'] == 'R5':
                    port = node.get('console')
                    print(f"Found R5 on port {port}")
                    
                    tn = telnetlib.Telnet('localhost', port, timeout=5)
                    time.sleep(0.2)
                    
                    tn.write(b'\x03\r\n')
                    time.sleep(0.1)
                    tn.write(b'enable\r\n')
                    time.sleep(0.1)
                    tn.write(b'show running-config | include area.*stub\r\n')
                    time.sleep(1)
                    output = tn.read_very_eager().decode('ascii', errors='ignore')
                    print(f"R5 stub config:\n{output}")
                    
                    tn.close()
                    break
except Exception as e:
    print(f"Error: {e}")