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