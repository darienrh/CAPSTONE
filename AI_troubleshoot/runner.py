#!/usr/bin/env python3

import warnings
warnings.filterwarnings('ignore')

import requests
from requests.auth import HTTPBasicAuth
import sys
import atexit
import telnetlib
import time
import re
from datetime import datetime
from pathlib import Path
import concurrent.futures
from threading import Lock
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.prompt import Confirm
from interface_tree import troubleshoot_device as troubleshoot_interfaces, verify_interface_status
from eigrp_tree import troubleshoot_eigrp, verify_eigrp_neighbors, get_eigrp_fix_commands
from config_parser import is_eigrp_router, is_ospf_router

try:
    from ospf_tree import troubleshoot_ospf, verify_ospf_neighbors, get_ospf_fix_commands
    OSPF_AVAILABLE = True
except ImportError:
    OSPF_AVAILABLE = False

console = Console()
HISTORY_DIR = Path.home() / "history"
CONFIG_DIR = Path.home() / "history" / "configs"

def connect_device(console_port, timeout=3):
    try:
        tn = telnetlib.Telnet('localhost', console_port, timeout=timeout)
        time.sleep(0.05)
        
        commands = [b'\r\n', b'\r\n', b'\x03', b'enable\r\n', b'\r\n']
        for cmd in commands:
            tn.write(cmd)
            time.sleep(0.05)
        
        return tn
    except Exception:
        return None

def close_device(tn):
    if tn:
        try:
            tn.write(b'end\r\n')
            tn.close()
        except:
            pass

def send_commands(tn, commands, delay=0.3):
    try:
        for cmd in commands:
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(delay)
            tn.read_very_eager()
        return True
    except:
        return False

def get_next_filename(directory, prefix, extension="txt"):
    directory.mkdir(parents=True, exist_ok=True)
    existing_files = list(directory.glob(f"{prefix}*.{extension}"))
    
    if not existing_files:
        return directory / f"{prefix}.{extension}"
    
    max_num = 0
    for file in existing_files:
        match = re.match(f'{prefix}(\\d*)\\.{extension}', file.name)
        if match:
            num_str = match.group(1)
            current_num = 0 if num_str == '' else int(num_str)
            max_num = max(max_num, current_num)
    
    next_num = max_num + 10
    return directory / f"{prefix}{next_num}.{extension}"

def save_history(fix_results, timestamp):
    try:
        filename = get_next_filename(HISTORY_DIR, "run")
        
        with open(filename, 'w') as f:
            f.write(f"Run Timestamp: {timestamp}\n{'=' * 80}\n\n")
            f.write("FINAL COMPLETION SUMMARY\n{'=' * 80}\n\n")
            
            if not fix_results:
                f.write("No fixes were applied during this run.\n")
            else:
                for i, result in enumerate(fix_results, 1):
                    f.write(f"Fix #{i}\nDevice: {result['device']}\n")
                    f.write(f"Commands Executed:\n")
                    for line in result['commands'].split('\n'):
                        f.write(f"  {line}\n")
                    f.write(f"Verification: {result['verification']}\n{'-' * 80}\n\n")
                f.write(f"Total fixes applied: {len(fix_results)}\n")
        
        console.print(f"\n[green]History saved to: {filename}[/green]")
        return True
    except Exception as e:
        console.print(f"[red]Failed to save history: {e}[/red]")
        return False

def save_stable_configs(device_configs, timestamp):
    try:
        filename = get_next_filename(CONFIG_DIR, "config_stable")
        
        with open(filename, 'w') as f:
            f.write(f"Stable Configurations Timestamp: {timestamp}\n{'=' * 80}\n\n")
            f.write("STABLE ROUTER CONFIGURATIONS\n{'=' * 80}\n\n")
            
            if not device_configs:
                f.write("No configurations were saved.\n")
            else:
                for device_name, config in device_configs.items():
                    f.write(f"DEVICE: {device_name}\n{'=' * 60}\n{config}\n\n")
        
        console.print(f"\n[green]Stable configurations saved to: {filename}[/green]")
        return filename
    except Exception as e:
        console.print(f"[red]Failed to save stable configurations: {e}[/red]")
        return None

