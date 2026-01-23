#!/usr/bin/env python3
"""
advanced_analytics.py - Advanced analytics and operational features

Implements advanced analytics capabilities for the network troubleshooting system:
- Cross-device correlation analysis
- Problem clustering and pattern analysis
- Root cause path tracing
- Confidence threshold tuning
- Explanation facility
- Historical trend analysis
- Audit logging and backup/recovery
"""

from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import json
import math
from pathlib import Path


class CrossDeviceCorrelator:
    """
    Detects cascading failures and correlations across network topology.

    Analyzes problem patterns across devices to identify:
    - Cascading failures (one device failure causing others)
    - Topology-aware correlations
    - Root cause propagation paths
    """

    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.correlation_graph = defaultdict(list)
        self.failure_chains = []

    def analyze_cascading_failures(self, problem_history: List[Dict]) -> Dict:
        """
        Analyze problem history for cascading failure patterns.

        Args:
            problem_history: List of historical problems

        Returns:
            Dictionary with cascading failure analysis
        """
        # Group problems by time windows
        time_windows = self._group_problems_by_time(problem_history)

        cascading_failures = []
        correlation_strengths = defaultdict(float)

        for window_problems in time_windows:
            if len(window_problems) < 2:
                continue

            # Sort by timestamp
            window_problems.sort(key=lambda x: x.get('timestamp', ''))

            # Look for causal chains
            chains = self._detect_causal_chains(window_problems)

            for chain in chains:
                if len(chain) >= 2:
                    cascading_failures.append(chain)

                    # Calculate correlation strength
                    for i in range(len(chain) - 1):
                        cause_device = chain[i]['device']
                        effect_device = chain[i + 1]['device']
                        key = f"{cause_device}->{effect_device}"
                        correlation_strengths[key] += 1.0

        return {
            'cascading_failures': cascading_failures,
            'correlation_strengths': dict(correlation_strengths),
            'total_chains': len(cascading_failures),
            'topology_aware': self.config_manager is not None
        }

    def _group_problems_by_time(self, problems: List[Dict], window_minutes: int = 30) -> List[List[Dict]]:
        """Group problems into time windows for correlation analysis."""
        if not problems:
            return []

        # Sort by timestamp
        sorted_problems = sorted(problems, key=lambda x: x.get('timestamp', ''))

        windows = []
        current_window = []
        window_start = None

        for problem in sorted_problems:
            try:
                problem_time = datetime.fromisoformat(problem.get('timestamp', ''))

                if window_start is None:
                    window_start = problem_time
                    current_window = [problem]
                elif (problem_time - window_start).total_seconds() <= window_minutes * 60:
                    current_window.append(problem)
                else:
                    if len(current_window) > 1:
                        windows.append(current_window)
                    window_start = problem_time
                    current_window = [problem]
            except (ValueError, TypeError):
                continue

        if len(current_window) > 1:
            windows.append(current_window)

        return windows

    def _detect_causal_chains(self, problems: List[Dict]) -> List[List[Dict]]:
        """Detect potential causal chains in a time window."""
        chains = []

        # Simple heuristic: problems on connected devices within short time
        for i, problem1 in enumerate(problems):
            chain = [problem1]

            for j, problem2 in enumerate(problems[i+1:], i+1):
                if self._are_devices_connected(problem1, problem2):
                    # Check if problem2 could be caused by problem1
                    if self._is_causal_relationship(problem1, problem2):
                        chain.append(problem2)

            if len(chain) >= 2:
                chains.append(chain)

        return chains

    def _are_devices_connected(self, problem1: Dict, problem2: Dict) -> bool:
        """Check if two devices are connected based on interface information."""
        device1 = problem1.get('device', '')
        device2 = problem2.get('device', '')

        if device1 == device2:
            return True  # Same device

        # Check if they share interface subnets (simplified topology check)
        intf1 = problem1.get('interface', '')
        intf2 = problem2.get('interface', '')

        # If we have config manager, do proper topology check
        if self.config_manager:
            return self._check_topology_connection(device1, device2, intf1, intf2)

        # Fallback: assume connected if different devices
        return device1 != device2

    def _check_topology_connection(self, device1: str, device2: str, intf1: str, intf2: str) -> bool:
        """Check if devices are connected via topology information."""
        try:
            config1 = self.config_manager.get_device_baseline(device1)
            config2 = self.config_manager.get_device_baseline(device2)

            if not config1 or not config2:
                return False

            # Check if interfaces have matching IP subnets
            ip1 = config1.get('interfaces', {}).get(intf1, {}).get('ip_address')
            ip2 = config2.get('interfaces', {}).get(intf2, {}).get('ip_address')

            if ip1 and ip2:
                # Simple subnet matching (could be enhanced)
                subnet1 = '.'.join(ip1.split('.')[:3])
                subnet2 = '.'.join(ip2.split('.')[:3])
                return subnet1 == subnet2

        except Exception:
            pass

        return False

    def _is_causal_relationship(self, cause: Dict, effect: Dict) -> bool:
        """Check if one problem could cause another."""
        cause_type = cause.get('type', '')
        effect_type = effect.get('type', '')

        # Known causal relationships
        causal_patterns = {
            'shutdown': ['no_eigrp_neighbor', 'no_ospf_neighbor', 'interface_down'],
            'interface_down': ['no_eigrp_neighbor', 'no_ospf_neighbor'],
            'as_mismatch': ['no_eigrp_neighbor'],
            'process_id_mismatch': ['no_ospf_neighbor'],
            'authentication_mismatch': ['no_eigrp_neighbor', 'no_ospf_neighbor']
        }

        return effect_type in causal_patterns.get(cause_type, [])


