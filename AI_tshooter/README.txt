AI Tshooter

Directory Structure:
AI_tshooter/
├── __init__.py
├── models/
│   ├── __init__.py
│   └── diagnostic.py          # Data models
├── analyzers/
│   ├── __init__.py
│   ├── base.py                # Base analyzer class
│   ├── interface_analyzer.py
│   ├── vlan_analyzer.py
│   ├── ospf_analyzer.py
│   ├── bgp_analyzer.py
│   ├── eigrp_analyzer.py
│   ├── performance_analyzer.py
│   └── other_analyzers.py     # Gateway, NTP, IPv6, GRE
├── engine.py                  # Main decision tree engine
├── formatters.py              # Output formatting
└── utils.py                   # Helper functions

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Data Flow:

0. User injects problems to GNS3 via python script
1. User opens terminal and runs decision tree analysis (python engine.py)
2. engine.py fetches Telemetry from prometheus, afterwards fetches every N seconds.
3. Prometheus scrapes SNMP data from GNS3
4. Telemetry data arrives, and decision tree engine starts its checks
5. decision tree calls all analyzer py files and returns results to formatters.py (results should make the problem very clear ex. "wrong AS number on R1")
6. formatters.py converts the results into natural language asking for the exact syntax configuration fix, and sends as context to LLM, Instructions will give LLM exact formatting parameters.
7. LLM returns structured configuration syntax response in file located in /responses Directory
8. engine.py then prompts user if it want to deploy the configuration change commands that are stored in the /responses Directory
9. If no--> return to main menu, If yes --> shipit.py will send python script fixing problems

#optional: create GUI to view and manage engine
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
initial files (since changed)
# ==================== models/diagnostic.py ====================
"""
Data models for diagnostic results
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class Severity(Enum):
    """Issue severity levels"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class DiagnosticResult:
    """Represents a single diagnostic finding"""
    category: str
    issue: str
    severity: Severity
    root_cause: str
    remediation_steps: List[str]
    affected_devices: List[str]
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'category': self.category,
            'issue': self.issue,
            'severity': self.severity.value,
            'root_cause': self.root_cause,
            'remediation_steps': self.remediation_steps,
            'affected_devices': self.affected_devices,
            'metrics': self.metrics
        }


# ==================== analyzers/base.py ====================
"""
Base network analyzer - Handles fundamental Layer 3 networking
Covers: Interfaces, IP Addressing, Hello/Dead Intervals, NTP, Default Gateway
"""
from typing import List, Dict, Any
from models.diagnostic import DiagnosticResult, Severity


class BaseNetworkAnalyzer:
    """Analyzes base Layer 3 networking components"""
    
    def __init__(self):
        self.results = []
    
    def analyze(self, device: str, data: Dict[str, Any]) -> List[DiagnosticResult]:
        """Run all base network diagnostics"""
        self.results = []
        
        self.results.extend(self._check_interfaces(device, data))
        self.results.extend(self._check_ip_addressing(device, data))
        self.results.extend(self._check_default_gateway(device, data))
        self.results.extend(self._check_ntp(device, data))
        
        return self.results
    
    # ==================== INTERFACE DIAGNOSTICS ====================
    
    def _check_interfaces(self, device: str, data: Dict) -> List[DiagnosticResult]:
        """Check interface status and configuration"""
        results = []
        interfaces = data.get('interfaces', {})
        
        for intf_name, intf_data in interfaces.items():
            admin_status = intf_data.get('admin_status', 'up')
            oper_status = intf_data.get('oper_status', 'up')
            port_security_violations = intf_data.get('port_security_violations', 0)
            input_errors = intf_data.get('input_errors', 0)
            output_errors = intf_data.get('output_errors', 0)
            crc_errors = intf_data.get('crc_errors', 0)
            duplex_mismatch = intf_data.get('duplex_mismatch', False)
            
            # Check for down/down state
            if admin_status == 'down' and oper_status == 'down':
                results.append(self._create_result(
                    category="Interface",
                    issue=f"Interface {intf_name} is administratively down",
                    severity=Severity.WARNING,
                    root_cause="Interface is in shutdown state",
                    remediation_steps=[
                        f"Access device {device}",
                        f"Enter configuration mode: configure terminal",
                        f"Select interface: interface {intf_name}",
                        f"Enable interface: no shutdown",
                        f"Verify status: show ip interface brief"
                    ],
                    device=device,
                    metrics={'admin_status': admin_status, 'oper_status': oper_status}
                ))
            
            # Check for up/down state (protocol down)
            elif admin_status == 'up' and oper_status == 'down':
                results.append(self._create_result(
                    category="Interface",
                    issue=f"Interface {intf_name} protocol is down",
                    severity=Severity.CRITICAL,
                    root_cause="Physical layer issue or no keepalives received",
                    remediation_steps=[
                        "Check physical cable connection",
                        "Verify correct cable type (straight-through vs crossover)",
                        "Check for speed/duplex mismatch",
                        "Verify remote end is up and configured",
                        f"Check errors: show interfaces {intf_name}",
                        "Test with different cable if available"
                    ],
                    device=device,
                    metrics={'admin_status': admin_status, 'oper_status': oper_status}
                ))
            
            # Check for port security violations
            if port_security_violations > 0:
                results.append(self._create_result(
                    category="Interface",
                    issue=f"Port security violations on {intf_name}",
                    severity=Severity.CRITICAL,
                    root_cause=f"{port_security_violations} port security violation(s) detected",
                    remediation_steps=[
                        f"Check violation details: show port-security interface {intf_name}",
                        f"View violated MAC: show port-security address",
                        f"Clear violations: clear port-security sticky interface {intf_name}",
                        f"Re-enable: shutdown, then no shutdown",
                        "Update allowed MAC addresses if needed"
                    ],
                    device=device,
                    metrics={'violations': port_security_violations}
                ))
            
            # Check for interface errors
            if input_errors > 100 or output_errors > 100:
                results.append(self._create_result(
                    category="Interface",
                    issue=f"High error count on {intf_name}",
                    severity=Severity.WARNING,
                    root_cause=f"Input errors: {input_errors}, Output errors: {output_errors}",
                    remediation_steps=[
                        f"Check interface statistics: show interfaces {intf_name}",
                        "Look for CRC errors (bad cable/NIC)",
                        "Check for collisions (duplex mismatch)",
                        "Verify cable quality and length",
                        "Consider replacing cable or transceiver"
                    ],
                    device=device,
                    metrics={'input_errors': input_errors, 'output_errors': output_errors}
                ))
            
            # Check for CRC errors specifically
            if crc_errors > 50:
                results.append(self._create_result(
                    category="Interface",
                    issue=f"CRC errors detected on {intf_name}",
                    severity=Severity.WARNING,
                    root_cause=f"{crc_errors} CRC errors indicate physical layer issues",
                    remediation_steps=[
                        "Replace network cable",
                        "Check for electromagnetic interference",
                        "Verify cable length is within specification",
                        "Test with different transceiver (SFP/GBIC)",
                        "Check for damaged port"
                    ],
                    device=device,
                    metrics={'crc_errors': crc_errors}
                ))
            
            # Check for duplex mismatch
            if duplex_mismatch:
                results.append(self._create_result(
                    category="Interface",
                    issue=f"Duplex mismatch detected on {intf_name}",
                    severity=Severity.CRITICAL,
                    root_cause="Speed/duplex settings don't match between devices",
                    remediation_steps=[
                        f"Check duplex: show interfaces {intf_name}",
                        "Set both ends to same duplex: duplex full",
                        "Or enable auto-negotiation on both ends: duplex auto",
                        "Recommended: Use auto-negotiation when possible",
                        "Hard-code only when auto-negotiation fails"
                    ],
                    device=device,
                    metrics={'duplex_mismatch': True}
                ))
        
        return results
    
    # ==================== IP ADDRESSING DIAGNOSTICS ====================
    
    def _check_ip_addressing(self, device: str, data: Dict) -> List[DiagnosticResult]:
        """Check IP addressing configuration"""
        results = []
        interfaces = data.get('interfaces', {})
        
        for intf_name, intf_data in interfaces.items():
            ip_address = intf_data.get('ip_address')
            subnet_mask = intf_data.get('subnet_mask')
            duplicate_ip = intf_data.get('duplicate_ip', False)
            wrong_subnet = intf_data.get('wrong_subnet', False)
            
            # Check for missing IP address
            if not ip_address or ip_address == '0.0.0.0':
                # Skip if it's a Layer 2 interface (like switchport)
                if not intf_data.get('is_switchport', False):
                    results.append(self._create_result(
                        category="IP Addressing",
                        issue=f"Interface {intf_name} missing IP address",
                        severity=Severity.WARNING,
                        root_cause="No IP address configured on Layer 3 interface",
                        remediation_steps=[
                            f"Configure interface: interface {intf_name}",
                            f"Assign IP: ip address <IP_ADDRESS> <SUBNET_MASK>",
                            f"Enable interface: no shutdown",
                            f"Verify: show ip interface brief"
                        ],
                        device=device,
                        metrics={'ip_address': ip_address}
                    ))
            
            # Check for duplicate IP address
            if duplicate_ip:
                results.append(self._create_result(
                    category="IP Addressing",
                    issue=f"Duplicate IP address detected on {intf_name}",
                    severity=Severity.CRITICAL,
                    root_cause=f"IP address {ip_address} is assigned to multiple devices",
                    remediation_steps=[
                        f"Identify conflicting device: show arp | include {ip_address}",
                        "Check DHCP scope for overlapping static assignments",
                        "Assign unique IP address to one device",
                        "Clear ARP cache: clear arp-cache",
                        "Document IP address assignments to prevent recurrence"
                    ],
                    device=device,
                    metrics={'ip_address': ip_address}
                ))
            
            # Check for incorrect subnet mask
            if wrong_subnet:
                results.append(self._create_result(
                    category="IP Addressing",
                    issue=f"Incorrect subnet configuration on {intf_name}",
                    severity=Severity.CRITICAL,
                    root_cause="Subnet mask doesn't match network design",
                    remediation_steps=[
                        f"Verify correct subnet mask for network segment",
                        f"Check connected devices' subnet masks",
                        f"Correct subnet mask: ip address {ip_address} <CORRECT_MASK>",
                        "Ensure all devices on segment use same mask"
                    ],
                    device=device,
                    metrics={'ip_address': ip_address, 'subnet_mask': subnet_mask}
                ))
        
        return results
    
    # ==================== DEFAULT GATEWAY DIAGNOSTICS ====================
    
    def _check_default_gateway(self, device: str, data: Dict) -> List[DiagnosticResult]:
        """Check default gateway configuration"""
        results = []
        gateway_data = data.get('default_gateway', {})
        
        if not gateway_data:
            return results
        
        configured_gw = gateway_data.get('configured_gateway')
        reachable = gateway_data.get('reachable', True)
        correct_subnet = gateway_data.get('correct_subnet', True)
        
        # Check if default gateway is configured
        if not configured_gw or configured_gw == '0.0.0.0':
            results.append(self._create_result(
                category="Default Gateway",
                issue="No default gateway configured",
                severity=Severity.WARNING,
                root_cause="Missing default route for external connectivity",
                remediation_steps=[
                    "Configure default route: ip route 0.0.0.0 0.0.0.0 <GATEWAY_IP>",
                    "Verify gateway is on directly connected subnet",
                    "Test connectivity: ping <GATEWAY_IP>",
                    "Verify routing: show ip route"
                ],
                device=device,
                metrics={'gateway': configured_gw}
            ))
        
        # Check if gateway is reachable
        elif not reachable:
            results.append(self._create_result(
                category="Default Gateway",
                issue=f"Default gateway {configured_gw} not reachable",
                severity=Severity.CRITICAL,
                root_cause="Cannot reach configured gateway IP address",
                remediation_steps=[
                    f"Test connectivity: ping {configured_gw}",
                    "Verify gateway IP is correct",
                    "Check physical connectivity to gateway",
                    "Verify interface to gateway is up",
                    "Check if gateway device is operational",
                    "Verify no ACLs blocking ICMP"
                ],
                device=device,
                metrics={'gateway': configured_gw, 'reachable': False}
            ))
        
        # Check if gateway is in correct subnet
        elif not correct_subnet:
            results.append(self._create_result(
                category="Default Gateway",
                issue=f"Default gateway {configured_gw} not in local subnet",
                severity=Severity.CRITICAL,
                root_cause="Gateway IP is not on a directly connected network",
                remediation_steps=[
                    "Verify gateway IP address is correct",
                    "Check interface IP and subnet mask",
                    "Ensure gateway is on same subnet as interface",
                    "Reconfigure gateway or interface addressing",
                    f"Show interfaces: show ip interface brief"
                ],
                device=device,
                metrics={'gateway': configured_gw}
            ))
        
        return results
    
    # ==================== NTP DIAGNOSTICS ====================
    
    def _check_ntp(self, device: str, data: Dict) -> List[DiagnosticResult]:
        """Check NTP synchronization status"""
        results = []
        ntp_data = data.get('ntp', {})
        
        if not ntp_data.get('configured', False):
            return results  # NTP not configured, skip checks
        
        synchronized = ntp_data.get('synchronized', False)
        server_ip = ntp_data.get('server_ip')
        server_reachable = ntp_data.get('server_reachable', True)
        stratum = ntp_data.get('stratum', 16)
        acl_blocking = ntp_data.get('acl_blocking', False)
        
        # Check if synchronized
        if not synchronized:
            if acl_blocking:
                results.append(self._create_result(
                    category="NTP",
                    issue="NTP traffic blocked by ACL",
                    severity=Severity.WARNING,
                    root_cause="Access control list blocking NTP packets (UDP 123)",
                    remediation_steps=[
                        "Check ACLs: show ip access-lists",
                        "Identify ACL blocking NTP: show ip interface",
                        "Add NTP permit rule: permit udp any any eq 123",
                        "Or permit NTP server specifically",
                        "Verify: show ntp status"
                    ],
                    device=device,
                    metrics={'server': server_ip}
                ))
            
            elif not server_reachable:
                results.append(self._create_result(
                    category="NTP",
                    issue=f"NTP server {server_ip} not reachable",
                    severity=Severity.WARNING,
                    root_cause="Cannot communicate with configured NTP server",
                    remediation_steps=[
                        f"Test connectivity: ping {server_ip}",
                        "Check routing to NTP server",
                        "Verify NTP server IP is correct",
                        "Check firewall rules between device and server",
                        "Verify NTP server is operational",
                        "Try alternate NTP server if available"
                    ],
                    device=device,
                    metrics={'server': server_ip, 'reachable': False}
                ))
            
            elif stratum == 16:
                results.append(self._create_result(
                    category="NTP",
                    issue="NTP stratum value indicates unsynchronized",
                    severity=Severity.WARNING,
                    root_cause="NTP stratum 16 means clock is unsynchronized",
                    remediation_steps=[
                        "Check NTP associations: show ntp associations",
                        "Verify NTP server configuration",
                        "Check NTP authentication if configured",
                        "Ensure system clock is not too far off (>1000 sec)",
                        "May need to manually set clock closer to correct time",
                        "Wait for synchronization (can take several minutes)"
                    ],
                    device=device,
                    metrics={'stratum': stratum, 'server': server_ip}
                ))
            
            else:
                results.append(self._create_result(
                    category="NTP",
                    issue="NTP not synchronized",
                    severity=Severity.WARNING,
                    root_cause="Clock not syncing with NTP server",
                    remediation_steps=[
                        "Check NTP status: show ntp status",
                        "View associations: show ntp associations detail",
                        f"Verify server configuration: ntp server {server_ip}",
                        "Check for authentication mismatch",
                        "Review NTP version compatibility",
                        "Check system logs for NTP errors"
                    ],
                    device=device,
                    metrics={'server': server_ip, 'synchronized': False}
                ))
        
        return results
    
    # ==================== HELPER METHODS ====================
    
    def _create_result(self, category: str, issue: str, severity: Severity,
                      root_cause: str, remediation_steps: List[str],
                      device: str, metrics: Dict[str, Any] = None) -> DiagnosticResult:
        """Helper to create a diagnostic result"""
        return DiagnosticResult(
            category=category,
            issue=issue,
            severity=severity,
            root_cause=root_cause,
            remediation_steps=remediation_steps,
            affected_devices=[device],
            metrics=metrics or {}
        )


