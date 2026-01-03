#!/usr/bin/env python3
"""inference_engine.py - Reasoning engine for network troubleshooting"""

from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class InferenceEngine:
    """
    Performs reasoning to:
    - Diagnose root causes
    - Chain rules together
    - Prioritize fixes
    - Handle uncertainty
    """
    
    def __init__(self, knowledge_base):
        """
        Initialize inference engine
        
        Args:
            knowledge_base: KnowledgeBase instance
        """
        self.kb = knowledge_base
        
        self.symptom_to_cause = {
            'interface_down': ['shutdown', 'cable_unplugged', 'hardware_failure'],
            'no_eigrp_neighbor': ['as_mismatch', 'k_value_mismatch', 'authentication_failure', 'interface_down', 'wrong_subnet'],
            'no_ospf_neighbor': ['process_id_mismatch', 'area_mismatch', 'hello_timer_mismatch', 'authentication_failure', 'interface_down'],
            'ip_mismatch': ['misconfiguration', 'manual_change'],
        }
        
        self.cause_relationships = {
            'interface_down': {'blocks': ['eigrp_adjacency', 'ospf_adjacency']},
            'wrong_subnet': {'blocks': ['eigrp_adjacency', 'ospf_adjacency']},
            'as_mismatch': {'blocks': ['eigrp_adjacency']},
            'process_id_mismatch': {'blocks': ['ospf_adjacency']},
        }
    
    def diagnose(self, symptoms, context=None):
        """
        Diagnose root cause from symptoms
        
        Args:
            symptoms: List of detected symptoms
            context: Additional context (device name, topology, etc.)
        
        Returns:
            List of probable root causes with confidence scores
        """
        diagnoses = []
        
        for symptom in symptoms:
            symptom_type = symptom.get('type', '')
            
            matching_rules = self.kb.get_matching_rules(symptom)
            
            for rule in matching_rules:
                diagnosis = {
                    'root_cause': symptom_type,
                    'confidence': rule['confidence'] * symptom.get('confidence', 1.0),
                    'evidence': [symptom],
                    'affected_components': [symptom.get('interface', symptom.get('device', 'unknown'))],
                    'rule_id': rule['id'],
                    'suggested_action': rule['action']['description']
                }
                diagnoses.append(diagnosis)
            
            possible_causes = self.symptom_to_cause.get(symptom_type, [symptom_type])
            for cause in possible_causes:
                if not any(d['root_cause'] == cause for d in diagnoses):
                    diagnoses.append({
                        'root_cause': cause,
                        'confidence': 0.5,
                        'evidence': [symptom],
                        'affected_components': [symptom.get('interface', 'unknown')],
                        'suggested_action': f"Investigate {cause}"
                    })
        
        diagnoses.sort(key=lambda x: x['confidence'], reverse=True)
        
        return diagnoses[:5]
    
    def recommend_fixes(self, diagnosis, max_recommendations=3):
        """
        Recommend fixes based on diagnosis
        
        Args:
            diagnosis: Output from diagnose()
            max_recommendations: Maximum number of fixes to recommend
        
        Returns:
            Prioritized list of recommended fixes
        """
        recommendations = []
        
        if isinstance(diagnosis, list):
            diagnosis_list = diagnosis
        else:
            diagnosis_list = [diagnosis]
        
        for diag in diagnosis_list[:max_recommendations]:
            root_cause = diag['root_cause']
            confidence = diag['confidence']
            
            problem_dict = {
                'type': root_cause,
                'confidence': confidence
            }
            
            if diag.get('evidence'):
                problem_dict.update(diag['evidence'][0])
            
            matching_rules = self.kb.get_matching_rules(problem_dict)
            
            for rule in matching_rules[:1]:
                recommendation = {
                    'fix_id': f"fix_{len(recommendations)+1}",
                    'description': rule['action']['description'],
                    'commands': rule['action'].get('commands', []),
                    'confidence': rule['confidence'],
                    'expected_outcome': f"Resolve {root_cause}",
                    'risks': self._assess_risks(rule['action']),
                    'verification': rule['action'].get('verification', 'Verify manually')
                }
                recommendations.append(recommendation)
        
        return recommendations
    
    def _assess_risks(self, action: Dict) -> List[str]:
        """Assess risks of an action"""
        risks = []
        
        if action.get('requires_manual'):
            risks.append("Requires manual intervention")
        
        commands = action.get('commands', [])
        if any('no router' in str(cmd) for cmd in commands):
            risks.append("Will remove routing protocol configuration")
        
        if any('shutdown' in str(cmd) for cmd in commands):
            risks.append("May cause temporary connectivity loss")
        
        return risks if risks else ["Minimal risk"]
    
    def chain_reasoning(self, initial_problem, depth=3):
        """
        Perform multi-step reasoning to trace problem chains
        
        Args:
            initial_problem: Starting problem
            depth: Maximum reasoning depth
        
        Returns:
            Problem chain showing cause-effect relationships
        """
        chain = {
            'root': initial_problem.get('type', 'unknown'),
            'leads_to': []
        }
        
        if depth <= 0:
            return chain
        
        problem_type = initial_problem.get('type', '')
        
        if problem_type in self.cause_relationships:
            blocked_items = self.cause_relationships[problem_type].get('blocks', [])
            
            for blocked in blocked_items:
                sub_chain = self.chain_reasoning(
                    {'type': blocked},
                    depth - 1
                )
                chain['leads_to'].append(sub_chain)
        
        return chain
    
    def explain_reasoning(self, diagnosis):
        """
        Generate human-readable explanation of diagnosis
        
        Args:
            diagnosis: Diagnosis result
        
        Returns:
            String explanation of reasoning process
        """
        if isinstance(diagnosis, list):
            if not diagnosis:
                return "No diagnosis could be determined from available symptoms."
            diagnosis = diagnosis[0]
        
        root_cause = diagnosis.get('root_cause', 'unknown')
        confidence = diagnosis.get('confidence', 0)
        evidence = diagnosis.get('evidence', [])
        
        explanation = f"Diagnosis: {root_cause} (confidence: {confidence:.0%})\n"
        
        if evidence:
            explanation += f"\nBased on the following evidence:\n"
            for i, symptom in enumerate(evidence, 1):
                symptom_type = symptom.get('type', 'unknown')
                location = symptom.get('interface', symptom.get('device', ''))
                explanation += f"  {i}. {symptom_type}"
                if location:
                    explanation += f" at {location}"
                explanation += "\n"
        
        explanation += f"\nSuggested action: {diagnosis.get('suggested_action', 'Investigate further')}"
        
        return explanation
    
    def calculate_fix_priority(self, fixes, criteria=None):
        """
        Prioritize fixes based on multiple criteria
        
        Args:
            fixes: List of potential fixes
            criteria: Dict of weights for different factors
        
        Returns:
            Reordered list of fixes with priority scores
        """
        if criteria is None:
            criteria = {
                'confidence': 0.4,
                'impact': 0.3,
                'risk': 0.2,
                'complexity': 0.1
            }
        
        scored_fixes = []
        
        for fix in fixes:
            if isinstance(fix, dict) and 'type' in fix:
                problem = fix
                confidence = problem.get('confidence', 0.5)
                
                impact_score = self._calculate_impact(problem)
                risk_score = self._calculate_risk_score(problem)
                complexity_score = self._calculate_complexity(problem)
                
                priority_score = (
                    confidence * criteria.get('confidence', 0.4) +
                    impact_score * criteria.get('impact', 0.3) +
                    (1 - risk_score) * criteria.get('risk', 0.2) +
                    (1 - complexity_score) * criteria.get('complexity', 0.1)
                )
                
                scored_fixes.append((priority_score, problem))
            else:
                scored_fixes.append((0.5, fix))
        
        scored_fixes.sort(key=lambda x: x[0], reverse=True)
        
        return [fix for score, fix in scored_fixes]
    
    def _calculate_impact(self, problem: Dict) -> float:
        """Calculate impact score (0-1) where 1 is high impact"""
        category = problem.get('category', '')
        severity = problem.get('severity', 'medium')
        
        impact = 0.5
        
        if severity == 'high' or severity == 'critical':
            impact += 0.3
        
        if category in ['eigrp', 'ospf']:
            impact += 0.2
        
        return min(1.0, impact)
    
    def _calculate_risk_score(self, problem: Dict) -> float:
        """Calculate risk score (0-1) where 1 is high risk"""
        problem_type = problem.get('type', '')
        
        high_risk_types = ['as mismatch', 'process id mismatch', 'authentication mismatch']
        medium_risk_types = ['k-value mismatch', 'hello timer mismatch', 'dead interval mismatch']
        
        if problem_type in high_risk_types:
            return 0.8
        elif problem_type in medium_risk_types:
            return 0.5
        else:
            return 0.3
    
    def _calculate_complexity(self, problem: Dict) -> float:
        """Calculate complexity score (0-1) where 1 is high complexity"""
        problem_type = problem.get('type', '')
        
        complex_types = ['as mismatch', 'duplicate router id', 'authentication mismatch']
        
        if problem_type in complex_types:
            return 0.8
        else:
            return 0.3
    
    def detect_conflicting_fixes(self, fix_list):
        """
        Identify fixes that may conflict with each other
        
        Args:
            fix_list: List of proposed fixes
        
        Returns:
            List of conflict groups
        """
        conflicts = []
        
        for i, fix1 in enumerate(fix_list):
            for j, fix2 in enumerate(fix_list[i+1:], i+1):
                conflict = self._check_fix_conflict(fix1, fix2)
                if conflict:
                    conflicts.append({
                        'conflict_type': conflict['type'],
                        'fixes': [i, j],
                        'reason': conflict['reason']
                    })
        
        return conflicts
    
    def _check_fix_conflict(self, fix1: Dict, fix2: Dict) -> Optional[Dict]:
        """Check if two fixes conflict"""
        device1 = fix1.get('device', '')
        device2 = fix2.get('device', '')
        
        if device1 != device2:
            return None
        
        interface1 = fix1.get('interface', '')
        interface2 = fix2.get('interface', '')
        
        if interface1 and interface2 and interface1 == interface2:
            return {
                'type': 'same_interface',
                'reason': f"Both fixes target the same interface {interface1}"
            }
        
        category1 = fix1.get('category', '')
        category2 = fix2.get('category', '')
        
        if category1 == category2 and category1 in ['eigrp', 'ospf']:
            type1 = fix1.get('type', '')
            type2 = fix2.get('type', '')
            
            if 'as mismatch' in type1 or 'as mismatch' in type2:
                return {
                    'type': 'protocol_reconfiguration',
                    'reason': "AS reconfiguration may affect other fixes"
                }
        
        return None
    
    def predict_outcome(self, fix, current_state):
        """
        Predict the outcome of applying a fix
        
        Args:
            fix: Fix to be applied
            current_state: Current network state
        
        Returns:
            Predicted state after fix with confidence
        """
        predicted_state = dict(current_state)
        
        fix_type = fix.get('type', '')
        
        if fix_type == 'shutdown':
            interface = fix.get('interface', '')
            if interface:
                predicted_state[f"{interface}_status"] = "up"
        
        elif 'ip address' in fix_type:
            interface = fix.get('interface', '')
            expected_ip = fix.get('expected_ip', '')
            if interface and expected_ip:
                predicted_state[f"{interface}_ip"] = expected_ip
        
        confidence = fix.get('confidence', 0.8)
        
        return {
            'predicted_state': predicted_state,
            'confidence': confidence,
            'changes': self._identify_changes(current_state, predicted_state)
        }
    
    def _identify_changes(self, old_state: Dict, new_state: Dict) -> List[str]:
        """Identify what changed between states"""
        changes = []
        
        for key in new_state:
            if key not in old_state:
                changes.append(f"Added: {key} = {new_state[key]}")
            elif old_state[key] != new_state[key]:
                changes.append(f"Changed: {key} from {old_state[key]} to {new_state[key]}")
        
        return changes
    
    def handle_uncertainty(self, ambiguous_symptoms):
        """
        Handle cases where diagnosis is uncertain
        
        Args:
            ambiguous_symptoms: Symptoms that could indicate multiple problems
        
        Returns:
            Recommendation for gathering more information
        """
        if not ambiguous_symptoms:
            return {
                'action': 'no_action',
                'reason': 'No ambiguous symptoms provided'
            }
        
        symptom = ambiguous_symptoms[0] if isinstance(ambiguous_symptoms, list) else ambiguous_symptoms
        symptom_type = symptom.get('type', '')
        
        diagnostic_commands = {
            'no_eigrp_neighbor': [
                'show ip eigrp neighbors',
                'show ip eigrp interfaces',
                'show running-config | section eigrp'
            ],
            'no_ospf_neighbor': [
                'show ip ospf neighbor',
                'show ip ospf interface',
                'show running-config | section ospf'
            ],
            'interface_down': [
                'show ip interface brief',
                'show interface status',
                'show running-config interface'
            ]
        }
        
        commands = diagnostic_commands.get(symptom_type, ['show running-config'])
        
        return {
            'action': 'gather_more_info',
            'commands_to_run': commands,
            'expected_clarification': f"Determine specific cause of {symptom_type}",
            'next_steps': "Review command output and re-diagnose"
        }