"""
CTM Use Cases - Praktische Anwendungen für CTM-ATM-R Integration

Basierend auf Sakana AI's Continuous Thought Machines:
- Iteratives Reasoning über mehrere Schritte
- Adaptive Routing zwischen Reasoning-Modi
- Trajektorien-basierte Problemlösung

Anwendungsfälle:
1. Multi-Step Reasoning (Mathe, Logik)
2. Planning & Decomposition
3. Creative Problem Solving
4. Code Generation with Iterative Refinement
5. Multi-Agent Task Orchestration
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from thalamo_pc_adaptive import ThalamoPC6Adaptive
from reasoning_modes import get_display_name, get_icon


def safe_print_mode(mode: str) -> str:
    """Terminal-safe mode printing without emojis."""
    return get_display_name(mode)


# ============================================================================
# USE CASE 1: Multi-Step Mathematical Reasoning
# ============================================================================

class CTMMathReasoner:
    """
    CTM für mehrstufiges mathematisches Denken.

    Beispiel: "Löse: ((15 + 7) * 3) - 8 / 2"

    Reasoning-Modi:
    - Visual Thinking: Visualisiere die Gleichung
    - Verbal Logic: Wende Regeln an (Punkt vor Strich)
    - Value Reasoning: Schätze Zwischenergebnisse
    """

    def __init__(self):
        self.atmr = ThalamoPC6Adaptive(seed=42)
        self.state = np.random.randn(128) * 0.1  # Initial thought state

    def solve_step_by_step(self, problem: str, max_steps: int = 20) -> Dict:
        """Löse mathematisches Problem schrittweise."""

        print(f"\n{'='*80}")
        print(f"MATH REASONING: {problem}")
        print(f"{'='*80}\n")

        trajectory = []
        thoughts = []

        for step in range(max_steps):
            # Prepare input für ATM-R
            x_t = {
                'vision': self.state[:128],           # Visualisierung
                'audio': self.state[:64] * 1.5,       # Logische Regeln
                'touch': np.zeros(32),
                'taste': np.random.randn(16) * 0.8,   # Wert-Schätzung
                'vestibular': np.zeros(16),
                'threat': np.zeros(8)
            }

            # ATM-R Routing
            out = self.atmr.step(x_t, adapt=True)
            dominant = self.atmr.modalities[np.argmax(out['g'])]

            # Update state (simuliert Denk-Fortschritt)
            self.state = np.tanh(self.state + np.random.randn(128) * 0.15)

            # Generiere Gedanken basierend auf Modus
            thought = self._generate_math_thought(dominant, step, out['g'])
            thoughts.append(thought)

            # Speichere Trajektorie
            trajectory.append({
                'step': step,
                'mode': dominant,
                'gates': out['g'].copy(),
                'thought': thought,
                'confidence': float(np.max(out['g']))
            })

            print(f"Step {step:2d} [{safe_print_mode(dominant):20s}] {thought}")

            # Konvergenz-Check
            if step > 5 and np.max(out['g']) > 0.85:
                print(f"\n-> Konvergiert nach {step+1} Schritten!")
                break

        return {
            'trajectory': trajectory,
            'thoughts': thoughts,
            'final_mode': dominant
        }

    def _generate_math_thought(self, mode: str, step: int, gates: np.ndarray) -> str:
        """Generiere Gedanken für math reasoning."""
        thoughts = {
            'vision': [
                "Visualize equation structure...",
                "See the parentheses hierarchy...",
                "Mental image of operation tree..."
            ],
            'audio': [
                "Apply order of operations rule...",
                "Parentheses first, then multiplication...",
                "Left to right evaluation..."
            ],
            'taste': [
                "Estimate: result should be around 60...",
                "Check if result is reasonable...",
                "Compare intermediate values..."
            ]
        }

        mode_thoughts = thoughts.get(mode, ["Processing..."])
        return mode_thoughts[step % len(mode_thoughts)]


# ============================================================================
# USE CASE 2: Planning & Task Decomposition
# ============================================================================

class CTMPlanner:
    """
    CTM für hierarchisches Planning und Task Decomposition.

    Beispiel: "Plane eine Reise von Berlin nach Tokyo"

    Reasoning-Modi:
    - Spatial Thinking: Route planen
    - Value Reasoning: Kosten/Nutzen abwägen
    - Safety Monitoring: Risiken checken
    """

    def __init__(self):
        self.atmr = ThalamoPC6Adaptive(seed=42)
        self.plan = []

    def plan_task(self, goal: str, max_steps: int = 30) -> List[Dict]:
        """Erstelle Plan für komplexe Aufgabe."""

        print(f"\n{'='*80}")
        print(f"PLANNING: {goal}")
        print(f"{'='*80}\n")

        state = np.random.randn(128) * 0.2

        for step in range(max_steps):
            # ATM-R Input
            x_t = {
                'vision': state[:128] * 0.8,
                'audio': state[:64] * 1.2,
                'touch': np.zeros(32),
                'taste': np.random.randn(16) * 2.0,      # Value important!
                'vestibular': np.random.randn(16) * 1.5,  # Spatial planning
                'threat': np.random.randn(8) * 0.5       # Safety checks
            }

            out = self.atmr.step(x_t, adapt=True)
            dominant = self.atmr.modalities[np.argmax(out['g'])]

            # Generiere Plan-Schritt
            plan_step = self._generate_plan_step(dominant, step)
            self.plan.append(plan_step)

            print(f"Step {step:2d} [{safe_print_mode(dominant):20s}] {plan_step['action']}")

            # Update state
            state = np.tanh(state + np.random.randn(128) * 0.1)

            # Konvergenz
            if step > 10 and np.max(out['g']) > 0.80:
                print(f"\n-> Plan complete after {step+1} steps!")
                break

        return self.plan

    def _generate_plan_step(self, mode: str, step: int) -> Dict:
        """Generiere Plan-Schritt."""
        actions = {
            'vestibular': f"Route segment {step}: Navigate...",
            'taste': f"Evaluate option {step}: Cost/benefit...",
            'threat': f"Safety check {step}: Verify risks...",
            'vision': f"Visualize step {step}: See the path...",
            'audio': f"Logical step {step}: Apply constraints..."
        }

        return {
            'step': step,
            'mode': mode,
            'action': actions.get(mode, f"Process step {step}...")
        }


# ============================================================================
# USE CASE 3: Creative Problem Solving
# ============================================================================

class CTMCreativeSolver:
    """
    CTM für kreative Problemlösung mit Exploration.

    Beispiel: "Design a new user interface"

    Features:
    - Höhere Entropy -> Mehr Exploration
    - Diverse Reasoning-Modi kombinieren
    - Iterative Refinement
    """

    def __init__(self, temperature: float = 0.8):
        self.atmr = ThalamoPC6Adaptive(seed=42)
        self.temperature = temperature  # Höher = mehr Exploration

    def explore_solutions(self, problem: str, iterations: int = 25) -> List[Dict]:
        """Exploriere kreative Lösungen."""

        print(f"\n{'='*80}")
        print(f"CREATIVE EXPLORATION: {problem}")
        print(f"Temperature: {self.temperature}")
        print(f"{'='*80}\n")

        solutions = []
        state = np.random.randn(128) * 0.3

        for i in range(iterations):
            # Mehr Noise für Exploration
            x_t = {
                'vision': state[:128] + np.random.randn(128) * self.temperature,
                'audio': state[:64] + np.random.randn(64) * self.temperature,
                'touch': np.random.randn(32) * self.temperature,
                'taste': np.random.randn(16) * self.temperature,
                'vestibular': np.random.randn(16) * self.temperature,
                'threat': np.zeros(8)  # Low threat for creativity
            }

            out = self.atmr.step(x_t, adapt=True)
            dominant = self.atmr.modalities[np.argmax(out['g'])]

            # Berechne Entropy (Diversity)
            gates = out['g'] + 1e-10
            entropy = -np.sum(gates * np.log2(gates))

            solution = {
                'iteration': i,
                'mode': dominant,
                'entropy': float(entropy),
                'diversity': 'HIGH' if entropy > 1.5 else 'MEDIUM' if entropy > 1.0 else 'LOW'
            }
            solutions.append(solution)

            if i % 5 == 0:
                print(f"Iteration {i:2d} [{safe_print_mode(dominant):20s}] "
                      f"Entropy: {entropy:.2f} bits ({solution['diversity']})")

            state = np.tanh(state + np.random.randn(128) * 0.15)

        return solutions


# ============================================================================
# USE CASE 4: Code Generation with Iterative Refinement
# ============================================================================

class CTMCodeGenerator:
    """
    CTM für Code-Generierung mit iterativer Verbesserung.

    Schritte:
    1. Visual Thinking: Visualisiere Code-Struktur
    2. Verbal Logic: Wende Syntax-Regeln an
    3. Value Reasoning: Bewerte Code-Qualität
    4. Safety Monitoring: Check für Bugs/Security
    """

    def __init__(self):
        # Custom modalities für Code-Generation
        self.atmr = ThalamoPC6Adaptive(
            modalities=['vision', 'audio', 'touch', 'taste', 'vestibular', 'threat'],
            seed=42
        )

    def generate_code(self, spec: str, refinement_steps: int = 15) -> Dict:
        """Generiere Code mit iterativer Verbesserung."""

        print(f"\n{'='*80}")
        print(f"CODE GENERATION: {spec}")
        print(f"{'='*80}\n")

        # Phasen: Design -> Implementation -> Testing -> Refinement
        phases = ['design', 'implement', 'test', 'refine']
        current_phase = 0

        quality_score = 0.0
        state = np.random.randn(128) * 0.2

        for step in range(refinement_steps):
            phase = phases[min(current_phase, len(phases)-1)]

            # Phase-abhängige Inputs
            if phase == 'design':
                x_t = {'vision': np.random.randn(128) * 2.0, 'audio': np.random.randn(64) * 1.0,
                       'touch': np.zeros(32), 'taste': np.zeros(16),
                       'vestibular': np.zeros(16), 'threat': np.zeros(8)}
            elif phase == 'implement':
                x_t = {'vision': np.random.randn(128) * 1.0, 'audio': np.random.randn(64) * 2.5,
                       'touch': np.zeros(32), 'taste': np.random.randn(16) * 0.5,
                       'vestibular': np.zeros(16), 'threat': np.zeros(8)}
            elif phase == 'test':
                x_t = {'vision': np.zeros(128), 'audio': np.random.randn(64) * 1.0,
                       'touch': np.zeros(32), 'taste': np.random.randn(16) * 2.0,
                       'vestibular': np.zeros(16), 'threat': np.random.randn(8) * 1.5}
            else:  # refine
                x_t = {'vision': np.random.randn(128) * 0.8, 'audio': np.random.randn(64) * 1.5,
                       'touch': np.zeros(32), 'taste': np.random.randn(16) * 2.5,
                       'vestibular': np.zeros(16), 'threat': np.random.randn(8) * 1.0}

            out = self.atmr.step(x_t, adapt=True)
            dominant = self.atmr.modalities[np.argmax(out['g'])]

            # Simuliere Quality-Verbesserung
            quality_score = min(1.0, quality_score + 0.05 + np.random.rand() * 0.03)

            print(f"Step {step:2d} [Phase: {phase:10s}] [{safe_print_mode(dominant):20s}] "
                  f"Quality: {quality_score:.1%}")

            # Phase-Wechsel bei Konvergenz
            if step > 0 and step % 4 == 0:
                current_phase += 1

            # Fertig bei hoher Qualität
            if quality_score > 0.90:
                print(f"\n-> Code ready! Quality: {quality_score:.1%}")
                break

        return {
            'quality': quality_score,
            'phases_completed': current_phase,
            'steps': step + 1
        }


# ============================================================================
# USE CASE 5: Multi-Agent Task Orchestration
# ============================================================================

class CTMAgentOrchestrator:
    """
    CTM für dynamisches Agent-Routing in Multi-Agent System.

    Statt fester Modalitäten: Agent-Typen!
    """

    def __init__(self):
        # Custom Agent-Modalitäten
        self.agent_router = ThalamoPC6Adaptive(
            modalities=['reasoning', 'code', 'search', 'memory', 'tools', 'security'],
            dimensions={
                'reasoning': 128,
                'code': 64,
                'search': 64,
                'memory': 96,
                'tools': 32,
                'security': 16
            },
            priors={
                'reasoning': 0.25,
                'code': 0.20,
                'search': 0.15,
                'memory': 0.15,
                'tools': 0.10,
                'security': 0.15
            },
            tau={
                'reasoning': 50.0,
                'code': 40.0,
                'search': 30.0,
                'memory': 45.0,
                'tools': 25.0,
                'security': 15.0
            },
            seed=42
        )

    def route_task(self, task: str, task_features: Dict[str, np.ndarray]) -> Dict:
        """Route task zu passenden Agenten."""

        out = self.agent_router.step(task_features, adapt=True)

        # Finde aktive Agenten (Threshold: 10%)
        active_agents = []
        for i, mod in enumerate(self.agent_router.modalities):
            if out['g'][i] > 0.10:
                active_agents.append({
                    'agent': mod,
                    'priority': float(out['g'][i]),
                    'should_execute': out['g'][i] > 0.15
                })

        # Sortiere nach Priorität
        active_agents.sort(key=lambda x: x['priority'], reverse=True)

        return {
            'task': task,
            'active_agents': active_agents,
            'dominant': self.agent_router.modalities[np.argmax(out['g'])],
            'routing_entropy': float(-np.sum((out['g'] + 1e-10) * np.log2(out['g'] + 1e-10)))
        }


# ============================================================================
# DEMO
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("CTM USE CASES - Practical Applications")
    print("="*80)

    # Use Case 1: Math Reasoning
    print("\n\n### USE CASE 1: Multi-Step Mathematical Reasoning ###")
    math_reasoner = CTMMathReasoner()
    result = math_reasoner.solve_step_by_step("((15 + 7) * 3) - 8 / 2", max_steps=12)

    # Use Case 2: Planning
    print("\n\n### USE CASE 2: Planning & Task Decomposition ###")
    planner = CTMPlanner()
    plan = planner.plan_task("Plan a trip from Berlin to Tokyo", max_steps=15)

    # Use Case 3: Creative Solving
    print("\n\n### USE CASE 3: Creative Problem Solving ###")
    creative = CTMCreativeSolver(temperature=0.9)
    solutions = creative.explore_solutions("Design innovative UI", iterations=15)

    # Use Case 4: Code Generation
    print("\n\n### USE CASE 4: Code Generation with Refinement ###")
    code_gen = CTMCodeGenerator()
    result = code_gen.generate_code("Implement binary search tree", refinement_steps=12)

    # Use Case 5: Agent Orchestration
    print("\n\n### USE CASE 5: Multi-Agent Task Orchestration ###")
    orchestrator = CTMAgentOrchestrator()

    # Simuliere Task mit Features
    task_features = {
        'reasoning': np.random.randn(128) * 2.0,
        'code': np.random.randn(64) * 3.0,
        'search': np.random.randn(64) * 0.5,
        'memory': np.random.randn(96) * 1.0,
        'tools': np.random.randn(32) * 0.8,
        'security': np.random.randn(16) * 1.5
    }

    routing = orchestrator.route_task("Debug security vulnerability in code", task_features)

    print(f"\nTask: {routing['task']}")
    print(f"Dominant Agent: {routing['dominant']}")
    print(f"Routing Entropy: {routing['routing_entropy']:.2f} bits")
    print("\nActive Agents:")
    for agent in routing['active_agents']:
        status = "EXECUTE" if agent['should_execute'] else "STANDBY"
        print(f"  {agent['agent']:12s} [{agent['priority']:6.1%}] -> {status}")

    print("\n" + "="*80)
    print("SUMMARY: CTM can be applied to diverse reasoning tasks!")
    print("="*80)
