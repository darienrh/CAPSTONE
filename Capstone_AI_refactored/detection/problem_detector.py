#!/usr/bin/env python3
"""problem_detector.py - Unified problem detection coordinator"""

import concurrent.futures
from threading import Lock
from datetime import datetime

# Import detection trees (will be refactored to use relative imports)
try:
    from detection.interface_tree import troubleshoot_device as troubleshoot_interfaces
    from detection.eigrp_tree import troubleshoot_eigrp
    from detection.ospf_tree import troubleshoot_ospf
except ImportError:
    # Fallback for transition period
    try:
        from interface_tree import troubleshoot_device as troubleshoot_interfaces
        from eigrp_tree import troubleshoot_eigrp
        from ospf_tree import troubleshoot_ospf
    except ImportError:
        pass

# Import config manager
try:
    from core.config_manager import ConfigManager
except ImportError:
    from config_parser import is_eigrp_router, is_ospf_router
    ConfigManager = None


class ProblemDetector:
    """
    Coordinates all detection modules and provides unified interface
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize problem detector
        
        Args:
            config_manager: ConfigManager instance (optional)
        """
        self.config_manager = config_manager if config_manager else (
            ConfigManager() if ConfigManager else None
        )
        self.router_type_cache = {}
    
    def get_router_type(self, device_name):
        """
        Determine what protocols a router should run
        
        Args:
            device_name: Name of device
        
        Returns:
            Tuple of (is_eigrp, is_ospf)
        """
        if device_name in self.router_type_cache:
            return self.router_type_cache[device_name]
        
        if self.config_manager:
            is_eigrp = self.config_manager.is_eigrp_router(device_name)
            is_ospf = self.config_manager.is_ospf_router(device_name)
        else:
            # Fallback
            is_eigrp = device_name.upper() in ['R1', 'R2', 'R3']
            is_ospf = device_name.upper() in ['R4', 'R5', 'R6']
        
        result = (is_eigrp, is_ospf)
        self.router_type_cache[device_name] = result
        return result
    
    def scan_device(self, device_name, telnet_connection, scan_options=None):
        """
        Comprehensive scan of a single device
        
        Args:
            device_name: Name of device
            telnet_connection: Active telnet connection
            scan_options: Dict specifying what to scan
                Example: {
                    'check_interfaces': True,
                    'check_eigrp': True,
                    'check_ospf': True
                }
        
        Returns:
            Dict with detected problems:
                {
                    'device': 'R1',
                    'scan_time': '2024-01-02 10:30:00',
                    'problems': {
                        'interfaces': [...],
                        'eigrp': [...],
                        'ospf': [...]
                    }
                }
        """
        if scan_options is None:
            scan_options = {
                'check_interfaces': True,
                'check_eigrp': True,
                'check_ospf': True
            }
        
        problems = {
            'interfaces': [],
            'eigrp': [],
            'ospf': []
        }
        
        # Check interfaces
        if scan_options.get('check_interfaces', True):
            try:
                intf_problems, _ = troubleshoot_interfaces(
                    device_name, 
                    telnet_connection, 
                    auto_prompt=False
                )
                if intf_problems:
                    problems['interfaces'] = intf_problems
            except Exception as e:
                print(f"Error checking interfaces on {device_name}: {e}")
        
        # Check EIGRP
        is_eigrp, is_ospf = self.get_router_type(device_name)
        
        if scan_options.get('check_eigrp', True) and is_eigrp:
            try:
                eigrp_problems, _ = troubleshoot_eigrp(
                    device_name,
                    telnet_connection,
                    auto_prompt=False
                )
                if eigrp_problems:
                    problems['eigrp'] = eigrp_problems
            except Exception as e:
                print(f"Error checking EIGRP on {device_name}: {e}")
        
        # Check OSPF
        if scan_options.get('check_ospf', True) and is_ospf:
            try:
                ospf_problems, _ = troubleshoot_ospf(
                    device_name,
                    telnet_connection,
                    auto_prompt=False
                )
                if ospf_problems:
                    problems['ospf'] = ospf_problems
            except Exception as e:
                print(f"Error checking OSPF on {device_name}: {e}")
        
        return {
            'device': device_name,
            'scan_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'problems': problems
        }
    
    def scan_single_device_thread_safe(self, device_name, telnet_connection, 
                                       scan_options, detected_issues, lock):
        """
        Thread-safe device scanning (for parallel execution)
        
        Args:
            device_name: Name of device
            telnet_connection: Telnet connection
            scan_options: Scan options dict
            detected_issues: Shared dict to store results
            lock: Thread lock for synchronization
        """
        try:
            result = self.scan_device(device_name, telnet_connection, scan_options)
            
            with lock:
                for category, problems in result['problems'].items():
                    if problems:
                        detected_issues[category][device_name] = problems
        except Exception as e:
            print(f"Error scanning {device_name}: {e}")
    
    def scan_all_devices(self, device_connections, scan_options=None, parallel=True):
        """
        Scan multiple devices
        
        Args:
            device_connections: Dict mapping device names to telnet connections
            scan_options: Scan options dict
            parallel: Whether to scan in parallel
        
        Returns:
            Dict with detected issues organized by category:
                {
                    'interfaces': {'R1': [...], 'R2': [...]},
                    'eigrp': {'R1': [...], 'R2': [...]},
                    'ospf': {'R4': [...], 'R5': [...]}
                }
        """
        detected_issues = {'interfaces': {}, 'eigrp': {}, 'ospf': {}}
        
        if not parallel or len(device_connections) == 1:
            # Sequential scanning
            for device_name, tn in device_connections.items():
                result = self.scan_device(device_name, tn, scan_options)
                for category, problems in result['problems'].items():
                    if problems:
                        detected_issues[category][device_name] = problems
        else:
            # Parallel scanning
            lock = Lock()
            max_workers = min(6, len(device_connections))
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for device_name, tn in device_connections.items():
                    future = executor.submit(
                        self.scan_single_device_thread_safe,
                        device_name, tn, scan_options, detected_issues, lock
                    )
                    futures.append(future)
                
                # Wait for all to complete
                concurrent.futures.wait(futures)
        
        return detected_issues
    
    def prioritize_problems(self, problem_list, strategy="severity"):
        """
        Prioritize detected problems
        
        Args:
            problem_list: List of problem dicts
            strategy: Prioritization strategy
        
        Returns:
            Reordered problem list with priority scores
        """
        # Simple severity-based prioritization
        severity_map = {
            'interface_down': 10,
            'ip address mismatch': 9,
            'missing ip address': 9,
            'as mismatch': 10,
            'router id mismatch': 8,
            'k-value mismatch': 7,
            'hello interval mismatch': 6,
            'dead interval mismatch': 6,
            'stub configuration': 7,
            'passive interface': 5,
            'missing network': 6,
            'extra network': 4,
            'process id mismatch': 8
        }
        
        for problem in problem_list:
            problem_type = problem.get('type', 'unknown')
            problem['priority'] = severity_map.get(problem_type, 5)
        
        return sorted(problem_list, key=lambda x: x.get('priority', 5), reverse=True)
    
    def correlate_problems(self, detected_issues):
        """
        Find correlations between problems
        
        Args:
            detected_issues: Dict of detected issues
        
        Returns:
            List of problem correlations
        """
        correlations = []
        
        # Example: If interface is down and EIGRP neighbor is missing, they're related
        for device in detected_issues.get('interfaces', {}):
            interface_problems = detected_issues['interfaces'].get(device, [])
            eigrp_problems = detected_issues.get('eigrp', {}).get(device, [])
            
            down_interfaces = [p['interface'] for p in interface_problems 
                             if p.get('status') == 'administratively down']
            
            if down_interfaces and eigrp_problems:
                correlations.append({
                    'device': device,
                    'root_problem': f"Interfaces down: {', '.join(down_interfaces)}",
                    'correlated_problems': [f"EIGRP issues: {len(eigrp_problems)} problems"],
                    'correlation_strength': 0.8
                })
        
        return correlations
    
    def calculate_health_score(self, detected_issues):
        """
        Calculate overall network health score
        
        Args:
            detected_issues: Dict of detected issues
        
        Returns:
            Health score (0-100)
        """
        total_problems = 0
        
        for category in detected_issues.values():
            for device_problems in category.values():
                total_problems += len(device_problems)
        
        # Simple scoring: start at 100, subtract 5 points per problem
        score = max(0, 100 - (total_problems * 5))
        return score