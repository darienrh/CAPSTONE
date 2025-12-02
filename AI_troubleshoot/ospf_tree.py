#!/usr/bin/env python3
"""OSPF troubleshooting with stable config baseline"""

import warnings
warnings.filterwarnings('ignore')

import time
import re

try:
    from config_parser import (get_device_baseline, get_ospf_process_id, is_ospf_router)
except ImportError:
    def get_device_baseline(device_name): return {}
    def get_ospf_process_id(device_name): return '10'
    def is_ospf_router(device_name):
        return device_name.upper() in ['R4', 'R5', 'R6']


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
    """Enable OSPF debugging"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'debug ip ospf adj\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except Exception:
        return False


def disable_debug(tn):
    """Disable all debugging"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'no debug all\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except Exception:
        return False


def gather_ospf_debug(tn, wait_time=10):
    """Gather OSPF debug output"""
    try:
        time.sleep(wait_time)
        tn.write(b"show logging\r\n")
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None


def get_ospf_neighbors(tn):
    """Get OSPF neighbor information"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip ospf neighbor\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None


def get_ospf_config(tn):
    """Get OSPF running configuration"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'show running-config | begin router ospf\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None


def get_ospf_interface_info(tn, interface):
    """Get OSPF interface information"""
    try:
        clear_line_and_reset(tn)
        cmd = f'show ip ospf interface {interface}\r\n'
        tn.write(cmd.encode('ascii'))
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None


def check_process_id_mismatch(tn, device_name):
    """Check for OSPF process ID mismatch"""
    config = get_ospf_config(tn)
    if not config:
        return None
    
    expected_process = get_ospf_process_id(device_name)
    
    # Find current process ID
    process_match = re.search(r'router ospf\s+(\d+)', config, re.IGNORECASE)
    if process_match:
        current_process = process_match.group(1)
        if current_process != expected_process:
            return {
                'type': 'process id mismatch',
                'current': current_process,
                'expected': expected_process,
                'line': f'router ospf {current_process} (expected: {expected_process})'
            }
    
    return None


def check_passive_interfaces(tn, device_name):
    """Check for incorrectly configured passive OSPF interfaces"""
    config = get_ospf_config(tn)
    if not config:
        return []

    baseline = get_device_baseline(device_name)
    expected_passive = baseline.get('ospf', {}).get('passive_interfaces', [])

    passive_interfaces = []
    current_passive = []
    
    for line in config.split('\n'):
        if 'passive-interface' in line.lower():
            match = re.search(r'passive-interface\s+(\S+)', line, re.IGNORECASE)
            if match:
                interface = match.group(1)
                current_passive.append(interface)
                
                # If this interface shouldn't be passive according to baseline
                if interface not in expected_passive:
                    passive_interfaces.append({
                        'type': 'passive interface',
                        'interface': interface,
                        'line': line.strip(),
                        'should_be_passive': False
                    })
    
    return passive_interfaces


def check_stub_config(tn, device_name):
    """Check for OSPF stub/totally stubby area configuration issues"""
    config = get_ospf_config(tn)
    if not config:
        return []

    issues = []
    
    # Look for stub area configurations
    stub_matches = re.findall(r'area\s+(\d+)\s+stub', config, re.IGNORECASE)
    
    for area in stub_matches:
        issues.append({
            'type': 'stub area',
            'area': area,
            'line': f'area {area} stub'
        })
    
    return issues


def check_network_statements(tn, device_name):
    """Check if OSPF network statements match baseline"""
    config = get_ospf_config(tn)
    if not config:
        return []

    baseline = get_device_baseline(device_name)
    expected_networks = baseline.get('ospf', {}).get('networks', [])
    
    # Parse current network statements
    current_networks = []
    for line in config.split('\n'):
        if line.strip().startswith('network'):
            match = re.search(r'network\s+([\d.]+)\s+([\d.]+)\s+area\s+(\d+)', line, re.IGNORECASE)
            if match:
                current_networks.append({
                    'network': match.group(1),
                    'wildcard': match.group(2),
                    'area': match.group(3)
                })
    
    issues = []
    
    # Convert to comparable format
    expected_set = {(n['network'], n['wildcard'], n['area']) for n in expected_networks}
    current_set = {(n['network'], n['wildcard'], n['area']) for n in current_networks}
    
    # Missing networks
    missing = expected_set - current_set
    for net, wild, area in missing:
        issues.append({
            'type': 'missing network',
            'network': net,
            'wildcard': wild,
            'area': area,
            'line': f'missing: network {net} {wild} area {area}'
        })
    
    # Extra networks
    extra = current_set - expected_set
    for net, wild, area in extra:
        issues.append({
            'type': 'extra network',
            'network': net,
            'wildcard': wild,
            'area': area,
            'line': f'unexpected: network {net} {wild} area {area}'
        })
    
    return issues


