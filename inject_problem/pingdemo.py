#!/usr/bin/env python3
"""
GNS3 Ping Demonstration - Simplified and Fixed
"""

import warnings
warnings.filterwarnings('ignore')

import telnetlib
import requests
from requests.auth import HTTPBasicAuth
import time
import sys


class GNS3Demo:
    
    def __init__(self, gns3_url="http://localhost:3080", username="admin", 
                 password="qrWaprDfbrbUaYw8eMZTRz6cXRfV96PltLIT0gzTIMo7u5vksgVCIjz1iOSIbelS"):
        self.gns3_url = gns3_url.rstrip('/')
        self.api_base = f"{self.gns3_url}/v2"
        self.project_id = None
        self.nodes = {}
        self.auth = HTTPBasicAuth(username, password) if username else None
        
    def connect(self):
        """Connect to GNS3 and load project"""
        try:
            # Test connection
            response = requests.get(f"{self.api_base}/version", auth=self.auth, timeout=5)
            if response.status_code != 200:
                print("Failed to connect to GNS3")
                return False
            
            version = response.json().get('version', 'unknown')
            print(f"Connected to GNS3 v{version}")
            
            # Get opened project
            response = requests.get(f"{self.api_base}/projects", auth=self.auth)
            projects = response.json()
            
            for project in projects:
                if project['status'] == 'opened':
                    self.project_id = project['project_id']
                    print(f"Using project: {project['name']}")
                    
                    # Load nodes
                    response = requests.get(f"{self.api_base}/projects/{self.project_id}/nodes", auth=self.auth)
                    nodes = response.json()
                    
                    for node in nodes:
                        self.nodes[node['name']] = node
                    
                    print(f"Found {len(nodes)} devices\n")
                    return True
            
            print("No opened project found")
            return False
            
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def get_console_port(self, device_name):
        """Get console port for device"""
        node = self.nodes.get(device_name)
        return node.get('console') if node else None
    
    def clear_line_and_reset(self, tn):
        """Clear any partial commands and return to privileged exec mode"""
        # Send backspaces to clear any typed commands
        for _ in range(10):
            tn.write(b'\x08')  # Backspace character
            time.sleep(0.05)
        
        # Send Ctrl+C to cancel any running command
        tn.write(b'\x03')
        time.sleep(0.3)
        
        # Clear buffer
        tn.read_very_eager()
        
        # Send 'end' to get back to privileged exec mode
        tn.write(b'end\r\n')
        time.sleep(0.5)
        tn.read_very_eager()
        
        # Send 'enable' to make sure we're in privileged mode
        tn.write(b'enable\r\n')
        time.sleep(0.3)
        tn.read_very_eager()
        
        # One more newline to get a fresh prompt
        tn.write(b'\r\n')
        time.sleep(0.3)
        tn.read_very_eager()
    
    def shutdown_interface(self, device_name, interface):
        """Shutdown an interface"""
        console_port = self.get_console_port(device_name)
        if not console_port:
            return False
        
        try:
            tn = telnetlib.Telnet('localhost', console_port, timeout=10)
            
            # Clear line and reset to base prompt
            self.clear_line_and_reset(tn)
            
            # Execute commands from privileged exec mode
            commands = ["configure terminal", 
                       f"interface {interface}", 
                       "shutdown", 
                       "end"]
            
            print("Executing commands:")
            for cmd in commands:
                print(f"  -> {cmd}")
                tn.write(cmd.encode('ascii') + b'\r\n')
                time.sleep(0.5)
                tn.read_very_eager()
            
            tn.close()
            print(f"Interface {interface} shut down")
            return True
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def no_shutdown_interface(self, device_name, interface):
        """Bring up an interface"""
        console_port = self.get_console_port(device_name)
        if not console_port:
            return False
        
        try:
            tn = telnetlib.Telnet('localhost', console_port, timeout=10)
            
            # Clear line and reset to base prompt
            self.clear_line_and_reset(tn)
            
            # Execute commands from privileged exec mode
            commands = ["configure terminal",
                       f"interface {interface}", 
                       "no shutdown", 
                       "end"]
            
            print("Executing commands:")
            for cmd in commands:
                print(f"  -> {cmd}")
                tn.write(cmd.encode('ascii') + b'\r\n')
                time.sleep(0.5)
                tn.read_very_eager()
            
            tn.close()
            print(f"Interface {interface} brought up")
            return True
        except Exception as e:
            print(f"Error: {e}")
            return False
    
    def ping(self, source_device, dest_ip, count=5):
        """Ping from source to destination"""
        print(f"Pinging {dest_ip} from {source_device}...")
        
        console_port = self.get_console_port(source_device)
        if not console_port:
            print("No console port")
            return False
        
        try:
            tn = telnetlib.Telnet('localhost', console_port, timeout=10)
            
            # Clear line and reset to base prompt
            self.clear_line_and_reset(tn)
            
            # Send ping command
            command = f"ping {dest_ip} repeat {count}"
            tn.write(command.encode('ascii') + b'\r\n')
            
            # Wait for ping to complete
            time.sleep(count * 2 + 3)
            
            # Read output
            output = tn.read_very_eager().decode('ascii', errors='ignore')
            tn.close()
            
            if "Success rate is" in output:
                for line in output.split('\n'):
                    if "Success rate is" in line:
                        print(line.strip())
                        return "100 percent" in line
                return False
            else:
                print("No response")
                return False
                
        except Exception as e:
            print(f"Error: {e}")
            return False


