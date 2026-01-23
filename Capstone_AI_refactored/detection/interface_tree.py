#!/usr/bin/env python3
"""
interface_tree.py - Interface troubleshooting detection tree
UPDATED: Integrated with new modular architecture
"""

import time
import re

# Import from new modular structure
try:
    from ..core.config_manager import ConfigManager
    from ..utils.telnet_utils import clear_line_and_reset, send_command
except ImportError:
    # Fallback for direct execution or transition period
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.config_manager import ConfigManager
    from utils.telnet_utils import clear_line_and_reset, send_command

# Initialize config manager
_config_manager = ConfigManager()

def get_interface_diagnostics(tn):
    try:
        clear_line_and_reset(tn)
        tn.write(b'show interfaces\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output if len(output) >= 50 else None
    except Exception:
        return None

def get_interface_stats(tn):
    try:
        clear_line_and_reset(tn)
        tn.write(b'show interface stats\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None


def collect_interface_diagnostics(tn):
    diagnostics = {
        'show_interfaces': None,
        'show_interface_stats': None
    }
    
    diagnostics['show_interfaces'] = get_interface_diagnostics(tn)
    diagnostics['show_interface_stats'] = get_interface_stats(tn)
    
    return diagnostics

def parse_interfaces_from_config(config, device_name):
    problems = []
    baseline = _config_manager.get_device_baseline(device_name)
    baseline_interfaces = baseline.get('interfaces', {})
    
    interface_sections = re.findall(
        r'interface\s+(\S+)\n(.*?)(?=\ninterface |\nrouter |\n!|\Z)',
        config, re.DOTALL
    )
    
    for intf_name, intf_config in interface_sections:
        if intf_name not in baseline_interfaces:
            continue
            
        expected_config = baseline_interfaces[intf_name]
        is_shutdown = bool(re.search(r'^\s*shutdown\s*$', intf_config, re.MULTILINE))
        should_be_up = _config_manager.should_interface_be_up(device_name, intf_name)
        
        if is_shutdown and should_be_up:
            ip_details = []
            if expected_config.get('ip_address'):
                ip_details.append(f"IPv4: {expected_config['ip_address']} {expected_config.get('subnet_mask', '')}")
            
            problems.append({
                'type': 'shutdown',
                'category': 'interface',
                'interface': intf_name,
                'status': 'administratively down',
                'should_be_up': True,
                'ip_details': " | ".join(ip_details) if ip_details else "IP configured",
                'protocol': 'down',
                'severity': 'high'
            })
        
        ip_match = re.search(r'ip address\s+([\d.]+)\s+([\d.]+)', intf_config, re.IGNORECASE)
        expected_ip = expected_config.get('ip_address')
        expected_mask = expected_config.get('subnet_mask')
        
        if ip_match and expected_ip:
            current_ip = ip_match.group(1)
            current_mask = ip_match.group(2)
            
            if current_ip != expected_ip or current_mask != expected_mask:
                problems.append({
                    'type': 'ip address mismatch',
                    'category': 'interface',
                    'interface': intf_name,
                    'current_ip': current_ip,
                    'current_mask': current_mask,
                    'expected_ip': expected_ip,
                    'expected_mask': expected_mask,
                    'severity': 'high'
                })
        elif not ip_match and expected_ip:
            problems.append({
                'type': 'missing ip address',
                'category': 'interface',
                'interface': intf_name,
                'expected_ip': expected_ip,
                'expected_mask': expected_mask,
                'severity': 'high'
            })
    
    return problems

def get_interface_config(tn, interface):
    """
    Get configuration for a specific interface
    
    Args:
        tn: Telnet connection
        interface: Interface name
    
    Returns:
        Interface configuration as string or None
    """
    try:
        clear_line_and_reset(tn)
        tn.write(f'show run interface {interface}\r\n'.encode('ascii'))
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        
        # Extract just the interface configuration section
        interface_pattern = rf'interface\s+{re.escape(interface)}\n(.*?)(?=\ninterface|\n!|\nrouter|\nend)'
        match = re.search(interface_pattern, output, re.DOTALL | re.IGNORECASE)
        
        if match:
            return match.group(1)
        else:
            # Fallback to parsing from running config
            return None
    except Exception:
        return None

def check_ip_address_mismatch(tn, device_name, interface):
    """
    Check if interface IP matches baseline configuration
    
    Args:
        tn: Telnet connection
        device_name: Device name
        interface: Interface name
    
    Returns:
        Problem dict or None
    """
    current_config = get_interface_config(tn, interface)
    if not current_config:
        return None
    
    # Get expected configuration from baseline
    expected_config = _config_manager.get_interface_ip_config(device_name, interface)
    if not expected_config:
        return None
    
    expected_ip = expected_config.get('ip_address')
    expected_mask = expected_config.get('subnet_mask')
    
    if not expected_ip:
        return None
    
    # Parse current IP from running config
    ip_match = re.search(r'ip address\s+([\d.]+)\s+([\d.]+)', current_config, re.IGNORECASE)
    
    if ip_match:
        current_ip = ip_match.group(1)
        current_mask = ip_match.group(2)
        
        # Check for mismatch
        if current_ip != expected_ip or current_mask != expected_mask:
            return {
                'type': 'ip address mismatch',
                'interface': interface,
                'current_ip': current_ip,
                'current_mask': current_mask,
                'expected_ip': expected_ip,
                'expected_mask': expected_mask,
                'severity': 'high'
            }
    elif expected_ip:
        # IP is completely missing
        return {
            'type': 'missing ip address',
            'interface': interface,
            'expected_ip': expected_ip,
            'expected_mask': expected_mask,
            'severity': 'high'
        }
    
    return None


def parse_interface_output(tn, output, device_name):
    problems = []

    for line in output.split('\n'):
        if not line.strip():
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        if not parts[0].startswith(('FastEthernet', 'GigabitEthernet', 'Ethernet', 'Serial', 'Loopback')):
            continue

        interface = parts[0]
        line_lower = line.lower()

        is_admin_down = 'administratively' in line_lower and 'down' in line_lower
        should_be_up = _config_manager.should_interface_be_up(device_name, interface)
        
        if is_admin_down and should_be_up:
            expected_config = _config_manager.get_interface_ip_config(device_name, interface)
            
            ip_details = []
            if expected_config.get('ip_address'):
                ip_details.append(f"IPv4: {expected_config['ip_address']} {expected_config.get('subnet_mask', '')}")
            
            problems.append({
                'type': 'shutdown',
                'category': 'interface',  
                'interface': interface,
                'status': 'administratively down',
                'should_be_up': True,
                'ip_details': " | ".join(ip_details) if ip_details else "IP configured",
                'protocol': 'down',
                'severity': 'high'
            })

    return problems


def fix_interface_shutdown(tn, interface):
    """
    Apply no shutdown to interface
    
    Args:
        tn: Telnet connection
        interface: Interface name
    
    Returns:
        True if successful, False otherwise
    """
    try:
        clear_line_and_reset(tn)
        commands = ["configure terminal", f"interface {interface}", "no shutdown", "end"]
        
        for cmd in commands:
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(0.2)
            tn.read_very_eager()
        
        return True
    except Exception:
        return False


def fix_interface_ip(tn, interface, ip_address, subnet_mask):
    """
    Configure IP address on interface
    
    Args:
        tn: Telnet connection
        interface: Interface name
        ip_address: IP address to configure
        subnet_mask: Subnet mask to configure
    
    Returns:
        True if successful, False otherwise
    """
    try:
        clear_line_and_reset(tn)
        commands = [
            "configure terminal",
            f"interface {interface}",
            f"ip address {ip_address} {subnet_mask}",
            "end"
        ]
        
        for cmd in commands:
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(0.2)
            tn.read_very_eager()
        
        return True
    except Exception:
        return False


def verify_interface_status(tn, interface):
    """
    Verify interface is up after fix
    
    Args:
        tn: Telnet connection
        interface: Interface name
    
    Returns:
        Status string
    """
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip interface brief\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        
        for line in output.split('\n'):
            if interface in line:
                parts = line.split()
                if len(parts) >= 6:
                    status = parts[-2]
                    protocol = parts[-1]
                    return f"{interface}: {status}/{protocol}"
        
        return f"{interface}: Status Unknown"
    except Exception:
        return f"{interface}: Verification Failed"


def troubleshoot_device(device_name, tn, auto_prompt=True):
    from utils.telnet_utils import get_running_config
    
    config = get_running_config(tn)
    if not config:
        return [], []
    
    problems = parse_interfaces_from_config(config, device_name)
    
    interface_diag = get_interface_diagnostics(tn)
    interface_stats = get_interface_stats(tn)
    
    
    if interface_diag:
        additional_problems = parse_interface_output(tn, interface_diag, device_name)
        for prob in additional_problems:
            if prob not in problems:
                problems.append(prob)
    
    if not problems:
        return [], []
    
    if not auto_prompt:
        return problems, []
    
    fixed_interfaces = []
    for problem in problems:
        problem_type = problem.get('type', 'shutdown')
        interface = problem['interface']
        
        if problem_type == 'ip address mismatch':
            print(f"\nProblem: {device_name} {interface} - IP address mismatch")
            print(f"  Current: {problem['current_ip']} {problem['current_mask']}")
            print(f"  Expected: {problem['expected_ip']} {problem['expected_mask']}")
            
            response = input("Fix IP address? (Y/n): ").strip().lower()
            if response != 'n':
                if fix_interface_ip(tn, interface, problem['expected_ip'], problem['expected_mask']):
                    print(f"✓ Fixed IP address on {interface}")
                    fixed_interfaces.append(interface)
                else:
                    print(f"✗ Failed to fix {interface}")
        
        elif problem_type == 'missing ip address':
            print(f"\nProblem: {device_name} {interface} - Missing IP address")
            print(f"  Expected: {problem['expected_ip']} {problem['expected_mask']}")
            
            response = input("Configure IP address? (Y/n): ").strip().lower()
            if response != 'n':
                if fix_interface_ip(tn, interface, problem['expected_ip'], problem['expected_mask']):
                    print(f"✓ Configured IP address on {interface}")
                    fixed_interfaces.append(interface)
                else:
                    print(f"✗ Failed to configure {interface}")
        
        else:
            ip_details = problem.get('ip_details', '')
            print(f"\nProblem: {device_name} {interface} administratively down")
            if ip_details:
                print(f"  Expected Configuration: {ip_details}")
            
            response = input("Apply 'no shutdown'? (Y/n): ").strip().lower()
            if response != 'n':
                if fix_interface_shutdown(tn, interface):
                    print(f"✓ Fix applied to {interface}")
                    fixed_interfaces.append(interface)
                else:
                    print(f"✗ Failed to fix {interface}")
    
    return problems, fixed_interfaces