class ProblemClusterer:
    """
    Groups similar problems for pattern analysis and trend detection.

    Uses clustering algorithms to identify:
    - Similar problem patterns
    - Recurring issue categories
    - Device-specific problem profiles
    """

    def __init__(self):
        self.clusters = []
        self.cluster_centers = []

    def cluster_problems(self, problems: List[Dict], num_clusters: int = 5) -> Dict:
        """
        Cluster problems using k-means-like algorithm.

        Args:
            problems: List of problem dictionaries
            num_clusters: Number of clusters to create

        Returns:
            Dictionary with clustering results
        """
        if len(problems) < num_clusters:
            return {
                'clusters': [[p] for p in problems],
                'cluster_centers': problems,
                'silhouette_score': 0.0
            }

        # Simple feature extraction
        features = []
        for problem in problems:
            feature_vector = self._extract_problem_features(problem)
            features.append(feature_vector)

        # K-means clustering
        clusters, centers = self._kmeans_clustering(features, num_clusters)

        # Assign problems to clusters
        clustered_problems = [[] for _ in range(num_clusters)]
        for i, cluster_id in enumerate(clusters):
            clustered_problems[cluster_id].append(problems[i])

        # Calculate cluster characteristics
        cluster_profiles = []
        for i, cluster_problems in enumerate(clustered_problems):
            profile = self._analyze_cluster_profile(cluster_problems)
            cluster_profiles.append(profile)

        return {
            'clusters': clustered_problems,
            'cluster_centers': centers,
            'cluster_profiles': cluster_profiles,
            'num_clusters': num_clusters,
            'total_problems': len(problems)
        }

    def _extract_problem_features(self, problem: Dict) -> List[float]:
        """Extract numerical features from a problem for clustering."""
        features = []

        # Problem type (categorical -> numerical)
        problem_type = problem.get('type', 'unknown')
        type_hash = hash(problem_type) % 1000 / 1000.0  # Normalize to 0-1
        features.append(type_hash)

        # Category
        category = problem.get('category', 'unknown')
        cat_hash = hash(category) % 1000 / 1000.0
        features.append(cat_hash)

        # Device (for device-specific clustering)
        device = problem.get('device', 'unknown')
        device_hash = hash(device) % 1000 / 1000.0
        features.append(device_hash)

        # Time of day (0-1, where 0 = midnight, 0.5 = noon)
        try:
            timestamp = problem.get('timestamp', '')
            if timestamp:
                dt = datetime.fromisoformat(timestamp)
                time_of_day = (dt.hour * 3600 + dt.minute * 60 + dt.second) / 86400.0
                features.append(time_of_day)
            else:
                features.append(0.5)  # Default to noon
        except:
            features.append(0.5)

        # Success indicator
        success = 1.0 if problem.get('success', False) else 0.0
        features.append(success)

        return features

    def _kmeans_clustering(self, features: List[List[float]], k: int) -> Tuple[List[int], List[List[float]]]:
        """Simple k-means clustering implementation."""
        # Initialize centers randomly
        centers = [features[i].copy() for i in range(min(k, len(features)))]

        for _ in range(10):  # Max iterations
            # Assign points to nearest center
            clusters = []
            for point in features:
                distances = [self._euclidean_distance(point, center) for center in centers]
                cluster_id = distances.index(min(distances))
                clusters.append(cluster_id)

            # Update centers
            for i in range(k):
                cluster_points = [features[j] for j in range(len(features)) if clusters[j] == i]
                if cluster_points:
                    centers[i] = [sum(x) / len(cluster_points) for x in zip(*cluster_points)]

        return clusters, centers

    def _euclidean_distance(self, point1: List[float], point2: List[float]) -> float:
        """Calculate Euclidean distance between two points."""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(point1, point2)))

    def _analyze_cluster_profile(self, problems: List[Dict]) -> Dict:
        """Analyze the characteristics of a problem cluster."""
        if not problems:
            return {}

        # Count problem types
        problem_types = Counter(p.get('type', 'unknown') for p in problems)
        categories = Counter(p.get('category', 'unknown') for p in problems)
        devices = Counter(p.get('device', 'unknown') for p in problems)

        # Success rate
        successes = sum(1 for p in problems if p.get('success', False))
        success_rate = successes / len(problems) if problems else 0

        # Time distribution
        times = []
        for p in problems:
            try:
                timestamp = p.get('timestamp', '')
                if timestamp:
                    dt = datetime.fromisoformat(timestamp)
                    times.append(dt.hour + dt.minute / 60.0)
            except:
                continue

        avg_time = sum(times) / len(times) if times else 12.0

        return {
            'size': len(problems),
            'problem_types': dict(problem_types.most_common(3)),
            'categories': dict(categories.most_common(3)),
            'devices': dict(devices.most_common(3)),
            'success_rate': success_rate,
            'avg_time_of_day': avg_time,
            'time_spread': max(times) - min(times) if times else 0
        }


