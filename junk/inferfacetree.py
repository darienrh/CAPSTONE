import time

from netmiko import ConnectHandler
from netmiko.cli_tools.outputters import output_raw

def show_interface(conn):
    conn.send_command('show ip int brief')

def disable_debug(conn):
    conn.send_command('no debug all')

def gather_interface_states(conn):
    time.sleep(10)
    output =   conn.send_command('show logging')
    return output

def troubleshoot_interface(conn):
    output = show_interface(conn)
    lines = output.splitlines()

    fixed_interface = []

    for line in lines:
        parts = line.split()
        if len(parts) < 6:
            continue
    intf=parts[0]
    line_status = parts[-2].lower()
    protocol = parts[-1].lower()

    if line_status == 'down' and protocol == 'down':
        print('Interface down for {intf}, tyring no shutdown')
        conn.send_command([f'config t'
                           f'interface {intf}'
                           "no shut"])
    fixed_interface.append(intf)
    return fixed_interface
