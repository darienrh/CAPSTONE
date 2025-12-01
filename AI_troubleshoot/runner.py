#!/usr/bin/env python3
"""
Network Diagnostic Runner - Optimized with Persistent Connections
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
from interface_tree import troubleshoot_device as troubleshoot_interfaces
from eigrp_tree import troubleshoot_eigrp
from ospf_tree import troubleshoot_ospf


# Connection management functions
def connect_device(console_port, timeout=5):
    """Establish telnet connection to a device"""
    try:
        tn = telnetlib.Telnet('localhost', console_port, timeout=timeout)
        # Initial cleanup
        time.sleep(0.2)
        tn.write(b'\x03')  # Ctrl+C
        time.sleep(0.1)
        tn.read_very_eager()
        tn.write(b'enable\r\n')
        time.sleep(0.1)
        tn.read_very_eager()
        return tn
    except Exception as e:
        print(f"Error connecting to port {console_port}: {e}")
        return None


def close_device(tn):
    """Close telnet connection properly"""
    if tn:
        try:
            try:
                tn.write(b'\x03')
                time.sleep(0.1)
                tn.read_very_eager()
            except:
                pass

            try:
                tn.write(b'end\r\n')
                time.sleep(0.1)
                tn.read_very_eager()
            except:
                pass

            try:
                tn.get_socket().shutdown(socket.SHUT_RDWR)
            except:
                pass

            tn.close()
        except:
            pass


class DiagnosticRunner:

    def __init__(self, gns3_url="http://localhost:3080", username="admin",
                 password="qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS"):
        self.gns3_url = gns3_url.rstrip('/')
        self.api_base = f"{self.gns3_url}/v2"
        self.project_id = None
        self.nodes = {}
        self.auth = HTTPBasicAuth(username, password) if username else None
        self.connections = {}  # Track open connections

    def connect(self):
        """Connect to GNS3 and load project"""
        try:
            response = requests.get(f"{self.api_base}/version", auth=self.auth, timeout=5)
            if response.status_code != 200:
                print("Failed to connect to GNS3")
                return False

            version = response.json().get('version', 'unknown')
            print(f"Connected to GNS3 v{version}")

            response = requests.get(f"{self.api_base}/projects", auth=self.auth)
            projects = response.json()

            for project in projects:
                if project['status'] == 'opened':
                    self.project_id = project['project_id']
                    print(f"Using project: {project['name']}")

                    response = requests.get(f"{self.api_base}/projects/{self.project_id}/nodes", auth=self.auth)
                    nodes = response.json()

                    for node in nodes:
                        if node['status'] == 'started':
                            self.nodes[node['name']] = node.get('console')

                    print(f"Found {len(self.nodes)} running devices")
                    return True

            print("No opened project found")
            return False

        except Exception as e:
            print(f"Error: {e}")
            return False

    def list_devices(self):
        """List available devices"""
        print("\nAvailable devices:")
        for i, device in enumerate(sorted(self.nodes.keys()), 1):
            print(f"  {i}. {device}")

    def get_console_port(self, device_name):
        """Get console port for device"""
        return self.nodes.get(device_name)

    def cleanup_all_connections(self):
        """Close all open telnet connections"""
        for device_name, tn in self.connections.items():
            print(f"Closing connection to {device_name}...")
            close_device(tn)
        self.connections.clear()

    def run_diagnostics(self, device_names, check_interfaces=True, check_eigrp=True):
        """Run diagnostics on specified devices - detection phase only"""
        detected_issues = {
            'interfaces': {},
            'eigrp': {}
        }

        print("\n" + "=" * 60)
        print("PHASE 1: DETECTING ISSUES")
        print("=" * 60)

        for device_name in device_names:
            console_port = self.get_console_port(device_name)

            if not console_port:
                print(f"\nDevice {device_name} not found or not running")
                continue

            # Open ONE connection per device for entire diagnostic session
            print(f"\nConnecting to {device_name}...")
            tn = connect_device(console_port)

            if not tn:
                print(f"Failed to connect to {device_name}")
                continue

            # Store connection for later use and cleanup
            self.connections[device_name] = tn

            try:
                if check_interfaces:
                    problems, _ = troubleshoot_interfaces(device_name, tn, auto_prompt=False)
                    detected_issues['interfaces'][device_name] = problems

                if check_eigrp:
                    problems, _ = troubleshoot_eigrp(device_name, tn, auto_prompt=False)
                    detected_issues['eigrp'][device_name] = problems
            except Exception as e:
                print(f"Error diagnosing {device_name}: {e}")
                detected_issues['interfaces'][device_name] = []
                detected_issues['eigrp'][device_name] = []

        return detected_issues

    def apply_fixes(self, detected_issues, check_interfaces=True, check_eigrp=True):
        """Apply fixes for detected issues using existing connections"""
        results = {
            'interfaces': {},
            'eigrp': {}
        }

        print("\n" + "=" * 60)
        print("PHASE 2: APPLYING FIXES")
        print("=" * 60)

        # Fix interface issues
        if check_interfaces:
            for device_name, problems in detected_issues['interfaces'].items():
                if not problems:
                    continue

                tn = self.connections.get(device_name)
                if not tn:
                    print(f"\nNo connection to {device_name} - skipping")
                    continue

                fixed = []

                print(f"\n{device_name} - Interface Issues:")
                print("-" * 60)

                for problem in problems:
                    interface = problem['interface']
                    print(f"\nProblem: {interface} administratively down")

                    response = input("Apply fix? (Y/n): ").strip().lower()

                    if response == 'n':
                        print("Skipping")
                        continue

                    print(f"Applying no shutdown to {interface}...")

                    # Import here to avoid circular import
                    from interface_tree import fix_interface

                    if fix_interface(tn, interface):
                        print(f"Fixed: {interface}")
                        fixed.append(interface)
                    else:
                        print(f"Failed to fix {interface}")

                results['interfaces'][device_name] = fixed

        # Fix EIGRP issues
        if check_eigrp:
            for device_name, problems in detected_issues['eigrp'].items():
                if not problems:
                    continue

                tn = self.connections.get(device_name)
                if not tn:
                    print(f"\nNo connection to {device_name} - skipping")
                    continue

                fixed = []

                print(f"\n{device_name} - EIGRP Issues:")
                print("-" * 60)

                for issue in problems:
                    issue_type = issue['type']
                    print(f"\nProblem: {issue_type}")

                    if 'line' in issue:
                        print(f"  Details: {issue['line'][:80]}")

                    response = input("Apply fix? (Y/n): ").strip().lower()

                    if response == 'n':
                        print("Skipping")
                        continue

                    # Generate fix commands
                    fix_commands = []

                    if issue_type == 'k-value mismatch' or issue_type == 'non-default k-values':
                        print("Fix: Resetting K-values to default")
                        fix_commands = [
                            "router eigrp 1",
                            "metric weights 0 1 0 1 0 0"
                        ]

                    elif issue_type == 'passive interface':
                        interface = issue['interface']
                        print(f"Fix: Removing passive-interface {interface}")
                        fix_commands = [
                            "router eigrp 1",
                            f"no passive-interface {interface}"
                        ]

                    elif issue_type == 'stub configuration' or issue_type == 'stub mismatch':
                        print("Fix: Removing EIGRP stub")
                        fix_commands = [
                            "router eigrp 1",
                            "no eigrp stub"
                        ]

                    elif issue_type == 'as mismatch':
                        print("Note: AS mismatch - manual intervention required")
                        continue

                    elif issue_type == 'authentication mismatch':
                        print("Note: Auth mismatch - manual intervention required")
                        continue

                    if fix_commands:
                        from eigrp_tree import apply_eigrp_fixes

                        if apply_eigrp_fixes(tn, fix_commands):
                            print(f"Fixed: {issue_type}")
                            fixed.append(issue_type)
                        else:
                            print(f"Failed to fix {issue_type}")

                results['eigrp'][device_name] = fixed

        if check_ospf:
            for device_name, problems in detected_issues['ospf'].items():
                if not problems:
                    continue

                tn = self.connections.get(device_name)
                if not tn:
                    print(f"\nNo connection to {device_name} - skipping")
                    continue

                fixed = []

                print(f"\n{device_name} - OSPF Issues:")
                print("-" * 60)

                for issue in problems:
                    issue_type = issue['type']
                    print(f"\nProblem: {issue_type}")

                    if 'line' in issue:
                        print(f"  Details: {issue['line'][:80]}")

                    response = input("Apply fix? (Y/n): ").strip().lower()

                    if response == 'n':
                        print("Skipping")
                        continue

                    # Generate fix commands
                    fix_commands = []

                    if issue_type == 'timer mismatch' or issue_type == 'non-default ospf-timers':
                        interface = issue['interface']
                        print("Fix: Resetting timer-values to default (10 40 40)")
                        fix_commands = ["interface {interface}", "ip ospf hello-interval 10", "ip ospf dead-interval 40"]

                    elif issue_type == 'passive interface':
                        interface = issue['interface']
                        print(f"Fix: Removing passive-interface for {interface}")
                        fix_commands = ["router ospf 1", f"no passive-interface {interface}"]

                    elif issue_type == 'stub configuration' or issue_type == 'stub mismatch':
                        print("Fix: Removing OSPF stub configuration")
                        fix_commands = ["router ospf 1", "no ospf stub"]

                    elif issue_type == 'area mismatch':
                        print("Note: Area mismatch - manual intervention required")
                        continue

                    if fix_commands:
                        from ospf_tree import apply_ospf_fixes

                        if apply_ospf_fixes(tn, fix_commands):
                            print(f"Fixed: {issue_type}")
                            fixed.append(issue_type)
                    else:
                            print(f"Failed to fix {issue_type}")

                    results['ospf'][device_name] = fixed
        return results


def main():
    runner = DiagnosticRunner()

    # Register cleanup handler
    def cleanup():
        runner.cleanup_all_connections()

    atexit.register(cleanup)

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n\nInterrupted - cleaning up connections...")
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    print("\nNetwork Diagnostic Tool")
    print("=" * 60)

    if not runner.connect():
        sys.exit(1)

    runner.list_devices()

    print("\n" + "=" * 60)
    response = input("Run diagnostics? (Y/n): ").strip().lower()

    if response == 'n':
        print("Exiting")
        sys.exit(0)

    print("\nSelect diagnostic types to run:")
    print("  1. Interface diagnostics")
    print("  2. EIGRP diagnostics")
    print("  3. OSPF diagnostics")
    print("  4. All (default)")

    diag_choice = input("\nChoice (1/2/3/4): ").strip()

    check_interfaces = diag_choice in ('1', '4', '')
    check_eigrp = diag_choice in ('2', '4', '')
    check_ospf = diag_choice in ('3', '4' , '')

    print("\nEnter device names to diagnose (comma-separated)")
    print("Example: R1,R2  or  R1, R2, R3")
    print("Press Enter for all devices")

    device_input = input("\nDevices: ").strip()

    if device_input:
        device_names = [d.strip() for d in device_input.split(',')]
        invalid_devices = [d for d in device_names if d not in runner.nodes]
        if invalid_devices:
            print(f"\nInvalid devices: {', '.join(invalid_devices)}")
            sys.exit(1)
    else:
        device_names = list(runner.nodes.keys())

    print(f"\nRunning diagnostics on: {', '.join(device_names)}")
    print("=" * 60)

    try:
        # Phase 1: Detect all issues (opens connections)
        detected_issues = runner.run_diagnostics(device_names, check_interfaces, check_eigrp, check_ospf)

        # Show detection summary
        print("\n" + "=" * 60)
        print("DETECTION SUMMARY")
        print("=" * 60)

        total_issues = 0

        if check_interfaces:
            print("\nInterface Issues:")
            for device, problems in detected_issues['interfaces'].items():
                if problems:
                    print(f"  {device}: {len(problems)} issue(s)")
                    for p in problems:
                        print(f"    - {p['interface']}: {p['status']}")
                    total_issues += len(problems)
                else:
                    print(f"  {device}: No issues")

        if check_eigrp:
            print("\nEIGRP Issues:")
            for device, problems in detected_issues['eigrp'].items():
                if problems:
                    print(f"  {device}: {len(problems)} issue(s)")
                    for p in problems:
                        print(f"    - {p['type']}")
                    total_issues += len(problems)
                else:
                    print(f"  {device}: No issues")

        
        if check_ospf:
            print("\nOSPF Issues:")
            for device, problems in detected_issues['ospf'].items():
                if problems:
                    print(f"  {device}: {len(problems)} issue(s)")
                    for p in problems:
                        print(f"    - {p['type']}")
                    total_issues += len(problems)
                else:
                    print(f"  {device}: No issues")

        print("=" * 60)
        print(f"\nTotal issues detected: {total_issues}")

        if total_issues == 0:
            print("\nNo issues found - network is healthy!")
            return

        # Phase 2: Apply fixes (reuses existing connections)
        print("\n" + "=" * 60)
        response = input("Proceed with fixes? (Y/n): ").strip().lower()

        if response == 'n':
            print("Exiting without applying fixes")
            return

        results = runner.apply_fixes(detected_issues, check_interfaces, check_eigrp, check_ospf)

        # Final Summary
        print("\n" + "=" * 60)
        print("FINAL SUMMARY")
        print("=" * 60)

        if check_interfaces:
            print("\nInterface Fixes Applied:")
            for device, fixed in results['interfaces'].items():
                if fixed:
                    print(f"  {device}: {len(fixed)} interface(s) - {', '.join(fixed)}")
                else:
                    print(f"  {device}: No fixes applied")

        if check_eigrp:
            print("\nEIGRP Fixes Applied:")
            for device, fixed in results['eigrp'].items():
                if fixed:
                    print(f"  {device}: {len(fixed)} issue(s) - {', '.join(fixed)}")
                else:
                    print(f"  {device}: No fixes applied")

        if check_ospf:
            print("\nOSPF Fixes Applied:")
            for device, fixed in results['ospf'].items():
                if fixed:
                    print(f"  {device}: {len(fixed)} issue(s) - {', '.join(fixed)}")
                else:
                    print(f"  {device}: No fixes applied")

        print("=" * 60)
        print("\nDiagnostics complete")

    finally:
        # Always cleanup connections at the end
        print("\nClosing all device connections...")
        runner.cleanup_all_connections()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

        sys.exit(1)