def check_interface_timers(tn, device_name):
    baseline = get_device_baseline(device_name)
    interfaces = baseline.get('interfaces', {})
    
    issues = []
    
    for intf_name, intf_info in interfaces.items():
        if not intf_info.get('ip_address'):
            continue
        
        intf_output = get_ospf_interface_info(tn, intf_name)
        if not intf_output:
            continue
        
        hello_match = re.search(r'Timer intervals.*Hello\s+(\d+)', intf_output, re.IGNORECASE)
        dead_match = re.search(r'Timer intervals.*Dead\s+(\d+)', intf_output, re.IGNORECASE)
        
        expected_hello = 10
        expected_dead = 40
        
        if hello_match:
            current_hello = int(hello_match.group(1))
            if current_hello != expected_hello:
                issues.append({
                    'type': 'hello interval mismatch',
                    'interface': intf_name,
                    'current': current_hello,
                    'expected': expected_hello,
                    'line': f'{intf_name}: Hello {current_hello} (expected {expected_hello})'
                })
        
        if dead_match:
            current_dead = int(dead_match.group(1))
            if current_dead != expected_dead:
                issues.append({
                    'type': 'dead interval mismatch',
                    'interface': intf_name,
                    'current': current_dead,
                    'expected': expected_dead,
                    'line': f'{intf_name}: Dead {current_dead} (expected {expected_dead})'
                })
    
    return issues

def check_router_id_conflicts(tn, device_name):
    issues = []
    
    expected_rids = {
        'R4': '4.4.4.4',
        'R5': '5.5.5.5',
        'R6': '6.6.6.6'
    }
    
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip ospf\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        
        rid_match = re.search(r'Router ID\s+([\d.]+)', output, re.IGNORECASE)
        if rid_match:
            current_rid = rid_match.group(1)
            expected_rid = expected_rids.get(device_name)
            
            if expected_rid and current_rid != expected_rid:
                issues.append({
                    'type': 'router id mismatch',
                    'current': current_rid,
                    'expected': expected_rid,
                    'line': f'Router ID {current_rid} (expected {expected_rid})'
                })
    except Exception:
        pass
    
    neighbor_output = get_ospf_neighbors(tn)
    if neighbor_output:
        for line in neighbor_output.split('\n'):
            if 'INIT' in line.upper():
                issues.append({
                    'type': 'possible duplicate router id',
                    'line': line.strip(),
                    'message': 'Neighbor stuck in INIT - may indicate duplicate router ID'
                })
                break
    
    return issues


def check_area_assignments(tn, device_name):
    baseline = get_device_baseline(device_name)
    expected_networks = baseline.get('ospf', {}).get('networks', [])
    
    if not expected_networks:
        return []
    
    issues = []
    
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip ospf interface brief\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        
        for line in output.split('\n'):
            if not line.strip() or 'Interface' in line:
                continue
            
            parts = line.split()
            if len(parts) >= 3:
                interface = parts[0]
                area = parts[2]
                
                if area != '0':
                    issues.append({
                        'type': 'area mismatch',
                        'interface': interface,
                        'current_area': area,
                        'expected_area': '0',
                        'line': f'{interface}: Area {area} (expected 0)'
                    })
    
    except Exception:
        pass
    
    return issues

def parse_ospf_debug(debug_output):
    """Parse OSPF debug output for mismatches"""
    mismatches = []
    
    for line in debug_output.splitlines():
        line_lower = line.lower()
        
        if "hello" in line_lower and "mismatch" in line_lower:
            mismatches.append({'type': 'hello interval mismatch', 'line': line.strip()})
        
        if "dead" in line_lower and "mismatch" in line_lower:
            mismatches.append({'type': 'dead interval mismatch', 'line': line.strip()})
        
        if "duplicate router" in line_lower or "duplicate rid" in line_lower:
            mismatches.append({'type': 'duplicate router id', 'line': line.strip()})
        
        if "area mismatch" in line_lower:
            mismatches.append({'type': 'area mismatch', 'line': line.strip()})
        
        if "netmask mismatch" in line_lower or "mask mismatch" in line_lower:
            mismatches.append({'type': 'netmask mismatch', 'line': line.strip()})
        
        if "authentication" in line_lower and ("fail" in line_lower or "mismatch" in line_lower):
            mismatches.append({'type': 'authentication mismatch', 'line': line.strip()})
    
    return mismatches