def get_router_config(tn, device_name):
    try:
        commands = [
            b'\r\n', b'\x03', b'enable\r\n',
            b'terminal length 0\r\n', b'\r\n',
            b'show running-config\r\n'
        ]
        
        for cmd in commands:
            tn.write(cmd)
            time.sleep(0.05)
        
        time.sleep(0.5)
        config_output = ""
        start_time = time.time()
        
        for _ in range(10):
            try:
                chunk = tn.read_very_eager().decode('ascii', errors='ignore')
                if chunk:
                    config_output += chunk
                    if len(config_output) > 300 and re.search(r'[Rr]\d+(?:\(config\))?#', chunk):
                        break
                time.sleep(0.1)
                if time.time() - start_time > 8:
                    break
            except Exception:
                break
        
        if not config_output or len(config_output) < 200:
            return None
            
        config_output = re.sub(r'^(show running-config|terminal length 0|enable|)$', '',
                              config_output, flags=re.MULTILINE)
        config_output = re.sub(r'^\s*\n', '', config_output, flags=re.MULTILINE)
        
        return config_output.strip()
        
    except Exception:
        return None

class DiagnosticRunner:
    def __init__(self, gns3_url="http://localhost:3080", username="admin", password="qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS"):
        self.gns3_url = gns3_url.rstrip('/')
        self.api_base = f"{self.gns3_url}/v2"
        self.auth = HTTPBasicAuth(username, password) if username else None
        self.nodes = {}
        self.connections = {}
        self.fix_results = []
        self.run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.router_type_cache = {}

    def get_router_type(self, device_name):
        if device_name in self.router_type_cache:
            return self.router_type_cache[device_name]
        
        is_eigrp = is_eigrp_router(device_name)
        is_ospf = OSPF_AVAILABLE and is_ospf_router(device_name)
        
        result = (is_eigrp, is_ospf)
        self.router_type_cache[device_name] = result
        return result

    def connect(self):
        try:
            response = requests.get(f"{self.api_base}/version", auth=self.auth, timeout=3)
            
            if response.status_code == 401:
                self.auth = None
                response = requests.get(f"{self.api_base}/version", timeout=3)

            if response.status_code != 200:
                console.print(f"[bold red]API Error:[/bold red] Status Code {response.status_code}")
                return False

            response = requests.get(f"{self.api_base}/projects", auth=self.auth, timeout=5)
            projects = response.json()

            for project in projects:
                if project['status'] == 'opened':
                    response = requests.get(f"{self.api_base}/projects/{project['project_id']}/nodes", 
                                          auth=self.auth, timeout=5)
                    nodes = response.json()

                    for node in nodes:
                        if node['status'] == 'started' and not node['name'].lower().startswith('switch'):
                            self.nodes[node['name']] = node.get('console')

                    if not self.nodes:
                        console.print("[yellow]No running routers found[/yellow]")
                        return False

                    console.print(f"[green]Found {len(self.nodes)} running router(s).[/green]")
                    return True

            console.print("[bold red]No open project found.[/bold red]")
            return False

        except requests.exceptions.ConnectionError:
            console.print(f"[bold red]Could not reach GNS3 at {self.gns3_url}[/bold red]")
            return False
        except Exception as e:
            console.print(f"[bold red]Connection Error:[/bold red] {str(e)[:100]}")
            return False

    def cleanup_all_connections(self):
        for tn in self.connections.values():
            close_device(tn)
        self.connections.clear()

    def scan_single_device(self, device_name, check_interfaces, check_eigrp, check_ospf, detected_issues, lock):
        console_port = self.nodes.get(device_name)
        if not console_port:
            return

        tn = connect_device(console_port)
        if not tn:
            return

        with lock:
            self.connections[device_name] = tn

        try:
            device_issues = {}
            
            if check_interfaces:
                probs, _ = troubleshoot_interfaces(device_name, tn, auto_prompt=False)
                if probs:
                    device_issues['interfaces'] = probs

            is_eigrp, is_ospf = self.get_router_type(device_name)
            
            if check_eigrp and is_eigrp:
                probs, _ = troubleshoot_eigrp(device_name, tn, auto_prompt=False)
                if probs:
                    device_issues['eigrp'] = probs
            
            if check_ospf and is_ospf:
                from ospf_tree import troubleshoot_ospf
                probs, _ = troubleshoot_ospf(device_name, tn, auto_prompt=False)
                if probs:
                    device_issues['ospf'] = probs
            
            with lock:
                for category, problems in device_issues.items():
                    if problems:
                        detected_issues[category][device_name] = problems
                        
        except Exception:
            pass

    def run_diagnostics(self, device_names, check_interfaces=True, check_eigrp=True, check_ospf=True):
        detected_issues = {'interfaces': {}, 'eigrp': {}, 'ospf': {}}
        
        console.print("\n[bold cyan]PHASE 1: DETECTING ISSUES[/bold cyan]")

        lock = Lock()
        
        max_workers = min(6, len(device_names))
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                     BarColumn(), TimeElapsedColumn(), console=console) as progress:
            
            task = progress.add_task("[cyan]Scanning devices...", total=len(device_names))
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for device_name in device_names:
                    future = executor.submit(
                        self.scan_single_device,
                        device_name, check_interfaces, check_eigrp, check_ospf,
                        detected_issues, lock
                    )
                    futures.append(future)
                
                for _ in concurrent.futures.as_completed(futures):
                    progress.advance(task)
        
        return detected_issues

    def save_stable_configurations(self, device_names):
        console.print("\n[bold cyan]SAVING STABLE CONFIGURATIONS[/bold cyan]")
        
        device_configs = {}
        
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                     BarColumn(), TimeElapsedColumn(), console=console) as progress:
            
            task = progress.add_task("[cyan]Saving configurations...", total=len(device_names))
            
            for device_name in device_names:
                progress.update(task, description=f"[cyan]Saving {device_name}...")
                
                console_port = self.nodes.get(device_name)
                if not console_port:
                    progress.advance(task)
                    continue
                
                tn = self.connections.get(device_name) or connect_device(console_port)
                if not tn:
                    progress.advance(task)
                    continue
                
                config = get_router_config(tn, device_name)
                if config:
                    device_configs[device_name] = config
                
                if device_name not in self.connections:
                    close_device(tn)
                
                progress.advance(task)
        
        if device_configs:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            saved_file = save_stable_configs(device_configs, timestamp)
            if saved_file:
                console.print(f"\n[bold green]✓ Saved {len(device_configs)} stable configuration(s)[/bold green]")
        else:
            console.print("[yellow]No configurations were saved[/yellow]")
        
        return len(device_configs) > 0

    def print_summary_table(self, detected_issues):
        if not detected_issues['interfaces'] and not detected_issues['eigrp'] and not detected_issues.get('ospf'):
            console.print("\n[bold green]✓ No Problems Detected[/bold green]")
            return False

        table = Table(title="Diagnostic Results", show_header=True, header_style="bold magenta")
        table.add_column("Device", style="cyan")
        table.add_column("Category", style="yellow")
        table.add_column("Issue", style="white")
        table.add_column("Status", style="red")

        for device, problems in detected_issues['interfaces'].items():
            for p in problems:
                issue_type = p.get('type', 'shutdown')
                if issue_type == 'ip address mismatch':
                    status = f"IP: {p['current_ip']} (expect: {p['expected_ip']})"
                elif issue_type == 'missing ip address':
                    status = f"Missing IP: {p['expected_ip']}"
                else:
                    status = "Admin Down"
                table.add_row(device, "Interface", p['interface'], status)

        for device, problems in detected_issues['eigrp'].items():
            for p in problems:
                table.add_row(device, "EIGRP", p.get('line', p['type'])[:40], p['type'])
        
        if detected_issues.get('ospf'):
            for device, problems in detected_issues['ospf'].items():
                for p in problems:
                    table.add_row(device, "OSPF", p.get('line', p['type'])[:40], p['type'])

        console.print(table)
        return True

    def apply_fixes(self, detected_issues):
        console.print("\n[bold cyan]PHASE 2: APPLYING FIXES[/bold cyan]")

        for device, problems in detected_issues['interfaces'].items():
            if not problems:
                continue
            tn = self.connections.get(device)
            if not tn:
                continue
                
            for problem in problems:
                interface = problem['interface']
                problem_type = problem.get('type', 'shutdown')
                
                if problem_type == 'ip address mismatch':
                    console.print(f"\n[yellow]Device:[/yellow] {device} | [yellow]Issue:[/yellow] {interface} IP mismatch")
                    console.print(f"  Current: {problem['current_ip']} {problem['current_mask']}")
                    console.print(f"  Expected: {problem['expected_ip']} {problem['expected_mask']}")
                    if Confirm.ask("Fix IP address?"):
                        from interface_tree import fix_interface_ip
                        if fix_interface_ip(tn, interface, problem['expected_ip'], problem['expected_mask']):
                            console.print(f"[green]✔ Fixed IP on {interface}[/green]")
                            time.sleep(1)
                            verification = verify_interface_status(tn, interface)
                            self.fix_results.append({
                                'device': device,
                                'commands': f"interface {interface}\nip address {problem['expected_ip']} {problem['expected_mask']}",
                                'verification': verification
                            })
                
                elif problem_type == 'missing ip address':
                    console.print(f"\n[yellow]Device:[/yellow] {device} | [yellow]Issue:[/yellow] {interface} missing IP")
                    console.print(f"  Expected: {problem['expected_ip']} {problem['expected_mask']}")
                    if Confirm.ask("Configure IP address?"):
                        from interface_tree import fix_interface_ip
                        if fix_interface_ip(tn, interface, problem['expected_ip'], problem['expected_mask']):
                            console.print(f"[green]✔ Configured IP on {interface}[/green]")
                            time.sleep(1)
                            verification = verify_interface_status(tn, interface)
                            self.fix_results.append({
                                'device': device,
                                'commands': f"interface {interface}\nip address {problem['expected_ip']} {problem['expected_mask']}",
                                'verification': verification
                            })
                
                else:
                    console.print(f"\n[yellow]Device:[/yellow] {device} | [yellow]Issue:[/yellow] {interface} is Down")
                    if Confirm.ask("Apply 'no shutdown'?"):
                        from interface_tree import fix_interface_shutdown
                        if fix_interface_shutdown(tn, interface):
                            console.print(f"[green]✔ Fixed {interface}[/green]")
                            time.sleep(1)
                            verification = verify_interface_status(tn, interface)
                            self.fix_results.append({
                                'device': device,
                                'commands': f"interface {interface}\nno shutdown",
                                'verification': verification
                            })

        for device, problems in detected_issues['eigrp'].items():
            if not problems:
                continue
            tn = self.connections.get(device)
            if not tn:
                continue
                
            for issue in problems:
                issue_type = issue['type']
                
                if issue_type in ['eigrp hello timer mismatch', 'eigrp hold timer mismatch']:
                    interface = issue.get('interface')
                    current = issue.get('current')
                    expected = issue.get('expected')
                    timer_type = 'Hello' if 'hello' in issue_type else 'Hold'
                    console.print(f"\n[yellow]Device:[/yellow] {device} | [yellow]Issue:[/yellow] {interface} {timer_type} timer")
                    console.print(f"  Current: {current}s | Expected: {expected}s")
                else:
                    console.print(f"\n[yellow]Device:[/yellow] {device} | [yellow]Issue:[/yellow] {issue_type}")
                
                fix_commands = get_eigrp_fix_commands(issue_type, issue, device)
                if not fix_commands:
                    console.print(f"[bold red]Manual intervention required[/bold red]")
                    continue
                if Confirm.ask(f"Apply fix?"):
                    from eigrp_tree import apply_eigrp_fixes
                    if apply_eigrp_fixes(tn, fix_commands):
                        console.print(f"[green]✔ Fixed {issue_type}[/green]")
                        time.sleep(2)
                        verification = verify_eigrp_neighbors(tn)
                        self.fix_results.append({
                            'device': device,
                            'commands': '\n'.join(fix_commands),
                            'verification': verification
                        })
        
        if detected_issues.get('ospf') and OSPF_AVAILABLE:
            from ospf_tree import apply_ospf_fixes, get_ospf_fix_commands, verify_ospf_neighbors
            for device, problems in detected_issues['ospf'].items():
                if not problems:
                    continue
                tn = self.connections.get(device)
                if not tn:
                    continue
                    
                for issue in problems:
                    issue_type = issue['type']
                    console.print(f"\n[yellow]Device:[/yellow] {device} | [yellow]Issue:[/yellow] {issue_type}")
                    fix_commands = get_ospf_fix_commands(issue_type, issue, device)
                    if not fix_commands:
                        console.print(f"[bold red]Manual intervention required[/bold red]")
                        continue
                    if Confirm.ask(f"Apply fix?"):
                        if apply_ospf_fixes(tn, fix_commands):
                            console.print(f"[green]✔ Fixed {issue_type}[/green]")
                            time.sleep(2)
                            verification = verify_ospf_neighbors(tn)
                            self.fix_results.append({
                                'device': device,
                                'commands': '\n'.join(fix_commands),
                                'verification': verification
                            })

    def print_completion_summary(self):
        if not self.fix_results:
            console.print("\n[bold green]✓ No Changes Made[/bold green]")
            return
        
        console.print("\n[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]")
        console.print("[bold green]FINAL COMPLETION SUMMARY[/bold green]", justify="center")
        console.print("[bold cyan]═══════════════════════════════════════════════════════════[/bold cyan]")
        
        table = Table(show_header=True, header_style="bold magenta", border_style="cyan")
        table.add_column("Device", style="cyan", width=12)
        table.add_column("Commands Executed", style="yellow", width=30)
        table.add_column("Verification", style="green", width=35)
        
        for result in self.fix_results:
            table.add_row(result['device'], result['commands'], result['verification'])
        
        console.print(table)
        console.print(f"\n[bold green]✓ Successfully applied {len(self.fix_results)} fix(es)[/bold green]")
        
        save_history(self.fix_results, self.run_timestamp)

