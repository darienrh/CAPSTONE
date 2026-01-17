#!/usr/bin/env python3
"""
Certainty Factor (CF) propagation system for expert system reasoning.

Implements MYCIN-style certainty factors for combining evidence from multiple
sources and propagating confidence through rule chains.
"""

import math
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta


class CertaintyFactor:
    """Certainty Factor calculation and propagation system."""
    
    THRESHOLD_CERTAIN = 0.8
    THRESHOLD_PROBABLE = 0.5
    THRESHOLD_UNKNOWN = 0.2
    THRESHOLD_IMPROBABLE = -0.5
    THRESHOLD_IMPOSSIBLE = -0.8
    DECAY_HALF_LIFE_DAYS = 30
    
    @staticmethod
    def combine_conjunctive(cf1: float, cf2: float) -> float:
        """Combine two CFs conjunctively (AND operation) using weakest link principle."""
        return min(cf1, cf2)
    
    @staticmethod
    def combine_disjunctive(cf1: float, cf2: float) -> float:
        """Combine two CFs disjunctively (OR operation) using strongest evidence principle."""
        return max(cf1, cf2)
    
    @staticmethod
    def combine_parallel(cf1: float, cf2: float) -> float:
        """Combine two CFs from parallel independent evidence sources using MYCIN formula."""
        if cf1 > 0 and cf2 > 0:
            return cf1 + cf2 - (cf1 * cf2)
        elif cf1 < 0 and cf2 < 0:
            return cf1 + cf2 + (cf1 * cf2)
        else:
            denominator = 1 - min(abs(cf1), abs(cf2))
            if denominator == 0:
                return 0
            return (cf1 + cf2) / denominator
    
    @staticmethod
    def combine_multiple(cfs: List[float], method: str = 'parallel') -> float:
        """Combine multiple certainty factors using specified method."""
        if not cfs:
            return 0.0
        if len(cfs) == 1:
            return cfs[0]
        
        if method == 'conjunctive':
            return min(cfs)
        elif method == 'disjunctive':
            return max(cfs)
        else:
            result = cfs[0]
            for cf in cfs[1:]:
                result = CertaintyFactor.combine_parallel(result, cf)
            return result
    
    @staticmethod
    def propagate_through_rule(evidence_cf: float, rule_cf: float) -> float:
        """Propagate certainty through a single rule."""
        return evidence_cf * rule_cf
    
    @staticmethod
    def propagate_through_chain(evidence_cfs: List[float], rule_cfs: List[float]) -> float:
        """Propagate certainty through a chain of rules."""
        combined_evidence = CertaintyFactor.combine_multiple(evidence_cfs, method='parallel')
        result = combined_evidence
        for rule_cf in rule_cfs:
            result = CertaintyFactor.propagate_through_rule(result, rule_cf)
        return result
    
    @staticmethod
    def apply_time_decay(cf: float, timestamp: datetime, 
                        current_time: Optional[datetime] = None) -> float:
        """Apply exponential time-based decay to certainty factor."""
        if current_time is None:
            current_time = datetime.now()
        
        age_days = (current_time - timestamp).total_seconds() / 86400
        decay_factor = math.pow(0.5, age_days / CertaintyFactor.DECAY_HALF_LIFE_DAYS)
        return cf * decay_factor
    
    @staticmethod
    def interpret_cf(cf: float) -> str:
        """Convert certainty factor to human-readable interpretation."""
        if cf >= CertaintyFactor.THRESHOLD_CERTAIN:
            return "Definitely True"
        elif cf >= CertaintyFactor.THRESHOLD_PROBABLE:
            return "Probably True"
        elif cf >= CertaintyFactor.THRESHOLD_UNKNOWN:
            return "Unknown/Uncertain"
        elif cf >= CertaintyFactor.THRESHOLD_IMPROBABLE:
            return "Probably False"
        else:
            return "Definitely False"
    
    @staticmethod
    def calculate_evidence_strength(symptoms: List[Dict], 
                                   expected_symptoms: List[str]) -> float:
        """Calculate overall evidence strength from symptom matching."""
        if not expected_symptoms:
            return 0.0
        
        matching_cfs = []
        for expected in expected_symptoms:
            for symptom in symptoms:
                if expected.lower() in symptom.get('type', '').lower():
                    matching_cfs.append(symptom.get('cf', 0.5))
                    break
        
        match_ratio = len(matching_cfs) / len(expected_symptoms)
        
        if matching_cfs:
            combined_cf = CertaintyFactor.combine_multiple(matching_cfs, method='parallel')
        else:
            combined_cf = 0.0
        
        return combined_cf * match_ratio
    
    @staticmethod
    def resolve_conflicting_evidence(positive_cfs: List[float], 
                                     negative_cfs: List[float]) -> Tuple[float, str]:
        """Resolve conflicting evidence and provide explanation."""
        if positive_cfs:
            positive_combined = CertaintyFactor.combine_multiple(positive_cfs, method='parallel')
        else:
            positive_combined = 0.0
        
        if negative_cfs:
            negative_combined = CertaintyFactor.combine_multiple(negative_cfs, method='parallel')
        else:
            negative_combined = 0.0
        
        final_cf = CertaintyFactor.combine_parallel(positive_combined, -negative_combined)
        
        if final_cf > 0.5:
            explanation = "Evidence mostly supports hypothesis"
        elif final_cf > 0:
            explanation = "Evidence weakly supports hypothesis"
        elif final_cf == 0:
            explanation = "Evidence is balanced/inconclusive"
        elif final_cf > -0.5:
            explanation = "Evidence weakly contradicts hypothesis"
        else:
            explanation = "Evidence mostly contradicts hypothesis"
        
        return final_cf, explanation
    
    @staticmethod
    def calculate_rule_support(rule_id: str, problem_history: List[Dict]) -> float:
        """Calculate support for a rule based on historical success with Laplace smoothing."""
        successes = 0
        attempts = 0
        
        for entry in problem_history:
            solution = entry.get('solution', {})
            if solution.get('rule_id') == rule_id:
                attempts += 1
                if entry.get('success', False):
                    successes += 1
        
        return (successes + 1) / (attempts + 2)
    
    @staticmethod
    def adjust_cf_by_context(base_cf: float, context: Dict) -> float:
        """Adjust certainty factor based on contextual factors."""
        adjusted_cf = base_cf
        
        if context.get('baseline_validated', False):
            adjusted_cf *= 1.10
        
        if context.get('historical_success_rate', 0) > 0.8:
            adjusted_cf *= 1.05
        
        if context.get('topology_dependent', False) and not context.get('baseline_validated', False):
            adjusted_cf *= 0.90
        
        if context.get('recent_failure', False):
            adjusted_cf *= 0.80
        
        if context.get('high_risk', False):
            adjusted_cf *= 0.85
        
        if context.get('requires_manual', False):
            adjusted_cf *= 0.75
        
        return max(-1.0, min(1.0, adjusted_cf))


