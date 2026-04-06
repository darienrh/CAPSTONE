#!/usr/bin/env python3
"""problem_detector.py - Unified problem detection coordinator"""

import concurrent.futures
from threading import Lock
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

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

class Problem:
    def __init__(self, problem_dict):
        self.type = problem_dict.get('type')
        self.category = problem_dict.get('category')
        self.device = problem_dict.get('device')
        self.severity = problem_dict.get('severity', 'medium')
        self.confidence = problem_dict.get('confidence', 0.8)
        self.raw_data = problem_dict
    
    def extract_symptoms(self) -> List[str]:
        """Extract AI-readable symptoms from problem"""
        symptoms = []
        if self.type:
            symptoms.append(self.type)
        if 'interface' in self.raw_data:
            symptoms.append(f"affects_{self.raw_data['interface']}")
        if 'expected' in self.raw_data and 'current' in self.raw_data:
            symptoms.append('config_mismatch')
        return symptoms
    
    def to_ai_format(self) -> Dict:
        """Convert to format suitable for inference engine"""
        return {
            'type': self.type,
            'category': self.category,
            'device': self.device,
            'symptoms': self.extract_symptoms(),
            'severity': self.severity,
            'confidence': self.confidence,
            'context': {k: v for k, v in self.raw_data.items() 
                       if k not in ['type', 'category', 'device']}
        }


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
        from utils.telnet_utils import get_running_config
        
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
        
        running_config = get_running_config(telnet_connection)
        if not running_config:
            print(f"Error: Could not retrieve running config for {device_name}")
            return {
                'device': device_name,
                'scan_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'problems': problems
            }
        
        if scan_options.get('check_interfaces', True):
            try:
                from detection.interface_tree import (
                    parse_interfaces_from_config,
                    collect_interface_diagnostics,
                    parse_interface_output
                )
                
                intf_problems = parse_interfaces_from_config(running_config, device_name)
                if intf_problems:
                    problems['interfaces'] = intf_problems
                
                interface_diagnostics = collect_interface_diagnostics(telnet_connection)
                
                if interface_diagnostics['show_interfaces']:
                    additional_problems = parse_interface_output(
                        telnet_connection,
                        interface_diagnostics['show_interfaces'],
                        device_name
                    )
                    for prob in additional_problems:
                        if prob not in problems['interfaces']:
                            problems['interfaces'].append(prob)
                
            except Exception as e:
                print(f"Error checking interfaces on {device_name}: {e}")
        
        is_eigrp, is_ospf = self.get_router_type(device_name)
        
        if scan_options.get('check_eigrp', True) and is_eigrp:
            try:
                from detection.eigrp_tree import (
                    check_as_mismatch, check_stub_configuration, check_passive_interfaces,
                    check_metric_weights, check_network_statements, check_eigrp_interface_timers,
                    check_eigrp_interface_participation, get_eigrp_neighbors  # Add this import
                )
                eigrp_problems = []
                as_issue = check_as_mismatch(running_config, device_name, self.config_manager)
                if as_issue:
                    eigrp_problems.append(as_issue)
                
                stub_issue = check_stub_configuration(running_config, device_name, self.config_manager)
                if stub_issue:
                    eigrp_problems.append(stub_issue)
                
                passive_intfs = check_passive_interfaces(running_config, device_name, self.config_manager)
                if passive_intfs:
                    eigrp_problems.extend(passive_intfs)
                
                k_values = check_metric_weights(running_config, device_name, self.config_manager)
                if k_values:
                    eigrp_problems.append(k_values)
                
                network_issues = check_network_statements(running_config, device_name, self.config_manager)
                if network_issues:
                    eigrp_problems.extend(network_issues)
                
                timer_issues = check_eigrp_interface_timers(running_config, device_name, self.config_manager)
                if timer_issues:
                    eigrp_problems.extend(timer_issues)
                
                participation_issues = check_eigrp_interface_participation(running_config, device_name, self.config_manager)
                if participation_issues:
                    eigrp_problems.extend(participation_issues)
                
                neighbor_output = get_eigrp_neighbors(telnet_connection)
                if eigrp_problems:
                    problems['eigrp'] = eigrp_problems
            except Exception as e:
                print(f"Error checking EIGRP on {device_name}: {e}")
        
        if scan_options.get('check_ospf', True) and is_ospf:
            try:
                from detection.ospf_tree import (
                    check_process_id_mismatch, check_passive_interfaces as check_ospf_passive,
                    check_stub_config, check_network_statements as check_ospf_networks,
                    check_ospf_enabled_interfaces, check_interface_timers,
                    check_area_assignments, check_router_id_conflicts, get_ospf_neighbors
                )
                
                ospf_problems = []
                
                process_issue = check_process_id_mismatch(running_config, device_name, self.config_manager)
                if process_issue:
                    ospf_problems.append(process_issue)
                
                passive_intfs = check_ospf_passive(running_config, device_name, self.config_manager)
                if passive_intfs:
                    ospf_problems.extend(passive_intfs)
                
                stub_issues = check_stub_config(running_config, device_name, self.config_manager)
                if stub_issues:
                    ospf_problems.extend(stub_issues)
                
                network_issues = check_ospf_networks(running_config, device_name, self.config_manager)
                if network_issues:
                    ospf_problems.extend(network_issues)
                
                ospf_participation_issues = check_ospf_enabled_interfaces(running_config, device_name, self.config_manager)
                if ospf_participation_issues:
                    ospf_problems.extend(ospf_participation_issues)
                
                timer_issues = check_interface_timers(running_config, device_name, self.config_manager)
                if timer_issues:
                    ospf_problems.extend(timer_issues)
                
                area_issues = check_area_assignments(running_config, device_name, self.config_manager)
                if area_issues:
                    ospf_problems.extend(area_issues)
                
                rid_issues = check_router_id_conflicts(running_config, device_name, self.config_manager)
                if rid_issues:
                    ospf_problems.extend(rid_issues)
                
                neighbor_output = get_ospf_neighbors(telnet_connection)
                
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
        detected_issues = {'interfaces': {}, 'eigrp': {}, 'ospf': {}}
        
        if not parallel or len(device_connections) == 1:
            for device_name, tn in device_connections.items():
                result = self.scan_device(device_name, tn, scan_options)
                for category, problems in result['problems'].items():
                    if problems:
                        detected_issues[category][device_name] = problems
        else:
            lock = Lock()
            max_workers = min(len(device_connections), 8)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for device_name, tn in device_connections.items():
                    future = executor.submit(
                        self.scan_single_device_thread_safe,
                        device_name, tn, scan_options, detected_issues, lock
                    )
                    futures.append(future)
                
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
