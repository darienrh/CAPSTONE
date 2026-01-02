#!/usr/bin/env python3
"""config_manager.py - Enhanced configuration management (migrated from config_parser.py)"""

import re
import difflib
from pathlib import Path
from datetime import datetime


CONFIG_DIR = Path.home() / "Capstone_AI_refactored" / "history" / "configs"

# Default values
EXPECTED_DEFAULTS = {
    'eigrp_hello': 5,
    'eigrp_hold': 15,
    'ospf_hello': 10,
    'ospf_dead': 40,
    'eigrp_k_values': '0 1 0 1 0 0',
    'ospf_stub_areas': [],
    'ospf_router_ids': {
        'R4': '4.4.4.4',
        'R5': '5.5.5.5',
        'R6': '6.6.6.6'
    }
}


class ConfigManager:
    """
    Manages device configurations including baselines, versioning, and comparison
    """
    
    def __init__(self, config_dir=None):
        """
        Initialize configuration manager
        
        Args:
            config_dir: Directory for storing configurations (default: ~/history/configs)
        """
        self.config_dir = Path(config_dir) if config_dir else CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_cache = {}  # Cache for parsed baselines
        
    def load_latest_baseline(self):
        """
        Load the latest stable configuration baseline
        
        Returns:
            Dict mapping device names to parsed configurations, or empty dict
        """
        if not self.config_dir.exists():
            return {}
        
        config_files = list(self.config_dir.glob("config_stable*.txt"))
        if not config_files:
            return {}
        
        config_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        latest_config = config_files[0]
        
        with open(latest_config, 'r') as f:
            content = f.read()
        
        # Parse devices from content
        devices = re.split(r'DEVICE:\s+(\w+)', content)
        baseline = {}
        
        for i in range(1, len(devices), 2):
            device_name = devices[i]
            device_config = devices[i + 1]
            baseline[device_name] = self._parse_device_config(device_name, device_config)
        
        self.baseline_cache = baseline
        return baseline
    
    def _parse_device_config(self, device_name, config):
        """
        Parse device configuration into structured format
        
        Args:
            device_name: Name of the device
            config: Raw configuration text
        
        Returns:
            Dict with parsed configuration sections
        """
        info = {
            'hostname': device_name,
            'eigrp': {},
            'ospf': {},
            'interfaces': {}
        }
        
        # Parse EIGRP configuration
        eigrp_match = re.search(r'router eigrp (\d+)\n(.*?)(?=\n!|\nrouter |\ninterface |\Z)', 
                               config, re.DOTALL)
        if eigrp_match:
            eigrp_as = eigrp_match.group(1)
            eigrp_config = eigrp_match.group(2)
            
            info['eigrp']['as_number'] = eigrp_as
            info['eigrp']['networks'] = re.findall(r'network\s+([\d.]+)', eigrp_config)
            info['eigrp']['passive_interfaces'] = re.findall(r'passive-interface\s+(\S+)', eigrp_config)
            info['eigrp']['is_stub'] = bool(re.search(r'eigrp stub', eigrp_config))
            
            k_match = re.search(r'metric weights\s+(\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+)', eigrp_config)
            info['eigrp']['k_values'] = k_match.group(1) if k_match else EXPECTED_DEFAULTS['eigrp_k_values']
        elif self._is_eigrp_router(device_name):
            info['eigrp']['as_number'] = '1'
            info['eigrp']['networks'] = []
            info['eigrp']['passive_interfaces'] = []
            info['eigrp']['is_stub'] = False
            info['eigrp']['k_values'] = EXPECTED_DEFAULTS['eigrp_k_values']
        
        # Parse OSPF configuration
        ospf_match = re.search(r'router ospf (\d+)\n(.*?)(?=\n!|\nrouter |\ninterface |\Z)', 
                              config, re.DOTALL)
        if ospf_match:
            ospf_process = ospf_match.group(1)
            ospf_config = ospf_match.group(2)
            
            info['ospf']['process_id'] = ospf_process
            
            network_matches = re.findall(r'network\s+([\d.]+)\s+([\d.]+)\s+area\s+(\d+)', ospf_config)
            info['ospf']['networks'] = [
                {'network': n[0], 'wildcard': n[1], 'area': n[2]} for n in network_matches
            ]
            info['ospf']['passive_interfaces'] = re.findall(r'passive-interface\s+(\S+)', ospf_config)
            
            rid_match = re.search(r'router-id\s+([\d.]+)', ospf_config)
            info['ospf']['router_id'] = (rid_match.group(1) if rid_match 
                                        else EXPECTED_DEFAULTS['ospf_router_ids'].get(device_name))
            
            stub_areas = re.findall(r'area\s+(\d+)\s+stub', ospf_config)
            info['ospf']['stub_areas'] = stub_areas
        elif self._is_ospf_router(device_name):
            info['ospf']['process_id'] = '10'
            info['ospf']['networks'] = []
            info['ospf']['passive_interfaces'] = []
            info['ospf']['router_id'] = EXPECTED_DEFAULTS['ospf_router_ids'].get(device_name)
            info['ospf']['stub_areas'] = []
        
        # Parse interface configurations
        interface_sections = re.findall(
            r'interface\s+(\S+)\n(.*?)(?=\ninterface |\nrouter |\n!|\Z)', 
            config, re.DOTALL
        )
        
        for intf_name, intf_config in interface_sections:
            intf_info = {'name': intf_name}
            
            ip_match = re.search(r'ip address\s+([\d.]+)\s+([\d.]+)', intf_config)
            if ip_match:
                intf_info['ip_address'] = ip_match.group(1)
                intf_info['subnet_mask'] = ip_match.group(2)
            
            intf_info['shutdown'] = bool(re.search(r'^\s*shutdown\s*$', intf_config, re.MULTILINE))
            
            # OSPF timers
            hello_match = re.search(r'ip ospf hello-interval\s+(\d+)', intf_config)
            dead_match = re.search(r'ip ospf dead-interval\s+(\d+)', intf_config)
            intf_info['ospf_hello'] = (int(hello_match.group(1)) if hello_match 
                                      else EXPECTED_DEFAULTS['ospf_hello'])
            intf_info['ospf_dead'] = (int(dead_match.group(1)) if dead_match 
                                     else EXPECTED_DEFAULTS['ospf_dead'])
            
            # EIGRP timers
            eigrp_hello_match = re.search(r'ip hello-interval eigrp\s+\d+\s+(\d+)', intf_config)
            eigrp_hold_match = re.search(r'ip hold-time eigrp\s+\d+\s+(\d+)', intf_config)
            intf_info['eigrp_hello'] = (int(eigrp_hello_match.group(1)) if eigrp_hello_match 
                                       else EXPECTED_DEFAULTS['eigrp_hello'])
            intf_info['eigrp_hold'] = (int(eigrp_hold_match.group(1)) if eigrp_hold_match 
                                      else EXPECTED_DEFAULTS['eigrp_hold'])
            
            info['interfaces'][intf_name] = intf_info
        
        return info
    
    def get_device_baseline(self, device_name):
        """
        Get baseline configuration for a specific device
        
        Args:
            device_name: Name of the device
        
        Returns:
            Parsed configuration dict or empty dict
        """
        if not self.baseline_cache:
            self.load_latest_baseline()
        return self.baseline_cache.get(device_name, {})
    
    def save_baseline(self, device_configs, tag="stable"):
        """
        Save device configurations as a baseline
        
        Args:
            device_configs: Dict mapping device names to config text
            tag: Tag for this baseline (e.g., 'stable', 'pre-change')
        
        Returns:
            Path to saved file or None on error
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            filename = self._get_next_filename(f"config_{tag}")
            
            with open(filename, 'w') as f:
                f.write(f"{tag.title()} Configurations Timestamp: {timestamp}\n")
                f.write("=" * 80 + "\n\n")
                f.write(f"{tag.upper()} ROUTER CONFIGURATIONS\n")
                f.write("=" * 80 + "\n\n")
                
                if not device_configs:
                    f.write("No configurations were saved.\n")
                else:
                    for device_name, config in device_configs.items():
                        f.write(f"DEVICE: {device_name}\n")
                        f.write("=" * 60 + "\n")
                        f.write(config + "\n\n")
            
            # Invalidate cache so next load gets new baseline
            self.baseline_cache = {}
            
            return filename
        except Exception as e:
            print(f"Error saving baseline: {e}")
            return None
    
    def _get_next_filename(self, prefix, extension="txt"):
        """
        Get next available filename with auto-increment
        
        Args:
            prefix: Filename prefix
            extension: File extension
        
        Returns:
            Path object for next filename
        """
        self.config_dir.mkdir(parents=True, exist_ok=True)
        existing_files = list(self.config_dir.glob(f"{prefix}*.{extension}"))
        
        if not existing_files:
            return self.config_dir / f"{prefix}.{extension}"
        
        max_num = 0
        for file in existing_files:
            match = re.match(f'{prefix}(\\d*)\\.{extension}', file.name)
            if match:
                num_str = match.group(1)
                current_num = 0 if num_str == '' else int(num_str)
                max_num = max(max_num, current_num)
        
        next_num = max_num + 10
        return self.config_dir / f"{prefix}{next_num}.{extension}"
    
    def compare_configs(self, config1, config2, ignore_comments=True):
        """
        Compare two configurations
        
        Args:
            config1: First configuration text
            config2: Second configuration text
            ignore_comments: Whether to ignore comment lines
        
        Returns:
            Dict with differences
        """
        if ignore_comments:
            config1 = '\n'.join(line for line in config1.split('\n') 
                               if not line.strip().startswith('!'))
            config2 = '\n'.join(line for line in config2.split('\n') 
                               if not line.strip().startswith('!'))
        
        diff = list(difflib.unified_diff(
            config1.splitlines(keepends=True),
            config2.splitlines(keepends=True),
            lineterm=''
        ))
        
        return {
            'unified_diff': ''.join(diff),
            'has_differences': len(diff) > 0
        }
    
    # Helper methods for backward compatibility with old code
    
    def get_eigrp_as_number(self, device_name):
        """Get EIGRP AS number for device"""
        baseline = self.get_device_baseline(device_name)
        return baseline.get('eigrp', {}).get('as_number', '1')
    
    def get_expected_k_values(self, device_name):
        """Get expected EIGRP K-values for device"""
        baseline = self.get_device_baseline(device_name)
        return baseline.get('eigrp', {}).get('k_values', EXPECTED_DEFAULTS['eigrp_k_values'])
    
    def get_ospf_process_id(self, device_name):
        """Get OSPF process ID for device"""
        baseline = self.get_device_baseline(device_name)
        return baseline.get('ospf', {}).get('process_id', '10')
    
    def should_interface_be_up(self, device_name, interface):
        """Check if interface should be up according to baseline"""
        baseline = self.get_device_baseline(device_name)
        intf_info = baseline.get('interfaces', {}).get(interface, {})
        has_ip = bool(intf_info.get('ip_address'))
        is_not_shutdown = not intf_info.get('shutdown', False)
        return has_ip and is_not_shutdown
    
    def get_interface_ip_config(self, device_name, interface):
        """Get interface IP configuration from baseline"""
        baseline = self.get_device_baseline(device_name)
        return baseline.get('interfaces', {}).get(interface, {})
    
    @staticmethod
    def _is_eigrp_router(device_name):
        """Check if device should run EIGRP"""
        return device_name.upper() in ['R1', 'R2', 'R3']
    
    @staticmethod
    def _is_ospf_router(device_name):
        """Check if device should run OSPF"""
        return device_name.upper() in ['R4', 'R5', 'R6']
    
    @staticmethod
    def is_eigrp_router(device_name):
        """Public method: Check if device should run EIGRP"""
        return ConfigManager._is_eigrp_router(device_name)
    
    @staticmethod
    def is_ospf_router(device_name):
        """Public method: Check if device should run OSPF"""
        return ConfigManager._is_ospf_router(device_name)


# Legacy global functions for backward compatibility
BASELINE = {}

def load_latest_stable_config():
    """Legacy function - loads latest stable config into global BASELINE"""
    global BASELINE
    manager = ConfigManager()
    BASELINE = manager.load_latest_baseline()
    return len(BASELINE) > 0

def get_device_baseline(device_name):
    """Legacy function"""
    if not BASELINE:
        load_latest_stable_config()
    return BASELINE.get(device_name, {})

def get_eigrp_as_number(device_name):
    """Legacy function"""
    baseline = get_device_baseline(device_name)
    return baseline.get('eigrp', {}).get('as_number', '1')

def get_expected_k_values(device_name):
    """Legacy function"""
    baseline = get_device_baseline(device_name)
    return baseline.get('eigrp', {}).get('k_values', EXPECTED_DEFAULTS['eigrp_k_values'])

def get_ospf_process_id(device_name):
    """Legacy function"""
    baseline = get_device_baseline(device_name)
    return baseline.get('ospf', {}).get('process_id', '10')

def should_interface_be_up(device_name, interface):
    """Legacy function"""
    baseline = get_device_baseline(device_name)
    intf_info = baseline.get('interfaces', {}).get(interface, {})
    has_ip = bool(intf_info.get('ip_address'))
    is_not_shutdown = not intf_info.get('shutdown', False)
    return has_ip and is_not_shutdown

def get_interface_ip_config(device_name, interface):
    """Legacy function"""
    baseline = get_device_baseline(device_name)
    return baseline.get('interfaces', {}).get(interface, {})

def is_eigrp_router(device_name):
    """Legacy function"""
    return ConfigManager.is_eigrp_router(device_name)

def is_ospf_router(device_name):
    """Legacy function"""
    return ConfigManager.is_ospf_router(device_name)