# ==================== analyzers/ipv6.py ====================
"""
IPv6 specific diagnostics analyzer
Covers all base functionality adapted for IPv6
"""
from typing import List, Dict, Any
from models.diagnostic import DiagnosticResult, Severity


class Ipv6Analyzer:
    """Analyzes IPv6 configuration and functionality"""
    
    def __init__(self):
        self.results = []
    
    def analyze(self, device: str, data: Dict[str, Any]) -> List[DiagnosticResult]:
        """Run all IPv6 diagnostics"""
        ipv6_data = data.get('ipv6', {})
        
        if not ipv6_data.get('configured', False):
            return []
        
        self.results = []
        self.results.extend(self._check_global_config(device, ipv6_data))
        self.results.extend(self._check_interfaces(device, ipv6_data))
        self.results.extend(self._check_routing(device, ipv6_data))
        self.results.extend(self._check_neighbor_discovery(device, ipv6_data))
        
        return self.results
    
    def _check_global_config(self, device: str, ipv6_data: Dict) -> List[DiagnosticResult]:
        """Check global IPv6 configuration"""
        results = []
        unicast_routing = ipv6_data.get('unicast_routing_enabled', False)
        cef_enabled = ipv6_data.get('cef_enabled', True)
        
        if not unicast_routing:
            results.append(self._create_result(
                category="IPv6",
                issue="IPv6 unicast routing not enabled",
                severity=Severity.CRITICAL,
                root_cause="IPv6 routing globally disabled",
                remediation_steps=[
                    "Enable IPv6 routing: ipv6 unicast-routing",
                    "Verify: show ipv6 interface brief",
                    "Check routing: show ipv6 route"
                ],
                device=device,
                metrics={'unicast_routing': unicast_routing}
            ))
        
        if not cef_enabled and unicast_routing:
            results.append(self._create_result(
                category="IPv6",
                issue="IPv6 CEF not enabled",
                severity=Severity.WARNING,
                root_cause="CEF switching disabled for IPv6",
                remediation_steps=[
                    "Enable IPv6 CEF: ipv6 cef",
                    "Improves forwarding performance",
                    "Verify: show ipv6 cef"
                ],
                device=device,
                metrics={'cef_enabled': cef_enabled}
            ))
        
        return results
    
    def _check_interfaces(self, device: str, ipv6_data: Dict) -> List[DiagnosticResult]:
        """Check IPv6 interface configuration"""
        results = []
        interfaces = ipv6_data.get('interfaces', {})
        
        for intf_name, intf_data in interfaces.items():
            ipv6_addresses = intf_data.get('ipv6_addresses', [])
            link_local = intf_data.get('link_local_address')
            dad_failed = intf_data.get('dad_failed', False)
            should_have_ipv6 = intf_data.get('should_have_ipv6', False)
            
            # Check for missing IPv6 address
            if should_have_ipv6 and len(ipv6_addresses) == 0:
                results.append(self._create_result(
                    category="IPv6",
                    issue=f"No IPv6 address on interface {intf_name}",
                    severity=Severity.WARNING,
                    root_cause="Interface missing IPv6 configuration",
                    remediation_steps=[
                        f"Configure IPv6 address: interface {intf_name}",
                        "ipv6 address <IPv6_ADDRESS/PREFIX>",
                        "Or use autoconfig: ipv6 address autoconfig",
                        "Or use EUI-64: ipv6 address <PREFIX>::/64 eui-64",
                        "Verify: show ipv6 interface {intf_name}"
                    ],
                    device=device,
                    metrics={'interface': intf_name}
                ))
            
            # Check for missing link-local address
            if not link_local and len(ipv6_addresses) > 0:
                results.append(self._create_result(
                    category="IPv6",
                    issue=f"No link-local address on {intf_name}",
                    severity=Severity.WARNING,
                    root_cause="Link-local address not configured",
                    remediation_steps=[
                        "Link-local required for IPv6 operation",
                        f"Enable IPv6 on interface: interface {intf_name}",
                        "ipv6 enable",
                        "Link-local auto-generated from MAC address",
                        "Or manually: ipv6 address <LINK_LOCAL>/64 link-local"
                    ],
                    device=device,
                    metrics={'interface': intf_name}
                ))
            
            # Check for DAD failures
            if dad_failed:
                results.append(self._create_result(
                    category="IPv6",
                    issue=f"DAD failure on {intf_name}",
                    severity=Severity.CRITICAL,
                    root_cause="Duplicate Address Detection failed - duplicate IPv6 address",
                    remediation_steps=[
                        "Duplicate IPv6 address detected on network",
                        "Identify conflicting device",
                        "Change IPv6 address to unique value",
                        "Check for manual configuration conflicts",
                        "Verify SLAAC not conflicting with static"
                    ],
                    device=device,
                    metrics={'interface': intf_name, 'dad_failed': True}
                ))
        
        return results
    
    def _check_routing(self, device: str, ipv6_data: Dict) -> List[DiagnosticResult]:
        """Check IPv6 routing configuration"""
        results = []
        routes = ipv6_data.get('routes', [])
        default_route = ipv6_data.get('default_route_exists', False)
        routing_protocols = ipv6_data.get('routing_protocols', [])
        
        # Check if no IPv6 routes
        if len(routes) == 0:
            results.append(self._create_result(
                category="IPv6",
                issue="No IPv6 routes in routing table",
                severity=Severity.WARNING,
                root_cause="No IPv6 routes learned or configured",
                remediation_steps=[
                    "Check routing table: show ipv6 route",
                    "Verify routing protocols are running",
                    "Check: show ipv6 protocols",
                    "Configure static routes if needed:",
                    "ipv6 route <DEST/PREFIX> <NEXT_HOP>",
                    "Or configure dynamic routing protocol"
                ],
                device=device,
                metrics={'route_count': 0}
            ))
        
        # Check for missing default route
        if not default_route and len(routes) > 0:
            results.append(self._create_result(
                category="IPv6",
                issue="No IPv6 default route",
                severity=Severity.INFO,
                root_cause="No default route for external IPv6 connectivity",
                remediation_steps=[
                    "Configure default route:",
                    "ipv6 route ::/0 <NEXT_HOP>",
                    "Or learn via routing protocol",
                    "Or via RA (Router Advertisement)"
                ],
                device=device,
                metrics={'default_route': False}
            ))
        
        return results
    
    def _check_neighbor_discovery(self, device: str, ipv6_data: Dict) -> List[DiagnosticResult]:
        """Check IPv6 Neighbor Discovery Protocol"""
        results = []
        nd_data = ipv6_data.get('neighbor_discovery', {})
        
        if not nd_data:
            return results
        
        ra_suppressed = nd_data.get('ra_suppressed', False)
        dad_attempts = nd_data.get('dad_attempts', 1)
        
        # Check if RA is suppressed on router interface
        if ra_suppressed:
            results.append(self._create_result(
                category="IPv6",
                issue="Router Advertisements suppressed",
                severity=Severity.INFO,
                root_cause="IPv6 ND RA suppression configured",
                remediation_steps=[
                    "If hosts need SLAAC, enable RA:",
                    "interface <INTERFACE>",
                    "no ipv6 nd ra suppress",
                    "Configure RA parameters if needed:",
                    "ipv6 nd prefix <PREFIX>",
                    "ipv6 nd ra interval <SECONDS>"
                ],
                device=device,
                metrics={'ra_suppressed': True}
            ))
        
        return results
    
    def _create_result(self, category: str, issue: str, severity: Severity,
                      root_cause: str, remediation_steps: List[str],
                      device: str, metrics: Dict[str, Any] = None) -> DiagnosticResult:
        """Helper to create a diagnostic result"""
        return DiagnosticResult(
            category=category,
            issue=issue,
            severity=severity,
            root_cause=root_cause,
            remediation_steps=remediation_steps,
            affected_devices=[device],
            metrics=metrics or {}
        )