class EvidenceAccumulator:
    """Accumulates evidence over time and combines it using CF methods."""
    
    def __init__(self):
        """Initialize evidence accumulator."""
        self.evidence_items = []
        self.combined_cf = 0.0
    
    def add_evidence(self, cf: float, description: str = "", 
                    timestamp: Optional[datetime] = None):
        """Add a piece of evidence with optional timestamp."""
        if timestamp is None:
            timestamp = datetime.now()
        
        self.evidence_items.append({
            'cf': cf,
            'description': description,
            'timestamp': timestamp
        })
        self._recalculate()
    
    def _recalculate(self):
        """Recalculate combined certainty factor from all evidence."""
        if not self.evidence_items:
            self.combined_cf = 0.0
            return
        
        current_time = datetime.now()
        decayed_cfs = [
            CertaintyFactor.apply_time_decay(item['cf'], item['timestamp'], current_time)
            for item in self.evidence_items
        ]
        self.combined_cf = CertaintyFactor.combine_multiple(decayed_cfs, method='parallel')
    
    def get_combined_cf(self) -> float:
        """Get the current combined certainty factor."""
        return self.combined_cf
    
    def get_interpretation(self) -> str:
        """Get human-readable interpretation of combined evidence."""
        return CertaintyFactor.interpret_cf(self.combined_cf)
    
    def get_evidence_summary(self) -> Dict:
        """Get summary of all evidence with details."""
        return {
            'num_evidence_items': len(self.evidence_items),
            'combined_cf': self.combined_cf,
            'interpretation': self.get_interpretation(),
            'evidence_items': [
                {
                    'cf': item['cf'],
                    'description': item['description'],
                    'age_days': (datetime.now() - item['timestamp']).days
                }
                for item in self.evidence_items
            ]
        }
    
    def clear(self):
        """Clear all accumulated evidence."""
        self.evidence_items = []
        self.combined_cf = 0.0


def combine_rule_confidences(rule_cfs: List[float], evidence_cfs: List[float]) -> float:
    """Combine multiple rules with their evidence."""
    if len(rule_cfs) != len(evidence_cfs):
        raise ValueError("Rule and evidence lists must have same length")
    
    propagated = [
        CertaintyFactor.propagate_through_rule(e_cf, r_cf)
        for e_cf, r_cf in zip(evidence_cfs, rule_cfs)
    ]
    return CertaintyFactor.combine_multiple(propagated, method='parallel')


def evaluate_diagnosis_certainty(symptoms: List[Dict], matching_rules: List[Dict]) -> Dict:
    """Evaluate overall certainty of a diagnosis."""
    if not matching_rules:
        return {
            'certainty': 0.0,
            'interpretation': 'No matching rules',
            'confidence_level': 'none'
        }
    
    rule_cfs = [rule.get('confidence', 0.5) for rule in matching_rules]
    
    evidence_cfs = []
    for rule in matching_rules:
        expected_symptoms = rule.get('condition', {}).get('symptoms', [])
        evidence_cf = CertaintyFactor.calculate_evidence_strength(symptoms, expected_symptoms)
        evidence_cfs.append(evidence_cf)
    
    final_cf = combine_rule_confidences(rule_cfs, evidence_cfs)
    
    return {
        'certainty': final_cf,
        'interpretation': CertaintyFactor.interpret_cf(final_cf),
        'confidence_level': 'high' if final_cf > 0.7 else 'medium' if final_cf > 0.4 else 'low',
        'num_rules': len(matching_rules),
        'avg_rule_confidence': sum(rule_cfs) / len(rule_cfs),
        'avg_evidence_strength': sum(evidence_cfs) / len(evidence_cfs)
    }
