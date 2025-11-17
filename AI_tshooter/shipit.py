"""
Configuration deployment module
Connects to network devices and applies configuration changes
"""

import time
from typing import List, Dict, Any, Optional
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
from models.diagnostic import ConfigurationFix
import json
import os
from datetime import datetime


class ConfigDeployer:
    """Handles deployment of configuration changes to network devices"""
    
    def __init__(self, device_credentials: Dict[str, Dict[str, str]] = None):
        """
        Initialize deployer with device credentials
        
        Args:
            device_credentials: Dictionary mapping device names to connection params
                Example:
                {
                    'router1': {
                        'device_type': 'cisco_ios',
                        'host': '192.168.1.1',
                        'username': 'admin',
                        'password': 'password',
                        'secret': 'enable_password'  # optional
                    }
                }
        """
        self.device_credentials = device_credentials or {}
        self.deployment_log = []
    
    def deploy_fix(self, fix: ConfigurationFix) -> Dict[str, Any]:
        """
        Deploy a single configuration fix to a device
        
        Args:
            fix: ConfigurationFix object with commands to deploy
            
        Returns:
            Dictionary with deployment result
        """
        device = fix.device
        
        if device not in self.device_credentials:
            return {
                'device': device,
                'success': False,
                'message': f'No credentials found for device {device}',
                'output': None
            }
        
        try:
            print(f"  → Connecting to {device}...")
            
            # Establish connection
            connection = ConnectHandler(**self.device_credentials[device])
            
            print(f"  → Connected. Entering enable mode...")
            connection.enable()
            
            # Send commands
            print(f"  → Applying {len(fix.commands)} command(s)...")
            output = connection.send_config_set(fix.commands)
            
            # Run verification commands if provided
            verification_output = ""
            if fix.verification_commands:
                print(f"  → Running {len(fix.verification_commands)} verification command(s)...")
                for verify_cmd in fix.verification_commands:
                    verification_output += connection.send_command(verify_cmd)
                    verification_output += "\n" + "="*50 + "\n"
            
            # Save configuration
            print(f"  → Saving configuration...")
            save_output = connection.save_config()
            
            connection.disconnect()
            
            result = {
                'device': device,
                'success': True,
                'message': 'Configuration applied successfully',
                'output': output,
                'verification': verification_output,
                'save_output': save_output,
                'timestamp': datetime.now().isoformat()
            }
            
            self.deployment_log.append(result)
            return result
            
        except NetmikoTimeoutException:
            return {
                'device': device,
                'success': False,
                'message': f'Connection timeout to {device}',
                'output': None
            }
        
        except NetmikoAuthenticationException:
            return {
                'device': device,
                'success': False,
                'message': f'Authentication failed for {device}',
                'output': None
            }
        
        except Exception as e:
            return {
                'device': device,
                'success': False,
                'message': f'Error: {str(e)}',
                'output': None
            }
    
    def deploy_multiple(self, fixes: List[ConfigurationFix], 
                       parallel: bool = False) -> List[Dict[str, Any]]:
        """
        Deploy multiple configuration fixes
        
        Args:
            fixes: List of ConfigurationFix objects
            parallel: If True, deploy to devices in parallel (future enhancement)
            
        Returns:
            List of deployment results
        """
        results = []
        
        print(f"\n{'='*70}")
        print(f"Deploying configurations to {len(fixes)} device(s)")
        print(f"{'='*70}\n")
        
        for idx, fix in enumerate(fixes, 1):
            print(f"[{idx}/{len(fixes)}] Deploying to {fix.device}")
            result = self.deploy_fix(fix)
            results.append(result)
            
            if result['success']:
                print(f"  ✅ Success\n")
            else:
                print(f"  ❌ Failed: {result['message']}\n")
            
            # Small delay between devices
            if idx < len(fixes):
                time.sleep(1)
        
        return results
    
    def save_deployment_log(self, filename: str = None):
        """Save deployment log to file"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"responses/deployment_log_{timestamp}.json"
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(self.deployment_log, f, indent=2)
        
        print(f"📝 Deployment log saved to: {filename}")
        return filename
    
    def create_rollback_script(self, fixes: List[ConfigurationFix], 
                               filename: str = None) -> str:
        """
        Create a rollback script from configuration fixes
        
        Args:
            fixes: List of applied fixes
            filename: Output filename for rollback script
            
        Returns:
            Path to rollback script file
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"responses/rollback_{timestamp}.txt"
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            f.write("# Rollback Script\n")
            f.write(f"# Generated: {datetime.now().isoformat()}\n")
            f.write(f"# Use this script to revert changes if needed\n\n")
            
            for fix in fixes:
                f.write(f"\n{'='*70}\n")
                f.write(f"# Device: {fix.device}\n")
                f.write(f"# Diagnostic: {fix.diagnostic_id}\n")
                f.write(f"{'='*70}\n\n")
                
                if fix.rollback_commands:
                    for cmd in fix.rollback_commands:
                        f.write(f"{cmd}\n")
                else:
                    f.write("# No rollback commands provided\n")
                    f.write("# Manual rollback may be required\n")
        
        print(f"📝 Rollback script saved to: {filename}")
        return filename