def main():
    print("\nGNS3 Network Problem Injection Demo")
    print("=" * 60)
    
    R1 = "R1"
    R2_IP = "192.168.2.2"
    INTERFACE = "FastEthernet0/0"
    
    # Initialize
    demo = GNS3Demo()
    if not demo.connect():
        sys.exit(1)
    
    # STEP 1: Baseline ping
    print("\nSTEP 1: Baseline - Test connectivity")
    print("-" * 60)
    input("Press Enter to continue...")
    success1 = demo.ping(R1, R2_IP)
    print(f"Result: {'PASS' if success1 else 'FAIL'}")
    
    # STEP 2: Shutdown interface
    print(f"\n\nSTEP 2: Shutdown {INTERFACE}")
    print("-" * 60)
    input("Press Enter to continue...")
    demo.shutdown_interface(R1, INTERFACE)
    time.sleep(3)
    
    # STEP 3: Verify failure
    print("\n\nSTEP 3: Verify connectivity is broken")
    print("-" * 60)
    input("Press Enter to continue...")
    success2 = demo.ping(R1, R2_IP)
    print(f"Result: {'FAIL (expected)' if not success2 else 'PASS (unexpected!)'}")
    
    # STEP 4: Restore interface
    print(f"\n\nSTEP 4: Restore {INTERFACE}")
    print("-" * 60)
    input("Press Enter to continue...")
    demo.no_shutdown_interface(R1, INTERFACE)
    print("Waiting for interface to come up...")
    time.sleep(8)  # Increased wait time for interface and routing to stabilize
    
    # STEP 5: Verify restoration
    print("\n\nSTEP 5: Verify connectivity is restored")
    print("-" * 60)
    input("Press Enter to continue...")
    success3 = demo.ping(R1, R2_IP)
    print(f"Result: {'PASS' if success3 else 'FAIL'}")
    
    # Summary
    print("\n\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Step 1 - Baseline:        {'PASS' if success1 else 'FAIL'}")
    print(f"Step 3 - After Shutdown:  {'PASS (failed as expected)' if not success2 else 'FAIL (still working)'}")
    print(f"Step 5 - After Restore:   {'PASS' if success3 else 'FAIL'}")
    print("=" * 60)
    
    if success1 and not success2 and success3:
        print("\nSUCCESS - Demo completed correctly!")
    else:
        print("\nUnexpected results")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)