# ==================== engine.py ====================
"""
Main decision tree engine that coordinates all analyzers
"""
from typing import List, Dict, Any
from models.diagnostic import DiagnosticResult


class NetworkDecisionTreeEngine:
    """Main decision tree engine for network diagnostics"""
    
    def __init__(self):
        # Import analyzers here to avoid circular imports
        from analyzers.base import BaseNetworkAnalyzer
        from analyzers.switch import SwitchAnalyzer
        from analyzers.vpn import VpnAnalyzer
        from analyzers.ospf import OspfAnalyzer
        from analyzers.eigrp import EigrpAnalyzer
        from analyzers.bgp import BgpAnalyzer
        from analyzers.isis import IsisAnalyzer
        from analyzers.ipv6 import Ipv6Analyzer
        
        self.analyzers = [
            BaseNetworkAnalyzer(),
            SwitchAnalyzer(),
            VpnAnalyzer(),
            OspfAnalyzer(),
            EigrpAnalyzer(),
            BgpAnalyzer(),
            IsisAnalyzer(),
            Ipv6Analyzer(),
        ]
    
    def analyze(self, telemetry_data: Dict[str, Any]) -> List[DiagnosticResult]:
        """
        Main analysis function - runs all diagnostic checks
        
        Args:
            telemetry_data: Dictionary containing network metrics from Prometheus
            Expected structure:
            {
                'devices': {
                    'router1': {
                        'interfaces': {...},
                        'cpu': 45.2,
                        'ospf': {...},
                        ...
                    }
                }
            }
        
        Returns:
            List of DiagnosticResult objects sorted by severity
        """
        all_results = []
        
        # Run all analyzers on each device
        for device_name, device_data in telemetry_data.get('devices', {}).items():
            for analyzer in self.analyzers:
                results = analyzer.analyze(device_name, device_data)
                all_results.extend(results)
        
        # Sort by severity (Critical -> Warning -> Info)
        severity_order = {'critical': 0, 'warning': 1, 'info': 2}
        all_results.sort(key=lambda r: severity_order.get(r.severity.value, 3))
        
        return all_results


# ==================== formatters.py ====================
"""
Output formatting utilities for diagnostic results
"""
import json
from typing import List, Dict, Any
from models.diagnostic import DiagnosticResult, Severity


class ResultFormatter:
    """Formats diagnostic results for various outputs"""
    
    @staticmethod
    def to_llm_context(results: List[DiagnosticResult]) -> str:
        """
        Format diagnostic results for LLM processing
        Returns a structured text summary suitable for LLM context
        """
        if not results:
            return "No issues detected. All network systems operating normally."
        
        output = f"NETWORK DIAGNOSTIC REPORT - {len(results)} Issue(s) Detected\n"
        output += "=" * 70 + "\n\n"
        
        # Group by severity
        critical = [r for r in results if r.severity == Severity.CRITICAL]
        warnings = [r for r in results if r.severity == Severity.WARNING]
        info = [r for r in results if r.severity == Severity.INFO]
        
        for severity_group, name in [(critical, "CRITICAL"), (warnings, "WARNING"), (info, "INFO")]:
            if severity_group:
                output += f"\n{name} ISSUES ({len(severity_group)}):\n"
                output += "-" * 70 + "\n"
                
                for idx, result in enumerate(severity_group, 1):
                    output += f"\n{idx}. [{result.category}] {result.issue}\n"
                    output += f"   Affected: {', '.join(result.affected_devices)}\n"
                    output += f"   Root Cause: {result.root_cause}\n"
                    output += f"   Resolution Steps:\n"
                    for step_idx, step in enumerate(result.remediation_steps, 1):
                        output += f"      {step_idx}. {step}\n"
                    if result.metrics:
                        output += f"   Metrics: {json.dumps(result.metrics, indent=6)}\n"
        
        return output
    
    @staticmethod
    def to_json(results: List[DiagnosticResult]) -> str:
        """Export results as JSON for API consumption"""
        return json.dumps([r.to_dict() for r in results], indent=2)
    
    @staticmethod
    def to_summary(results: List[DiagnosticResult]) -> Dict[str, Any]:
        """Create a summary report with statistics"""
        critical = len([r for r in results if r.severity == Severity.CRITICAL])
        warnings = len([r for r in results if r.severity == Severity.WARNING])
        info_count = len([r for r in results if r.severity == Severity.INFO])
        
        devices_affected = set()
        categories = {}
        
        for result in results:
            devices_affected.update(result.affected_devices)
            categories[result.category] = categories.get(result.category, 0) + 1
        
        # Calculate health score (0-100)
        # Critical issues: -20 points each
        # Warning issues: -5 points each
        # Info issues: -1 point each
        health_score = max(0, 100 - (critical * 20 + warnings * 5 + info_count * 1))
        
        return {
            'total_issues': len(results),
            'critical': critical,
            'warnings': warnings,
            'info': info_count,
            'devices_affected': list(devices_affected),
            'device_count': len(devices_affected),
            'categories': categories,
            'health_score': health_score,
            'status': 'healthy' if health_score >= 80 else 'degraded' if health_score >= 50 else 'critical'
        }
    
    @staticmethod
    def to_html_dashboard(results: List[DiagnosticResult], summary: Dict[str, Any]) -> str:
        """Generate HTML dashboard snippet"""
        html = f"""
        <div class="network-health-dashboard">
            <div class="health-score">
                <h2>Network Health Score</h2>
                <div class="score {summary['status']}">{summary['health_score']}/100</div>
            </div>
            <div class="issue-summary">
                <div class="critical">{summary['critical']} Critical</div>
                <div class="warning">{summary['warnings']} Warnings</div>
                <div class="info">{summary['info']} Info</div>
            </div>
            <div class="devices-affected">
                <h3>Devices Affected: {summary['device_count']}</h3>
                <p>{', '.join(summary['devices_affected'])}</p>
            </div>
        </div>
        """
        return html


# ==================== USAGE EXAMPLE ====================

if __name__ == "__main__":
    # Example usage demonstrating the modular structure
    
    sample_telemetry = {
        'devices': {
            'router1': {
                'cpu': 85.5,
                'memory': 67.2,
                'interfaces': {
                    'GigabitEthernet0/0': {
                        'admin_status': 'down',
                        'oper_status': 'down',
                        'ip_address': '192.168.1.1',
                        'is_switchport': False
                    },
                    'GigabitEthernet0/1': {
                        'admin_status': 'up',
                        'oper_status': 'up',
                        'ip_address': None,
                        'is_switchport': False
                    }
                },
                'ospf': {
                    'enabled': True,
                    'router_id': '1.1.1.1',
                    'duplicate_router_id': True,
                    'neighbors': [],
                    'interfaces': {},
                    'routes': []
                },
                'bgp': {
                    'enabled': True,
                    'local_as': 65001,
                    'neighbors': [
                        {
                            'neighbor_ip': '10.0.0.2',
                            'neighbor_as': 65002,
                            'state': 'Active',
                            'interface_up': True,
                            'l3_connectivity': False,
                            'acl_blocking': False
                        }
                    ]
                }
            },
            'switch1': {
                'interfaces': {
                    'FastEthernet0/1': {
                        'mode': 'trunk',
                        'trunk_operational': False,
                        'allowed_vlans': [],
                        'native_vlan': 1
                    }
                },
                'vlans': {
                    '10': {'exists': False},
                    '20': {'exists': True, 'status': 'active'}
                },
                'stp': {
                    'enabled': True,
                    'is_root': True,
                    'expected_root': False,
                    'topology_changes': 25,
                    'bpdu_guard_violations': ['Fa0/24']
                }
            }
        }
    }
    
    # Initialize engine
    engine = NetworkDecisionTreeEngine()
    
    # Run analysis
    print("Running network diagnostics...")
    results = engine.analyze(sample_telemetry)
    
    # Format results
    formatter = ResultFormatter()
    
    # Print summary
    summary = formatter.to_summary(results)
    print("\n" + "="*70)
    print("SUMMARY:")
    print(json.dumps(summary, indent=2))
    
    # Print LLM context
    print("\n" + "="*70)
    print("DETAILED REPORT FOR LLM:")
    print(formatter.to_llm_context(results))
    
    # Export JSON (for API)
    # json_output = formatter.to_json(results)
    # with open('diagnostics.json', 'w') as f:
    #     f.write(json_output)
    
    print("\n" + "="*70)
    print(f"Analysis complete: {len(results)} issues detected")



# ==================== analyzers/eigrp.py ====================
"""
EIGRP routing protocol analyzer
"""
from typing import List, Dict, Any
from models.diagnostic import DiagnosticResult, Severity


