#!/usr/bin/env python3
"""
Network Diagnostic Runner - Fixed Connection & Case Sensitivity
"""
 
import warnings
warnings.filterwarnings('ignore')
 
import requests
from requests.auth import HTTPBasicAuth
import sys
import atexit
import signal
import telnetlib
import time
import socket
 
# UI Imports
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.prompt import Confirm
 
# Custom imports (Ensure these files exist in the same folder)
from interface_tree import troubleshoot_device as troubleshoot_interfaces
from eigrp_tree import troubleshoot_eigrp
 
# Initialize Rich Console
console = Console()
 
# --- Connection Management ---
def connect_device(console_port, timeout=5):
    """Establish telnet connection to a device"""
    try:
        tn = telnetlib.Telnet('localhost', console_port, timeout=timeout)
        time.sleep(0.2)
        tn.write(b'\x03')
        time.sleep(0.1)
        tn.read_very_eager()
        tn.write(b'enable\r\n')
        time.sleep(0.1)
        tn.read_very_eager()
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
 
class DiagnosticRunner:
    def __init__(self, gns3_url="http://localhost:3080", username="admin", password="qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS"):
        self.gns3_url = gns3_url.rstrip('/')
        self.api_base = f"{self.gns3_url}/v2"
        # Try auth, but we will handle failures gracefully
        self.auth = HTTPBasicAuth(username, password) if username else None
        self.nodes = {}
        self.connections = {} 
 
    @staticmethod
    def _get_eigrp_fix_commands(issue_type, issue_details):
        if issue_type in ['k-value mismatch', 'non-default k-values']:
            return ["router eigrp 1", "metric weights 0 1 0 1 0 0"]
        elif issue_type == 'passive interface':
            interface = issue_details.get('interface')
            return ["router eigrp 1", f"no passive-interface {interface}"]
        elif issue_type in ['stub configuration', 'stub mismatch']:
            return ["router eigrp 1", "no eigrp stub"]
        return []
 
    def connect(self):
        """Connect to GNS3 with better error handling"""
        console.print(f"[dim]Attempting connection to {self.api_base}...[/dim]")
 
        try:
            # 1. Try to get version (Quick check)
            try:
                response = requests.get(f"{self.api_base}/version", auth=self.auth, timeout=2)
            except requests.exceptions.ConnectionError:
                console.print(f"[bold red]Error:[/bold red] Could not reach GNS3 at {self.gns3_url}")
                console.print("[yellow]Hint:[/yellow] Is the GNS3 app running?")
                return False
 
            # Handle 401 Unauthorized by retrying without auth
            if response.status_code == 401:
                console.print("[yellow]Auth failed. Retrying without credentials...[/yellow]")
                self.auth = None
                response = requests.get(f"{self.api_base}/version", timeout=2)
 
            if response.status_code != 200:
                console.print(f"[bold red]API Error:[/bold red] Status Code {response.status_code}")
                return False
 
            version = response.json().get('version', 'unknown')
            console.print(f"[green]Connected to GNS3 v{version}[/green]")
 
            # 2. Get Projects
            response = requests.get(f"{self.api_base}/projects", auth=self.auth)
            projects = response.json()
 
            project_found = False
            for project in projects:
                if project['status'] == 'opened':
                    project_found = True
                    console.print(f"[dim]Found active project: {project['name']}[/dim]")
 
                    # 3. Get Nodes for the open project
                    response = requests.get(f"{self.api_base}/projects/{project['project_id']}/nodes", auth=self.auth)
                    nodes = response.json()
 
                    count = 0
                    for node in nodes:
                        if node['status'] == 'started':
                            self.nodes[node['name']] = node.get('console')
                            count += 1
 
                    if count == 0:
                        console.print("[yellow]Warning:[/yellow] Project is open, but no devices are started.")
                        console.print("[dim]Please start your devices in GNS3.[/dim]")
                        return False
 
                    console.print(f"[green]Found {count} running devices.[/green]")
                    return True
 
            if not project_found:
                console.print("[bold red]No open project found.[/bold red]")
                console.print("[yellow]Hint:[/yellow] Open a project in the GNS3 GUI first.")
                return False
 
        except Exception as e:
            console.print(f"[bold red]Unexpected Connection Error:[/bold red] {e}")
            return False
 
    def cleanup_all_connections(self):
        for tn in self.connections.values():
            close_device(tn)
        self.connections.clear()
 
    def run_diagnostics(self, device_names, check_interfaces=True, check_eigrp=True):
        detected_issues = {'interfaces': {}, 'eigrp': {}}
 
        console.print("\n[bold cyan]PHASE 1: DETECTING ISSUES[/bold cyan]")
 
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
 
            task = progress.add_task("[cyan]Scanning devices...", total=len(device_names))
 
            for device_name in device_names:
                progress.update(task, description=f"[cyan]Scanning {device_name}...")
 
                console_port = self.nodes.get(device_name)
                # No need to check if port exists here, we filter in main()
 
                tn = connect_device(console_port)
                if not tn:
                    console.print(f"[red]Failed to connect to {device_name}[/red]")
                    progress.advance(task)
                    continue
 
                self.connections[device_name] = tn
 
                try:
                    if check_interfaces:
                        probs, _ = troubleshoot_interfaces(device_name, tn, auto_prompt=False)
                        detected_issues['interfaces'][device_name] = probs
 
                    if check_eigrp:
                        probs, _ = troubleshoot_eigrp(device_name, tn, auto_prompt=False)
                        detected_issues['eigrp'][device_name] = probs
                except Exception as e:
                    console.print(f"[red]Error on {device_name}: {e}[/red]")
 
                progress.advance(task)
 
        return detected_issues
 
    def print_summary_table(self, detected_issues):
        table = Table(title="Diagnostic Results", show_header=True, header_style="bold magenta")
        table.add_column("Device", style="cyan")
        table.add_column("Category", style="yellow")
        table.add_column("Issue", style="white")
        table.add_column("Status", style="red")
 
        has_issues = False
 
        for device, problems in detected_issues['interfaces'].items():
            for p in problems:
                table.add_row(device, "Interface", p['interface'], "Admin Down")
                has_issues = True
 
        for device, problems in detected_issues['eigrp'].items():
            for p in problems:
                table.add_row(device, "EIGRP", p.get('line', 'N/A')[:30], p['type'])
                has_issues = True
 
        if has_issues:
            console.print(table)
        else:
            console.print("\n[bold green]:check_mark: No issues found. Network is healthy![/bold green]")
 
        return has_issues
 
    def apply_fixes(self, detected_issues, check_interfaces=True, check_eigrp=True):
        console.print("\n[bold cyan]PHASE 2: APPLYING FIXES[/bold cyan]")
        results = []
 
        if check_interfaces:
            for device, problems in detected_issues['interfaces'].items():
                if not problems: continue
                tn = self.connections.get(device)
                for problem in problems:
                    interface = problem['interface']
                    console.print(f"\n[yellow]Device:[/yellow] {device} | [yellow]Issue:[/yellow] {interface} is Down")
                    if Confirm.ask("Apply 'no shutdown'?"):
                        from interface_tree import fix_interface
                        if fix_interface(tn, interface):
                            console.print(f"[green]✔ Fixed {interface}[/green]")
                            results.append([device, "Interface", interface, "Fixed"])
                        else:
                            console.print(f"[red]✘ Failed to fix {interface}[/red]")
 
        if check_eigrp:
            for device, problems in detected_issues['eigrp'].items():
                if not problems: continue
                tn = self.connections.get(device)
                for issue in problems:
                    issue_type = issue['type']
                    console.print(f"\n[yellow]Device:[/yellow] {device} | [yellow]Issue:[/yellow] {issue_type}")
                    fix_commands = self._get_eigrp_fix_commands(issue_type, issue)
                    if not fix_commands:
                        console.print(f"[bold red]Manual intervention required[/bold red]")
                        continue
                    if Confirm.ask(f"Apply fix?"):
                        from eigrp_tree import apply_eigrp_fixes
                        if apply_eigrp_fixes(tn, fix_commands):
                            console.print(f"[green]✔ Fixed {issue_type}[/green]")
                            results.append([device, "EIGRP", issue_type, "Fixed"])
                        else:
                            console.print(f"[red]✘ Failed to fix {issue_type}[/red]")
        return results
 
