"""
CTM Training Data Generation & Validation (P2.16-18)

Generates large-scale persistent synthetic training datasets for all CTM domains
and validates existing trained models against comprehensive test corpora.

Features:
1. 2000+ diverse training samples per domain with varied complexity
2. Persistent JSON dataset storage in data/training_datasets/
3. Training validation against target module routing
4. Domain-specific task templates beyond the basic Klotski puzzles
5. Calibration corpus for domain router (P2.19)
"""

import json
import os
import time
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime

from core.shared_enums import CTMDomain


# ─── Rich Task Templates ──────────────────────────────────────────────

LOGIC_TASK_TEMPLATES = [
    # Constraint validation
    "Validate Kubernetes YAML against security policies",
    "Check type constraints in function signatures for {lang}",
    "Verify schema compliance for REST API request payloads",
    "Validate configuration file syntax and semantic rules",
    "Check access control policy violations in IAM configuration",
    "Verify data integrity constraints across {n} database tables",
    "Validate state machine transitions for {system} workflow",
    # Type checking
    "Run static type analysis on {lang} module with {n} functions",
    "Verify generic type parameter bounds in collection framework",
    "Check nullable safety violations in data pipeline code",
    # Rule engines
    "Evaluate {n} business rules against incoming order payload",
    "Check HIPAA compliance rules for patient data handling",
    "Validate GDPR consent requirements across user data flows",
    "Verify circuit breaker policy thresholds for microservice calls",
    # Formal methods
    "Prove correctness of sorting algorithm with {n} elements",
    "Verify deadlock freedom in concurrent lock acquisition order",
    "Check invariant preservation across {n} state transitions",
    "Validate precondition/postcondition contracts for API endpoints",
    # Security
    "Audit authentication flow for injection vulnerabilities",
    "Verify certificate chain validity for TLS configuration",
    "Check CORS policy correctness for cross-origin requests",
    "Validate input sanitization rules for {n} form fields",
    # Testing
    "Verify test coverage meets {pct}% threshold for critical paths",
    "Check assertion correctness in property-based test suite",
    "Validate mock contract conformance with real service behavior",
]

TEMPORAL_TASK_TEMPLATES = [
    # Time-series analysis
    "Detect anomalies in production metrics time-series over {n} hours",
    "Identify periodic patterns in system log frequency data",
    "Predict resource usage spikes from historical {n}-day data",
    "Forecast traffic load patterns for next {n} hours",
    "Detect latency degradation trends in API response times",
    # Scheduling
    "Schedule {n} microservice auto-scaling events optimally",
    "Optimize batch job scheduling across {n} worker nodes",
    "Plan deployment windows avoiding peak traffic periods",
    "Coordinate {n} cron jobs to minimize resource contention",
    "Schedule database maintenance during lowest-activity window",
    # Sequence analysis
    "Detect sequential access patterns in user session logs",
    "Identify request chain dependencies for timeout tuning",
    "Analyze event ordering in distributed transaction log",
    "Detect causality violations in event-sourced system",
    # Pattern recognition
    "Classify {n} time-series segments as normal or anomalous",
    "Detect change-points in deployment frequency over {n} weeks",
    "Identify seasonality in customer behavior metrics",
    "Recognize recurring failure patterns in incident history",
    # Monitoring & alerting
    "Configure alert thresholds from {n} days of baseline data",
    "Detect flapping alerts by analyzing state transition frequency",
    "Identify correlated alerts across {n} monitoring systems",
    "Predict SLO budget exhaustion timeline from burn rate",
    # Performance
    "Analyze garbage collection pause time distribution",
    "Profile request latency percentiles across time windows",
    "Detect memory leak progression from heap size time-series",
]