class RootCauseTracer:
    """
    Traces the complete reasoning path from symptoms to root cause diagnosis.

    Provides detailed explanation of:
    - Evidence collection and evaluation
    - Rule application sequence
    - Confidence propagation
    - Alternative hypotheses considered
    """

    def __init__(self, knowledge_base, inference_engine):
        self.kb = knowledge_base
        self.ie = inference_engine
        self.trace_log = []

    def trace_diagnosis_path(self, symptoms: List[Dict], diagnosis: Dict) -> Dict:
        """
        Trace the complete reasoning path for a diagnosis.

        Args:
            symptoms: Original symptoms
            diagnosis: Final diagnosis

        Returns:
            Detailed reasoning trace
        """
        trace = {
            'symptoms': symptoms,
            'diagnosis': diagnosis,
            'reasoning_steps': [],
            'evidence_evaluation': [],
            'rule_applications': [],
            'confidence_propagation': [],
            'alternative_hypotheses': []
        }

        # Step 1: Evidence collection
        evidence_trace = self._trace_evidence_collection(symptoms)
        trace['evidence_evaluation'] = evidence_trace

        # Step 2: Rule matching
        rule_trace = self._trace_rule_matching(symptoms)
        trace['rule_applications'] = rule_trace

        # Step 3: Confidence propagation
        confidence_trace = self._trace_confidence_propagation(symptoms, diagnosis)
        trace['confidence_propagation'] = confidence_trace

        # Step 4: Alternative hypotheses
        alternatives = self._find_alternative_hypotheses(symptoms, diagnosis)
        trace['alternative_hypotheses'] = alternatives

        # Step 5: Final reasoning chain
        reasoning_chain = self._build_reasoning_chain(trace)
        trace['reasoning_steps'] = reasoning_chain

        return trace

    def _trace_evidence_collection(self, symptoms: List[Dict]) -> List[Dict]:
        """Trace how evidence was collected and evaluated."""
        evidence_trace = []

        for symptom in symptoms:
            evidence = {
                'symptom': symptom,
                'collection_method': 'direct_detection',
                'reliability': self._assess_symptom_reliability(symptom),
                'context_factors': self._extract_context_factors(symptom),
                'timestamp': datetime.now().isoformat()
            }
            evidence_trace.append(evidence)

        return evidence_trace

    def _assess_symptom_reliability(self, symptom: Dict) -> float:
        """Assess the reliability of a symptom."""
        # Factors affecting reliability
        reliability = 0.8  # Base reliability

        # Recent symptoms are more reliable
        try:
            timestamp = symptom.get('timestamp', '')
            if timestamp:
                age_hours = (datetime.now() - datetime.fromisoformat(timestamp)).total_seconds() / 3600
                if age_hours < 1:
                    reliability += 0.1  # Very recent
                elif age_hours < 24:
                    reliability += 0.05  # Recent
        except:
            pass

        # Verified symptoms are more reliable
        if symptom.get('verified', False):
            reliability += 0.1

        return min(1.0, reliability)

    def _extract_context_factors(self, symptom: Dict) -> Dict:
        """Extract contextual factors affecting symptom interpretation."""
        return {
            'device_type': self._get_device_type(symptom.get('device', '')),
            'interface_type': self._get_interface_type(symptom.get('interface', '')),
            'protocol_context': symptom.get('category', 'unknown'),
            'severity_level': symptom.get('severity', 'medium')
        }

    def _get_device_type(self, device: str) -> str:
        """Determine device type from name."""
        if not device:
            return 'unknown'

        device_upper = device.upper()
        if 'R' in device_upper and any(char.isdigit() for char in device_upper):
            return 'router'
        elif 'SW' in device_upper or 'S' in device_upper:
            return 'switch'
        else:
            return 'network_device'

    def _get_interface_type(self, interface: str) -> str:
        """Determine interface type."""
        if not interface:
            return 'unknown'

        if interface.startswith('Fa') or interface.startswith('FastEthernet'):
            return 'FastEthernet'
        elif interface.startswith('Gi') or interface.startswith('GigabitEthernet'):
            return 'GigabitEthernet'
        elif interface.startswith('Se') or interface.startswith('Serial'):
            return 'Serial'
        elif interface.startswith('Lo') or interface.startswith('Loopback'):
            return 'Loopback'
        else:
            return 'other'

    def _trace_rule_matching(self, symptoms: List[Dict]) -> List[Dict]:
        """Trace which rules were considered and why."""
        rule_trace = []

        # Get all matching rules
        all_matching_rules = self.kb.get_matching_rules(symptoms[0], min_confidence=0.0)

        for rule in all_matching_rules:
            rule_analysis = {
                'rule_id': rule.get('id', 'unknown'),
                'rule_description': rule.get('action', {}).get('description', ''),
                'match_score': rule.get('confidence', 0.0),
                'matching_criteria': self._analyze_rule_match(rule, symptoms),
                'applied': True,  # All in this list were considered
                'reason_for_match': self._explain_rule_match(rule, symptoms)
            }
            rule_trace.append(rule_analysis)

        return rule_trace

    def _analyze_rule_match(self, rule: Dict, symptoms: List[Dict]) -> Dict:
        """Analyze why a rule matched the symptoms."""
        condition = rule.get('condition', {})
        required_type = condition.get('problem_type', '')
        required_category = condition.get('category', '')

        matches = []
        for symptom in symptoms:
            symptom_type = symptom.get('type', '')
            symptom_category = symptom.get('category', '')

            if required_type and symptom_type == required_type:
                matches.append(f"type_match: {symptom_type}")
            if required_category and symptom_category == required_category:
                matches.append(f"category_match: {symptom_category}")

        return {
            'matched_symptoms': matches,
            'total_symptoms': len(symptoms),
            'match_strength': len(matches) / len(symptoms) if symptoms else 0
        }

    def _explain_rule_match(self, rule: Dict, symptoms: List[Dict]) -> str:
        """Generate human-readable explanation of rule match."""
        condition = rule.get('condition', {})
        problem_type = condition.get('problem_type', 'any problem')
        category = condition.get('category', 'any category')

        explanation = f"Rule matches {problem_type} problems in {category} category"

        # Add symptom-specific details
        symptom_matches = []
        for symptom in symptoms:
            if symptom.get('type') == problem_type or symptom.get('category') == category:
                symptom_matches.append(f"{symptom.get('type', 'unknown')} on {symptom.get('device', 'unknown')}")

        if symptom_matches:
            explanation += f" based on symptoms: {', '.join(symptom_matches[:3])}"

        return explanation

    def _trace_confidence_propagation(self, symptoms: List[Dict], diagnosis: Dict) -> List[Dict]:
        """Trace how confidence was propagated through the reasoning chain."""
        confidence_trace = []

        # Initial evidence confidence
        for symptom in symptoms:
            confidence_trace.append({
                'stage': 'evidence_collection',
                'item': f"symptom_{symptom.get('type', 'unknown')}",
                'confidence': symptom.get('confidence', 0.8),
                'source': 'direct_detection'
            })

        # Rule application confidence
        rule_id = diagnosis.get('rule_id', '')
        if rule_id and rule_id in self.kb.rules:
            rule = self.kb.rules[rule_id]
            confidence_trace.append({
                'stage': 'rule_application',
                'item': rule_id,
                'confidence': rule.get('confidence', 0.5),
                'source': 'rule_base'
            })

        # Final diagnosis confidence
        confidence_trace.append({
            'stage': 'final_diagnosis',
            'item': diagnosis.get('root_cause', 'unknown'),
            'confidence': diagnosis.get('confidence', 0.0),
            'source': 'combined_evidence'
        })

        return confidence_trace

    def _find_alternative_hypotheses(self, symptoms: List[Dict], diagnosis: Dict) -> List[Dict]:
        """Find alternative hypotheses that were considered."""
        alternatives = []

        # Get all rules that matched
        all_rules = self.kb.get_matching_rules(symptoms[0], min_confidence=0.0)

        winning_rule_id = diagnosis.get('rule_id', '')

        for rule in all_rules:
            rule_id = rule.get('id', '')
            if rule_id != winning_rule_id:
                alternatives.append({
                    'rule_id': rule_id,
                    'description': rule.get('action', {}).get('description', ''),
                    'confidence': rule.get('confidence', 0.0),
                    'why_not_chosen': self._explain_why_not_chosen(rule, diagnosis)
                })

        return alternatives[:5]  # Limit to top 5 alternatives

    def _explain_why_not_chosen(self, alternative_rule: Dict, winning_diagnosis: Dict) -> str:
        """Explain why an alternative rule was not chosen."""
        alt_confidence = alternative_rule.get('confidence', 0.0)
        win_confidence = winning_diagnosis.get('confidence', 0.0)

        if alt_confidence < win_confidence:
            return f"Lower confidence ({alt_confidence:.2f} vs {win_confidence:.2f})"
        else:
            return "Other factors (specificity, recency, etc.)"

    def _build_reasoning_chain(self, trace: Dict) -> List[Dict]:
        """Build a coherent reasoning chain from all trace information."""
        reasoning_steps = []

        # Step 1: Problem identification
        symptoms = trace.get('symptoms', [])
        if symptoms:
            reasoning_steps.append({
                'step': 1,
                'type': 'problem_identification',
                'description': f"Detected {len(symptoms)} symptoms: " +
                              ', '.join([s.get('type', 'unknown') for s in symptoms[:3]]),
                'evidence': [s.get('type', 'unknown') for s in symptoms]
            })

        # Step 2: Evidence evaluation
        evidence_eval = trace.get('evidence_evaluation', [])
        if evidence_eval:
            avg_reliability = sum(e.get('reliability', 0.8) for e in evidence_eval) / len(evidence_eval)
            reasoning_steps.append({
                'step': 2,
                'type': 'evidence_evaluation',
                'description': f"Evaluated evidence reliability: {avg_reliability:.2f} average",
                'evidence': f"{len(evidence_eval)} pieces of evidence collected"
            })

        # Step 3: Rule matching
        rule_apps = trace.get('rule_applications', [])
        if rule_apps:
            top_rules = sorted(rule_apps, key=lambda x: x.get('match_score', 0), reverse=True)[:3]
            reasoning_steps.append({
                'step': 3,
                'type': 'rule_matching',
                'description': f"Matched {len(rule_apps)} rules, top: " +
                              ', '.join([r.get('rule_id', '') for r in top_rules]),
                'evidence': f"Considered {len(rule_apps)} applicable rules"
            })

        # Step 4: Confidence propagation
        confidence_prop = trace.get('confidence_propagation', [])
        if confidence_prop:
            final_confidence = confidence_prop[-1].get('confidence', 0.0) if confidence_prop else 0.0
            reasoning_steps.append({
                'step': 4,
                'type': 'confidence_propagation',
                'description': f"Propagated confidence through reasoning chain: {final_confidence:.2f} final",
                'evidence': f"Confidence evolved through {len(confidence_prop)} stages"
            })

        # Step 5: Diagnosis
        diagnosis = trace.get('diagnosis', {})
        reasoning_steps.append({
            'step': 5,
            'type': 'diagnosis',
            'description': f"Diagnosed: {diagnosis.get('root_cause', 'unknown')} " +
                          f"(confidence: {diagnosis.get('confidence', 0.0):.2f})",
            'evidence': f"Applied rule: {diagnosis.get('rule_id', 'unknown')}"
        })

        return reasoning_steps

    def generate_human_explanation(self, trace: Dict) -> str:
        """
        Generate a human-readable explanation of the diagnosis process.

        Args:
            trace: Reasoning trace from trace_diagnosis_path

        Returns:
            Natural language explanation
        """
        explanation = []

        # Introduction
        symptoms = trace.get('symptoms', [])
        diagnosis = trace.get('diagnosis', {})

        explanation.append("Network Troubleshooting Diagnosis Explanation")
        explanation.append("=" * 50)
        explanation.append("")

        # Problem description
        explanation.append("PROBLEM IDENTIFIED:")
        for symptom in symptoms:
            explanation.append(f"  - {symptom.get('type', 'Unknown issue')} detected on " +
                             f"{symptom.get('device', 'unknown device')} " +
                             f"{symptom.get('interface', '')}")

        explanation.append("")

        # Reasoning process
        reasoning_steps = trace.get('reasoning_steps', [])
        explanation.append("REASONING PROCESS:")
        for step in reasoning_steps:
            explanation.append(f"{step['step']}. {step['description']}")

        explanation.append("")

        # Evidence evaluation
        evidence_eval = trace.get('evidence_evaluation', [])
        if evidence_eval:
            explanation.append("EVIDENCE RELIABILITY:")
            for evidence in evidence_eval[:3]:  # Show top 3
                reliability = evidence.get('reliability', 0.8)
                symptom = evidence.get('symptom', {})
                explanation.append(f"  - {symptom.get('type', 'Unknown')}: " +
                                 f"{reliability:.1%} reliable")
            explanation.append("")

        # Alternatives considered
        alternatives = trace.get('alternative_hypotheses', [])
        if alternatives:
            explanation.append("ALTERNATIVE HYPOTHESES CONSIDERED:")
            for alt in alternatives[:3]:
                explanation.append(f"  - {alt.get('description', 'Unknown')} " +
                                 f"(confidence: {alt.get('confidence', 0.0):.2f})")
                explanation.append(f"    Reason not chosen: {alt.get('why_not_chosen', 'Unknown')}")
            explanation.append("")

        # Final diagnosis
        explanation.append("FINAL DIAGNOSIS:")
        explanation.append(f"Root Cause: {diagnosis.get('root_cause', 'Unknown')}")
        explanation.append(f"Confidence: {diagnosis.get('confidence', 0.0):.1%}")
        explanation.append(f"Recommended Action: {diagnosis.get('suggested_action', 'Investigate further')}")

        return '\n'.join(explanation)