def load_device_credentials(config_file: str = "device_credentials.json") -> Dict[str, Dict[str, str]]:
    """
    Load device credentials from JSON file
    
    Expected format:
    {
        "router1": {
            "device_type": "cisco_ios",
            "host": "192.168.1.1",
            "username": "admin",
            "password": "password"
        }
    }
    """
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️  Credentials file not found: {config_file}")
        print(f"   Creating template file...")
        
        # Create template
        template = {
            "router1": {
                "device_type": "cisco_ios",
                "host": "192.168.1.1",
                "username": "admin",
                "password": "changeme",
                "secret": "enable_password"
            },
            "switch1": {
                "device_type": "cisco_ios",
                "host": "192.168.1.2",
                "username": "admin",
                "password": "changeme"
            }
        }
        
        with open(config_file, 'w') as f:
            json.dump(template, f, indent=2)
        
        print(f"   Template created. Please update {config_file} with actual credentials.")
        return {}
    
    except Exception as e:
        print(f"❌ Error loading credentials: {e}")
        return {}


def deploy_configurations(fixes: List[ConfigurationFix], 
                         credentials_file: str = "device_credentials.json",
                         save_logs: bool = True) -> List[Dict[str, Any]]:
    """
    Main function to deploy configurations
    
    Args:
        fixes: List of ConfigurationFix objects to deploy
        credentials_file: Path to device credentials JSON file
        save_logs: Whether to save deployment logs
        
    Returns:
        List of deployment results
    """
    # Load credentials
    credentials = load_device_credentials(credentials_file)
    
    if not credentials:
        print("❌ No device credentials available. Aborting deployment.")
        return []
    
    # Create deployer
    deployer = ConfigDeployer(credentials)
    
    # Create rollback script before deployment
    print("📝 Creating rollback script...")
    deployer.create_rollback_script(fixes)
    
    # Deploy configurations
    results = deployer.deploy_multiple(fixes)
    
    # Save logs
    if save_logs:
        deployer.save_deployment_log()
    
    return results


def test_connectivity(credentials_file: str = "device_credentials.json"):
    """
    Test connectivity to all configured devices
    """
    credentials = load_device_credentials(credentials_file)
    
    print(f"\n{'='*70}")
    print("Testing Device Connectivity")
    print(f"{'='*70}\n")
    
    results = {}
    
    for device_name, device_params in credentials.items():
        print(f"Testing {device_name} ({device_params.get('host')})...")
        
        try:
            connection = ConnectHandler(**device_params)
            connection.enable()
            hostname = connection.send_command("show version | include uptime")
            connection.disconnect()
            
            results[device_name] = {
                'reachable': True,
                'info': hostname.split('\n')[0] if hostname else 'Connected'
            }
            print(f"  ✅ Success\n")
            
        except NetmikoTimeoutException:
            results[device_name] = {
                'reachable': False,
                'error': 'Connection timeout'
            }
            print(f"  ❌ Timeout\n")
            
        except NetmikoAuthenticationException:
            results[device_name] = {
                'reachable': False,
                'error': 'Authentication failed'
            }
            print(f"  ❌ Authentication failed\n")
            
        except Exception as e:
            results[device_name] = {
                'reachable': False,
                'error': str(e)
            }
            print(f"  ❌ Error: {e}\n")
    
    # Summary
    reachable = sum(1 for r in results.values() if r['reachable'])
    print(f"{'='*70}")
    print(f"Summary: {reachable}/{len(results)} device(s) reachable")
    print(f"{'='*70}\n")
    
    return results


# CLI interface for standalone usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("""
Usage:
    python shipit.py test                    # Test device connectivity
    python shipit.py deploy <fixes.json>     # Deploy configurations from file
        """)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "test":
        test_connectivity()
    
    elif command == "deploy":
        if len(sys.argv) < 3:
            print("Error: Please provide fixes JSON file")
            sys.exit(1)
        
        fixes_file = sys.argv[2]
        
        # Load fixes from JSON
        try:
            with open(fixes_file, 'r') as f:
                fixes_data = json.load(f)
            
            # Convert to ConfigurationFix objects
            fixes = []
            for fix_dict in fixes_data:
                fix = ConfigurationFix(
                    diagnostic_id=fix_dict['diagnostic_id'],
                    device=fix_dict['device'],
                    device_type=fix_dict['device_type'],
                    commands=fix_dict['commands'],
                    verification_commands=fix_dict.get('verification_commands', []),
                    rollback_commands=fix_dict.get('rollback_commands', [])
                )
                fixes.append(fix)
            
            # Deploy
            results = deploy_configurations(fixes)
            
            # Print summary
            successful = sum(1 for r in results if r['success'])
            print(f"\n{'='*70}")
            print(f"Deployment Complete: {successful}/{len(results)} successful")
            print(f"{'='*70}\n")
            
        except FileNotFoundError:
            print(f"❌ File not found: {fixes_file}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)