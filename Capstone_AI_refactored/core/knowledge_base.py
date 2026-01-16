#!/usr/bin/env python3
"""knowledge_base.py - Centralized knowledge repository for network troubleshooting"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional


class KnowledgeBase:
    """
    Stores and manages troubleshooting knowledge including:
    - Problem patterns
    - Solution rules
    - Historical fixes
    - Configuration baselines

    Implements three-tier decision making:
    Tier 1: High-confidence, topology-independent rules (0.9+)
    Tier 2: Baseline-informed rules with topology validation (0.7-0.9)
    Tier 3: Revert to baseline for complex topology-dependent issues
    """

    def __init__(self, db_path=None, config_dir=None, config_manager=None):
        self.knowledge_dir = Path.home() / "Capstone_AI" / "history" / "knowledge"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = self._get_next_kb_filename()

        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            possible_dirs = [
                Path.home() / "history" / "configs",
                Path.home() / "Capstone_AI" / "history" / "configs",
                Path.home() / "AI_troubleshoot" / "history" / "configs",
                Path.home() / "Capstone_AI_refactored" / "history" / "configs"
            ]

            self.config_dir = None
            for dir_path in possible_dirs:
                if dir_path.exists() and list(dir_path.glob("config_stable*.txt")):
                    self.config_dir = dir_path
                    break

            if not self.config_dir:
                self.config_dir = possible_dirs[0]

        # ConfigManager integration for three-tier decision making
        self.config_manager = config_manager

        # In-memory storage
        self.rules = {}  # rule_id -> rule_dict
        self.problem_history = []  # List of problem-solution pairs
        self.rule_stats = defaultdict(lambda: {'attempts': 0, 'successes': 0})
        
        # Protocol defaults
        self.protocol_defaults = {
            'eigrp': {
                'hello_timer': 5,
                'hold_timer': 15,
                'k_values': '0 1 0 1 0 0',
                'as_number': '1'
            },
            'ospf': {
                'hello_timer': 10,
                'dead_timer': 40,
                'process_id': '10',
                'router_ids': {
                    'R4': '4.4.4.4',
                    'R5': '5.5.5.5',
                    'R6': '6.6.6.6'
                }
            }
        }
        
        # Load existing knowledge or initialize
        if self.db_path.exists():
            self._load_knowledge()
        else:
            self._initialize_basic_rules()
    
    def _get_next_kb_filename(self):
        existing_files = list(self.knowledge_dir.glob("knowledge_base*.json"))
        
        if not existing_files:
            return self.knowledge_dir / "knowledge_base.json"
        
        max_num = 0
        for file in existing_files:
            match = re.match(r'knowledge_base(\d*)\.json', file.name)
            if match:
                num_str = match.group(1)
                current_num = 0 if num_str == '' else int(num_str)
                max_num = max(max_num, current_num)
        
        next_num = max_num + 10
        return self.knowledge_dir / f"knowledge_base{next_num}.json"
    
    def _initialize_basic_rules(self):
        """Initialize knowledge base with basic troubleshooting rules from detection trees"""

        # Rule 1: Interface Shutdown (topology-independent)
        self.add_rule(
            rule_id='INT_001',
            condition={
                'problem_type': 'shutdown',
                'category': 'interface',
                'symptoms': ['administratively down', 'should_be_up']
            },
            action={
                'fix_type': 'no_shutdown',
                'commands': ['interface {interface}', 'no shutdown', 'end'],
                'verification': 'show ip interface brief',
                'description': 'Bring interface up with no shutdown'
            },
            confidence=0.95,
            category='interface',
            topology_dependent=False  # Always safe
        )

        # Rule 2: IP Address Mismatch (topology-dependent)
        self.add_rule(
            rule_id='INT_002',
            condition={
                'problem_type': 'ip address mismatch',
                'category': 'interface',
                'symptoms': ['current_ip', 'expected_ip']
            },
            action={
                'fix_type': 'configure_ip',
                'commands': ['interface {interface}', 'ip address {expected_ip} {expected_mask}', 'end'],
                'verification': 'show ip interface brief',
                'description': 'Configure correct IP address'
            },
            confidence=0.90,
            category='interface',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 3: Missing IP Address (topology-dependent)
        self.add_rule(
            rule_id='INT_003',
            condition={
                'problem_type': 'missing ip address',
                'category': 'interface',
                'symptoms': ['expected_ip', 'expected_mask']
            },
            action={
                'fix_type': 'configure_ip',
                'commands': ['interface {interface}', 'ip address {expected_ip} {expected_mask}', 'end'],
                'verification': 'show ip interface brief',
                'description': 'Add missing IP address configuration'
            },
            confidence=0.90,
            category='interface',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 4: EIGRP AS Mismatch (always revert)
        self.add_rule(
            rule_id='EIGRP_001',
            condition={
                'problem_type': 'as mismatch',
                'category': 'eigrp',
                'symptoms': ['current', 'expected']
            },
            action={
                'fix_type': 'revert_to_baseline',
                'commands': ['# Revert to stable configuration'],
                'verification': 'show ip eigrp neighbors',
                'description': 'AS mismatch requires reverting to baseline configuration',
                'requires_manual': True
            },
            confidence=0.95,
            category='eigrp',
            topology_dependent=True
        )

        # Rule 5: EIGRP K-Values Mismatch (topology-dependent)
        self.add_rule(
            rule_id='EIGRP_002',
            condition={
                'problem_type': 'k-value mismatch',
                'category': 'eigrp',
                'symptoms': ['values', 'expected']
            },
            action={
                'fix_type': 'configure_k_values',
                'commands': ['router eigrp {as_number}', 'metric weights {expected}', 'end'],
                'verification': 'show ip eigrp topology',
                'description': 'Reset EIGRP metric weights to default'
            },
            confidence=0.85,
            category='eigrp',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 6: EIGRP Hello Timer Mismatch (topology-dependent)
        self.add_rule(
            rule_id='EIGRP_003',
            condition={
                'problem_type': 'eigrp hello timer mismatch',
                'category': 'eigrp',
                'symptoms': ['interface', 'current', 'expected']
            },
            action={
                'fix_type': 'configure_timers',
                'commands': [
                    'interface {interface}',
                    'ip hello-interval eigrp {as_number} {expected_hello}',
                    'ip hold-time eigrp {as_number} {expected_hold}',
                    'end'
                ],
                'verification': 'show ip eigrp interfaces detail {interface}',
                'description': 'Adjust EIGRP timers to match baseline'
            },
            confidence=0.85,
            category='eigrp',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 7: EIGRP Stub Configuration (topology-dependent)
        self.add_rule(
            rule_id='EIGRP_004',
            condition={
                'problem_type': 'stub configuration',
                'category': 'eigrp',
                'symptoms': ['should_be_stub']
            },
            action={
                'fix_type': 'remove_stub',
                'commands': ['router eigrp {as_number}', 'no eigrp stub', 'end'],
                'verification': 'show ip protocols',
                'description': 'Remove incorrect stub configuration'
            },
            confidence=0.80,
            category='eigrp',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 8: EIGRP Passive Interface (topology-dependent)
        self.add_rule(
            rule_id='EIGRP_005',
            condition={
                'problem_type': 'passive interface',
                'category': 'eigrp',
                'symptoms': ['interface', 'should_be_passive']
            },
            action={
                'fix_type': 'remove_passive',
                'commands': ['router eigrp {as_number}', 'no passive-interface {interface}', 'end'],
                'verification': 'show ip eigrp neighbors',
                'description': 'Remove passive interface configuration'
            },
            confidence=0.85,
            category='eigrp',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 9: EIGRP Missing Network (topology-dependent)
        self.add_rule(
            rule_id='EIGRP_006',
            condition={
                'problem_type': 'missing network',
                'category': 'eigrp',
                'symptoms': ['network']
            },
            action={
                'fix_type': 'add_network',
                'commands': ['router eigrp {as_number}', 'network {network}', 'end'],
                'verification': 'show ip eigrp topology',
                'description': 'Add missing network statement'
            },
            confidence=0.80,
            category='eigrp',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 10: OSPF Process ID Mismatch (always revert)
        self.add_rule(
            rule_id='OSPF_001',
            condition={
                'problem_type': 'process id mismatch',
                'category': 'ospf',
                'symptoms': ['current', 'expected']
            },
            action={
                'fix_type': 'revert_to_baseline',
                'commands': ['# Revert to stable configuration'],
                'verification': 'show ip ospf',
                'description': 'Process ID mismatch requires reverting to baseline',
                'requires_manual': True
            },
            confidence=0.90,
            category='ospf',
            topology_dependent=True
        )

        # Rule 11: OSPF Hello Interval Mismatch (topology-dependent)
        self.add_rule(
            rule_id='OSPF_002',
            condition={
                'problem_type': 'hello interval mismatch',
                'category': 'ospf',
                'symptoms': ['interface', 'current', 'expected']
            },
            action={
                'fix_type': 'configure_timers',
                'commands': [
                    'interface {interface}',
                    'ip ospf hello-interval {expected_hello}',
                    'ip ospf dead-interval {expected_dead}',
                    'end'
                ],
                'verification': 'show ip ospf interface {interface}',
                'description': 'Adjust OSPF timers to match neighbors'
            },
            confidence=0.85,
            category='ospf',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 12: OSPF Router ID Mismatch (topology-dependent)
        self.add_rule(
            rule_id='OSPF_003',
            condition={
                'problem_type': 'router id mismatch',
                'category': 'ospf',
                'symptoms': ['current', 'expected']
            },
            action={
                'fix_type': 'configure_router_id',
                'commands': [
                    'router ospf {process_id}',
                    'router-id {expected}',
                    'end',
                    '# NOTE: May need to clear OSPF process'
                ],
                'verification': 'show ip ospf',
                'description': 'Configure correct OSPF router ID'
            },
            confidence=0.75,
            category='ospf',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 13: OSPF Duplicate Router ID (always revert)
        self.add_rule(
            rule_id='OSPF_004',
            condition={
                'problem_type': 'possible duplicate router id',
                'category': 'ospf',
                'symptoms': ['message']
            },
            action={
                'fix_type': 'revert_to_baseline',
                'commands': ['# Revert to stable configuration with unique router IDs'],
                'verification': 'show ip ospf neighbor',
                'description': 'Duplicate RID requires baseline restoration',
                'requires_manual': True
            },
            confidence=0.80,
            category='ospf',
            topology_dependent=True
        )

        # Rule 14: OSPF Passive Interface (topology-dependent)
        self.add_rule(
            rule_id='OSPF_005',
            condition={
                'problem_type': 'passive interface',
                'category': 'ospf',
                'symptoms': ['interface', 'should_be_passive']
            },
            action={
                'fix_type': 'remove_passive',
                'commands': ['router ospf {process_id}', 'no passive-interface {interface}', 'end'],
                'verification': 'show ip ospf neighbor',
                'description': 'Remove passive interface configuration'
            },
            confidence=0.85,
            category='ospf',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 15: OSPF Interface Not in OSPF (topology-dependent)
        self.add_rule(
            rule_id='OSPF_006',
            condition={
                'problem_type': 'interface not in ospf',
                'category': 'ospf',
                'symptoms': ['interface', 'expected_network', 'expected_area']
            },
            action={
                'fix_type': 'add_to_ospf',
                'commands': [
                    'router ospf {process_id}',
                    'network {expected_network} {expected_wildcard} area {expected_area}',
                    'end'
                ],
                'verification': 'show ip ospf interface brief',
                'description': 'Add interface to OSPF process'
            },
            confidence=0.80,
            category='ospf',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 16: OSPF Area Mismatch (topology-dependent)
        self.add_rule(
            rule_id='OSPF_007',
            condition={
                'problem_type': 'area mismatch',
                'category': 'ospf',
                'symptoms': ['interface', 'current_area', 'expected_area']
            },
            action={
                'fix_type': 'configure_area',
                'commands': [
                    'interface {interface}',
                    'ip ospf {process_id} area {expected_area}',
                    'end'
                ],
                'verification': 'show ip ospf interface {interface}',
                'description': 'Configure correct OSPF area'
            },
            confidence=0.85,
            category='ospf',
            topology_dependent=True  # Needs baseline values
        )

        # Rule 17: Authentication Mismatch (Generic) (always revert)
        self.add_rule(
            rule_id='AUTH_001',
            condition={
                'problem_type': 'authentication mismatch',
                'category': 'general',
                'symptoms': []
            },
            action={
                'fix_type': 'revert_to_baseline',
                'commands': ['# Revert to stable configuration for authentication'],
                'verification': 'show ip protocols',
                'description': 'Authentication issues require baseline restoration',
                'requires_manual': True
            },
            confidence=0.70,
            category='general',
            topology_dependent=True
        )

        print(f"[KnowledgeBase] Initialized with {len(self.rules)} basic rules")
    
    def add_rule(self, rule_id, condition, action, confidence=1.0, category="general", topology_dependent=False):
        """
        Add a troubleshooting rule to knowledge base

        Args:
            rule_id: Unique identifier for the rule
            condition: Dict describing when rule applies
            action: Dict describing fix action
            confidence: Float 0-1 indicating rule confidence
            category: Category (interface, eigrp, ospf, general)
            topology_dependent: True if rule requires baseline/topology knowledge
                              (e.g., AS numbers, router IDs, network statements)
        """
        self.rules[rule_id] = {
            'id': rule_id,
            'condition': condition,
            'action': action,
            'confidence': confidence,
            'category': category,
            'topology_dependent': topology_dependent,  # NEW
            'created': datetime.now().isoformat()
        }
    
    def get_matching_rules(self, problem_dict, min_confidence=0.5):
        """
        Find rules that match a given problem
        
        Args:
            problem_dict: Dict describing the problem
            min_confidence: Minimum confidence threshold
        
        Returns:
            List of matching rules sorted by confidence
        """
        matching_rules = []
        
        problem_type = problem_dict.get('type', '').lower()
        problem_category = problem_dict.get('category', '').lower()
        
        for rule_id, rule in self.rules.items():
            # Skip if confidence too low
            if rule['confidence'] < min_confidence:
                continue
            
            # Check if problem type matches
            rule_problem_type = rule['condition'].get('problem_type', '').lower()
            if rule_problem_type and rule_problem_type != problem_type:
                continue
            
            # Check if category matches
            rule_category = rule['condition'].get('category', '').lower()
            if rule_category and rule_category != problem_category and rule_category != 'general':
                continue
            
            # Check if required symptoms are present
            required_symptoms = rule['condition'].get('symptoms', [])
            if required_symptoms:
                # Check if problem dict has the required fields
                has_all_symptoms = all(
                    symptom in problem_dict or symptom in str(problem_dict.values())
                    for symptom in required_symptoms
                )
                if not has_all_symptoms:
                    # Partial match - reduce confidence
                    rule = rule.copy()
                    rule['confidence'] *= 0.8
            
            # Calculate adjusted confidence based on historical success
            if rule_id in self.rule_stats:
                stats = self.rule_stats[rule_id]
                if stats['attempts'] > 0:
                    success_rate = stats['successes'] / stats['attempts']
                    adjusted_confidence = rule['confidence'] * (0.5 + 0.5 * success_rate)
                    rule = rule.copy()
                    rule['confidence'] = adjusted_confidence
                    rule['historical_success_rate'] = success_rate
            
            matching_rules.append(rule)
        
        # Sort by confidence (highest first)
        matching_rules.sort(key=lambda x: x['confidence'], reverse=True)
        
        return matching_rules

    def get_tiered_recommendations(self, problem_dict, baseline_context=None):
        """
        IMPROVED: Get recommendations with actual baseline validation

        Args:
            problem_dict: Problem description
            baseline_context: Optional baseline data (if None, will fetch)

        Returns:
            Dict with tier1, tier2, tier3 lists of recommendations
        """
        device_name = problem_dict.get('device', '')

        # Get baseline if not provided
        if baseline_context is None and self.config_manager and device_name:
            baseline_context = self.config_manager.get_device_baseline(device_name)

        tier1 = []  # High confidence, topology-independent, working
        tier2 = []  # Medium confidence, baseline-validated
        tier3 = []  # Low confidence or requires baseline revert

        # Get all matching rules
        all_rules = self.get_matching_rules(problem_dict, min_confidence=0.0)

        for rule in all_rules:
            base_confidence = rule['confidence']
            topology_dependent = rule.get('topology_dependent', False)

            # Check if this is a "revert to baseline" action
            is_revert_action = rule['action'].get('fix_type') == 'revert_to_baseline'

            if is_revert_action:
                # Always tier 3 for baseline reverts
                rule_copy = rule.copy()
                rule_copy['tier'] = 3
                rule_copy['baseline_validated'] = True
                tier3.append(rule_copy)
                continue

            # For topology-dependent rules, validate against baseline
            if topology_dependent and baseline_context:
                validated_rule = self._validate_and_format_rule(
                    rule, problem_dict, baseline_context
                )

                if validated_rule['baseline_validated']:
                    # Successfully validated - boost to tier 2
                    validated_rule['tier'] = 2
                    tier2.append(validated_rule)
                else:
                    # Couldn't validate - demote to tier 3
                    validated_rule['tier'] = 3
                    tier3.append(validated_rule)

            # For topology-dependent rules WITHOUT baseline
            elif topology_dependent and not baseline_context:
                # Can't validate - tier 3
                rule_copy = rule.copy()
                rule_copy['tier'] = 3
                rule_copy['baseline_validated'] = False
                rule_copy['confidence'] *= 0.5  # Reduce confidence
                tier3.append(rule_copy)

            # For topology-independent rules, use confidence tiers
            else:
                rule_copy = rule.copy()
                rule_copy['baseline_validated'] = False

                if base_confidence >= 0.85:
                    rule_copy['tier'] = 1
                    tier1.append(rule_copy)
                elif base_confidence >= 0.7:
                    rule_copy['tier'] = 2
                    tier2.append(rule_copy)
                else:
                    rule_copy['tier'] = 3
                    tier3.append(rule_copy)

        # If no rules in any tier, add baseline revert fallback
        if not tier1 and not tier2 and not tier3:
            baseline_revert = self.get_revert_to_baseline_solution(problem_dict)
            baseline_revert['tier'] = 3
            baseline_revert['baseline_validated'] = True
            tier3.append(baseline_revert)

        return {
            'tier1': tier1,
            'tier2': tier2,
            'tier3': tier3
        }

    def get_baseline_validated_fix(self, rule, problem_dict):
        """
        Validate a rule against baseline configuration

        Args:
            rule: Rule to validate
            problem_dict: Problem context

        Returns:
            Validated rule with updated confidence and validation status
        """
        validated_rule = rule.copy()
        device_name = problem_dict.get('device', '')
        interface = problem_dict.get('interface', '')

        if not self.config_manager or not device_name:
            # No config manager or device info, return rule as-is
            validated_rule['baseline_validated'] = False
            return validated_rule

        try:
            # Get baseline config for device
            baseline = self.config_manager.get_device_baseline(device_name)

            if not baseline:
                validated_rule['baseline_validated'] = False
                return validated_rule

            # Validate rule against baseline
            validation_result = self._validate_rule_against_baseline(rule, problem_dict, baseline)

            validated_rule['baseline_validated'] = validation_result['valid']
            if validation_result['valid']:
                # Boost confidence for validated rules
                validated_rule['confidence'] = min(0.95, validated_rule['confidence'] * 1.2)
            else:
                # Reduce confidence for invalid rules
                validated_rule['confidence'] *= 0.7

            return validated_rule

        except Exception as e:
            # If validation fails, return rule with reduced confidence
            validated_rule['baseline_validated'] = False
            validated_rule['confidence'] *= 0.8
            return validated_rule

    def _validate_and_format_rule(self, rule, problem_dict, baseline):
        """
        FIXED: Validate rule AND format commands with comprehensive placeholder handling

        Args:
            rule: Rule to validate
            problem_dict: Problem context
            baseline: Baseline configuration

        Returns:
            Rule with properly formatted commands and validation status
        """
        validated_rule = rule.copy()
        validated_rule['action'] = rule['action'].copy()

        problem_type = problem_dict.get('type', '').lower()
        device_name = problem_dict.get('device', '')
        interface = problem_dict.get('interface', '')

        # Track what we found in baseline
        baseline_values = {}
        is_valid = False

        # ===== INTERFACE VALIDATIONS =====
        if 'shutdown' in problem_type:
            if interface in baseline.get('interfaces', {}):
                should_be_up = self.config_manager.should_interface_be_up(device_name, interface)
                if should_be_up:
                    is_valid = True
                    baseline_values['interface'] = interface

        elif 'ip address' in problem_type or 'missing ip' in problem_type:
            if interface in baseline.get('interfaces', {}):
                intf_baseline = baseline['interfaces'][interface]
                expected_ip = intf_baseline.get('ip_address')
                expected_mask = intf_baseline.get('subnet_mask')

                if expected_ip and expected_mask:
                    is_valid = True
                    baseline_values.update({
                        'interface': interface,
                        'expected_ip': expected_ip,
                        'expected_mask': expected_mask
                    })

        # ===== EIGRP VALIDATIONS =====
        elif 'eigrp timer' in problem_type or 'eigrp hello' in problem_type:
            if interface in baseline.get('interfaces', {}):
                intf_baseline = baseline['interfaces'][interface]
                expected_hello = intf_baseline.get('eigrp_hello', 5)
                expected_hold = intf_baseline.get('eigrp_hold', 15)
                as_number = self.config_manager.get_eigrp_as_number(device_name)

                is_valid = True
                baseline_values.update({
                    'interface': interface,
                    'expected_hello': expected_hello,
                    'expected_hold': expected_hold,
                    'as_number': as_number
                })

        elif 'k-value' in problem_type or 'k value' in problem_type:
            expected_k = self.config_manager.get_expected_k_values(device_name)
            as_number = self.config_manager.get_eigrp_as_number(device_name)

            is_valid = True
            baseline_values.update({
                'expected': expected_k,
                'as_number': as_number
            })

        elif 'passive interface' in problem_type and 'eigrp' in problem_dict.get('category', ''):
            as_number = self.config_manager.get_eigrp_as_number(device_name)
            is_valid = True
            baseline_values.update({
                'interface': interface,
                'as_number': as_number
            })

        elif 'stub configuration' in problem_type:
            as_number = self.config_manager.get_eigrp_as_number(device_name)
            is_valid = True
            baseline_values.update({
                'as_number': as_number
            })

        elif 'missing network' in problem_type and 'eigrp' in problem_dict.get('category', ''):
            as_number = self.config_manager.get_eigrp_as_number(device_name)
            network = problem_dict.get('network', '')
            if network:
                is_valid = True
                baseline_values.update({
                    'as_number': as_number,
                    'network': network
                })

        # ===== OSPF VALIDATIONS =====
        elif 'ospf timer' in problem_type or 'hello interval' in problem_type or 'dead interval' in problem_type:
            if interface in baseline.get('interfaces', {}):
                intf_baseline = baseline['interfaces'][interface]
                expected_hello = intf_baseline.get('ospf_hello', 10)
                expected_dead = intf_baseline.get('ospf_dead', 40)
                process_id = self.config_manager.get_ospf_process_id(device_name)

                is_valid = True
                baseline_values.update({
                    'interface': interface,
                    'expected_hello': expected_hello,
                    'expected_dead': expected_dead,
                    'process_id': process_id
                })

        elif 'router id' in problem_type and 'ospf' in problem_dict.get('category', ''):
            ospf_baseline = baseline.get('ospf', {})
            expected_rid = ospf_baseline.get('router_id')
            process_id = self.config_manager.get_ospf_process_id(device_name)

            if expected_rid:
                is_valid = True
                baseline_values.update({
                    'expected': expected_rid,
                    'process_id': process_id
                })

        elif 'passive interface' in problem_type and 'ospf' in problem_dict.get('category', ''):
            process_id = self.config_manager.get_ospf_process_id(device_name)
            is_valid = True
            baseline_values.update({
                'interface': interface,
                'process_id': process_id
            })

        elif 'area mismatch' in problem_type:
            process_id = self.config_manager.get_ospf_process_id(device_name)
            expected_area = problem_dict.get('expected_area', '0')
            is_valid = True
            baseline_values.update({
                'interface': interface,
                'process_id': process_id,
                'expected_area': expected_area
            })

        # ===== COMPREHENSIVE PLACEHOLDER MAPPING =====
        # Build complete format_values with fallbacks
        format_values = {**problem_dict, **baseline_values}
        
        # Add protocol defaults as fallbacks for missing values
        if 'as_number' not in format_values:
            format_values['as_number'] = self.protocol_defaults['eigrp']['as_number']
        
        if 'process_id' not in format_values:
            format_values['process_id'] = self.protocol_defaults['ospf']['process_id']
        
        # Add common placeholders with safe defaults
        if 'expected_hello' not in format_values:
            if 'eigrp' in problem_dict.get('category', ''):
                format_values['expected_hello'] = self.protocol_defaults['eigrp']['hello_timer']
            elif 'ospf' in problem_dict.get('category', ''):
                format_values['expected_hello'] = self.protocol_defaults['ospf']['hello_timer']
        
        if 'expected_hold' not in format_values:
            format_values['expected_hold'] = self.protocol_defaults['eigrp']['hold_timer']
        
        if 'expected_dead' not in format_values:
            format_values['expected_dead'] = self.protocol_defaults['ospf']['dead_timer']
        
        if 'expected' not in format_values and 'k-value' in problem_type:
            format_values['expected'] = self.protocol_defaults['eigrp']['k_values']

        # ===== FORMAT COMMANDS WITH COMPREHENSIVE VALUES =====
        formatted_commands = []
        missing_placeholders = []
        
        for cmd in validated_rule['action'].get('commands', []):
            try:
                # Try to format the command
                formatted_cmd = cmd.format(**format_values)
                formatted_commands.append(formatted_cmd)
                
                # Check if any placeholders remain (indicates missing value)
                if '{' in formatted_cmd and '}' in formatted_cmd:
                    # Extract remaining placeholders
                    import re
                    remaining = re.findall(r'\{(\w+)\}', formatted_cmd)
                    if remaining:
                        missing_placeholders.extend(remaining)
                        print(f"[KB] Warning: Command still has placeholders: {formatted_cmd}")
                        print(f"[KB] Missing values for: {remaining}")
                
            except KeyError as e:
                # Missing placeholder - log it and keep original
                missing_key = str(e).strip("'")
                missing_placeholders.append(missing_key)
                formatted_commands.append(cmd)
                print(f"[KB] Warning: Missing placeholder '{missing_key}' in command: {cmd}")
        
        # Update the validated rule with formatted commands
        validated_rule['action']['commands'] = formatted_commands
        validated_rule['baseline_validated'] = is_valid and len(missing_placeholders) == 0
        validated_rule['baseline_values'] = baseline_values
        validated_rule['missing_placeholders'] = missing_placeholders
        
        # Log formatting results
        if missing_placeholders:
            print(f"[KB] Command formatting incomplete. Missing: {set(missing_placeholders)}")
            print(f"[KB] Available values: {list(format_values.keys())}")
            # Reduce confidence if placeholders are missing
            validated_rule['confidence'] *= 0.6
        elif is_valid:
            # Boost confidence for fully validated and formatted rules
            validated_rule['confidence'] = min(0.95, validated_rule['confidence'] * 1.15)
            print(f"[KB] Successfully formatted commands with baseline values")
        else:
            # Reduce confidence if validation failed
            validated_rule['confidence'] *= 0.7

        return validated_rule

    def _validate_rule_against_baseline(self, rule, problem_dict, baseline):
        """
        Validate a specific rule against baseline configuration

        Args:
            rule: Rule to validate
            problem_dict: Problem context
            baseline: Baseline configuration

        Returns:
            Dict with 'valid' boolean and optional validation details
        """
        rule_type = rule.get('condition', {}).get('problem_type', '')
        device_name = problem_dict.get('device', '')
        interface = problem_dict.get('interface', '')

        # Interface-related validations
        if 'shutdown' in rule_type:
            if interface and interface in baseline.get('interfaces', {}):
                baseline_intf = baseline['interfaces'][interface]
                # Check if interface should be up according to baseline
                should_be_up = self.config_manager.should_interface_be_up(device_name, interface)
                if should_be_up:
                    return {'valid': True, 'reason': 'Interface should be up per baseline'}
                else:
                    return {'valid': False, 'reason': 'Interface should be down per baseline'}

        elif 'ip address' in rule_type:
            if interface and interface in baseline.get('interfaces', {}):
                baseline_intf = baseline['interfaces'][interface]
                expected_ip = baseline_intf.get('ip_address')
                expected_mask = baseline_intf.get('subnet_mask')
                if expected_ip and expected_mask:
                    return {'valid': True, 'expected_ip': expected_ip, 'expected_mask': expected_mask}

        # EIGRP validations
        elif 'as mismatch' in rule_type:
            expected_as = self.config_manager.get_eigrp_as_number(device_name)
            if expected_as and expected_as != '1':  # 1 is default, might indicate no config
                return {'valid': True, 'expected_as': expected_as}

        elif 'k-value mismatch' in rule_type:
            expected_k = self.config_manager.get_expected_k_values(device_name)
            if expected_k:
                return {'valid': True, 'expected_k': expected_k}

        # OSPF validations
        elif 'process id mismatch' in rule_type:
            expected_pid = self.config_manager.get_ospf_process_id(device_name)
            if expected_pid and expected_pid != '10':  # 10 is default
                return {'valid': True, 'expected_pid': expected_pid}

        elif 'router id mismatch' in rule_type:
            ospf_config = baseline.get('ospf', {})
            expected_rid = ospf_config.get('router_id')
            if expected_rid:
                return {'valid': True, 'expected_rid': expected_rid}

        # Default: assume valid if we can't validate
        return {'valid': True, 'reason': 'Cannot validate against baseline'}

    def add_problem_solution_pair(self, problem, solution, success=True):
        """
        Record a problem and its solution for learning
        
        Args:
            problem: Dict describing the problem
            solution: Dict describing the solution that was applied
            success: Bool indicating if solution worked
        """
        pair = {
            'timestamp': datetime.now().isoformat(),
            'problem': problem,
            'solution': solution,
            'success': success,
            'device': problem.get('device', 'unknown'),
            'category': problem.get('category', 'unknown'),
            'problem_type': problem.get('type', 'unknown')
        }
        
        self.problem_history.append(pair)
        
        # Update rule statistics if rule_id is provided
        rule_id = solution.get('rule_id')
        if rule_id:
            self.rule_stats[rule_id]['attempts'] += 1
            if success:
                self.rule_stats[rule_id]['successes'] += 1
        
        # Auto-save history periodically (every 10 entries)
        if len(self.problem_history) % 10 == 0:
            self._save_knowledge()
    
    def get_similar_problems(self, problem_dict, limit=5):
        """
        Find historically similar problems
        
        Args:
            problem_dict: Current problem description
            limit: Max number of similar problems to return
        
        Returns:
            List of similar historical problems with their solutions
        """
        problem_type = problem_dict.get('type', '')
        problem_category = problem_dict.get('category', '')
        device = problem_dict.get('device', '')
        
        # Score each historical problem for similarity
        scored_problems = []
        
        for entry in self.problem_history:
            score = 0
            
            # Exact problem type match
            if entry['problem_type'] == problem_type:
                score += 50
            
            # Category match
            if entry['category'] == problem_category:
                score += 30
            
            # Same device
            if entry['device'] == device:
                score += 10
            
            # Bonus for successful solutions
            if entry['success']:
                score += 20
            
            # Check for matching symptoms/fields
            for key, value in problem_dict.items():
                if key in entry['problem'] and entry['problem'][key] == value:
                    score += 5
            
            if score > 0:
                scored_problems.append((score, entry))
        
        # Sort by score and return top N
        scored_problems.sort(key=lambda x: x[0], reverse=True)
        return [entry for score, entry in scored_problems[:limit]]
    
    def update_rule_confidence(self, rule_id, success):
        """
        Update rule confidence based on success/failure using Bayesian update
        
        Args:
            rule_id: Rule identifier
            success: Bool indicating if rule worked
        """
        if rule_id not in self.rules:
            return
        
        # Simple Bayesian update
        current_confidence = self.rules[rule_id]['confidence']
        
        if success:
            # Increase confidence (but not beyond 0.99)
            new_confidence = min(0.99, current_confidence + (1 - current_confidence) * 0.1)
        else:
            # Decrease confidence (but not below 0.1)
            new_confidence = max(0.1, current_confidence * 0.8)
        
        self.rules[rule_id]['confidence'] = new_confidence
        self.rules[rule_id]['last_updated'] = datetime.now().isoformat()
        
        # Save updated confidence
        self._save_knowledge()
    
    def get_protocol_defaults(self, protocol, parameter):
        """
        Get default values for protocol parameters
        
        Args:
            protocol: 'eigrp', 'ospf', etc.
            parameter: 'hello_timer', 'hold_timer', etc.
        
        Returns:
            Default value or None
        """
        return self.protocol_defaults.get(protocol, {}).get(parameter)
    
    def get_latest_stable_config_path(self):
        """Find the latest stable configuration file"""
        if not self.config_dir.exists():
            return None
        
        config_files = list(self.config_dir.glob("config_stable*.txt"))
        if not config_files:
            return None
        
        def extract_number(path):
            match = re.search(r'config_stable(\d+)\.txt', path.name)
            return int(match.group(1)) if match else 0
        
        config_files.sort(key=extract_number, reverse=True)
        return config_files[0]
    
    def get_revert_to_baseline_solution(self, problem_dict):
        """
        Generate a solution to revert to baseline configuration
        Args:
            problem_dict: Problem description
        Returns:
            Solution dict with revert instructions
        """
        latest_config = self.get_latest_stable_config_path()
        
        return {
            'fix_type': 'revert_to_baseline',
            'description': 'Revert device to last known stable configuration',
            'config_file': str(latest_config) if latest_config else 'No stable config found',
            'commands': [
                '# Manual process:',
                '# 1. Review stable configuration file',
                '# 2. Apply relevant sections',
                '# 3. Verify functionality'
            ],
            'requires_manual': True,
            'verification': 'show running-config'
        }
    
    def export_knowledge(self, filepath=None):
        if filepath:
            filepath = Path(filepath)
        else:
            filepath = self._get_next_kb_filename()
        
        export_data = {
            'rules': self.rules,
            'problem_history': self.problem_history,
            'rule_stats': dict(self.rule_stats),
            'protocol_defaults': self.protocol_defaults,
            'exported': datetime.now().isoformat()
        }
        
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"[KnowledgeBase] Exported to {filepath}")
        return filepath
    
    def import_knowledge(self, filepath):
        """
        Import knowledge from file
        
        Args:
            filepath: Path to import file
        """
        filepath = Path(filepath)
        if not filepath.exists():
            print(f"[KnowledgeBase] Import file not found: {filepath}")
            return
        
        with open(filepath, 'r') as f:
            import_data = json.load(f)
        
        # Merge rules (keep existing if conflict)
        for rule_id, rule in import_data.get('rules', {}).items():
            if rule_id not in self.rules:
                self.rules[rule_id] = rule
        
        # Append problem history
        self.problem_history.extend(import_data.get('problem_history', []))
        
        # Merge statistics
        for rule_id, stats in import_data.get('rule_stats', {}).items():
            if rule_id in self.rule_stats:
                self.rule_stats[rule_id]['attempts'] += stats['attempts']
                self.rule_stats[rule_id]['successes'] += stats['successes']
            else:
                self.rule_stats[rule_id] = stats
        
        print(f"[KnowledgeBase] Imported from {filepath}")
        print(f"  - Rules: {len(self.rules)}")
        print(f"  - History entries: {len(self.problem_history)}")
    
    def _save_knowledge(self):
        saved_path = self.export_knowledge()
        self.db_path = saved_path
    
    def _load_knowledge(self):
        if not self.db_path.exists():
            existing_files = list(self.knowledge_dir.glob("knowledge_base*.json"))
            if existing_files:
                def extract_number(path):
                    match = re.search(r'knowledge_base(\d+)\.json', path.name)
                    return int(match.group(1)) if match else 0
                
                existing_files.sort(key=extract_number, reverse=True)
                self.db_path = existing_files[0]
            else:
                return
        
        self.import_knowledge(self.db_path)
    
    def get_statistics(self):
        """
        Get knowledge base statistics
        
        Returns:
            Dict with stats like rule count, problem count, success rate
        """
        total_attempts = sum(stats['attempts'] for stats in self.rule_stats.values())
        total_successes = sum(stats['successes'] for stats in self.rule_stats.values())
        
        success_rate = (total_successes / total_attempts * 100) if total_attempts > 0 else 0
        
        # Category breakdown
        category_counts = defaultdict(int)
        for rule in self.rules.values():
            category_counts[rule['category']] += 1
        
        # Recent problems
        recent_problems = len([p for p in self.problem_history 
                              if datetime.fromisoformat(p['timestamp']) > 
                              datetime.now().replace(hour=0, minute=0, second=0)])
        
        return {
            'total_rules': len(self.rules),
            'total_problems_logged': len(self.problem_history),
            'total_fix_attempts': total_attempts,
            'total_successes': total_successes,
            'overall_success_rate': round(success_rate, 2),
            'rules_by_category': dict(category_counts),
            'problems_today': recent_problems,
            'config_directory': str(self.config_dir),
            'config_dir_exists': self.config_dir.exists(),
            'latest_stable_config': str(self.get_latest_stable_config_path()) if self.get_latest_stable_config_path() else 'None',
            'most_successful_rules': self._get_top_rules(5)
        }
    
    def _get_top_rules(self, limit=5):
        """Get top performing rules by success rate"""
        rule_performance = []
        
        for rule_id, stats in self.rule_stats.items():
            if stats['attempts'] >= 3:  # Only consider rules with 3+ attempts
                success_rate = stats['successes'] / stats['attempts']
                rule_performance.append({
                    'rule_id': rule_id,
                    'success_rate': round(success_rate * 100, 2),
                    'attempts': stats['attempts']
                })
        
        rule_performance.sort(key=lambda x: x['success_rate'], reverse=True)
        return rule_performance[:limit]
    
    def print_statistics(self):
        """Print formatted statistics"""
        stats = self.get_statistics()
        
        print("\n" + "=" * 60)
        print("KNOWLEDGE BASE STATISTICS")
        print("=" * 60)
        print(f"Total Rules: {stats['total_rules']}")
        print(f"Problems Logged: {stats['total_problems_logged']}")
        print(f"Fix Attempts: {stats['total_fix_attempts']}")
        print(f"Overall Success Rate: {stats['overall_success_rate']}%")
        print(f"\nRules by Category:")
        for category, count in stats['rules_by_category'].items():
            print(f"  {category}: {count}")
        print(f"\nConfig Directory: {stats['config_directory']}")
        print(f"Config Dir Exists: {stats['config_dir_exists']}")
        print(f"Latest Stable Config: {stats['latest_stable_config']}")
        
        if stats['most_successful_rules']:
            print(f"\nTop Performing Rules:")
            for rule in stats['most_successful_rules']:
                print(f"  {rule['rule_id']}: {rule['success_rate']}% ({rule['attempts']} attempts)")
        print("=" * 60 + "\n")
    
    # ========================================================================
    # RULE REFINEMENT ENGINE
    # ========================================================================
    
    def refine_rules(self, min_precision: float = 0.6, min_support: int = 5) -> Dict:
        """
        NEW: Automatically refine rules by splitting, merging, and pruning.
        
        Args:
            min_precision: Minimum precision (success rate) to keep a rule
            min_support: Minimum number of attempts before considering refinement
        
        Returns:
            Dictionary with refinement statistics
        """
        print(f"[RuleRefinement] Starting rule refinement process...")
        
        stats = {
            'rules_split': 0,
            'rules_merged': 0,
            'rules_pruned': 0,
            'rules_generalized': 0,
            'total_before': len(self.rules),
            'total_after': 0
        }
        
        # Step 1: Split broad rules
        split_count = self._split_broad_rules(min_support)
        stats['rules_split'] = split_count
        
        # Step 2: Merge redundant rules
        merge_count = self._merge_redundant_rules()
        stats['rules_merged'] = merge_count
        
        # Step 3: Generalize similar rules
        generalize_count = self._generalize_rules()
        stats['rules_generalized'] = generalize_count
        
        # Step 4: Prune low-performing rules
        prune_count = self._prune_low_performing_rules(min_precision, min_support)
        stats['rules_pruned'] = prune_count
        
        stats['total_after'] = len(self.rules)
        
        print(f"[RuleRefinement] Refinement complete:")
        print(f"  - Split: {split_count} rules")
        print(f"  - Merged: {merge_count} rules")
        print(f"  - Generalized: {generalize_count} rules")
        print(f"  - Pruned: {prune_count} rules")
        print(f"  - Total: {stats['total_before']} -> {stats['total_after']} rules")
        
        # Save refined knowledge base
        self._save_knowledge()
        
        return stats
    
    def _split_broad_rules(self, min_support: int) -> int:
        """Split overly broad rules into more specific variants."""
        split_count = 0
        new_rules = {}
        
        for rule_id, rule in list(self.rules.items()):
            # Check if rule is broad (few conditions, low precision)
            if self._is_broad_rule(rule, min_support):
                # Split by context
                variants = self._create_rule_variants(rule)
                
                if len(variants) > 1:
                    print(f"[RuleRefinement] Splitting broad rule {rule_id} into {len(variants)} variants")
                    
                    # Remove original broad rule
                    del self.rules[rule_id]
                    
                    # Add variants
                    for i, variant in enumerate(variants):
                        variant_id = f"{rule_id}_V{i+1}"
                        variant['id'] = variant_id
                        variant['parent_rule'] = rule_id
                        variant['split_from'] = rule_id
                        new_rules[variant_id] = variant
                    
                    split_count += 1
        
        # Add new rules
        self.rules.update(new_rules)
        
        return split_count
    
    def _is_broad_rule(self, rule: Dict, min_support: int) -> bool:
        """Check if a rule is overly broad."""
        rule_id = rule.get('id', '')
        
        # Check if rule has enough history
        if rule_id not in self.rule_stats:
            return False
        
        stats = self.rule_stats[rule_id]
        if stats['attempts'] < min_support:
            return False
        
        # Check precision
        precision = stats['successes'] / stats['attempts'] if stats['attempts'] > 0 else 0
        
        # Broad if: low precision AND few conditions
        condition = rule.get('condition', {})
        num_conditions = len(condition.get('symptoms', [])) + (1 if condition.get('problem_type') else 0)
        
        return precision < 0.7 and num_conditions < 2
    
    def _create_rule_variants(self, rule: Dict) -> List[Dict]:
        """Create specialized variants of a broad rule."""
        variants = []
        base_condition = rule.get('condition', {})
        
        # Find contexts where this rule was applied
        contexts = self._extract_rule_contexts(rule.get('id', ''))
        
        if not contexts:
            return [rule]  # Can't split without context
        
        # Create variant for each unique context
        for context in contexts:
            variant = {
                'id': rule.get('id', ''),
                'condition': dict(base_condition),
                'action': dict(rule.get('action', {})),
                'confidence': rule.get('confidence', 0.5),
                'category': rule.get('category', 'general'),
                'topology_dependent': rule.get('topology_dependent', False),
                'created': datetime.now().isoformat(),
                'refined': True
            }
            
            # Add context-specific conditions
            if context.get('device'):
                variant['condition']['device'] = context['device']
                variant['context_specific'] = True
            
            if context.get('interface_type'):
                variant['condition']['interface_type'] = context['interface_type']
            
            variants.append(variant)
        
        return variants if len(variants) > 1 else [rule]
    
    def _extract_rule_contexts(self, rule_id: str) -> List[Dict]:
        """Extract unique contexts where a rule was applied."""
        contexts = []
        seen_contexts = set()
        
        for entry in self.problem_history:
            solution = entry.get('solution', {})
            if solution.get('rule_id') == rule_id:
                problem = entry.get('problem', {})
                
                context = {
                    'device': problem.get('device', ''),
                    'interface_type': self._get_interface_type(problem.get('interface', ''))
                }
                
                context_key = f"{context['device']}_{context['interface_type']}"
                if context_key not in seen_contexts:
                    seen_contexts.add(context_key)
                    contexts.append(context)
        
        return contexts[:5]  # Limit to 5 variants
    
    def _get_interface_type(self, interface: str) -> str:
        """Extract interface type from interface name."""
        if not interface:
            return 'unknown'
        
        if interface.startswith('Fa') or interface.startswith('FastEthernet'):
            return 'FastEthernet'
        elif interface.startswith('Gi') or interface.startswith('GigabitEthernet'):
            return 'GigabitEthernet'
        elif interface.startswith('Se') or interface.startswith('Serial'):
            return 'Serial'
        else:
            return 'other'
    
    def _merge_redundant_rules(self) -> int:
        """Merge rules that are essentially the same."""
        merge_count = 0
        merged_ids = set()
        
        rule_list = list(self.rules.items())
        
        for i, (rule_id1, rule1) in enumerate(rule_list):
            if rule_id1 in merged_ids:
                continue
            
            for rule_id2, rule2 in rule_list[i+1:]:
                if rule_id2 in merged_ids:
                    continue
                
                # Check if rules are similar
                if self._rules_are_redundant(rule1, rule2):
                    print(f"[RuleRefinement] Merging redundant rules {rule_id1} and {rule_id2}")
                    
                    # Merge into rule1
                    merged_rule = self._merge_two_rules(rule1, rule2)
                    self.rules[rule_id1] = merged_rule
                    
                    # Remove rule2
                    del self.rules[rule_id2]
                    merged_ids.add(rule_id2)
                    
                    merge_count += 1
        
        return merge_count
    
    def _rules_are_redundant(self, rule1: Dict, rule2: Dict) -> bool:
        """Check if two rules are redundant (same conditions and actions)."""
        # Same problem type and category
        cond1 = rule1.get('condition', {})
        cond2 = rule2.get('condition', {})
        
        if (cond1.get('problem_type') != cond2.get('problem_type') or
            cond1.get('category') != cond2.get('category')):
            return False
        
        # Same fix type
        action1 = rule1.get('action', {})
        action2 = rule2.get('action', {})
        
        if action1.get('fix_type') != action2.get('fix_type'):
            return False
        
        # Similar confidence (within 10%)
        conf1 = rule1.get('confidence', 0)
        conf2 = rule2.get('confidence', 0)
        
        return abs(conf1 - conf2) < 0.1
    
    def _merge_two_rules(self, rule1: Dict, rule2: Dict) -> Dict:
        """Merge two rules into one with combined statistics."""
        merged = dict(rule1)
        
        # Combine confidences (weighted average)
        stats1 = self.rule_stats.get(rule1.get('id', ''), {'attempts': 1, 'successes': 1})
        stats2 = self.rule_stats.get(rule2.get('id', ''), {'attempts': 1, 'successes': 1})
        
        total_attempts = stats1['attempts'] + stats2['attempts']
        total_successes = stats1['successes'] + stats2['successes']
        
        merged['confidence'] = total_successes / total_attempts if total_attempts > 0 else 0.5
        merged['merged_from'] = [rule1.get('id', ''), rule2.get('id', '')]
        merged['last_updated'] = datetime.now().isoformat()
        
        # Update statistics
        self.rule_stats[rule1.get('id', '')]['attempts'] = total_attempts
        self.rule_stats[rule1.get('id', '')]['successes'] = total_successes
        
        return merged
    
    def _generalize_rules(self) -> int:
        """Find common patterns and create generalized parent rules."""
        generalize_count = 0
        
        # Group rules by category and fix type
        rule_groups = defaultdict(list)
        
        for rule_id, rule in self.rules.items():
            category = rule.get('category', 'general')
            fix_type = rule.get('action', {}).get('fix_type', 'unknown')
            key = f"{category}_{fix_type}"
            rule_groups[key].append((rule_id, rule))
        
        # For each group with multiple rules, try to generalize
        for group_key, rules in rule_groups.items():
            if len(rules) >= 3:  # Need at least 3 similar rules to generalize
                generalized = self._create_generalized_rule(rules)
                
                if generalized:
                    gen_id = f"GEN_{group_key}_{generalize_count+1}"
                    generalized['id'] = gen_id
                    self.rules[gen_id] = generalized
                    generalize_count += 1
                    
                    print(f"[RuleRefinement] Created generalized rule {gen_id} from {len(rules)} specific rules")
        
        return generalize_count
    
    def _create_generalized_rule(self, rules: List[Tuple[str, Dict]]) -> Optional[Dict]:
        """Create a generalized rule from multiple specific rules."""
        if not rules:
            return None
        
        # Use first rule as template
        _, first_rule = rules[0]
        generalized = dict(first_rule)
        
        # Remove context-specific conditions
        condition = generalized.get('condition', {})
        condition.pop('device', None)
        condition.pop('interface_type', None)
        condition.pop('interface', None)
        
        # Calculate average confidence
        confidences = [rule.get('confidence', 0.5) for _, rule in rules]
        generalized['confidence'] = sum(confidences) / len(confidences)
        
        # Mark as generalized
        generalized['generalized'] = True
        generalized['specialized_rules'] = [rule_id for rule_id, _ in rules]
        generalized['created'] = datetime.now().isoformat()
        
        return generalized
    
    def _prune_low_performing_rules(self, min_precision: float, min_support: int) -> int:
        """Remove rules with consistently poor performance."""
        prune_count = 0
        to_prune = []
        
        for rule_id, rule in self.rules.items():
            # Skip if not enough data
            if rule_id not in self.rule_stats:
                continue
            
            stats = self.rule_stats[rule_id]
            if stats['attempts'] < min_support:
                continue
            
            # Calculate precision
            precision = stats['successes'] / stats['attempts'] if stats['attempts'] > 0 else 0
            
            # Prune if precision is too low
            if precision < min_precision:
                print(f"[RuleRefinement] Pruning low-performing rule {rule_id} (precision: {precision:.2%})")
                to_prune.append(rule_id)
                prune_count += 1
        
        # Archive pruned rules instead of deleting
        for rule_id in to_prune:
            rule = self.rules[rule_id]
            rule['archived'] = True
            rule['archived_date'] = datetime.now().isoformat()
            rule['archived_reason'] = f"Low precision: {self.rule_stats[rule_id]['successes']}/{self.rule_stats[rule_id]['attempts']}"
            # Move to archived rules (could save separately)
            del self.rules[rule_id]
        
        return prune_count
    
    # ========================================================================
    # KNOWLEDGE BASE IMPROVEMENTS
    # ========================================================================
    
    def calculate_rule_quality_metrics(self, rule_id: str) -> Dict:
        """
        NEW: Calculate precision, recall, and F1 score for a rule.
        
        Args:
            rule_id: Rule identifier
        
        Returns:
            Dictionary with quality metrics
        """
        if rule_id not in self.rule_stats:
            return {
                'precision': 0.0,
                'recall': 0.0,
                'f1_score': 0.0,
                'support': 0,
                'message': 'No statistics available'
            }
        
        stats = self.rule_stats[rule_id]
        rule = self.rules.get(rule_id, {})
        
        # Precision: Of all times rule was applied, how many succeeded?
        precision = stats['successes'] / stats['attempts'] if stats['attempts'] > 0 else 0.0
        
        # Recall: Of all problems of this type, how many did this rule catch?
        problem_type = rule.get('condition', {}).get('problem_type', '')
        category = rule.get('category', '')
        
        total_problems_of_type = sum(
            1 for entry in self.problem_history
            if (entry.get('problem', {}).get('type') == problem_type and
                entry.get('problem', {}).get('category') == category)
        )
        
        recall = stats['attempts'] / total_problems_of_type if total_problems_of_type > 0 else 0.0
        
        # F1 Score: Harmonic mean of precision and recall
        f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        return {
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1_score': round(f1_score, 4),
            'support': stats['attempts'],
            'true_positives': stats['successes'],
            'false_positives': stats['attempts'] - stats['successes'],
            'total_problems_of_type': total_problems_of_type
        }
    
    def get_rule_version_history(self, rule_id: str) -> List[Dict]:
        """
        NEW: Track rule evolution over time.
        
        Args:
            rule_id: Rule identifier
        
        Returns:
            List of rule versions with timestamps
        """
        versions = []
        
        # Current version
        if rule_id in self.rules:
            current_rule = self.rules[rule_id]
            versions.append({
                'version': 'current',
                'timestamp': current_rule.get('last_updated', current_rule.get('created', '')),
                'confidence': current_rule.get('confidence', 0.0),
                'changes': 'Current active version'
            })
        
        # Check for parent/split/merged information
        rule = self.rules.get(rule_id, {})
        
        if rule.get('parent_rule'):
            versions.append({
                'version': 'parent',
                'rule_id': rule['parent_rule'],
                'timestamp': rule.get('created', ''),
                'changes': f"Split from {rule['parent_rule']}"
            })
        
        if rule.get('merged_from'):
            versions.append({
                'version': 'merged',
                'rule_ids': rule['merged_from'],
                'timestamp': rule.get('last_updated', ''),
                'changes': f"Merged from {len(rule['merged_from'])} rules"
            })
        
        if rule.get('split_from'):
            versions.append({
                'version': 'split',
                'rule_id': rule['split_from'],
                'timestamp': rule.get('created', ''),
                'changes': f"Split from {rule['split_from']}"
            })
        
        return versions
    
    def find_similar_cases(self, problem: Dict, top_k: int = 5) -> List[Dict]:
        """
        NEW: Case-based reasoning - retrieve similar past solutions.
        
        Args:
            problem: Current problem description
            top_k: Number of similar cases to return
        
        Returns:
            List of similar historical cases with solutions
        """
        similar_cases = []
        
        problem_type = problem.get('type', '')
        category = problem.get('category', '')
        device = problem.get('device', '')
        
        for entry in self.problem_history:
            hist_problem = entry.get('problem', {})
            
            # Calculate similarity score
            similarity = 0.0
            
            # Exact type match
            if hist_problem.get('type') == problem_type:
                similarity += 0.4
            
            # Category match
            if hist_problem.get('category') == category:
                similarity += 0.3
            
            # Device match
            if hist_problem.get('device') == device:
                similarity += 0.2
            
            # Success bonus
            if entry.get('success', False):
                similarity += 0.1
            
            if similarity > 0:
                similar_cases.append({
                    'similarity': similarity,
                    'problem': hist_problem,
                    'solution': entry.get('solution', {}),
                    'success': entry.get('success', False),
                    'timestamp': entry.get('timestamp', '')
                })
        
        # Sort by similarity and return top k
        similar_cases.sort(key=lambda x: x['similarity'], reverse=True)
        return similar_cases[:top_k]
    
    def build_rule_dependency_graph(self) -> Dict:
        """
        NEW: Build graph showing which rules trigger others.
        
        Returns:
            Dictionary representing rule dependency graph
        """
        graph = {
            'nodes': [],
            'edges': []
        }
        
        # Add all rules as nodes
        for rule_id, rule in self.rules.items():
            graph['nodes'].append({
                'id': rule_id,
                'category': rule.get('category', 'unknown'),
                'confidence': rule.get('confidence', 0.0),
                'problem_type': rule.get('condition', {}).get('problem_type', '')
            })
        
        # Find dependencies (rules that could trigger each other)
        for rule_id1, rule1 in self.rules.items():
            action1 = rule1.get('action', {})
            fix_type1 = action1.get('fix_type', '')
            
            for rule_id2, rule2 in self.rules.items():
                if rule_id1 == rule_id2:
                    continue
                
                condition2 = rule2.get('condition', {})
                problem_type2 = condition2.get('problem_type', '')
                
                # Check if fix from rule1 could trigger rule2
                if self._fix_triggers_problem(fix_type1, problem_type2):
                    graph['edges'].append({
                        'from': rule_id1,
                        'to': rule_id2,
                        'type': 'triggers',
                        'reason': f"{fix_type1} may cause {problem_type2}"
                    })
        
        return graph
    
    def _fix_triggers_problem(self, fix_type: str, problem_type: str) -> bool:
        """Check if a fix type could trigger a problem type."""
        # Known trigger relationships
        triggers = {
            'configure_ip': ['ip_mismatch', 'wrong_subnet'],
            'configure_timers': ['timer_mismatch'],
            'no_shutdown': ['interface_flap']
        }
        
        return problem_type in triggers.get(fix_type, [])
    
    def validate_knowledge_consistency(self) -> Dict:
        """
        NEW: Detect contradictory or outdated rules.
        
        Returns:
            Dictionary with validation results
        """
        issues = {
            'contradictions': [],
            'outdated_rules': [],
            'low_quality_rules': [],
            'orphaned_rules': []
        }
        
        # Check for contradictions
        for rule_id1, rule1 in self.rules.items():
            for rule_id2, rule2 in self.rules.items():
                if rule_id1 >= rule_id2:
                    continue
                
                if self._rules_contradict(rule1, rule2):
                    issues['contradictions'].append({
                        'rule1': rule_id1,
                        'rule2': rule_id2,
                        'reason': 'Same problem, different fixes'
                    })
        
        # Check for outdated rules (not used in 6+ months)
        six_months_ago = datetime.now().timestamp() - (6 * 30 * 24 * 60 * 60)
        
        for rule_id, rule in self.rules.items():
            created = rule.get('created', '')
            if created:
                try:
                    created_time = datetime.fromisoformat(created).timestamp()
                    if created_time < six_months_ago:
                        # Check if used recently
                        used_recently = any(
                            entry.get('solution', {}).get('rule_id') == rule_id and
                            datetime.fromisoformat(entry.get('timestamp', '')).timestamp() > six_months_ago
                            for entry in self.problem_history
                            if entry.get('timestamp')
                        )
                        
                        if not used_recently:
                            issues['outdated_rules'].append({
                                'rule_id': rule_id,
                                'created': created,
                                'reason': 'Not used in 6+ months'
                            })
                except (ValueError, TypeError):
                    pass
        
        # Check for low quality rules
        for rule_id in self.rules.keys():
            metrics = self.calculate_rule_quality_metrics(rule_id)
            if metrics['support'] >= 5 and metrics['precision'] < 0.5:
                issues['low_quality_rules'].append({
                    'rule_id': rule_id,
                    'precision': metrics['precision'],
                    'support': metrics['support']
                })
        
        # Check for orphaned rules (no history)
        for rule_id in self.rules.keys():
            if rule_id not in self.rule_stats or self.rule_stats[rule_id]['attempts'] == 0:
                issues['orphaned_rules'].append({
                    'rule_id': rule_id,
                    'reason': 'Never applied'
                })
        
        return issues
    
    def _rules_contradict(self, rule1: Dict, rule2: Dict) -> bool:
        """Check if two rules contradict each other."""
        # Same problem type
        cond1 = rule1.get('condition', {})
        cond2 = rule2.get('condition', {})
        
        if (cond1.get('problem_type') != cond2.get('problem_type') or
            cond1.get('category') != cond2.get('category')):
            return False
        
        # Different fix types
        action1 = rule1.get('action', {})
        action2 = rule2.get('action', {})
        
        return action1.get('fix_type') != action2.get('fix_type')


# Convenience function for quick testing
if __name__ == "__main__":
    kb = KnowledgeBase()
    kb.print_statistics()
    
    # Test matching
    test_problem = {
        'type': 'shutdown',
        'category': 'interface',
        'device': 'R1',
        'interface': 'Fa0/0',
        'should_be_up': True
    }
    
    print("\nTesting rule matching for:", test_problem)
    matches = kb.get_matching_rules(test_problem)
    print(f"Found {len(matches)} matching rules:")
    for rule in matches[:3]:
        print(f"  - {rule['id']}: {rule['action']['description']} (confidence: {rule['confidence']:.2f})")