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


def get_interface_status(tn):
    """
    Get interface status from device
    
    Args:
        tn: Telnet connection
    
    Returns:
        Command output string or None
    """
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip interface brief\r\n')
        time.sleep(1.5)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output if len(output) >= 50 else None
    except Exception:
        return None


def get_interface_config(tn, interface):
    """
    Get running configuration for a specific interface
    
    Args:
        tn: Telnet connection
        interface: Interface name
    
    Returns:
        Configuration text or None
    """
    try:
        clear_line_and_reset(tn)
        tn.write(b'terminal length 0\r\n')
        time.sleep(0.1)
        cmd = f"show running-config interface {interface}\r\n"
        tn.write(cmd.encode('ascii'))
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
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
    """
    Parse show ip interface brief output and detect problems
    
    Args:
        tn: Telnet connection
        output: Command output text
        device_name: Device name
    
    Returns:
        List of problem dicts
    """
    problems = []

    for line in output.split('\n'):
        if not line.strip():
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        # Check if this is an interface line
        if not parts[0].startswith(('FastEthernet', 'GigabitEthernet', 'Ethernet', 'Serial', 'Loopback')):
            continue

        interface = parts[0]
        line_lower = line.lower()

        # Check if interface is administratively down
        is_admin_down = 'administratively' in line_lower and 'down' in line_lower
        
        # Check if this interface should be up according to baseline
        should_be_up = _config_manager.should_interface_be_up(device_name, interface)
        
        if is_admin_down and should_be_up:
            # Get expected IP configuration for context
            expected_config = _config_manager.get_interface_ip_config(device_name, interface)
            
            ip_details = []
            if expected_config.get('ip_address'):
                ip_details.append(f"IPv4: {expected_config['ip_address']} {expected_config.get('subnet_mask', '')}")
            
            problems.append({
                'type': 'shutdown',
                'interface': interface,
                'status': 'administratively down',
                'should_be_up': True,
                'ip_details': " | ".join(ip_details) if ip_details else "IP configured",
                'protocol': 'down',
                'severity': 'high'
            })
        
        # Also check for IP address mismatches on interfaces that are up
        elif not is_admin_down:
            ip_mismatch = check_ip_address_mismatch(tn, device_name, interface)
            if ip_mismatch:
                problems.append(ip_mismatch)

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
    """
    Run interface troubleshooting on a device
    
    Args:
        device_name: Name of the device
        tn: Open telnet connection
        auto_prompt: If True, prompt user for fixes. If False, just detect issues.
    
    Returns:
        (problems, fixed_interfaces): Tuple of detected problems and fixed interfaces
    """
    # Get interface status
    output = get_interface_status(tn)
    if not output:
        return [], []

    # Parse and detect problems
    problems = parse_interface_output(tn, output, device_name)
    if not problems:
        return [], []

    # If not in auto-prompt mode, just return detected problems
    if not auto_prompt:
        return problems, []

    # Interactive fix mode (for backward compatibility)
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
        
        else:  # administratively down
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