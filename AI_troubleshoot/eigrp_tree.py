#!/usr/bin/env python3
"""
EIGRP troubleshooting decision tree - Uses connections managed by runner
"""

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


def enable_eigrp_debug(tn):
    """Enable EIGRP packet debugging using existing connection"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'debug eigrp packets\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except Exception as e:
        print(f"Error enabling debug: {e}")
        return False


def disable_debug(tn):
    """Disable all debugging using existing connection"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'no debug all\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except Exception as e:
        print(f"Error disabling debug: {e}")
        return False


def gather_eigrp_debug(tn, wait_time=5):
    """Gather EIGRP debug output using existing connection"""
    try:
        print(f"Collecting debug output for {wait_time} seconds...")
        time.sleep(wait_time)

        tn.write(b'show logging\r\n')
        time.sleep(1)

        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception as e:
        print(f"Error gathering debug: {e}")
        return None


def get_eigrp_neighbors(tn):
    """Get EIGRP neighbor information using existing connection"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip eigrp neighbors\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception as e:
        print(f"Error getting neighbors: {e}")
        return None


def get_eigrp_config(tn):
    """Get EIGRP running configuration using existing connection"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'show running-config | begin router eigrp\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception as e:
        print(f"Error getting EIGRP config: {e}")
        return None


def get_interface_timers(tn, interface):
    """Get EIGRP timers for an interface using existing connection"""
    try:
        clear_line_and_reset(tn)
        cmd = f'show ip eigrp interfaces detail {interface}\r\n'
        tn.write(cmd.encode('ascii'))
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception as e:
        print(f"Error getting interface timers: {e}")
        return None


def parse_eigrp_debug(debug_output):
    """Parse EIGRP debug output for common mismatches"""
    mismatches = []
    lines = debug_output.split('\n')

    for line in lines:
        line_lower = line.lower()

        if "k-value mismatch" in line_lower or "k value mismatch" in line_lower:
            mismatches.append({'type': 'k-value mismatch', 'line': line.strip()})

        if "not on common subnet" in line_lower:
            interface = None
            match = re.search(r'(FastEthernet|GigabitEthernet|Ethernet)[\d/]+', line)
            if match:
                interface = match.group(0)
            mismatches.append({'type': 'wrong subnet', 'interface': interface, 'line': line.strip()})

        if "authentication" in line_lower and ("fail" in line_lower or "mismatch" in line_lower):
            mismatches.append({'type': 'authentication mismatch', 'line': line.strip()})

        if "as mismatch" in line_lower or "autonomous system" in line_lower:
            mismatches.append({'type': 'as mismatch', 'line': line.strip()})

        if "peer terminating" in line_lower and "stub" in line_lower:
            mismatches.append({'type': 'stub mismatch', 'line': line.strip()})

        if "stub configuration" in line_lower or "stuck in active" in line_lower:
            mismatches.append({'type': 'stub mismatch', 'line': line.strip()})

    return mismatches


def check_passive_interfaces(tn):
    """Check for passive EIGRP interfaces"""
    config = get_eigrp_config(tn)
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
    """Check for EIGRP stub configuration"""
    config = get_eigrp_config(tn)
    if not config:
        return None

    for line in config.split('\n'):
        if 'eigrp stub' in line.lower():
            return {'type': 'stub configuration', 'line': line.strip()}
    return None


def check_metric_weights(tn):
    """Check EIGRP K-values"""
    config = get_eigrp_config(tn)
    if not config:
        return None

    for line in config.split('\n'):
        if 'metric weights' in line.lower():
            match = re.search(r'metric weights\s+(\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+)', line, re.IGNORECASE)
            if match:
                k_values = match.group(1)
                if k_values != '0 1 0 1 0 0':
                    return {'type': 'non-default k-values', 'values': k_values, 'line': line.strip()}
    return None


def apply_eigrp_fixes(tn, fixes):
    """Apply EIGRP configuration fixes using existing connection"""
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


def troubleshoot_eigrp(device_name, tn, auto_prompt=True):
    """
    Run EIGRP troubleshooting on a device using provided connection

    Args:
        device_name: Name of the device
        tn: Open telnetlib.Telnet connection (managed by runner)
        auto_prompt: If True, prompt user for fixes. If False, just detect issues.

    Returns:
        (all_issues, fixed_issues): Tuple of detected issues and fixed issues
    """
    print(f"\nDiagnosing EIGRP on {device_name}...")
    print("-" * 60)

    all_issues = []

    print("Checking EIGRP configuration...")

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
    k_values = check_metric_weights(tn)
    if k_values:
        all_issues.append(k_values)
        print(f"  Found: Non-default K-values ({k_values['values']})")

    # Check if EIGRP neighbors exist
    neighbor_output = get_eigrp_neighbors(tn)
    if not neighbor_output:
        print("Failed to get EIGRP neighbor information")
        return [], []

    # Check if there are any neighbors
    neighbor_lines = [l for l in neighbor_output.split('\n')
                     if l.strip() and not l.startswith('H') and 'Address' not in l]
    neighbor_count = len([l for l in neighbor_lines if any(c.isdigit() for c in l)])

    if neighbor_count > 0:
        print(f"Found {neighbor_count} EIGRP neighbor(s)")
    else:
        print("No EIGRP neighbors found - investigating with debug...")

        print("\nEnabling EIGRP debugging...")
        if not enable_eigrp_debug(tn):
            print("Failed to enable debugging")
            return [], []

        debug_output = gather_eigrp_debug(tn, wait_time=5)

        print("Disabling debugging...")
        disable_debug(tn)

        if debug_output:
            print("Parsing debug output...")
            debug_issues = parse_eigrp_debug(debug_output)
            all_issues.extend(debug_issues)

    if not all_issues:
        print("No EIGRP issues detected")
        return [], []

    print(f"Found {len(all_issues)} EIGRP problem(s):")
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

        if issue_type == 'k-value mismatch' or issue_type == 'non-default k-values':
            print("Fix: Resetting K-values to default (0 1 0 1 0 0)")
            fix_commands = ["router eigrp 1", "metric weights 0 1 0 1 0 0"]

        elif issue_type == 'passive interface':
            interface = issue['interface']
            print(f"Fix: Removing passive-interface for {interface}")
            fix_commands = ["router eigrp 1", f"no passive-interface {interface}"]

        elif issue_type == 'stub configuration' or issue_type == 'stub mismatch':
            print("Fix: Removing EIGRP stub configuration")
            fix_commands = ["router eigrp 1", "no eigrp stub"]

        elif issue_type == 'as mismatch':
            print("Note: AS number mismatch - manual intervention required")
            continue

        elif issue_type == 'authentication mismatch':
            print("Note: Authentication mismatch - manual key configuration required")
            continue

        if fix_commands:
            print(f"Applying fixes to {device_name}...")
            if apply_eigrp_fixes(tn, fix_commands):
                print("Fixes applied successfully")
                fixed_issues.append(issue_type)
            else:
                print("Failed to apply fixes")

    return all_issues, fixed_issues