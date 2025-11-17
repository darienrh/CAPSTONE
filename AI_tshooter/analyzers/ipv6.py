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