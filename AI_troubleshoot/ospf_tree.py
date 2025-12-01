#!/usr/bin/env python3
import warnings
warnings.filterwarnings('ignore')

import time
import re

def clear_line_and_reset(tn):
    """Clear any partial commands and return to privileged exec mode"""
    tn.write(b'\x03')
    time.sleep(0.1)
    tn.read_very_eager()

    tn.write(b'end\r\n')
    time.sleep(0.1)
    tn.read_very_eager()

    tn.write(b'enable\r\n')
    time.sleep(0.1)
    tn.read_very_eager()

    tn.write(b'\r\n')
    time.sleep(0.1)
    tn.read_very_eager()

def enable_ospf_debug(tn):
    try:
        clear_line_and_reset(tn)
        tn.write(b'debug ip ospf\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except Exception as e:
        print(f"Error enabling ospf debug: {e}")
        return False

def disable_debug(tn):
    try:
        clear_line_and_reset(tn)
        tn.write(b'no debug all\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except Exception as e:
        print(f"Error disabling debug: {e}")
        return False

def gather_ospf_debug(tn, watinig_time=5):
    waiting_time = time.sleep(10)
    try:
        print(f"Collecting ospf debugs for {waiting_time}")
        time.sleep(waiting_time)

        tn.write(b"show logging \r\n")
        time.sleep(1)

        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception as e:
        print("Error gather debug: {e}")
        return None

def get_ospf_neighbors(tn):
    """Get OSPF neighbor information using existing connection"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip ospf neighbors\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception as e:
        print(f"Error getting neighbors: {e}")
        return None

def get_ospf_config(tn):
    """Get OSPF running configuration using existing connection"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'show running-config | begin router ospf\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception as e:
        print(f"Error getting OSPF config: {e}")
        return None
    
def get_interface_timers(tn, interface):
    """Get OSPF timers for an interface using existing connection"""
    try:
        clear_line_and_reset(tn)
        cmd = f'show ip ospf interfaces {interface}\r\n'
        tn.write(cmd.encode('ascii'))
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception as e:
        print(f"Error getting interface timers: {e}")
        return None

def check_passive_interfaces(tn):
    """Check for passive OSPF interfaces"""
    config = get_ospf_config(tn)
    if not config:
        return []

    passive_interfaces = []
    for line in config.split('\n'):
        if 'passive-interface' in line.lower():
            match = re.search(r'passive-interface\s+(\S+)', line, re.IGNORECASE)
            if match:
                interface = match.group(1)
                passive_interfaces.append({
                    'type': 'passive interface',
                    'interface': interface,
                    'line': line.strip()
                })
    return passive_interfaces


def check_stub_config(tn):
    """Check for OSPF stub configuration"""
    config = get_ospf_config(tn)
    if not config:
        return None

    for line in config.split('\n'):
        if 'ospf stub' in line.lower():
            return {'type': 'stub configuration', 'line': line.strip()}
    return None


def check_values(tn):
    """Check OSPF values"""
    config = get_ospf_config(tn)
    if not config:
        return None

    for line in config.split('\n'):
        if 'timer intervals' in line.lower():
            match = re.search(r"Hello\s+(\d+),\s+Dead\s+(\d+),\s+Wait\s+(\d+)", line, re.IGNORECASE)
            if match:
                current_timers = f"{match.group(1)} {match.group(2)} {match.group(3)}"
                if current_timers != '10 40 40':
                    return {'type': 'non-default ospf-timers', 'values': current_timers, 'line': line.strip()}
    return None


def parse_ospf_debug(debug_output):
    # Example parse for hello packet mismatch messages
    mismatches = []
    lines = debug_output.splitlines()
    for line in lines:
        lines_lower = line.lower()
        if "Hello interval mismatch" in lines_lower or "Dead interval mismatch" in lines_lower:
            mismatches.append({'type': 'timer mismatch', 'line': line.strip()})
        if "OSPF detected duplicate router-id" in lines_lower:
            mismatches.append({'type': 'duplicate_ids', 'line': line.strip()})
        if "area mismatch" in lines_lower or "Init" in lines_lower:
            mismatches.append({'type': 'area mismatch', 'line': line.strip()})
        if "stub configuration" in lines_lower or "stuck in active" in lines_lower:
            mismatches.append({'type': 'stub mismatch', 'line': line.strip()})
    return mismatches

def apply_ospf_fixes(tn, fixes):
    """Apply OSPF configuration fixes using existing connection"""
    try:
        clear_line_and_reset(tn)

        tn.write(b'configure terminal\r\n')
        time.sleep(0.3)
        tn.read_very_eager()

        for cmd in fixes:
            print(f"  -> {cmd}")
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(0.3)
            tn.read_very_eager()

        tn.write(b'end\r\n')
        time.sleep(0.3)
        tn.read_very_eager()

        tn.write(b'write memory\r\n')
        time.sleep(1)
        tn.read_very_eager()

        return True
    except Exception as e:
        print(f"Error applying fixes: {e}")
        return False


def troubleshoot_ospf(device_name, tn, auto_prompt=True):
    """
    Run OSPF troubleshooting on a device using provided connection

    Args:
        device_name: Name of the device
        tn: Open telnetlib.Telnet connection (managed by runner)
        auto_prompt: If True, prompt user for fixes. If False, just detect issues.

    Returns:
        (all_issues, fixed_issues): Tuple of detected issues and fixed issues
    """
    print(f"\nDiagnosing OSPF on {device_name}...")
    print("-" * 60)

    all_issues = []

    print("Checking OSPF configuration...")

    # Check for passive interfaces
    passive_intfs = check_passive_interfaces(tn)
    if passive_intfs:
        all_issues.extend(passive_intfs)
        for pintf in passive_intfs:
            print(f"  Found: Passive interface {pintf['interface']}")

    # Check for stub configuration
    stub_config = check_stub_config(tn)
    if stub_config:
        all_issues.append(stub_config)
        print(f"  Found: {stub_config['line']}")

    # Check for non-default K-values
    timer_values = check_values(tn)
    if timer_values:
        all_issues.append(timer_values)
        print(f"  Found: Non-default timer-values ({timer_values['values']})")

    # Check if OSPF neighbors exist
    neighbor_output = get_ospf_neighbors(tn)
    if not neighbor_output:
        print("Failed to get OSPF neighbor information")
        return [], []

    # Check if there are any neighbors
    neighbor_lines = [l for l in neighbor_output.split('\n')
                     if l.strip() and not l.startswith('H') and 'Address' not in l]
    neighbor_count = len([l for l in neighbor_lines if any(c.isdigit() for c in l)])

    if neighbor_count > 0:
        print(f"Found {neighbor_count} OSPF neighbor(s)")
    else:
        print("No OSPF neighbors found - investigating with debug...")

        print("\nEnabling OSPF debugging...")
        if not enable_ospf_debug(tn):
            print("Failed to enable debugging")
            return [], []

        debug_output = gather_ospf_debug(tn, wait_time=5)

        print("Disabling debugging...")
        disable_debug(tn)

        if debug_output:
            print("Parsing debug output...")
            debug_issues = parse_ospf_debug(debug_output)
            all_issues.extend(debug_issues)

    if not all_issues:
        print("No OSPF issues detected")
        return [], []

    print(f"Found {len(all_issues)} OSPF problem(s):")
    for issue in all_issues:
        print(f"  - {issue['type']}")

    if not auto_prompt:
        return all_issues, []

    # Interactive fixing
    fixed_issues = []

    for issue in all_issues:
        issue_type = issue['type']
        print(f"\nProblem: {device_name} - {issue_type}")

        if 'line' in issue:
            print(f"  Details: {issue['line'][:80]}")

        response = input("Apply fixes? (Y/n): ").strip().lower()

        if response == 'n':
            print("Skipping fix")
            continue

        fix_commands = []

        if issue_type == 'timer mismatch' or issue_type == 'non-default ospf-timers':
            interface = issue['interface']
            print("Fix: Resetting timer-values to default (10 40 40)")
            fix_commands = ["interface {interface}", "ip ospf hello-interval 10", "ip ospf dead-interval 40"]

        elif issue_type == 'passive interface':
            interface = issue['interface']
            print(f"Fix: Removing passive-interface for {interface}")
            fix_commands = ["router ospf 10", f"no passive-interface {interface}"]

        elif issue_type == 'stub configuration' or issue_type == 'stub mismatch':
            print("Fix: Removing OSPF stub configuration")
            fix_commands = ["router ospf 10", "no ospf stub"]

        elif issue_type == 'area mismatch':
            print("Note: Area mismatch - manual intervention required")
            continue

        if fix_commands:
            print(f"Applying fixes to {device_name}...")
            if apply_ospf_fixes(tn, fix_commands):
                print("Fixes applied successfully")
                fixed_issues.append(issue_type)
            else:
                print("Failed to apply fixes")

    return all_issues, fixed_issues
