import time

from netmiko import ConnectHandler
from netmiko.cli_tools.outputters import output_raw


def enableEIGRPdebug(conn):
    conn.send_command('debug eigrp packets')

def disabledebug(conn):
    conn.send_command('no debug all')

def gatherEIGRPdebug(conn):
    time.sleep(10)
    output =   conn.send_command('show logging')
    return output

def parse_ospf_debug(debug_output):
    # Example parse for hello packet mismatch messages
    mismatches = []
    lines = debug_output.splitlines()
    for line in lines:
        if "K-value mismatch" in line:
            mismatches.append("k-value mismatch")
        if "not on common subnet" in line:
            mismatches.append("wrong subnet")
    return mismatches

def getEIGRPconfigs(conn):
    return conn.send_command("show running-config | section router eigrp")

def pushEIGRPconfig(conn, commands):
    conn.send_config_set(commands)
    conn.save_config()

def troubleshoot_and_fix_ospf(device_ip, username, password, enable_pass, neighbor):
    device = {
        "device_type": "cisco_ios",
        "ip": device_ip,
        "username": username,
        "password": password,
        "secret": enable_pass,
    }
    conn = ConnectHandler(**device)
    conn.enable()

    print("Enabling OSPF hello debugging...")
    enableEIGRPdebug(conn)

    print(f"Collecting debug output for 10 seconds...")
    debug_output = gatherEIGRPdebug(conn)

    print("Disabling debugging to avoid performance impact...")
    disabledebug(conn)

    print("Parsing debug output for mismatches...")
    mismatches = parse_ospf_debug(debug_output)
    print("Detected OSPF mismatches:", mismatches)

    commands_to_fix = []

    interface = "GigabitEthernet0/1"

    if "k-value mismatch" in mismatches:
        commands_to_fix += [
            f"router eigrp 1",
            "metric weights 1 0 1 0 0"
        ]

    if "wrong subnet" in mismatches:
        commands_to_fix += [
            f"interface {interface}",
            "ip address {ip address}"
        ]

    if commands_to_fix:
        print(f"Applying configuration fixes on device {device_ip}...")
        pushEIGRPconfig(conn, commands_to_fix)
        conn.save_config()
    else:
        print("No config changes required based on debug output.")

    conn.disconnect()
