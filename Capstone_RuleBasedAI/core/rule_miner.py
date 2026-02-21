#!/usr/bin/env python3
"""
rule_miner.py - Automated rule mining from problem history

Extracts new troubleshooting rules from historical problem-solution patterns.
Uses data mining techniques to discover:
- Frequent problem-solution associations
- Temporal patterns and cascading failures
- Context-dependent rules
- Success rate patterns
"""

from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import re


class RuleMiner:
    """
    Mines troubleshooting rules from historical problem-solution data.
    
    Implements:
    - Frequent pattern mining (Apriori-like algorithm)
    - Association rule generation
    - Temporal pattern detection
    - Context-aware rule extraction
    """
    
    # Mining thresholds
    MIN_SUPPORT = 0.3        # Minimum support for frequent patterns (30%)
    MIN_CONFIDENCE = 0.6     # Minimum confidence for rules (60%)
    MIN_OCCURRENCES = 3      # Minimum times pattern must occur
    
    def __init__(self, knowledge_base):
        """
        Initialize rule miner.
        
        Args:
            knowledge_base: KnowledgeBase instance with problem history
        """
        self.kb = knowledge_base
        self.mined_rules = []
        self.pattern_cache = {}
    
    def mine_rules_from_history(self, min_support: Optional[float] = None,
                                min_confidence: Optional[float] = None) -> List[Dict]:
        """
        Mine new rules from problem history.
        
        Args:
            min_support: Minimum support threshold (default: MIN_SUPPORT)
            min_confidence: Minimum confidence threshold (default: MIN_CONFIDENCE)
        
        Returns:
            List of newly mined rules
        """
        if min_support is None:
            min_support = self.MIN_SUPPORT
        if min_confidence is None:
            min_confidence = self.MIN_CONFIDENCE
        
        print(f"[RuleMiner] Mining rules from {len(self.kb.problem_history)} historical entries...")
        
        # Step 1: Extract frequent problem patterns
        frequent_patterns = self._find_frequent_patterns(min_support)
        print(f"[RuleMiner] Found {len(frequent_patterns)} frequent patterns")
        
        # Step 2: Generate association rules
        association_rules = self._generate_association_rules(frequent_patterns, min_confidence)
        print(f"[RuleMiner] Generated {len(association_rules)} association rules")
        
        # Step 3: Mine temporal patterns
        temporal_rules = self._mine_temporal_patterns()
        print(f"[RuleMiner] Found {len(temporal_rules)} temporal patterns")
        
        # Step 4: Extract context-specific rules
        context_rules = self._extract_context_rules(min_support)
        print(f"[RuleMiner] Extracted {len(context_rules)} context-specific rules")
        
        # Combine and deduplicate
        all_rules = association_rules + temporal_rules + context_rules
        unique_rules = self._deduplicate_rules(all_rules)
        
        print(f"[RuleMiner] Total unique rules mined: {len(unique_rules)}")
        
        self.mined_rules = unique_rules
        return unique_rules
    
    def _find_frequent_patterns(self, min_support: float) -> List[Dict]:
        """
        Find frequent problem-solution patterns using Apriori-like algorithm.
        
        Args:
            min_support: Minimum support threshold
        
        Returns:
            List of frequent patterns with their support
        """
        if not self.kb.problem_history:
            return []
        
        # Count problem-solution pairs
        pattern_counts = defaultdict(int)
        total_entries = len(self.kb.problem_history)
        
        for entry in self.kb.problem_history:
            problem = entry.get('problem', {})
            solution = entry.get('solution', {})
            success = entry.get('success', False)
            
            if not success:
                continue  # Only learn from successful solutions
            
            # Create pattern key
            problem_type = problem.get('type', 'unknown')
            category = problem.get('category', 'unknown')
            fix_type = solution.get('fix_type', 'unknown')
            
            pattern_key = (problem_type, category, fix_type)
            pattern_counts[pattern_key] += 1
        
        # Filter by minimum support
        frequent_patterns = []
        for pattern, count in pattern_counts.items():
            support = count / total_entries
            if support >= min_support and count >= self.MIN_OCCURRENCES:
                problem_type, category, fix_type = pattern
                frequent_patterns.append({
                    'problem_type': problem_type,
                    'category': category,
                    'fix_type': fix_type,
                    'support': support,
                    'count': count
                })
        
        # Sort by support (descending)
        frequent_patterns.sort(key=lambda x: x['support'], reverse=True)
        
        return frequent_patterns
    
    def _generate_association_rules(self, frequent_patterns: List[Dict],
                                   min_confidence: float) -> List[Dict]:
        """
        Generate association rules from frequent patterns.
        
        Args:
            frequent_patterns: List of frequent patterns
            min_confidence: Minimum confidence threshold
        
        Returns:
            List of association rules
        """
        rules = []
        
        for pattern in frequent_patterns:
            # Calculate confidence from historical success rate
            problem_type = pattern['problem_type']
            category = pattern['category']
            fix_type = pattern['fix_type']
            
            # Count successes and failures for this pattern
            successes = 0
            attempts = 0
            
            for entry in self.kb.problem_history:
                problem = entry.get('problem', {})
                solution = entry.get('solution', {})
                
                if (problem.get('type') == problem_type and
                    problem.get('category') == category and
                    solution.get('fix_type') == fix_type):
                    attempts += 1
                    if entry.get('success', False):
                        successes += 1
            
            if attempts == 0:
                continue
            
            confidence = successes / attempts
            
            if confidence >= min_confidence:
                # Generate rule
                rule = self._create_rule_from_pattern(
                    pattern, confidence, successes, attempts
                )
                rules.append(rule)
        
        return rules
    
    def _create_rule_from_pattern(self, pattern: Dict, confidence: float,
                                 successes: int, attempts: int) -> Dict:
        """
        Create a rule structure from a mined pattern.
        
        Args:
            pattern: Pattern dictionary
            confidence: Rule confidence
            successes: Number of successful applications
            attempts: Total attempts
        
        Returns:
            Rule dictionary
        """
        problem_type = pattern['problem_type']
        category = pattern['category']
        fix_type = pattern['fix_type']
        
        # Generate rule ID
        rule_id = f"MINED_{category.upper()}_{len(self.mined_rules) + 1:03d}"
        
        # Extract common symptoms from history
        symptoms = self._extract_common_symptoms(problem_type, category)
        
        # Generate fix commands based on fix type
        commands = self._generate_fix_commands(fix_type, category)
        
        # Determine if topology-dependent
        topology_dependent = self._is_topology_dependent(fix_type, category)
        
        rule = {
            'id': rule_id,
            'condition': {
                'problem_type': problem_type,
                'category': category,
                'symptoms': symptoms
            },
            'action': {
                'fix_type': fix_type,
                'commands': commands,
                'description': f"Auto-mined: {fix_type} for {problem_type}",
                'verification': self._get_verification_command(category)
            },
            'confidence': confidence,
            'category': category,
            'topology_dependent': topology_dependent,
            'mined': True,
            'mining_stats': {
                'support': pattern['support'],
                'successes': successes,
                'attempts': attempts,
                'success_rate': confidence
            },
            'created': datetime.now().isoformat()
        }
        
        return rule
    
    def _extract_common_symptoms(self, problem_type: str, category: str) -> List[str]:
        """Extract common symptoms for a problem type."""
        symptom_counts = Counter()
        
        for entry in self.kb.problem_history:
            problem = entry.get('problem', {})
            if (problem.get('type') == problem_type and
                problem.get('category') == category):
                # Extract symptom keywords
                for key, value in problem.items():
                    if key not in ['type', 'category', 'device', 'timestamp']:
                        symptom_counts[key] += 1
        
        # Return most common symptoms
        common_symptoms = [symptom for symptom, count in symptom_counts.most_common(5)]
        return common_symptoms
    
    def _generate_fix_commands(self, fix_type: str, category: str) -> List[str]:
        """Generate template commands for a fix type."""
        # This is a simplified version - in practice, would learn from history
        command_templates = {
            'no_shutdown': [
                'interface {interface}',
                'no shutdown',
                'end'
            ],
            'configure_ip': [
                'interface {interface}',
                'ip address {expected_ip} {expected_mask}',
                'end'
            ],
            'configure_timers': [
                'interface {interface}',
                'ip hello-interval {protocol} {as_number} {expected_hello}',
                'ip hold-time {protocol} {as_number} {expected_hold}',
                'end'
            ] if category == 'eigrp' else [
                'interface {interface}',
                'ip ospf hello-interval {expected_hello}',
                'ip ospf dead-interval {expected_dead}',
                'end'
            ],
            'remove_passive': [
                'router {protocol} {as_or_process}',
                'no passive-interface {interface}',
                'end'
            ],
            'configure_k_values': [
                'router eigrp {as_number}',
                'metric weights {expected}',
                'end'
            ],
            'configure_router_id': [
                'router ospf {process_id}',
                'router-id {expected}',
                'end'
            ]
        }
        
        return command_templates.get(fix_type, ['# Auto-generated fix'])
    
    def _get_verification_command(self, category: str) -> str:
        """Get verification command for a category."""
        verification_commands = {
            'interface': 'show ip interface brief',
            'eigrp': 'show ip eigrp neighbors',
            'ospf': 'show ip ospf neighbor',
            'general': 'show ip protocols'
        }
        return verification_commands.get(category, 'show running-config')
    
    def _is_topology_dependent(self, fix_type: str, category: str) -> bool:
        """Determine if a fix type is topology-dependent."""
        topology_independent = ['no_shutdown']
        topology_dependent = [
            'configure_ip', 'configure_timers', 'configure_k_values',
            'configure_router_id', 'add_network', 'configure_area'
        ]
        
        if fix_type in topology_independent:
            return False
        elif fix_type in topology_dependent:
            return True
        else:
            # Default: protocol fixes are usually topology-dependent
            return category in ['eigrp', 'ospf']
    
    def _mine_temporal_patterns(self) -> List[Dict]:
        """
        Mine temporal patterns (problem sequences and cascading failures).
        
        Returns:
            List of temporal pattern rules
        """
        if len(self.kb.problem_history) < 2:
            return []
        
        # Sort history by timestamp
        sorted_history = sorted(
            self.kb.problem_history,
            key=lambda x: x.get('timestamp', '')
        )
        
        # Find problem sequences (problems that occur close together)
        sequences = defaultdict(list)
        time_window = timedelta(minutes=30)  # 30-minute window
        
        for i in range(len(sorted_history) - 1):
            entry1 = sorted_history[i]
            entry2 = sorted_history[i + 1]
            
            try:
                time1 = datetime.fromisoformat(entry1.get('timestamp', ''))
                time2 = datetime.fromisoformat(entry2.get('timestamp', ''))
                
                if time2 - time1 <= time_window:
                    problem1_type = entry1.get('problem', {}).get('type', '')
                    problem2_type = entry2.get('problem', {}).get('type', '')
                    
                    if problem1_type and problem2_type:
                        sequence_key = (problem1_type, problem2_type)
                        sequences[sequence_key].append((entry1, entry2))
            except (ValueError, TypeError):
                continue
        
        # Generate rules for frequent sequences
        temporal_rules = []
        for sequence_key, occurrences in sequences.items():
            if len(occurrences) >= self.MIN_OCCURRENCES:
                problem1_type, problem2_type = sequence_key
                
                rule = {
                    'id': f"TEMPORAL_{len(temporal_rules) + 1:03d}",
                    'condition': {
                        'problem_type': problem1_type,
                        'category': 'temporal',
                        'symptoms': ['leads_to', problem2_type]
                    },
                    'action': {
                        'fix_type': 'investigate_cascade',
                        'commands': [
                            f"# Check for cascading failure: {problem1_type} -> {problem2_type}",
                            f"# Fix {problem1_type} first to prevent {problem2_type}"
                        ],
                        'description': f"Temporal pattern: {problem1_type} often leads to {problem2_type}",
                        'verification': 'Monitor for secondary issues'
                    },
                    'confidence': min(0.7, len(occurrences) / len(self.kb.problem_history)),
                    'category': 'temporal',
                    'topology_dependent': False,
                    'mined': True,
                    'temporal_pattern': True,
                    'occurrences': len(occurrences),
                    'created': datetime.now().isoformat()
                }
                temporal_rules.append(rule)
        
        return temporal_rules
    
    def _extract_context_rules(self, min_support: float) -> List[Dict]:
        """
        Extract context-specific rules (device-specific, protocol-specific, etc.).
        
        Args:
            min_support: Minimum support threshold
        
        Returns:
            List of context-specific rules
        """
        context_rules = []
        
        # Group by device
        device_patterns = defaultdict(lambda: defaultdict(int))
        
        for entry in self.kb.problem_history:
            if not entry.get('success', False):
                continue
            
            problem = entry.get('problem', {})
            solution = entry.get('solution', {})
            device = problem.get('device', 'unknown')
            problem_type = problem.get('type', 'unknown')
            fix_type = solution.get('fix_type', 'unknown')
            
            pattern_key = (problem_type, fix_type)
            device_patterns[device][pattern_key] += 1
        
        # Find device-specific patterns
        for device, patterns in device_patterns.items():
            total_for_device = sum(patterns.values())
            
            for pattern_key, count in patterns.items():
                support = count / total_for_device if total_for_device > 0 else 0
                
                if support >= min_support and count >= self.MIN_OCCURRENCES:
                    problem_type, fix_type = pattern_key
                    
                    rule = {
                        'id': f"CONTEXT_{device}_{len(context_rules) + 1:03d}",
                        'condition': {
                            'problem_type': problem_type,
                            'category': 'context',
                            'symptoms': ['device', device]
                        },
                        'action': {
                            'fix_type': fix_type,
                            'commands': self._generate_fix_commands(fix_type, 'general'),
                            'description': f"Device-specific: {fix_type} for {problem_type} on {device}",
                            'verification': 'show running-config'
                        },
                        'confidence': support,
                        'category': 'context',
                        'topology_dependent': True,
                        'mined': True,
                        'context_specific': True,
                        'device': device,
                        'occurrences': count,
                        'created': datetime.now().isoformat()
                    }
                    context_rules.append(rule)
        
        return context_rules
    
    def _deduplicate_rules(self, rules: List[Dict]) -> List[Dict]:
        """
        Remove duplicate rules based on condition and action similarity.
        
        Args:
            rules: List of rules to deduplicate
        
        Returns:
            List of unique rules
        """
        unique_rules = []
        seen_signatures = set()
        
        for rule in rules:
            # Create signature from condition and action
            condition = rule.get('condition', {})
            action = rule.get('action', {})
            
            signature = (
                condition.get('problem_type', ''),
                condition.get('category', ''),
                action.get('fix_type', '')
            )
            
            if signature not in seen_signatures:
                seen_signatures.add(signature)
                unique_rules.append(rule)
            else:
                # If duplicate, keep the one with higher confidence
                for i, existing_rule in enumerate(unique_rules):
                    existing_condition = existing_rule.get('condition', {})
                    existing_action = existing_rule.get('action', {})
                    
                    existing_signature = (
                        existing_condition.get('problem_type', ''),
                        existing_condition.get('category', ''),
                        existing_action.get('fix_type', '')
                    )
                    
                    if existing_signature == signature:
                        if rule.get('confidence', 0) > existing_rule.get('confidence', 0):
                            unique_rules[i] = rule
                        break
        
        return unique_rules
    
    def validate_mined_rule(self, rule: Dict) -> Tuple[bool, str]:
        """
        Validate a mined rule before adding to knowledge base.
        
        Args:
            rule: Rule to validate
        
        Returns:
            Tuple of (is_valid, reason)
        """
        # Check required fields
        required_fields = ['id', 'condition', 'action', 'confidence', 'category']
        for field in required_fields:
            if field not in rule:
                return False, f"Missing required field: {field}"
        
        # Check confidence range
        confidence = rule.get('confidence', 0)
        if not (0 <= confidence <= 1):
            return False, f"Invalid confidence: {confidence}"
        
        # Check if rule already exists
        for existing_rule in self.kb.rules.values():
            if self._rules_are_similar(rule, existing_rule):
                return False, "Similar rule already exists"
        
        # Check minimum confidence threshold
        if confidence < self.MIN_CONFIDENCE:
            return False, f"Confidence {confidence} below threshold {self.MIN_CONFIDENCE}"
        
        return True, "Valid"
    
    def _rules_are_similar(self, rule1: Dict, rule2: Dict, threshold: float = 0.9) -> bool:
        """Check if two rules are similar."""
        # Compare conditions
        cond1 = rule1.get('condition', {})
        cond2 = rule2.get('condition', {})
        
        if (cond1.get('problem_type') == cond2.get('problem_type') and
            cond1.get('category') == cond2.get('category')):
            
            # Compare actions
            action1 = rule1.get('action', {})
            action2 = rule2.get('action', {})
            
            if action1.get('fix_type') == action2.get('fix_type'):
                return True
        
        return False
    
    def add_mined_rules_to_kb(self, rules: Optional[List[Dict]] = None,
                             validate: bool = True) -> Tuple[int, int]:
        """
        Add mined rules to the knowledge base.
        
        Args:
            rules: List of rules to add (default: use self.mined_rules)
            validate: Whether to validate rules before adding
        
        Returns:
            Tuple of (added_count, rejected_count)
        """
        if rules is None:
            rules = self.mined_rules
        
        added = 0
        rejected = 0
        
        for rule in rules:
            if validate:
                is_valid, reason = self.validate_mined_rule(rule)
                if not is_valid:
                    print(f"[RuleMiner] Rejected rule {rule.get('id')}: {reason}")
                    rejected += 1
                    continue
            
            # Add to knowledge base
            rule_id = rule['id']
            self.kb.rules[rule_id] = rule
            added += 1
            print(f"[RuleMiner] Added rule {rule_id}: {rule['action']['description']}")
        
        if added > 0:
            self.kb._save_knowledge()
            print(f"[RuleMiner] Successfully added {added} rules to knowledge base")
        
        return added, rejected
    
    def get_mining_statistics(self) -> Dict:
        """
        Get statistics about the mining process.
        
        Returns:
            Dictionary with mining statistics
        """
        if not self.mined_rules:
            return {
                'total_mined': 0,
                'by_category': {},
                'avg_confidence': 0,
                'temporal_patterns': 0,
                'context_specific': 0
            }
        
        by_category = defaultdict(int)
        confidences = []
        temporal_count = 0
        context_count = 0
        
        for rule in self.mined_rules:
            category = rule.get('category', 'unknown')
            by_category[category] += 1
            confidences.append(rule.get('confidence', 0))
            
            if rule.get('temporal_pattern', False):
                temporal_count += 1
            if rule.get('context_specific', False):
                context_count += 1
        
        return {
            'total_mined': len(self.mined_rules),
            'by_category': dict(by_category),
            'avg_confidence': sum(confidences) / len(confidences) if confidences else 0,
            'min_confidence': min(confidences) if confidences else 0,
            'max_confidence': max(confidences) if confidences else 0,
            'temporal_patterns': temporal_count,
            'context_specific': context_count
        }


# Convenience function for quick mining
def mine_and_add_rules(knowledge_base, min_support: float = 0.3,
                       min_confidence: float = 0.6) -> Dict:
    """
    Mine rules from history and add them to knowledge base.
    
    Args:
        knowledge_base: KnowledgeBase instance
        min_support: Minimum support threshold
        min_confidence: Minimum confidence threshold
    
    Returns:
        Dictionary with mining results
    """
    miner = RuleMiner(knowledge_base)
    
    # Mine rules
    mined_rules = miner.mine_rules_from_history(min_support, min_confidence)
    
    # Add to KB
    added, rejected = miner.add_mined_rules_to_kb(validate=True)
    
    # Get statistics
    stats = miner.get_mining_statistics()
    
    return {
        'mined': len(mined_rules),
        'added': added,
        'rejected': rejected,
        'statistics': stats
    }
