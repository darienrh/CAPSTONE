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

def get_eigrp_neighbors(tn):
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip eigrp neighbors\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None

def check_eigrp_interface_timers(config, device_name, config_manager=None):
    issues = []
    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    baseline_interfaces = baseline.get('interfaces', {})
    as_number = config_manager.get_eigrp_as_number(device_name)
    
    interface_sections = re.findall(
        r'interface\s+(\S+)\n(.*?)(?=\ninterface |\nrouter |\n!|\Z)',
        config, re.DOTALL
    )
    
    for intf_name, intf_config in interface_sections:
        if intf_name not in baseline_interfaces:
            continue
        
        intf_info = baseline_interfaces[intf_name]
        if not intf_info.get('ip_address'):
            continue
        
        eigrp_hello_match = re.search(r'ip hello-interval eigrp\s+\d+\s+(\d+)', intf_config)
        eigrp_hold_match = re.search(r'ip hold-time eigrp\s+\d+\s+(\d+)', intf_config)
        
        expected_hello = intf_info.get('eigrp_hello', 5)
        expected_hold = intf_info.get('eigrp_hold', 15)
        
        current_hello = int(eigrp_hello_match.group(1)) if eigrp_hello_match else expected_hello
        current_hold = int(eigrp_hold_match.group(1)) if eigrp_hold_match else expected_hold
        
        if current_hello != expected_hello or current_hold != expected_hold:
            issues.append({
                'type': 'eigrp timer mismatch',
                'category': 'eigrp',
                'interface': intf_name,
                'current_hello': current_hello,
                'current_hold': current_hold,
                'expected_hello': expected_hello,
                'expected_hold': expected_hold,
                'as_number': as_number,
                'line': f'{intf_name}: Hello {current_hello}s/{expected_hello}s, Hold {current_hold}s/{expected_hold}s'
            })
    
    return issues

def check_eigrp_interface_participation(config, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    expected_eigrp_interfaces = set(
        config_manager.EIGRP_INTERFACE_PARTICIPATION.get(device_name, [])
    )
    
    if not expected_eigrp_interfaces:
        return []
    
    baseline = config_manager.get_device_baseline(device_name)
    baseline_interfaces = baseline.get('interfaces', {})
    
    # Get current EIGRP network statements from config
    current_eigrp_networks = []
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
                current_eigrp_networks.append(network)
    
    # Check which interfaces should be in EIGRP based on IP addresses matching network statements
    current_eigrp_interfaces = set()
    
    for intf_name in baseline_interfaces:
        intf_info = baseline_interfaces[intf_name]
        ip_address = intf_info.get('ip_address')
        
        if not ip_address:
            continue
        
        # Check if this interface's IP matches any current EIGRP network statement
        for network in current_eigrp_networks:
            if ip_matches_eigrp_network(ip_address, network):
                current_eigrp_interfaces.add(intf_name)
                break
    
    issues = []
    
    missing_interfaces = expected_eigrp_interfaces - current_eigrp_interfaces
    
    for intf in missing_interfaces:
        if intf not in baseline_interfaces:
            continue
            
        intf_info = baseline_interfaces.get(intf, {})
        ip_addr = intf_info.get('ip_address', 'unknown')
        
        issues.append({
            'type': 'interface not in eigrp',
            'interface': intf,
            'ip_address': ip_addr,
            'line': f'{intf} ({ip_addr}) should be in EIGRP but is not configured',
            'should_be_in_eigrp': True
        })
    
    extra_interfaces = current_eigrp_interfaces - expected_eigrp_interfaces
    
    for intf in extra_interfaces:
        if intf not in baseline_interfaces:
            continue
            
        intf_info = baseline_interfaces.get(intf, {})
        ip_addr = intf_info.get('ip_address', 'unknown')
        
        issues.append({
            'type': 'interface should not be in eigrp',
            'interface': intf,
            'ip_address': ip_addr,
            'line': f'{intf} ({ip_addr}) should NOT be in EIGRP (end-user facing interface)',
            'should_be_in_eigrp': False
        })
    
    return issues

def ip_matches_eigrp_network(ip_address, network):
    try:
        ip_parts = [int(x) for x in ip_address.split('.')]
        net_parts = [int(x) for x in network.split('.')]
        
        # For networks like "192.168.1.0", check first 3 octets
        # This assumes /24 networks for simplicity
        for i in range(3):
            if net_parts[i] != ip_parts[i]:
                return False
        
        return True
    except (ValueError, IndexError, AttributeError):
        return False

def check_stub_configuration(config, device_name, config_manager=None):
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

def check_as_mismatch(config, device_name, config_manager=None):
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

def check_passive_interfaces(config, device_name, config_manager=None):
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

def check_metric_weights(config, device_name, config_manager=None):
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

def check_network_statements(config, device_name, config_manager=None):
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
    if config_manager is None:
        config_manager = ConfigManager()
    
    as_number = config_manager.get_eigrp_as_number(device_name)
    
    if issue_type in ['interface not in eigrp', 'interface should not be in eigrp']:
        interface = issue_details.get('interface')
        should_be_in_eigrp = issue_details.get('should_be_in_eigrp', False)
        
        if should_be_in_eigrp:
            baseline = config_manager.get_device_baseline(device_name)
            intf_info = baseline.get('interfaces', {}).get(interface, {})
            ip_address = intf_info.get('ip_address', '')
            
            if ip_address:
                network_parts = ip_address.split('.')
                network = f"{network_parts[0]}.{network_parts[1]}.{network_parts[2]}.0"
                
                return [
                    f"router eigrp {as_number}",
                    f"network {network}",
                    "end"
                ]
            else:
                return ["# Cannot determine network for interface without IP address"]
        else:
            baseline = config_manager.get_device_baseline(device_name)
            intf_info = baseline.get('interfaces', {}).get(interface, {})
            ip_address = intf_info.get('ip_address', '')
            
            if ip_address:
                network_parts = ip_address.split('.')
                network = f"{network_parts[0]}.{network_parts[1]}.{network_parts[2]}.0"
                
                return [
                    f"router eigrp {as_number}",
                    f"no network {network}",
                    "end"
                ]
            else:
                return ["# Cannot determine network to remove for interface without IP address"]
    
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
                "end"
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
    from utils.telnet_utils import get_running_config
    if config_manager is None:
        config_manager = ConfigManager()
    
    if not config_manager.is_eigrp_router(device_name):
        return [], []
    
    config = get_running_config(tn)
    if not config:
        return [], []
    
    all_issues = []
    
    as_issue = check_as_mismatch(config, device_name, config_manager)
    if as_issue:
        all_issues.append(as_issue)
    
    stub_issue = check_stub_configuration(config, device_name, config_manager)
    if stub_issue:
        all_issues.append(stub_issue)
    
    passive_intfs = check_passive_interfaces(config, device_name, config_manager)
    if passive_intfs:
        all_issues.extend(passive_intfs)
    
    k_values = check_metric_weights(config, device_name, config_manager)
    if k_values:
        all_issues.append(k_values)
    
    network_issues = check_network_statements(config, device_name, config_manager)
    if network_issues:
        all_issues.extend(network_issues)
    
    timer_issues = check_eigrp_interface_timers(config, device_name, config_manager)
    if timer_issues:
        all_issues.extend(timer_issues)
    
    participation_issues = check_eigrp_interface_participation(config, device_name, config_manager)
    if participation_issues:
        all_issues.extend(participation_issues)
    
    neighbor_output = get_eigrp_neighbors(tn)
    
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