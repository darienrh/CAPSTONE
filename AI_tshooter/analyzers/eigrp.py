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