#ospf_tree.py
import warnings
warnings.filterwarnings('ignore')
import time
import re

try:
    from ..core.config_manager import ConfigManager
except ImportError:
    from core.config_manager import ConfigManager
    def get_device_baseline(device_name): return {}
    def get_ospf_process_id(device_name): return '10'
    def is_ospf_router(device_name):
        return device_name.upper() in ['R4', 'R5', 'R6', 'R7']

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



def disable_debug(tn):
    """Disable all debugging"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'no debug all\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except Exception:
        return False



def get_ospf_neighbors(tn):
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip ospf neighbor\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None



def get_ospf_interface_info(tn, interface):
    """Get OSPF interface information"""
    try:
        clear_line_and_reset(tn)
        cmd = f'show ip ospf interface {interface}\r\n'
        tn.write(cmd.encode('ascii'))
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None



def check_process_id_mismatch(config, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    expected_process = config_manager.get_ospf_process_id(device_name)
    process_match = re.search(r'router ospf\s+(\d+)', config, re.IGNORECASE)
    
    if process_match:
        current_process = process_match.group(1)
        if current_process != expected_process:
            return {
                'type': 'process id mismatch',
                'current': current_process,
                'expected': expected_process,
                'line': f'router ospf {current_process} (expected: {expected_process})'
            }
    
    return None

def check_passive_interfaces(config, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    expected_passive = baseline.get('ospf', {}).get('passive_interfaces', [])
    
    issues = []
    current_passive = []
    
    for line in config.split('\n'):
        if 'passive-interface' in line.lower():
            match = re.search(r'passive-interface\s+(\S+)', line, re.IGNORECASE)
            if match:
                interface = match.group(1)
                current_passive.append(interface)
                if interface not in expected_passive:
                    issues.append({
                        'type': 'passive interface',
                        'category': 'ospf',
                        'interface': interface,
                        'line': line.strip(),
                        'should_be_passive': False
                    })
    
    for expected_intf in expected_passive:
        if expected_intf not in current_passive:
            issues.append({
                'type': 'missing passive interface',
                'category': 'ospf',
                'interface': expected_intf,
                'line': f'passive-interface {expected_intf} missing',
                'should_be_passive': True
            })
    
    return issues


def check_stub_config(config, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    expected_stub_areas = baseline.get('ospf', {}).get('stub_areas', [])
    
    issues = []
    current_stub_areas = re.findall(r'area\s+(\d+)\s+stub', config, re.IGNORECASE)
    
    for area in current_stub_areas:
        if area not in expected_stub_areas:
            issues.append({
                'type': 'unexpected stub area',
                'category': 'ospf',
                'area': area,
                'line': f'area {area} stub (should not be configured)',
                'should_be_stub': False
            })
    
    for area in expected_stub_areas:
        if area not in current_stub_areas:
            issues.append({
                'type': 'missing stub area',
                'category': 'ospf',
                'area': area,
                'line': f'area {area} stub missing',
                'should_be_stub': True
            })
    
    return issues

def check_network_statements(config, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    expected_networks = baseline.get('ospf', {}).get('networks', [])
    
    current_networks = []
    in_ospf_section = False
    
    for line in config.split('\n'):
        line_stripped = line.strip()
        if line_stripped.startswith('router ospf'):
            in_ospf_section = True
            continue
        if in_ospf_section and (line_stripped.startswith('!') or line_stripped.startswith('router ') or line_stripped.startswith('interface ')):
            in_ospf_section = False
        if in_ospf_section and 'network' in line_stripped:
            match = re.search(r'network\s+([\d.]+)\s+([\d.]+)\s+area\s+(\d+)', line_stripped, re.IGNORECASE)
            if match:
                current_networks.append({
                    'network': match.group(1),
                    'wildcard': match.group(2),
                    'area': match.group(3)
                })
    
    issues = []
    expected_set = {(n['network'], n['wildcard'], n['area']) for n in expected_networks}
    current_set = {(n['network'], n['wildcard'], n['area']) for n in current_networks}
    
    extra = current_set - expected_set
    for net, wild, area in extra:
        issues.append({
            'type': 'extra network',
            'category': 'ospf',
            'network': net,
            'wildcard': wild,
            'area': area,
            'line': f'unexpected: network {net} {wild} area {area}'
        })
    
    return issues

def ip_matches_network(ip_address, network, wildcard):
    try:
        ip_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(ip_address.split('.')))
        net_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(network.split('.')))
        wild_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(wildcard.split('.')))
        
        mask = ~wild_int & 0xFFFFFFFF
        return (ip_int & mask) == (net_int & mask)
    except (ValueError, IndexError, AttributeError):
        return False


def check_ospf_enabled_interfaces(config, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    expected_ospf_interfaces = set(
        config_manager.OSPF_INTERFACE_PARTICIPATION.get(device_name, [])
    )
    
    if not expected_ospf_interfaces:
        return []
    
    baseline = config_manager.get_device_baseline(device_name)
    baseline_interfaces = baseline.get('interfaces', {})
    baseline_networks = baseline.get('ospf', {}).get('networks', [])
    
    current_ospf_networks = []
    in_ospf_section = False
    
    for line in config.split('\n'):
        line_stripped = line.strip()
        if line_stripped.startswith('router ospf'):
            in_ospf_section = True
            continue
        if in_ospf_section and (line_stripped.startswith('!') or line_stripped.startswith('router ') or line_stripped.startswith('interface ')):
            in_ospf_section = False
        if in_ospf_section and 'network' in line_stripped:
            match = re.search(r'network\s+([\d.]+)\s+([\d.]+)\s+area\s+(\d+)', line_stripped, re.IGNORECASE)
            if match:
                current_ospf_networks.append({
                    'network': match.group(1),
                    'wildcard': match.group(2),
                    'area': match.group(3)
                })
    
    current_ospf_interfaces = set()
    
    for intf_name in expected_ospf_interfaces:
        if intf_name not in baseline_interfaces:
            continue
        
        intf_info = baseline_interfaces[intf_name]
        ip_address = intf_info.get('ip_address')
        
        if not ip_address:
            continue
        
        for network_entry in current_ospf_networks:
            network = network_entry.get('network', '')
            wildcard = network_entry.get('wildcard', '')
            if network and wildcard:
                if ip_matches_network(ip_address, network, wildcard):
                    current_ospf_interfaces.add(intf_name)
                    break
    
    issues = []
    
    missing_interfaces = expected_ospf_interfaces - current_ospf_interfaces
    
    for intf in missing_interfaces:
        intf_info = baseline_interfaces.get(intf, {})
        ip_addr = intf_info.get('ip_address', 'unknown')
        
        matched_network = None
        for network_entry in baseline_networks:
            network = network_entry.get('network', '')
            wildcard = network_entry.get('wildcard', '')
            if network and wildcard:
                if ip_matches_network(ip_addr, network, wildcard):
                    matched_network = network_entry
                    break
        
        if matched_network:
            issues.append({
                'type': 'interface not in ospf',
                'interface': intf,
                'ip_address': ip_addr,
                'expected_network': matched_network['network'],
                'expected_wildcard': matched_network['wildcard'],
                'expected_area': matched_network['area'],
                'line': f'{intf} ({ip_addr}) not in OSPF (should be in {matched_network["network"]}/{matched_network["wildcard"]} area {matched_network["area"]})'
            })
    
    return issues

def check_interface_timers(config, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    interfaces = baseline.get('interfaces', {})
    
    issues = []
    
    interface_sections = re.findall(
        r'interface\s+(\S+)\n(.*?)(?=\ninterface |\nrouter |\n!|\Z)',
        config, re.DOTALL
    )
    
    for intf_name, intf_config in interface_sections:
        if intf_name not in interfaces:
            continue
        
        intf_info = interfaces[intf_name]
        if not intf_info.get('ip_address'):
            continue
        
        hello_match = re.search(r'ip ospf hello-interval\s+(\d+)', intf_config)
        dead_match = re.search(r'ip ospf dead-interval\s+(\d+)', intf_config)
        
        expected_hello = intf_info.get('ospf_hello', 10)
        expected_dead = intf_info.get('ospf_dead', 40)
        
        current_hello = int(hello_match.group(1)) if hello_match else expected_hello
        current_dead = int(dead_match.group(1)) if dead_match else expected_dead
        
        if current_hello != expected_hello:
            issues.append({
                'type': 'hello interval mismatch',
                'category': 'ospf',
                'interface': intf_name,
                'current': current_hello,
                'expected': expected_hello,
                'line': f'{intf_name}: Hello {current_hello} (expected {expected_hello})'
            })
        
        if current_dead != expected_dead:
            issues.append({
                'type': 'dead interval mismatch',
                'category': 'ospf',
                'interface': intf_name,
                'current': current_dead,
                'expected': expected_dead,
                'line': f'{intf_name}: Dead {current_dead} (expected {expected_dead})'
            })
    
    return issues

def check_router_id_conflicts(config, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    issues = []
    baseline = config_manager.get_device_baseline(device_name)
    expected_rid = baseline.get('ospf', {}).get('router_id')
    
    rid_match = re.search(r'router-id\s+([\d.]+)', config, re.IGNORECASE)
    
    if rid_match and expected_rid:
        current_rid = rid_match.group(1)
        if current_rid != expected_rid:
            issues.append({
                'type': 'router id mismatch',
                'category': 'ospf',
                'current': current_rid,
                'expected': expected_rid,
                'line': f'Router ID {current_rid} (expected {expected_rid})'
            })
    
    return issues


def check_area_assignments(config, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    baseline_interfaces = baseline.get('interfaces', {})
    
    issues = []
    
    interface_sections = re.findall(
        r'interface\s+(\S+)\n(.*?)(?=\ninterface |\nrouter |\n!|\Z)',
        config, re.DOTALL
    )
    
    for intf_name, intf_config in interface_sections:
        if intf_name not in baseline_interfaces:
            continue
        
        intf_info = baseline_interfaces[intf_name]
        if not intf_info.get('ip_address'):
            continue
        
        area_match = re.search(r'ip ospf\s+\d+\s+area\s+(\d+)', intf_config)
        if not area_match:
            continue
        
        current_area = area_match.group(1)
        
        expected_area = '0'
        expected_networks = baseline.get('ospf', {}).get('networks', [])
        interface_ip = intf_info.get('ip_address', '')
        
        for net in expected_networks:
            network = net.get('network', '')
            wildcard = net.get('wildcard', '')
            if network and wildcard:
                if ip_matches_network(interface_ip, network, wildcard):
                    expected_area = net.get('area', '0')
                    break
        
        if current_area != expected_area:
            issues.append({
                'type': 'area mismatch',
                'category': 'ospf',
                'interface': intf_name,
                'current_area': current_area,
                'expected_area': expected_area,
                'line': f'{intf_name}: Area {current_area} (expected {expected_area})'
            })
    
    return issues



def get_ospf_fix_commands(issue_type, issue_details, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    process_id = config_manager.get_ospf_process_id(device_name)
    
    if issue_type in ['hello interval mismatch', 'dead interval mismatch', 'ospf timer mismatch']:
        interface = issue_details.get('interface')
        expected_hello = issue_details.get('expected_hello', 10)
        expected_dead = issue_details.get('expected_dead', 40)
        return [
            f"interface {interface}",
            f"ip ospf hello-interval {expected_hello}",
            f"ip ospf dead-interval {expected_dead}",
            "end"
        ]
    elif issue_type == 'passive interface':
        interface = issue_details.get('interface')
        should_be_passive = issue_details.get('should_be_passive', False)
        if not should_be_passive:
            return [
                f"router ospf {process_id}",
                f"no passive-interface {interface}",
                "end"
            ]
    elif issue_type == 'process id mismatch':
        expected_process = issue_details.get('expected', process_id)
        current_process = issue_details.get('current')
        if current_process and expected_process:
            return [
                f"no router ospf {current_process}",
                f"router ospf {expected_process}",
                "# Re-add network statements and other OSPF config",
                "end"
            ]
    elif issue_type == 'missing network':
        network = issue_details.get('network')
        wildcard = issue_details.get('wildcard')
        area = issue_details.get('area')
        return [
            f"router ospf {process_id}",
            f"network {network} {wildcard} area {area}",
            "end"
        ]
    elif issue_type == 'extra network':
        network = issue_details.get('network')
        wildcard = issue_details.get('wildcard')
        area = issue_details.get('area')
        return [
            f"router ospf {process_id}",
            f"no network {network} {wildcard} area {area}",
            "end"
        ]
    elif issue_type in ['stub area', 'unexpected stub area']:
        area = issue_details.get('area')
        should_be_stub = issue_details.get('should_be_stub', False)
        if not should_be_stub:
            return [
                f"router ospf {process_id}",
                f"no area {area} stub",
                "end"
            ]
    elif issue_type == 'missing stub area':
        area = issue_details.get('area')
        return [
            f"router ospf {process_id}",
            f"area {area} stub",
            "end"
        ]
    elif issue_type == 'router id mismatch':
        expected_rid = issue_details.get('expected')
        if expected_rid:
            return [
                f"router ospf {process_id}",
                f"router-id {expected_rid}",
                "end",
                "# NOTE: May need to clear OSPF process: clear ip ospf process"
            ]
    elif issue_type == 'suspicious router id':
        expected_rid = issue_details.get('expected')
        if expected_rid:
            return [
                f"router ospf {process_id}",
                f"router-id {expected_rid}",
                "end",
                "# IMPORTANT: Clear OSPF process after: clear ip ospf process"
            ]
    elif issue_type == 'possible duplicate router id':
        return []
    elif issue_type == 'area mismatch':
        interface = issue_details.get('interface')
        expected_area = issue_details.get('expected_area', '0')
        return [
            f"interface {interface}",
            f"ip ospf {process_id} area {expected_area}",
            "end"
        ]
    elif issue_type == 'interface not in ospf':
        interface = issue_details.get('interface')
        network = issue_details.get('expected_network')
        wildcard = issue_details.get('expected_wildcard')
        area = issue_details.get('expected_area', '0')
        return [
            f"router ospf {process_id}",
            f"network {network} {wildcard} area {area}",
            "end",
            f"# Verify {interface} is now in OSPF"
        ]
    
    return []


def apply_ospf_fixes(tn, fixes):
    """Apply OSPF configuration fixes"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'configure terminal\r\n')
        time.sleep(0.3)
        tn.read_very_eager()

        for cmd in fixes:
            if cmd.startswith('#'):  # Skip comments
                continue
            tn.write(cmd.encode('ascii') + b'\r\n')
            time.sleep(0.3)
            tn.read_very_eager()

        tn.write(b'end\r\n')
        time.sleep(0.3)
        tn.read_very_eager()
        tn.write(b'write memory\r\n')
        time.sleep(1)
        tn.read_very_eager()

        return True
    except Exception:
        return False


