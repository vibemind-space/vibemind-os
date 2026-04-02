"""
Evolutionary CTM Selection for Adaptive Cognitive System (ACS)

Implements evolutionary algorithms to optimize CTM populations:
- Population management of CTM configurations
- Fitness evaluation based on task performance
- Selection, crossover, and mutation operators
- Multi-objective optimization (consciousness + efficiency)
- Integration with Meta-CTM Supervisor for feedback

The system evolves CTM hyperparameters to find optimal configurations
for different cognitive domains.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable
from enum import Enum
import random
import math
from datetime import datetime
from collections import deque
import threading
import copy


class SelectionMethod(Enum):
    """Selection methods for evolutionary algorithm"""
    TOURNAMENT = "tournament"
    ROULETTE = "roulette"
    RANK = "rank"
    ELITE = "elite"


@dataclass
class CTMGenes:
    """
    Genetic representation of CTM configuration

    These parameters define the CTM's characteristics and can be
    evolved through genetic operators.
    """
    # Core parameters
    consciousness_threshold: float = 0.85
    max_reasoning_steps: int = 50
    learning_rate: float = 0.001

    # Architecture parameters
    feature_dim: int = 256
    attention_heads: int = 8
    memory_size: int = 100

    # Behavior parameters
    exploration_rate: float = 0.1
    patience: int = 5  # Steps without improvement before stopping
    temperature: float = 1.0  # Softmax temperature

    # Domain specialization weights (0.0-1.0)
    spatial_weight: float = 0.25
    logic_weight: float = 0.25
    temporal_weight: float = 0.25
    value_weight: float = 0.25

    def mutate(self, mutation_rate: float = 0.1, mutation_strength: float = 0.2) -> 'CTMGenes':
        """Create a mutated copy of these genes"""
        new_genes = copy.deepcopy(self)

        # Mutate each parameter with probability mutation_rate
        if random.random() < mutation_rate:
            new_genes.consciousness_threshold = max(0.5, min(0.99,
                new_genes.consciousness_threshold + random.gauss(0, mutation_strength * 0.1)))

        if random.random() < mutation_rate:
            new_genes.max_reasoning_steps = max(10, min(200,
                int(new_genes.max_reasoning_steps * (1 + random.gauss(0, mutation_strength)))))

        if random.random() < mutation_rate:
            new_genes.learning_rate = max(0.0001, min(0.1,
                new_genes.learning_rate * (1 + random.gauss(0, mutation_strength))))

        if random.random() < mutation_rate:
            new_genes.exploration_rate = max(0.01, min(0.5,
                new_genes.exploration_rate + random.gauss(0, mutation_strength * 0.1)))

        if random.random() < mutation_rate:
            new_genes.patience = max(1, min(20,
                int(new_genes.patience + random.gauss(0, mutation_strength * 3))))

        if random.random() < mutation_rate:
            new_genes.temperature = max(0.1, min(3.0,
                new_genes.temperature + random.gauss(0, mutation_strength)))

        # Mutate domain weights and renormalize
        if random.random() < mutation_rate:
            weights = [new_genes.spatial_weight, new_genes.logic_weight,
                      new_genes.temporal_weight, new_genes.value_weight]
            for i in range(4):
                if random.random() < mutation_rate:
                    weights[i] = max(0.01, weights[i] + random.gauss(0, mutation_strength * 0.2))

            # Normalize to sum to 1
            total = sum(weights)
            new_genes.spatial_weight = weights[0] / total
            new_genes.logic_weight = weights[1] / total
            new_genes.temporal_weight = weights[2] / total
            new_genes.value_weight = weights[3] / total

        return new_genes

    @staticmethod
    def crossover(parent1: 'CTMGenes', parent2: 'CTMGenes') -> 'CTMGenes':
        """Create offspring through crossover of two parents"""
        child = CTMGenes()

        # Uniform crossover - randomly pick from each parent
        child.consciousness_threshold = random.choice([
            parent1.consciousness_threshold, parent2.consciousness_threshold])
        child.max_reasoning_steps = random.choice([
            parent1.max_reasoning_steps, parent2.max_reasoning_steps])
        child.learning_rate = random.choice([
            parent1.learning_rate, parent2.learning_rate])
        child.feature_dim = random.choice([
            parent1.feature_dim, parent2.feature_dim])
        child.attention_heads = random.choice([
            parent1.attention_heads, parent2.attention_heads])
        child.memory_size = random.choice([
            parent1.memory_size, parent2.memory_size])
        child.exploration_rate = random.choice([
            parent1.exploration_rate, parent2.exploration_rate])
        child.patience = random.choice([
            parent1.patience, parent2.patience])
        child.temperature = random.choice([
            parent1.temperature, parent2.temperature])

        # Blend domain weights
        alpha = random.random()
        child.spatial_weight = alpha * parent1.spatial_weight + (1 - alpha) * parent2.spatial_weight
        child.logic_weight = alpha * parent1.logic_weight + (1 - alpha) * parent2.logic_weight
        child.temporal_weight = alpha * parent1.temporal_weight + (1 - alpha) * parent2.temporal_weight
        child.value_weight = alpha * parent1.value_weight + (1 - alpha) * parent2.value_weight

        # Normalize domain weights
        total = child.spatial_weight + child.logic_weight + child.temporal_weight + child.value_weight
        child.spatial_weight /= total
        child.logic_weight /= total
        child.temporal_weight /= total
        child.value_weight /= total

        return child


@dataclass
class CTMIndividual:
    """
    An individual in the CTM population

    Represents a single CTM configuration with its genes and fitness history.
    """
    id: str
    genes: CTMGenes
    domain: str  # spatial, logic, temporal, value
    generation: int = 0
    fitness: float = 0.0

    # Performance tracking
    total_tasks: int = 0
    successful_tasks: int = 0
    avg_consciousness: float = 0.0
    avg_response_time: float = 0.0

    # Multi-objective scores
    consciousness_score: float = 0.0
    efficiency_score: float = 0.0
    reliability_score: float = 0.0

    # History
    fitness_history: deque = field(default_factory=lambda: deque(maxlen=50))
    created_at: datetime = field(default_factory=datetime.now)
    last_evaluated: Optional[datetime] = None

    def update_fitness(
        self,
        consciousness: float,
        response_time: float,
        success: bool,
        complexity: float = 0.5
    ):
        """Update fitness based on task result"""
        self.total_tasks += 1
        if success:
            self.successful_tasks += 1

        # Update running averages
        alpha = 0.1  # Exponential moving average factor
        self.avg_consciousness = (1 - alpha) * self.avg_consciousness + alpha * consciousness
        self.avg_response_time = (1 - alpha) * self.avg_response_time + alpha * response_time

        # Calculate multi-objective scores
        self.consciousness_score = consciousness
        self.efficiency_score = max(0, 1 - (response_time / 30.0))  # 30s baseline
        self.reliability_score = self.successful_tasks / max(1, self.total_tasks)

        # Combined fitness (weighted sum)
        self.fitness = (
            0.4 * self.consciousness_score +
            0.3 * self.efficiency_score +
            0.3 * self.reliability_score
        )

        # Bonus for handling complex tasks
        if success and complexity > 0.75:
            self.fitness *= 1.1

        self.fitness_history.append(self.fitness)
        self.last_evaluated = datetime.now()

    @property
    def fitness_trend(self) -> float:
        """Calculate fitness improvement trend"""
        if len(self.fitness_history) < 5:
            return 0.0

        recent = list(self.fitness_history)[-10:]
        if len(recent) < 2:
            return 0.0

        # Simple linear regression slope
        n = len(recent)
        x_mean = (n - 1) / 2
        y_mean = sum(recent) / n

        numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(recent))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0
        return numerator / denominator


class EvolutionaryCTMSelector:
    """
    Evolutionary CTM Selection System

    Manages populations of CTM configurations and evolves them
    to find optimal settings for different cognitive domains.

    Features:
    - Domain-specific populations (spatial, logic, temporal, value)
    - Multi-objective fitness evaluation
    - Tournament, roulette, rank, and elite selection
    - Adaptive mutation rates
    - Population diversity maintenance
    """

    def __init__(
        self,
        population_size: int = 20,
        elite_count: int = 2,
        mutation_rate: float = 0.15,
        crossover_rate: float = 0.7,
        selection_method: SelectionMethod = SelectionMethod.TOURNAMENT,
        tournament_size: int = 3,
        diversity_threshold: float = 0.1,
        enable_adaptive_mutation: bool = True
    ):
        """
        Initialize Evolutionary CTM Selector

        Args:
            population_size: Number of individuals per domain
            elite_count: Number of best individuals to preserve
            mutation_rate: Base probability of mutation
            crossover_rate: Probability of crossover vs cloning
            selection_method: How to select parents
            tournament_size: Size of tournament for tournament selection
            diversity_threshold: Minimum genetic diversity to maintain
            enable_adaptive_mutation: Adjust mutation rate based on progress
        """
        self.population_size = population_size
        self.elite_count = elite_count
        self.base_mutation_rate = mutation_rate
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.selection_method = selection_method
        self.tournament_size = tournament_size
        self.diversity_threshold = diversity_threshold
        self.enable_adaptive_mutation = enable_adaptive_mutation

        # Populations for each domain
        self.populations: Dict[str, List[CTMIndividual]] = {
            'spatial': [],
            'logic': [],
            'temporal': [],
            'value': []
        }

        # Generation counter per domain
        self.generations: Dict[str, int] = {
            'spatial': 0,
            'logic': 0,
            'temporal': 0,
            'value': 0
        }

        # Best individuals ever found
        self.hall_of_fame: Dict[str, CTMIndividual] = {}

        # Evolution history
        self.evolution_history: Dict[str, List[Dict]] = {
            domain: [] for domain in self.populations
        }

        # Thread safety
        self._lock = threading.Lock()

        # Initialize populations
        self._initialize_populations()

    def _initialize_populations(self):
        """Create initial populations for each domain"""
        for domain in self.populations:
            self.populations[domain] = []
            for i in range(self.population_size):
                genes = CTMGenes()

                # Domain-specific initialization
                if domain == 'spatial':
                    genes.spatial_weight = 0.5
                    genes.logic_weight = 0.2
                    genes.temporal_weight = 0.15
                    genes.value_weight = 0.15
                elif domain == 'logic':
                    genes.spatial_weight = 0.15
                    genes.logic_weight = 0.5
                    genes.temporal_weight = 0.2
                    genes.value_weight = 0.15
                elif domain == 'temporal':
                    genes.spatial_weight = 0.15
                    genes.logic_weight = 0.2
                    genes.temporal_weight = 0.5
                    genes.value_weight = 0.15
                elif domain == 'value':
                    genes.spatial_weight = 0.15
                    genes.logic_weight = 0.2
                    genes.temporal_weight = 0.15
                    genes.value_weight = 0.5

                # Add some random variation
                genes = genes.mutate(mutation_rate=0.5, mutation_strength=0.3)

                individual = CTMIndividual(
                    id=f"{domain}_{i:03d}_gen0",
                    genes=genes,
                    domain=domain,
                    generation=0,
                    fitness=random.uniform(0.3, 0.5)  # Initial random fitness
                )
                self.populations[domain].append(individual)

    def select_best_ctm(self, domain: str) -> Optional[CTMIndividual]:
        """
        Select the best CTM configuration for a domain

        Args:
            domain: Cognitive domain (spatial/logic/temporal/value)

        Returns:
            Best CTMIndividual for the domain
        """
        with self._lock:
            if domain not in self.populations or not self.populations[domain]:
                return None

            # Sort by fitness and return best
            sorted_pop = sorted(
                self.populations[domain],
                key=lambda x: x.fitness,
                reverse=True
            )
            return sorted_pop[0]

    def record_performance(
        self,
        domain: str,
        individual_id: str,
        consciousness: float,
        response_time: float,
        success: bool,
        complexity: float = 0.5
    ):
        """
        Record performance of a CTM individual

        Args:
            domain: Cognitive domain
            individual_id: ID of the individual that performed
            consciousness: Final consciousness level achieved
            response_time: Time taken in seconds
            success: Whether task succeeded
            complexity: Task complexity (0-1)
        """
        with self._lock:
            if domain not in self.populations:
                return

            for ind in self.populations[domain]:
                if ind.id == individual_id:
                    ind.update_fitness(consciousness, response_time, success, complexity)

                    # Update hall of fame
                    if domain not in self.hall_of_fame or ind.fitness > self.hall_of_fame[domain].fitness:
                        self.hall_of_fame[domain] = copy.deepcopy(ind)
                    break

    def evolve_population(self, domain: str) -> Dict:
        """
        Evolve the population for a domain

        Args:
            domain: Cognitive domain to evolve

        Returns:
            Evolution statistics
        """
        with self._lock:
            if domain not in self.populations:
                return {'error': 'Invalid domain'}

            population = self.populations[domain]
            if len(population) < 2:
                return {'error': 'Population too small'}

            # Sort by fitness
            population.sort(key=lambda x: x.fitness, reverse=True)

            # Record pre-evolution stats
            pre_stats = {
                'best_fitness': population[0].fitness,
                'avg_fitness': sum(ind.fitness for ind in population) / len(population),
                'diversity': self._calculate_diversity(population)
            }

            # Adaptive mutation rate
            if self.enable_adaptive_mutation:
                self._adapt_mutation_rate(population)

            new_population = []

            # Preserve elites
            for i in range(min(self.elite_count, len(population))):
                elite = copy.deepcopy(population[i])
                elite.generation = self.generations[domain] + 1
                new_population.append(elite)

            # Generate rest of population
            while len(new_population) < self.population_size:
                # Select parents
                parent1 = self._select_parent(population)
                parent2 = self._select_parent(population)

                # Crossover or clone
                if random.random() < self.crossover_rate:
                    child_genes = CTMGenes.crossover(parent1.genes, parent2.genes)
                else:
                    child_genes = copy.deepcopy(parent1.genes if parent1.fitness > parent2.fitness else parent2.genes)

                # Mutation
                child_genes = child_genes.mutate(
                    mutation_rate=self.mutation_rate,
                    mutation_strength=0.2
                )

                # Create child individual
                child = CTMIndividual(
                    id=f"{domain}_{len(new_population):03d}_gen{self.generations[domain] + 1}",
                    genes=child_genes,
                    domain=domain,
                    generation=self.generations[domain] + 1,
                    fitness=0.3  # Will be evaluated
                )
                new_population.append(child)

            # Replace population
            self.populations[domain] = new_population[:self.population_size]
            self.generations[domain] += 1

            # Record post-evolution stats
            post_stats = {
                'best_fitness': new_population[0].fitness,
                'avg_fitness': sum(ind.fitness for ind in new_population) / len(new_population),
                'diversity': self._calculate_diversity(new_population)
            }

            # Record history
            evolution_record = {
                'generation': self.generations[domain],
                'timestamp': datetime.now().isoformat(),
                'pre_evolution': pre_stats,
                'post_evolution': post_stats,
                'mutation_rate': self.mutation_rate
            }
            self.evolution_history[domain].append(evolution_record)

            return {
                'domain': domain,
                'generation': self.generations[domain],
                'pre_evolution': pre_stats,
                'post_evolution': post_stats,
                'mutation_rate': self.mutation_rate,
                'elite_preserved': self.elite_count
            }

    def _select_parent(self, population: List[CTMIndividual]) -> CTMIndividual:
        """Select a parent using the configured selection method"""
        if self.selection_method == SelectionMethod.TOURNAMENT:
            return self._tournament_selection(population)
        elif self.selection_method == SelectionMethod.ROULETTE:
            return self._roulette_selection(population)
        elif self.selection_method == SelectionMethod.RANK:
            return self._rank_selection(population)
        else:  # ELITE
            return self._elite_selection(population)

    def _tournament_selection(self, population: List[CTMIndividual]) -> CTMIndividual:
        """Tournament selection"""
        tournament = random.sample(population, min(self.tournament_size, len(population)))
        return max(tournament, key=lambda x: x.fitness)

    def _roulette_selection(self, population: List[CTMIndividual]) -> CTMIndividual:
        """Roulette wheel selection"""
        total_fitness = sum(max(0.01, ind.fitness) for ind in population)
        pick = random.uniform(0, total_fitness)
        current = 0
        for ind in population:
            current += max(0.01, ind.fitness)
            if current >= pick:
                return ind
        return population[-1]

    def _rank_selection(self, population: List[CTMIndividual]) -> CTMIndividual:
        """Rank-based selection"""
        sorted_pop = sorted(population, key=lambda x: x.fitness)
        n = len(sorted_pop)
        total_rank = n * (n + 1) / 2
        pick = random.uniform(0, total_rank)
        current = 0
        for i, ind in enumerate(sorted_pop):
            current += i + 1
            if current >= pick:
                return ind
        return sorted_pop[-1]

    def _elite_selection(self, population: List[CTMIndividual]) -> CTMIndividual:
        """Select from top performers"""
        elite_size = max(2, len(population) // 5)
        sorted_pop = sorted(population, key=lambda x: x.fitness, reverse=True)
        return random.choice(sorted_pop[:elite_size])

    def _calculate_diversity(self, population: List[CTMIndividual]) -> float:
        """Calculate genetic diversity of population"""
        if len(population) < 2:
            return 0.0

        # Calculate variance in key parameters
        consciousnesses = [ind.genes.consciousness_threshold for ind in population]
        steps = [ind.genes.max_reasoning_steps for ind in population]
        exploration = [ind.genes.exploration_rate for ind in population]

        def variance(values):
            mean = sum(values) / len(values)
            return sum((v - mean) ** 2 for v in values) / len(values)

        # Normalized diversity score
        diversity = (
            variance(consciousnesses) * 10 +
            variance([s / 100 for s in steps]) +
            variance(exploration) * 10
        ) / 3

        return min(1.0, diversity)

    def _adapt_mutation_rate(self, population: List[CTMIndividual]):
        """Adapt mutation rate based on population state"""
        diversity = self._calculate_diversity(population)

        # Increase mutation if diversity is low
        if diversity < self.diversity_threshold:
            self.mutation_rate = min(0.5, self.base_mutation_rate * 2)
        # Decrease mutation if making progress
        elif len(self.evolution_history) > 2:
            recent = self.evolution_history.get(population[0].domain, [])[-5:]
            if recent:
                improvements = sum(
                    1 for i in range(1, len(recent))
                    if recent[i]['pre_evolution']['best_fitness'] > recent[i-1]['pre_evolution']['best_fitness']
                )
                if improvements >= 3:
                    self.mutation_rate = max(0.05, self.base_mutation_rate * 0.5)
                else:
                    self.mutation_rate = self.base_mutation_rate
        else:
            self.mutation_rate = self.base_mutation_rate

    def get_population_stats(self, domain: str) -> Dict:
        """Get statistics for a domain's population"""
        with self._lock:
            if domain not in self.populations:
                return {'error': 'Invalid domain'}

            population = self.populations[domain]
            if not population:
                return {'error': 'Empty population'}

            fitnesses = [ind.fitness for ind in population]

            return {
                'domain': domain,
                'generation': self.generations[domain],
                'population_size': len(population),
                'best_fitness': max(fitnesses),
                'worst_fitness': min(fitnesses),
                'avg_fitness': sum(fitnesses) / len(fitnesses),
                'diversity': self._calculate_diversity(population),
                'mutation_rate': self.mutation_rate,
                'hall_of_fame_fitness': self.hall_of_fame.get(domain, CTMIndividual(
                    id='none', genes=CTMGenes(), domain=domain)).fitness
            }

    def get_all_stats(self) -> Dict:
        """Get statistics for all domains"""
        return {
            domain: self.get_population_stats(domain)
            for domain in self.populations
        }

    def get_best_genes(self, domain: str) -> Optional[CTMGenes]:
        """Get the best genes for a domain"""
        best = self.select_best_ctm(domain)
        return best.genes if best else None

    def inject_individual(self, domain: str, genes: CTMGenes, fitness: float = 0.5):
        """
        Inject a custom individual into a population

        Useful for introducing pre-trained configurations.

        Args:
            domain: Target domain
            genes: Gene configuration
            fitness: Initial fitness estimate
        """
        with self._lock:
            if domain not in self.populations:
                return

            individual = CTMIndividual(
                id=f"{domain}_injected_{datetime.now().strftime('%H%M%S')}",
                genes=genes,
                domain=domain,
                generation=self.generations[domain],
                fitness=fitness
            )

            # Replace worst individual
            self.populations[domain].sort(key=lambda x: x.fitness)
            if len(self.populations[domain]) >= self.population_size:
                self.populations[domain][0] = individual
            else:
                self.populations[domain].append(individual)