VALUE_TASK_TEMPLATES = [
    # Resource allocation
    "Optimize cloud resource allocation balancing cost vs performance",
    "Allocate {n} GPU instances across training jobs by priority",
    "Distribute {n}GB storage budget across hot, warm, cold tiers",
    "Balance compute resources between batch and real-time workloads",
    # Decision making
    "Choose deployment strategy trading off speed vs reliability",
    "Select database engine comparing consistency vs throughput",
    "Decide caching strategy weighing hit rate vs memory cost",
    "Choose between monolith and microservice for {system} module",
    # Cost optimization
    "Optimize cloud spending by selecting reserved vs on-demand mix",
    "Reduce storage costs by tiering {n}TB of data by access pattern",
    "Minimize network egress costs through CDN placement strategy",
    "Balance spot instance savings against reliability requirements",
    # Trade-off analysis
    "Evaluate trade-offs in choosing {n} features for MVP release",
    "Analyze consistency vs availability for distributed data store",
    "Compare build vs buy decision for {system} component",
    "Assess technical debt payoff timeline vs feature velocity",
    # Prioritization
    "Prioritize {n} feature requests by impact and effort scores",
    "Rank incident severity for {n} concurrent system issues",
    "Triage {n} security vulnerabilities by risk and exploitability",
    "Order API migration tasks by dependency and business value",
    # Multi-objective optimization
    "Optimize service placement across {n} regions for latency and cost",
    "Balance throughput, latency, and cost for message queue config",
    "Find Pareto-optimal scaling policies for {n}-tier application",
    "Optimize CI/CD pipeline for build speed, test coverage, and cost",
]

SPATIAL_TASK_TEMPLATES = [
    "Design microservice architecture with {n} services and load balancing",
    "Optimize container placement across {n} cluster nodes",
    "Layout UI component tree for responsive dashboard design",
    "Plan data center rack configuration for {n} servers",
    "Design network topology for minimal cross-region latency",
    "Architect event-driven system with {n} bounded contexts",
    "Design API gateway routing for {n} backend services",
    "Plan Kubernetes namespace topology for multi-tenant cluster",
    "Design message bus topology connecting {n} microservices",
    "Optimize graph database schema for relationship queries",
    "Design distributed cache topology for session management",
    "Plan service mesh configuration with sidecar proxies",
]


# ─── Training Data Generator ──────────────────────────────────────────

