"""Version 2 (Not all of these problems are correctly fixed yet)"""

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
            auth=auth
        )
        nodes = response.json()

        for node in nodes:
            if node['name'] == device_name:
                return node.get('console')
        return None
    except:
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
    except:
        return False


def clear_and_enable(tn):
    """Clear line and get to enable mode"""
    tn.write(b'\x03')
    time.sleep(0.2)
    tn.write(b'enable\r\n')
    time.sleep(0.2)
    tn.read_very_eager()


def inject_problems_on_device(device_name, port, problem_set):
    """Inject all problems on a single device in one session"""
    results = []
    
    try:
        tn = telnetlib.Telnet('localhost', port, timeout=5)
        clear_and_enable(tn)
        
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
                # Configure a non-backbone area as stub
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
            
            elif problem_type == 'ospf_wrong_area':
                # Put interface in wrong area using interface command
                all_commands.extend([
                    f"interface {params['interface']}",
                    f"ip ospf 10 area {params.get('wrong_area', '1')}",
                    "exit"
                ])
                results.append(f"{device_name}: OSPF wrong area on {params['interface']}")
            
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
        return []


def main():
    print("Starting minimal problem injection (one of each type)...\n")
    
    GNS3_URL = "http://localhost:3080"
    auth = HTTPBasicAuth("admin", "qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS")
    
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
    
    # Minimal problem set - ONE of each type
    problem_definitions = {
        # Interface shutdown - one device
        'R1': [
            ('shutdown', {'interface': 'FastEthernet1/0'})
        ],
        
        # EIGRP problems - one of each
        'R2': [
            ('eigrp_passive', {'interface': 'FastEthernet2/0'}),  # Wrong passive
            ('eigrp_stub', {})  # Incorrect stub
        ],
        
        'R3': [
            ('eigrp_k_values', {}),  # Non-default K-values
            ('eigrp_timers', {'interface': 'FastEthernet0/0'})  # Timer mismatch
        ],
        
        # OSPF problems - one of each
        'R4': [
            ('ospf_timers', {'interface': 'Serial0/0'})  # Hello/dead mismatch
        ],
        
        'R5': [
            ('ospf_stub', {'area': '1'}),  # Unexpected stub area
            ('ospf_wrong_area', {'interface': 'Serial0/1', 'wrong_area': '1'}),  # Wrong area
            ('ospf_dup_rid', {'rid': '1.1.1.1'})  # Duplicate RID (part 1)
        ],
        
        'R6': [
            ('ospf_passive', {'interface': 'FastEthernet0/0'}),  # Wrong passive
            ('ospf_dup_rid', {'rid': '1.1.1.1'})  # Duplicate RID (part 2)
        ]
    }
    
    print("\n" + "="*70)
    print("PROBLEM INJECTION PLAN (One of Each Type):")
    print("="*70)
    
    # Show what will be injected
    total_problems = 0
    for device, problems in problem_definitions.items():
        if device in ports:
            print(f"\n{device}:")
            for problem_type, params in problems:
                total_problems += 1
                if problem_type == 'shutdown':
                    print(f"  • Interface {params['interface']} shutdown")
                elif problem_type == 'eigrp_stub':
                    print(f"  • EIGRP stub (incorrect)")
                elif problem_type == 'eigrp_k_values':
                    print(f"  • EIGRP non-default K-values")
                elif problem_type == 'eigrp_passive':
                    print(f"  • EIGRP passive interface {params['interface']}")
                elif problem_type == 'eigrp_timers':
                    print(f"  • EIGRP timers on {params['interface']}")
                elif problem_type == 'ospf_stub':
                    print(f"  • OSPF area {params.get('area', '1')} stub")
                elif problem_type == 'ospf_passive':
                    print(f"  • OSPF passive interface {params['interface']}")
                elif problem_type == 'ospf_timers':
                    print(f"  • OSPF timers on {params['interface']}")
                elif problem_type == 'ospf_wrong_area':
                    print(f"  • OSPF {params['interface']} in area {params.get('wrong_area', '1')}")
                elif problem_type == 'ospf_dup_rid':
                    print(f"  • OSPF router-id {params.get('rid', '1.1.1.1')}")
    
    print(f"\n{'='*70}")
    print("SUMMARY:")
    print("  • 1x Interface shutdown")
    print("  • 1x EIGRP passive interface (incorrect)")
    print("  • 1x EIGRP stub (incorrect)")
    print("  • 1x EIGRP K-values (non-default)")
    print("  • 1x EIGRP timers (non-default)")
    print("  • 1x OSPF passive interface (incorrect)")
    print("  • 1x OSPF timers (non-default)")
    print("  • 1x OSPF stub area (unexpected)")
    print("  • 1x OSPF wrong area")
    print("  • 1x OSPF duplicate RID (R5 and R6 both = 1.1.1.1)")
    print(f"\nTotal: {total_problems} configuration changes")
    print("="*70)
    
    response = input("\nProceed with injection? [y/N]: ").strip().lower()
    if response != 'y':
        print("Aborted.")
        return
    
    print("\nInjecting problems concurrently...")
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
                    problem_definitions[device]
                )
                futures[future] = device
        
        for future in as_completed(futures):
            device = futures[future]
            try:
                results = future.result()
                injected.extend(results)
                print(f"✓ Completed {device}: {len(results)} problems")
            except Exception as e:
                print(f"✗ Failed {device}: {e}")
    
    elapsed = time.time() - start_time
    
    print("\n" + "="*70)
    print("INJECTION COMPLETE:")
    print("="*70)
    
    # Group by category
    interface_issues = [p for p in injected if 'shutdown' in p]
    eigrp_issues = [p for p in injected if 'EIGRP' in p]
    ospf_issues = [p for p in injected if 'OSPF' in p]
    
    if interface_issues:
        print("\nINTERFACE PROBLEMS:")
        for problem in interface_issues:
            print(f"  ✓ {problem}")
    
    if eigrp_issues:
        print("\nEIGRP PROBLEMS:")
        for problem in eigrp_issues:
            print(f"  ✓ {problem}")
    
    if ospf_issues:
        print("\nOSPF PROBLEMS:")
        for problem in ospf_issues:
            print(f"  ✓ {problem}")
    
    print(f"\n{'='*70}")
    print(f"Successfully injected: {len(injected)}/{total_problems} problems")
    print(f"Time: {elapsed:.2f} seconds")
    print("="*70)
    
    print("\n💡 TIP: Run your diagnostic runner to detect these problems!")
    print("   python3 runner.py\n")


if __name__ == "__main__":
    main()