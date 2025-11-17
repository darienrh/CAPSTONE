"""
Helper utilities for network troubleshooting engine
"""

import requests
import json
from typing import Dict, Any, Optional, List
from datetime import datetime


class PrometheusClient:
    """Client for fetching telemetry from Prometheus"""
    
    def __init__(self, url: str = "http://localhost:9090"):
        self.url = url.rstrip('/')
        self.api_url = f"{self.url}/api/v1"
    
    def fetch_telemetry(self) -> Dict[str, Any]:
        """
        Fetch network telemetry from Prometheus
        
        Returns:
            Dictionary with device telemetry data
        """
        try:
            # Query for all devices (using SNMP metrics)
            devices = self._get_devices()
            
            telemetry_data = {'devices': {}}
            
            for device in devices:
                device_data = self._fetch_device_metrics(device)
                if device_data:
                    telemetry_data['devices'][device] = device_data
            
            return telemetry_data
            
        except Exception as e:
            print(f"❌ Error fetching telemetry: {e}")
            return {'devices': {}}
    
    def _get_devices(self) -> List[str]:
        """Get list of monitored devices from Prometheus"""
        try:
            # Query for unique device instances
            query = 'up{job="snmp"}'
            response = requests.get(
                f"{self.api_url}/query",
                params={'query': query},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            devices = set()
            for result in data.get('data', {}).get('result', []):
                instance = result.get('metric', {}).get('instance', '')
                if instance:
                    # Extract device name from instance
                    device_name = instance.split(':')[0]
                    devices.add(device_name)
            
            return list(devices)
            
        except Exception as e:
            print(f"⚠️  Error getting device list: {e}")
            return []
    
    def _fetch_device_metrics(self, device: str) -> Optional[Dict[str, Any]]:
        """Fetch all metrics for a specific device"""
        try:
            # This is a simplified example - expand based on your Prometheus metrics
            metrics = {
                'interfaces': self._fetch_interface_metrics(device),
                'cpu': self._fetch_metric(f'snmp_cpu_usage{{instance="{device}:161"}}'),
                'memory': self._fetch_metric(f'snmp_memory_usage{{instance="{device}:161"}}'),
                'ospf': self._fetch_ospf_metrics(device),
                'bgp': self._fetch_bgp_metrics(device),
                # Add more protocol metrics as needed
            }
            
            return metrics
            
        except Exception as e:
            print(f"⚠️  Error fetching metrics for {device}: {e}")
            return None
    
    def _fetch_interface_metrics(self, device: str) -> Dict[str, Any]:
        """Fetch interface metrics from Prometheus"""
        # Simplified example - adjust queries based on your SNMP exporter config
        interfaces = {}
        
        try:
            # Query interface status
            query = f'ifOperStatus{{instance="{device}:161"}}'
            response = requests.get(
                f"{self.api_url}/query",
                params={'query': query},
                timeout=10
            )
            data = response.json()
            
            for result in data.get('data', {}).get('result', []):
                if_name = result.get('metric', {}).get('ifDescr', 'unknown')
                interfaces[if_name] = {
                    'oper_status': 'up' if result.get('value', [0, 0])[1] == '1' else 'down',
                    'admin_status': 'up',  # Fetch from ifAdminStatus
                    # Add more interface metrics
                }
            
        except Exception as e:
            print(f"⚠️  Error fetching interfaces: {e}")
        
        return interfaces
    
    def _fetch_ospf_metrics(self, device: str) -> Dict[str, Any]:
        """Fetch OSPF metrics"""
        # Implement based on your SNMP MIBs
        return {
            'enabled': False,  # Detect if OSPF is running
            'router_id': None,
            'neighbors': [],
            'interfaces': {}
        }
    
    def _fetch_bgp_metrics(self, device: str) -> Dict[str, Any]:
        """Fetch BGP metrics"""
        return {
            'enabled': False,
            'local_as': None,
            'neighbors': []
        }
    
    def _fetch_metric(self, query: str) -> Optional[float]:
        """Fetch a single metric value"""
        try:
            response = requests.get(
                f"{self.api_url}/query",
                params={'query': query},
                timeout=10
            )
            data = response.json()
            results = data.get('data', {}).get('result', [])
            
            if results:
                return float(results[0].get('value', [0, 0])[1])
            
        except Exception:
            pass
        
        return None


class LLMClient:
    """Client for interacting with LLM (Ollama/OpenAI-compatible API)"""
    
    def __init__(self, api_url: str = "http://localhost:11434"):
        self.api_url = api_url.rstrip('/')
        self.model = "llama2"  # Default model
    
    def generate_config(self, prompt: str, model: Optional[str] = None) -> Optional[str]:
        """
        Generate configuration commands using LLM
        
        Args:
            prompt: The prompt to send to LLM
            model: Model to use (default: self.model)
            
        Returns:
            Generated configuration text or None if failed
        """
        try:
            response = requests.post(
                f"{self.api_url}/api/generate",
                json={
                    'model': model or self.model,
                    'prompt': prompt,
                    'stream': False,
                    'options': {
                        'temperature': 0.1,  # Low temperature for precise configs
                        'top_p': 0.9,
                    }
                },
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            return result.get('response', '')
            
        except requests.exceptions.Timeout:
            print("⚠️  LLM request timed out")
            return None
        except Exception as e:
            print(f"❌ LLM error: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test if LLM is reachable"""
        try:
            response = requests.get(f"{self.api_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False


def load_config(config_file: str = "config.json") -> Dict[str, Any]:
    """Load configuration from JSON file"""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Return default config
        return {
            'prometheus_url': 'http://localhost:9090',
            'llm_api_url': 'http://localhost:11434',
            'poll_interval': 30,
            'gns3_api_url': 'http://localhost:3080',
            'devices': {}
        }
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return {}


def save_config(config: Dict[str, Any], config_file: str = "config.json"):
    """Save configuration to JSON file"""
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving config: {e}")
        return False


def timestamp() -> str:
    """Get current timestamp string"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')