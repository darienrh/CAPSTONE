#!/usr/bin/env python3
"""
Interface troubleshooting decision tree - Uses connections managed by runner
"""

import warnings
warnings.filterwarnings('ignore')

import time


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
    """Get interface status from device using existing connection"""
    try:
        clear_line_and_reset(tn)

        tn.write(b'show ip interface brief\r\n')
        time.sleep(1.5)

        output = tn.read_very_eager().decode('ascii', errors='ignore')

        if not output or len(output) < 50:
            print(f"Warning: Little or no output received (length: {len(output)})")
            return None

        return output
    except Exception as e:
        print(f"Error getting interface status: {e}")
        return None


def parse_interface_output(output):
    """Parse show ip interface brief output and find problems"""
    problems = []

    lines = output.split('\n')

    for line in lines:
        if not line.strip():
            continue

        parts = line.split()

        if len(parts) < 5:
            continue

        if not parts[0].startswith(('FastEthernet', 'GigabitEthernet', 'Ethernet', 'Serial')):
            continue

        interface = parts[0]
        line_lower = line.lower()

        if 'administratively' in line_lower and 'down' in line_lower:
            for i in range(len(parts) - 1):
                if parts[i].lower() == 'administratively' and parts[i+1].lower() == 'down':
                    problems.append({
                        'interface': interface,
                        'status': 'administratively down',
                        'protocol': parts[-1].lower()
                    })
                    break

    return problems


def fix_interface(tn, interface):
    """Apply no shutdown to interface using existing connection"""
    try:
        clear_line_and_reset(tn)

        commands = [
            "configure terminal",
            f"interface {interface}",
            "no shutdown",
            "end"
        ]

        for cmd in commands:
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(0.2)
            tn.read_very_eager()

        return True
    except Exception as e:
        print(f"Error fixing interface: {e}")
        return False


def troubleshoot_device(device_name, tn, auto_prompt=True):
    """
    Run troubleshooting on a device using provided connection

    Args:
        device_name: Name of the device
        tn: Open telnetlib.Telnet connection (managed by runner)
        auto_prompt: If True, prompt user for fixes. If False, just detect issues.

    Returns:
        (problems, fixed_interfaces): Tuple of detected problems and fixed interfaces
    """
    print(f"\nDiagnosing {device_name}...")
    print("-" * 60)

    # Get interface status
    output = get_interface_status(tn)

    if not output:
        print(f"Failed to get interface status from {device_name}")
        return [], []

    # Parse for problems
    problems = parse_interface_output(output)

    if not problems:
        print(f"No interface problems detected on {device_name}")
        return [], []

    # Report problems
    print(f"Found {len(problems)} interface problem(s):")
    for problem in problems:
        interface = problem['interface']
        print(f"  - {interface}: {problem['status']}")

    if not auto_prompt:
        return problems, []

    # Prompt and fix
    fixed_interfaces = []

    for problem in problems:
        interface = problem['interface']
        print(f"\nProblem: {device_name} {interface} administratively down")

        response = input("Apply fixes? (Y/n): ").strip().lower()

        if response == 'n':
            print("Skipping fix")
            continue

        print(f"Applying no shutdown to {interface}...")

        if fix_interface(tn, interface):
            print(f"Fix applied to {interface}")
            fixed_interfaces.append(interface)
        else:
            print(f"Failed to fix {interface}")

    return problems, fixed_interfaces
