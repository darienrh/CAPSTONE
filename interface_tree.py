#!/usr/bin/env python3
"""
Interface troubleshooting with stable config baseline
Detects interfaces that should be up based on stable config
"""

import warnings
warnings.filterwarnings('ignore')

import time
import re

try:
    from config_parser import (get_device_baseline, should_interface_be_up, 
                               get_interface_ip_config)
except ImportError:
    def get_device_baseline(device_name): return {}
    def should_interface_be_up(device_name, interface): return True
    def get_interface_ip_config(device_name, interface): return {}


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


def get_interface_status(tn):
    """Get interface status from device"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip interface brief\r\n')
        time.sleep(1.5)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output if len(output) >= 50 else None
    except Exception:
        return None


def get_interface_config(tn, interface):
    """Get running configuration for a specific interface"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'terminal length 0\r\n')
        cmd = f"show running-config interface {interface}\r\n"
        tn.write(cmd.encode('ascii'))
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None


def check_ip_address_mismatch(tn, device_name, interface):
    """Check if interface IP matches stable config"""
    current_config = get_interface_config(tn, interface)
    if not current_config:
        return None
    
    expected_config = get_interface_ip_config(device_name, interface)
    if not expected_config:
        return None
    
    expected_ip = expected_config.get('ip_address')
    expected_mask = expected_config.get('subnet_mask')
    
    if not expected_ip:
        return None
    
    # Parse current IP
    ip_match = re.search(r'ip address\s+([\d.]+)\s+([\d.]+)', current_config, re.IGNORECASE)
    
    if ip_match:
        current_ip = ip_match.group(1)
        current_mask = ip_match.group(2)
        
        if current_ip != expected_ip or current_mask != expected_mask:
            return {
                'type': 'ip address mismatch',
                'interface': interface,
                'current_ip': current_ip,
                'current_mask': current_mask,
                'expected_ip': expected_ip,
                'expected_mask': expected_mask
            }
    elif expected_ip:
        # IP is missing entirely
        return {
            'type': 'missing ip address',
            'interface': interface,
            'expected_ip': expected_ip,
            'expected_mask': expected_mask
        }
    
    return None


def parse_interface_output(tn, output, device_name):
    """Parse show ip interface brief output and compare against stable config"""
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

        # Check if interface is administratively down
        is_admin_down = 'administratively' in line_lower and 'down' in line_lower
        
        # Check if this interface should be up according to stable config
        should_be_up = should_interface_be_up(device_name, interface)
        
        if is_admin_down and should_be_up:
            # Get expected IP configuration
            expected_config = get_interface_ip_config(device_name, interface)
            
            ip_details = []
            if expected_config.get('ip_address'):
                ip_details.append(f"IPv4: {expected_config['ip_address']} {expected_config.get('subnet_mask', '')}")
            
            problems.append({
                'interface': interface,
                'status': 'administratively down',
                'should_be_up': True,
                'ip_details': " | ".join(ip_details) if ip_details else "IP configured",
                'protocol': 'down'
            })
        
        # Also check for IP address mismatches on interfaces that are up
        elif not is_admin_down:
            ip_mismatch = check_ip_address_mismatch(tn, device_name, interface)
            if ip_mismatch:
                problems.append(ip_mismatch)

    return problems


def fix_interface_shutdown(tn, interface):
    """Apply no shutdown to interface"""
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
    """Fix interface IP address"""
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
    """Verify interface is up after fix"""
    try:
        tn.write(b'\x03')
        time.sleep(0.1)
        tn.read_very_eager()
        tn.write(b'end\r\n')
        time.sleep(0.1)
        tn.read_very_eager()
        
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
    Run troubleshooting on a device

    Args:
        device_name: Name of the device
        tn: Open telnetlib.Telnet connection
        auto_prompt: If True, prompt user for fixes. If False, just detect issues.

    Returns:
        (problems, fixed_interfaces): Tuple of detected problems and fixed interfaces
    """
    output = get_interface_status(tn)
    if not output:
        return [], []

    problems = parse_interface_output(tn, output, device_name)
    if not problems:
        return [], []

    if not auto_prompt:
        return problems, []

    fixed_interfaces = []
    
    for problem in problems:
        problem_type = problem.get('type', 'administratively down')
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