if __name__ == "__main__":
    # Test Evolutionary CTM Selector
    print("=" * 70)
    print("Evolutionary CTM Selector Test")
    print("=" * 70)

    selector = EvolutionaryCTMSelector(
        population_size=10,
        elite_count=2,
        mutation_rate=0.15
    )

    # Test initial population
    print("\nInitial Population Stats:")
    stats = selector.get_all_stats()
    for domain, domain_stats in stats.items():
        print(f"  {domain}: best={domain_stats['best_fitness']:.3f}, avg={domain_stats['avg_fitness']:.3f}")

    # Simulate some task executions
    print("\nSimulating task executions...")
    for _ in range(20):
        for domain in ['spatial', 'logic', 'temporal', 'value']:
            best = selector.select_best_ctm(domain)
            if best:
                # Simulate random performance
                consciousness = random.uniform(0.6, 0.95)
                response_time = random.uniform(1, 15)
                success = random.random() > 0.3

                selector.record_performance(
                    domain=domain,
                    individual_id=best.id,
                    consciousness=consciousness,
                    response_time=response_time,
                    success=success,
                    complexity=0.7
                )

    # Evolve populations
    print("\nEvolving populations...")
    for domain in ['spatial', 'logic', 'temporal', 'value']:
        result = selector.evolve_population(domain)
        print(f"  {domain} Gen {result['generation']}: "
              f"best {result['pre_evolution']['best_fitness']:.3f} -> {result['post_evolution']['best_fitness']:.3f}")

    # Final stats
    print("\nFinal Population Stats:")
    stats = selector.get_all_stats()
    for domain, domain_stats in stats.items():
        print(f"  {domain}: gen={domain_stats['generation']}, "
              f"best={domain_stats['best_fitness']:.3f}, "
              f"diversity={domain_stats['diversity']:.3f}")

    # Show best genes
    print("\nBest Genes for Spatial Domain:")
    best_genes = selector.get_best_genes('spatial')
    if best_genes:
        print(f"  consciousness_threshold: {best_genes.consciousness_threshold:.3f}")
        print(f"  max_reasoning_steps: {best_genes.max_reasoning_steps}")
        print(f"  exploration_rate: {best_genes.exploration_rate:.3f}")
        print(f"  domain weights: spatial={best_genes.spatial_weight:.2f}, "
              f"logic={best_genes.logic_weight:.2f}, "
              f"temporal={best_genes.temporal_weight:.2f}, "
              f"value={best_genes.value_weight:.2f}")

    print("\n" + "=" * 70)
    print("Evolutionary CTM Selector Test Complete!")
    print("=" * 70)
