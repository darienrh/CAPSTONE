#!/usr/bin/env python3
"""
config_manager.py - Configuration management for network devices

Manages baseline configurations, provides expected values for validation,
and handles configuration versioning and comparison.
"""

import re
import difflib
from pathlib import Path
from datetime import datetime


CONFIG_DIR = Path.home() / "Capstone_AI" / "history" / "configs"

# Default values for protocol parameters
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
    Manages device configurations including baselines, versioning, and comparison.
    
    This class handles:
    - Loading and parsing baseline configurations
    - Providing expected values for validation
    - Saving configuration snapshots
    - Comparing configurations
    """
    
    def __init__(self, config_dir=None):
        """
        Initialize configuration manager.
        
        Args:
            config_dir: Directory for storing configurations (default: ~/Capstone_AI/history/configs)
        """
        self.config_dir = Path(config_dir) if config_dir else CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_cache = {}  # Cache for parsed baselines
        
    def load_latest_baseline(self):
        print(f"[DEBUG ConfigManager] Loading baseline from {self.config_dir}")
        
        if not self.config_dir.exists():
            print(f"[DEBUG ConfigManager] Config dir does not exist!")
            return {}
        
        config_files = list(self.config_dir.glob("config_stable*.txt"))
        print(f"[DEBUG ConfigManager] Found {len(config_files)} config files")
        
        if not config_files:
            return {}
        
        config_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        latest_config = config_files[0]
        print(f"[DEBUG ConfigManager] Using config file: {latest_config}")
        
        with open(latest_config, 'r') as f:
            content = f.read()
        
        print(f"[DEBUG ConfigManager] Config file size: {len(content)} bytes")
        
        devices = re.split(r'DEVICE:\s+(\w+)', content)
        print(f"[DEBUG ConfigManager] Split into {len(devices)} parts")
        
        baseline = {}
        # Process device configs (devices list has: ['', 'device1', 'config1', 'device2', 'config2', ...])
        for i in range(1, len(devices), 2):
            device_name = devices[i]
            device_config = devices[i + 1]
            print(f"[DEBUG ConfigManager] Parsing {device_name}, config length: {len(device_config)}")
            
            parsed = self._parse_device_config(device_name, device_config)
            baseline[device_name] = parsed
            
            # DEBUG: Print what was parsed for OSPF routers
            if device_name.upper() in ['R4', 'R5', 'R6']:
                print(f"[DEBUG ConfigManager] {device_name} OSPF networks: {parsed.get('ospf', {}).get('networks', [])}")
        
        self.baseline_cache = baseline
        print(f"[DEBUG ConfigManager] Loaded baseline for {len(baseline)} devices")
        return baseline
    
    def _parse_device_config(self, device_name, config):
        """
        Parse device configuration into structured format.
        
        Used by load_latest_baseline method to extract specific routing protocol 
        details and interface configurations from raw config text.
        
        Args:
            device_name: Name of the device
            config: Raw configuration text
        
        Returns:
            Dict: Parsed configuration sections including eigrp, ospf, interfaces
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
            info['eigrp']['networks'] = re.findall(r'^\s*network\s+([\d.]+)',
                                                eigrp_config, re.MULTILINE)
            info['eigrp']['passive_interfaces'] = re.findall(r'^\s*passive-interface\s+(\S+)',
                                                            eigrp_config, re.MULTILINE)
            info['eigrp']['is_stub'] = bool(re.search(r'^\s*eigrp stub',
                                                    eigrp_config, re.MULTILINE))
            k_match = re.search(r'^\s*metric weights\s+(\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+)',
                            eigrp_config, re.MULTILINE)
            info['eigrp']['k_values'] = k_match.group(1) if k_match else EXPECTED_DEFAULTS['eigrp_k_values']
        elif self._is_eigrp_router(device_name):
            info['eigrp']['as_number'] = '1'
            info['eigrp']['networks'] = []
            info['eigrp']['passive_interfaces'] = []
            info['eigrp']['is_stub'] = False
            info['eigrp']['k_values'] = EXPECTED_DEFAULTS['eigrp_k_values']
        
        ospf_match = re.search(r'router ospf (\d+)\n(.*?)(?=\n!|\nrouter |\ninterface |\Z)', config, re.DOTALL)
        if ospf_match:
            ospf_process = ospf_match.group(1)
            ospf_config = ospf_match.group(2)
            info['ospf']['process_id'] = ospf_process
            network_matches = re.findall(r'^\s*network\s+([\d.]+)\s+([\d.]+)\s+area\s+(\d+)',
                                        ospf_config, re.MULTILINE | re.IGNORECASE)
            info['ospf']['networks'] = [
                {'network': n[0], 'wildcard': n[1], 'area': n[2]} for n in network_matches
            ]
            info['ospf']['passive_interfaces'] = re.findall(r'^\s*passive-interface\s+(\S+)',
                                                            ospf_config, re.MULTILINE)
            rid_match = re.search(r'router-id\s+([\d.]+)', ospf_config)
            info['ospf']['router_id'] = (rid_match.group(1) if rid_match
                                        else EXPECTED_DEFAULTS['ospf_router_ids'].get(device_name))
            stub_areas = re.findall(r'^\s*area\s+(\d+)\s+stub', ospf_config, re.MULTILINE)
            info['ospf']['stub_areas'] = stub_areas
        elif self._is_ospf_router(device_name):
            info['ospf']['process_id'] = '10'
            info['ospf']['networks'] = []
            info['ospf']['passive_interfaces'] = []
            info['ospf']['router_id'] = EXPECTED_DEFAULTS['ospf_router_ids'].get(device_name)
            info['ospf']['stub_areas'] = []
        
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
            hello_match = re.search(r'ip ospf hello-interval\s+(\d+)', intf_config)
            dead_match = re.search(r'ip ospf dead-interval\s+(\d+)', intf_config)
            intf_info['ospf_hello'] = (int(hello_match.group(1)) if hello_match
                                    else EXPECTED_DEFAULTS['ospf_hello'])
            intf_info['ospf_dead'] = (int(dead_match.group(1)) if dead_match
                                    else EXPECTED_DEFAULTS['ospf_dead'])
            eigrp_hello_match = re.search(r'ip hello-interval eigrp\s+\d+\s+(\d+)', intf_config)
            eigrp_hold_match = re.search(r'ip hold-time eigrp\s+\d+\s+(\d+)', intf_config)
            intf_info['eigrp_hello'] = (int(eigrp_hello_match.group(1)) if eigrp_hello_match
                                    else EXPECTED_DEFAULTS['eigrp_hello'])
            intf_info['eigrp_hold'] = (int(eigrp_hold_match.group(1)) if eigrp_hold_match
                                    else EXPECTED_DEFAULTS['eigrp_hold'])
            
            ospf_area_match = re.search(r'ip ospf\s+\d+\s+area\s+\d+', intf_config)
            intf_info['ospf_enabled'] = bool(ospf_area_match)
            
            if not intf_info['ospf_enabled'] and info.get('ospf', {}).get('networks'):
                ip_addr = intf_info.get('ip_address')
                if ip_addr:
                    for net in info['ospf']['networks']:
                        if self._ip_matches_network(ip_addr, net['network'], net['wildcard']):
                            if intf_name not in info['ospf'].get('passive_interfaces', []):
                                intf_info['ospf_enabled'] = True
                            break
            
            info['interfaces'][intf_name] = intf_info
        return info
    
    def _ip_matches_network(self, ip_address, network, wildcard):
        try:
            ip_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(ip_address.split('.')))
            net_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(network.split('.')))
            wild_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(wildcard.split('.')))
            
            mask = ~wild_int & 0xFFFFFFFF
            return (ip_int & mask) == (net_int & mask)
        except (ValueError, IndexError, AttributeError):
            return False

    OSPF_INTERFACE_PARTICIPATION = {
        'R4': ['Serial0/0', 'Serial0/1'],
        'R5': ['Serial0/0', 'Serial0/1'],
        'R6': ['Serial0/0', 'Serial0/1', 'FastEthernet0/1'],
        'R7': ['FastEthernet0/0']
    }

    def should_interface_be_in_ospf(self, device_name, interface):
        return interface in self.OSPF_INTERFACE_PARTICIPATION.get(device_name, [])

    EIGRP_INTERFACE_PARTICIPATION = {
        'R1': ['FastEthernet0/0', 'FastEthernet1/0', 'FastEthernet2/0'],
        'R2': ['FastEthernet0/0', 'FastEthernet1/0'],
        'R3': ['FastEthernet0/0', 'FastEthernet1/0'],
        'R7': ['FastEthernet1/0']
    }

    def get_device_baseline(self, device_name):
        """
        Get baseline configuration for a specific device.
        
        If cache is empty, loads the latest baseline config automatically.
        
        Args:
            device_name: Name of the device
        
        Returns:
            Dict: Parsed configuration dict or empty dict if not found
        """
        if not self.baseline_cache:
            self.load_latest_baseline()
        return self.baseline_cache.get(device_name, {})
    
    def save_baseline(self, device_configs, tag="stable"):
        """
        Save device configurations as a baseline.
        
        Args:
            device_configs: Dict mapping device names to config text
            tag: Tag for this baseline (e.g., 'stable', 'pre-change')
        
        Returns:
            Path: Path to saved file or None on error
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
        Get next available filename with auto-increment.
        
        Args:
            prefix: Filename prefix
            extension: File extension
        
        Returns:
            Path: Path object for next filename
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
        Compare two configurations.
        
        Args:
            config1: First configuration text
            config2: Second configuration text
            ignore_comments: Whether to ignore comment lines
        
        Returns:
            Dict: Dictionary with 'unified_diff' and 'has_differences' keys
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
        """
        Get EIGRP AS number for device from baseline.
        
        Args:
            device_name: Device name
            
        Returns:
            str: AS number, defaults to '1'
        """
        baseline = self.get_device_baseline(device_name)
        return baseline.get('eigrp', {}).get('as_number', '1')
    
    def get_expected_k_values(self, device_name):
        """
        Get expected EIGRP K-values for device from baseline.
        
        Args:
            device_name: Device name
            
        Returns:
            str: K-values string, defaults to '0 1 0 1 0 0'
        """
        baseline = self.get_device_baseline(device_name)
        return baseline.get('eigrp', {}).get('k_values', EXPECTED_DEFAULTS['eigrp_k_values'])
    
    def get_ospf_process_id(self, device_name):
        """
        Get OSPF process ID for device from baseline.
        
        Args:
            device_name: Device name
            
        Returns:
            str: Process ID, defaults to '10'
        """
        baseline = self.get_device_baseline(device_name)
        return baseline.get('ospf', {}).get('process_id', '10')
    
    def should_interface_be_up(self, device_name, interface):
        """
        Check if interface should be up according to baseline.
        
        An interface should be up if it has an IP address configured
        and is not explicitly shut down in the baseline.
        
        Args:
            device_name: Device name
            interface: Interface name
            
        Returns:
            bool: True if interface should be up
        """
        baseline = self.get_device_baseline(device_name)
        intf_info = baseline.get('interfaces', {}).get(interface, {})
        has_ip = bool(intf_info.get('ip_address'))
        is_not_shutdown = not intf_info.get('shutdown', False)
        return has_ip and is_not_shutdown
    
    def get_interface_ip_config(self, device_name, interface):
        """
        Get interface IP configuration from baseline.
        
        Args:
            device_name: Device name
            interface: Interface name
            
        Returns:
            Dict: Interface config with ip_address, subnet_mask, etc.
        """
        baseline = self.get_device_baseline(device_name)
        return baseline.get('interfaces', {}).get(interface, {})
    
    @staticmethod
    def _is_eigrp_router(device_name):
        """
        Check if device should run EIGRP (internal method).
        
        Args:
            device_name: Device name
            
        Returns:
            bool: True if device is R1, R2, or R3
        """
        return device_name.upper() in ['R1', 'R2', 'R3', 'R7']
    
    @staticmethod
    def _is_ospf_router(device_name):
        """
        Check if device should run OSPF (internal method).
        
        Args:
            device_name: Device name
            
        Returns:
            bool: True if device is R4, R5, or R6
        """
        return device_name.upper() in ['R4', 'R5', 'R6', 'R7']
    
    @staticmethod
    def is_eigrp_router(device_name):
        """
        Check if device should run EIGRP (public method).
        
        Args:
            device_name: Device name
            
        Returns:
            bool: True if device is R1, R2, or R3
        """
        return ConfigManager._is_eigrp_router(device_name)
    
    @staticmethod
    def is_ospf_router(device_name):
        """
        Check if device should run OSPF (public method).
        
        Args:
            device_name: Device name
            
        Returns:
            bool: True if device is R4, R5, or R6
        """
        return ConfigManager._is_ospf_router(device_name)


# ============================================================================
# GLOBAL INSTANCE AND LEGACY COMPATIBILITY FUNCTIONS
# ============================================================================
# These provide backward compatibility for code that uses the old global
# function-based API instead of the class-based API.
# ============================================================================

# Create a global singleton instance
_global_config_manager = None

def _get_global_manager():
    """Get or create the global ConfigManager instance."""
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = ConfigManager()
    return _global_config_manager


# Legacy global functions that delegate to the singleton instance

def load_latest_stable_config():
    """
    Legacy function - loads latest stable config.
    
    Returns:
        bool: True if configs were loaded successfully
    """
    manager = _get_global_manager()
    baseline = manager.load_latest_baseline()
    return len(baseline) > 0


def get_device_baseline(device_name):
    """
    Legacy function - get device baseline.
    
    Args:
        device_name: Device name
        
    Returns:
        Dict: Parsed device configuration
    """
    manager = _get_global_manager()
    return manager.get_device_baseline(device_name)


def get_eigrp_as_number(device_name):
    """
    Legacy function - get EIGRP AS number.
    
    Args:
        device_name: Device name
        
    Returns:
        str: AS number
    """
    manager = _get_global_manager()
    return manager.get_eigrp_as_number(device_name)


def get_expected_k_values(device_name):
    """
    Legacy function - get expected EIGRP K-values.
    
    Args:
        device_name: Device name
        
    Returns:
        str: K-values string
    """
    manager = _get_global_manager()
    return manager.get_expected_k_values(device_name)


def get_ospf_process_id(device_name):
    """
    Legacy function - get OSPF process ID.
    
    Args:
        device_name: Device name
        
    Returns:
        str: Process ID
    """
    manager = _get_global_manager()
    return manager.get_ospf_process_id(device_name)


def should_interface_be_up(device_name, interface):
    """
    Legacy function - check if interface should be up.
    
    Args:
        device_name: Device name
        interface: Interface name
        
    Returns:
        bool: True if interface should be up
    """
    manager = _get_global_manager()
    return manager.should_interface_be_up(device_name, interface)


def get_interface_ip_config(device_name, interface):
    """
    Legacy function - get interface IP config.
    
    Args:
        device_name: Device name
        interface: Interface name
        
    Returns:
        Dict: Interface configuration
    """
    manager = _get_global_manager()
    return manager.get_interface_ip_config(device_name, interface)


def is_eigrp_router(device_name):
    """
    Legacy function - check if device runs EIGRP.
    
    Args:
        device_name: Device name
        
    Returns:
        bool: True if device is EIGRP router
    """
    return ConfigManager.is_eigrp_router(device_name)


def is_ospf_router(device_name):
    """
    Legacy function - check if device runs OSPF.
    
    Args:
        device_name: Device name
        
    Returns:
        bool: True if device is OSPF router
    """
    return ConfigManager.is_ospf_router(device_name)