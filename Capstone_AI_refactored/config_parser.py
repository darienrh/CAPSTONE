#!/usr/bin/env python3
"""config_parser.py"""

import re
from pathlib import Path

CONFIG_DIR = Path.home() / "history" / "configs"
BASELINE = {}

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

def load_latest_stable_config():
    global BASELINE
    
    if not CONFIG_DIR.exists():
        return False
    
    config_files = list(CONFIG_DIR.glob("config_stable*.txt"))
    if not config_files:
        return False
    
    config_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    latest_config = config_files[0]
    
    with open(latest_config, 'r') as f:
        content = f.read()
    
    devices = re.split(r'DEVICE:\s+(\w+)', content)
    
    for i in range(1, len(devices), 2):
        device_name = devices[i]
        device_config = devices[i + 1]
        
        BASELINE[device_name] = parse_device_config(device_name, device_config)
    
    return True

def parse_device_config(device_name, config):
    info = {
        'hostname': device_name,
        'eigrp': {},
        'ospf': {},
        'interfaces': {}
    }
    
    eigrp_match = re.search(r'router eigrp (\d+)\n(.*?)(?=\n!|\nrouter |\ninterface |\Z)', config, re.DOTALL)
    if eigrp_match:
        eigrp_as = eigrp_match.group(1)
        eigrp_config = eigrp_match.group(2)
        
        info['eigrp']['as_number'] = eigrp_as
        info['eigrp']['networks'] = re.findall(r'network\s+([\d.]+)', eigrp_config)
        info['eigrp']['passive_interfaces'] = re.findall(r'passive-interface\s+(\S+)', eigrp_config)
        info['eigrp']['is_stub'] = bool(re.search(r'eigrp stub', eigrp_config))
        
        k_match = re.search(r'metric weights\s+(\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+)', eigrp_config)
        info['eigrp']['k_values'] = k_match.group(1) if k_match else '0 1 0 1 0 0'
    elif is_eigrp_router(device_name):
        info['eigrp']['as_number'] = '1'
        info['eigrp']['networks'] = []
        info['eigrp']['passive_interfaces'] = []
        info['eigrp']['is_stub'] = False
        info['eigrp']['k_values'] = '0 1 0 1 0 0'
    
    ospf_match = re.search(r'router ospf (\d+)\n(.*?)(?=\n!|\nrouter |\ninterface |\Z)', config, re.DOTALL)
    if ospf_match:
        ospf_process = ospf_match.group(1)
        ospf_config = ospf_match.group(2)
        
        info['ospf']['process_id'] = ospf_process
        
        network_matches = re.findall(r'network\s+([\d.]+)\s+([\d.]+)\s+area\s+(\d+)', ospf_config)
        info['ospf']['networks'] = [{'network': n[0], 'wildcard': n[1], 'area': n[2]} for n in network_matches]
        info['ospf']['passive_interfaces'] = re.findall(r'passive-interface\s+(\S+)', ospf_config)
        
        rid_match = re.search(r'router-id\s+([\d.]+)', ospf_config)
        info['ospf']['router_id'] = rid_match.group(1) if rid_match else EXPECTED_DEFAULTS['ospf_router_ids'].get(device_name)
        
        stub_areas = re.findall(r'area\s+(\d+)\s+stub', ospf_config)
        info['ospf']['stub_areas'] = stub_areas
    elif is_ospf_router(device_name):
        info['ospf']['process_id'] = '10'
        info['ospf']['networks'] = []
        info['ospf']['passive_interfaces'] = []
        info['ospf']['router_id'] = EXPECTED_DEFAULTS['ospf_router_ids'].get(device_name)
        info['ospf']['stub_areas'] = []
    
    interface_sections = re.findall(r'interface\s+(\S+)\n(.*?)(?=\ninterface |\nrouter |\n!|\Z)', config, re.DOTALL)
    
    for intf_name, intf_config in interface_sections:
        intf_info = {'name': intf_name}
        
        ip_match = re.search(r'ip address\s+([\d.]+)\s+([\d.]+)', intf_config)
        if ip_match:
            intf_info['ip_address'] = ip_match.group(1)
            intf_info['subnet_mask'] = ip_match.group(2)
        
        intf_info['shutdown'] = bool(re.search(r'^\s*shutdown\s*$', intf_config, re.MULTILINE))
        
        hello_match = re.search(r'ip ospf hello-interval\s+(\d+)', intf_config)
        dead_match = re.search(r'ip ospf dead-interval\s+(\d+)', intf_config)
        intf_info['ospf_hello'] = int(hello_match.group(1)) if hello_match else EXPECTED_DEFAULTS['ospf_hello']
        intf_info['ospf_dead'] = int(dead_match.group(1)) if dead_match else EXPECTED_DEFAULTS['ospf_dead']
        
        eigrp_hello_match = re.search(r'ip hello-interval eigrp\s+\d+\s+(\d+)', intf_config)
        eigrp_hold_match = re.search(r'ip hold-time eigrp\s+\d+\s+(\d+)', intf_config)
        intf_info['eigrp_hello'] = int(eigrp_hello_match.group(1)) if eigrp_hello_match else EXPECTED_DEFAULTS['eigrp_hello']
        intf_info['eigrp_hold'] = int(eigrp_hold_match.group(1)) if eigrp_hold_match else EXPECTED_DEFAULTS['eigrp_hold']
        
        info['interfaces'][intf_name] = intf_info
    
    return info

def get_device_baseline(device_name):
    if not BASELINE:
        load_latest_stable_config()
    return BASELINE.get(device_name, {})

def get_eigrp_as_number(device_name):
    baseline = get_device_baseline(device_name)
    return baseline.get('eigrp', {}).get('as_number', '1')

def get_expected_k_values(device_name):
    baseline = get_device_baseline(device_name)
    return baseline.get('eigrp', {}).get('k_values', '0 1 0 1 0 0')

def get_ospf_process_id(device_name):
    baseline = get_device_baseline(device_name)
    return baseline.get('ospf', {}).get('process_id', '10')

def should_interface_be_up(device_name, interface):
    baseline = get_device_baseline(device_name)
    intf_info = baseline.get('interfaces', {}).get(interface, {})
    has_ip = bool(intf_info.get('ip_address'))
    is_not_shutdown = not intf_info.get('shutdown', False)
    return has_ip and is_not_shutdown

def get_interface_ip_config(device_name, interface):
    baseline = get_device_baseline(device_name)
    return baseline.get('interfaces', {}).get(interface, {})

def is_eigrp_router(device_name):
    return device_name.upper() in ['R1', 'R2', 'R3', 'R7']

def is_ospf_router(device_name):
    return device_name.upper() in ['R4', 'R5', 'R6', 'R7']