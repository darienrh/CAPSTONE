#!/usr/bin/env python3
"""inference_engine.py - Reasoning engine for network troubleshooting"""

from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict, deque
from datetime import datetime

# Import certainty factor system
try:
    from core.certainty_factors import CertaintyFactor, evaluate_diagnosis_certainty
except ImportError:
    # Fallback if certainty_factors not available
    CertaintyFactor = None
    evaluate_diagnosis_certainty = None


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
            'no_eigrp_neighbor': [
                'as_mismatch', 'k_value_mismatch', 'authentication_failure', 
                'interface_down', 'wrong_subnet'
            ],
            'no_ospf_neighbor': [
                'process_id_mismatch', 'area_mismatch', 'hello_timer_mismatch', 
                'authentication_failure', 'interface_down'
            ],
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
        IMPROVED: Diagnose with proper three-tier decision making

        Args:
            symptoms: List of detected symptoms
            context: Additional context

        Returns:
            List of diagnoses sorted by tier and confidence
        """
        diagnoses = []

        for symptom in symptoms:
            device_name = symptom.get('device', '')

            # Get baseline context
            baseline_context = None
            if self.kb.config_manager and device_name:
                baseline_context = self.kb.config_manager.get_device_baseline(device_name)

            # Get tiered recommendations (now with proper validation)
            tiered_recs = self.kb.get_tiered_recommendations(
                symptom,
                baseline_context=baseline_context
            )

            # Process Tier 1 (high confidence, topology-independent)
            for rule in tiered_recs['tier1']:
                diagnosis = self._create_diagnosis_from_rule(rule, symptom, tier=1)
                diagnoses.append(diagnosis)

            # Process Tier 2 (baseline-validated)
            for rule in tiered_recs['tier2']:
                diagnosis = self._create_diagnosis_from_rule(rule, symptom, tier=2)
                diagnoses.append(diagnosis)

            # Process Tier 3 (complex/revert to baseline)
            for rule in tiered_recs['tier3']:
                diagnosis = self._create_diagnosis_from_rule(rule, symptom, tier=3)
                diagnoses.append(diagnosis)

        # Sort by tier first, then confidence
        diagnoses.sort(key=lambda x: (x['tier'], -x['confidence']))

        return diagnoses

    def _create_diagnosis_from_rule(self, rule, symptom, tier):
        """
        Create diagnosis dict from rule

        Args:
            rule: Matched rule
            symptom: Original symptom
            tier: Tier number (1, 2, or 3)

        Returns:
            Diagnosis dict
        """
        return {
            'root_cause': symptom.get('type', ''),
            'confidence': rule['confidence'],
            'evidence': [symptom],
            'affected_components': [
                symptom.get('interface', symptom.get('device', 'unknown'))
            ],
            'rule_id': rule.get('id', 'unknown'),
            'suggested_action': rule['action']['description'],
            'commands': rule['action'].get('commands', []),
            'tier': tier,
            'baseline_validated': rule.get('baseline_validated', False),
            'requires_manual': rule['action'].get('requires_manual', False),
            'verification': rule['action'].get('verification', 'Verify manually')
        }
    
    def recommend_fixes(self, diagnosis, max_recommendations=3):
        """
        IMPROVED: Recommend fixes with formatted commands
        
        Args:
            diagnosis: Diagnosis from diagnose()
            max_recommendations: Max fixes to recommend
        
        Returns:
            List of fix recommendations
        """
        recommendations = []
        
        if isinstance(diagnosis, list):
            diagnosis_list = diagnosis
        else:
            diagnosis_list = [diagnosis]
        
        for diag in diagnosis_list[:max_recommendations]:
            recommendation = {
                'fix_id': f"fix_{len(recommendations)+1}",
                'description': diag.get('suggested_action', 'Unknown fix'),
                'commands': diag.get('commands', []),  # Already formatted!
                'confidence': diag['confidence'],
                'tier': diag.get('tier', 3),
                'baseline_validated': diag.get('baseline_validated', False),
                'expected_outcome': f"Resolve {diag['root_cause']}",
                'risks': self._assess_risks(diag),
                'verification': diag.get('verification', 'Verify manually'),
                'requires_manual': diag.get('requires_manual', False)
            }
            recommendations.append(recommendation)
        
        return recommendations
    
    def _assess_risks(self, diagnosis: Dict) -> List[str]:
        """
        IMPROVED: Assess risks from diagnosis with tier consideration
        
        Args:
            diagnosis: Diagnosis dict with tier and baseline info
            
        Returns:
            List of risk descriptions
        """
        risks = []
        
        if diagnosis.get('requires_manual'):
            risks.append("Requires manual intervention")
        
        commands = diagnosis.get('commands', [])
        if any('no router' in str(cmd) for cmd in commands):
            risks.append("Will remove routing protocol configuration")
        
        if any('shutdown' in str(cmd) for cmd in commands):
            risks.append("May cause temporary connectivity loss")
        
        # Tier-based risk assessment
        tier = diagnosis.get('tier', 3)
        if tier == 3 and not diagnosis.get('requires_manual'):
            risks.append("Low confidence - consider baseline revert")
        
        # Baseline validation status
        if not diagnosis.get('baseline_validated', False) and diagnosis.get('topology_dependent', False):
            risks.append("Not validated against baseline configuration")
        
        return risks if risks else ["Minimal risk"]
    
    def chain_reasoning(self, initial_problem, depth=3):
        """
        ENHANCED: Perform multi-step reasoning to trace problem chains
        
        Args:
            initial_problem: Starting problem
            depth: Maximum reasoning depth
        
        Returns:
            Problem chain showing cause-effect relationships with impact analysis
        """
        problem_type = initial_problem.get('type', '').lower()
        device = initial_problem.get('device', 'unknown')
        interface = initial_problem.get('interface', '')
        
        chain = {
            'root': problem_type,
            'device': device,
            'interface': interface,
            'leads_to': [],
            'impact': self._assess_chain_impact(problem_type),
            'priority': 'high' if problem_type in ['shutdown', 'interface_down'] else 'medium'
        }
        
        if depth <= 0:
            return chain
        
        # Check what this problem blocks
        if problem_type in self.cause_relationships:
            blocked_items = self.cause_relationships[problem_type].get('blocks', [])
            
            for blocked in blocked_items:
                sub_chain = self.chain_reasoning(
                    {'type': blocked, 'device': device, 'interface': interface},
                    depth - 1
                )
                chain['leads_to'].append(sub_chain)
        
        # Special case: interface down blocks everything on that interface
        if 'shutdown' in problem_type or 'interface' in problem_type and 'down' in problem_type:
            chain['leads_to'].extend([
                {'root': 'eigrp_adjacency', 'blocked_by': problem_type},
                {'root': 'ospf_adjacency', 'blocked_by': problem_type}
            ])
        
        return chain
    
    def _assess_chain_impact(self, problem_type: str) -> str:
        """Assess the impact level of a problem in the chain"""
        high_impact = ['shutdown', 'interface_down', 'as_mismatch', 'process_id_mismatch']
        medium_impact = ['ip_mismatch', 'timer_mismatch', 'k_value_mismatch']
        
        if any(hi in problem_type for hi in high_impact):
            return 'high'
        elif any(mi in problem_type for mi in medium_impact):
            return 'medium'
        else:
            return 'low'
    
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
        ENHANCED: Identify fixes that may conflict with each other
        
        Args:
            fix_list: List of proposed fixes
        
        Returns:
            List of conflict groups with resolution suggestions
        """
        conflicts = []
        
        for i, fix1 in enumerate(fix_list):
            for j, fix2 in enumerate(fix_list[i+1:], i+1):
                conflict = self._check_fix_conflict(fix1, fix2)
                if conflict:
                    conflicts.append({
                        'conflict_type': conflict['type'],
                        'fix_indices': [i, j],
                        'fix1': fix1.get('type', 'unknown'),
                        'fix2': fix2.get('type', 'unknown'),
                        'reason': conflict['reason'],
                        'resolution': conflict.get('resolution', 'Apply fixes sequentially'),
                        'severity': conflict.get('severity', 'medium')
                    })
        
        return conflicts
    
    def _check_fix_conflict(self, fix1: Dict, fix2: Dict) -> Optional[Dict]:
        """ENHANCED: Check if two fixes conflict with detailed analysis"""
        device1 = fix1.get('device', '')
        device2 = fix2.get('device', '')
        
        # No conflict if different devices
        if device1 != device2:
            return None
        
        interface1 = fix1.get('interface', '')
        interface2 = fix2.get('interface', '')
        
        # Same interface conflict
        if interface1 and interface2 and interface1 == interface2:
            # Check if fixes are compatible
            type1 = fix1.get('type', '')
            type2 = fix2.get('type', '')
            
            # IP change + shutdown are compatible (do IP first, then no shutdown)
            if ('ip address' in type1 and 'shutdown' in type2) or \
               ('shutdown' in type1 and 'ip address' in type2):
                return {
                    'type': 'compatible_sequence',
                    'reason': f"Both fixes target {interface1} but can be sequenced",
                    'resolution': "Apply IP configuration first, then bring interface up",
                    'severity': 'low'
                }
            
            return {
                'type': 'same_interface',
                'reason': f"Both fixes target the same interface {interface1}",
                'resolution': "Apply fixes sequentially with verification between",
                'severity': 'medium'
            }
        
        category1 = fix1.get('category', '')
        category2 = fix2.get('category', '')
        type1 = fix1.get('type', '')
        type2 = fix2.get('type', '')
        
        # Protocol reconfiguration conflicts
        if category1 == category2 and category1 in ['eigrp', 'ospf']:
            if 'as mismatch' in type1 or 'as mismatch' in type2:
                return {
                    'type': 'protocol_reconfiguration',
                    'reason': "AS reconfiguration may affect other EIGRP fixes",
                    'resolution': "Apply AS fix first, then revalidate other fixes",
                    'severity': 'high'
                }
            
            if 'process id' in type1 or 'process id' in type2:
                return {
                    'type': 'protocol_reconfiguration',
                    'reason': "Process ID change may affect other OSPF fixes",
                    'resolution': "Apply process ID fix first, then revalidate other fixes",
                    'severity': 'high'
                }
        
        # Interface down blocks protocol fixes
        if 'shutdown' in type1 and category2 in ['eigrp', 'ospf']:
            if interface1 == interface2:
                return {
                    'type': 'dependency',
                    'reason': f"Interface {interface1} must be up before protocol fixes",
                    'resolution': "Bring interface up first, then apply protocol fixes",
                    'severity': 'high'
                }
        
        return None
    
    def build_fix_plan(self, fix_list: List[Dict]) -> Dict:
        """
        NEW: Build optimized fix plan to minimize downtime and conflicts
        
        Args:
            fix_list: List of fixes to plan
        
        Returns:
            Optimized fix plan with phases and ordering
        """
        # Detect conflicts
        conflicts = self.detect_conflicting_fixes(fix_list)
        
        # Build dependency graph
        dependencies = self._build_dependency_graph(fix_list, conflicts)
        
        # Group fixes into phases
        phases = self._create_fix_phases(fix_list, dependencies)
        
        # Calculate total estimated time
        total_time = sum(
            self._parse_time(self._estimate_downtime(fix))
            for fix in fix_list
        )
        
        return {
            'phases': phases,
            'total_fixes': len(fix_list),
            'conflicts_detected': len(conflicts),
            'conflicts': conflicts,
            'estimated_total_time': self._format_time(total_time),
            'optimization_applied': True
        }
    
    def _build_dependency_graph(self, fix_list: List[Dict], conflicts: List[Dict]) -> Dict:
        """Build dependency graph from conflicts"""
        dependencies = defaultdict(list)
        
        for conflict in conflicts:
            if conflict['severity'] == 'high' or conflict['conflict_type'] == 'dependency':
                # Fix with higher priority should go first
                idx1, idx2 = conflict['fix_indices']
                fix1 = fix_list[idx1]
                fix2 = fix_list[idx2]
                
                # Interface fixes before protocol fixes
                if 'shutdown' in fix1.get('type', ''):
                    dependencies[idx2].append(idx1)
                elif 'shutdown' in fix2.get('type', ''):
                    dependencies[idx1].append(idx2)
                # IP fixes before protocol fixes
                elif 'ip address' in fix1.get('type', ''):
                    dependencies[idx2].append(idx1)
                elif 'ip address' in fix2.get('type', ''):
                    dependencies[idx1].append(idx2)
        
        return dependencies
    
    def _create_fix_phases(self, fix_list: List[Dict], dependencies: Dict) -> List[Dict]:
        """Create fix phases based on dependencies"""
        phases = []
        applied = set()
        
        while len(applied) < len(fix_list):
            current_phase = []
            
            for i, fix in enumerate(fix_list):
                if i in applied:
                    continue
                
                # Check if all dependencies are satisfied
                deps = dependencies.get(i, [])
                if all(d in applied for d in deps):
                    current_phase.append({
                        'fix_index': i,
                        'fix': fix,
                        'device': fix.get('device', ''),
                        'type': fix.get('type', ''),
                        'estimated_time': self._estimate_downtime(fix)
                    })
                    applied.add(i)
            
            if current_phase:
                phases.append({
                    'phase_number': len(phases) + 1,
                    'fixes': current_phase,
                    'can_parallelize': len(current_phase) > 1 and self._can_parallelize(current_phase),
                    'phase_time': self._format_time(
                        max(self._parse_time(f['estimated_time']) for f in current_phase)
                        if current_phase else 0
                    )
                })
            else:
                # Circular dependency or error - add remaining fixes
                break
        
        return phases
    
    def _can_parallelize(self, fixes: List[Dict]) -> bool:
        """Check if fixes in a phase can be applied in parallel"""
        devices = set(f['fix'].get('device', '') for f in fixes)
        # Can parallelize if all fixes are on different devices
        return len(devices) == len(fixes)
    
    def _parse_time(self, time_str: str) -> int:
        """Parse time string to seconds"""
        if 'minute' in time_str:
            return int(time_str.split()[0].replace('~', '')) * 60
        elif 'second' in time_str:
            return int(time_str.split()[0].replace('~', '').replace('<', ''))
        return 10
    
    def _format_time(self, seconds: int) -> str:
        """Format seconds to readable string"""
        if seconds < 60:
            return f"{seconds} seconds"
        else:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}m {secs}s" if secs > 0 else f"{minutes}m"
    
    def predict_outcome(self, fix, current_state):
        """
        ENHANCED: Predict the outcome of applying a fix with detailed impact analysis
        
        Args:
            fix: Fix to be applied
            current_state: Current network state
        
        Returns:
            Predicted state after fix with confidence and impact details
        """
        predicted_state = dict(current_state)
        fix_type = fix.get('type', '')
        device = fix.get('device', '')
        interface = fix.get('interface', '')
        
        # Predict state changes based on fix type
        if 'shutdown' in fix_type:
            if interface:
                predicted_state[f"{device}_{interface}_status"] = "up"
                predicted_state[f"{device}_{interface}_admin_status"] = "up"
                # Predict protocol adjacencies will form
                if 'eigrp' in current_state.get(f"{device}_protocols", []):
                    predicted_state[f"{device}_{interface}_eigrp"] = "forming"
                if 'ospf' in current_state.get(f"{device}_protocols", []):
                    predicted_state[f"{device}_{interface}_ospf"] = "forming"
        
        elif 'ip address' in fix_type:
            expected_ip = fix.get('expected_ip', '')
            expected_mask = fix.get('expected_mask', '')
            if interface and expected_ip:
                predicted_state[f"{device}_{interface}_ip"] = expected_ip
                predicted_state[f"{device}_{interface}_mask"] = expected_mask
                predicted_state[f"{device}_{interface}_subnet_match"] = "correct"
        
        elif 'eigrp' in fix_type:
            if 'timer' in fix_type:
                predicted_state[f"{device}_{interface}_eigrp_timers"] = "matched"
                predicted_state[f"{device}_eigrp_adjacency"] = "forming"
            elif 'k-value' in fix_type:
                predicted_state[f"{device}_eigrp_k_values"] = "matched"
                predicted_state[f"{device}_eigrp_adjacency"] = "forming"
        
        elif 'ospf' in fix_type:
            if 'timer' in fix_type:
                predicted_state[f"{device}_{interface}_ospf_timers"] = "matched"
                predicted_state[f"{device}_ospf_adjacency"] = "forming"
            elif 'router id' in fix_type:
                predicted_state[f"{device}_ospf_router_id"] = fix.get('expected', 'configured')
        
        # Calculate confidence based on fix type and historical success
        base_confidence = fix.get('confidence', 0.8)
        
        # Adjust confidence based on complexity
        if fix.get('requires_manual', False):
            base_confidence *= 0.7
        if fix.get('baseline_validated', False):
            base_confidence *= 1.1
        
        confidence = min(0.95, base_confidence)
        
        # Identify all changes
        changes = self._identify_changes(current_state, predicted_state)
        
        # Predict side effects
        side_effects = self._predict_side_effects(fix, current_state)
        
        return {
            'predicted_state': predicted_state,
            'confidence': confidence,
            'changes': changes,
            'side_effects': side_effects,
            'estimated_downtime': self._estimate_downtime(fix),
            'success_probability': confidence
        }
    
    def _predict_side_effects(self, fix: Dict, current_state: Dict) -> List[str]:
        """Predict potential side effects of applying a fix"""
        side_effects = []
        fix_type = fix.get('type', '')
        
        if 'no shutdown' in str(fix.get('commands', [])):
            side_effects.append("Interface will come up - may cause routing updates")
        
        if 'router eigrp' in str(fix.get('commands', [])) or 'router ospf' in str(fix.get('commands', [])):
            side_effects.append("Routing protocol changes - may cause brief convergence")
        
        if 'ip address' in fix_type:
            side_effects.append("IP change will drop existing connections on this interface")
        
        if 'timer' in fix_type:
            side_effects.append("Timer changes may cause brief adjacency flap")
        
        return side_effects if side_effects else ["No significant side effects expected"]
    
    def _estimate_downtime(self, fix: Dict) -> str:
        """Estimate downtime caused by fix"""
        commands = fix.get('commands', [])
        num_commands = len(commands)
        
        # Base time per command
        base_time = num_commands * 2
        
        # Add extra time for protocol changes
        if any('router' in str(cmd) for cmd in commands):
            base_time += 10  # Protocol convergence time
        
        if any('ip address' in str(cmd) for cmd in commands):
            base_time += 5  # Interface reconfiguration time
        
        if base_time < 5:
            return "< 5 seconds"
        elif base_time < 30:
            return f"~{base_time} seconds"
        else:
            return f"~{base_time // 60} minutes"
    
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
    
    # ========================================================================
    # FORWARD CHAINING (Data-Driven Reasoning)
    # ========================================================================
    
    def forward_chain(self, initial_facts: List[Dict], max_iterations: int = 10) -> Dict:
        """
        NEW: Forward chaining inference (data-driven reasoning).
        
        Start from known facts (symptoms) and apply rules to derive new conclusions.
        Continues until no new facts can be derived or max iterations reached.
        
        Args:
            initial_facts: List of initial symptoms/facts
            max_iterations: Maximum inference iterations
        
        Returns:
            Dictionary with derived conclusions and reasoning trace
        """
        print(f"[ForwardChain] Starting with {len(initial_facts)} initial facts")
        
        # Working memory: facts we know
        working_memory = set()
        for fact in initial_facts:
            fact_key = self._fact_to_key(fact)
            working_memory.add(fact_key)
        
        # Track which rules have been fired (refractoriness)
        fired_rules = set()
        
        # Reasoning trace
        trace = []
        derived_conclusions = []
        
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            new_facts_added = False
            
            print(f"[ForwardChain] Iteration {iteration}: {len(working_memory)} facts in memory")
            
            # Match-Resolve-Act cycle
            for rule_id, rule in self.kb.rules.items():
                # Skip if rule already fired (refractoriness)
                if rule_id in fired_rules:
                    continue
                
                # Check if rule conditions are satisfied
                if self._rule_matches_facts(rule, working_memory, initial_facts):
                    # Fire the rule
                    conclusion = self._fire_rule(rule, initial_facts)
                    
                    if conclusion:
                        conclusion_key = self._fact_to_key(conclusion)
                        
                        if conclusion_key not in working_memory:
                            # New fact derived!
                            working_memory.add(conclusion_key)
                            derived_conclusions.append(conclusion)
                            new_facts_added = True
                            
                            trace.append({
                                'iteration': iteration,
                                'rule_id': rule_id,
                                'rule_description': rule['action']['description'],
                                'conclusion': conclusion,
                                'confidence': rule.get('confidence', 0.5)
                            })
                            
                            print(f"[ForwardChain] Rule {rule_id} fired -> {conclusion.get('type', 'unknown')}")
                    
                    # Mark rule as fired
                    fired_rules.add(rule_id)
            
            # Stop if no new facts were added
            if not new_facts_added:
                print(f"[ForwardChain] No new facts derived. Stopping at iteration {iteration}")
                break
        
        return {
            'mode': 'forward_chaining',
            'iterations': iteration,
            'initial_facts': len(initial_facts),
            'derived_conclusions': derived_conclusions,
            'total_facts': len(working_memory),
            'rules_fired': len(fired_rules),
            'reasoning_trace': trace,
            'converged': iteration < max_iterations
        }
    
    def _fact_to_key(self, fact: Dict) -> str:
        """Convert a fact to a unique key for working memory."""
        return f"{fact.get('type', '')}_{fact.get('device', '')}_{fact.get('interface', '')}"
    
    def _rule_matches_facts(self, rule: Dict, working_memory: Set[str], facts: List[Dict]) -> bool:
        """Check if a rule's conditions match the current facts."""
        condition = rule.get('condition', {})
        problem_type = condition.get('problem_type', '')
        category = condition.get('category', '')
        
        # Check if any fact matches this rule's conditions
        for fact in facts:
            fact_key = self._fact_to_key(fact)
            if fact_key in working_memory:
                if (fact.get('type', '') == problem_type or
                    fact.get('category', '') == category):
                    return True
        
        return False
    
    def _fire_rule(self, rule: Dict, facts: List[Dict]) -> Optional[Dict]:
        """Fire a rule and generate its conclusion."""
        action = rule.get('action', {})
        
        # Create a conclusion fact
        conclusion = {
            'type': f"conclusion_{rule.get('id', 'unknown')}",
            'category': rule.get('category', 'derived'),
            'fix_type': action.get('fix_type', 'unknown'),
            'description': action.get('description', ''),
            'confidence': rule.get('confidence', 0.5),
            'derived_from': rule.get('id', 'unknown'),
            'timestamp': datetime.now().isoformat()
        }
        
        return conclusion
    
    # ========================================================================
    # BACKWARD CHAINING (Goal-Driven Reasoning)
    # ========================================================================
    
    def backward_chain(self, goal: Dict, available_facts: List[Dict], 
                      max_depth: int = 5) -> Dict:
        """
        NEW: Backward chaining inference (goal-driven reasoning).
        
        Start from a goal (hypothesis) and work backwards to verify it with evidence.
        
        Args:
            goal: Goal/hypothesis to prove
            available_facts: Available facts/symptoms
            max_depth: Maximum recursion depth
        
        Returns:
            Dictionary with proof status and reasoning trace
        """
        print(f"[BackwardChain] Attempting to prove goal: {goal.get('type', 'unknown')}")
        
        # Track visited goals to avoid cycles
        visited = set()
        
        # Reasoning trace
        trace = []
        
        # Attempt to prove the goal
        proof_result = self._prove_goal(goal, available_facts, visited, trace, depth=0, max_depth=max_depth)
        
        return {
            'mode': 'backward_chaining',
            'goal': goal,
            'proved': proof_result['proved'],
            'confidence': proof_result['confidence'],
            'reasoning_trace': trace,
            'supporting_facts': proof_result.get('supporting_facts', []),
            'applied_rules': proof_result.get('applied_rules', [])
        }
    
    def _prove_goal(self, goal: Dict, facts: List[Dict], visited: Set[str],
                   trace: List[Dict], depth: int, max_depth: int) -> Dict:
        """Recursively attempt to prove a goal."""
        goal_key = self._fact_to_key(goal)
        
        # Check if already visited (cycle detection)
        if goal_key in visited:
            return {'proved': False, 'confidence': 0.0, 'reason': 'Cycle detected'}
        
        # Check depth limit
        if depth >= max_depth:
            return {'proved': False, 'confidence': 0.0, 'reason': 'Max depth reached'}
        
        visited.add(goal_key)
        
        # Check if goal is directly satisfied by available facts
        for fact in facts:
            if self._fact_matches_goal(fact, goal):
                trace.append({
                    'depth': depth,
                    'goal': goal.get('type', 'unknown'),
                    'method': 'direct_fact',
                    'confidence': 1.0
                })
                return {
                    'proved': True,
                    'confidence': 1.0,
                    'supporting_facts': [fact],
                    'applied_rules': []
                }
        
        # Try to prove goal using rules (backward chaining)
        for rule_id, rule in self.kb.rules.items():
            # Check if this rule can derive the goal
            if self._rule_derives_goal(rule, goal):
                # Get rule's prerequisites
                prerequisites = self._get_rule_prerequisites(rule)
                
                # Try to prove all prerequisites
                all_proved = True
                combined_confidence = rule.get('confidence', 0.5)
                supporting_facts = []
                applied_rules = [rule_id]
                
                for prereq in prerequisites:
                    prereq_result = self._prove_goal(
                        prereq, facts, visited, trace, depth + 1, max_depth
                    )
                    
                    if not prereq_result['proved']:
                        all_proved = False
                        break
                    
                    # Combine confidences
                    if CertaintyFactor:
                        combined_confidence = CertaintyFactor.propagate_through_rule(
                            prereq_result['confidence'],
                            combined_confidence
                        )
                    else:
                        combined_confidence *= prereq_result['confidence']
                    
                    supporting_facts.extend(prereq_result.get('supporting_facts', []))
                    applied_rules.extend(prereq_result.get('applied_rules', []))
                
                if all_proved:
                    trace.append({
                        'depth': depth,
                        'goal': goal.get('type', 'unknown'),
                        'method': 'rule_application',
                        'rule_id': rule_id,
                        'confidence': combined_confidence
                    })
                    return {
                        'proved': True,
                        'confidence': combined_confidence,
                        'supporting_facts': supporting_facts,
                        'applied_rules': applied_rules
                    }
        
        # Goal could not be proved
        trace.append({
            'depth': depth,
            'goal': goal.get('type', 'unknown'),
            'method': 'failed',
            'confidence': 0.0
        })
        
        return {'proved': False, 'confidence': 0.0, 'reason': 'No proof found'}
    
    def _fact_matches_goal(self, fact: Dict, goal: Dict) -> bool:
        """Check if a fact satisfies a goal."""
        return (fact.get('type', '') == goal.get('type', '') and
                fact.get('category', '') == goal.get('category', ''))
    
    def _rule_derives_goal(self, rule: Dict, goal: Dict) -> bool:
        """Check if a rule can derive the goal."""
        action = rule.get('action', {})
        condition = rule.get('condition', {})
        
        return (condition.get('problem_type', '') == goal.get('type', '') or
                condition.get('category', '') == goal.get('category', ''))
    
    def _get_rule_prerequisites(self, rule: Dict) -> List[Dict]:
        """Get prerequisites (conditions) for a rule."""
        condition = rule.get('condition', {})
        symptoms = condition.get('symptoms', [])
        
        prerequisites = []
        for symptom in symptoms:
            prerequisites.append({
                'type': symptom,
                'category': condition.get('category', 'unknown')
            })
        
        return prerequisites
    
    # ========================================================================
    # SYSTEMATIC CONFLICT RESOLUTION
    # ========================================================================
    
    def resolve_conflicts_systematic(self, conflicting_rules: List[Dict],
                                    context: Optional[Dict] = None) -> Dict:
        """
        NEW: Systematically resolve conflicts between competing rules.
        
        Applies multiple resolution strategies in order:
        1. Specificity - More specific rules win
        2. Recency - Newer rules preferred
        3. Confidence - Higher confidence wins
        4. Support - More historical evidence wins
        5. Refractoriness - Don't reapply same rule
        
        Args:
            conflicting_rules: List of rules that conflict
            context: Additional context for resolution
        
        Returns:
            Dictionary with winning rule and resolution explanation
        """
        if not conflicting_rules:
            return {'winner': None, 'reason': 'No rules to resolve'}
        
        if len(conflicting_rules) == 1:
            return {
                'winner': conflicting_rules[0],
                'reason': 'Only one rule',
                'strategy': 'none'
            }
        
        print(f"[ConflictResolution] Resolving conflict between {len(conflicting_rules)} rules")
        
        # Strategy 1: Specificity
        winner = self._resolve_by_specificity(conflicting_rules)
        if winner:
            return {
                'winner': winner,
                'reason': 'Most specific rule',
                'strategy': 'specificity',
                'candidates': len(conflicting_rules)
            }
        
        # Strategy 2: Recency
        winner = self._resolve_by_recency(conflicting_rules)
        if winner:
            return {
                'winner': winner,
                'reason': 'Most recently created/updated rule',
                'strategy': 'recency',
                'candidates': len(conflicting_rules)
            }
        
        # Strategy 3: Confidence
        winner = self._resolve_by_confidence(conflicting_rules)
        if winner:
            return {
                'winner': winner,
                'reason': 'Highest confidence',
                'strategy': 'confidence',
                'candidates': len(conflicting_rules)
            }
        
        # Strategy 4: Support (historical success)
        winner = self._resolve_by_support(conflicting_rules)
        if winner:
            return {
                'winner': winner,
                'reason': 'Best historical performance',
                'strategy': 'support',
                'candidates': len(conflicting_rules)
            }
        
        # Default: Return first rule
        return {
            'winner': conflicting_rules[0],
            'reason': 'Default selection (no clear winner)',
            'strategy': 'default',
            'candidates': len(conflicting_rules)
        }
    
    def _resolve_by_specificity(self, rules: List[Dict]) -> Optional[Dict]:
        """Resolve by specificity - more specific rules win."""
        max_specificity = -1
        most_specific = None
        
        for rule in rules:
            specificity = self._calculate_rule_specificity(rule)
            if specificity > max_specificity:
                max_specificity = specificity
                most_specific = rule
        
        # Only return if there's a clear winner
        specific_rules = [r for r in rules if self._calculate_rule_specificity(r) == max_specificity]
        if len(specific_rules) == 1:
            return most_specific
        
        return None
    
    def _calculate_rule_specificity(self, rule: Dict) -> int:
        """Calculate how specific a rule is (more conditions = more specific)."""
        condition = rule.get('condition', {})
        specificity = 0
        
        # Count conditions
        if condition.get('problem_type'):
            specificity += 2
        if condition.get('category'):
            specificity += 1
        specificity += len(condition.get('symptoms', []))
        
        # Topology-dependent rules are more specific
        if rule.get('topology_dependent', False):
            specificity += 1
        
        # Context-specific rules are more specific
        if rule.get('context_specific', False):
            specificity += 2
        
        return specificity
    
    def _resolve_by_recency(self, rules: List[Dict]) -> Optional[Dict]:
        """Resolve by recency - newer rules preferred."""
        most_recent = None
        latest_time = None
        
        for rule in rules:
            created = rule.get('created') or rule.get('last_updated')
            if created:
                try:
                    rule_time = datetime.fromisoformat(created)
                    if latest_time is None or rule_time > latest_time:
                        latest_time = rule_time
                        most_recent = rule
                except (ValueError, TypeError):
                    continue
        
        return most_recent
    
    def _resolve_by_confidence(self, rules: List[Dict]) -> Optional[Dict]:
        """Resolve by confidence - highest confidence wins."""
        max_confidence = -1
        highest_confidence = None
        
        for rule in rules:
            confidence = rule.get('confidence', 0)
            if confidence > max_confidence:
                max_confidence = confidence
                highest_confidence = rule
        
        # Only return if there's a significant difference (>5%)
        high_conf_rules = [r for r in rules if r.get('confidence', 0) >= max_confidence - 0.05]
        if len(high_conf_rules) == 1:
            return highest_confidence
        
        return None
    
    def _resolve_by_support(self, rules: List[Dict]) -> Optional[Dict]:
        """Resolve by support - best historical performance wins."""
        if not CertaintyFactor:
            return None
        
        max_support = -1
        best_support = None
        
        for rule in rules:
            rule_id = rule.get('id', '')
            support = CertaintyFactor.calculate_rule_support(rule_id, self.kb.problem_history)
            
            if support > max_support:
                max_support = support
                best_support = rule
        
        return best_support
