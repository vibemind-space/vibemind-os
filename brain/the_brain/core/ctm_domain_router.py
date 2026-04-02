"""
CTM Domain Router - Task Classification for Multi-CTM Ensemble

Routes tasks to specialized CTMs based on cognitive domain analysis.

Domains:
- Spatial: Architecture, infrastructure, topology, dependencies
- Logic: Verification, constraints, validation, compliance
- Temporal: Patterns, scheduling, time-series, sequences
- Value: Decisions, trade-offs, prioritization, optimization

Usage:
    router = CTMDomainRouter()
    result = router.classify_task("Design microservice architecture")
    # result.primary_domain = 'spatial'
    # result.confidence = 0.92
    # result.secondary_domains = []
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from core.shared_enums import CTMDomain


@dataclass
class DomainClassification:
    """
    Result of task domain classification

    Attributes:
        primary_domain: Most relevant CTM domain
        confidence: Confidence score (0-1)
        domain_scores: Scores for all domains
        secondary_domains: Additional relevant domains (for multi-CTM)
        is_mixed_domain: True if multiple domains score high
        reasoning: Explanation of classification
    """
    primary_domain: CTMDomain
    confidence: float
    domain_scores: Dict[CTMDomain, float]
    secondary_domains: List[CTMDomain]
    is_mixed_domain: bool
    reasoning: str


class CTMDomainRouter:
    """
    Task-to-Domain classifier for Multi-CTM Ensemble

    Analyzes task features to determine which specialized CTM(s)
    should handle the reasoning.

    Architecture:
    1. Keyword-based feature extraction
    2. Domain scoring (weighted sum of features)
    3. Confidence thresholding
    4. Multi-domain detection (if multiple domains score high)
    """

    def __init__(
        self,
        mixed_domain_threshold: float = 0.70,  # Threshold for secondary domains
        confidence_min: float = 0.50           # Minimum confidence to classify
    ):
        """
        Initialize CTM Domain Router

        Args:
            mixed_domain_threshold: Score threshold to include secondary domains
            confidence_min: Minimum confidence to make primary classification
        """
        self.mixed_domain_threshold = mixed_domain_threshold
        self.confidence_min = confidence_min

        # Domain keyword patterns
        self._init_domain_keywords()

        print(f"[CTMDomainRouter] Initialized")
        print(f"[CTMDomainRouter] Mixed domain threshold: {mixed_domain_threshold}")
        print(f"[CTMDomainRouter] Confidence minimum: {confidence_min}")

    def _init_domain_keywords(self):
        """Initialize keyword patterns for each domain"""

        # Spatial domain keywords
        self.spatial_keywords = {
            # Architecture
            'architecture': 3.0,
            'microservice': 2.5,
            'microservices': 2.5,
            'infrastructure': 2.5,
            'topology': 3.0,
            'network': 2.0,
            'service mesh': 2.5,
            'dependencies': 2.0,
            'dependency': 2.0,
            'layout': 2.0,
            'structure': 1.5,
            'component': 1.5,
            'graph': 2.0,
            'tree': 1.5,
            'hierarchy': 2.0,
            'layer': 1.5,
            'tier': 1.5,
            'cluster': 2.0,
            'node': 1.5,
            'container': 1.5,
            'orchestration': 2.0,
            'deployment': 1.5,
            'distributed': 2.0,
            'spatial': 3.0,
            'relationship': 1.5,
            # Infrastructure & placement
            'rack': 2.0,
            'gateway': 2.0,
            'namespace': 2.0,
            'sidecar': 2.0,
            'proxy': 1.5,
            'event-driven': 2.0,
            'bounded context': 2.5,
            'schema': 1.5,
            'routing': 2.0,
            'backend': 1.5,
            'frontend': 1.5,
            'multi-tenant': 2.0,
            'placement': 2.5,
            'floor': 1.5,
            'warehouse': 1.5,
            'region': 1.5,
            'data center': 2.5,
        }

        # Logic domain keywords
        self.logic_keywords = {
            # Verification & Constraints
            'validate': 3.0,
            'validation': 3.0,
            'verify': 3.0,
            'verification': 3.0,
            'check': 2.5,
            'constraint': 3.0,
            'constraints': 3.0,
            'rule': 2.5,
            'rules': 2.5,
            'policy': 2.5,
            'policies': 2.5,
            'compliance': 2.5,
            'conform': 2.0,
            'type': 2.0,
            'typing': 2.5,
            'correct': 1.5,
            'correctness': 2.0,
            'proof': 3.0,
            'logic': 3.0,
            'logical': 2.5,
            'boolean': 2.0,
            'condition': 1.5,
            'invariant': 2.5,
            'precondition': 2.5,
            'postcondition': 2.5,
            'assertion': 2.5,
            'security': 2.0,
            'safety': 2.0,
            # Extended logic
            'audit': 2.5,
            'sanitization': 2.5,
            'injection': 2.5,
            'vulnerability': 2.0,
            'certificate': 2.0,
            'cors': 2.5,
            'hipaa': 2.5,
            'gdpr': 2.5,
            'consent': 2.0,
            'contract': 2.0,
            'mock': 1.5,
            'deadlock': 2.5,
            'nullable': 2.0,
            'generic': 1.5,
            'coverage': 2.0,
            'property-based': 2.5,
            'static': 1.5,
            'syntax': 2.0,
            'semantic': 2.0,
        }

        # Temporal domain keywords
        self.temporal_keywords = {
            # Time & Patterns
            'timeout': 3.0,
            'schedule': 3.0,
            'scheduling': 3.0,
            'periodic': 2.5,
            'pattern': 2.0,
            'patterns': 2.0,
            'time-series': 3.0,
            'timeseries': 3.0,
            'sequence': 2.5,
            'sequential': 2.5,
            'rhythm': 2.0,
            'cadence': 2.0,
            'temporal': 3.0,
            'time': 1.5,
            'timing': 2.0,
            'duration': 2.0,
            'interval': 2.0,
            'delay': 2.0,
            'latency': 2.0,
            'deadline': 2.5,
            'cycle': 2.0,
            'frequency': 2.0,
            'auto-scaling': 2.5,
            'autoscaling': 2.5,
            'trigger': 2.0,
            'event': 1.5,
            'anomaly': 2.5,
            'detection': 1.5,
            # Extended temporal
            'forecast': 3.0,
            'predict': 2.5,
            'spike': 2.5,
            'spikes': 2.5,
            'metrics': 2.0,
            'log': 1.5,
            'logs': 1.5,
            'alert': 2.5,
            'alerting': 2.5,
            'threshold': 2.0,
            'baseline': 2.5,
            'seasonality': 3.0,
            'degradation': 2.5,
            'burn rate': 3.0,
            'slo': 2.5,
            'flapping': 2.5,
            'change-point': 3.0,
            'correlation': 2.0,
            'correlated': 2.0,
            'cron': 2.5,
            'batch': 2.0,
            'window': 1.5,
            'percentile': 2.0,
            'garbage collection': 2.5,
            'memory leak': 2.5,
            'heap': 2.0,
            'profil': 2.0,
            'traffic': 1.5,
            'peak': 2.0,
        }

        # Value domain keywords
        self.value_keywords = {
            # Decisions & Optimization
            'decide': 3.0,
            'decision': 3.0,
            'prioritize': 3.0,
            'priority': 2.5,
            'trade-off': 3.0,
            'tradeoff': 3.0,
            'trade-offs': 3.0,
            'allocate': 2.5,
            'allocation': 2.5,
            'optimize': 3.0,
            'optimization': 3.0,
            'optimal': 2.5,
            'resource': 2.0,
            'resources': 2.0,
            'cost': 2.5,
            'benefit': 2.5,
            'risk': 2.5,
            'reward': 2.0,
            'utility': 2.5,
            'value': 2.0,
            'objective': 2.0,
            'goal': 1.5,
            'strategy': 2.0,
            'strategic': 2.0,
            'choose': 2.0,
            'select': 2.0,
            'selection': 2.0,
            'prefer': 1.5,
            'preference': 2.0,
            'balance': 2.0,
            # Extended value
            'budget': 2.5,
            'spending': 2.5,
            'savings': 2.5,
            'triage': 2.5,
            'severity': 2.5,
            'impact': 2.5,
            'effort': 2.5,
            'rank': 2.0,
            'ranking': 2.0,
            'evaluate': 2.0,
            'comparison': 2.0,
            'compare': 2.0,
            'build vs buy': 3.0,
            'technical debt': 2.5,
            'pareto': 3.0,
            'multi-objective': 3.0,
            'reserved': 1.5,
            'on-demand': 1.5,
            'spot instance': 2.5,
            'instance type': 2.0,
            'egress': 2.0,
            'cdn': 1.5,
            'feature': 1.0,
            'mvp': 2.0,
            'eviction': 2.0,
            'cache': 1.5,
            'hit rate': 2.0,
            'throughput': 1.5,
            'reliability': 1.5,
            'speed': 1.5,
            'performance': 1.5,
            # Choice & comparison
            'monolith': 2.0,
            'vs': 2.0,
            'reduce': 1.5,
            'minimize': 2.0,
            'maximize': 2.0,
            'tiering': 2.5,
            'storage': 1.5,
            'compute': 1.5,
            'consistency': 1.5,
            'availability': 1.5,
            'velocity': 2.0,
            'payoff': 2.5,
            'exploitability': 2.5,
        }

    def classify_task(self, task: str) -> DomainClassification:
        """
        Classify task into CTM domain(s)

        Args:
            task: Task description string

        Returns:
            DomainClassification with primary domain and confidence
        """
        # Compute domain scores
        domain_scores = self._compute_domain_scores(task)

        # Find primary domain
        primary_domain = max(domain_scores.items(), key=lambda x: x[1])[0]
        confidence = domain_scores[primary_domain]

        # Find secondary domains (for mixed-domain tasks)
        secondary_domains = [
            domain for domain, score in domain_scores.items()
            if domain != primary_domain and score >= self.mixed_domain_threshold
        ]

        is_mixed_domain = len(secondary_domains) > 0

        # Generate reasoning
        reasoning = self._generate_reasoning(
            task, domain_scores, primary_domain, secondary_domains
        )

        # Warn if confidence too low
        if confidence < self.confidence_min:
            print(f"[CTMDomainRouter] WARNING: Low confidence {confidence:.2f} for task: {task[:50]}...")
            print(f"[CTMDomainRouter] Defaulting to SpatialCTM (most general)")
            primary_domain = CTMDomain.SPATIAL

        return DomainClassification(
            primary_domain=primary_domain,
            confidence=confidence,
            domain_scores=domain_scores,
            secondary_domains=secondary_domains,
            is_mixed_domain=is_mixed_domain,
            reasoning=reasoning
        )

    def _compute_domain_scores(self, task: str) -> Dict[CTMDomain, float]:
        """
        Compute scores for each domain based on keyword matching

        Args:
            task: Task description

        Returns:
            Dict mapping CTMDomain to score (0-1)
        """
        task_lower = task.lower()

        # Score each domain
        spatial_score = self._score_keywords(task_lower, self.spatial_keywords)
        logic_score = self._score_keywords(task_lower, self.logic_keywords)
        temporal_score = self._score_keywords(task_lower, self.temporal_keywords)
        value_score = self._score_keywords(task_lower, self.value_keywords)

        # Normalize to 0-1 scale
        scores = {
            CTMDomain.SPATIAL: spatial_score,
            CTMDomain.LOGIC: logic_score,
            CTMDomain.TEMPORAL: temporal_score,
            CTMDomain.VALUE: value_score
        }

        # Normalize by max score (or use sigmoid for soft scores)
        max_score = max(scores.values())
        if max_score > 0:
            scores = {
                domain: self._sigmoid(score / max_score)
                for domain, score in scores.items()
            }
        else:
            # No keywords matched - default to spatial (most general)
            scores = {
                CTMDomain.SPATIAL: 0.5,
                CTMDomain.LOGIC: 0.3,
                CTMDomain.TEMPORAL: 0.3,
                CTMDomain.VALUE: 0.3
            }

        return scores

    def _score_keywords(self, text: str, keywords: Dict[str, float]) -> float:
        """
        Score text based on keyword presence and weights

        Args:
            text: Lowercased text to analyze
            keywords: Dict of keyword -> weight

        Returns:
            Total weighted score
        """
        score = 0.0
        for keyword, weight in keywords.items():
            # Use regex for word boundaries (avoid substring matches)
            pattern = r'\b' + re.escape(keyword) + r'\b'
            matches = len(re.findall(pattern, text))
            score += matches * weight

        return score

    def _sigmoid(self, x: float) -> float:
        """Sigmoid activation for soft scores"""
        import math
        return 1.0 / (1.0 + math.exp(-5 * (x - 0.5)))  # Centered at 0.5

    def _generate_reasoning(
        self,
        task: str,
        domain_scores: Dict[CTMDomain, float],
        primary_domain: CTMDomain,
        secondary_domains: List[CTMDomain]
    ) -> str:
        """
        Generate human-readable reasoning for classification

        Args:
            task: Original task
            domain_scores: Computed scores per domain
            primary_domain: Selected primary domain
            secondary_domains: Additional relevant domains

        Returns:
            Reasoning string
        """
        lines = []

        # Primary domain
        lines.append(
            f"Primary domain: {primary_domain.value} "
            f"(score: {domain_scores[primary_domain]:.2f})"
        )

        # Secondary domains (if any)
        if secondary_domains:
            secondary_str = ", ".join(
                f"{d.value} ({domain_scores[d]:.2f})"
                for d in secondary_domains
            )
            lines.append(f"Secondary domains: {secondary_str}")

        # Detected keywords
        task_lower = task.lower()
        detected_keywords = []

        if primary_domain == CTMDomain.SPATIAL:
            keywords = self.spatial_keywords
        elif primary_domain == CTMDomain.LOGIC:
            keywords = self.logic_keywords
        elif primary_domain == CTMDomain.TEMPORAL:
            keywords = self.temporal_keywords
        else:  # VALUE
            keywords = self.value_keywords

        for keyword in keywords:
            if re.search(r'\b' + re.escape(keyword) + r'\b', task_lower):
                detected_keywords.append(keyword)

        if detected_keywords:
            lines.append(f"Detected keywords: {', '.join(detected_keywords[:5])}")

        return " | ".join(lines)

    def get_recommended_ctms(
        self,
        classification: DomainClassification
    ) -> List[CTMDomain]:
        """
        Get list of CTMs to invoke for this task

        Args:
            classification: DomainClassification result

        Returns:
            List of CTM domains to invoke (primary + secondary)
        """
        ctms = [classification.primary_domain]

        if classification.is_mixed_domain:
            ctms.extend(classification.secondary_domains)

        return ctms


if __name__ == "__main__":
    # Test CTM Domain Router
    print("="*70)
    print("Testing CTM Domain Router")
    print("="*70)

    router = CTMDomainRouter(
        mixed_domain_threshold=0.70,
        confidence_min=0.50
    )

    # Test cases
    test_tasks = [
        # Pure spatial
        "Design microservice architecture with service mesh",

        # Pure logic
        "Validate Kubernetes manifest against security policies",

        # Pure temporal
        "Detect anomalies in time-series metrics from production logs",

        # Pure value
        "Optimize resource allocation with cost and performance trade-offs",

        # Mixed: Spatial + Logic
        "Deploy distributed system with fault tolerance constraints",

        # Mixed: Spatial + Temporal + Value
        "Design auto-scaling architecture with cost optimization",

        # Ambiguous (low confidence)
        "Help me with the thing",
    ]

    for i, task in enumerate(test_tasks, 1):
        print(f"\n{'='*70}")
        print(f"Test {i}: {task}")
        print('='*70)

        classification = router.classify_task(task)

        print(f"\nPrimary Domain: {classification.primary_domain.value}")
        print(f"Confidence: {classification.confidence:.2f}")
        print(f"Mixed Domain: {classification.is_mixed_domain}")

        print(f"\nDomain Scores:")
        for domain, score in sorted(
            classification.domain_scores.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            print(f"  {domain.value}: {score:.3f}")

        if classification.secondary_domains:
            print(f"\nSecondary Domains:")
            for domain in classification.secondary_domains:
                print(f"  - {domain.value}")

        print(f"\nReasoning: {classification.reasoning}")

        recommended_ctms = router.get_recommended_ctms(classification)
        print(f"\nRecommended CTMs: {[ctm.value for ctm in recommended_ctms]}")

    print("\n" + "="*70)
    print("CTM Domain Router Test Complete!")
    print("="*70)
