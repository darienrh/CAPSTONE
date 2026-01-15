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
    Get full running configuration with improved reliability
    
    Args:
        tn: Telnet connection object
    
    Returns:
        Configuration text or None
    """
    try:
        clear_line_and_reset(tn)
        
        # Set terminal length to 0 to avoid pagination
        tn.write(b'terminal length 0\r\n')
        time.sleep(0.2)
        tn.read_very_eager()
        
        # Send show running-config command
        tn.write(b'show running-config\r\n')
        time.sleep(0.5)  # Initial wait for command to start executing
        
        config_output = ""
        start_time = time.time()
        no_data_count = 0
        max_no_data = 5  # Allow 5 consecutive empty reads before giving up
        
        # Read config with improved timeout and iteration count
        for iteration in range(50):  # Increased from 10 to 50 iterations
            try:
                chunk = tn.read_very_eager().decode('ascii', errors='ignore')
                
                if chunk:
                    config_output += chunk
                    no_data_count = 0  # Reset counter when we get data
                    
                    # Check for config end markers
                    # Look for "end" followed by prompt (e.g., "R1#" or "Router#")
                    if len(config_output) > 500:
                        # Check last 200 characters for end marker
                        tail = config_output[-200:].lower()
                        if 'end' in tail and '#' in tail:
                            # Found end marker, wait a bit more to ensure we got everything
                            time.sleep(0.3)
                            final_chunk = tn.read_very_eager().decode('ascii', errors='ignore')
                            if final_chunk:
                                config_output += final_chunk
                            break
                else:
                    no_data_count += 1
                    if no_data_count >= max_no_data:
                        # No data for several iterations, likely done
                        if len(config_output) > 500:
                            break
                
                # Sleep between reads
                time.sleep(0.15)  # Slightly longer sleep for more reliable reading
                
                # Overall timeout check (increased to 20 seconds)
                if time.time() - start_time > 20:
                    break
                    
            except Exception as e:
                # On error, if we have substantial config, return it
                if len(config_output) > 500:
                    break
                else:
                    raise
        
        # Validate we got a complete config
        if len(config_output) < 300:
            # Config too short, likely incomplete
            return None
        
        # Check for basic config markers
        config_lower = config_output.lower()
        if 'building configuration' not in config_lower and 'current configuration' not in config_lower:
            # Doesn't look like a valid config
            return None
        
        return config_output.strip()
        
    except Exception as e:
        print(f"[DEBUG] Error getting running config: {e}")
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