"""3 problems: R1 interface shut, R3 stub, R6 passive interface"""
import warnings
warnings.filterwarnings('ignore', message="'telnetlib' is deprecated")
import telnetlib
import requests
from requests.auth import HTTPBasicAuth
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console
from rich.prompt import Confirm

console = Console()


def get_console_port(gns3_url, project_id, device_name, auth):
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
    tn.write(b'\x03')
    time.sleep(0.2)
    tn.write(b'enable\r\n')
    time.sleep(0.2)
    tn.read_very_eager()


def inject_problems_on_device(device_name, port, problem_set):
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
            
            elif problem_type == 'eigrp_timers':
                all_commands.extend([
                    f"interface {params['interface']}",
                    "ip hello-interval eigrp 1 1",
                    "ip hold-time eigrp 1 3",
                    "exit"
                ])
                results.append(f"{device_name}: EIGRP non-default timers on {params['interface']}")
            
            elif problem_type == 'ospf_passive':
                all_commands.extend([
                    "router ospf 10",
                    f"passive-interface {params['interface']}",
                    "exit"
                ])
                results.append(f"{device_name}: OSPF passive interface {params['interface']}")
        
        all_commands.append("end")
        
        if send_commands_bulk(tn, all_commands):
            tn.close()
            return results
        
        tn.close()
        return []
        
    except Exception:
        return []


def main():
    console.print("[bold blue]Problem Injection Tool[/bold blue]", justify="center")
    
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
            console.print("[bold red]✗ No opened project found[/bold red]")
            return
    except:
        console.print("[bold red]✗ Failed to connect to GNS3[/bold red]")
        return
    
    devices = ['R1', 'R3', 'R6']
    ports = {}
    
    for device in devices:
        port = get_console_port(GNS3_URL, project_id, device, auth)
        if port:
            ports[device] = port
    
    if not ports:
        console.print("[bold red]✗ No devices found[/bold red]")
        return
    
    problem_definitions = {
        'R1': [('shutdown', {'interface': 'FastEthernet0/0'})],
        'R3': [('eigrp_timers', {'interface': 'FastEthernet0/0'})],
        'R6': [('ospf_passive', {'interface': 's0/0'})]
    }
    
    console.print("\n[cyan]Commands:[/cyan]")
    console.print("  • R1: FastEthernet0/0 shutdown")
    console.print("  • R3: EIGRP timer mismatch on FastEthernet0/0")
    console.print("  • R6: OSPF passive interface on s0/0")
    
    if not Confirm.ask("\nProceed? "):
        console.print("[bold red]✗ Injection aborted[/bold red]")
        return
    
    start_time = time.time()
    injected = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
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
            results = future.result()
            injected.extend(results)
    
    elapsed = time.time() - start_time
    
    interface_issues = [p for p in injected if 'shutdown' in p]
    eigrp_issues = [p for p in injected if 'EIGRP' in p]
    ospf_issues = [p for p in injected if 'OSPF' in p]
    
    if interface_issues:
        console.print("\n[pink1]INTERFACE PROBLEMS:[/pink1]")
        for problem in interface_issues:
            console.print(f"  [green]✓[/green] {problem}")
    
    if eigrp_issues:
        console.print("\n[orange1]EIGRP PROBLEMS:[/orange1]")
        for problem in eigrp_issues:
            console.print(f"  [green]✓[/green] {problem}")
    
    if ospf_issues:
        console.print("\n[blue]OSPF PROBLEMS:[/blue]")
        for problem in ospf_issues:
            console.print(f"  [green]✓[/green] {problem}")
    
    success_count = len(injected)
    total_problems = sum(len(v) for v in problem_definitions.values())
    
    print("\n" + "=" * 70)
    if success_count == total_problems:
        console.print(f"[green]✓ Successfully injected: {success_count}/{total_problems} problems[/green]")
    else:
        console.print(f"[red]✗ Injection failed: {success_count}/{total_problems} problems[/red]")
    print(f"Time: {elapsed:.2f} seconds")


if __name__ == "__main__":
    main()