def get_ospf_fix_commands(issue_type, issue_details, device_name):
    """Get fix commands for OSPF issues"""
    process_id = get_ospf_process_id(device_name)
    
    if issue_type in ['hello interval mismatch', 'dead interval mismatch']:
        interface = issue_details.get('interface')
        expected_hello = 10
        expected_dead = 40
        
        return [
            f"interface {interface}",
            f"ip ospf hello-interval {expected_hello}",
            f"ip ospf dead-interval {expected_dead}"
        ]
    
    elif issue_type == 'passive interface':
        interface = issue_details.get('interface')
        should_be_passive = issue_details.get('should_be_passive', False)
        if not should_be_passive:
            return [f"router ospf {process_id}", f"no passive-interface {interface}"]
    
    elif issue_type == 'process id mismatch':
        expected_process = issue_details.get('expected', process_id)
        current_process = issue_details.get('current')
        if current_process and expected_process:
            return [
                f"no router ospf {current_process}",
                f"router ospf {expected_process}",
                "# Network statements will need to be re-added manually"
            ]
    
    elif issue_type == 'missing network':
        network = issue_details.get('network')
        wildcard = issue_details.get('wildcard')
        area = issue_details.get('area')
        return [f"router ospf {process_id}", f"network {network} {wildcard} area {area}"]
    
    elif issue_type == 'extra network':
        network = issue_details.get('network')
        wildcard = issue_details.get('wildcard')
        area = issue_details.get('area')
        return [f"router ospf {process_id}", f"no network {network} {wildcard} area {area}"]
    
    elif issue_type == 'stub area':
        area = issue_details.get('area')
        return [f"router ospf {process_id}", f"no area {area} stub"]
    
    # **NEW: Router ID fixes**
    elif issue_type == 'router id mismatch':
        expected_rid = issue_details.get('expected')
        if expected_rid:
            return [
                f"router ospf {process_id}",
                f"router-id {expected_rid}",
                "# May need to clear OSPF process: clear ip ospf process"
            ]
    
    elif issue_type == 'possible duplicate router id':
        return []  # Manual intervention required
    
    elif issue_type == 'area mismatch':
        interface = issue_details.get('interface')
        expected_area = issue_details.get('expected_area', '0')
        
        return [
            f"router ospf {process_id}",
            f"# Check network statements and fix area assignments to area {expected_area}"
        ]
    
    return []


def apply_ospf_fixes(tn, fixes):
    """Apply OSPF configuration fixes"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'configure terminal\r\n')
        time.sleep(0.3)
        tn.read_very_eager()

        for cmd in fixes:
            if cmd.startswith('#'):  # Skip comments
                continue
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
    except Exception:
        return False


def verify_ospf_neighbors(tn):
    """Verify OSPF neighbors after fix"""
    try:
        tn.write(b'\x03')
        time.sleep(0.1)
        tn.read_very_eager()
        tn.write(b'end\r\n')
        time.sleep(0.1)
        tn.read_very_eager()
        
        tn.write(b'show ip ospf neighbor\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        
        neighbors = []
        for line in output.split('\n'):
            if re.search(r'\d+\.\d+\.\d+\.\d+', line) and 'Neighbor ID' not in line and 'Address' not in line:
                parts = line.split()
                if len(parts) >= 1:
                    # First IP is usually the neighbor ID
                    match = re.match(r'\d+\.\d+\.\d+\.\d+', parts[0])
                    if match:
                        neighbors.append(parts[0])
        
        if neighbors:
            return "OSPF Neighbors: " + ", ".join(set(neighbors))
        else:
            return "OSPF: No neighbors found"
    except Exception:
        return "OSPF: Verification Failed"


def troubleshoot_ospf(device_name, tn, auto_prompt=True):

    if not is_ospf_router(device_name):
        return [], []
    
    all_issues = []

    # Check process ID
    process_issue = check_process_id_mismatch(tn, device_name)
    if process_issue:
        all_issues.append(process_issue)

    # Check passive interfaces
    passive_intfs = check_passive_interfaces(tn, device_name)
    if passive_intfs:
        all_issues.extend(passive_intfs)

    # Check stub configuration
    stub_issues = check_stub_config(tn, device_name)
    if stub_issues:
        all_issues.extend(stub_issues)

    # Check network statements
    network_issues = check_network_statements(tn, device_name)
    if network_issues:
        all_issues.extend(network_issues)

    # Check interface timers
    timer_issues = check_interface_timers(tn, device_name)
    if timer_issues:
        all_issues.extend(timer_issues)

    # Check router ID conflicts
    rid_issues = check_router_id_conflicts(tn, device_name)
    if rid_issues:
        all_issues.extend(rid_issues)
    
    # Check area assignments
    area_issues = check_area_assignments(tn, device_name)
    if area_issues:
        all_issues.extend(area_issues)

    # Check if OSPF neighbors exist
    neighbor_output = get_ospf_neighbors(tn)
    if not neighbor_output:
        return all_issues, []

    neighbor_lines = [l for l in neighbor_output.split('\n')
                     if l.strip() and 'Neighbor' not in l and 'Address' not in l]
    neighbor_count = len([l for l in neighbor_lines if any(c.isdigit() for c in l)])

    # If no neighbors, use debug to find more issues
    if neighbor_count == 0 and not all_issues:
        if enable_ospf_debug(tn):
            debug_output = gather_ospf_debug(tn, wait_time=10)
            disable_debug(tn)
            if debug_output:
                debug_issues = parse_ospf_debug(debug_output)
                all_issues.extend(debug_issues)

    if not all_issues:
        return [], []

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
            continue

        fix_commands = get_ospf_fix_commands(issue_type, issue, device_name)
        
        if not fix_commands:
            print("Note: Manual intervention required")
            continue

        print(f"Commands to apply:")
        for cmd in fix_commands:
            print(f"  {cmd}")

        if apply_ospf_fixes(tn, fix_commands):
            print("Fixes applied successfully")
            fixed_issues.append(issue_type)
        else:
            print("Failed to apply fixes")

    return all_issues, fixed_issues