def main():
    runner = DiagnosticRunner()
    atexit.register(runner.cleanup_all_connections)
 
    console.print("[bold blue]Network Diagnostic Tool[/bold blue]", justify="center")
 
    # 1. Connection Check
    if not runner.connect():
        sys.exit(1)
 
    # 2. Case-Insensitive Device Selection
    available_devices = list(runner.nodes.keys()) # e.g. ['R1', 'R2']
 
    # Create a map: {'r1': 'R1', 'r2': 'R2'}
    device_map = {name.lower(): name for name in available_devices}
 
    console.print(f"\nAvailable: [green]{', '.join(available_devices)}[/green]")
    user_input = console.input("Enter devices (e.g. 'r1, r2') or Press Enter for all: ").strip()
 
    final_target_list = []
 
    if not user_input:
        final_target_list = available_devices
    else:
        # Split input and clean whitespace
        requested_devices = [d.strip().lower() for d in user_input.split(',')]
 
        for req in requested_devices:
            if req in device_map:
                # Append the REAL name (e.g. 'R1') not the user input (e.g. 'r1')
                final_target_list.append(device_map[req])
            else:
                console.print(f"[yellow]Warning: '{req}' not found. Skipping.[/yellow]")
 
    if not final_target_list:
        console.print("[bold red]No valid devices selected. Exiting.[/bold red]")
        sys.exit(1)
 
    console.print(f"[dim]Running on: {', '.join(final_target_list)}[/dim]")
 
    # 3. Execution
    detected_issues = runner.run_diagnostics(final_target_list)
    has_issues = runner.print_summary_table(detected_issues)
 
    if has_issues and Confirm.ask("\nProceed to fix menu?"):
        runner.apply_fixes(detected_issues)
        console.print("\n[bold green]Done.[/bold green]")
 
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold red]Interrupted[/bold red]")
        sys.exit(0)