def verify_ospf_neighbors(tn):
    """Verify OSPF neighbors after fix"""
    try:
        tn.write(b'\x03')
        time.sleep(0.1)
        tn.read_very_eager()
        tn.write(b'end\r\n')
        time.sleep(0.1)
        tn.read_very_eager()
        
        tn.write(b'show ip ospf neighbor\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        
        neighbors = []
        for line in output.split('\n'):
            if re.search(r'\d+\.\d+\.\d+\.\d+', line) and 'Neighbor ID' not in line and 'Address' not in line:
                parts = line.split()
                if len(parts) >= 1:
                    match = re.match(r'\d+\.\d+\.\d+\.\d+', parts[0])
                    if match:
                        neighbors.append(parts[0])
        
        if neighbors:
            return "OSPF Neighbors: " + ", ".join(set(neighbors))
        else:
            return "OSPF: No neighbors found"
    except Exception:
        return "OSPF: Verification Failed"


def troubleshoot_ospf(device_name, tn, auto_prompt=True, config_manager=None):
    from utils.telnet_utils import get_running_config
    
    if config_manager is None:
        config_manager = ConfigManager()
    
    if not config_manager.is_ospf_router(device_name):
        return [], []
    
    config = get_running_config(tn)
    if not config:
        return [], []
    
    all_issues = []
    
    process_issue = check_process_id_mismatch(config, device_name, config_manager)
    if process_issue:
        all_issues.append(process_issue)
    
    passive_intfs = check_passive_interfaces(config, device_name, config_manager)
    if passive_intfs:
        all_issues.extend(passive_intfs)
    
    stub_issues = check_stub_config(config, device_name, config_manager)
    if stub_issues:
        all_issues.extend(stub_issues)
    
    network_issues = check_network_statements(config, device_name, config_manager)
    if network_issues:
        all_issues.extend(network_issues)
    
    ospf_participation_issues = check_ospf_enabled_interfaces(config, device_name, config_manager)
    if ospf_participation_issues:
        all_issues.extend(ospf_participation_issues)
    
    timer_issues = check_interface_timers(config, device_name, config_manager)
    if timer_issues:
        all_issues.extend(timer_issues)
    
    area_issues = check_area_assignments(config, device_name, config_manager)
    if area_issues:
        all_issues.extend(area_issues)
    
    rid_issues = check_router_id_conflicts(config, device_name, config_manager)
    if rid_issues:
        all_issues.extend(rid_issues)
    
    neighbor_output = get_ospf_neighbors(tn)
    
    if not all_issues:
        return [], []
    
    if not auto_prompt:
        return all_issues, []
    
    fixed_issues = []
    for issue in all_issues:
        issue_type = issue['type']
        print(f"\nProblem: {device_name} - {issue_type}")
        if 'line' in issue:
            print(f"  Details: {issue['line'][:80]}")
        
        response = input("Apply fixes? (Y/n): ").strip().lower()
        if response == 'n':
            continue
        
        fix_commands = get_ospf_fix_commands(issue_type, issue, device_name, config_manager)
        if not fix_commands:
            print("Note: Manual intervention required")
            continue
        
        print(f"Commands to apply:")
        for cmd in fix_commands:
            print(f"  {cmd}")
        
        if apply_ospf_fixes(tn, fix_commands):
            print("Fixes applied successfully")
            fixed_issues.append(issue_type)
        else:
            print("Failed to apply fixes")
    
    return all_issues, fixed_issues