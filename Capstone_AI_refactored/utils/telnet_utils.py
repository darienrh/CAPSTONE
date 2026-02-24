#!/usr/bin/env python3
"""
telnet_utils.py - Telnet connection utilities extracted from runner.py and trees
Patched: Removed unstable sleep loops and replaced with stateful read_until prompt matching.
"""

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
    except Exception as e:
        return None

def close_device(tn):
    """
    Safely close a telnet connection
    """
    if tn:
        try:
            tn.write(b'end\r\n')
            tn.close()
        except Exception:
            pass

def clear_line_and_reset(tn):
    """
    Clear any partial commands and return to privileged exec mode using prompt matching
    """
    try:
        tn.write(b'\x03\r\n')
        tn.read_until(b'#', timeout=1)
        
        tn.write(b'end\r\n')
        tn.read_until(b'#', timeout=1)
        
        tn.write(b'\r\n')
        tn.read_until(b'#', timeout=1)
    except Exception:
        pass

def send_commands(tn, commands, delay=0.1):
    """
    Send multiple commands to device using prompt matching
    """
    try:
        for cmd in commands:
            tn.write(cmd.encode('ascii') + b'\r\n')
            # Wait until the router is ready for the next command
            tn.read_until(b'#', timeout=2)
            time.sleep(delay)
        return True
    except Exception:
        return False

def send_command(tn, command, wait_time=2):
    """
    Send a single command and return output using prompt matching
    """
    try:
        clear_line_and_reset(tn)
        tn.write(command.encode('ascii') + b'\r\n')
        
        # Read until the prompt comes back, proving command is finished
        output = tn.read_until(b'#', timeout=wait_time)
        return output.decode('ascii', errors='ignore')
    except Exception as e:
        return None

def enter_config_mode(tn):
    """
    Enter configuration mode
    """
    try:
        clear_line_and_reset(tn)
        tn.write(b'configure terminal\r\n')
        tn.read_until(b'#', timeout=2)
        return True
    except Exception:
        return False

def exit_config_mode(tn):
    """
    Exit configuration mode
    """
    try:
        tn.write(b'end\r\n')
        tn.read_until(b'#', timeout=2)
        return True
    except Exception:
        return False

def apply_config_commands(tn, commands):
    """
    Apply configuration commands (enters config mode, applies, exits)
    """
    try:
        if not enter_config_mode(tn):
            return False
        
        for cmd in commands:
            if cmd.startswith('#'):  # Skip comments
                continue
            tn.write(cmd.encode('ascii') + b'\r\n')
            tn.read_until(b'#', timeout=2)
        
        return exit_config_mode(tn)
    except Exception:
        return False

def get_running_config(tn):
    """
    Get full running configuration using robust prompt matching.
    Eliminates race conditions and partial file reads.
    """
    try:
        clear_line_and_reset(tn)
        
        # Set terminal length to 0 to avoid pagination
        tn.write(b'terminal length 0\r\n')
        tn.read_until(b'#', timeout=2)
        
        # Request the configuration
        tn.write(b'show running-config\r\n')
        
        # BUG FIX: Instead of looping and guessing with time.sleep(),
        # we tell Telnet to strictly wait until the router prompt ('#') 
        # is returned. This guarantees the entire config has been printed.
        config_bytes = tn.read_until(b'#', timeout=15)
        config_output = config_bytes.decode('ascii', errors='ignore')
        
        if not config_output or len(config_output) < 300:
            return None
            
        config_lower = config_output.lower()
        if 'building configuration' not in config_lower and 'current configuration' not in config_lower:
            return None
            
        return config_output.strip()
        
    except Exception as e:
        print(f"[DEBUG] Error getting running config: {e}")
        return None

def enable_debug(tn, debug_command):
    """
    Enable debugging
    """
    try:
        clear_line_and_reset(tn)
        tn.write(debug_command.encode('ascii') + b'\r\n')
        tn.read_until(b'#', timeout=2)
        return True
    except Exception:
        return False

def disable_all_debug(tn):
    """
    Disable all debugging
    """
    try:
        clear_line_and_reset(tn)
        tn.write(b'undebug all\r\n')
        tn.read_until(b'#', timeout=2)
        return True
    except Exception:
        return False

def get_debug_output(tn, wait_time=5):
    """
    Gather debug output after waiting
    """
    try:
        time.sleep(wait_time) # We actually want a sleep here to let debug packets accumulate
        tn.write(b'show logging\r\n')
        output = tn.read_until(b'#', timeout=5)
        return output.decode('ascii', errors='ignore')
    except Exception:
        return None
