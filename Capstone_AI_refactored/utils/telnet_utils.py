#!/usr/bin/env python3
"""telnet_utils.py - Telnet connection utilities extracted from runner.py and trees"""

import telnetlib
import time

def connect_device(console_port, timeout=3):
    """
    Connect to a device via telnet
    
    Args:
        console_port: Console port number
        timeout: Connection timeout in seconds
    
    Returns:
        Telnet connection object or None on failure
    """
    try:
        tn = telnetlib.Telnet('localhost', console_port, timeout=timeout)
        time.sleep(0.05)
        
        commands = [b'\r\n', b'\r\n', b'\x03', b'enable\r\n', b'\r\n']
        for cmd in commands:
            tn.write(cmd)
            time.sleep(0.05)
        
        return tn
    except Exception:
        return None


def close_device(tn):
    """
    Safely close a telnet connection
    
    Args:
        tn: Telnet connection object
    """
    if tn:
        try:
            tn.write(b'end\r\n')
            tn.close()
        except:
            pass


def clear_line_and_reset(tn):
    """
    Clear any partial commands and return to privileged exec mode
    
    Args:
        tn: Telnet connection object
    """
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


def send_commands(tn, commands, delay=0.3):
    """
    Send multiple commands to device
    
    Args:
        tn: Telnet connection object
        commands: List of command strings
        delay: Delay between commands in seconds
    
    Returns:
        True if successful, False otherwise
    """
    try:
        for cmd in commands:
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(delay)
            tn.read_very_eager()
        return True
    except:
        return False


def send_command(tn, command, wait_time=1):
    """
    Send a single command and return output
    
    Args:
        tn: Telnet connection object
        command: Command string
        wait_time: Time to wait for output
    
    Returns:
        Command output as string
    """
    try:
        clear_line_and_reset(tn)
        tn.write(command.encode('ascii') + b'\r\n')
        time.sleep(wait_time)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None


def enter_config_mode(tn):
    """
    Enter configuration mode
    
    Args:
        tn: Telnet connection object
    
    Returns:
        True if successful
    """
    try:
        clear_line_and_reset(tn)
        tn.write(b'configure terminal\r\n')
        time.sleep(0.3)
        tn.read_very_eager()
        return True
    except:
        return False


def exit_config_mode(tn):
    """
    Exit configuration mode
    
    Args:
        tn: Telnet connection object
    
    Returns:
        True if successful
    """
    try:
        tn.write(b'end\r\n')
        time.sleep(0.3)
        tn.read_very_eager()
        return True
    except:
        return False


def apply_config_commands(tn, commands):
    """
    Apply configuration commands (enters config mode, applies, exits)
    
    Args:
        tn: Telnet connection object
        commands: List of command strings
    
    Returns:
        True if successful
    """
    try:
        if not enter_config_mode(tn):
            return False
        
        for cmd in commands:
            if cmd.startswith('#'):  # Skip comments
                continue
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(0.3)
            tn.read_very_eager()
        
        return exit_config_mode(tn)
    except:
        return False


def get_running_config(tn):
    """
    Get full running configuration
    
    Args:
        tn: Telnet connection object
    
    Returns:
        Configuration text or None
    """
    try:
        clear_line_and_reset(tn)
        tn.write(b'terminal length 0\r\n')
        time.sleep(0.1)
        tn.read_very_eager()
        tn.write(b'show running-config\r\n')
        time.sleep(1)
        
        config_output = ""
        start_time = time.time()
        
        for _ in range(10):
            try:
                chunk = tn.read_very_eager().decode('ascii', errors='ignore')
                if chunk:
                    config_output += chunk
                    if len(config_output) > 300 and 'end' in chunk.lower():
                        break
                time.sleep(0.1)
                if time.time() - start_time > 8:
                    break
            except Exception:
                break
        
        return config_output.strip() if len(config_output) > 200 else None
    except:
        return None


def enable_debug(tn, debug_command):
    """
    Enable debugging
    
    Args:
        tn: Telnet connection object
        debug_command: Debug command (e.g., 'debug eigrp packets')
    
    Returns:
        True if successful
    """
    try:
        clear_line_and_reset(tn)
        tn.write(debug_command.encode('ascii') + b'\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except:
        return False


def disable_all_debug(tn):
    """
    Disable all debugging
    
    Args:
        tn: Telnet connection object
    
    Returns:
        True if successful
    """
    try:
        clear_line_and_reset(tn)
        tn.write(b'no debug all\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except:
        return False


def get_debug_output(tn, wait_time=5):
    """
    Gather debug output after waiting
    
    Args:
        tn: Telnet connection object
        wait_time: Time to wait for debug messages
    
    Returns:
        Debug output string
    """
    try:
        time.sleep(wait_time)
        tn.write(b'show logging\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except:
        return None