#!/usr/bin/env python3
"""
REFACTORED runner.py - Simplified orchestrator using new modular architecture

This version imports and uses the new modules instead of having all logic inline.
"""

import warnings
warnings.filterwarnings('ignore')

import requests
from requests.auth import HTTPBasicAuth
import sys
import atexit
from datetime import datetime
from rich.prompt import Confirm, Prompt

# Import new modules
from core.config_manager import ConfigManager
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
        """Initialize runner with new modular components"""
        self.gns3_url = gns3_url.rstrip('/')
        self.api_base = f"{self.gns3_url}/v2"
        self.auth = HTTPBasicAuth(username, password) if username else None
        
        # Initialize modular components
        self.config_manager = ConfigManager()
        self.problem_detector = ProblemDetector(self.config_manager)
        self.reporter = Reporter()
        self.fix_applier = FixApplier(self.config_manager, self.reporter)
        
        # Device management
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
        Restore configurations from stable baseline
        
        Args:
            device_names: List of devices to restore (None = all)
        
        Returns:
            True if successful
        """
        self.reporter.print_phase_header("RESTORING STABLE CONFIGURATIONS")
        
        # Load latest baseline
        baseline = self.config_manager.load_latest_baseline()
        
        if not baseline:
            self.reporter.print_error("No stable configuration file found!")
            return False
        
        # Determine which devices to restore
        if device_names is None:
            devices_to_restore = list(baseline.keys())
        else:
            devices_to_restore = [d for d in device_names if d in baseline]
        
        if not devices_to_restore:
            self.reporter.print_error("No matching devices found in baseline!")
            return False
        
        self.reporter.print_info(f"Will restore: {', '.join(devices_to_restore)}")
        
        if not Confirm.ask(f"Restore {len(devices_to_restore)} device(s)?"):
            return False
        
        # TODO: Implement actual config restoration logic
        self.reporter.print_warning("Config restoration not yet fully implemented")
        
        return False
    
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
        """Print final summary"""
        fix_results = self.fix_applier.get_fix_results()
        self.reporter.print_fix_completion_summary(fix_results)
        self.reporter.save_run_history(fix_results, self.run_timestamp)


def main():
    """Main entry point"""
    runner = DiagnosticRunner()
    atexit.register(runner.cleanup_all_connections)
    
    runner.reporter.print_info("Network Diagnostic Tool")
    
    # Connect to GNS3
    if not runner.connect():
        sys.exit(1)
    
    # Get device list
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
    
    # Run diagnostics
    detected_issues = runner.run_diagnostics(final_target_list)
    has_issues = runner.reporter.print_scan_summary(detected_issues)
    
    # Apply fixes if issues found
    if has_issues and Confirm.ask("\nProceed to fix menu?"):
        runner.apply_fixes(detected_issues)
        runner.print_completion_summary()
    else:
        if not has_issues:
            runner.reporter.save_run_history([], runner.run_timestamp)
    
    print("\n" + "=" * 60)
    
    # Baseline management menu
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