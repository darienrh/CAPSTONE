"""Version 2 - Quick problem injection for demo (no user input, no write memory)"""

import telnetlib
import requests
from requests.auth import HTTPBasicAuth
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed


def get_console_port(gns3_url, project_id, device_name, auth):
    """Get console port for a device"""
    try:
        response = requests.get(
            f"{gns3_url}/v2/projects/{project_id}/nodes",
            auth=auth,
            timeout=5
        )
        response.raise_for_status()
        nodes = response.json()

        for node in nodes:
            if node['name'] == device_name:
                return node.get('console')
        return None
    except Exception as e:
        print(f"Error getting console port for {device_name}: {e}")
        return None


def send_commands_bulk(tn, commands, delay=0.3):
    """Send multiple commands to device"""
    try:
        for cmd in commands:
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(delay)
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except Exception as e:
        print(f"Error sending commands: {e}")
        return False


def clear_and_enable(tn):
    """Clear line and get to enable mode"""
    try:
        tn.write(b'\x03\r\n')
        time.sleep(0.2)
        tn.write(b'enable\r\n')
        time.sleep(0.2)
        tn.read_very_eager()
        return True
    except Exception as e:
        print(f"Error in clear_and_enable: {e}")
        return False


def inject_problems_on_device(device_name, port, problem_set, gns3_host='localhost'):
    """Inject all problems on a single device in one session"""
    results = []
    
    try:
        tn = telnetlib.Telnet(gns3_host, port, timeout=5)
        
        if not clear_and_enable(tn):
            tn.close()
            return []
        
        all_commands = ["configure terminal"]
        
        for problem_type, params in problem_set:
            if problem_type == 'shutdown':
                all_commands.extend([
                    f"interface {params['interface']}",
                    "shutdown",
                    "exit"
                ])
                results.append(f"{device_name}: {params['interface']} shutdown")
            
            elif problem_type == 'eigrp_stub':
                all_commands.extend([
                    "router eigrp 1",
                    "eigrp stub connected",
                    "exit"
                ])
                results.append(f"{device_name}: EIGRP stub configured")
            
            elif problem_type == 'eigrp_k_values':
                all_commands.extend([
                    "router eigrp 1",
                    "metric weights 0 2 0 1 0 0",
                    "exit"
                ])
                results.append(f"{device_name}: EIGRP non-default K-values")
            
            elif problem_type == 'eigrp_passive':
                all_commands.extend([
                    "router eigrp 1",
                    f"passive-interface {params['interface']}",
                    "exit"
                ])
                results.append(f"{device_name}: EIGRP passive interface {params['interface']}")
            
            elif problem_type == 'eigrp_timers':
                all_commands.extend([
                    f"interface {params['interface']}",
                    "ip hello-interval eigrp 1 1",
                    "ip hold-time eigrp 1 3",
                    "exit"
                ])
                results.append(f"{device_name}: EIGRP non-default timers on {params['interface']}")
            
            elif problem_type == 'ospf_stub':
                all_commands.extend([
                    "router ospf 10",
                    f"area {params.get('area', '1')} stub",
                    "exit"
                ])
                results.append(f"{device_name}: OSPF area {params.get('area', '1')} stub")
            
            elif problem_type == 'ospf_passive':
                all_commands.extend([
                    "router ospf 10",
                    f"passive-interface {params['interface']}",
                    "exit"
                ])
                results.append(f"{device_name}: OSPF passive interface {params['interface']}")
            
            elif problem_type == 'ospf_timers':
                all_commands.extend([
                    f"interface {params['interface']}",
                    "ip ospf hello-interval 30",
                    "ip ospf dead-interval 120",
                    "exit"
                ])
                results.append(f"{device_name}: OSPF non-default timers on {params['interface']}")
            
            elif problem_type == 'ospf_wrong_area_network':
                all_commands.extend([
                    "router ospf 10",
                    f"no network {params['network']} {params['wildcard']} area {params['correct_area']}",
                    f"network {params['network']} {params['wildcard']} area {params['wrong_area']}",
                    "exit"
                ])
                results.append(f"{device_name}: OSPF wrong area on {params['network']} (area {params['wrong_area']} instead of area {params['correct_area']})")
            
            elif problem_type == 'ospf_dup_rid':
                all_commands.extend([
                    "router ospf 10",
                    f"router-id {params.get('rid', '1.1.1.1')}",
                    "exit"
                ])
                results.append(f"{device_name}: OSPF router-id {params.get('rid', '1.1.1.1')}")
        
        all_commands.append("end")
        
        if send_commands_bulk(tn, all_commands):
            tn.close()
            return results
        
        tn.close()
        return []
    
    except Exception as e:
        print(f"Exception on {device_name}: {e}")
        return []


def main():
    print("Injecting problems for demo...\n")
    
    GNS3_URL = "http://192.168.231.1:3080"
    USERNAME = "admin"
    PASSWORD = "qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS"
    auth = HTTPBasicAuth(USERNAME, PASSWORD)
    
    from urllib.parse import urlparse
    gns3_host = urlparse(GNS3_URL).hostname
    
    try:
        response = requests.get(f"{GNS3_URL}/v2/projects", auth=auth, timeout=5)
        response.raise_for_status()
        projects = response.json()
        
        project_id = None
        for project in projects:
            if project['status'] == 'opened':
                project_id = project['project_id']
                break
        
        if not project_id:
            print("No opened project found")
            return
    except Exception as e:
        print(f"Failed to connect to GNS3: {e}")
        return
    
    devices = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6']
    ports = {}
    
    for device in devices:
        port = get_console_port(GNS3_URL, project_id, device, auth)
        if port:
            ports[device] = port
    
    if not ports:
        print("No devices found")
        return
    
    problem_definitions = {
        'R1': [
            ('shutdown', {'interface': 'FastEthernet1/0'})
        ],
        'R2': [
            ('eigrp_passive', {'interface': 'FastEthernet1/0'}),
            ('eigrp_stub', {})
        ],
        'R3': [
            ('eigrp_k_values', {}),
            ('eigrp_timers', {'interface': 'FastEthernet0/0'})
        ],
        'R4': [
            ('ospf_timers', {'interface': 'Serial0/0'})
        ],
        'R5': [
            ('ospf_stub', {'area': '1'}),
            ('ospf_wrong_area_network', {
                'network': '192.168.10.0',
                'wildcard': '0.0.0.255',
                'correct_area': '0',
                'wrong_area': '1'
            }),
            ('ospf_dup_rid', {'rid': '1.1.1.1'})
        ],
        'R6': [
            ('ospf_passive', {'interface': 'FastEthernet0/0'}),
            ('ospf_dup_rid', {'rid': '1.1.1.1'})
        ]
    }
    
    print("Injecting problems...")
    start_time = time.time()
    
    injected = []
    
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {}
        
        for device, port in ports.items():
            if device in problem_definitions:
                future = executor.submit(
                    inject_problems_on_device,
                    device,
                    port,
                    problem_definitions[device],
                    gns3_host
                )
                futures[future] = device
        
        for future in as_completed(futures):
            device = futures[future]
            try:
                results = future.result()
                injected.extend(results)
                print(f"✓ {device}: {len(results)} problems")
            except Exception as e:
                print(f"✗ {device}: {e}")
    
    elapsed = time.time() - start_time
    
    print(f"\n{'='*50}")
    print(f"Injected {len(injected)} problems in {elapsed:.2f}s")
    print("="*50)
    print("\nReady for demo - run the diagnostic tool!")


if __name__ == "__main__":
    main()