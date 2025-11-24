import ospftree as ospf_issues
import inferfacetree as intefacetree_issues

def OSPFdecisiontree(ospf_status):
    if not ospf_status['ping_neighbor']:
        return "Layer 1/2 connectivity issue. Check cables, interfaces, and IP connectivity."
    if not ospf_status['protocol_89']:
        return "OSPF packets blocked. Check ACL/firewall for IP protocol 89."
    if ospf_status['neighbor_state'] == "DOWN":
        if not ospf_status['hello_packets']:
            return "No Hello packets. Check OSPF configuration, network types, and timers."
        if ospf_status['area_id_mismatch']:
            return "Area ID mismatch. Correct area configuration on both sides."
        if ospf_status['subnet_mismatch']:
            return "Subnet mask mismatch. Ensure matched subnet masks."
        if ospf_status['timer_mismatch']:
            return "Hello/dead interval mismatch. Configure timers to match."
        return "Unknown reason for neighbor-down. Use debug and logs for deeper inspection."
    if ospf_status['neighbor_state'] == "EXSTART" or ospf_status['neighbor_state'] == "EXCHANGE":
        return "Adjacency stuck in EXSTART/EXCHANGE. Possible MTU mismatch."
    if ospf_status['routes_missing']:
        return "Route not in OSPF table. Check network statements and passive interfaces."
    return "OSPF appears operational."

def Intefacedecisiontree(status):
    if status['down interface']:
        intefacetree_issues.troubleshoot_interface(status)
        return "Attempted to no shutdown interface."

# Example usage:
ospf_status = {
    'ping_neighbor': True,
    'protocol_89': True,
    'neighbor_state': "DOWN",
    'hello_packets': True,
    'area_id_mismatch': False,
    'subnet_mismatch': True,
    'timer_mismatch': False,
    'routes_missing': False
}

def main_troubleshoot(status_info, protocol):
    if protocol == 'OSPF':
        return OSPFdecisiontree(status_info)
    elif protocol == 'BGP':
        return BGPdecisiontree(status_info)
    elif protocol == 'OSPF':
        return Intefacedecisiontree(status_info)
    else:
        return "Unsupported protocol for troubleshooting."