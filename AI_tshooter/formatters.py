"""
Output formatting utilities for diagnostic results
"""
import json
from typing import List, Dict, Any
from models.diagnostic import DiagnosticResult, Severity


class ResultFormatter:
    """Formats diagnostic results for various outputs"""
    
    def to_llm_prompt(self, result: DiagnosticResult) -> str:
        """
        Format a single diagnostic result as LLM prompt for config generation
        
        Returns a structured prompt asking LLM to generate exact CLI commands
        """
        prompt = f"""You are a network configuration expert. Generate EXACT Cisco IOS commands to fix the following issue.

NETWORK ISSUE DETAILS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Device(s): {', '.join(result.affected_devices)}
Category: {result.category}
Severity: {result.severity.value.upper()}

Problem: {result.issue}
Root Cause: {result.root_cause}

Configuration Context:
{self._format_config_context(result.config_context)}

Metrics:
{json.dumps(result.metrics, indent=2)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INSTRUCTIONS:
1. Generate ONLY the exact configuration commands needed
2. Use proper Cisco IOS syntax for {result.device_type}
3. Include commands in the correct sequence
4. Start with 'configure terminal' if entering config mode
5. Include 'exit' or 'end' commands as needed
6. Add verification commands at the end (show commands)
7. DO NOT include explanations, comments, or markdown
8. DO NOT include any text before or after the commands

RESPONSE FORMAT:
Return ONLY commands, one per line, in a code block:
```
configure terminal
<command1>
<command2>
...
end
<verification command>
```

GENERATE COMMANDS NOW:"""
        
        return prompt
    
    def _format_config_context(self, context: Dict[str, Any]) -> str:
        """Format configuration context in readable format"""
        if not context:
            return "  (No additional context provided)"
        
        lines = []
        for key, value in context.items():
            # Format key nicely
            formatted_key = key.replace('_', ' ').title()
            lines.append(f"  • {formatted_key}: {value}")
        
        return "\n".join(lines) if lines else "  (No additional context)"
    
    def to_console_summary(self, results: List[DiagnosticResult]) -> str:
        """
        Format results for console display with color and formatting
        """
        if not results:
            return "✅ No issues detected"
        
        output = []
        
        # Group by severity
        critical = [r for r in results if r.severity == Severity.CRITICAL]
        warnings = [r for r in results if r.severity == Severity.WARNING]
        info = [r for r in results if r.severity == Severity.INFO]
        
        for severity_group, emoji, name in [
            (critical, "🔴", "CRITICAL"),
            (warnings, "🟡", "WARNING"),
            (info, "🔵", "INFO")
        ]:
            if severity_group:
                output.append(f"\n{emoji} {name} ({len(severity_group)}):")
                for idx, result in enumerate(severity_group, 1):
                    devices = ', '.join(result.affected_devices)
                    output.append(f"  {idx}. [{result.category}] {result.issue}")
                    output.append(f"     Device(s): {devices}")
                    output.append(f"     Cause: {result.root_cause}")
        
        return "\n".join(output)
    
    def to_llm_context(self, results: List[DiagnosticResult]) -> str:
        """
        Format diagnostic results for LLM processing
        Returns a structured text summary suitable for LLM context
        """
        if not results:
            return "No issues detected. All network systems operating normally."
        
        output = f"NETWORK DIAGNOSTIC REPORT - {len(results)} Issue(s) Detected\n"
        output += "=" * 70 + "\n\n"
        
        # Group by severity
        critical = [r for r in results if r.severity == Severity.CRITICAL]
        warnings = [r for r in results if r.severity == Severity.WARNING]
        info = [r for r in results if r.severity == Severity.INFO]
        
        for severity_group, name in [(critical, "CRITICAL"), (warnings, "WARNING"), (info, "INFO")]:
            if severity_group:
                output += f"\n{name} ISSUES ({len(severity_group)}):\n"
                output += "-" * 70 + "\n"
                
                for idx, result in enumerate(severity_group, 1):
                    output += f"\n{idx}. [{result.category}] {result.issue}\n"
                    output += f"   Affected: {', '.join(result.affected_devices)}\n"
                    output += f"   Root Cause: {result.root_cause}\n"
                    output += f"   Resolution Steps:\n"
                    for step_idx, step in enumerate(result.remediation_steps, 1):
                        output += f"      {step_idx}. {step}\n"
                    if result.metrics:
                        output += f"   Metrics: {json.dumps(result.metrics, indent=6)}\n"
        
        return output
    
    def to_json(self, results: List[DiagnosticResult]) -> str:
        """Export results as JSON for API consumption"""
        return json.dumps([r.to_dict() for r in results], indent=2)
    
    def to_summary(self, results: List[DiagnosticResult]) -> Dict[str, Any]:
        """Create a summary report with statistics"""
        critical = len([r for r in results if r.severity == Severity.CRITICAL])
        warnings = len([r for r in results if r.severity == Severity.WARNING])
        info_count = len([r for r in results if r.severity == Severity.INFO])
        
        devices_affected = set()
        categories = {}
        
        for result in results:
            devices_affected.update(result.affected_devices)
            categories[result.category] = categories.get(result.category, 0) + 1
        
        # Calculate health score (0-100)
        health_score = max(0, 100 - (critical * 20 + warnings * 5 + info_count * 1))
        
        return {
            'total_issues': len(results),
            'critical': critical,
            'warnings': warnings,
            'info': info_count,
            'devices_affected': list(devices_affected),
            'device_count': len(devices_affected),
            'categories': categories,
            'health_score': health_score,
            'status': 'healthy' if health_score >= 80 else 'degraded' if health_score >= 50 else 'critical'
        }