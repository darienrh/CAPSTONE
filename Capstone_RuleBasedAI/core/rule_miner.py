from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import re


class RuleMiner:
    MIN_SUPPORT = 0.3
    MIN_CONFIDENCE = 0.6
    MIN_OCCURRENCES = 3

    def __init__(self, knowledge_base):
        self.kb = knowledge_base
        self.mined_rules = []
        self.pattern_cache = {}

    def mine_rules_from_history(self, min_support=None, min_confidence=None):
        if min_confidence is None:
            min_confidence = self.MIN_CONFIDENCE
        if min_support is None:
            n = len(self.kb.problem_history)
            min_support = max(0.05, min(self.MIN_SUPPORT, self.MIN_OCCURRENCES / n)) if n > 0 else self.MIN_SUPPORT

        print(f"[RuleMiner] Mining rules from {len(self.kb.problem_history)} historical entries...")

        frequent_patterns = self._find_frequent_patterns(min_support)
        print(f"[RuleMiner] Found {len(frequent_patterns)} frequent patterns")

        association_rules = self._generate_association_rules(frequent_patterns, min_confidence)
        print(f"[RuleMiner] Generated {len(association_rules)} association rules")

        temporal_rules = self._mine_temporal_patterns()
        print(f"[RuleMiner] Found {len(temporal_rules)} temporal patterns")

        context_rules = self._extract_context_rules(min_support)
        print(f"[RuleMiner] Extracted {len(context_rules)} context-specific rules")

        all_rules = association_rules + temporal_rules + context_rules
        unique_rules = self._deduplicate_rules(all_rules)
        print(f"[RuleMiner] Total unique rules mined: {len(unique_rules)}")

        self.mined_rules = unique_rules
        return unique_rules

    def mine_and_add_to_kb(self, min_support=None, min_confidence=None):
        new_rules = self.mine_rules_from_history(min_support, min_confidence)
        added = 0
        for rule in new_rules:
            rule_id = rule['id']
            if rule_id in self.kb.rules:
                if self.kb.rules[rule_id].get('confidence', 0) >= rule.get('confidence', 0):
                    continue
            problem_type = rule['condition'].get('problem_type', '')
            category = rule['condition'].get('category', '')
            conflicting = self._find_conflicting_rule(problem_type, category, rule)
            if conflicting:
                print(f"[RuleMiner] Skipping {rule_id}: conflicts with {conflicting}")
                continue
            self.kb.rules[rule_id] = rule
            added += 1
            print(f"[RuleMiner] Added mined rule: {rule_id} (CF={rule.get('confidence', 0):.3f})")

        if added > 0:
            self.kb._rebuild_rule_index()
            self.kb._save_knowledge()
            print(f"[RuleMiner] Saved {added} new rule(s) to knowledge base")
        return added

    def _find_conflicting_rule(self, problem_type, category, new_rule):
        new_fix = new_rule.get('action', {}).get('fix_type', '')
        for rule_id, rule in self.kb.rules.items():
            cond = rule.get('condition', {})
            if (cond.get('problem_type', '').lower() == problem_type.lower() and
                    cond.get('category', '').lower() == category.lower()):
                existing_fix = rule.get('action', {}).get('fix_type', '')
                if existing_fix != new_fix and rule.get('confidence', 0) >= 0.8:
                    return rule_id
        return None

    def _get_fix_type(self, entry: dict) -> str:
        solution = entry.get('solution', {})
        fix_type = solution.get('fix_type', '')
        if fix_type:
            return fix_type
        rule_id = solution.get('rule_id', '')
        if rule_id and rule_id in self.kb.rules:
            return self.kb.rules[rule_id].get('action', {}).get('fix_type', 'unknown')
        return 'unknown'

    def _find_frequent_patterns(self, min_support):
        if not self.kb.problem_history:
            return []

        pattern_counts = defaultdict(int)
        total_entries = len(self.kb.problem_history)

        for entry in self.kb.problem_history:
            if not entry.get('success', False):
                continue
            problem = entry.get('problem', {})
            key = (
                problem.get('type', 'unknown'),
                problem.get('category', 'unknown'),
                self._get_fix_type(entry)
            )
            pattern_counts[key] += 1

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

        frequent_patterns.sort(key=lambda x: x['support'], reverse=True)
        return frequent_patterns

    def _generate_association_rules(self, frequent_patterns, min_confidence):
        triple_stats = defaultdict(lambda: (0, 0))
        for entry in self.kb.problem_history:
            problem = entry.get('problem', {})
            key = (
                problem.get('type'),
                problem.get('category'),
                self._get_fix_type(entry),
            )
            attempts, successes = triple_stats[key]
            attempts += 1
            if entry.get('success', False):
                successes += 1
            triple_stats[key] = (attempts, successes)

        rules = []
        for pattern in frequent_patterns:
            problem_type = pattern['problem_type']
            category = pattern['category']
            fix_type = pattern['fix_type']
            attempts, successes = triple_stats.get(
                (problem_type, category, fix_type), (0, 0)
            )
            if attempts == 0:
                continue
            confidence = successes / attempts
            if confidence >= min_confidence:
                rules.append(self._create_rule_from_pattern(
                    pattern, confidence, successes, attempts
                ))
        return rules

    def _create_rule_from_pattern(self, pattern, confidence, successes, attempts):
        problem_type = pattern['problem_type']
        category = pattern['category']
        fix_type = pattern['fix_type']
        rule_id = f"MINED_{category.upper()}_{len(self.mined_rules) + 1:03d}"
        symptoms = self._extract_common_symptoms(problem_type, category)
        commands = self._generate_fix_commands(fix_type, category)
        topology_dependent = self._is_topology_dependent(fix_type, category)

        return {
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

    def _mine_temporal_patterns(self):
        if len(self.kb.problem_history) < 2:
            return []

        sorted_history = sorted(
            self.kb.problem_history,
            key=lambda x: x.get('timestamp', '')
        )

        sequences = defaultdict(list)
        time_window = timedelta(minutes=30)

        for i in range(len(sorted_history) - 1):
            e1 = sorted_history[i]
            e2 = sorted_history[i + 1]
            try:
                t1 = datetime.fromisoformat(e1.get('timestamp', ''))
                t2 = datetime.fromisoformat(e2.get('timestamp', ''))
                if t2 - t1 <= time_window:
                    p1 = e1.get('problem', {}).get('type', '')
                    p2 = e2.get('problem', {}).get('type', '')
                    if p1 and p2:
                        sequences[(p1, p2)].append((e1, e2))
            except (ValueError, TypeError):
                continue

        rules = []
        for (p1_type, p2_type), occurrences in sequences.items():
            if len(occurrences) < self.MIN_OCCURRENCES:
                continue
            successful = [(e1, e2) for e1, e2 in occurrences
                         if e1.get('success', False) and e2.get('success', False)]
            if not successful:
                continue
            confidence = len(successful) / len(occurrences)
            if confidence < self.MIN_CONFIDENCE:
                continue

            sample_e2 = successful[0][1]
            category = sample_e2.get('problem', {}).get('category', 'general')
            fix_type = sample_e2.get('solution', {}).get('fix_type', 'unknown')
            rule_id = f"TEMPORAL_{len(rules) + 1:03d}"

            rules.append({
                'id': rule_id,
                'condition': {
                    'problem_type': p2_type,
                    'category': category,
                    'symptoms': [p1_type],
                    'preceded_by': p1_type,
                },
                'action': {
                    'fix_type': fix_type,
                    'commands': self._generate_fix_commands(fix_type, category),
                    'description': f"Temporal: after {p1_type}, apply {fix_type} for {p2_type}",
                    'verification': self._get_verification_command(category)
                },
                'confidence': confidence,
                'category': category,
                'topology_dependent': self._is_topology_dependent(fix_type, category),
                'mined': True,
                'temporal': True,
                'mining_stats': {
                    'occurrences': len(occurrences),
                    'successful_pairs': len(successful),
                    'success_rate': confidence,
                },
                'created': datetime.now().isoformat()
            })

        return rules

    def _extract_context_rules(self, min_support):
        if not self.kb.problem_history:
            return []

        context_patterns = defaultdict(lambda: defaultdict(lambda: {'success': 0, 'total': 0}))

        for entry in self.kb.problem_history:
            problem = entry.get('problem', {})
            device = problem.get('device', '')
            problem_type = problem.get('type', '')
            fix_type = self._get_fix_type(entry)
            if not (device and problem_type and fix_type and fix_type != 'unknown'):
                continue
            ctx = context_patterns[(problem_type, device)][fix_type]
            ctx['total'] += 1
            if entry.get('success', False):
                ctx['success'] += 1

        total_entries = max(len(self.kb.problem_history), 1)
        rules = []

        for (problem_type, device), fix_stats in context_patterns.items():
            for fix_type, stats in fix_stats.items():
                if stats['total'] < self.MIN_OCCURRENCES:
                    continue
                support = stats['total'] / total_entries
                if support < min_support:
                    continue
                confidence = stats['success'] / stats['total']
                if confidence < self.MIN_CONFIDENCE:
                    continue

                category = self._infer_category(problem_type)
                rule_id = f"CTX_{device.upper()}_{len(rules) + 1:03d}"
                rules.append({
                    'id': rule_id,
                    'condition': {
                        'problem_type': problem_type,
                        'category': category,
                        'device': device,
                        'symptoms': self._extract_common_symptoms(problem_type, category),
                    },
                    'action': {
                        'fix_type': fix_type,
                        'commands': self._generate_fix_commands(fix_type, category),
                        'description': f"Context ({device}): {fix_type} for {problem_type}",
                        'verification': self._get_verification_command(category)
                    },
                    'confidence': confidence,
                    'category': category,
                    'topology_dependent': self._is_topology_dependent(fix_type, category),
                    'mined': True,
                    'context_specific': True,
                    'context_device': device,
                    'mining_stats': {
                        'support': support,
                        'successes': stats['success'],
                        'attempts': stats['total'],
                        'success_rate': confidence,
                    },
                    'created': datetime.now().isoformat()
                })

        return rules

    def _deduplicate_rules(self, rules):
        seen = {}
        for rule in rules:
            key = (
                rule['condition'].get('problem_type', ''),
                rule['condition'].get('category', ''),
                rule['action'].get('fix_type', ''),
                rule['condition'].get('device', '')
            )
            if key not in seen or rule.get('confidence', 0) > seen[key].get('confidence', 0):
                seen[key] = rule
        return list(seen.values())

    def _extract_common_symptoms(self, problem_type, category):
        symptom_counts = Counter()
        for entry in self.kb.problem_history:
            problem = entry.get('problem', {})
            if problem.get('type') == problem_type and problem.get('category') == category:
                for key in problem:
                    if key not in ('type', 'category', 'device', 'timestamp'):
                        symptom_counts[key] += 1
        return [s for s, _ in symptom_counts.most_common(5)]

    def _generate_fix_commands(self, fix_type, category):
        templates = {
            'no_shutdown': ['interface {interface}', 'no shutdown', 'end'],
            'configure_ip': [
                'interface {interface}',
                'ip address {expected_ip} {expected_mask}', 'end'
            ],
            'configure_timers': (
                ['interface {interface}',
                 'ip hello-interval eigrp {as_number} {expected_hello}',
                 'ip hold-time eigrp {as_number} {expected_hold}', 'end']
                if category == 'eigrp' else
                ['interface {interface}',
                 'ip ospf hello-interval {expected_hello}',
                 'ip ospf dead-interval {expected_dead}', 'end']
            ),
            'remove_passive': [
                'router {protocol} {as_or_process}',
                'no passive-interface {interface}', 'end'
            ],
            'configure_k_values': [
                'router eigrp {as_number}', 'metric weights {expected}', 'end'
            ],
            'configure_router_id': [
                'router ospf {process_id}', 'router-id {expected}', 'end'
            ],
            'add_network': (
                ['router eigrp {as_number}', 'network {network}', 'end']
                if category == 'eigrp' else
                ['router ospf {process_id}',
                 'network {network} {wildcard} area {area}', 'end']
            ),
            'remove_stub': [
                'router eigrp {as_number}', 'no eigrp stub', 'end'
            ],
            'remove_stub_area': [
                'router ospf {process_id}', 'no area {area} stub', 'end'
            ],
            'remove_network': [
                'router ospf {process_id}',
                'no network {network} {wildcard} area {area}', 'end'
            ],
            'revert_to_baseline': ['# Revert to stable configuration'],
        }
        return templates.get(fix_type, ['# Auto-generated fix'])

    def _get_verification_command(self, category):
        return {
            'interface': 'show ip interface brief',
            'eigrp': 'show ip eigrp neighbors',
            'ospf': 'show ip ospf neighbor',
            'general': 'show ip protocols'
        }.get(category, 'show running-config')

    def _is_topology_dependent(self, fix_type, category):
        if fix_type in ('no_shutdown',):
            return False
        if fix_type in ('configure_ip', 'configure_timers', 'configure_k_values',
                        'configure_router_id', 'add_network', 'configure_area',
                        'remove_stub_area', 'remove_network', 'remove_stub'):
            return True
        return category in ('eigrp', 'ospf')

    def _infer_category(self, problem_type):
        pt = problem_type.lower()
        if 'eigrp' in pt or 'as ' in pt or 'k-value' in pt or 'k value' in pt or 'stub config' in pt:
            return 'eigrp'
        if ('ospf' in pt or 'router id' in pt or 'stub area' in pt
                or 'extra network' in pt or 'missing network' in pt
                or 'hello interval' in pt or 'dead interval' in pt):
            return 'ospf'
        if 'interface' in pt or 'shutdown' in pt or 'ip address' in pt or 'passive' in pt:
            return 'interface'
        return 'general'