class ConfidenceTuner:
    """
    Automatically tunes confidence thresholds based on historical performance.

    Adapts thresholds to optimize:
    - True positive rate
    - False positive rate
    - Overall diagnostic accuracy
    """

    def __init__(self, knowledge_base):
        self.kb = knowledge_base
        self.performance_history = []
        self.current_thresholds = {
            'min_confidence': 0.5,
            'high_confidence': 0.8,
            'critical_confidence': 0.9
        }

    def tune_thresholds(self, recent_performance: List[Dict]) -> Dict:
        """
        Tune confidence thresholds based on recent performance data.

        Args:
            recent_performance: List of recent diagnosis outcomes

        Returns:
            Updated thresholds and tuning analysis
        """
        if not recent_performance:
            return {'thresholds': self.current_thresholds, 'changes': 'none'}

        # Analyze performance at different threshold levels
        threshold_analysis = self._analyze_threshold_performance(recent_performance)

        # Find optimal thresholds
        optimal_thresholds = self._find_optimal_thresholds(threshold_analysis)

        # Update thresholds gradually (don't change too drastically)
        updated_thresholds = self._smooth_threshold_updates(optimal_thresholds)

        changes = self._calculate_threshold_changes(updated_thresholds)

        self.current_thresholds = updated_thresholds

        return {
            'thresholds': updated_thresholds,
            'changes': changes,
            'analysis': threshold_analysis,
            'optimal_found': optimal_thresholds
        }

    def _analyze_threshold_performance(self, performance_data: List[Dict]) -> Dict:
        """Analyze how different thresholds perform."""
        thresholds_to_test = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

        analysis = {}

        for threshold in thresholds_to_test:
            # Filter diagnoses above threshold
            high_conf_diagnoses = [
                p for p in performance_data
                if p.get('diagnosis_confidence', 0) >= threshold
            ]

            if not high_conf_diagnoses:
                analysis[threshold] = {
                    'true_positives': 0,
                    'false_positives': 0,
                    'precision': 0.0,
                    'recall': 0.0,
                    'f1_score': 0.0
                }
                continue

            # Calculate performance metrics
            true_positives = sum(1 for p in high_conf_diagnoses if p.get('correct_diagnosis', False))
            false_positives = len(high_conf_diagnoses) - true_positives

            # Precision: Of high-confidence diagnoses, how many were correct?
            precision = true_positives / len(high_conf_diagnoses) if high_conf_diagnoses else 0.0

            # Recall: Of all correct diagnoses, how many had high confidence?
            total_correct = sum(1 for p in performance_data if p.get('correct_diagnosis', False))
            recall = true_positives / total_correct if total_correct > 0 else 0.0

            # F1 Score
            f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

            analysis[threshold] = {
                'true_positives': true_positives,
                'false_positives': false_positives,
                'precision': precision,
                'recall': recall,
                'f1_score': f1_score,
                'total_diagnoses': len(high_conf_diagnoses)
            }

        return analysis

    def _find_optimal_thresholds(self, analysis: Dict) -> Dict:
        """Find optimal thresholds based on performance analysis."""
        # Find threshold with best F1 score for min_confidence
        best_f1_threshold = max(analysis.keys(), key=lambda t: analysis[t]['f1_score'])

        # Set high_confidence as threshold with precision >= 0.8
        high_conf_candidates = [
            t for t, metrics in analysis.items()
            if metrics['precision'] >= 0.8 and metrics['total_diagnoses'] >= 5
        ]
        high_conf_threshold = max(high_conf_candidates) if high_conf_candidates else 0.8

        # Set critical_confidence as threshold with precision >= 0.9
        critical_candidates = [
            t for t, metrics in analysis.items()
            if metrics['precision'] >= 0.9 and metrics['total_diagnoses'] >= 3
        ]
        critical_threshold = max(critical_candidates) if critical_candidates else 0.9

        return {
            'min_confidence': best_f1_threshold,
            'high_confidence': high_conf_threshold,
            'critical_confidence': critical_threshold
        }

    def _smooth_threshold_updates(self, optimal_thresholds: Dict) -> Dict:
        """Smooth threshold updates to avoid drastic changes."""
        updated = {}

        for threshold_name, optimal_value in optimal_thresholds.items():
            current_value = self.current_thresholds.get(threshold_name, 0.5)

            # Limit change to maximum of 0.1 per tuning cycle
            max_change = 0.1
            change = optimal_value - current_value
            change = max(-max_change, min(max_change, change))

            updated[threshold_name] = current_value + change

        return updated

    def _calculate_threshold_changes(self, new_thresholds: Dict) -> Dict:
        """Calculate what changed in thresholds."""
        changes = {}

        for name, new_value in new_thresholds.items():
            old_value = self.current_thresholds.get(name, 0.5)
            if abs(new_value - old_value) > 0.01:  # Significant change
                changes[name] = {
                    'old': old_value,
                    'new': new_value,
                    'change': new_value - old_value
                }

        return changes


