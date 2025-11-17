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