class EigrpAnalyzer:
    """Analyzes EIGRP routing protocol configuration"""
    
    def __init__(self):
        self.results = []
    
    def analyze(self, device: str, data: Dict[str, Any]) -> List[DiagnosticResult]:
        """Run all EIGRP diagnostics"""
        eigrp_data = data.get('eigrp', {})
        
        if not eigrp_data.get('enabled', False):
            return []
        
        self.results = []
        self.results.extend(self._check_as_number(device, eigrp_data))
        self.results.extend(self._check_neighbors(device, eigrp_data))
        self.results.extend(self._check_interfaces(device, data, eigrp_data))
        self.results.extend(self._check_routes(device, eigrp_data))
        
        return self.results
    
    def _check_as_number(self, device: str, eigrp_data: Dict) -> List[DiagnosticResult]:
        """Check EIGRP AS number configuration"""
        results = []
        as_number = eigrp_data.get('as_number')
        
        if not as_number:
            results.append(self._create_result(
                category="EIGRP",
                issue="EIGRP AS number not configured",
                severity=Severity.CRITICAL,
                root_cause="No EIGRP autonomous system number set",
                remediation_steps=[
                    "Configure EIGRP: router eigrp <AS_NUMBER>",
                    "Add networks: network <IP> <WILDCARD>",
                    "Verify: show ip protocols"
                ],
                device=device,
                metrics={'as_number': as_number}
            ))
        
        return results
    
    def _check_neighbors(self, device: str, eigrp_data: Dict) -> List[DiagnosticResult]:
        """Check EIGRP neighbor relationships"""
        results = []
        neighbors = eigrp_data.get('neighbors', [])
        as_number = eigrp_data.get('as_number')
        
        # Check if no neighbors
        if len(neighbors) == 0:
            results.append(self._create_result(
                category="EIGRP",
                issue="No EIGRP neighbors detected",
                severity=Severity.CRITICAL,
                root_cause="EIGRP adjacency not forming",
                remediation_steps=[
                    "Verify EIGRP is enabled: show ip protocols",
                    f"Check AS number matches neighbors: {as_number}",
                    "Verify network statements: show ip eigrp interfaces",
                    "Check for ACLs blocking multicast (224.0.0.10)",
                    "Verify K-values match (show ip protocols)",
                    "Check authentication if configured",
                    "Ensure interfaces are up and in same subnet"
                ],
                device=device,
                metrics={'as_number': as_number, 'neighbor_count': 0}
            ))
        
        # Check individual neighbors
        for neighbor in neighbors:
            neighbor_ip = neighbor.get('neighbor_ip')
            as_mismatch = neighbor.get('as_mismatch', False)
            k_value_mismatch = neighbor.get('k_value_mismatch', False)
            auth_failure = neighbor.get('auth_failure', False)
            
            if as_mismatch:
                neighbor_as = neighbor.get('neighbor_as')
                results.append(self._create_result(
                    category="EIGRP",
                    issue=f"AS number mismatch with neighbor {neighbor_ip}",
                    severity=Severity.CRITICAL,
                    root_cause=f"Local AS {as_number} != Neighbor AS {neighbor_as}",
                    remediation_steps=[
                        "Verify correct AS number on both devices",
                        f"Change AS if needed: router eigrp {neighbor_as}",
                        "Migrate network statements to correct AS",
                        "Verify: show ip eigrp neighbors"
                    ],
                    device=device,
                    metrics={'local_as': as_number, 'neighbor_as': neighbor_as, 'neighbor_ip': neighbor_ip}
                ))
            
            if k_value_mismatch:
                results.append(self._create_result(
                    category="EIGRP",
                    issue=f"K-value mismatch with neighbor {neighbor_ip}",
                    severity=Severity.CRITICAL,
                    root_cause="EIGRP metric calculation weights don't match",
                    remediation_steps=[
                        "Check K-values: show ip protocols",
                        "Default: K1=1, K2=0, K3=1, K4=0, K5=0",
                        "Match K-values on both devices:",
                        "router eigrp <AS>",
                        "metric weights <TOS> <K1> <K2> <K3> <K4> <K5>",
                        "Recommended: Use default K-values"
                    ],
                    device=device,
                    metrics={'neighbor_ip': neighbor_ip}
                ))
            
            if auth_failure:
                results.append(self._create_result(
                    category="EIGRP",
                    issue=f"Authentication failure with neighbor {neighbor_ip}",
                    severity=Severity.CRITICAL,
                    root_cause="EIGRP authentication mismatch",
                    remediation_steps=[
                        "Verify authentication configuration on both sides",
                        "Check key chain configuration",
                        "Verify key strings match exactly",
                        "Check key chain timing if configured",
                        "Example config:",
                        "key chain EIGRP_KEYS",
                        "  key 1",
                        "    key-string <PASSWORD>",
                        "interface <INTF>",
                        "  ip authentication mode eigrp <AS> md5",
                        "  ip authentication key-chain eigrp <AS> EIGRP_KEYS"
                    ],
                    device=device,
                    metrics={'neighbor_ip': neighbor_ip}
                ))
        
        return results
    
    def _check_interfaces(self, device: str, data: Dict, eigrp_data: Dict) -> List[DiagnosticResult]:
        """Check EIGRP interface participation"""
        results = []
        eigrp_interfaces = eigrp_data.get('interfaces', [])
        device_interfaces = data.get('interfaces', {})
        
        # Check for interfaces that should run EIGRP
        for intf_name, intf_data in device_interfaces.items():
            should_run_eigrp = intf_data.get('should_run_eigrp', False)
            is_up = intf_data.get('oper_status') == 'up'
            
            if should_run_eigrp and is_up and intf_name not in eigrp_interfaces:
                results.append(self._create_result(
                    category="EIGRP",
                    issue=f"Interface {intf_name} not running EIGRP",
                    severity=Severity.WARNING,
                    root_cause="Interface not included in EIGRP network statements",
                    remediation_steps=[
                        "Add interface to EIGRP:",
                        "router eigrp <AS_NUMBER>",
                        "network <IP_ADDRESS> <WILDCARD_MASK>",
                        "Or use classful: network <NETWORK>",
                        "Verify: show ip eigrp interfaces"
                    ],
                    device=device,
                    metrics={'interface': intf_name}
                ))
        
        # Check for passive interfaces
        for intf_name in eigrp_interfaces:
            intf_eigrp_data = eigrp_data.get('interface_details', {}).get(intf_name, {})
            if intf_eigrp_data.get('passive', False):
                should_be_passive = intf_eigrp_data.get('should_be_passive', True)
                if not should_be_passive:
                    results.append(self._create_result(
                        category="EIGRP",
                        issue=f"Interface {intf_name} configured as passive",
                        severity=Severity.INFO,
                        root_cause="Interface won't form EIGRP neighbors",
                        remediation_steps=[
                            "Remove passive if neighbors needed:",
                            "router eigrp <AS_NUMBER>",
                            f"no passive-interface {intf_name}",
                            "Verify: show ip eigrp interfaces"
                        ],
                        device=device,
                        metrics={'interface': intf_name}
                    ))
        
        return results
    
    def _check_routes(self, device: str, eigrp_data: Dict) -> List[DiagnosticResult]:
        """Check EIGRP route learning"""
        results = []
        routes = eigrp_data.get('routes', [])
        neighbors = eigrp_data.get('neighbors', [])
        
        if len(routes) == 0 and len(neighbors) > 0:
            results.append(self._create_result(
                category="EIGRP",
                issue="No EIGRP routes despite having neighbors",
                severity=Severity.WARNING,
                root_cause="Neighbors present but no routes learned",
                remediation_steps=[
                    "Check EIGRP topology: show ip eigrp topology",
                    "Verify routes in topology table",
                    "Check for distribute-lists: show ip protocols",
                    "Verify no route filtering",
                    "Check: show ip route eigrp",
                    "Look for feasible successors"
                ],
                device=device,
                metrics={'neighbor_count': len(neighbors), 'route_count': 0}
            ))
        
        return results
    
    def _create_result(self, category: str, issue: str, severity: Severity,
                      root_cause: str, remediation_steps: List[str],
                      device: str, metrics: Dict[str, Any] = None) -> DiagnosticResult:
        """Helper to create a diagnostic result"""
        return DiagnosticResult(
            category=category,
            issue=issue,
            severity=severity,
            root_cause=root_cause,
            remediation_steps=remediation_steps,
            affected_devices=[device],
            metrics=metrics or {}
        )


# ==================== analyzers/bgp.py ====================
"""
BGP routing protocol analyzer
"""
from typing import List, Dict, Any
from models.diagnostic import DiagnosticResult, Severity


