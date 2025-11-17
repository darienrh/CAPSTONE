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