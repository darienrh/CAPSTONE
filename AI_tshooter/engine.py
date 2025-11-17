"""
Main decision tree engine that coordinates all analyzers
"""
import time
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from models.diagnostic import DiagnosticResult, ConfigurationFix
from formatters import ResultFormatter
from utils import PrometheusClient, LLMClient
import shipit


class NetworkDecisionTreeEngine:
    """Main decision tree engine for network diagnostics"""
    
    def __init__(self, prometheus_url: str = "http://localhost:9090", 
                 poll_interval: int = 30,
                 llm_api_url: str = "http://localhost:11434"):
        # Import analyzers
        from analyzers.base import BaseNetworkAnalyzer
        from analyzers.switch import SwitchAnalyzer
        from analyzers.vpn import VpnAnalyzer
        from analyzers.ospf import OspfAnalyzer
        from analyzers.eigrp import EigrpAnalyzer
        from analyzers.bgp import BgpAnalyzer
        from analyzers.isis import IsisAnalyzer
        from analyzers.ipv6 import Ipv6Analyzer
        
        self.analyzers = [
            BaseNetworkAnalyzer(),
            SwitchAnalyzer(),
            VpnAnalyzer(),
            OspfAnalyzer(),
            EigrpAnalyzer(),
            BgpAnalyzer(),
            IsisAnalyzer(),
            Ipv6Analyzer(),
        ]
        
        self.prometheus_client = PrometheusClient(prometheus_url)
        self.llm_client = LLMClient(llm_api_url)
        self.formatter = ResultFormatter()
        self.poll_interval = poll_interval
        self.running = False
        
        # Create responses directory
        os.makedirs("responses", exist_ok=True)
    
    def analyze(self, telemetry_data: Dict[str, Any]) -> List[DiagnosticResult]:
        """
        Main analysis function - runs all diagnostic checks
        
        Args:
            telemetry_data: Dictionary containing network metrics from Prometheus
        
        Returns:
            List of DiagnosticResult objects sorted by severity
        """
        all_results = []
        
        # Run all analyzers on each device
        for device_name, device_data in telemetry_data.get('devices', {}).items():
            for analyzer in self.analyzers:
                results = analyzer.analyze(device_name, device_data)
                all_results.extend(results)
        
        # Sort by severity (Critical -> Warning -> Info)
        severity_order = {'critical': 0, 'warning': 1, 'info': 2}
        all_results.sort(key=lambda r: severity_order.get(r.severity.value, 3))
        
        return all_results
    
    def run_continuous(self):
        """Run continuous monitoring loop"""
        print("=" * 70)
        print("Network Decision Tree Engine - Continuous Monitoring")
        print("=" * 70)
        print(f"Prometheus: {self.prometheus_client.url}")
        print(f"Poll Interval: {self.poll_interval} seconds")
        print("Press Ctrl+C to stop\n")
        
        self.running = True
        iteration = 0
        
        try:
            while self.running:
                iteration += 1
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iteration {iteration}")
                print("-" * 70)
                
                # Fetch telemetry from Prometheus
                print("Fetching telemetry from Prometheus...")
                telemetry_data = self.prometheus_client.fetch_telemetry()
                
                if not telemetry_data or not telemetry_data.get('devices'):
                    print("⚠️  No telemetry data received. Waiting...")
                    time.sleep(self.poll_interval)
                    continue
                
                # Run analysis
                print("Running diagnostic checks...")
                results = self.analyze(telemetry_data)
                
                if not results:
                    print("✅ No issues detected. Network healthy.")
                    time.sleep(self.poll_interval)
                    continue
                
                # Display summary
                summary = self.formatter.to_summary(results)
                print(f"\n🔍 Found {summary['total_issues']} issue(s):")
                print(f"   Critical: {summary['critical']}")
                print(f"   Warnings: {summary['warnings']}")
                print(f"   Info: {summary['info']}")
                print(f"   Health Score: {summary['health_score']}/100")
                
                # Display issues
                print("\n" + self.formatter.to_console_summary(results))
                
                # Ask user if they want to generate fixes
                response = input("\n🤖 Generate configuration fixes with LLM? (y/n): ").strip().lower()
                
                if response == 'y':
                    self.generate_and_deploy_fixes(results)
                else:
                    print("Skipping fix generation. Continuing monitoring...\n")
                
                time.sleep(self.poll_interval)
                
        except KeyboardInterrupt:
            print("\n\nStopping monitoring...")
            self.running = False
    
    def generate_and_deploy_fixes(self, results: List[DiagnosticResult]):
        """Generate configuration fixes using LLM and optionally deploy"""
        print("\n" + "=" * 70)
        print("Generating Configuration Fixes")
        print("=" * 70)
        
        all_fixes = []
        
        for idx, result in enumerate(results):
            print(f"\n[{idx + 1}/{len(results)}] Generating fix for: {result.issue}")
            
            # Convert to LLM prompt
            llm_prompt = self.formatter.to_llm_prompt(result)
            
            # Call LLM
            llm_response = self.llm_client.generate_config(llm_prompt)
            
            if llm_response:
                # Parse LLM response into ConfigurationFix
                fix = self._parse_llm_response(result, llm_response)
                all_fixes.append(fix)
                print(f"   ✅ Generated {len(fix.commands)} command(s)")
            else:
                print(f"   ❌ Failed to generate fix")
        
        if not all_fixes:
            print("\n⚠️  No fixes generated.")
            return
        
        # Save fixes to file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        fix_file = f"responses/fixes_{timestamp}.json"
        
        with open(fix_file, 'w') as f:
            json.dump([fix.to_dict() for fix in all_fixes], f, indent=2)
        
        print(f"\n💾 Fixes saved to: {fix_file}")
        
        # Display preview
        print("\n" + "=" * 70)
        print("Configuration Preview")
        print("=" * 70)
        self._display_fixes(all_fixes)
        
        # Ask to deploy
        response = input("\n🚀 Deploy these configurations? (yes/no): ").strip().lower()
        
        if response == 'yes':
            print("\nDeploying configurations...")
            results = shipit.deploy_configurations(all_fixes)
            self._display_deployment_results(results)
        else:
            print("Deployment cancelled. Fixes saved to file.")
    
    def _parse_llm_response(self, diagnostic: DiagnosticResult, 
                           llm_response: str) -> ConfigurationFix:
        """Parse LLM response into ConfigurationFix object"""
        # Extract commands from code block
        commands = []
        in_code_block = False
        
        for line in llm_response.split('\n'):
            line = line.strip()
            if line.startswith('```'):
                in_code_block = not in_code_block
                continue
            if in_code_block and line:
                commands.append(line)
        
        # If no code block found, use all non-empty lines
        if not commands:
            commands = [line.strip() for line in llm_response.split('\n') 
                       if line.strip() and not line.startswith('#')]
        
        device = diagnostic.affected_devices[0] if diagnostic.affected_devices else "unknown"
        
        return ConfigurationFix(
            diagnostic_id=f"{diagnostic.category}_{diagnostic.issue[:20]}",
            device=device,
            device_type=diagnostic.device_type,
            commands=commands,
            verification_commands=self._extract_verification_commands(commands)
        )
    
    def _extract_verification_commands(self, commands: List[str]) -> List[str]:
        """Extract show/verification commands from command list"""
        verification = []
        for cmd in commands:
            if cmd.startswith('show ') or cmd.startswith('verify '):
                verification.append(cmd)
        return verification
    
    def _display_fixes(self, fixes: List[ConfigurationFix]):
        """Display configuration fixes"""
        for idx, fix in enumerate(fixes, 1):
            print(f"\n[{idx}] Device: {fix.device}")
            print(f"    Commands ({len(fix.commands)}):")
            for cmd in fix.commands[:5]:  # Show first 5
                print(f"      - {cmd}")
            if len(fix.commands) > 5:
                print(f"      ... and {len(fix.commands) - 5} more")
    
    def _display_deployment_results(self, results: List[Dict[str, Any]]):
        """Display deployment results"""
        print("\n" + "=" * 70)
        print("Deployment Results")
        print("=" * 70)
        
        for result in results:
            status = "✅" if result['success'] else "❌"
            print(f"{status} {result['device']}: {result['message']}")


def main():
    """Main entry point"""
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║   Network Decision Tree Troubleshooting Engine            ║
    ║   AI-Powered Network Diagnostics & Auto-Remediation       ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Initialize engine
    engine = NetworkDecisionTreeEngine(
        prometheus_url="http://localhost:9090",
        poll_interval=30,
        llm_api_url="http://localhost:11434"
    )
    
    # Run continuous monitoring
    engine.run_continuous()


if __name__ == "__main__":
    main()