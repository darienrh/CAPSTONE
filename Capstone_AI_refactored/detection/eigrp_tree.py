#!/usr/bin/env python3
"""EIGRP troubleshooting detection and fix generation module."""

import warnings
warnings.filterwarnings('ignore')

import time
import re
from typing import List, Dict, Optional, Tuple

try:
    from core.config_manager import ConfigManager
except ImportError:
    from core.config_manager import ConfigManager


def clear_line_and_reset(tn):
    """Clear any partial commands and return to privileged exec mode."""
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
    """Enable EIGRP packet debugging."""
    try:
        clear_line_and_reset(tn)
        tn.write(b'debug eigrp packets\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except Exception:
        return False


def disable_debug(tn):
    """Disable all debugging."""
    try:
        clear_line_and_reset(tn)
        tn.write(b'no debug all\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except Exception:
        return False


def gather_eigrp_debug(tn, wait_time=5):
    """Gather EIGRP debug output."""
    try:
        time.sleep(wait_time)
        tn.write(b'show logging\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None


def get_eigrp_neighbors(tn):
    """Get EIGRP neighbor information."""
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip eigrp neighbors\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None


def get_eigrp_config(tn):
    """Get EIGRP running configuration."""
    try:
        clear_line_and_reset(tn)
        tn.write(b'terminal length 0\r\n')
        tn.write(b'show running-config\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None


def get_eigrp_interfaces(tn):
    """Get EIGRP interface information."""
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip eigrp interfaces\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None


def check_eigrp_interface_timers(tn, device_name, config_manager=None):
    """Check EIGRP hello and hold timers on all interfaces."""
    issues = []
    
    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    baseline_interfaces = baseline.get('interfaces', {})
    as_number = config_manager.get_eigrp_as_number(device_name)
    
    for intf_name, intf_info in baseline_interfaces.items():
        if not intf_info.get('ip_address'):
            continue
        
        try:
            clear_line_and_reset(tn)
            cmd = f'show ip eigrp interfaces detail {intf_name}\r\n'
            tn.write(cmd.encode('ascii'))
            time.sleep(1)
            output = tn.read_very_eager().decode('ascii', errors='ignore')
            
            if 'not found' in output.lower() or 'not running' in output.lower():
                continue
            
            hello_match = re.search(r'Hello[- ]interval[- ]is\s+(\d+)', output, re.IGNORECASE)
            hold_match = re.search(r'Hold[- ]time[- ]is\s+(\d+)', output, re.IGNORECASE)
            
            expected_hello = intf_info.get('eigrp_hello', 5)
            expected_hold = intf_info.get('eigrp_hold', 15)
            
            has_mismatch = False
            current_hello = None
            current_hold = None
            
            if hello_match:
                current_hello = int(hello_match.group(1))
                if current_hello != expected_hello:
                    has_mismatch = True
            
            if hold_match:
                current_hold = int(hold_match.group(1))
                if current_hold != expected_hold:
                    has_mismatch = True
            
            if has_mismatch:
                issues.append({
                    'type': 'eigrp timer mismatch',
                    'category': 'eigrp',
                    'interface': intf_name,
                    'current_hello': current_hello if current_hello else expected_hello,
                    'current_hold': current_hold if current_hold else expected_hold,
                    'expected_hello': expected_hello,
                    'expected_hold': expected_hold,
                    'as_number': as_number,
                    'line': f'{intf_name}: Hello {current_hello}s/{expected_hello}s, Hold {current_hold}s/{expected_hold}s'
                })
                
        except Exception as e:
            print(f"[DEBUG] Error checking timers on {intf_name}: {e}")
            continue
    
    return issues


def check_stub_configuration(tn, device_name, config_manager=None):
    """Check EIGRP stub configuration against baseline."""
    config = get_eigrp_config(tn)
    if not config:
        return None
    
    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    expected_stub = baseline.get('eigrp', {}).get('is_stub', False)
    current_stub = bool(re.search(r'eigrp stub', config, re.IGNORECASE))
    
    if current_stub and not expected_stub:
        return {
            'type': 'stub configuration',
            'category': 'eigrp',
            'should_be_stub': False,
            'line': 'eigrp stub (should not be configured)'
        }
    elif not current_stub and expected_stub:
        return {
            'type': 'missing stub configuration',
            'category': 'eigrp',
            'should_be_stub': True,
            'line': 'eigrp stub missing (should be configured)'
        }
    
    return None


def check_as_mismatch(tn, device_name, config_manager=None):
    """Check for EIGRP AS number mismatch."""
    config = get_eigrp_config(tn)
    if not config:
        return None
    
    if config_manager is None:
        config_manager = ConfigManager()
    
    expected_as = config_manager.get_eigrp_as_number(device_name)
    
    as_match = re.search(r'router eigrp\s+(\d+)', config, re.IGNORECASE)
    if as_match:
        current_as = as_match.group(1)
        if current_as != expected_as:
            return {
                'type': 'as mismatch',
                'category': 'eigrp',
                'current': current_as,
                'expected': expected_as,
                'line': f'router eigrp {current_as} (expected: {expected_as})'
            }
    
    return None


def parse_eigrp_debug(debug_output):
    """Parse EIGRP debug output for common mismatches."""
    mismatches = []
    
    for line in debug_output.split('\n'):
        line_lower = line.lower()

        if "k-value mismatch" in line_lower or "k value mismatch" in line_lower:
            mismatches.append({'type': 'k-value mismatch', 'category': 'eigrp', 'line': line.strip()})

        if "not on common subnet" in line_lower:
            interface = None
            match = re.search(r'(FastEthernet|GigabitEthernet|Ethernet|Serial)[\d/]+', line)
            if match:
                interface = match.group(0)
            mismatches.append({'type': 'wrong subnet', 'category': 'eigrp', 'interface': interface, 'line': line.strip()})

        if "authentication" in line_lower and ("fail" in line_lower or "mismatch" in line_lower):
            mismatches.append({'type': 'authentication mismatch', 'category': 'eigrp', 'line': line.strip()})

        if "as mismatch" in line_lower or "autonomous system" in line_lower:
            as_numbers = re.findall(r'AS\s+(\d+)', line, re.IGNORECASE)
            mismatches.append({
                'type': 'as mismatch',
                'category': 'eigrp',
                'line': line.strip(),
                'as_numbers': as_numbers if as_numbers else []
            })

        if ("peer terminating" in line_lower and "stub" in line_lower) or "stub configuration" in line_lower:
            mismatches.append({'type': 'stub mismatch', 'category': 'eigrp', 'line': line.strip()})

    return mismatches


def check_passive_interfaces(tn, device_name, config_manager=None):
    """Check for incorrectly configured passive EIGRP interfaces."""
    config = get_eigrp_config(tn)
    if not config:
        return []

    if config_manager is None:
        config_manager = ConfigManager()

    baseline = config_manager.get_device_baseline(device_name)
    expected_passive = baseline.get('eigrp', {}).get('passive_interfaces', [])

    passive_interfaces = []
    
    for line in config.split('\n'):
        if 'passive-interface' in line.lower():
            match = re.search(r'passive-interface\s+(\S+)', line, re.IGNORECASE)
            if match:
                interface = match.group(1)
                
                if interface not in expected_passive:
                    passive_interfaces.append({
                        'type': 'passive interface',
                        'category': 'eigrp',
                        'interface': interface,
                        'line': line.strip(),
                        'should_be_passive': False
                    })
    
    return passive_interfaces


def check_metric_weights(tn, device_name, config_manager=None):
    """Check EIGRP metric weights (K-values) against baseline."""
    config = get_eigrp_config(tn)
    if not config:
        return None

    if config_manager is None:
        config_manager = ConfigManager()

    baseline = config_manager.get_device_baseline(device_name)
    expected_k = baseline.get('eigrp', {}).get('k_values', '0 1 0 1 0 0')
    
    for line in config.split('\n'):
        if 'metric weights' in line.lower():
            match = re.search(r'metric weights\s+(\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+)', line, re.IGNORECASE)
            if match:
                current_k = match.group(1)
                if current_k != expected_k:
                    return {
                        'type': 'non-default k-values',
                        'category': 'eigrp',
                        'values': current_k,
                        'expected': expected_k,
                        'line': line.strip()
                    }
    return None


def check_network_statements(tn, device_name, config_manager=None):
    """Check if EIGRP network statements match baseline."""
    config = get_eigrp_config(tn)
    if not config:
        return []

    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    expected_networks_list = baseline.get('eigrp', {}).get('networks', [])
    expected_networks = set(expected_networks_list) if expected_networks_list else set()
    
    current_networks = set()
    in_eigrp_section = False
    
    for line in config.split('\n'):
        line = line.strip()
        
        if line.startswith('router eigrp'):
            in_eigrp_section = True
            continue
        
        if in_eigrp_section and line.startswith('!'):
            in_eigrp_section = False
            continue
        
        if in_eigrp_section and line.startswith('network'):
            match = re.search(r'network\s+([\d.]+)', line, re.IGNORECASE)
            if match:
                network = match.group(1)
                current_networks.add(network)
    
    issues = []
    
    if not expected_networks:
        print(f"[WARNING {device_name}] No expected networks in baseline - skipping network check")
        return []
    
    missing = expected_networks - current_networks
    for net in missing:
        issues.append({
            'type': 'missing network',
            'category': 'eigrp',
            'network': net,
            'line': f'missing: network {net}'
        })
    
    extra = current_networks - expected_networks
    for net in extra:
        issues.append({
            'type': 'extra network',
            'category': 'eigrp',
            'network': net,
            'line': f'unexpected: network {net}'
        })
    
    return issues


def get_eigrp_fix_commands(issue_type, issue_details, device_name, config_manager=None):
    """Get fix commands for EIGRP issues."""
    if config_manager is None:
        config_manager = ConfigManager()
    
    as_number = config_manager.get_eigrp_as_number(device_name)
    
    if issue_type in ['k-value mismatch', 'non-default k-values']:
        expected_k = issue_details.get('expected', '0 1 0 1 0 0')
        return [
            f"router eigrp {as_number}",
            f"metric weights {expected_k}",
            "end"
        ]
    
    elif issue_type == 'passive interface':
        interface = issue_details.get('interface')
        should_be_passive = issue_details.get('should_be_passive', False)
        if not should_be_passive:
            return [
                f"router eigrp {as_number}",
                f"no passive-interface {interface}",
                "end"
            ]
    
    elif issue_type == 'stub configuration':
        should_be_stub = issue_details.get('should_be_stub', False)
        if not should_be_stub:
            return [
                f"router eigrp {as_number}",
                "no eigrp stub",
                "end"
            ]
    
    elif issue_type == 'missing stub configuration':
        return [
            f"router eigrp {as_number}",
            "eigrp stub",
            "end"
        ]
    
    elif issue_type == 'as mismatch':
        expected_as = issue_details.get('expected', as_number)
        current_as = issue_details.get('current')
        if current_as and expected_as:
            return [
                f"no router eigrp {current_as}",
                f"router eigrp {expected_as}",
                "# NOTE: Network statements will need to be re-added"
            ]
    
    elif issue_type == 'missing network':
        network = issue_details.get('network')
        return [
            f"router eigrp {as_number}",
            f"network {network}",
            "end"
        ]
    
    elif issue_type == 'extra network':
        network = issue_details.get('network')
        return [
            f"router eigrp {as_number}",
            f"no network {network}",
            "end"
        ]
    
    elif issue_type in ['eigrp hello timer mismatch', 'eigrp hold timer mismatch', 'eigrp timer mismatch']:
        interface = issue_details.get('interface')
        expected_hello = issue_details.get('expected_hello', 5)
        expected_hold = issue_details.get('expected_hold', 15)
        cmd_as_number = issue_details.get('as_number', as_number)
        
        return [
            f"interface {interface}",
            f"ip hello-interval eigrp {cmd_as_number} {expected_hello}",
            f"ip hold-time eigrp {cmd_as_number} {expected_hold}",
            "end"
        ]
    
    return []


def apply_eigrp_fixes(tn, fixes):
    """Apply EIGRP configuration fixes."""
    try:
        clear_line_and_reset(tn)
        tn.write(b'configure terminal\r\n')
        time.sleep(0.3)
        tn.read_very_eager()

        for cmd in fixes:
            if cmd.startswith('#'):
                continue
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(0.3)
            tn.read_very_eager()

        tn.write(b'end\r\n')
        time.sleep(0.3)
        tn.read_very_eager()

        return True
    except Exception:
        return False


def verify_eigrp_neighbors(tn):
    """Verify EIGRP neighbors after fix."""
    try:
        tn.write(b'\x03')
        time.sleep(0.1)
        tn.read_very_eager()
        tn.write(b'end\r\n')
        time.sleep(0.1)
        tn.read_very_eager()
        
        tn.write(b'show ip eigrp neighbors\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        
        neighbors = []
        for line in output.split('\n'):
            if re.search(r'\d+\.\d+\.\d+\.\d+', line) and 'Address' not in line:
                parts = line.split()
                if len(parts) >= 2:
                    for part in parts:
                        if re.match(r'\d+\.\d+\.\d+\.\d+', part):
                            neighbors.append(part)
                            break
        
        if neighbors:
            return "EIGRP Neighbors: " + ", ".join(neighbors)
        else:
            return "EIGRP: No neighbors found"
    except Exception:
        return "EIGRP: Verification Failed"


def troubleshoot_eigrp(device_name, tn, auto_prompt=True, config_manager=None):
    """Main EIGRP troubleshooting function."""
    if config_manager is None:
        config_manager = ConfigManager()
    
    if not config_manager.is_eigrp_router(device_name):
        return [], []
    
    all_issues = []

    as_issue = check_as_mismatch(tn, device_name, config_manager)
    if as_issue:
        all_issues.append(as_issue)

    stub_issue = check_stub_configuration(tn, device_name, config_manager)
    if stub_issue:
        all_issues.append(stub_issue)

    passive_intfs = check_passive_interfaces(tn, device_name, config_manager)
    if passive_intfs:
        all_issues.extend(passive_intfs)

    k_values = check_metric_weights(tn, device_name, config_manager)
    if k_values:
        all_issues.append(k_values)

    network_issues = check_network_statements(tn, device_name, config_manager)
    if network_issues:
        all_issues.extend(network_issues)

    timer_issues = check_eigrp_interface_timers(tn, device_name, config_manager)
    if timer_issues:
        all_issues.extend(timer_issues)

    neighbor_output = get_eigrp_neighbors(tn)
    if not neighbor_output:
        return all_issues, []

    neighbor_lines = [l for l in neighbor_output.split('\n')
                     if l.strip() and not l.startswith('H') and 'Address' not in l]
    neighbor_count = len([l for l in neighbor_lines if any(c.isdigit() for c in l)])

    if neighbor_count == 0 and not all_issues:
        if enable_eigrp_debug(tn):
            debug_output = gather_eigrp_debug(tn, wait_time=5)
            disable_debug(tn)
            if debug_output:
                debug_issues = parse_eigrp_debug(debug_output)
                all_issues.extend(debug_issues)

    if not all_issues:
        return [], []

    if not auto_prompt:
        return all_issues, []

    fixed_issues = []
    for issue in all_issues:
        issue_type = issue['type']
        print(f"\nProblem: {device_name} - {issue_type}")
        if 'line' in issue:
            print(f"  Details: {issue['line'][:80]}")
        if 'message' in issue:
            print(f"  {issue['message']}")

        response = input("Apply fixes? (Y/n): ").strip().lower()
        if response == 'n':
            continue

        fix_commands = get_eigrp_fix_commands(issue_type, issue, device_name, config_manager)
        
        if not fix_commands:
            print("Note: Manual intervention required")
            continue

        print(f"Commands to apply:")
        for cmd in fix_commands:
            print(f"  {cmd}")

        if apply_eigrp_fixes(tn, fix_commands):
            print("Fixes applied successfully")
            fixed_issues.append(issue_type)
        else:
            print("Failed to apply fixes")

    return all_issues, fixed_issues