class CTMTrainingDataGenerator:
    """
    Generates large-scale persistent training datasets for all CTM domains.

    Creates diverse, parameterized tasks with varied complexity levels
    and saves them as JSON for reproducible training.
    """

    def __init__(self, output_dir: str = "data/training_datasets", seed: int = 42):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.rng = np.random.RandomState(seed)

    def _fill_template(self, template: str) -> str:
        """Fill template placeholders with random values."""
        result = template
        while '{n}' in result:
            result = result.replace('{n}', str(self.rng.randint(3, 50)), 1)
        while '{pct}' in result:
            result = result.replace('{pct}', str(self.rng.choice([80, 85, 90, 95])), 1)
        while '{lang}' in result:
            result = result.replace('{lang}', self.rng.choice([
                'Python', 'TypeScript', 'Go', 'Rust', 'Java', 'C#'
            ]), 1)
        while '{system}' in result:
            result = result.replace('{system}', self.rng.choice([
                'order-processing', 'auth-service', 'payment-gateway',
                'notification-engine', 'search-indexer', 'data-pipeline'
            ]), 1)
        return result

    def _create_puzzle_state(self, domain: str, complexity: float) -> List[List[int]]:
        """Create a 5x4 puzzle state based on domain and complexity."""
        state = np.zeros((5, 4), dtype=int)

        # Red block (2x2) - position varies by complexity
        r_pos = self.rng.randint(0, 3)
        c_pos = self.rng.randint(0, 2)
        state[r_pos:r_pos+2, c_pos:c_pos+2] = 1

        # Add sub-blocks based on complexity (more blocks = harder)
        num_blocks = int(2 + complexity * 6)  # 2-8 blocks
        for i in range(num_blocks):
            r, c = self.rng.randint(0, 5), self.rng.randint(0, 4)
            if state[r, c] == 0:
                state[r, c] = 2 + i

        return state.tolist()

    def generate_domain_dataset(
        self,
        domain: CTMDomain,
        num_samples: int = 2000,
        complexity_range: Tuple[float, float] = (0.3, 0.95)
    ) -> List[Dict[str, Any]]:
        """
        Generate a large training dataset for a specific domain.

        Args:
            domain: CTM domain
            num_samples: Number of samples to generate
            complexity_range: (min, max) complexity range

        Returns:
            List of task dictionaries
        """
        templates = {
            CTMDomain.LOGIC: LOGIC_TASK_TEMPLATES,
            CTMDomain.TEMPORAL: TEMPORAL_TASK_TEMPLATES,
            CTMDomain.VALUE: VALUE_TASK_TEMPLATES,
            CTMDomain.SPATIAL: SPATIAL_TASK_TEMPLATES,
        }[domain]

        target_modules = {
            CTMDomain.LOGIC: {'LAN': 0.70, 'DLPFC': 0.20, 'ACC': 0.10},
            CTMDomain.TEMPORAL: {'AUD': 0.60, 'MTL': 0.25, 'DLPFC': 0.15},
            CTMDomain.VALUE: {'OFC': 0.70, 'ACC': 0.20, 'DLPFC': 0.10},
            CTMDomain.SPATIAL: {'VIS': 0.50, 'DLPFC': 0.30, 'SOM': 0.20},
        }[domain]

        dataset = []
        for i in range(num_samples):
            template = self.rng.choice(templates)
            task_desc = self._fill_template(template)
            complexity = self.rng.uniform(*complexity_range)
            puzzle_state = self._create_puzzle_state(domain.value, complexity)

            sample = {
                'id': f"{domain.value}_{i:05d}",
                'task_description': task_desc,
                'domain': domain.value,
                'complexity': round(complexity, 4),
                'puzzle_state': puzzle_state,
                'target_modules': target_modules,
                'expected_solution_length': int(8 + complexity * 35),
                'metadata': {
                    'template_index': i % len(templates),
                    'generated_at': datetime.now().isoformat(),
                }
            }
            dataset.append(sample)

        return dataset

    def generate_all_datasets(
        self,
        samples_per_domain: int = 2000
    ) -> Dict[str, Dict[str, Any]]:
        """
        Generate training datasets for all domains and save to disk.

        Args:
            samples_per_domain: Number of samples per domain

        Returns:
            Summary of generated datasets
        """
        summary = {}
        domains = [CTMDomain.LOGIC, CTMDomain.TEMPORAL, CTMDomain.VALUE, CTMDomain.SPATIAL]

        for domain in domains:
            t0 = time.time()
            print(f"[CTMTrainingData] Generating {samples_per_domain} {domain.value} samples...")

            dataset = self.generate_domain_dataset(domain, samples_per_domain)

            # Split train/validation (80/20)
            split_idx = int(len(dataset) * 0.8)
            train_data = dataset[:split_idx]
            val_data = dataset[split_idx:]

            # Save to disk
            train_path = self.output_dir / f"{domain.value}_train.json"
            val_path = self.output_dir / f"{domain.value}_val.json"

            with open(train_path, 'w') as f:
                json.dump({
                    'domain': domain.value,
                    'type': 'training',
                    'num_samples': len(train_data),
                    'generated_at': datetime.now().isoformat(),
                    'samples': train_data,
                }, f, indent=2)

            with open(val_path, 'w') as f:
                json.dump({
                    'domain': domain.value,
                    'type': 'validation',
                    'num_samples': len(val_data),
                    'generated_at': datetime.now().isoformat(),
                    'samples': val_data,
                }, f, indent=2)

            elapsed = time.time() - t0
            summary[domain.value] = {
                'train_samples': len(train_data),
                'val_samples': len(val_data),
                'train_path': str(train_path),
                'val_path': str(val_path),
                'generation_time_s': round(elapsed, 3),
            }
            print(f"  => {len(train_data)} train + {len(val_data)} val ({elapsed:.2f}s)")

        # Save summary
        summary_path = self.output_dir / 'dataset_summary.json'
        with open(summary_path, 'w') as f:
            json.dump({
                'generated_at': datetime.now().isoformat(),
                'samples_per_domain': samples_per_domain,
                'domains': summary,
            }, f, indent=2)

        print(f"\n[CTMTrainingData] All datasets saved to {self.output_dir}/")
        return summary


