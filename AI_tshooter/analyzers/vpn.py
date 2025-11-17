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