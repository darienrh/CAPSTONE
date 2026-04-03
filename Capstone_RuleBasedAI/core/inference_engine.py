from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict, deque
from datetime import datetime

try:
    from core.certainty_factors import CertaintyFactor
except ImportError:
    CertaintyFactor = None


class InferenceEngine:
    def __init__(self, knowledge_base):
        self.kb = knowledge_base
        self.explanation_traces = []

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

    # ── Core diagnosis ──────────────────────────────────────────────────────

    def diagnose(self, symptoms, context=None):
        diagnoses = []
        for symptom in symptoms:
            device_name = symptom.get('device', '')
            baseline_context = None
            if self.kb.config_manager and device_name:
                baseline_context = self.kb.config_manager.get_device_baseline(device_name)

            tiered_recs = self.kb.get_tiered_recommendations(
                symptom, baseline_context=baseline_context
            )

            for rule in tiered_recs['tier1']:
                diagnoses.append(self._create_diagnosis_from_rule(rule, symptom, tier=1))
            for rule in tiered_recs['tier2']:
                diagnoses.append(self._create_diagnosis_from_rule(rule, symptom, tier=2))
            for rule in tiered_recs['tier3']:
                diagnoses.append(self._create_diagnosis_from_rule(rule, symptom, tier=3))

        diagnoses.sort(key=lambda x: (x['tier'], -x['confidence']))
        return diagnoses

    def _create_diagnosis_from_rule(self, rule, symptom, tier):
        cf = self._compute_certainty_factor(rule, symptom)
        return {
            'root_cause': symptom.get('type', ''),
            'confidence': cf,
            'raw_confidence': rule['confidence'],
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
            'verification': rule['action'].get('verification', 'Verify manually'),
            'topology_dependent': rule.get('topology_dependent', False),
        }

    # ── Certainty factor computation ─────────────────────────────────────────

    def _compute_certainty_factor(self, rule: Dict, symptom: Dict) -> float:
        base_cf = rule.get('confidence', 0.5)

        if CertaintyFactor is None:
            return base_cf

        context = {
            'baseline_validated': rule.get('baseline_validated', False),
            'topology_dependent': rule.get('topology_dependent', False),
            'high_risk': rule.get('action', {}).get('requires_manual', False),
            'requires_manual': rule.get('action', {}).get('requires_manual', False),
        }

        rule_id = rule.get('id', '')
        if rule_id and rule_id in self.kb.rule_stats:
            stats = self.kb.rule_stats[rule_id]
            if stats.get('attempts', 0) > 0:
                context['historical_success_rate'] = (
                    stats['successes'] / stats['attempts']
                )
                if stats['attempts'] >= 3 and context['historical_success_rate'] < 0.4:
                    context['recent_failure'] = True

        adjusted = CertaintyFactor.adjust_cf_by_context(base_cf, context)

        similar = self.kb.get_similar_problems(symptom, limit=3)
        if similar:
            positive_cfs = [s['solution'].get('confidence', 0.5)
                           for s in similar if s['success']]
            negative_cfs = [s['solution'].get('confidence', 0.5)
                           for s in similar if not s['success']]
            if positive_cfs or negative_cfs:
                historical_cf, _ = CertaintyFactor.resolve_conflicting_evidence(
                    positive_cfs, negative_cfs
                )
                adjusted = CertaintyFactor.combine_parallel(adjusted, historical_cf * 0.3)

        return round(max(0.0, min(1.0, adjusted)), 4)

    # ── Fix recommendation & sequencing (IE drives this) ────────────────────

    def recommend_fixes(self, diagnosis, max_recommendations=3):
        if isinstance(diagnosis, list):
            diagnosis_list = diagnosis
        else:
            diagnosis_list = [diagnosis]

        sequenced = self._sequence_by_confidence(diagnosis_list)

        recommendations = []
        for diag in sequenced[:max_recommendations]:
            recommendation = {
                'fix_id': f"fix_{len(recommendations)+1}",
                'description': diag.get('suggested_action', 'Unknown fix'),
                'commands': diag.get('commands', []),
                'confidence': diag['confidence'],
                'tier': diag.get('tier', 3),
                'baseline_validated': diag.get('baseline_validated', False),
                'expected_outcome': f"Resolve {diag['root_cause']}",
                'risks': self._assess_risks(diag),
                'verification': diag.get('verification', 'Verify manually'),
                'requires_manual': diag.get('requires_manual', False),
                'rule_id': diag.get('rule_id', ''),
            }
            recommendations.append(recommendation)
        return recommendations

    def _sequence_by_confidence(self, diagnoses: List[Dict]) -> List[Dict]:
        """
        IE-driven sequencing: tier first, then CF score descending.
        Within same tier, higher confidence fixes run first.
        Manual-intervention fixes always pushed to end.
        """
        manual = [d for d in diagnoses if d.get('requires_manual')]
        auto = [d for d in diagnoses if not d.get('requires_manual')]
        auto.sort(key=lambda x: (x.get('tier', 3), -x.get('confidence', 0)))
        manual.sort(key=lambda x: -x.get('confidence', 0))
        return auto + manual

    def select_fix_for_problem(self, problem: Dict) -> Optional[Dict]:
        """
        Single entry point: IE selects the best fix for a problem using
        KB rules + CF scoring + historical data. Returns the top recommendation.
        """
        symptoms = [problem]
        diagnoses = self.diagnose(symptoms)
        if not diagnoses:
            return None

        sequenced = self._sequence_by_confidence(diagnoses)
        best = sequenced[0]

        trace = self._build_explanation_trace(problem, diagnoses, best)
        self.explanation_traces.append(trace)

        return {
            'rule_id': best.get('rule_id'),
            'commands': best.get('commands', []),
            'confidence': best.get('confidence'),
            'tier': best.get('tier'),
            'description': best.get('suggested_action'),
            'baseline_validated': best.get('baseline_validated', False),
            'requires_manual': best.get('requires_manual', False),
            'verification': best.get('verification'),
            'trace_id': trace['trace_id'],
        }

    def sequence_fixes(self, problems: List[Dict]) -> List[Dict]:
        """
        Given a list of problems, IE determines the optimal fix order
        using priority scoring (confidence, impact, risk, complexity).
        Returns problems in apply-order.
        """
        return self.calculate_fix_priority(problems)

    # ── Explanation trace ────────────────────────────────────────────────────

    def _build_explanation_trace(self, problem: Dict, all_diagnoses: List[Dict],
                                  chosen: Dict) -> Dict:
        trace_id = f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        trace = {
            'trace_id': trace_id,
            'timestamp': datetime.now().isoformat(),
            'problem': {
                'type': problem.get('type'),
                'category': problem.get('category'),
                'device': problem.get('device'),
                'interface': problem.get('interface'),
            },
            'reasoning_steps': [],
            'chosen_fix': {
                'rule_id': chosen.get('rule_id'),
                'confidence': chosen.get('confidence'),
                'tier': chosen.get('tier'),
                'description': chosen.get('suggested_action'),
                'baseline_validated': chosen.get('baseline_validated'),
            },
            'alternatives_considered': [
                {
                    'rule_id': d.get('rule_id'),
                    'confidence': d.get('confidence'),
                    'tier': d.get('tier'),
                    'rejected_reason': self._rejection_reason(d, chosen),
                }
                for d in all_diagnoses if d.get('rule_id') != chosen.get('rule_id')
            ][:5],
        }

        trace['reasoning_steps'].append(
            f"Problem detected: {problem.get('type')} on {problem.get('device')}"
        )
        trace['reasoning_steps'].append(
            f"KB returned {len(all_diagnoses)} candidate rule(s)"
        )

        similar = self.kb.get_similar_problems(problem, limit=3)
        if similar:
            trace['reasoning_steps'].append(
                f"Found {len(similar)} similar historical case(s)"
            )

        trace['reasoning_steps'].append(
            f"IE selected rule {chosen.get('rule_id')} "
            f"(CF={chosen.get('confidence'):.3f}, tier={chosen.get('tier')})"
        )

        if chosen.get('baseline_validated'):
            trace['reasoning_steps'].append("Commands baseline-validated and pre-formatted")
        if chosen.get('requires_manual'):
            trace['reasoning_steps'].append("WARNING: Fix requires manual intervention")

        return trace

    def _rejection_reason(self, candidate: Dict, chosen: Dict) -> str:
        if candidate.get('tier', 3) > chosen.get('tier', 3):
            return f"Lower tier ({candidate['tier']} vs {chosen['tier']})"
        if candidate.get('confidence', 0) < chosen.get('confidence', 0):
            return f"Lower CF ({candidate['confidence']:.3f} vs {chosen['confidence']:.3f})"
        if candidate.get('requires_manual') and not chosen.get('requires_manual'):
            return "Requires manual intervention"
        return "Superseded by higher-confidence rule"

    def get_explanation_traces(self) -> List[Dict]:
        return self.explanation_traces

    def get_last_trace(self) -> Optional[Dict]:
        return self.explanation_traces[-1] if self.explanation_traces else None

    def print_trace(self, trace: Dict):
        print(f"\n{'='*60}")
        print(f"EXPLANATION TRACE: {trace['trace_id']}")
        print(f"{'='*60}")
        print(f"Problem : {trace['problem']['type']} on {trace['problem']['device']}")
        print(f"\nReasoning Path:")
        for i, step in enumerate(trace['reasoning_steps'], 1):
            print(f"  {i}. {step}")
        fix = trace['chosen_fix']
        print(f"\nChosen Fix  : {fix['rule_id']} | CF={fix['confidence']:.3f} | Tier={fix['tier']}")
        print(f"Description : {fix['description']}")
        print(f"Validated   : {fix['baseline_validated']}")
        if trace['alternatives_considered']:
            print(f"\nAlternatives Rejected:")
            for alt in trace['alternatives_considered']:
                print(f"  - {alt['rule_id']} ({alt['rejected_reason']})")
        print(f"{'='*60}\n")

    # ── Priority scoring ─────────────────────────────────────────────────────

    def calculate_fix_priority(self, fixes, criteria=None):
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
        category = problem.get('category', '')
        severity = problem.get('severity', 'medium')
        impact = 0.5
        if severity in ('high', 'critical'):
            impact += 0.3
        if category in ('eigrp', 'ospf'):
            impact += 0.2
        return min(1.0, impact)

    def _calculate_risk_score(self, problem: Dict) -> float:
        problem_type = problem.get('type', '')
        high_risk = ['as mismatch', 'process id mismatch', 'authentication mismatch']
        medium_risk = ['k-value mismatch', 'hello timer mismatch', 'dead interval mismatch']
        if problem_type in high_risk:
            return 0.8
        elif problem_type in medium_risk:
            return 0.5
        return 0.3

    def _calculate_complexity(self, problem: Dict) -> float:
        problem_type = problem.get('type', '')
        complex_types = ['as mismatch', 'duplicate router id', 'authentication mismatch']
        return 0.8 if problem_type in complex_types else 0.3

    # ── Risk assessment ──────────────────────────────────────────────────────

    def _assess_risks(self, diagnosis: Dict) -> List[str]:
        risks = []
        if diagnosis.get('requires_manual'):
            risks.append("Requires manual intervention")
        commands = diagnosis.get('commands', [])
        if any('no router' in str(cmd) for cmd in commands):
            risks.append("Will remove routing protocol configuration")
        if any('shutdown' in str(cmd) for cmd in commands):
            risks.append("May cause temporary connectivity loss")
        tier = diagnosis.get('tier', 3)
        if tier == 3 and not diagnosis.get('requires_manual'):
            risks.append("Low confidence - consider baseline revert")
        if not diagnosis.get('baseline_validated') and diagnosis.get('topology_dependent'):
            risks.append("Not validated against baseline configuration")
        return risks if risks else ["Minimal risk"]

    # ── Chain reasoning ──────────────────────────────────────────────────────

    def chain_reasoning(self, initial_problem, depth=3):
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
        if problem_type in self.cause_relationships:
            for blocked in self.cause_relationships[problem_type].get('blocks', []):
                sub_chain = self.chain_reasoning(
                    {'type': blocked, 'device': device, 'interface': interface},
                    depth - 1
                )
                chain['leads_to'].append(sub_chain)
        if 'shutdown' in problem_type or ('interface' in problem_type and 'down' in problem_type):
            chain['leads_to'].extend([
                {'root': 'eigrp_adjacency', 'blocked_by': problem_type},
                {'root': 'ospf_adjacency', 'blocked_by': problem_type}
            ])
        return chain

    def _assess_chain_impact(self, problem_type: str) -> str:
        high_impact = ['shutdown', 'interface_down', 'as_mismatch', 'process_id_mismatch']
        medium_impact = ['ip_mismatch', 'timer_mismatch', 'k_value_mismatch']
        if any(hi in problem_type for hi in high_impact):
            return 'high'
        elif any(mi in problem_type for mi in medium_impact):
            return 'medium'
        return 'low'

    # ── Explain reasoning (text) ─────────────────────────────────────────────

    def explain_reasoning(self, diagnosis):
        if isinstance(diagnosis, list):
            if not diagnosis:
                return "No diagnosis could be determined from available symptoms."
            diagnosis = diagnosis[0]
        root_cause = diagnosis.get('root_cause', 'unknown')
        confidence = diagnosis.get('confidence', 0)
        evidence = diagnosis.get('evidence', [])
        cf_label = ""
        if CertaintyFactor:
            cf_label = f" [{CertaintyFactor.interpret_cf(confidence)}]"
        explanation = f"Diagnosis: {root_cause} (CF: {confidence:.3f}{cf_label})\n"
        if evidence:
            explanation += "\nBased on the following evidence:\n"
            for i, symptom in enumerate(evidence, 1):
                symptom_type = symptom.get('type', 'unknown')
                location = symptom.get('interface', symptom.get('device', ''))
                explanation += f"  {i}. {symptom_type}"
                if location:
                    explanation += f" at {location}"
                explanation += "\n"
        explanation += f"\nSuggested action: {diagnosis.get('suggested_action', 'Investigate further')}"
        return explanation

    # ── Conflict detection ───────────────────────────────────────────────────

    def detect_conflicting_fixes(self, fix_list):
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
                        'reason': conflict.get('reason', ''),
                    })
        return conflicts

    def _check_fix_conflict(self, fix1: Dict, fix2: Dict) -> Optional[Dict]:
        same_device = fix1.get('device') == fix2.get('device')
        same_intf = fix1.get('interface') == fix2.get('interface')
        same_cat = fix1.get('category') == fix2.get('category')
        if same_device and same_intf and same_cat:
            return {
                'type': 'resource_conflict',
                'reason': f"Both fixes target {fix1.get('interface')} on {fix1.get('device')}"
            }
        return None