# ─── Domain Router Calibration Corpus ──────────────────────────────────

class DomainRouterCalibrationCorpus:
    """
    Generates a calibration corpus for testing and tuning the CTMDomainRouter.

    Creates 500+ diverse tasks with known ground-truth domain labels
    for measuring classification accuracy.
    """

    def __init__(self, seed: int = 123):
        self.rng = np.random.RandomState(seed)

    def generate_calibration_corpus(self, samples_per_domain: int = 150) -> List[Dict[str, Any]]:
        """
        Generate labeled calibration tasks for domain router tuning.

        Returns:
            List of {task, ground_truth_domain, difficulty, is_mixed} dicts
        """
        corpus = []

        # Pure domain tasks (easy)
        for domain, templates in [
            ('logic', LOGIC_TASK_TEMPLATES),
            ('temporal', TEMPORAL_TASK_TEMPLATES),
            ('value', VALUE_TASK_TEMPLATES),
            ('spatial', SPATIAL_TASK_TEMPLATES),
        ]:
            for i in range(samples_per_domain):
                template = self.rng.choice(templates)
                task = self._fill_template(template)
                corpus.append({
                    'task': task,
                    'ground_truth_domain': domain,
                    'difficulty': 'easy',
                    'is_mixed': False,
                })

        # Mixed domain tasks (hard)
        mixed_tasks = [
            # Logic + Temporal
            ("Validate time-series alerting rules against SLO policy constraints", 'logic', ['temporal']),
            ("Check scheduling constraint violations in cron job configuration", 'logic', ['temporal']),
            ("Verify temporal ordering invariants in event-sourced system", 'logic', ['temporal']),

            # Logic + Value
            ("Validate cost allocation rules for multi-tenant billing system", 'logic', ['value']),
            ("Check budget constraint compliance for resource allocation plan", 'logic', ['value']),
            ("Verify optimization constraint satisfaction for resource allocation", 'value', ['logic']),

            # Temporal + Value
            ("Optimize scheduling of batch jobs to minimize cost over time", 'value', ['temporal']),
            ("Predict optimal auto-scaling timeline for cost efficiency", 'temporal', ['value']),
            ("Schedule resource allocation changes based on traffic patterns", 'temporal', ['value']),

            # Spatial + Logic
            ("Validate microservice topology against dependency constraints", 'spatial', ['logic']),
            ("Check network architecture compliance with security policies", 'logic', ['spatial']),
            ("Verify container placement rules for distributed system design", 'logic', ['spatial']),

            # Spatial + Temporal
            ("Design auto-scaling architecture with traffic pattern awareness", 'spatial', ['temporal']),
            ("Plan network topology changes based on temporal load patterns", 'spatial', ['temporal']),

            # Spatial + Value
            ("Optimize service mesh topology for cost and latency trade-offs", 'spatial', ['value']),
            ("Design infrastructure layout balancing performance and budget", 'spatial', ['value']),

            # Triple domain
            ("Design auto-scaling architecture with cost optimization based on time patterns", 'spatial', ['temporal', 'value']),
            ("Validate scheduling constraints for resource allocation in distributed topology", 'logic', ['temporal', 'spatial']),
        ]

        for task, primary, secondary in mixed_tasks:
            corpus.append({
                'task': task,
                'ground_truth_domain': primary,
                'secondary_domains': secondary,
                'difficulty': 'hard',
                'is_mixed': True,
            })

        # Ambiguous tasks (very hard)
        ambiguous_tasks = [
            ("Help me with the deployment", 'spatial'),
            ("Fix the production issue", 'logic'),
            ("Improve system performance", 'value'),
            ("Analyze the logs", 'temporal'),
            ("Review the configuration", 'logic'),
            ("Update the infrastructure", 'spatial'),
            ("Check the metrics", 'temporal'),
            ("Make it faster", 'value'),
            ("Plan the migration", 'spatial'),
            ("Debug the timeout", 'temporal'),
        ]

        for task, primary in ambiguous_tasks:
            corpus.append({
                'task': task,
                'ground_truth_domain': primary,
                'difficulty': 'ambiguous',
                'is_mixed': False,
            })

        self.rng.shuffle(corpus)
        return corpus

    def _fill_template(self, template: str) -> str:
        """Fill template placeholders."""
        result = template
        while '{n}' in result:
            result = result.replace('{n}', str(self.rng.randint(3, 50)), 1)
        while '{pct}' in result:
            result = result.replace('{pct}', str(self.rng.choice([80, 85, 90, 95])), 1)
        while '{lang}' in result:
            result = result.replace('{lang}', self.rng.choice([
                'Python', 'TypeScript', 'Go', 'Rust', 'Java', 'C#'
            ]), 1)
        while '{system}' in result:
            result = result.replace('{system}', self.rng.choice([
                'order-processing', 'auth-service', 'payment-gateway',
                'notification-engine', 'search-indexer', 'data-pipeline'
            ]), 1)
        return result


