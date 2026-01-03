#!/usr/bin/env python3
"""knowledge_base.py - Centralized knowledge repository for network troubleshooting"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict


class KnowledgeBase:
    """
    Stores and manages troubleshooting knowledge including:
    - Problem patterns
    - Solution rules
    - Historical fixes
    - Configuration baselines
    """
    
    def __init__(self, db_path=None, config_dir=None):
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
        
        # Rule 1: Interface Shutdown
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
            category='interface'
        )
        
        # Rule 2: IP Address Mismatch
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
            category='interface'
        )
        
        # Rule 3: Missing IP Address
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
            category='interface'
        )
        
        # Rule 4: EIGRP AS Mismatch
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
            category='eigrp'
        )
        
        # Rule 5: EIGRP K-Values Mismatch
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
            category='eigrp'
        )
        
        # Rule 6: EIGRP Hello Timer Mismatch
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
            category='eigrp'
        )
        
        # Rule 7: EIGRP Stub Configuration
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
            category='eigrp'
        )
        
        # Rule 8: EIGRP Passive Interface
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
            category='eigrp'
        )
        
        # Rule 9: EIGRP Missing Network
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
            category='eigrp'
        )
        
        # Rule 10: OSPF Process ID Mismatch
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
            category='ospf'
        )
        
        # Rule 11: OSPF Hello Interval Mismatch
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
            category='ospf'
        )
        
        # Rule 12: OSPF Router ID Mismatch
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
            category='ospf'
        )
        
        # Rule 13: OSPF Duplicate Router ID
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
            category='ospf'
        )
        
        # Rule 14: OSPF Passive Interface
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
            category='ospf'
        )
        
        # Rule 15: OSPF Interface Not in OSPF
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
            category='ospf'
        )
        
        # Rule 16: OSPF Area Mismatch
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
            category='ospf'
        )
        
        # Rule 17: Authentication Mismatch (Generic)
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
            category='general'
        )
        
        print(f"[KnowledgeBase] Initialized with {len(self.rules)} basic rules")
    
    def add_rule(self, rule_id, condition, action, confidence=1.0, category="general"):
        """
        Add a troubleshooting rule to knowledge base
        
        Args:
            rule_id: Unique identifier for the rule
            condition: Dict describing when rule applies
            action: Dict describing fix action
            confidence: Float 0-1 indicating rule confidence
            category: Category (interface, eigrp, ospf, general)
        """
        self.rules[rule_id] = {
            'id': rule_id,
            'condition': condition,
            'action': action,
            'confidence': confidence,
            'category': category,
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