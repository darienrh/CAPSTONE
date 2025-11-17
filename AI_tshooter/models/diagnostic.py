"""
Data models for diagnostic results
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class Severity(Enum):
    """Issue severity levels"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class DiagnosticResult:
    """Represents a single diagnostic finding"""
    category: str
    issue: str
    severity: Severity
    root_cause: str
    remediation_steps: List[str]
    affected_devices: List[str]
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    # NEW: Fields for configuration generation
    device_type: str = "cisco_ios"  # For netmiko
    config_context: Dict[str, Any] = field(default_factory=dict)  # Specific values needed for fix
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'category': self.category,
            'issue': self.issue,
            'severity': self.severity.value,
            'root_cause': self.root_cause,
            'remediation_steps': self.remediation_steps,
            'affected_devices': self.affected_devices,
            'metrics': self.metrics,
            'device_type': self.device_type,
            'config_context': self.config_context
        }
    
    def to_llm_prompt(self) -> str:
        """Convert to LLM prompt format for configuration generation"""
        prompt = f"""
DEVICE: {', '.join(self.affected_devices)}
DEVICE_TYPE: {self.device_type}
CATEGORY: {self.category}
ISSUE: {issue}
ROOT_CAUSE: {self.root_cause}

CONFIGURATION CONTEXT:
{self._format_config_context()}

TASK: Generate exact Cisco IOS commands to resolve this issue.

REQUIREMENTS:
- Provide ONLY the configuration commands, no explanations
- Use exact syntax for {self.device_type}
- Include all necessary commands in sequence
- Start with configuration mode commands if needed
- End with verification commands

FORMAT YOUR RESPONSE AS:
```
<command1>
<command2>
...
```
"""
        return prompt
    
    def _format_config_context(self) -> str:
        """Format configuration context for LLM"""
        if not self.config_context:
            return "No additional context"
        
        lines = []
        for key, value in self.config_context.items():
            lines.append(f"  {key}: {value}")
        return "\n".join(lines)


@dataclass
class ConfigurationFix:
    """Represents a configuration fix for a diagnostic result"""
    diagnostic_id: str
    device: str
    device_type: str
    commands: List[str]
    verification_commands: List[str] = field(default_factory=list)
    rollback_commands: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'diagnostic_id': self.diagnostic_id,
            'device': self.device,
            'device_type': self.device_type,
            'commands': self.commands,
            'verification_commands': self.verification_commands,
            'rollback_commands': self.rollback_commands
        }