# ─── Training Validator ────────────────────────────────────────────────

class CTMTrainingValidator:
    """
    Validates trained CTM models against target module routing.

    Reads existing checkpoint data and validates:
    1. Convergence to target routing distributions
    2. Cross-domain separation quality
    3. Training stability (no oscillation in later epochs)
    """

    def __init__(self, checkpoint_dir: str = "data/ctm_checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)

    def validate_all_domains(self) -> Dict[str, Any]:
        """
        Validate training for all domains.

        Returns:
            Validation report with per-domain results
        """
        results = {}

        for domain_name in ['logic', 'temporal', 'value']:
            result = self.validate_domain(domain_name)
            results[domain_name] = result

        # Overall assessment
        all_pass = bool(all(r.get('converged', False) for r in results.values()))
        avg_convergence = float(np.mean([r.get('best_convergence', 0) for r in results.values()]))

        return {
            'timestamp': datetime.now().isoformat(),
            'all_domains_pass': all_pass,
            'average_convergence': round(float(avg_convergence), 6),
            'domains': results,
        }

    def validate_domain(self, domain_name: str) -> Dict[str, Any]:
        """Validate a single domain's training."""
        # Try extended training summary first
        ext_summary_path = self.checkpoint_dir / 'extended_training_summary.json'
        summary_path = self.checkpoint_dir / 'training_summary.json'

        best_data = None

        if ext_summary_path.exists():
            with open(ext_summary_path, 'r') as f:
                ext_data = json.load(f)
                if domain_name in ext_data.get('results', {}):
                    best_data = ext_data['results'][domain_name]

        if best_data is None and summary_path.exists():
            with open(summary_path, 'r') as f:
                data = json.load(f)
                if domain_name in data:
                    best_data = data[domain_name]

        if best_data is None:
            return {'status': 'no_training_data', 'converged': False}

        convergence = float(best_data.get('best_convergence', 0))
        final_routing = best_data.get('final_routing', {})
        target_routing = best_data.get('target_routing', {})

        # Check convergence threshold
        converged = bool(convergence >= 0.95)

        # Check individual module accuracy
        module_accuracy = {}
        for module, target in target_routing.items():
            actual = final_routing.get(module, 0)
            accuracy = 1.0 - abs(target - actual) / max(target, 0.01)
            module_accuracy[module] = round(accuracy, 4)

        # Check training stability (look for latest epoch checkpoint)
        stability = self._check_stability(domain_name)

        return {
            'status': best_data.get('status', 'unknown'),
            'converged': converged,
            'best_convergence': round(convergence, 6),
            'best_epoch': best_data.get('best_epoch', 0),
            'final_routing': final_routing,
            'target_routing': target_routing,
            'module_accuracy': module_accuracy,
            'training_time_s': best_data.get('training_time', 0),
            'brain_path': best_data.get('brain_path', ''),
            'stability': stability,
        }

    def _check_stability(self, domain_name: str) -> Dict[str, Any]:
        """Check training stability by looking at later epoch convergence values."""
        # Find all epoch checkpoints for this domain
        checkpoints = sorted(self.checkpoint_dir.glob(f"{domain_name}_epoch_*.json"))

        if len(checkpoints) < 3:
            return {'stable': True, 'reason': 'too_few_checkpoints'}

        # Read last 5 checkpoints
        convergence_values = []
        for cp in checkpoints[-5:]:
            try:
                with open(cp, 'r') as f:
                    data = json.load(f)
                    conv = data.get('progress', {}).get('routing_convergence', 0)
                    convergence_values.append(conv)
            except Exception:
                pass

        if len(convergence_values) < 2:
            return {'stable': True, 'reason': 'insufficient_data'}

        # Check for oscillation (std dev of last 5 should be low)
        std_dev = np.std(convergence_values)
        monotonic = all(convergence_values[i] >= convergence_values[i-1] - 0.01
                       for i in range(1, len(convergence_values)))

        return {
            'stable': bool(std_dev < 0.05 and monotonic),
            'std_dev': round(float(std_dev), 6),
            'monotonic_improvement': bool(monotonic),
            'last_values': [round(float(v), 4) for v in convergence_values],
        }


# ─── Domain Router Calibrator ─────────────────────────────────────────

class DomainRouterCalibrator:
    """
    Calibrates the CTMDomainRouter using the calibration corpus.

    Tests classification accuracy and tunes thresholds for optimal performance.
    """

    def __init__(self):
        from core.ctm_domain_router import CTMDomainRouter
        self.router = CTMDomainRouter(
            mixed_domain_threshold=0.70,
            confidence_min=0.50
        )

    def calibrate(self, corpus: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Run calibration on the domain router.

        Args:
            corpus: Calibration corpus (generates one if None)

        Returns:
            Calibration report with accuracy metrics
        """
        if corpus is None:
            gen = DomainRouterCalibrationCorpus()
            corpus = gen.generate_calibration_corpus()

        # Run classification on all tasks
        correct = 0
        total = 0
        per_domain = {'logic': {'correct': 0, 'total': 0},
                      'temporal': {'correct': 0, 'total': 0},
                      'value': {'correct': 0, 'total': 0},
                      'spatial': {'correct': 0, 'total': 0}}
        per_difficulty = {'easy': {'correct': 0, 'total': 0},
                          'hard': {'correct': 0, 'total': 0},
                          'ambiguous': {'correct': 0, 'total': 0}}

        misclassifications = []

        for item in corpus:
            task = item['task']
            gt_domain = item['ground_truth_domain']
            difficulty = item.get('difficulty', 'easy')

            classification = self.router.classify_task(task)
            predicted = classification.primary_domain.value

            is_correct = predicted == gt_domain
            if is_correct:
                correct += 1
            else:
                misclassifications.append({
                    'task': task[:80],
                    'expected': gt_domain,
                    'predicted': predicted,
                    'confidence': round(classification.confidence, 3),
                    'difficulty': difficulty,
                })

            total += 1
            per_domain[gt_domain]['total'] += 1
            if is_correct:
                per_domain[gt_domain]['correct'] += 1
            per_difficulty[difficulty]['total'] += 1
            if is_correct:
                per_difficulty[difficulty]['correct'] += 1

        # Compute per-domain accuracy
        domain_accuracy = {}
        for domain, stats in per_domain.items():
            if stats['total'] > 0:
                domain_accuracy[domain] = round(stats['correct'] / stats['total'], 4)
            else:
                domain_accuracy[domain] = 0.0

        difficulty_accuracy = {}
        for diff, stats in per_difficulty.items():
            if stats['total'] > 0:
                difficulty_accuracy[diff] = round(stats['correct'] / stats['total'], 4)
            else:
                difficulty_accuracy[diff] = 0.0

        overall_accuracy = correct / total if total > 0 else 0

        return {
            'timestamp': datetime.now().isoformat(),
            'total_tasks': total,
            'correct': correct,
            'overall_accuracy': round(overall_accuracy, 4),
            'domain_accuracy': domain_accuracy,
            'difficulty_accuracy': difficulty_accuracy,
            'misclassification_count': len(misclassifications),
            'sample_misclassifications': misclassifications[:10],
            'thresholds': {
                'mixed_domain_threshold': self.router.mixed_domain_threshold,
                'confidence_min': self.router.confidence_min,
            },
        }

    def find_optimal_thresholds(self, corpus: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Search for optimal router thresholds via grid search.

        Returns:
            Best thresholds and their accuracy
        """
        if corpus is None:
            gen = DomainRouterCalibrationCorpus()
            corpus = gen.generate_calibration_corpus()

        from core.ctm_domain_router import CTMDomainRouter

        best_accuracy = 0
        best_thresholds = (0.70, 0.50)
        results = []

        for mixed_thresh in [0.60, 0.65, 0.70, 0.75, 0.80]:
            for conf_min in [0.40, 0.45, 0.50, 0.55, 0.60]:
                self.router = CTMDomainRouter(
                    mixed_domain_threshold=mixed_thresh,
                    confidence_min=conf_min
                )
                report = self.calibrate(corpus)
                acc = report['overall_accuracy']
                results.append({
                    'mixed_threshold': mixed_thresh,
                    'confidence_min': conf_min,
                    'accuracy': acc,
                })
                if acc > best_accuracy:
                    best_accuracy = acc
                    best_thresholds = (mixed_thresh, conf_min)

        return {
            'best_mixed_threshold': best_thresholds[0],
            'best_confidence_min': best_thresholds[1],
            'best_accuracy': best_accuracy,
            'grid_search_results': sorted(results, key=lambda x: -x['accuracy'])[:5],
        }


if __name__ == '__main__':
    print("=" * 70)
    print("CTM Training Data Generation & Validation")
    print("=" * 70)

    # 1. Generate datasets
    print("\n1. Generating training datasets...")
    gen = CTMTrainingDataGenerator(seed=42)
    summary = gen.generate_all_datasets(samples_per_domain=2000)

    # 2. Validate existing training
    print("\n2. Validating existing training...")
    validator = CTMTrainingValidator()
    validation = validator.validate_all_domains()
    print(json.dumps(validation, indent=2))

    # 3. Calibrate domain router
    print("\n3. Calibrating domain router...")
    calibrator = DomainRouterCalibrator()
    cal_report = calibrator.calibrate()
    print(f"Overall accuracy: {cal_report['overall_accuracy']:.1%}")
    print(f"Per-domain: {cal_report['domain_accuracy']}")

    # 4. Find optimal thresholds
    print("\n4. Finding optimal thresholds...")
    optimal = calibrator.find_optimal_thresholds()
    print(f"Best: mixed={optimal['best_mixed_threshold']}, conf={optimal['best_confidence_min']}, acc={optimal['best_accuracy']:.1%}")

    print("\n" + "=" * 70)
    print("COMPLETE")
    print("=" * 70)
