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
        return device_name.upper() in ['R4', 'R5', 'R6']

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

def enable_ospf_debug(tn):
    """Enable OSPF debugging"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'debug ip ospf adj\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        return True
    except Exception:
        return False

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

def gather_ospf_debug(tn, wait_time=10):
    """Gather OSPF debug output"""
    try:
        time.sleep(wait_time)
        tn.write(b"show logging\r\n")
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None

def get_ospf_neighbors(tn):
    """Get OSPF neighbor information"""
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip ospf neighbor\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        return output
    except Exception:
        return None

def get_ospf_config(tn):
    try:
        clear_line_and_reset(tn)
        tn.write(b'terminal length 0\r\n')
        time.sleep(0.2)
        tn.read_very_eager()
        
        tn.write(b'show running-config\r\n')
        time.sleep(1.5)
        
        output = ""
        for _ in range(20):
            chunk = tn.read_very_eager().decode('ascii', errors='ignore')
            if chunk:
                output += chunk
            time.sleep(0.1)
            if 'end' in output.lower() and len(output) > 500:
                break
        
        if len(output) < 200:
            return None
        
        return output
    except Exception as e:
        print(f"[DEBUG] Error getting OSPF config: {e}")
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



def check_process_id_mismatch(tn, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    config = get_ospf_config(tn)
    if not config:
        return None
    
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

def check_passive_interfaces(tn, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    config = get_ospf_config(tn)
    if not config:
        return []
    
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


def check_stub_config(tn, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    config = get_ospf_config(tn)
    if not config:
        return []
    
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

def check_network_statements(tn, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    config = get_ospf_config(tn)
    
    print(f"[DEBUG {device_name}] get_ospf_config returned: {len(config) if config else 0} bytes")
    
    if not config:
        print(f"[DEBUG {device_name}] No config returned from get_ospf_config!")
        return []
    
    baseline = config_manager.get_device_baseline(device_name)
    expected_networks = baseline.get('ospf', {}).get('networks', [])
    
    print(f"[DEBUG {device_name}] Expected networks from baseline:")
    for net in expected_networks:
        print(f"  {net}")
    
    current_networks = []
    in_ospf_section = False
    
    for line in config.split('\n'):
        line_stripped = line.strip()
        
        if line_stripped.startswith('router ospf'):
            in_ospf_section = True
            print(f"[DEBUG {device_name}] Found OSPF section: {line_stripped}")
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
                print(f"[DEBUG {device_name}] Found network statement: {match.group(1)} {match.group(2)} area {match.group(3)}")
    
    print(f"[DEBUG {device_name}] Current networks from running config:")
    for net in current_networks:
        print(f"  {net}")
    
    issues = []
    expected_set = {(n['network'], n['wildcard'], n['area']) for n in expected_networks}
    current_set = {(n['network'], n['wildcard'], n['area']) for n in current_networks}
    
    print(f"[DEBUG {device_name}] Expected set: {expected_set}")
    print(f"[DEBUG {device_name}] Current set: {current_set}")
    
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
    """
    Check if an IP address matches a network/wildcard combination.
    """
    try:
        # Convert to integers for bitwise operations
        ip_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(ip_address.split('.')))
        net_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(network.split('.')))
        wild_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(wildcard.split('.')))
        
        # Apply wildcard mask
        mask = ~wild_int & 0xFFFFFFFF
        return (ip_int & mask) == (net_int & mask)
    except (ValueError, IndexError, AttributeError):
        return False


def check_ospf_enabled_interfaces(tn, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    baseline_interfaces = baseline.get('interfaces', {})
    expected_networks = baseline.get('ospf', {}).get('networks', [])
    
    if not expected_networks:
        return []
    
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip ospf interface brief\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
    except Exception:
        return []
    
    ospf_interfaces = set()
    for line in output.split('\n'):
        if not line.strip() or 'Interface' in line or 'PID' in line:
            continue
        match = re.match(r'^(\S+)', line.strip())
        if match and re.search(r'\d+', line):
            ospf_interfaces.add(match.group(1))
    
    expected_interfaces = set()
    for intf_name, intf_info in baseline_interfaces.items():
        interface_ip = intf_info.get('ip_address')
        if not interface_ip:
            continue
        
        for network_entry in expected_networks:
            network = network_entry.get('network', '')
            wildcard = network_entry.get('wildcard', '')
            if network and wildcard:
                if ip_matches_network(interface_ip, network, wildcard):
                    expected_interfaces.add(intf_name)
                    break
    
    issues = []
    missing_interfaces = expected_interfaces - ospf_interfaces
    for intf in missing_interfaces:
        intf_info = baseline_interfaces.get(intf, {})
        ip_addr = intf_info.get('ip_address', 'unknown')
        
        for network_entry in expected_networks:
            network = network_entry.get('network', '')
            wildcard = network_entry.get('wildcard', '')
            area = network_entry.get('area', '0')
            if ip_matches_network(ip_addr, network, wildcard):
                issues.append({
                    'type': 'interface not in ospf',
                    'interface': intf,
                    'ip_address': ip_addr,
                    'expected_network': network,
                    'expected_wildcard': wildcard,
                    'expected_area': area,
                    'line': f'{intf} ({ip_addr}) not in OSPF (should be in {network}/{wildcard} area {area})'
                })
                break
    
    return issues

def check_interface_timers(tn, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    interfaces = baseline.get('interfaces', {})
    issues = []
    
    for intf_name, intf_info in interfaces.items():
        if not intf_info.get('ip_address'):
            continue
        
        try:
            clear_line_and_reset(tn)
            cmd = f'show ip ospf interface {intf_name}\r\n'
            tn.write(cmd.encode('ascii'))
            time.sleep(1)
            output = tn.read_very_eager().decode('ascii', errors='ignore')
            
            if 'not found' in output.lower() or 'not enabled' in output.lower():
                continue
            
            hello_match = re.search(r'Hello\s+(\d+)', output, re.IGNORECASE)
            dead_match = re.search(r'Dead\s+(\d+)', output, re.IGNORECASE)
            
            if not hello_match:
                hello_match = re.search(r'Hello[- ]interval\s+(\d+)', output, re.IGNORECASE)
            if not dead_match:
                dead_match = re.search(r'Dead[- ]interval\s+(\d+)', output, re.IGNORECASE)
            
            expected_hello = intf_info.get('ospf_hello', 10)
            expected_dead = intf_info.get('ospf_dead', 40)
            
            if hello_match:
                current_hello = int(hello_match.group(1))
                if current_hello != expected_hello:
                    issues.append({
                        'type': 'hello interval mismatch',
                        'category': 'ospf',
                        'interface': intf_name,
                        'current': current_hello,
                        'expected': expected_hello,
                        'line': f'{intf_name}: Hello {current_hello} (expected {expected_hello})'
                    })
            
            if dead_match:
                current_dead = int(dead_match.group(1))
                if current_dead != expected_dead:
                    issues.append({
                        'type': 'dead interval mismatch',
                        'category': 'ospf',
                        'interface': intf_name,
                        'current': current_dead,
                        'expected': expected_dead,
                        'line': f'{intf_name}: Dead {current_dead} (expected {expected_dead})'
                    })
        except Exception:
            continue
    
    return issues

def check_router_id_conflicts(tn, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    issues = []
    baseline = config_manager.get_device_baseline(device_name)
    expected_rid = baseline.get('ospf', {}).get('router_id')
    
    try:
        clear_line_and_reset(tn)
        tn.write(b'show ip ospf\r\n')
        time.sleep(1)
        output = tn.read_very_eager().decode('ascii', errors='ignore')
        
        rid_match = re.search(r'Routing Process.*?ospf.*?Router ID\s+([\d.]+)', output, re.IGNORECASE | re.DOTALL)
        if not rid_match:
            rid_match = re.search(r'Router ID\s+([\d.]+)', output, re.IGNORECASE)
        
        if rid_match:
            current_rid = rid_match.group(1)
            if expected_rid and current_rid != expected_rid:
                issues.append({
                    'type': 'router id mismatch',
                    'category': 'ospf',
                    'current': current_rid,
                    'expected': expected_rid,
                    'line': f'Router ID {current_rid} (expected {expected_rid})'
                })
    except Exception:
        pass
    
    neighbor_output = get_ospf_neighbors(tn)
    if neighbor_output:
        init_count = 0
        for line in neighbor_output.split('\n'):
            if not line.strip() or 'Neighbor ID' in line or 'Address' in line:
                continue
            if not re.search(r'\d+\.\d+\.\d+\.\d+', line):
                continue
            state_match = re.search(r'\s+(INIT|DOWN)/', line.upper())
            if state_match:
                init_count += 1
        
        if init_count > 0:
            issues.append({
                'type': 'possible duplicate router id',
                'category': 'ospf',
                'line': f'{init_count} neighbor(s) in INIT/DOWN state',
                'message': 'Neighbors stuck - may indicate duplicate router ID'
            })
    
    return issues


def check_area_assignments(tn, device_name, config_manager=None):
    if config_manager is None:
        config_manager = ConfigManager()
    
    baseline = config_manager.get_device_baseline(device_name)
    baseline_interfaces = baseline.get('interfaces', {})
    issues = []
    
    for intf_name, intf_info in baseline_interfaces.items():
        if not intf_info.get('ip_address'):
            continue
        
        try:
            clear_line_and_reset(tn)
            cmd = f'show ip ospf interface {intf_name}\r\n'
            tn.write(cmd.encode('ascii'))
            time.sleep(1)
            output = tn.read_very_eager().decode('ascii', errors='ignore')
            
            if 'not found' in output.lower() or 'not enabled' in output.lower():
                continue
            
            area_match = re.search(r'Area\s+(\d+)', output, re.IGNORECASE)
            if area_match:
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
        except Exception:
            continue
    
    return issues

def parse_ospf_debug(debug_output):
    """Parse OSPF debug output for mismatches"""
    mismatches = []
    
    for line in debug_output.splitlines():
        line_lower = line.lower()
        
        if "hello" in line_lower and "mismatch" in line_lower:
            mismatches.append({'type': 'hello interval mismatch', 'line': line.strip()})
        
        if "dead" in line_lower and "mismatch" in line_lower:
            mismatches.append({'type': 'dead interval mismatch', 'line': line.strip()})
        
        if "duplicate router" in line_lower or "duplicate rid" in line_lower:
            mismatches.append({'type': 'duplicate router id', 'line': line.strip()})
        
        if "area mismatch" in line_lower:
            mismatches.append({'type': 'area mismatch', 'line': line.strip()})
        
        if "netmask mismatch" in line_lower or "mask mismatch" in line_lower:
            mismatches.append({'type': 'netmask mismatch', 'line': line.strip()})
        
        if "authentication" in line_lower and ("fail" in line_lower or "mismatch" in line_lower):
            mismatches.append({'type': 'authentication mismatch', 'line': line.strip()})
    
    return mismatches


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
    if config_manager is None:
        config_manager = ConfigManager()
    
    if not config_manager.is_ospf_router(device_name):
        return [], []
    
    all_issues = []
    
    process_issue = check_process_id_mismatch(tn, device_name, config_manager)
    if process_issue:
        all_issues.append(process_issue)
    
    passive_intfs = check_passive_interfaces(tn, device_name, config_manager)
    if passive_intfs:
        all_issues.extend(passive_intfs)
    
    stub_issues = check_stub_config(tn, device_name, config_manager)
    if stub_issues:
        all_issues.extend(stub_issues)
    
    network_issues = check_network_statements(tn, device_name, config_manager)
    if network_issues:
        all_issues.extend(network_issues)
    
    ospf_participation_issues = check_ospf_enabled_interfaces(tn, device_name, config_manager)
    if ospf_participation_issues:
        all_issues.extend(ospf_participation_issues)
    
    timer_issues = check_interface_timers(tn, device_name, config_manager)
    if timer_issues:
        all_issues.extend(timer_issues)
    
    area_issues = check_area_assignments(tn, device_name, config_manager)
    if area_issues:
        all_issues.extend(area_issues)
    
    rid_issues = check_router_id_conflicts(tn, device_name, config_manager)
    if rid_issues:
        all_issues.extend(rid_issues)
    
    neighbor_output = get_ospf_neighbors(tn)
    if not neighbor_output:
        return all_issues, []
    
    neighbor_lines = [l for l in neighbor_output.split('\n')
                     if l.strip() and 'Neighbor' not in l and 'Address' not in l]
    neighbor_count = len([l for l in neighbor_lines if any(c.isdigit() for c in l)])
    
    if neighbor_count == 0 and not all_issues:
        if enable_ospf_debug(tn):
            debug_output = gather_ospf_debug(tn, wait_time=10)
            disable_debug(tn)
            if debug_output:
                debug_issues = parse_ospf_debug(debug_output)
                all_issues.extend(debug_issues)
    
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