class HistoricalTrendAnalyzer:
    """
    Analyzes historical trends to identify recurring problem patterns.

    Detects:
    - Seasonal patterns
    - Time-of-day patterns
    - Device-specific trends
    - Protocol-specific issues
    """

    def __init__(self):
        self.trends = {}
        self.patterns = []

    def analyze_trends(self, problem_history: List[Dict], time_window_days: int = 30) -> Dict:
        """
        Analyze historical trends in problem data.

        Args:
            problem_history: List of historical problems
            time_window_days: Analysis window in days

        Returns:
            Dictionary with trend analysis
        """
        if not problem_history:
            return {'trends': {}, 'patterns': [], 'insights': []}

        # Filter recent problems
        cutoff_date = datetime.now() - timedelta(days=time_window_days)
        recent_problems = [
            p for p in problem_history
            if p.get('timestamp') and datetime.fromisoformat(p['timestamp']) > cutoff_date
        ]

        trends = {
            'daily_patterns': self._analyze_daily_patterns(recent_problems),
            'device_trends': self._analyze_device_trends(recent_problems),
            'protocol_trends': self._analyze_protocol_trends(recent_problems),
            'severity_trends': self._analyze_severity_trends(recent_problems),
            'time_window_days': time_window_days,
            'total_problems_analyzed': len(recent_problems)
        }

        # Generate insights
        insights = self._generate_trend_insights(trends)

        return {
            'trends': trends,
            'patterns': self.patterns,
            'insights': insights,
            'analysis_period': f"{time_window_days} days"
        }

    def _analyze_daily_patterns(self, problems: List[Dict]) -> Dict:
        """Analyze daily occurrence patterns."""
        hourly_counts = defaultdict(int)
        daily_counts = defaultdict(int)

        for problem in problems:
            try:
                timestamp = problem.get('timestamp', '')
                if timestamp:
                    dt = datetime.fromisoformat(timestamp)
                    hourly_counts[dt.hour] += 1
                    daily_counts[dt.weekday()] += 1  # 0=Monday, 6=Sunday
            except:
                continue

        # Find peak hours
        peak_hour = max(hourly_counts.keys(), key=lambda h: hourly_counts[h]) if hourly_counts else None
        peak_day = max(daily_counts.keys(), key=lambda d: daily_counts[d]) if daily_counts else None

        return {
            'hourly_distribution': dict(hourly_counts),
            'daily_distribution': dict(daily_counts),
            'peak_hour': peak_hour,
            'peak_day': peak_day,
            'peak_hour_count': hourly_counts.get(peak_hour, 0) if peak_hour is not None else 0,
            'peak_day_count': daily_counts.get(peak_day, 0) if peak_day is not None else 0
        }

    def _analyze_device_trends(self, problems: List[Dict]) -> Dict:
        """Analyze device-specific problem trends."""
        device_problems = defaultdict(list)

        for problem in problems:
            device = problem.get('device', 'unknown')
            device_problems[device].append(problem)

        device_stats = {}
        for device, probs in device_problems.items():
            problem_types = Counter(p.get('type', 'unknown') for p in probs)
            categories = Counter(p.get('category', 'unknown') for p in probs)

            device_stats[device] = {
                'total_problems': len(probs),
                'problem_types': dict(problem_types.most_common(3)),
                'categories': dict(categories.most_common(3)),
                'success_rate': sum(1 for p in probs if p.get('success', False)) / len(probs) if probs else 0
            }

        return device_stats

    def _analyze_protocol_trends(self, problems: List[Dict]) -> Dict:
        """Analyze protocol-specific trends."""
        protocol_problems = defaultdict(list)

        for problem in problems:
            category = problem.get('category', 'unknown')
            protocol_problems[category].append(problem)

        protocol_stats = {}
        for protocol, probs in protocol_problems.items():
            problem_types = Counter(p.get('type', 'unknown') for p in probs)

            protocol_stats[protocol] = {
                'total_problems': len(probs),
                'problem_types': dict(problem_types.most_common(3)),
                'avg_confidence': sum(p.get('confidence', 0.5) for p in probs) / len(probs) if probs else 0,
                'success_rate': sum(1 for p in probs if p.get('success', False)) / len(probs) if probs else 0
            }

        return protocol_stats

    def _analyze_severity_trends(self, problems: List[Dict]) -> Dict:
        """Analyze problem severity trends."""
        severity_counts = Counter(p.get('severity', 'medium') for p in problems)

        # Calculate severity distribution
        total = len(problems)
        severity_distribution = {
            level: {
                'count': count,
                'percentage': count / total * 100 if total > 0 else 0
            }
            for level, count in severity_counts.items()
        }

        return severity_distribution

    def _generate_trend_insights(self, trends: Dict) -> List[str]:
        """Generate actionable insights from trend analysis."""
        insights = []

        # Daily pattern insights
        daily_patterns = trends.get('daily_patterns', {})
        if daily_patterns.get('peak_hour') is not None:
            peak_hour = daily_patterns['peak_hour']
            peak_count = daily_patterns['peak_hour_count']
            insights.append(f"Peak problem hour: {peak_hour}:00 with {peak_count} issues")

        # Device-specific insights
        device_trends = trends.get('device_trends', {})
        for device, stats in device_trends.items():
            if stats['total_problems'] >= 5:
                top_problem = list(stats['problem_types'].keys())[0] if stats['problem_types'] else 'unknown'
                insights.append(f"Device {device}: {stats['total_problems']} issues, mainly {top_problem}")

        # Protocol insights
        protocol_trends = trends.get('protocol_trends', {})
        for protocol, stats in protocol_trends.items():
            if stats['success_rate'] < 0.7 and stats['total_problems'] >= 3:
                insights.append(f"{protocol.upper()} protocol: Low success rate ({stats['success_rate']:.1%})")

        # Severity insights
        severity_trends = trends.get('severity_trends', {})
        critical_pct = severity_trends.get('critical', {}).get('percentage', 0)
        if critical_pct > 20:
            insights.append(f"High critical issue rate: {critical_pct:.1f}% of problems")

        return insights