class BgpAnalyzer:
    """Analyzes BGP routing protocol configuration"""
    
    def __init__(self):
        self.results = []
    
    def analyze(self, device: str, data: Dict[str, Any]) -> List[DiagnosticResult]:
        """Run all BGP diagnostics"""
        bgp_data = data.get('bgp', {})
        
        if not bgp_data.get('enabled', False):
            return []
        
        self.results = []
        self.results.extend(self._check_neighbors(device, bgp_data))
        self.results.extend(self._check_prefixes(device, bgp_data))
        
        return self.results
    
    def _check_neighbors(self, device: str, bgp_data: Dict) -> List[DiagnosticResult]:
        """Check BGP neighbor relationships"""
        results = []
        neighbors = bgp_data.get('neighbors', [])
        local_as = bgp_data.get('local_as')
        
        for neighbor in neighbors:
            neighbor_ip = neighbor.get('neighbor_ip')
            neighbor_as = neighbor.get('neighbor_as')
            state = neighbor.get('state', 'Idle')
            is_ibgp = local_as == neighbor_as
            
            if state != 'Established':
                interface_up = neighbor.get('interface_up', True)
                l3_connectivity = neighbor.get('l3_connectivity', True)
                acl_blocking = neighbor.get('acl_blocking', False)
                auth_failure = neighbor.get('auth_failure', False)
                
                if not interface_up:
                    results.append(self._create_result(
                        category="BGP",
                        issue=f"Interface to BGP neighbor {neighbor_ip} is down",
                        severity=Severity.CRITICAL,
                        root_cause="Physical interface to BGP peer not operational",
                        remediation_steps=[
                            "Check interface status: show ip interface brief",
                            "Verify physical connectivity",
                            "Enable interface: no shutdown",
                            "Check for errors: show interfaces"
                        ],
                        device=device,
                        metrics={'neighbor': neighbor_ip, 'state': state}
                    ))
                
                elif not l3_connectivity:
                    results.append(self._create_result(
                        category="BGP",
                        issue=f"No Layer 3 connectivity to {neighbor_ip}",
                        severity=Severity.CRITICAL,
                        root_cause="Cannot reach BGP neighbor IP",
                        remediation_steps=[
                            f"Test connectivity: ping {neighbor_ip}",
                            "Check routing table: show ip route",
                            "Verify correct neighbor IP configured",
                            "For iBGP: Check IGP is providing reachability",
                            "Verify update-source if using loopbacks",
                            "Check for routing issues"
                        ],
                        device=device,
                        metrics={'neighbor': neighbor_ip, 'state': state}
                    ))
                
                elif acl_blocking:
                    results.append(self._create_result(
                        category="BGP",
                        issue=f"ACL blocking BGP to {neighbor_ip}",
                        severity=Severity.CRITICAL,
                        root_cause="Access list blocking TCP port 179 (BGP)",
                        remediation_steps=[
                            "Check ACLs: show ip access-lists",
                            "Check interface ACLs: show ip interface",
                            "Add BGP permit rule: permit tcp any any eq 179",
                            "Also permit: permit tcp any eq 179 any",
                            "Check firewall rules if present"
                        ],
                        device=device,
                        metrics={'neighbor': neighbor_ip, 'state': state}
                    ))
                
                elif auth_failure:
                    results.append(self._create_result(
                        category="BGP",
                        issue=f"Authentication failure with {neighbor_ip}",
                        severity=Severity.CRITICAL,
                        root_cause="BGP MD5 authentication mismatch",
                        remediation_steps=[
                            "Verify password configured on both sides",
                            "Check password matches exactly (case-sensitive)",
                            "Configure: neighbor <IP> password <PASSWORD>",
                            "Remove and reconfigure if needed",
                            "Check logs: show logging | include BGP"
                        ],
                        device=device,
                        metrics={'neighbor': neighbor_ip, 'state': state}
                    ))
                
                elif state == 'Active':
                    results.append(self._create_result(
                        category="BGP",
                        issue=f"BGP neighbor {neighbor_ip} stuck in Active state",
                        severity=Severity.CRITICAL,
                        root_cause="BGP attempting to connect but failing",
                        remediation_steps=[
                            "Active state means trying to establish TCP connection",
                            f"Verify neighbor can reach this device",
                            "Check if neighbor is configured",
                            "For iBGP: Verify update-source configuration",
                            "Check routing in both directions",
                            "Verify no firewall blocking port 179"
                        ],
                        device=device,
                        metrics={'neighbor': neighbor_ip, 'state': state}
                    ))
                
                elif state == 'Idle':
                    results.append(self._create_result(
                        category="BGP",
                        issue=f"BGP neighbor {neighbor_ip} in Idle state",
                        severity=Severity.CRITICAL,
                        root_cause="BGP not attempting connection",
                        remediation_steps=[
                            "Idle means BGP refusing to establish connection",
                            "Check if neighbor statement exists",
                            "Verify neighbor AS number is correct",
                            f"Check: show ip bgp summary",
                            "May need: clear ip bgp <IP>",
                            "Check for admin shutdown: no neighbor <IP> shutdown",
                            "Verify local AS configuration"
                        ],
                        device=device,
                        metrics={'neighbor': neighbor_ip, 'state': state}
                    ))
                
                else:
                    results.append(self._create_result(
                        category="BGP",
                        issue=f"BGP neighbor {neighbor_ip} not established",
                        severity=Severity.CRITICAL,
                        root_cause=f"BGP in {state} state",
                        remediation_steps=[
                            f"Check BGP status: show ip bgp summary",
                            f"Debug BGP: debug ip bgp",
                            "Verify AS numbers",
                            "Check for maximum prefix limit exceeded",
                            "Verify capabilities negotiation",
                            "Check: show ip bgp neighbors <IP>"
                        ],
                        device=device,
                        metrics={'neighbor': neighbor_ip, 'state': state}
                    ))
                
                # iBGP specific checks
                if is_ibgp and state != 'Established':
                    update_source = neighbor.get('update_source')
                    if not update_source:
                        results.append(self._create_result(
                            category="BGP",
                            issue=f"iBGP peer {neighbor_ip} missing update-source",
                            severity=Severity.WARNING,
                            root_cause="No update-source configured for iBGP session",
                            remediation_steps=[
                                "For iBGP, configure update-source:",
                                f"router bgp {local_as}",
                                f"neighbor {neighbor_ip} update-source <LOOPBACK>",
                                "Use loopback for stability",
                                "Ensure IGP provides reachability to loopback"
                            ],
                            device=device,
                            metrics={'neighbor': neighbor_ip, 'is_ibgp': True}
                        ))
        
        return results
    
    def _check_prefixes(self, device: str, bgp_data: Dict) -> List[DiagnosticResult]:
        """Check BGP prefix advertisement and learning"""
        results = []
        advertised_prefixes = bgp_data.get('advertised_prefixes', 0)
        received_prefixes = bgp_data.get('received_prefixes', 0)
        neighbors = bgp_data.get('neighbors', [])
        established_count = len([n for n in neighbors if n.get('state') == 'Established'])
        
        # Check if no prefixes advertised
        if advertised_prefixes == 0:
            results.append(self._create_result(
                category="BGP",
                issue="No prefixes being advertised via BGP",
                severity=Severity.WARNING,
                root_cause="No networks configured for BGP advertisement",
                remediation_steps=[
                    "Check network statements: show ip protocols",
                    "Add networks: router bgp <AS>",
                    "network <PREFIX> mask <MASK>",
                    "Or use redistribution (with caution)",
                    "Verify: show ip bgp"
                ],
                device=device,
                metrics={'advertised': 0}
            ))
        
        # Check if no prefixes received despite established sessions
        if received_prefixes == 0 and established_count > 0:
            results.append(self._create_result(
                category="BGP",
                issue="No BGP prefixes received from peers",
                severity=Severity.WARNING,
                root_cause="No routes learned from BGP neighbors",
                remediation_steps=[
                    "Check if neighbors are advertising routes",
                    "Verify no inbound filtering: show ip bgp neighbors <IP>",
                    "Check route-maps, prefix-lists, filter-lists",
                    "Verify: show ip bgp",
                    "Check neighbor's BGP table: (on neighbor) show ip bgp"
                ],
                device=device,
                metrics={'received': 0, 'established_neighbors': established_count}
            ))
        
        return results
    
    def _create_result(self, category: str, issue: str, severity: Severity,
                      root_cause: str, remediation_steps: List[str],
                      device: str, metrics: Dict[str, Any] = None) -> DiagnosticResult:
        """Helper to create a diagnostic result"""
        return DiagnosticResult(
            category=category,
            issue=issue,
            severity=severity,
            root_cause=root_cause,
            remediation_steps=remediation_steps,
            affected_devices=[device],
            metrics=metrics or {}
        )


# ==================== analyzers/isis.py ====================
"""
IS-IS routing protocol analyzer
"""
from typing import List, Dict, Any
from models.diagnostic import DiagnosticResult, Severity


class IsisAnalyzer:
    """Analyzes IS-IS routing protocol configuration"""
    
    def __init__(self):
        self.results = []
    
    def analyze(self, device: str, data: Dict[str, Any]) -> List[DiagnosticResult]:
        """Run all IS-IS diagnostics"""
        isis_data = data.get('isis', {})
        
        if not isis_data.get('enabled', False):
            return []
        
        self.results = []
        self.results.extend(self._check_net(device, isis_data))
        self.results.extend(self._check_neighbors(device, isis_data))
        self.results.extend(self._check_interfaces(device, data, isis_data))
        
        return self.results
    
    def _check_net(self, device: str, isis_data: Dict) -> List[DiagnosticResult]:
        """Check IS-IS NET (Network Entity Title) configuration"""
        results = []
        net = isis_data.get('net')
        duplicate_system_id = isis_data.get('duplicate_system_id', False)
        
        if not net:
            results.append(self._create_result(
                category="IS-IS",
                issue="No IS-IS NET configured",
                severity=Severity.CRITICAL,
                root_cause="Network Entity Title not set",
                remediation_steps=[
                    "Configure NET: router isis",
                    "net <AREA>.<SYSTEM_ID>.00",
                    "Example: net 49.0001.1921.6800.1001.00",
                    "Area: 49.0001, System ID: 1921.6800.1001"
                ],
                device=device,
                metrics={'net': net}
            ))
        
        if duplicate_system_id:
            results.append(self._create_result(
                category="IS-IS",
                issue="Duplicate IS-IS System ID detected",
                severity=Severity.CRITICAL,
                root_cause="Multiple devices using same System ID",
                remediation_steps=[
                    "Each router needs unique System ID",
                    "Change NET: router isis",
                    "net <AREA>.<UNIQUE_SYSTEM_ID>.00",
                    "Often derived from router's IP address",
                    "Clear IS-IS: clear isis *"
                ],
                device=device,
                metrics={'net': net}
            ))
        
        return results
    
    def _check_neighbors(self, device: str, isis_data: Dict) -> List[DiagnosticResult]:
        """Check IS-IS neighbor adjacencies"""
        results = []
        neighbors = isis_data.get('neighbors', [])
        
        if len(neighbors) == 0:
            results.append(self._create_result(
                category="IS-IS",
                issue="No IS-IS neighbors detected",
                severity=Severity.CRITICAL,
                root_cause="IS-IS adjacency not forming",
                remediation_steps=[
                    "Check interfaces: show isis interface",
                    "Verify IS-IS enabled on interfaces",
                    "Check interface circuit-type matches",
                    "Verify hello intervals match",
                    "Check area IDs are compatible",
                    "Ensure interfaces are up",
                    "Debug: debug isis adj-packets"
                ],
                device=device,
                metrics={'neighbor_count': 0}
            ))
        
        for neighbor in neighbors:
            neighbor_id = neighbor.get('neighbor_id')
            state = neighbor.get('state')
            level_mismatch = neighbor.get('level_mismatch', False)
            mtu_mismatch = neighbor.get('mtu_mismatch', False)
            
            if state != 'UP':
                results.append(self._create_result(
                    category="IS-IS",
                    issue=f"IS-IS neighbor {neighbor_id} not UP",
                    severity=Severity.CRITICAL,
                    root_cause=f"Adjacency in {state} state",
                    remediation_steps=[
                        f"Check neighbor state: show isis neighbors detail",
                        "Verify interface is up",
                        "Check circuit types match",
                        "Verify authentication if configured",
                        "Check MTU matches on both sides"
                    ],
                    device=device,
                    metrics={'neighbor': neighbor_id, 'state': state}
                ))
            
            if level_mismatch:
                results.append(self._create_result(
                    category="IS-IS",
                    issue=f"IS-IS level mismatch with {neighbor_id}",
                    severity=Severity.CRITICAL,
                    root_cause="Circuit type (level) doesn't match",
                    remediation_steps=[
                        "Check circuit type: show isis interface",
                        "Options: level-1, level-2, level-1-2",
                        "Configure: isis circuit-type <TYPE>",
                        "Ensure both sides compatible"
                    ],
                    device=device,
                    metrics={'neighbor': neighbor_id}
                ))
            
            if mtu_mismatch:
                results.append(self._create_result(
                    category="IS-IS",
                    issue=f"MTU mismatch with IS-IS neighbor {neighbor_id}",
                    severity=Severity.WARNING,
                    root_cause="Interface MTU sizes don't match",
                    remediation_steps=[
                        "Check MTU: show interfaces",
                        "Standardize MTU on both sides",
                        "Configure: ip mtu <SIZE>",
                        "Typical: 1500 bytes"
                    ],
                    device=device,
                    metrics={'neighbor': neighbor_id}
                ))
        
        return results
    
    def _check_interfaces(self, device: str, data: Dict, isis_data: Dict) -> List[DiagnosticResult]:
        """Check IS-IS interface configuration"""
        results = []
        isis_interfaces = isis_data.get('interfaces', [])
        device_interfaces = data.get('interfaces', {})
        
        for intf_name, intf_data in device_interfaces.items():
            should_run_isis = intf_data.get('should_run_isis', False)
            is_up = intf_data.get('oper_status') == 'up'
            
            if should_run_isis and is_up and intf_name not in isis_interfaces:
                results.append(self._create_result(
                    category="IS-IS",
                    issue=f"Interface {intf_name} not running IS-IS",
                    severity=Severity.WARNING,
                    root_cause="IS-IS not enabled on interface",
                    remediation_steps=[
                        f"Enable IS-IS: interface {intf_name}",
                        "ip router isis",
                        "Optionally set circuit type",
                        "Verify: show isis interface"
                    ],
                    device=device,
                    metrics={'interface': intf_name}
                ))
        
        return results
    
    def _create_result(self, category: str, issue: str, severity: Severity,
                      root_cause: str, remediation_steps: List[str],
                      device: str, metrics: Dict[str, Any] = None) -> DiagnosticResult:
        """Helper to create a diagnostic result"""
        return DiagnosticResult(
            category=category,
            issue=issue,
            severity=severity,
            root_cause=root_cause,
            remediation_steps=remediation_steps,
            affected_devices=[device],
            metrics=metrics or {}
        )


# ==================== analyzers/switch.py ====================
"""
Layer 2 switching analyzer
Covers: VLANs, Trunks, Port-Channels (EtherChannel), STP
"""
from typing import List, Dict, Any
from models.diagnostic import DiagnosticResult, Severity


