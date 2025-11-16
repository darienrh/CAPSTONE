import time

from netmiko import ConnectHandler
from netmiko.cli_tools.outputters import output_raw


def enableospfhellodebug(conn):
    conn.send_command('debug ospf hello')

def disabledebug(conn):
    conn.send_command('no debug all')

def gatherospfdebug(conn):
    time.sleep(10)
    output =   conn.send_command('show logging')
    return output

def parse_ospf_debug(debug_output):
    # Example parse for hello packet mismatch messages
    mismatches = []
    lines = debug_output.splitlines()
    for line in lines:
        if "Hello interval mismatch" in line:
            mismatches.append("hello interval mismatch")
        if "Dead interval mismatch" in line:
            mismatches.append("dead interval mismatch")
    return mismatches

def getospfconfigs(conn):
    return conn.send_command("show running-config | section router ospf")

def pushospfconfig(conn, commands):
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
    enableospfhellodebug(conn)

    print(f"Collecting debug output for 10 seconds...")
    debug_output = gatherospfdebug(conn)

    print("Disabling debugging to avoid performance impact...")
    disabledebug(conn)

    print("Parsing debug output for mismatches...")
    mismatches = parse_ospf_debug(debug_output)
    print("Detected OSPF mismatches:", mismatches)

    commands_to_fix = []

    interface = "GigabitEthernet0/1"
    area = "0"

    if "hello interval mismatch" in mismatches:
        commands_to_fix += [
            f"interface {interface}",
            "ip ospf hello-interval 10"
        ]

    if "dead interval mismatch" in mismatches:
        commands_to_fix += [
            f"interface {interface}",
            "ip ospf dead-interval 40"
        ]

    if commands_to_fix:
        print(f"Applying configuration fixes on device {device_ip}...")
        pushospfconfig(conn, commands_to_fix)
        conn.save_config()
    else:
        print("No config changes required based on debug output.")

    conn.disconnect()