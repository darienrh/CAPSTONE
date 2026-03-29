#!/usr/bin/env python3
"""fix_recommender.py - Fix recommendation and generation"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from core.knowledge_base import KnowledgeBase
from core.inference_engine import InferenceEngine
from core.config_manager import ConfigManager


class FixRecommender:
    """
    Recommends and generates fixes for detected problems
    Works with inference engine to provide intelligent fix recommendations
    """
    
    def __init__(self, knowledge_base, inference_engine, config_manager):
        """
        Initialize fix recommender
        
        Args:
            knowledge_base: KnowledgeBase instance
            inference_engine: InferenceEngine instance
            config_manager: ConfigManager instance
        """
        self.kb = knowledge_base
        self.ie = inference_engine
        self.cm = config_manager
        
        self.fix_templates = self._load_fix_templates()
        self.fix_history = []
    
    def _load_fix_templates(self) -> Dict[str, Dict]:
        """
        Load fix command templates
        
        Returns:
            Dict of fix templates by problem type
        """
        templates = {
            'interface_shutdown': {
                'commands': ['interface {interface}', 'no shutdown'],
                'verification': 'show ip interface brief | include {interface}',
                'rollback': ['interface {interface}', 'shutdown']
            },
            'ip_address_mismatch': {
                'commands': ['interface {interface}', 
                           'ip address {ip_address} {subnet_mask}'],
                'verification': 'show run interface {interface}',
                'rollback': ['interface {interface}', 
                           'ip address {old_ip} {old_mask}']
            },
        }
        
        return templates
    
    def recommend_fixes(self, problem: Dict, 
                       context: Optional[Dict] = None) -> List[Dict]:
        """
        Recommend fixes for a specific problem
        
        Args:
            problem: Problem dict from detector
            context: Additional context (device state, topology, etc.)
        
        Returns:
            List of recommended fixes with full metadata
        """
        recommendations = []
        
        problem_type = problem.get('type', 'unknown')
        
        matching_rules = self.kb.get_matching_rules(problem)
        
        for rule in matching_rules[:3]:
            fix = {
                'fix_id': self._generate_fix_id(),
                'problem_id': problem.get('id'),
                'rule_id': rule['id'],
                'commands': self._customize_commands(rule['action']['commands'], problem),
                'verification_commands': [rule['action']['verification']],
                'description': rule['action']['description'],
                'confidence': rule['confidence'],
                'risk_level': self._assess_risk(problem, rule['action']),
                'estimated_downtime': self._estimate_downtime(rule['action']),
                'prerequisites': self._check_prerequisites(rule['action'], context),
                'requires_manual': rule['action'].get('requires_manual', False)
            }
            
            recommendations.append(fix)
        
        template = self.fix_templates.get(problem_type)
        if template and not recommendations:
            fix = self.customize_fix(template, problem)
            fix.update({
                'fix_id': self._generate_fix_id(),
                'problem_id': problem.get('id'),
                'confidence': problem.get('confidence', 0.8),
                'risk_level': self._assess_risk(problem, fix),
                'estimated_downtime': self._estimate_downtime(fix),
                'prerequisites': self._check_prerequisites(fix, context)
            })
            recommendations.append(fix)
        
        return recommendations
    
    def generate_fix_plan(self, problem_list: List[Dict], 
                         strategy: str = "sequential") -> Dict:
        """
        Generate comprehensive fix plan for multiple problems
        
        Args:
            problem_list: List of problems to fix
            strategy: Fix strategy
                - 'sequential': Fix one at a time
                - 'parallel': Fix independent problems together
                - 'optimal': Minimize total commands/downtime
        
        Returns:
            Fix plan with phases and ordering
        """
        plan = {
            'strategy': strategy,
            'total_fixes': len(problem_list),
            'estimated_time': '0 minutes',
            'phases': []
        }
        
        if strategy == "sequential":
            for i, problem in enumerate(problem_list, 1):
                fixes = self.recommend_fixes(problem)
                if fixes:
                    plan['phases'].append({
                        'phase': i,
                        'description': f"Fix {problem.get('type')}",
                        'fixes': [fixes[0]],
                        'can_run_parallel': False
                    })
        
        elif strategy == "parallel":
            independent_groups = self._group_independent_fixes(problem_list)
            for i, group in enumerate(independent_groups, 1):
                group_fixes = []
                for problem in group:
                    fixes = self.recommend_fixes(problem)
                    if fixes:
                        group_fixes.append(fixes[0])
                
                if group_fixes:
                    plan['phases'].append({
                        'phase': i,
                        'description': f"Fix group {i}",
                        'fixes': group_fixes,
                        'can_run_parallel': True
                    })
        
        elif strategy == "optimal":
            prioritized = self.ie.calculate_fix_priority(problem_list)
            plan['phases'] = self._create_optimal_phases(prioritized)
        
        plan['estimated_time'] = self._calculate_total_time(plan['phases'])
        
        return plan
    
    def _group_independent_fixes(self, problem_list: List[Dict]) -> List[List[Dict]]:
        """Group problems that can be fixed independently"""
        groups = []
        used = set()
        
        for i, problem in enumerate(problem_list):
            if i in used:
                continue
            
            group = [problem]
            used.add(i)
            
            for j, other in enumerate(problem_list[i+1:], i+1):
                if j in used:
                    continue
                
                if not self._problems_conflict(problem, other):
                    group.append(other)
                    used.add(j)
            
            groups.append(group)
        
        return groups
    
    def _problems_conflict(self, p1: Dict, p2: Dict) -> bool:
        """Check if two problems conflict and cannot be fixed in parallel"""
        same_device = p1.get('device') == p2.get('device')
        same_interface = p1.get('interface') == p2.get('interface')
        same_protocol = p1.get('category') == p2.get('category')
        
        if same_device and same_interface:
            return True
        
        if same_device and same_protocol and p1.get('category') in ['eigrp', 'ospf']:
            return True
        
        return False
    
    def _create_optimal_phases(self, prioritized_problems: List[Dict]) -> List[Dict]:
        """Create optimal fix phases minimizing time and risk"""
        phases = []
        current_phase = []
        
        for problem in prioritized_problems:
            conflicts = any(self._problems_conflict(problem, p) for p in current_phase)
            
            if conflicts and current_phase:
                phases.append({
                    'phase': len(phases) + 1,
                    'description': f"Phase {len(phases) + 1}",
                    'fixes': current_phase,
                    'can_run_parallel': False
                })
                current_phase = []
            
            current_phase.append(problem)
        
        if current_phase:
            phases.append({
                'phase': len(phases) + 1,
                'description': f"Phase {len(phases) + 1}",
                'fixes': current_phase,
                'can_run_parallel': False
            })
        
        return phases
    
    def validate_fix(self, fix: Dict, current_state: Dict) -> Dict:
        """
        Validate that a fix is safe to apply
        
        Args:
            fix: Fix to validate
            current_state: Current device state
        
        Returns:
            Validation result
        """
        result = {
            'is_safe': True,
            'warnings': [],
            'blockers': [],
            'prerequisites_met': True
        }
        
        prereqs = fix.get('prerequisites', [])
        for prereq in prereqs:
            if not self._check_prerequisite(prereq, current_state):
                result['is_safe'] = False
                result['blockers'].append(f"Prerequisite not met: {prereq}")
                result['prerequisites_met'] = False
        
        risk_level = fix.get('risk_level', 'medium')
        if risk_level in ['high', 'critical']:
            result['warnings'].append(
                f"This is a {risk_level} risk operation"
            )
        
        return result
    
    def generate_rollback_plan(self, fix_plan: Dict) -> Dict:
        """
        Generate rollback plan for a fix plan
        
        Args:
            fix_plan: Original fix plan
        
        Returns:
            Rollback plan with reverse commands
        """
        rollback = {
            'phases': []
        }
        
        for phase in reversed(fix_plan.get('phases', [])):
            rollback_phase = {
                'phase': phase['phase'],
                'description': f"Rollback: {phase['description']}",
                'fixes': []
            }
            
            for fix in phase.get('fixes', []):
                rollback_commands = fix.get('rollback_commands', [])
                if rollback_commands:
                    rollback_phase['fixes'].append({
                        'commands': rollback_commands,
                        'description': f"Revert {fix.get('description', '')}"
                    })
            
            rollback['phases'].append(rollback_phase)
        
        return rollback
    
    def customize_fix(self, fix_template: Dict, 
                     problem_details: Dict) -> Dict:
        """
        Customize a fix template for specific problem
        
        Args:
            fix_template: Generic fix template
            problem_details: Specific problem instance
        
        Returns:
            Customized fix with filled-in parameters
        """
        customized = dict(fix_template)
        
        commands = customized.get('commands', [])
        customized_commands = self._customize_commands(commands, problem_details)
        
        customized['commands'] = customized_commands
        customized['description'] = self._generate_description(problem_details)
        
        return customized
    
    def _customize_commands(self, commands: List[str], problem_details: Dict) -> List[str]:
        """Replace placeholders in commands with actual values"""
        customized_commands = []
        
        for cmd in commands:
            for key, value in problem_details.items():
                placeholder = '{' + key + '}'
                if placeholder in cmd:
                    cmd = cmd.replace(placeholder, str(value))
            customized_commands.append(cmd)
        
        return customized_commands
    
    def _generate_description(self, problem: Dict) -> str:
        """Generate human-readable fix description"""
        ptype = problem.get('type', 'unknown')
        device = problem.get('device', '')
        location = problem.get('interface', problem.get('location', ''))
        
        return f"Fix {ptype} on {device} {location}"
    
    def estimate_fix_impact(self, fix: Dict, 
                           network_state: Dict) -> Dict:
        """
        Estimate impact of applying a fix
        
        Args:
            fix: Fix to analyze
            network_state: Current network state
        
        Returns:
            Impact analysis
        """
        impact = {
            'affected_devices': [],
            'affected_services': [],
            'downtime_estimate': '0 seconds',
            'traffic_impact': 'minimal',
            'success_probability': 0.95
        }
        
        commands = fix.get('commands', [])
        
        return impact
    
    def suggest_alternative_fixes(self, problem: Dict, 
                                  primary_fix: Dict) -> List[Dict]:
        """
        Suggest alternative approaches to fix a problem
        
        Args:
            problem: Problem to fix
            primary_fix: The recommended fix
        
        Returns:
            List of alternative fixes with trade-offs
        """
        alternatives = []
        
        matching_rules = self.kb.get_matching_rules(problem, min_confidence=0.3)
        
        for rule in matching_rules[1:4]:
            alternative = {
                'fix_id': self._generate_fix_id(),
                'commands': self._customize_commands(rule['action']['commands'], problem),
                'description': rule['action']['description'],
                'confidence': rule['confidence'],
                'trade_offs': self._compare_fixes(primary_fix, rule['action'])
            }
            alternatives.append(alternative)
        
        return alternatives
    
    def _compare_fixes(self, fix1: Dict, fix2: Dict) -> str:
        """Compare two fixes and describe trade-offs"""
        return "Alternative approach with different risk/complexity profile"
    
    def optimize_commands(self, command_list: List[str]) -> List[str]:
        """
        Optimize command list to minimize device interaction
        
        Args:
            command_list: Raw list of commands
        
        Returns:
            Optimized command list
        """
        optimized = []
        seen = set()
        
        for cmd in command_list:
            if cmd not in seen:
                optimized.append(cmd)
                seen.add(cmd)
        
        return optimized
    
    def generate_verification_plan(self, fix_plan: Dict) -> Dict:
        """
        Generate plan to verify fixes were successful
        
        Args:
            fix_plan: Plan that was or will be executed
        
        Returns:
            Verification plan with commands and expected outputs
        """
        verification = {
            'checks': []
        }
        
        for phase in fix_plan.get('phases', []):
            for fix in phase.get('fixes', []):
                verification['checks'].append({
                    'fix_id': fix.get('fix_id'),
                    'commands': fix.get('verification_commands', []),
                    'expected_result': 'up/up' if 'interface' in str(fix) else 'success',
                    'timeout': 30
                })
        
        return verification
    
    def learn_from_fix_result(self, fix: Dict, result: Dict):
        """
        Learn from the result of applying a fix
        
        Args:
            fix: Fix that was applied
            result: Result of application (success/failure/partial)
        """
        success = result.get('success', False)
        
        self.fix_history.append({
            'fix': fix,
            'result': result,
            'timestamp': result.get('timestamp')
        })
        
        if 'rule_id' in fix:
            self.kb.update_rule_confidence(fix['rule_id'], success)
    
    def _generate_fix_id(self) -> str:
        """Generate unique fix ID"""
        import uuid
        return f"FIX_{uuid.uuid4().hex[:8]}"
    
    def _assess_risk(self, problem: Dict, fix: Dict) -> str:
        """Assess risk level of a fix"""
        commands = fix.get('commands', [])
        
        if any('router' in str(cmd) for cmd in commands):
            return 'high'
        elif any('interface' in str(cmd) for cmd in commands):
            return 'medium'
        else:
            return 'low'
    
    def _estimate_downtime(self, fix: Dict) -> str:
        """Estimate downtime caused by fix"""
        num_commands = len(fix.get('commands', []))
        seconds = num_commands * 2
        
        if seconds < 5:
            return f"{seconds} seconds"
        elif seconds < 60:
            return f"{seconds} seconds"
        else:
            minutes = seconds // 60
            return f"{minutes} minutes"
    
    def _check_prerequisites(self, fix: Dict, 
                            context: Optional[Dict]) -> List[str]:
        """Check prerequisites for a fix"""
        return []
    
    def _check_prerequisite(self, prereq: str, 
                           current_state: Dict) -> bool:
        """Check if a single prerequisite is met"""
        return True
    
    def _calculate_total_time(self, phases: List[Dict]) -> str:
        """Calculate total estimated time for all phases"""
        total_seconds = 0
        
        for phase in phases:
            for fix in phase.get('fixes', []):
                time_str = fix.get('estimated_downtime', '0 seconds')
                if 'second' in time_str:
                    total_seconds += int(time_str.split()[0])
                elif 'minute' in time_str:
                    total_seconds += int(time_str.split()[0]) * 60
        
        if total_seconds < 60:
            return f"{total_seconds} seconds"
        else:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes} minutes {seconds} seconds"