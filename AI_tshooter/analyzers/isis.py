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