class SwitchAnalyzer:
    """Analyzes Layer 2 switching components"""
    
    def __init__(self):
        self.results = []
    
    def analyze(self, device: str, data: Dict[str, Any]) -> List[DiagnosticResult]:
        """Run all switching diagnostics"""
        self.results = []
        
        self.results.extend(self._check_vlans(device, data))
        self.results.extend(self._check_trunks(device, data))
        self.results.extend(self._check_port_channels(device, data))
        self.results.extend(self._check_stp(device, data))
        
        return self.results
    
    # ==================== VLAN DIAGNOSTICS ====================
    
    def _check_vlans(self, device: str, data: Dict) -> List[DiagnosticResult]:
        """Check VLAN configuration and existence"""
        results = []
        vlans = data.get('vlans', {})
        interfaces = data.get('interfaces', {})
        
        # Check if VLANs exist
        for vlan_id, vlan_data in vlans.items():
            if not vlan_data.get('exists', True):
                results.append(self._create_result(
                    category="VLAN",
                    issue=f"VLAN {vlan_id} does not exist",
                    severity=Severity.WARNING,
                    root_cause="VLAN not created in VLAN database",
                    remediation_steps=[
                        f"Create VLAN: vlan {vlan_id}",
                        f"Assign name: name <VLAN_NAME>",
                        f"Exit: exit",
                        f"Verify: show vlan brief"
                    ],
                    device=device,
                    metrics={'vlan_id': vlan_id}
                ))
            
            # Check if VLAN is active
            if vlan_data.get('status') == 'suspended':
                results.append(self._create_result(
                    category="VLAN",
                    issue=f"VLAN {vlan_id} is suspended",
                    severity=Severity.CRITICAL,
                    root_cause="VLAN is administratively suspended",
                    remediation_steps=[
                        f"Activate VLAN: vlan {vlan_id}",
                        f"Remove suspension: state active",
                        f"Verify: show vlan id {vlan_id}"
                    ],
                    device=device,
                    metrics={'vlan_id': vlan_id, 'status': 'suspended'}
                ))
        
        # Check access port VLAN assignments
        for intf_name, intf_data in interfaces.items():
            if intf_data.get('mode') == 'access':
                assigned_vlan = intf_data.get('access_vlan')
                if assigned_vlan and not vlans.get(str(assigned_vlan), {}).get('exists', True):
                    results.append(self._create_result(
                        category="VLAN",
                        issue=f"Interface {intf_name} assigned to non-existent VLAN {assigned_vlan}",
                        severity=Severity.CRITICAL,
                        root_cause=f"Access port configured for VLAN that doesn't exist",
                        remediation_steps=[
                            f"Create VLAN: vlan {assigned_vlan}",
                            f"Or reassign port: interface {intf_name}",
                            f"Change VLAN: switchport access vlan <CORRECT_VLAN>",
                            f"Verify: show vlan brief"
                        ],
                        device=device,
                        metrics={'interface': intf_name, 'vlan': assigned_vlan}
                    ))
        
        return results
    
    # ==================== TRUNK DIAGNOSTICS ====================
    
    def _check_trunks(self, device: str, data: Dict) -> List[DiagnosticResult]:
        """Check trunk configuration and status"""
        results = []
        interfaces = data.get('interfaces', {})
        
        for intf_name, intf_data in interfaces.items():
            if intf_data.get('mode') != 'trunk' and intf_data.get('type') != 'trunk':
                continue
            
            trunk_status = intf_data.get('trunk_operational', False)
            allowed_vlans = intf_data.get('allowed_vlans', [])
            native_vlan = intf_data.get('native_vlan')
            encapsulation = intf_data.get('encapsulation')
            
            # Check trunk operational status
            if not trunk_status:
                results.append(self._create_result(
                    category="Trunk",
                    issue=f"Trunk {intf_name} is not operational",
                    severity=Severity.CRITICAL,
                    root_cause="Trunk link down or misconfigured",
                    remediation_steps=[
                        f"Check physical status: show interfaces {intf_name} status",
                        f"Verify trunk config: show interfaces {intf_name} switchport",
                        "Ensure both ends configured as trunk",
                        f"Set encapsulation: switchport trunk encapsulation dot1q",
                        f"Set mode: switchport mode trunk",
                        "Check for DTP negotiation issues"
                    ],
                    device=device,
                    metrics={'trunk_status': trunk_status}
                ))
            
            # Check allowed VLANs
            if not allowed_vlans or len(allowed_vlans) == 0:
                results.append(self._create_result(
                    category="Trunk",
                    issue=f"No VLANs allowed on trunk {intf_name}",
                    severity=Severity.WARNING,
                    root_cause="All VLANs pruned from trunk",
                    remediation_steps=[
                        f"Check allowed VLANs: show interfaces {intf_name} switchport",
                        f"Allow specific VLANs: switchport trunk allowed vlan <VLAN_LIST>",
                        f"Or allow all: switchport trunk allowed vlan all",
                        "Verify VLANs needed for traffic flow"
                    ],
                    device=device,
                    metrics={'allowed_vlans': allowed_vlans}
                ))
            
            # Check for native VLAN mismatch
            if 'trunk_neighbor' in intf_data:
                neighbor_native = intf_data['trunk_neighbor'].get('native_vlan')
                if native_vlan and neighbor_native and native_vlan != neighbor_native:
                    results.append(self._create_result(
                        category="Trunk",
                        issue=f"Native VLAN mismatch on trunk {intf_name}",
                        severity=Severity.CRITICAL,
                        root_cause=f"Local native VLAN {native_vlan} != Neighbor native VLAN {neighbor_native}",
                        remediation_steps=[
                            "Check CDP/LLDP for native VLAN mismatch warnings",
                            f"Verify native VLAN on both ends",
                            f"Standardize: switchport trunk native vlan <VLAN_ID>",
                            "Recommended: Use native VLAN that is not in use"
                        ],
                        device=device,
                        metrics={'local_native': native_vlan, 'neighbor_native': neighbor_native}
                    ))
            
            # Check encapsulation
            if not encapsulation or encapsulation not in ['dot1q', '802.1q']:
                results.append(self._create_result(
                    category="Trunk",
                    issue=f"Trunk {intf_name} missing or incorrect encapsulation",
                    severity=Severity.WARNING,
                    root_cause="Trunk encapsulation not properly configured",
                    remediation_steps=[
                        f"Set encapsulation: switchport trunk encapsulation dot1q",
                        f"Verify: show interfaces {intf_name} switchport"
                    ],
                    device=device,
                    metrics={'encapsulation': encapsulation}
                ))
        
        return results
    
    # ==================== PORT-CHANNEL DIAGNOSTICS ====================
    
    def _check_port_channels(self, device: str, data: Dict) -> List[DiagnosticResult]:
        """Check EtherChannel/Port-Channel configuration"""
        results = []
        port_channels = data.get('port_channels', {})
        
        for po_name, po_data in port_channels.items():
            protocol = po_data.get('protocol')  # LACP, PAgP, or static
            status = po_data.get('status')
            members = po_data.get('members', [])
            suspended_members = po_data.get('suspended_members', [])
            protocol_mismatch = po_data.get('protocol_mismatch', False)
            
            # Check if port-channel is down
            if status == 'down':
                results.append(self._create_result(
                    category="Port-Channel",
                    issue=f"Port-Channel {po_name} is down",
                    severity=Severity.CRITICAL,
                    root_cause="EtherChannel bundle is not operational",
                    remediation_steps=[
                        f"Check member ports: show etherchannel {po_name} detail",
                        "Verify all member interfaces are up",
                        "Check for configuration mismatches",
                        "Ensure consistent settings (speed, duplex, VLAN)",
                        f"Verify protocol: show etherchannel summary"
                    ],
                    device=device,
                    metrics={'status': status, 'members': len(members)}
                ))
            
            # Check for suspended member ports
            if suspended_members and len(suspended_members) > 0:
                results.append(self._create_result(
                    category="Port-Channel",
                    issue=f"Suspended ports in Port-Channel {po_name}",
                    severity=Severity.WARNING,
                    root_cause=f"{len(suspended_members)} member port(s) suspended due to misconfiguration",
                    remediation_steps=[
                        f"Identify suspended ports: {', '.join(suspended_members)}",
                        "Check for speed/duplex mismatches",
                        "Verify VLAN configuration matches",
                        "Ensure trunk/access mode is consistent",
                        "Check for MTU mismatches",
                        "Verify all members have same channel-group configuration"
                    ],
                    device=device,
                    metrics={'suspended_members': suspended_members}
                ))
            
            # Check for protocol mismatch
            if protocol_mismatch:
                results.append(self._create_result(
                    category="Port-Channel",
                    issue=f"Protocol mismatch in Port-Channel {po_name}",
                    severity=Severity.CRITICAL,
                    root_cause="EtherChannel protocol doesn't match between devices",
                    remediation_steps=[
                        "Verify both ends use same protocol (LACP/PAgP/On)",
                        "Recommended: Use LACP (IEEE 802.3ad) for interoperability",
                        f"Configure LACP: channel-group <NUM> mode active/passive",
                        f"Or PAgP: channel-group <NUM> mode desirable/auto",
                        f"Or static: channel-group <NUM> mode on"
                    ],
                    device=device,
                    metrics={'protocol': protocol}
                ))
            
            # Check if no members
            if not members or len(members) == 0:
                results.append(self._create_result(
                    category="Port-Channel",
                    issue=f"Port-Channel {po_name} has no member ports",
                    severity=Severity.WARNING,
                    root_cause="No interfaces assigned to port-channel",
                    remediation_steps=[
                        f"Assign interfaces to bundle:",
                        f"interface range <INTERFACE_RANGE>",
                        f"channel-group <NUM> mode <active|passive|desirable|auto|on>",
                        f"Verify: show etherchannel summary"
                    ],
                    device=device,
                    metrics={'members': 0}
                ))
        
        return results
    
    # ==================== STP DIAGNOSTICS ====================
    
    def _check_stp(self, device: str, data: Dict) -> List[DiagnosticResult]:
        """Check Spanning Tree Protocol configuration and status"""
        results = []
        stp_data = data.get('stp', {})
        
        if not stp_data.get('enabled', True):
            return results
        
        root_bridge = stp_data.get('is_root', False)
        expected_root = stp_data.get('expected_root', True)
        topology_changes = stp_data.get('topology_changes', 0)
        blocking_ports = stp_data.get('blocking_ports', [])
        bpdu_guard_violations = stp_data.get('bpdu_guard_violations', [])
        root_guard_violations = stp_data.get('root_guard_violations', [])
        
        # Check for unexpected root bridge
        if root_bridge and not expected_root:
            results.append(self._create_result(
                category="STP",
                issue="Device is root bridge but shouldn't be",
                severity=Severity.WARNING,
                root_cause="Incorrect root bridge election",
                remediation_steps=[
                    "Check STP priority: show spanning-tree",
                    "Verify intended root bridge priority is lower",
                    "Set correct root: spanning-tree vlan <VLAN> root primary",
                    "Or set priority manually: spanning-tree vlan <VLAN> priority <VALUE>",
                    "Ensure intended root has lowest priority (0-61440, multiples of 4096)"
                ],
                device=device,
                metrics={'is_root': root_bridge}
            ))
        
        # Check for excessive topology changes
        if topology_changes > 10:
            results.append(self._create_result(
                category="STP",
                issue=f"Excessive STP topology changes: {topology_changes}",
                severity=Severity.WARNING,
                root_cause="Frequent STP recalculations indicating network instability",
                remediation_steps=[
                    "Identify flapping links: show spanning-tree detail",
                    "Check for physical layer issues",
                    "Enable BPDU Guard on access ports: spanning-tree bpduguard enable",
                    "Consider PortFast on access ports: spanning-tree portfast",
                    "Review recent changes to network topology",
                    "Check logs for interface flapping"
                ],
                device=device,
                metrics={'topology_changes': topology_changes}
            ))
        
        # Check for BPDU Guard violations
        if bpdu_guard_violations and len(bpdu_guard_violations) > 0:
            results.append(self._create_result(
                category="STP",
                issue=f"BPDU Guard violations detected",
                severity=Severity.CRITICAL,
                root_cause=f"Ports {', '.join(bpdu_guard_violations)} received BPDUs with BPDU Guard enabled",
                remediation_steps=[
                    "Identify affected ports: show spanning-tree inconsistentports",
                    "Verify no switches connected to access ports",
                    "Remove unauthorized switches if present",
                    "Re-enable ports: shutdown, then no shutdown",
                    "Consider disabling BPDU Guard if switches are intentional"
                ],
                device=device,
                metrics={'violations': bpdu_guard_violations}
            ))
        
        # Check for Root Guard violations
        if root_guard_violations and len(root_guard_violations) > 0:
            results.append(self._create_result(
                category="STP",
                issue=f"Root Guard violations detected",
                severity=Severity.CRITICAL,
                root_cause=f"Ports {', '.join(root_guard_violations)} received superior BPDUs",
                remediation_steps=[
                    "Check affected ports: show spanning-tree inconsistentports",
                    "Verify root bridge priority is correct",
                    "Ensure no rogue devices advertising as root",
                    "Correct root bridge priority if needed",
                    "Ports will recover automatically when violation stops"
                ],
                device=device,
                metrics={'violations': root_guard_violations}
            ))
        
        return results
    
    def _create_result(self, category: str, issue: str, severity: Severity,
                      root_cause: str, remediation_steps: List[str],
                      device: str, metrics: Dict[str, Any] = None) -> DiagnosticResult:
        """Helper to create a diagnostic result"""
        return DiagnosticResult(
            category=category,
            issue=issue,
            severity=severity,
            root_cause=root_cause,
            remediation_steps=remediation_steps,
            affected_devices=[device],
            metrics=metrics or {}
        )


