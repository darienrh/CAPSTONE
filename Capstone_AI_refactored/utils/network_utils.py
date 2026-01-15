#!/usr/bin/env python3
"""network_utils.py - Network-related utility functions"""

import re
import ipaddress


def parse_ip_address(ip_string):
    """
    Parse and validate an IP address
    
    Args:
        ip_string: IP address string
    
    Returns:
        ipaddress.IPv4Address object or None
    """
    try:
        return ipaddress.IPv4Address(ip_string)
    except:
        return None


def parse_network(network_string, wildcard_string):
    """
    Parse network and wildcard mask into network object
    
    Args:
        network_string: Network address (e.g., '10.1.1.0')
        wildcard_string: Wildcard mask (e.g., '0.0.0.255')
    
    Returns:
        ipaddress.IPv4Network object or None
    """
    try:
        # Convert wildcard to netmask
        wildcard = ipaddress.IPv4Address(wildcard_string)
        netmask = ipaddress.IPv4Address(int(wildcard) ^ 0xFFFFFFFF)
        
        # Create network
        network = ipaddress.IPv4Network(f"{network_string}/{netmask}", strict=False)
        return network
    except:
        return None


def ip_in_network(ip_address, network, wildcard):
    """
    Check if an IP address is in a network defined by network/wildcard
    
    Args:
        ip_address: IP address string
        network: Network address string
        wildcard: Wildcard mask string
    
    Returns:
        True if IP is in network, False otherwise
    """
    try:
        ip_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(ip_address.split('.')))
        net_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(network.split('.')))
        wild_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(wildcard.split('.')))
        
        mask = ~wild_int & 0xFFFFFFFF
        return (ip_int & mask) == (net_int & mask)
    except:
        return False


def wildcard_to_netmask(wildcard):
    """
    Convert wildcard mask to subnet mask
    
    Args:
        wildcard: Wildcard mask string (e.g., '0.0.0.255')
    
    Returns:
        Subnet mask string (e.g., '255.255.255.0')
    """
    try:
        wild_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(wildcard.split('.')))
        netmask_int = wild_int ^ 0xFFFFFFFF
        return '.'.join(str((netmask_int >> (8 * (3 - i))) & 0xFF) for i in range(4))
    except:
        return None


def netmask_to_wildcard(netmask):
    """
    Convert subnet mask to wildcard mask
    
    Args:
        netmask: Subnet mask string (e.g., '255.255.255.0')
    
    Returns:
        Wildcard mask string (e.g., '0.0.0.255')
    """
    try:
        mask_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(netmask.split('.')))
        wildcard_int = mask_int ^ 0xFFFFFFFF
        return '.'.join(str((wildcard_int >> (8 * (3 - i))) & 0xFF) for i in range(4))
    except:
        return None


def parse_interface_name(interface_string):
    """
    Parse interface name into type and number
    
    Args:
        interface_string: Interface name (e.g., 'GigabitEthernet0/0')
    
    Returns:
        Tuple of (type, number) or (None, None)
    """
    match = re.match(r'([A-Za-z]+)([\d/]+)', interface_string)
    if match:
        return match.group(1), match.group(2)
    return None, None


def normalize_interface_name(interface_string):
    """
    Normalize interface name to long form
    
    Args:
        interface_string: Interface name (e.g., 'Fa0/0', 'f0/0')
    
    Returns:
        Normalized name (e.g., 'FastEthernet0/0')
    """
    # Mapping of abbreviations to full names
    abbrev_map = {
        'Fa': 'FastEthernet',
        'Gi': 'GigabitEthernet',
        'Te': 'TenGigabitEthernet',
        'Et': 'Ethernet',
        'Se': 'Serial',
        'Lo': 'Loopback'
    }
    
    for abbrev, full in abbrev_map.items():
        if interface_string.startswith(abbrev):
            return interface_string.replace(abbrev, full, 1)
    
    return interface_string


