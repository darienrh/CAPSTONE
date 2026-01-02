#!/usr/bin/env python3
"""fix_applier.py - Apply fixes to devices (extracted from runner.py and trees)"""

import time
from rich.prompt import Confirm

try:
    from utils.telnet_utils import apply_config_commands, send_command
except ImportError:
    from telnet_utils import apply_config_commands, send_command

# Import fix generators from trees
try:
    from detection.interface_tree import fix_interface_shutdown, fix_interface_ip, verify_interface_status
    from detection.eigrp_tree import get_eigrp_fix_commands, apply_eigrp_fixes, verify_eigrp_neighbors
    from detection.ospf_tree import get_ospf_fix_commands, apply_ospf_fixes, verify_ospf_neighbors
except ImportError:
    # Fallback for transition period
    try:
        from interface_tree import fix_interface_shutdown, fix_interface_ip, verify_interface_status
        from eigrp_tree import get_eigrp_fix_commands, apply_eigrp_fixes, verify_eigrp_neighbors
        from ospf_tree import get_ospf_fix_commands, apply_ospf_fixes, verify_ospf_neighbors
    except ImportError:
        pass


class FixApplier:
    """
    Applies fixes to devices
    """
    
    def __init__(self, config_manager=None, reporter=None):
        """
        Initialize fix applier
        
        Args:
            config_manager: ConfigManager instance
            reporter: Reporter instance
        """
        self.config_manager = config_manager
        self.reporter = reporter
        self.fix_results = []
    
    def apply_interface_fix(self, device_name, telnet_connection, problem, auto_approve=False):
        """
        Apply interface fix
        
        Args:
            device_name: Device name
            telnet_connection: Telnet connection
            problem: Problem dict
            auto_approve: If True, don't prompt user
        
        Returns:
            Fix result dict or None
        """
        problem_type = problem.get('type', 'shutdown')
        interface = problem['interface']
        
        if problem_type == 'ip address mismatch':
            if self.reporter:
                self.reporter.print_warning(
                    f"Device: {device_name} | Issue: {interface} IP mismatch"
                )
                self.reporter.print_info(f"  Current: {problem['current_ip']} {problem['current_mask']}")
                self.reporter.print_info(f"  Expected: {problem['expected_ip']} {problem['expected_mask']}")
            
            if auto_approve or Confirm.ask("Fix IP address?"):
                if fix_interface_ip(telnet_connection, interface, 
                                   problem['expected_ip'], problem['expected_mask']):
                    if self.reporter:
                        self.reporter.print_success(f"✔ Fixed IP on {interface}")
                    
                    time.sleep(1)
                    verification = verify_interface_status(telnet_connection, interface)
                    
                    return {
                        'device': device_name,
                        'commands': f"interface {interface}\nip address {problem['expected_ip']} {problem['expected_mask']}",
                        'verification': verification
                    }
        
        elif problem_type == 'missing ip address':
            if self.reporter:
                self.reporter.print_warning(f"Device: {device_name} | Issue: {interface} missing IP")
                self.reporter.print_info(f"  Expected: {problem['expected_ip']} {problem['expected_mask']}")
            
            if auto_approve or Confirm.ask("Configure IP address?"):
                if fix_interface_ip(telnet_connection, interface,
                                   problem['expected_ip'], problem['expected_mask']):
                    if self.reporter:
                        self.reporter.print_success(f"✔ Configured IP on {interface}")
                    
                    time.sleep(1)
                    verification = verify_interface_status(telnet_connection, interface)
                    
                    return {
                        'device': device_name,
                        'commands': f"interface {interface}\nip address {problem['expected_ip']} {problem['expected_mask']}",
                        'verification': verification
                    }
        
        else:  # administratively down
            if self.reporter:
                self.reporter.print_warning(f"Device: {device_name} | Issue: {interface} is Down")
            
            if auto_approve or Confirm.ask("Apply 'no shutdown'?"):
                if fix_interface_shutdown(telnet_connection, interface):
                    if self.reporter:
                        self.reporter.print_success(f"✔ Fixed {interface}")
                    
                    time.sleep(1)
                    verification = verify_interface_status(telnet_connection, interface)
                    
                    return {
                        'device': device_name,
                        'commands': f"interface {interface}\nno shutdown",
                        'verification': verification
                    }
        
        return None
    
    def apply_eigrp_fix(self, device_name, telnet_connection, problem, auto_approve=False):
        """
        Apply EIGRP fix
        
        Args:
            device_name: Device name
            telnet_connection: Telnet connection
            problem: Problem dict
            auto_approve: If True, don't prompt user
        
        Returns:
            Fix result dict or None
        """
        issue_type = problem['type']
        
        # Display issue
        if issue_type in ['eigrp hello timer mismatch', 'eigrp hold timer mismatch']:
            interface = problem.get('interface')
            current = problem.get('current')
            expected = problem.get('expected')
            timer_type = 'Hello' if 'hello' in issue_type else 'Hold'
            
            if self.reporter:
                self.reporter.print_warning(f"Device: {device_name} | Issue: {interface} {timer_type} timer")
                self.reporter.print_info(f"  Current: {current}s | Expected: {expected}s")
        else:
            if self.reporter:
                self.reporter.print_warning(f"Device: {device_name} | Issue: {issue_type}")
        
        # Get fix commands
        fix_commands = get_eigrp_fix_commands(issue_type, problem, device_name)
        
        if not fix_commands:
            if self.reporter:
                self.reporter.print_error("Manual intervention required")
            return None
        
        if auto_approve or Confirm.ask("Apply fix?"):
            if apply_eigrp_fixes(telnet_connection, fix_commands):
                if self.reporter:
                    self.reporter.print_success(f"✔ Fixed {issue_type}")
                
                time.sleep(2)
                verification = verify_eigrp_neighbors(telnet_connection)
                
                return {
                    'device': device_name,
                    'commands': '\n'.join(fix_commands),
                    'verification': verification
                }
        
        return None
    
    def apply_ospf_fix(self, device_name, telnet_connection, problem, auto_approve=False):
        """
        Apply OSPF fix
        
        Args:
            device_name: Device name
            telnet_connection: Telnet connection
            problem: Problem dict
            auto_approve: If True, don't prompt user
        
        Returns:
            Fix result dict or None
        """
        issue_type = problem['type']
        
        if self.reporter:
            self.reporter.print_warning(f"Device: {device_name} | Issue: {issue_type}")
        
        fix_commands = get_ospf_fix_commands(issue_type, problem, device_name)
        
        if not fix_commands:
            if self.reporter:
                self.reporter.print_error("Manual intervention required")
            return None
        
        if auto_approve or Confirm.ask("Apply fix?"):
            if apply_ospf_fixes(telnet_connection, fix_commands):
                if self.reporter:
                    self.reporter.print_success(f"✔ Fixed {issue_type}")
                
                time.sleep(2)
                verification = verify_ospf_neighbors(telnet_connection)
                
                return {
                    'device': device_name,
                    'commands': '\n'.join(fix_commands),
                    'verification': verification
                }
        
        return None
    
    def apply_all_fixes(self, detected_issues, device_connections, auto_approve_all=False):
        """
        Apply all fixes based on detected issues
        
        Args:
            detected_issues: Dict of detected issues from ProblemDetector
            device_connections: Dict mapping device names to telnet connections
            auto_approve_all: If True, apply all fixes without prompting
        
        Returns:
            List of fix results
        """
        self.fix_results = []
        
        # Apply interface fixes
        for device, problems in detected_issues.get('interfaces', {}).items():
            tn = device_connections.get(device)
            if not tn:
                continue
            
            for problem in problems:
                result = self.apply_interface_fix(device, tn, problem, auto_approve_all)
                if result:
                    self.fix_results.append(result)
        
        # Apply EIGRP fixes
        for device, problems in detected_issues.get('eigrp', {}).items():
            tn = device_connections.get(device)
            if not tn:
                continue
            
            for problem in problems:
                result = self.apply_eigrp_fix(device, tn, problem, auto_approve_all)
                if result:
                    self.fix_results.append(result)
        
        # Apply OSPF fixes
        for device, problems in detected_issues.get('ospf', {}).items():
            tn = device_connections.get(device)
            if not tn:
                continue
            
            for problem in problems:
                result = self.apply_ospf_fix(device, tn, problem, auto_approve_all)
                if result:
                    self.fix_results.append(result)
        
        return self.fix_results
    
    def get_fix_results(self):
        """
        Get all fix results from this session
        
        Returns:
            List of fix result dicts
        """
        return self.fix_results
    
    def clear_results(self):
        """Clear fix results"""
        self.fix_results = []


def apply_fixes_interactive(detected_issues, device_connections, config_manager=None, reporter=None):
    """
    Legacy function: Apply fixes with user interaction
    
    Args:
        detected_issues: Dict of detected issues
        device_connections: Dict of device connections
        config_manager: ConfigManager instance
        reporter: Reporter instance
    
    Returns:
        List of fix results
    """
    from rich.prompt import Prompt
    
    fix_mode = Prompt.ask(
        "\n[cyan]Apply fixes:[/cyan]",
        choices=["all", "one-by-one"],
        default="one-by-one"
    )
    
    auto_approve_all = (fix_mode == "all")
    
    applier = FixApplier(config_manager, reporter)
    return applier.apply_all_fixes(detected_issues, device_connections, auto_approve_all)