# ==================== analyzers/vpn.py ====================
"""
VPN Technologies analyzer
Covers: GRE Tunnels, DMVPN, IPsec
"""
from typing import List, Dict, Any
from models.diagnostic import DiagnosticResult, Severity


class VpnAnalyzer:
    """Analyzes VPN technologies and tunnel configurations"""
    
    def __init__(self):
        self.results = []
    
    def analyze(self, device: str, data: Dict[str, Any]) -> List[DiagnosticResult]:
        """Run all VPN diagnostics"""
        self.results = []
        
        self.results.extend(self._check_gre_tunnels(device, data))
        self.results.extend(self._check_dmvpn(device, data))
        
        return self.results
    
    # ==================== GRE TUNNEL DIAGNOSTICS ====================
    
    def _check_gre_tunnels(self, device: str, data: Dict) -> List[DiagnosticResult]:
        """Check GRE tunnel configuration and status"""
        results = []
        tunnels = data.get('tunnels', {})
        
        for tunnel_name, tunnel_data in tunnels.items():
            if tunnel_data.get('type') != 'gre':
                continue
            
            status = tunnel_data.get('status', 'down')
            source = tunnel_data.get('source')
            destination = tunnel_data.get('destination')
            source_reachable = tunnel_data.get('source_reachable', True)
            dest_reachable = tunnel_data.get('dest_reachable', True)
            keepalive_enabled = tunnel_data.get('keepalive_enabled', False)
            key_match = tunnel_data.get('key_match', True)
            tunnel_mode = tunnel_data.get('tunnel_mode')
            
            # Check if tunnel is down
            if status == 'down':
                if not source_reachable:
                    results.append(self._create_result(
                        category="GRE Tunnel",
                        issue=f"Tunnel {tunnel_name} source interface down",
                        severity=Severity.CRITICAL,
                        root_cause=f"Source interface {source} is not operational",
                        remediation_steps=[
                            f"Check source interface: show interface {source}",
                            f"Verify source has IP address",
                            f"Enable interface: interface {source}, no shutdown",
                            f"Verify routing to source subnet"
                        ],
                        device=device,
                        metrics={'tunnel': tunnel_name, 'source': source}
                    ))
                
                elif not dest_reachable:
                    results.append(self._create_result(
                        category="GRE Tunnel",
                        issue=f"Tunnel {tunnel_name} destination unreachable",
                        severity=Severity.CRITICAL,
                        root_cause=f"Cannot reach tunnel destination {destination}",
                        remediation_steps=[
                            f"Test connectivity: ping {destination} source {source}",
                            f"Check routing table: show ip route {destination}",
                            "Verify firewall allows GRE (IP protocol 47)",
                            "Check if remote device is operational",
                            "Verify remote tunnel is configured correctly",
                            "Check for NAT issues if traversing NAT"
                        ],
                        device=device,
                        metrics={'tunnel': tunnel_name, 'destination': destination}
                    ))
                
                elif not key_match:
                    results.append(self._create_result(
                        category="GRE Tunnel",
                        issue=f"Tunnel {tunnel_name} key mismatch",
                        severity=Severity.CRITICAL,
                        root_cause="Tunnel keys don't match on both endpoints",
                        remediation_steps=[
                            f"Check local key: show interface {tunnel_name}",
                            "Verify remote device's tunnel key",
                            f"Set matching key: tunnel key <KEY_VALUE>",
                            "Or remove keys from both sides if not needed",
                            "Keys must match exactly on both endpoints"
                        ],
                        device=device,
                        metrics={'tunnel': tunnel_name}
                    ))
                
                elif tunnel_mode != 'gre ip':
                    results.append(self._create_result(
                        category="GRE Tunnel",
                        issue=f"Tunnel {tunnel_name} incorrect mode",
                        severity=Severity.WARNING,
                        root_cause=f"Tunnel mode is {tunnel_mode}, expected 'gre ip'",
                        remediation_steps=[
                            f"Set tunnel mode: interface {tunnel_name}",
                            "tunnel mode gre ip",
                            "Verify both endpoints use same mode",
                            f"Check config: show interface {tunnel_name}"
                        ],
                        device=device,
                        metrics={'tunnel': tunnel_name, 'mode': tunnel_mode}
                    ))
                
                else:
                    results.append(self._create_result(
                        category="GRE Tunnel",
                        issue=f"Tunnel {tunnel_name} is down",
                        severity=Severity.CRITICAL,
                        root_cause="GRE tunnel not operational",
                        remediation_steps=[
                            f"Check tunnel status: show interface {tunnel_name}",
                            f"Verify source: tunnel source {source}",
                            f"Verify destination: tunnel destination {destination}",
                            "Check tunnel mode: tunnel mode gre ip",
                            "Verify IP addressing on tunnel interface",
                            "Enable keepalives: keepalive <SECONDS> <RETRIES>",
                            "Check remote endpoint configuration"
                        ],
                        device=device,
                        metrics={'tunnel': tunnel_name, 'status': status}
                    ))
            
            # Check if keepalives are not enabled (recommendation)
            elif not keepalive_enabled and status == 'up':
                results.append(self._create_result(
                    category="GRE Tunnel",
                    issue=f"Tunnel {tunnel_name} has no keepalives configured",
                    severity=Severity.INFO,
                    root_cause="Keepalives help detect tunnel failures faster",
                    remediation_steps=[
                        f"Consider enabling keepalives: interface {tunnel_name}",
                        "keepalive <PERIOD> <RETRIES>",
                        "Example: keepalive 10 3",
                        "This detects failures in 30 seconds"
                    ],
                    device=device,
                    metrics={'tunnel': tunnel_name}
                ))
        
        return results
    
    # ==================== DMVPN DIAGNOSTICS ====================
    
    def _check_dmvpn(self, device: str, data: Dict) -> List[DiagnosticResult]:
        """Check DMVPN (Dynamic Multipoint VPN) configuration"""
        results = []
        dmvpn_data = data.get('dmvpn', {})
        
        if not dmvpn_data.get('enabled', False):
            return results
        
        is_hub = dmvpn_data.get('is_hub', False)
        nhrp_peers = dmvpn_data.get('nhrp_peers', [])
        ipsec_enabled = dmvpn_data.get('ipsec_enabled', False)
        nhrp_registration = dmvpn_data.get('nhrp_registration', True)
        
        # Check NHRP peer count
        if is_hub and len(nhrp_peers) == 0:
            results.append(self._create_result(
                category="DMVPN",
                issue="DMVPN hub has no registered spokes",
                severity=Severity.CRITICAL,
                root_cause="No spokes registered via NHRP",
                remediation_steps=[
                    "Check NHRP status: show ip nhrp",
                    "Verify tunnel is up: show interface tunnel <NUM>",
                    "Check IPsec if used: show crypto ipsec sa",
                    "Verify spokes can reach hub's public IP",
                    "Check NHRP authentication keys match",
                    "Review hub NHRP configuration"
                ],
                device=device,
                metrics={'peer_count': 0, 'is_hub': True}
            ))
        
        elif not is_hub and not nhrp_registration:
            results.append(self._create_result(
                category="DMVPN",
                issue="DMVPN spoke not registered with hub",
                severity=Severity.CRITICAL,
                root_cause="Spoke unable to register via NHRP",
                remediation_steps=[
                    "Check NHRP registration: show ip nhrp",
                    "Verify tunnel interface is up",
                    "Test connectivity to hub NBMA address",
                    "Verify NHRP NHS (hub) configuration",
                    "Check NHRP authentication keys",
                    "Verify NHRP network-id matches",
                    "Check if IPsec is blocking NHRP"
                ],
                device=device,
                metrics={'registered': False, 'is_hub': False}
            ))
        
        # Check IPsec protection
        if not ipsec_enabled:
            results.append(self._create_result(
                category="DMVPN",
                issue="DMVPN tunnel not protected by IPsec",
                severity=Severity.WARNING,
                root_cause="DMVPN traffic is not encrypted",
                remediation_steps=[
                    "Configure IPsec protection for DMVPN",
                    "Create crypto map or IPsec profile",
                    "Apply to tunnel: tunnel protection ipsec profile <NAME>",
                    "Verify: show crypto ipsec sa",
                    "Recommended for production environments"
                ],
                device=device,
                metrics={'ipsec_enabled': False}
            ))
        
        return results
    
    def _create_result(self, category: str, issue: str, severity: Severity,
                      root_cause: str, remediation_steps: List[str],
                      device: str, metrics: Dict[str, Any] = None) -> DiagnosticResult:
        """Helper to create a diagnostic result"""
        return DiagnosticResult(
            category=category,
            issue=issue,
            severity=severity,
            root_cause=root_cause,
            remediation_steps=remediation_steps,
            affected_devices=[device],
            metrics=metrics or {}
        )


# ==================== analyzers/ospf.py ====================
"""
OSPF routing protocol analyzer
"""
from typing import List, Dict, Any
from models.diagnostic import DiagnosticResult, Severity