def extract_ip_addresses(text):
    """
    Extract all IP addresses from text
    
    Args:
        text: Text to search
    
    Returns:
        List of IP address strings
    """
    pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    return re.findall(pattern, text)


def parse_router_id(text):
    """
    Extract router ID from show command output
    
    Args:
        text: Command output text
    
    Returns:
        Router ID string or None
    """
    match = re.search(r'Router ID[:\s]+(\d+\.\d+\.\d+\.\d+)', text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def parse_as_number(text):
    """
    Extract AS number from EIGRP output
    
    Args:
        text: Command output text
    
    Returns:
        AS number string or None
    """
    match = re.search(r'AS\((\d+)\)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'router eigrp\s+(\d+)', text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def parse_process_id(text):
    """
    Extract OSPF process ID from output
    
    Args:
        text: Command output text
    
    Returns:
        Process ID string or None
    """
    match = re.search(r'router ospf\s+(\d+)', text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def is_valid_subnet_mask(mask):
    """
    Check if a subnet mask is valid
    
    Args:
        mask: Subnet mask string
    
    Returns:
        True if valid, False otherwise
    """
    try:
        # Check if it's a valid IP address
        mask_obj = ipaddress.IPv4Address(mask)
        mask_int = int(mask_obj)
        
        # Check if it's a valid subnet mask (contiguous 1s followed by 0s)
        # A valid mask XOR with (mask + 1) should equal all 1s up to that point
        inverted = mask_int ^ 0xFFFFFFFF
        return (inverted & (inverted + 1)) == 0
    except:
        return False


def calculate_network_address(ip, netmask):
    """
    Calculate network address from IP and netmask
    
    Args:
        ip: IP address string
        netmask: Subnet mask string
    
    Returns:
        Network address string or None
    """
    try:
        ip_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(ip.split('.')))
        mask_int = sum(int(octet) << (8 * (3 - i)) for i, octet in enumerate(netmask.split('.')))
        
        network_int = ip_int & mask_int
        return '.'.join(str((network_int >> (8 * (3 - i))) & 0xFF) for i in range(4))
    except:
        return None


def get_interface_type(interface_name):
    """
    Determine interface type
    
    Args:
        interface_name: Interface name
    
    Returns:
        Type string ('ethernet', 'serial', 'loopback', 'tunnel', 'unknown')
    """
    name_lower = interface_name.lower()
    
    if 'ethernet' in name_lower:
        return 'ethernet'
    elif 'serial' in name_lower:
        return 'serial'
    elif 'loopback' in name_lower:
        return 'loopback'
    elif 'tunnel' in name_lower:
        return 'tunnel'
    else:
        return 'unknown'


def format_mac_address(mac):
    """
    Format MAC address to standard notation
    
    Args:
        mac: MAC address in any format
    
    Returns:
        Formatted MAC address (e.g., '00:1a:2b:3c:4d:5e')
    """
    # Remove all non-hex characters
    mac_clean = re.sub(r'[^0-9a-fA-F]', '', mac)
    
    if len(mac_clean) != 12:
        return None
    
    # Format as xx:xx:xx:xx:xx:xx
    return ':'.join(mac_clean[i:i+2] for i in range(0, 12, 2)).lower()


def parse_bandwidth(bandwidth_string):
    """
    Parse bandwidth string to numeric value in Kbps
    
    Args:
        bandwidth_string: Bandwidth string (e.g., '100 Mbps', '1544 Kbit')
    
    Returns:
        Bandwidth in Kbps or None
    """
    match = re.search(r'(\d+(?:\.\d+)?)\s*(Kbps?|Mbps?|Gbps?|Kbit|Mbit|Gbit)?', 
                     bandwidth_string, re.IGNORECASE)
    
    if not match:
        return None
    
    value = float(match.group(1))
    unit = match.group(2).lower() if match.group(2) else 'kbps'
    
    # Convert to Kbps
    if 'gbps' in unit or 'gbit' in unit:
        return value * 1000000
    elif 'mbps' in unit or 'mbit' in unit:
        return value * 1000
    else:  # kbps/kbit
        return value