class AuditLogger:
    """
    Logs all knowledge base modifications and fix applications for audit purposes.

    Tracks:
    - Rule additions/modifications/deletions
    - Fix applications and outcomes
    - System configuration changes
    - User actions
    """

    def __init__(self, log_file: str = "kb_audit.log"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_action(self, action_type: str, details: Dict, user: str = "system") -> None:
        """
        Log an auditable action.

        Args:
            action_type: Type of action (rule_add, rule_delete, fix_apply, etc.)
            details: Action details
            user: User performing the action
        """
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'action_type': action_type,
            'user': user,
            'details': details,
            'session_id': details.get('session_id', 'unknown')
        }

        # Append to log file
        with open(self.log_file, 'a') as f:
            json.dump(log_entry, f)
            f.write('\n')

    def get_audit_trail(self, start_date: datetime = None, end_date: datetime = None,
                       action_types: List[str] = None) -> List[Dict]:
        """
        Retrieve audit trail for specified criteria.

        Args:
            start_date: Start date for filtering
            end_date: End date for filtering
            action_types: List of action types to include

        Returns:
            List of matching audit entries
        """
        if not self.log_file.exists():
            return []

        audit_trail = []

        with open(self.log_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    entry_time = datetime.fromisoformat(entry['timestamp'])

                    # Apply filters
                    if start_date and entry_time < start_date:
                        continue
                    if end_date and entry_time > end_date:
                        continue
                    if action_types and entry['action_type'] not in action_types:
                        continue

                    audit_trail.append(entry)
                except (json.JSONDecodeError, KeyError):
                    continue

        return audit_trail

    def generate_audit_report(self, days: int = 7) -> Dict:
        """
        Generate an audit report for the specified period.

        Args:
            days: Number of days to include in report

        Returns:
            Dictionary with audit statistics
        """
        start_date = datetime.now() - timedelta(days=days)
        audit_trail = self.get_audit_trail(start_date=start_date)

        # Analyze audit data
        action_counts = Counter(entry['action_type'] for entry in audit_trail)
        user_activity = Counter(entry['user'] for entry in audit_trail)

        # Daily activity
        daily_activity = defaultdict(int)
        for entry in audit_trail:
            date = datetime.fromisoformat(entry['timestamp']).date()
            daily_activity[str(date)] += 1

        return {
            'period_days': days,
            'total_actions': len(audit_trail),
            'action_breakdown': dict(action_counts),
            'user_activity': dict(user_activity),
            'daily_activity': dict(daily_activity),
            'most_active_user': user_activity.most_common(1)[0][0] if user_activity else 'none',
            'most_common_action': action_counts.most_common(1)[0][0] if action_counts else 'none'
        }


class BackupManager:
    """
    Manages automatic backup and recovery of knowledge base state.

    Features:
    - Scheduled backups
    - Incremental backups
    - Recovery from backup
    - Backup validation
    """

    def __init__(self, backup_dir: str = "backups", knowledge_base=None):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.kb = knowledge_base

    def create_backup(self, backup_type: str = "full") -> str:
        """
        Create a backup of the knowledge base.

        Args:
            backup_type: Type of backup ('full', 'incremental')

        Returns:
            Path to created backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"kb_backup_{backup_type}_{timestamp}.json"

        backup_path = self.backup_dir / backup_filename

        if self.kb:
            # Export current KB state
            backup_data = self.kb.export_knowledge()
            backup_path = Path(backup_data)  # export_knowledge returns the path
        else:
            # Create empty backup structure
            backup_data = {
                'timestamp': datetime.now().isoformat(),
                'type': backup_type,
                'data': {}
            }

            with open(backup_path, 'w') as f:
                json.dump(backup_data, f, indent=2)

        return str(backup_path)

    def restore_backup(self, backup_path: str) -> bool:
        """
        Restore knowledge base from backup.

        Args:
            backup_path: Path to backup file

        Returns:
            True if restoration successful
        """
        backup_file = Path(backup_path)

        if not backup_file.exists():
            print(f"Backup file not found: {backup_path}")
            return False

        try:
            with open(backup_file, 'r') as f:
                backup_data = json.load(f)

            if self.kb:
                # Restore to knowledge base
                self.kb.import_knowledge(backup_path)
                print(f"Successfully restored KB from {backup_path}")
                return True
            else:
                print("No knowledge base instance to restore to")
                return False

        except Exception as e:
            print(f"Error restoring backup: {e}")
            return False

    def list_backups(self) -> List[Dict]:
        """
        List available backups.

        Returns:
            List of backup information
        """
        backups = []

        for backup_file in self.backup_dir.glob("kb_backup_*.json"):
            try:
                with open(backup_file, 'r') as f:
                    data = json.load(f)

                backup_info = {
                    'filename': backup_file.name,
                    'path': str(backup_file),
                    'timestamp': data.get('timestamp', 'unknown'),
                    'type': data.get('type', 'unknown'),
                    'size_mb': backup_file.stat().st_size / (1024 * 1024)
                }
                backups.append(backup_info)
            except:
                # If we can't read the backup, still list it
                backups.append({
                    'filename': backup_file.name,
                    'path': str(backup_file),
                    'timestamp': 'unknown',
                    'type': 'unknown',
                    'size_mb': backup_file.stat().st_size / (1024 * 1024)
                })

        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        return backups

    def cleanup_old_backups(self, keep_days: int = 30, keep_count: int = 10) -> int:
        """
        Clean up old backups.

        Args:
            keep_days: Keep backups from last N days
            keep_count: Keep at least N most recent backups

        Returns:
            Number of backups deleted
        """
        backups = self.list_backups()
        deleted_count = 0

        if len(backups) <= keep_count:
            return 0  # Keep all if we have fewer than the minimum

        cutoff_date = datetime.now() - timedelta(days=keep_days)

        for backup in backups[keep_count:]:  # Skip the most recent keep_count
            try:
                backup_time = datetime.fromisoformat(backup['timestamp'])
                if backup_time < cutoff_date:
                    backup_path = Path(backup['path'])
                    backup_path.unlink()
                    deleted_count += 1
                    print(f"Deleted old backup: {backup['filename']}")
            except:
                continue

        return deleted_count


class DataRetentionManager:
    """
    Manages data retention policies for problem history and logs.

    Features:
    - Automatic cleanup of old data
    - Configurable retention periods
    - Archival of historical data
    """

    def __init__(self, knowledge_base, retention_days: int = 365):
        self.kb = knowledge_base
        self.retention_days = retention_days
        self.archive_dir = Path("archives")
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def apply_retention_policy(self) -> Dict:
        """
        Apply data retention policy to clean up old data.

        Returns:
            Dictionary with cleanup statistics
        """
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)

        # Clean problem history
        original_count = len(self.kb.problem_history)
        self.kb.problem_history = [
            entry for entry in self.kb.problem_history
            if not entry.get('timestamp') or
               datetime.fromisoformat(entry['timestamp']) > cutoff_date
        ]
        history_cleaned = original_count - len(self.kb.problem_history)

        # Archive old data before deletion
        archived_data = self._archive_old_data(cutoff_date)

        # Clean rule statistics (remove stats for deleted problems)
        stats_cleaned = self._cleanup_rule_statistics()

        return {
            'retention_days': self.retention_days,
            'cutoff_date': cutoff_date.isoformat(),
            'history_entries_cleaned': history_cleaned,
            'archived_entries': len(archived_data),
            'rule_stats_cleaned': stats_cleaned,
            'archive_file': str(self.archive_dir / f"archived_{cutoff_date.strftime('%Y%m%d')}.json")
        }

    def _archive_old_data(self, cutoff_date: datetime) -> List[Dict]:
        """Archive old problem history before deletion."""
        old_entries = [
            entry for entry in self.kb.problem_history
            if entry.get('timestamp') and
               datetime.fromisoformat(entry['timestamp']) <= cutoff_date
        ]

        if old_entries:
            archive_file = self.archive_dir / f"archived_{cutoff_date.strftime('%Y%m%d')}.json"

            archive_data = {
                'archived_date': datetime.now().isoformat(),
                'cutoff_date': cutoff_date.isoformat(),
                'retention_days': self.retention_days,
                'entries': old_entries
            }

            with open(archive_file, 'w') as f:
                json.dump(archive_data, f, indent=2)

        return old_entries

    def _cleanup_rule_statistics(self) -> int:
        """Clean up rule statistics for rules that no longer exist."""
        cleaned_count = 0

        # Remove stats for rules that don't exist
        existing_rule_ids = set(self.kb.rules.keys())
        for rule_id in list(self.kb.rule_stats.keys()):
            if rule_id not in existing_rule_ids:
                del self.kb.rule_stats[rule_id]
                cleaned_count += 1

        return cleaned_count

    def set_retention_policy(self, days: int) -> None:
        """
        Set the data retention policy.

        Args:
            days: Number of days to retain data
        """
        self.retention_days = days
        print(f"Data retention policy set to {days} days")

    def get_retention_status(self) -> Dict:
        """
        Get current retention status.

        Returns:
            Dictionary with retention statistics
        """
        total_entries = len(self.kb.problem_history)
        oldest_entry = None
        newest_entry = None

        for entry in self.kb.problem_history:
            if entry.get('timestamp'):
                entry_time = datetime.fromisoformat(entry['timestamp'])
                if oldest_entry is None or entry_time < oldest_entry:
                    oldest_entry = entry_time
                if newest_entry is None or entry_time > newest_entry:
                    newest_entry = entry_time

        return {
            'retention_days': self.retention_days,
            'total_entries': total_entries,
            'oldest_entry': oldest_entry.isoformat() if oldest_entry else None,
            'newest_entry': newest_entry.isoformat() if newest_entry else None,
            'archive_directory': str(self.archive_dir),
            'archived_files': len(list(self.archive_dir.glob("*.json")))
        }