class OspfAnalyzer:
    """Analyzes OSPF routing protocol configuration"""
    
    def __init__(self):
        self.results = []
    
    def analyze(self, device: str, data: Dict[str, Any]) -> List[DiagnosticResult]:
        """Run all OSPF diagnostics"""
        ospf_data = data.get('ospf', {})
        
        if not ospf_data.get('enabled', False):
            return []
        
        self.results = []
        self.results.extend(self._check_router_id(device, ospf_data))
        self.results.extend(self._check_neighbors(device, ospf_data))
        self.results.extend(self._check_interfaces(device, data, ospf_data))
        self.results.extend(self._check_areas(device, ospf_data))
        self.results.extend(self._check_routes(device, ospf_data))
        
        return self.results
    
    def _check_router_id(self, device: str, ospf_data: Dict) -> List[DiagnosticResult]:
        """Check OSPF router ID configuration"""
        results = []
        router_id = ospf_data.get('router_id')
        duplicate_rid = ospf_data.get('duplicate_router_id', False)
        
        # Check for duplicate router ID
        if duplicate_rid:
            results.append(self._create_result(
                category="OSPF",
                issue=f"Duplicate OSPF router ID: {router_id}",
                severity=Severity.CRITICAL,
                root_cause="Multiple devices configured with same OSPF router ID",
                remediation_steps=[
                    "Identify all devices with this router ID",
                    f"Change router ID: router ospf <PROCESS_ID>",
                    "router-id <NEW_UNIQUE_IP>",
                    "Clear OSPF process: clear ip ospf process",
                    "Verify: show ip ospf | include Router ID"
                ],
                device=device,
                metrics={'router_id': router_id, 'duplicate': True}
            ))
        
        # Check if router ID is set
        if not router_id or router_id == '0.0.0.0':
            results.append(self._create_result(
                category="OSPF",
                issue="No OSPF router ID configured",
                severity=Severity.WARNING,
                root_cause="Router ID not explicitly set",
                remediation_steps=[
                    "Set router ID: router ospf <PROCESS_ID>",
                    "router-id <UNIQUE_IP>",
                    "Best practice: Use loopback IP",
                    "Clear process: clear ip ospf process"
                ],
                device=device,
                metrics={'router_id': router_id}
            ))
        
        return results
    
    def _check_neighbors(self, device: str, ospf_data: Dict) -> List[DiagnosticResult]:
        """Check OSPF neighbor relationships"""
        results = []
        neighbors = ospf_data.get('neighbors', [])
        
        # Check if no neighbors
        if len(neighbors) == 0:
            results.append(self._create_result(
                category="OSPF",
                issue="No OSPF neighbors detected",
                severity=Severity.CRITICAL,
                root_cause="OSPF adjacency not forming",
                remediation_steps=[
                    "Check interfaces running OSPF: show ip ospf interface brief",
                    "Verify interfaces are up: show ip interface brief",
                    "Enable debugging: debug ip ospf adj",
                    "Check for area mismatches",
                    "Verify network types match",
                    "Check hello/dead timers",
                    "Ensure no ACLs blocking multicast (224.0.0.5, 224.0.0.6)",
                    "Verify authentication if configured"
                ],
                device=device,
                metrics={'neighbor_count': 0}
            ))
        
        # Check individual neighbor states
        for neighbor in neighbors:
            neighbor_id = neighbor.get('neighbor_id')
            state = neighbor.get('state')
            interface = neighbor.get('interface')
            
            # Check for non-FULL state
            if state != 'FULL' and state != '2WAY':  # 2WAY is OK for DR/BDR scenarios
                area_mismatch = neighbor.get('area_mismatch', False)
                hello_mismatch = neighbor.get('hello_mismatch', False)
                network_type_mismatch = neighbor.get('network_type_mismatch', False)
                
                if area_mismatch:
                    results.append(self._create_result(
                        category="OSPF",
                        issue=f"Area mismatch with neighbor {neighbor_id}",
                        severity=Severity.CRITICAL,
                        root_cause="Neighbors configured in different OSPF areas",
                        remediation_steps=[
                            f"Check local area: show ip ospf interface {interface}",
                            "Verify neighbor's area configuration",
                            "Correct area on interface:",
                            f"interface {interface}",
                            "ip ospf <PROCESS> area <CORRECT_AREA>",
                            "Or under router ospf: network <IP> <WILDCARD> area <AREA>"
                        ],
                        device=device,
                        metrics={'neighbor': neighbor_id, 'interface': interface}
                    ))
                
                if hello_mismatch:
                    results.append(self._create_result(
                        category="OSPF",
                        issue=f"Timer mismatch with neighbor {neighbor_id}",
                        severity=Severity.CRITICAL,
                        root_cause="Hello or dead timer mismatch",
                        remediation_steps=[
                            f"Check timers: show ip ospf interface {interface}",
                            "Match neighbor's timers on interface:",
                            f"interface {interface}",
                            "ip ospf hello-interval <SECONDS>",
                            "ip ospf dead-interval <SECONDS>",
                            "Default: hello=10s, dead=40s",
                            "Timers must match for adjacency"
                        ],
                        device=device,
                        metrics={'neighbor': neighbor_id, 'interface': interface}
                    ))
                
                if network_type_mismatch:
                    results.append(self._create_result(
                        category="OSPF",
                        issue=f"Network type mismatch with neighbor {neighbor_id}",
                        severity=Severity.CRITICAL,
                        root_cause="Different OSPF network types configured",
                        remediation_steps=[
                            f"Check network type: show ip ospf interface {interface}",
                            "Common types: broadcast, point-to-point, non-broadcast",
                            "Match neighbor's network type:",
                            f"interface {interface}",
                            "ip ospf network <point-to-point|broadcast|non-broadcast>",
                            "Point-to-point recommended for WAN links"
                        ],
                        device=device,
                        metrics={'neighbor': neighbor_id, 'interface': interface}
                    ))
                
                # Generic neighbor state issue
                if not area_mismatch and not hello_mismatch and not network_type_mismatch:
                    results.append(self._create_result(
                        category="OSPF",
                        issue=f"Neighbor {neighbor_id} stuck in {state} state",
                        severity=Severity.WARNING,
                        root_cause=f"OSPF adjacency not reaching FULL state",
                        remediation_steps=[
                            f"Check neighbor details: show ip ospf neighbor {neighbor_id}",
                            "Debug adjacency: debug ip ospf adj",
                            "Verify MTU matches on both sides",
                            "Check for duplicate router IDs",
                            "Verify no authentication mismatch",
                            "Check interface for errors",
                            "May need: clear ip ospf process"
                        ],
                        device=device,
                        metrics={'neighbor': neighbor_id, 'state': state, 'interface': interface}
                    ))
        
        return results
    
    def _check_interfaces(self, device: str, data: Dict, ospf_data: Dict) -> List[DiagnosticResult]:
        """Check OSPF interface participation"""
        results = []
        ospf_interfaces = ospf_data.get('interfaces', {})
        device_interfaces = data.get('interfaces', {})
        
        # Check if expected interfaces are running OSPF
        for intf_name, intf_data in device_interfaces.items():
            should_run_ospf = intf_data.get('should_run_ospf', False)
            is_up = intf_data.get('oper_status') == 'up'
            
            if should_run_ospf and is_up and intf_name not in ospf_interfaces:
                results.append(self._create_result(
                    category="OSPF",
                    issue=f"Interface {intf_name} not running OSPF",
                    severity=Severity.WARNING,
                    root_cause="Interface not included in OSPF process",
                    remediation_steps=[
                        "Add interface to OSPF:",
                        "Option 1 - Interface command:",
                        f"interface {intf_name}",
                        "ip ospf <PROCESS_ID> area <AREA>",
                        "Option 2 - Network command:",
                        "router ospf <PROCESS_ID>",
                        "network <IP> <WILDCARD> area <AREA>",
                        "Verify: show ip ospf interface"
                    ],
                    device=device,
                    metrics={'interface': intf_name}
                ))
        
        # Check for passive interfaces that shouldn't be
        for intf_name, intf_ospf_data in ospf_interfaces.items():
            if intf_ospf_data.get('passive', False):
                should_be_passive = intf_ospf_data.get('should_be_passive', True)
                if not should_be_passive:
                    results.append(self._create_result(
                        category="OSPF",
                        issue=f"Interface {intf_name} unnecessarily passive",
                        severity=Severity.INFO,
                        root_cause="Interface configured as passive but should form adjacencies",
                        remediation_steps=[
                            f"Remove passive: router ospf <PROCESS_ID>",
                            f"no passive-interface {intf_name}",
                            "Verify: show ip ospf interface"
                        ],
                        device=device,
                        metrics={'interface': intf_name}
                    ))
        
        return results
    
    def _check_areas(self, device: str, ospf_data: Dict) -> List[DiagnosticResult]:
        """Check OSPF area configuration"""
        results = []
        areas = ospf_data.get('areas', {})
        
        for area_id, area_data in areas.items():
            area_type = area_data.get('type', 'normal')  # normal, stub, nssa, totally-stub
            is_abr = area_data.get('is_abr', False)
            
            # Check if stub area is properly configured
            if area_type in ['stub', 'totally-stub'] and not is_abr:
                if not area_data.get('default_route_received', False):
                    results.append(self._create_result(
                        category="OSPF",
                        issue=f"No default route in stub area {area_id}",
                        severity=Severity.WARNING,
                        root_cause="Stub area not receiving default route from ABR",
                        remediation_steps=[
                            "On ABR, verify stub configuration:",
                            f"router ospf <PROCESS_ID>",
                            f"area {area_id} stub",
                            f"For totally stub: area {area_id} stub no-summary",
                            "ABR should inject default route automatically",
                            "Check ABR configuration and connectivity"
                        ],
                        device=device,
                        metrics={'area': area_id, 'type': area_type}
                    ))
        
        return results
    
    def _check_routes(self, device: str, ospf_data: Dict) -> List[DiagnosticResult]:
        """Check OSPF route learning"""
        results = []
        routes = ospf_data.get('routes', [])
        neighbors = ospf_data.get('neighbors', [])
        filter_lists = ospf_data.get('filter_lists', {})
        
        # Check if no routes despite having neighbors
        if len(routes) == 0 and len(neighbors) > 0:
            if filter_lists.get('incoming') or filter_lists.get('outgoing'):
                results.append(self._create_result(
                    category="OSPF",
                    issue="OSPF routes being filtered",
                    severity=Severity.WARNING,
                    root_cause="Distribute-list blocking OSPF routes",
                    remediation_steps=[
                        "Check filters: show ip protocols",
                        "Review distribute-list configuration",
                        "Verify ACLs or prefix-lists",
                        "Temporarily remove to test:",
                        "router ospf <PROCESS_ID>",
                        "no distribute-list <ACL> in",
                        "Check: show ip route ospf"
                    ],
                    device=device,
                    metrics={'filter_lists': filter_lists}
                ))
            else:
                results.append(self._create_result(
                    category="OSPF",
                    issue="No OSPF routes learned despite neighbors",
                    severity=Severity.WARNING,
                    root_cause="Neighbors present but no routes in routing table",
                    remediation_steps=[
                        "Check OSPF database: show ip ospf database",
                        "Verify routes in database",
                        "Check administrative distance",
                        "Look for better routes from other protocols",
                        "Verify no distribute-lists filtering",
                        "Check: show ip route ospf"
                    ],
                    device=device,
                    metrics={'neighbor_count': len(neighbors), 'route_count': 0}
                ))
        
        return results
    
    def _create_result(self, category: str, issue: str, severity: Severity,
                      root_cause: str, remediation_steps: List[str],
                      device: str, metrics: Dict[str, Any] = None) -> DiagnosticResult:
        """Helper to create a diagnostic result"""
        return DiagnosticResult(
            category=category,
            issue=issue,
            severity=severity,
            root_cause=root_cause,
            remediation_steps=remediation_steps,
            affected_devices=[device],
            metrics=metrics or {}
        )