def main():
    runner = DiagnosticRunner()
    atexit.register(runner.cleanup_all_connections)

    console.print("[bold blue]Network Diagnostic Tool[/bold blue]", justify="center")

    if not runner.connect():
        sys.exit(1)

    available_devices = [name for name in runner.nodes.keys() if not name.lower().startswith('switch')]
    device_map = {name.lower(): name for name in available_devices}

    console.print(f"\nAvailable: [green]{', '.join(available_devices)}[/green]")
    user_input = console.input("Enter devices (e.g. 'r1, r2') or Press Enter for all: ").strip()

    final_target_list = []
    if not user_input:
        final_target_list = available_devices
    else:
        for req in [d.strip().lower() for d in user_input.split(',')]:
            if req in device_map:
                final_target_list.append(device_map[req])

    if not final_target_list:
        console.print("[bold red]No valid devices selected. Exiting.[/bold red]")
        sys.exit(1)

    detected_issues = runner.run_diagnostics(final_target_list)
    has_issues = runner.print_summary_table(detected_issues)

    if has_issues and Confirm.ask("\nProceed to fix menu?"):
        runner.apply_fixes(detected_issues)
        runner.print_completion_summary()
    else:
        if not has_issues:
            save_history([], runner.run_timestamp)
    
    console.print("\n" + "=" * 60)
    if Confirm.ask("Save stable configurations of all routers now?"):
        runner.save_stable_configurations(final_target_list)
    
    console.print("\n[bold green]Script completed successfully![/bold green]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold red]Interrupted[/bold red]")
        sys.exit(0)