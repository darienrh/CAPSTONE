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