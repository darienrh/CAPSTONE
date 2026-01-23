#!/usr/bin/env python3
"""
REFACTORED runner.py - Simplified orchestrator using new modular architecture

This version imports and uses the new modules instead of having all logic inline.
"""

import warnings
import time
warnings.filterwarnings('ignore')

import requests
from requests.auth import HTTPBasicAuth
import sys
import atexit
from datetime import datetime
from rich.prompt import Confirm, Prompt

from core.config_manager import ConfigManager
from core.knowledge_base import KnowledgeBase
from detection.problem_detector import ProblemDetector
from resolution.fix_applier import FixApplier
from utils.reporter import Reporter
from utils.telnet_utils import connect_device, close_device, get_running_config


class DiagnosticRunner:
    """
    Simplified diagnostic runner that orchestrates the modular components
    """
    
    def __init__(self, gns3_url="http://localhost:3080", username="admin", 
                 password="qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS"):
        self.gns3_url = gns3_url.rstrip('/')
        self.api_base = f"{self.gns3_url}/v2"
        self.auth = HTTPBasicAuth(username, password) if username else None
        
        self.config_manager = ConfigManager()
        self.knowledge_base = KnowledgeBase(config_manager=self.config_manager)
        self.problem_detector = ProblemDetector(self.config_manager)
        self.reporter = Reporter()
        self.fix_applier = FixApplier(self.config_manager, self.reporter, self.knowledge_base)
        
        self.nodes = {}
        self.connections = {}
        self.run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def connect(self):
        """
        Connect to GNS3 and discover running devices
        
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.get(f"{self.api_base}/version", auth=self.auth, timeout=3)
            
            if response.status_code == 401:
                self.auth = None
                response = requests.get(f"{self.api_base}/version", timeout=3)
            
            if response.status_code != 200:
                self.reporter.print_error(f"API Error: Status Code {response.status_code}")
                return False
            
            # Get running project and nodes
            response = requests.get(f"{self.api_base}/projects", auth=self.auth, timeout=5)
            projects = response.json()
            
            for project in projects:
                if project['status'] == 'opened':
                    response = requests.get(
                        f"{self.api_base}/projects/{project['project_id']}/nodes",
                        auth=self.auth, timeout=5
                    )
                    nodes = response.json()
                    
                    for node in nodes:
                        if node['status'] == 'started' and not node['name'].lower().startswith('switch'):
                            self.nodes[node['name']] = node.get('console')
                    
                    if not self.nodes:
                        self.reporter.print_warning("No running routers found")
                        return False
                    
                    self.reporter.print_success(f"Found {len(self.nodes)} running router(s).")
                    return True
            
            self.reporter.print_error("No open project found.")
            return False
        
        except requests.exceptions.ConnectionError:
            self.reporter.print_error(f"Could not reach GNS3 at {self.gns3_url}")
            return False
        except Exception as e:
            self.reporter.print_error(f"Connection Error: {str(e)[:100]}")
            return False
    
    def connect_to_devices(self, device_names):
        """
        Establish telnet connections to devices
        
        Args:
            device_names: List of device names to connect to
        
        Returns:
            Dict mapping device names to telnet connections
        """
        for device_name in device_names:
            console_port = self.nodes.get(device_name)
            if not console_port:
                continue
            
            tn = connect_device(console_port)
            if tn:
                self.connections[device_name] = tn
        
        return self.connections
    
    def cleanup_all_connections(self):
        """Close all telnet connections"""
        for tn in self.connections.values():
            close_device(tn)
        self.connections.clear()
    
    def run_diagnostics(self, device_names):
        """
        Run diagnostics on specified devices
        
        Args:
            device_names: List of device names
        
        Returns:
            Dict of detected issues
        """
        self.reporter.print_phase_header("PHASE 1: DETECTING ISSUES")
        
        # Connect to devices if not already connected
        if not self.connections:
            self.connect_to_devices(device_names)
        
        # Use progress bar
        with self.reporter.create_progress_bar("Scanning devices...", len(device_names)) as progress:
            task = progress.add_task("[cyan]Scanning...", total=len(device_names))
            
            # Scan all devices in parallel
            detected_issues = self.problem_detector.scan_all_devices(
                self.connections,
                scan_options={
                    'check_interfaces': True,
                    'check_eigrp': True,
                    'check_ospf': True
                },
                parallel=True
            )
            
            progress.update(task, completed=len(device_names))
        
        return detected_issues
    
    def save_stable_configurations(self, device_names):
        """
        Save current configurations as stable baseline
        
        Args:
            device_names: List of device names
        
        Returns:
            True if successful
        """
        self.reporter.print_phase_header("SAVING STABLE CONFIGURATIONS")
        
        device_configs = {}
        
        with self.reporter.create_progress_bar("Saving configurations...", len(device_names)) as progress:
            task = progress.add_task("[cyan]Saving...", total=len(device_names))
            
            for device_name in device_names:
                console_port = self.nodes.get(device_name)
                if not console_port:
                    progress.advance(task)
                    continue
                
                tn = self.connections.get(device_name) or connect_device(console_port)
                if not tn:
                    progress.advance(task)
                    continue
                
                config = get_running_config(tn)
                if config:
                    device_configs[device_name] = config
                
                if device_name not in self.connections:
                    close_device(tn)
                
                progress.advance(task)
        
        if device_configs:
            saved_file = self.config_manager.save_baseline(device_configs, tag="stable")
            if saved_file:
                self.reporter.print_success(f"✓ Saved {len(device_configs)} stable configuration(s)")
                return True
        else:
            self.reporter.print_warning("No configurations were saved")
        
        return False
    
    def restore_stable_configurations(self, device_names=None):
        """
        Restore configurations from stable baseline asynchronously
        
        Args:
            device_names: List of device names or None for all
        
        Returns:
            True if successful
        """
        self.reporter.print_phase_header("RESTORING STABLE CONFIGURATIONS")
        
        # Load latest baseline config file content
        config_files = list(self.config_manager.config_dir.glob("config_stable*.txt"))
        if not config_files:
            self.reporter.print_error("No stable configuration file found!")
            return False
        
        config_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        latest_config = config_files[0]
        
        with open(latest_config, 'r') as f:
            content = f.read()
        
        # Parse device configs
        import re as regex_module
        devices = regex_module.split(r'DEVICE:\s+(\w+)', content)
        device_configs = {}
        
        for i in range(1, len(devices), 2):
            device_name = devices[i]
            device_config = devices[i + 1]
            device_configs[device_name] = device_config
        
        # Determine which devices to restore
        if device_names is None:
            devices_to_restore = list(device_configs.keys())
        else:
            devices_to_restore = [d for d in device_names if d in device_configs]
        
        if not devices_to_restore:
            self.reporter.print_error("No matching devices found in baseline!")
            return False
        
        self.reporter.print_info(f"Using baseline: {latest_config.name}")
        self.reporter.print_info(f"Will restore: {', '.join(devices_to_restore)}")
        
        if not Confirm.ask(f"Restore {len(devices_to_restore)} device(s)?"):
            return False
        
        # Process configurations asynchronously
        success_count = 0
        failed_devices = []
        
        # Function to restore a single device
        def restore_single_device(device_name, config):
            try:
                console_port = self.nodes.get(device_name)
                if not console_port:
                    return device_name, False, "No console port"
                
                tn = self.connections.get(device_name) or connect_device(console_port)
                if not tn:
                    return device_name, False, "Connection failed"
                
                # Clear line and reset
                tn.write(b'\x03\r\n')
                time.sleep(0.1)
                tn.read_very_eager()
                tn.write(b'end\r\n')
                time.sleep(0.1)
                tn.read_very_eager()
                
                # STEP 1: Remove existing routing protocol configurations
                tn.write(b'configure terminal\r\n')
                time.sleep(0.2)
                tn.read_very_eager()
                
                # Determine which protocols to clear based on device
                is_eigrp = device_name.upper() in ['R1', 'R2', 'R3']
                is_ospf = device_name.upper() in ['R4', 'R5', 'R6']
                
                if is_eigrp:
                    # Remove EIGRP configuration
                    tn.write(b'no router eigrp 1\r\n')
                    time.sleep(0.3)
                    tn.read_very_eager()
                
                if is_ospf:
                    # Remove OSPF configuration
                    tn.write(b'no router ospf 10\r\n')
                    time.sleep(0.3)
                    tn.read_very_eager()
                
                # STEP 2: Reset all interface configurations to defaults
                # Parse interfaces from config
                import re as regex_module
                interface_sections = regex_module.findall(
                    r'interface\s+(\S+)',
                    config,
                    regex_module.IGNORECASE
                )
                
                for intf in interface_sections:
                    # Reset interface to default
                    tn.write(f'default interface {intf}\r\n'.encode('ascii'))
                    time.sleep(0.2)
                    tn.read_very_eager()
                
                tn.write(b'end\r\n')
                time.sleep(0.2)
                tn.read_very_eager()
                
                # STEP 3: Parse interface shutdown states from stable config BEFORE applying
                # This ensures we know the exact desired state for each interface
                interface_states = {}  # {interface_name: should_be_shutdown}
                current_interface = None
                
                for line in config.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('!') or line.startswith('Building') or line.startswith('Current'):
                        continue
                    
                    if line.lower().startswith('interface '):
                        current_interface = line.split()[1] if len(line.split()) > 1 else None
                        if current_interface:
                            # Default: interface should be up (no shutdown)
                            interface_states[current_interface] = False
                    
                    elif current_interface and line.lower() == 'shutdown':
                        # Mark this interface as should be shutdown
                        interface_states[current_interface] = True
                    
                    elif line.lower().startswith(('router ', 'ip classless', 'line ', 'end', '!')):
                        # Exited interface context
                        current_interface = None
                
                # STEP 4: Apply baseline configuration (without shutdown commands)
                tn.write(b'configure terminal\r\n')
                time.sleep(0.2)
                tn.read_very_eager()
                
                for line in config.split('\n'):
                    line = line.strip()
                    
                    # Skip empty lines, comments, and banner lines
                    if not line or line.startswith('!') or line.startswith('Building') or line.startswith('Current'):
                        continue
                    
                    # Skip problematic lines that should not be changed
                    skip_keywords = ['version', 'hostname', 'service ', 'enable ', 'line ', 'boot-']
                    if any(skip in line.lower() for skip in skip_keywords):
                        continue
                    
                    # Skip shutdown commands - we'll apply them separately at the end
                    if line.lower() == 'shutdown':
                        continue
                    
                    # Apply the command
                    tn.write(line.encode('ascii') + b'\r\n')
                    time.sleep(0.05)
                    tn.read_very_eager()
                
                # STEP 5: Explicitly set shutdown state for each interface based on stable config
                # First, ensure we're in config mode
                tn.write(b'end\r\n')
                time.sleep(0.2)
                tn.read_very_eager()
                
                tn.write(b'configure terminal\r\n')
                time.sleep(0.2)
                tn.read_very_eager()
                
                # Now apply interface states
                for intf, should_shutdown in interface_states.items():
                    tn.write(f'interface {intf}\r\n'.encode('ascii'))
                    time.sleep(0.1)
                    tn.read_very_eager()
                    
                    if should_shutdown:
                        tn.write(b'shutdown\r\n')
                    else:
                        tn.write(b'no shutdown\r\n')
                    
                    time.sleep(0.1)
                    tn.read_very_eager()
                
                # STEP 6: Save configuration
                tn.write(b'end\r\n')
                time.sleep(0.3)
                tn.read_very_eager()
                
                tn.write(b'write memory\r\n')
                time.sleep(1)
                tn.read_very_eager()
                
                # Disconnect if not in main connections dict
                if device_name not in self.connections:
                    close_device(tn)
                
                return device_name, True, "Success"
                
            except Exception as e:
                # Close connection on error
                try:
                    if 'tn' in locals():
                        close_device(tn)
                except Exception:
                    pass
                return device_name, False, str(e)
        
        # Process devices asynchronously
        import concurrent.futures
        from concurrent.futures import ThreadPoolExecutor
        
        self.reporter.print_info(f"Starting parallel restore of {len(devices_to_restore)} devices...")
        
        # Create progress bar
        with self.reporter.create_progress_bar("Restoring...", len(devices_to_restore)) as progress:
            task = progress.add_task("[cyan]Restoring...", total=len(devices_to_restore))
            
            # Use ThreadPoolExecutor for parallel execution
            max_workers = min(8, len(devices_to_restore))  # Limit concurrent connections
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all restoration tasks
                future_to_device = {}
                for device_name in devices_to_restore:
                    config = device_configs.get(device_name, '')
                    future = executor.submit(restore_single_device, device_name, config)
                    future_to_device[future] = device_name
                
                # Process results as they complete
                for future in concurrent.futures.as_completed(future_to_device):
                    device_name = future_to_device[future]
                    try:
                        device, success, message = future.result(timeout=30)
                        
                        if success:
                            progress.update(task, advance=1, 
                                        description=f"[green]✓ {device_name}")
                            success_count += 1
                        else:
                            progress.update(task, advance=1,
                                        description=f"[red]✗ {device_name}")
                            failed_devices.append((device_name, message))
                            
                    except concurrent.futures.TimeoutError:
                        progress.update(task, advance=1,
                                    description=f"[red]⏰ {device_name} (timeout)")
                        failed_devices.append((device_name, "Timeout"))
                    except Exception as e:
                        progress.update(task, advance=1,
                                    description=f"[red]✗ {device_name} (error)")
                        failed_devices.append((device_name, str(e)))
        
        # Report results
        if success_count == len(devices_to_restore):
            self.reporter.print_success(f"✓ All {success_count} devices restored successfully!")
        elif success_count > 0:
            self.reporter.print_warning(f"✓ {success_count}/{len(devices_to_restore)} devices restored")
            if failed_devices:
                self.reporter.print_error("Failed devices:")
                for device, error in failed_devices:
                    self.reporter.print_error(f"  {device}: {error[:100]}")
        else:
            self.reporter.print_error("✗ No devices were restored successfully")
        
        return success_count > 0
    
    def apply_fixes(self, detected_issues):
        """
        Apply fixes for detected issues
        
        Args:
            detected_issues: Dict of detected issues
        """
        self.reporter.print_phase_header("PHASE 2: APPLYING FIXES")
        
        # Ask for fix mode
        fix_mode = Prompt.ask(
            "\n[cyan]Apply fixes:[/cyan]",
            choices=["all", "one-by-one"],
            default="one-by-one"
        )
        
        auto_approve_all = (fix_mode == "all")
        
        # Apply fixes using FixApplier
        fix_results = self.fix_applier.apply_all_fixes(
            detected_issues,
            self.connections,
            auto_approve_all
        )
        
        return fix_results
    
    def print_completion_summary(self):
        fix_results = self.fix_applier.get_fix_results()
        self.reporter.print_fix_completion_summary(fix_results)
        self.reporter.save_run_history(fix_results, self.run_timestamp)
        
        # Enhanced learning: Log detailed problem-solution pairs
        for result in fix_results:
            problem = result.get('problem', {})
            problem['device'] = result['device']
            
            solution = {
                'commands': result['commands'],
                'verification': result['verification'],
                'rule_id': problem.get('rule_id') if 'rule_id' in problem else None
            }
            
            success = result.get('success', True)
            self.knowledge_base.add_problem_solution_pair(problem, solution, success=success)
            
            if success:
                print(f"[Learning] Logged successful fix for {problem.get('type', 'unknown')} on {result['device']}")
            else:
                print(f"[Learning] Logged failed fix for {problem.get('type', 'unknown')} on {result['device']}")
    
    def show_kb_statistics(self):
        self.reporter.print_phase_header("KNOWLEDGE BASE STATISTICS")
        self.knowledge_base.print_statistics()


def main():
    runner = DiagnosticRunner()
    atexit.register(runner.cleanup_all_connections)
    
    runner.reporter.print_info("Network Diagnostic Tool")
    
    stats = runner.knowledge_base.get_statistics()
    runner.reporter.print_info(
        f"Knowledge Base: {stats['total_rules']} rules, "
        f"{stats['total_problems_logged']} problems logged, "
        f"{stats['overall_success_rate']}% success rate"
    )
    
    if not runner.connect():
        sys.exit(1)
    
    available_devices = [name for name in runner.nodes.keys() 
                        if not name.lower().startswith('switch')]
    device_map = {name.lower(): name for name in available_devices}
    
    runner.reporter.print_info(f"\nAvailable: {', '.join(available_devices)}")
    user_input = input("Enter devices (e.g. 'r1, r2') or Press Enter for all: ").strip()
    
    final_target_list = []
    if not user_input:
        final_target_list = available_devices
    else:
        for req in [d.strip().lower() for d in user_input.split(',')]:
            if req in device_map:
                final_target_list.append(device_map[req])
    
    if not final_target_list:
        runner.reporter.print_error("No valid devices selected. Exiting.")
        sys.exit(1)
    
    detected_issues = runner.run_diagnostics(final_target_list)
    has_issues = runner.reporter.print_scan_summary(detected_issues)
    
    if has_issues and Confirm.ask("\nProceed to fix menu?"):
        runner.apply_fixes(detected_issues)
        runner.print_completion_summary()
    else:
        if not has_issues:
            runner.reporter.save_run_history([], runner.run_timestamp)
    
    print("\n" + "=" * 60)
    
    if Confirm.ask("View Knowledge Base statistics?", default=False):
        runner.show_kb_statistics()
    
    print("\n" + "=" * 60)
    
    if Confirm.ask("Revert configs to last stable version?", default=False):
        revert_mode = Prompt.ask(
            "[cyan]Revert:[/cyan]",
            choices=["all", "select"],
            default="all"
        )
        
        if revert_mode == "all":
            runner.restore_stable_configurations(final_target_list)
        else:
            device_input = input("Enter devices to revert (e.g. 'R1, R2, R4'): ").strip()
            if device_input:
                device_map = {name.lower(): name for name in final_target_list}
                revert_devices = []
                for req in [d.strip().lower() for d in device_input.split(',')]:
                    if req in device_map:
                        revert_devices.append(device_map[req])
                
                if revert_devices:
                    runner.restore_stable_configurations(revert_devices)
    
    print("\n" + "=" * 60)
    if Confirm.ask("Save stable configurations of all routers now?"):
        runner.save_stable_configurations(final_target_list)
    
    runner.reporter.print_success("\nScript completed successfully!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[bold red]Interrupted[/bold red]")
        sys.exit(0)