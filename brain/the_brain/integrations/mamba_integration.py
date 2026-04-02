"""
Mamba/SSM Integration für CTM-ATM-R

Kombiniert State Space Models (Mamba) mit ATM-R Routing
für effizienteres kontinuierliches Reasoning.

Konzept:
- Mamba: Effizientes State Modeling innerhalb jedes Reasoning-Modus
- ATM-R: High-level Routing zwischen Modi
- CTM: Iteratives Reasoning über die kombinierte Architektur
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from thalamo_pc_adaptive import ThalamoPC6Adaptive
from reasoning_modes import get_display_name, get_icon


# ============================================================================
# MAMBA SSM SIMULATOR
# ============================================================================

class MambaSSMSimulator:
    """
    Vereinfachte Mamba SSM Implementation.

    In echter Implementation würden Sie hier ein trainiertes Mamba-Modell laden.
    Für Demo: Simulieren wir Mamba's selektive State Space Dynamics.

    Mamba Kerngleichungen:
    1. Selective Parameters: Δ, B, C = f(x_t)  [input-dependent!]
    2. State Update: h_t = A·h_{t-1} + B·x_t   [diskretisiert mit Δ]
    3. Output: y_t = C·h_t
    """

    def __init__(self, d_model: int = 128, d_state: int = 16, seed: int = 42):
        """
        Args:
            d_model: Input/Output dimension
            d_state: Hidden state dimension (klein für Effizienz!)
            seed: Random seed
        """
        np.random.seed(seed)

        self.d_model = d_model
        self.d_state = d_state

        # SSM Parameters (würden normalerweise gelernt)
        self.A = np.random.randn(d_state, d_state) * 0.1  # State transition
        self.A = self.A - self.A.T  # Make skew-symmetric (stable)

        # Selective projection weights
        self.W_delta = np.random.randn(d_model, 1) * 0.01  # Time scale selector
        self.W_B = np.random.randn(d_model, d_state) * 0.01  # Input selector
        self.W_C = np.random.randn(d_model, d_state) * 0.01  # Output selector

        # State
        self.h = np.zeros(d_state)  # Hidden state

    def step(self, x: np.ndarray) -> np.ndarray:
        """
        Ein Mamba SSM Schritt.

        Args:
            x: Input vector [d_model]

        Returns:
            y: Output vector [d_model]
        """
        # 1. Compute selective parameters (INPUT-DEPENDENT!)
        delta = np.tanh(x @ self.W_delta).item()  # Time scale [scalar]
        B = x @ self.W_B  # Input projection [d_state]
        C = (x @ self.W_C).reshape(-1)  # Output projection [d_state], ensure 1D

        # 2. Discretize continuous SSM with selective delta
        A_discrete = np.eye(self.d_state) + delta * self.A
        B_discrete = delta * B

        # 3. State update (recurrent!)
        self.h = A_discrete @ self.h + B_discrete * x[:self.d_state]

        # 4. Output
        y = C @ self.h

        # Expand back to d_model dimension
        if isinstance(y, (int, float, np.number)):
            # Scalar output
            y_full = np.zeros(self.d_model)
            y_full[0] = y
            y = y_full
        elif len(y) < self.d_model:
            # Vector output but too short
            y_full = np.zeros(self.d_model)
            y_full[:len(y)] = y
            y = y_full

        return y

    def reset_state(self):
        """Reset hidden state."""
        self.h = np.zeros(self.d_state)


# ============================================================================
# CTM + ATM-R + MAMBA Integration
# ============================================================================

class CTMMambaReasoner:
    """
    CTM Reasoner mit Mamba SSM für jede Modalität.

    Architektur:
    - Jede Modalität hat ein eigenes Mamba SSM Modul
    - ATM-R routet zwischen Modalitäten
    - Mamba innerhalb jeder Modalität macht effizientes State Modeling

    Vorteile:
    - Linear statt quadratisch in Sequenzlänge
    - Selektive Attention innerhalb Modi
    - Kontinuierliche State Dynamics
    - Effizienter für lange Reasoning-Trajektorien
    """

    def __init__(self, use_mamba: bool = True, seed: int = 42):
        """
        Args:
            use_mamba: Wenn False, nutze einfache Feedforward (Baseline)
            seed: Random seed
        """
        self.use_mamba = use_mamba

        # ATM-R für high-level Routing
        self.atmr = ThalamoPC6Adaptive(seed=seed)

        # Mamba SSM für jede Modalität
        self.mamba_modules = {}
        if use_mamba:
            for mod in self.atmr.modalities:
                self.mamba_modules[mod] = MambaSSMSimulator(
                    d_model=self.atmr.d[mod],
                    d_state=max(4, self.atmr.d[mod] // 8),  # d_state = d_model/8
                    seed=seed
                )

        print(f"CTMMambaReasoner initialized:")
        print(f"  ATM-R Modalities: {self.atmr.modalities}")
        print(f"  Mamba: {'Enabled' if use_mamba else 'Disabled (Baseline)'}")
        if use_mamba:
            print(f"  Mamba State Dims: {[self.mamba_modules[m].d_state for m in self.atmr.modalities]}")

    def reason(self, problem: str, initial_state: Optional[Dict] = None,
               max_steps: int = 30) -> Dict:
        """
        Iteratives Reasoning mit Mamba SSM.

        Process:
        1. Initial state
        2. For each step:
           a) ATM-R routes to modalitäten (compute gate weights)
           b) Each active modality processes with its Mamba SSM
           c) Combine outputs weighted by gates
           d) Update state
        3. Converge when confidence high
        """
        print(f"\n{'='*80}")
        print(f"REASONING WITH MAMBA: {problem}")
        print(f"{'='*80}\n")

        # Initialize
        if initial_state is None:
            state = {mod: np.random.randn(self.atmr.d[mod]) * 0.1
                    for mod in self.atmr.modalities}
        else:
            state = initial_state

        trajectory = []

        for step in range(max_steps):
            # 1. ATM-R Routing
            out = self.atmr.step(state, adapt=True)
            gates = out['g']
            dominant_idx = np.argmax(gates)
            dominant_mode = self.atmr.modalities[dominant_idx]

            # 2. Process with Mamba SSM (or baseline)
            new_state = {}
            for i, mod in enumerate(self.atmr.modalities):
                if gates[i] > 0.05:  # Only process active modes
                    if self.use_mamba:
                        # Mamba SSM processing
                        processed = self.mamba_modules[mod].step(state[mod])
                    else:
                        # Baseline: Simple tanh
                        processed = np.tanh(state[mod] + np.random.randn(self.atmr.d[mod]) * 0.1)

                    # Weight by gate
                    new_state[mod] = processed * gates[i]
                else:
                    new_state[mod] = state[mod]  # Keep unchanged

            # 3. Normalize
            state = new_state

            # 4. Track trajectory
            confidence = float(np.max(gates))
            entropy = float(-np.sum((gates + 1e-10) * np.log2(gates + 1e-10)))

            trajectory.append({
                'step': step,
                'dominant': dominant_mode,
                'confidence': confidence,
                'entropy': entropy,
                'gates': gates.copy()
            })

            # Print progress
            if step % 5 == 0:
                mode_name = get_display_name(dominant_mode)
                print(f"Step {step:2d} [{mode_name:20s}] "
                      f"Conf: {confidence:.1%} | Entropy: {entropy:.2f} bits")

            # 5. Convergence check
            if confidence > 0.85 and entropy < 0.5:
                print(f"\n-> Converged after {step+1} steps!")
                break

        return {
            'trajectory': trajectory,
            'final_state': state,
            'steps': step + 1,
            'converged': confidence > 0.85
        }

    def reset_mamba_states(self):
        """Reset all Mamba hidden states."""
        if self.use_mamba:
            for mod in self.mamba_modules:
                self.mamba_modules[mod].reset_state()


# ============================================================================
# VERGLEICH: Mit vs. Ohne Mamba
# ============================================================================

def compare_mamba_vs_baseline():
    """Vergleiche Mamba-enhanced vs. Baseline CTM."""

    print("\n" + "="*80)
    print("COMPARISON: CTM + Mamba vs. Baseline CTM")
    print("="*80)

    problem = "Solve complex multi-step reasoning task"

    # Baseline (ohne Mamba)
    print("\n### BASELINE: CTM ohne Mamba ###")
    baseline = CTMMambaReasoner(use_mamba=False, seed=42)
    result_baseline = baseline.reason(problem, max_steps=30)

    # Mit Mamba
    print("\n\n### MAMBA: CTM mit Mamba SSM ###")
    mamba = CTMMambaReasoner(use_mamba=True, seed=42)
    result_mamba = mamba.reason(problem, max_steps=30)

    # Vergleich
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)

    print(f"\nBaseline:")
    print(f"  Steps to convergence: {result_baseline['steps']}")
    print(f"  Converged: {result_baseline['converged']}")
    print(f"  Final confidence: {result_baseline['trajectory'][-1]['confidence']:.1%}")

    print(f"\nMamba:")
    print(f"  Steps to convergence: {result_mamba['steps']}")
    print(f"  Converged: {result_mamba['converged']}")
    print(f"  Final confidence: {result_mamba['trajectory'][-1]['confidence']:.1%}")

    print(f"\nImprovement:")
    step_improvement = (result_baseline['steps'] - result_mamba['steps']) / result_baseline['steps'] * 100
    print(f"  Steps reduction: {step_improvement:+.1f}%")


# ============================================================================
# INTEGRATION STRATEGIES
# ============================================================================

def integration_strategy_1_mamba_per_modality():
    """
    Strategy 1: Mamba SSM pro Modalität

    Jede Modalität hat eigenes Mamba-Modul für lokales State Modeling.
    ATM-R routet high-level zwischen Modalitäten.
    """
    print("\n" + "="*80)
    print("INTEGRATION STRATEGY 1: Mamba per Modality")
    print("="*80)

    print("""
Architecture:

    Input x_t
       |
       v
    ATM-R Routing  (gate weights g_i)
       |
       +---> [Modality 1] ---> Mamba SSM 1 ---> y_1
       |
       +---> [Modality 2] ---> Mamba SSM 2 ---> y_2
       |
       +---> [Modality 3] ---> Mamba SSM 3 ---> y_3
       |
       v
    Weighted Sum (g_i * y_i)
       |
       v
    Output

Vorteile:
- Effizientes State Modeling pro Modus
- Parallele Verarbeitung möglich
- Jeder Modus hat eigene Dynamics

Nachteil:
- Mehr Parameter (ein Mamba pro Modus)
""")


def integration_strategy_2_shared_mamba():
    """
    Strategy 2: Shared Mamba mit Modalität-Conditioning

    Ein gemeinsames Mamba für alle Modalitäten,
    konditioniert auf aktuelle Modalität.
    """
    print("\n" + "="*80)
    print("INTEGRATION STRATEGY 2: Shared Mamba")
    print("="*80)

    print("""
Architecture:

    Input x_t + Modality Embedding
       |
       v
    Shared Mamba SSM
       |
       v
    ATM-R Routing (post-processing)
       |
       v
    Output

Vorteile:
- Weniger Parameter
- Cross-modal Information Sharing
- Einheitliche State Dynamics

Nachteil:
- Weniger spezialisiert pro Modus
""")


def integration_strategy_3_hierarchical():
    """
    Strategy 3: Hierarchisches Mamba

    - Low-level: Mamba für schnelle lokale Reasoning
    - High-level: ATM-R für strategisches Routing
    """
    print("\n" + "="*80)
    print("INTEGRATION STRATEGY 3: Hierarchical Mamba + ATM-R")
    print("="*80)

    print("""
Architecture:

    High-Level (ATM-R):
    - Strategic routing between reasoning modes
    - Slow dynamics (tau = 40-60)

         |
         v

    Mid-Level (Modality Processing):
    - Mode-specific processing

         |
         v

    Low-Level (Mamba SSM):
    - Fast sequential reasoning within mode
    - Efficient state updates
    - Selective attention

Vorteile:
- Beste Separation of Concerns
- ATM-R für Strategie, Mamba für Effizienz
- Skaliert gut für lange Sequenzen

Empfehlung: DIESE STRATEGIE! (BEST)
""")


# ============================================================================
# PRACTICAL USE CASE: Long-Context Reasoning
# ============================================================================

class MambaLongContextReasoner:
    """
    Use Case: Reasoning über sehr lange Kontexte.

    Mamba's Stärke: Linear Complexity → Gut für lange Sequenzen!
    ATM-R: Adaptive Routing → Fokus auf relevante Modi

    Beispiel: Analyse eines langen Dokuments
    """

    def __init__(self):
        self.reasoner = CTMMambaReasoner(use_mamba=True, seed=42)

    def analyze_long_document(self, document: str, max_steps: int = 100):
        """
        Analysiere langes Dokument mit Mamba+ATM-R.

        Transformer: O(n²) → unpraktisch für n=100+ steps
        Mamba: O(n) → effizient auch für n=1000 steps!
        """
        print(f"\n{'='*80}")
        print(f"LONG CONTEXT REASONING")
        print(f"Document length: {len(document)} chars")
        print(f"Max steps: {max_steps}")
        print(f"{'='*80}\n")

        # Simuliere lange Sequenz
        result = self.reasoner.reason(
            problem=f"Analyze document: {document[:50]}...",
            max_steps=max_steps
        )

        print(f"\nProcessed {result['steps']} steps efficiently with Mamba!")
        print(f"Complexity: O({result['steps']}) vs. O({result['steps']**2}) for Transformer")

        return result


# ============================================================================
# DEMO
# ============================================================================

if __name__ == "__main__":

    print("\n" + "="*80)
    print("MAMBA/SSM INTEGRATION FOR CTM-ATM-R")
    print("="*80)

    # Demo 1: Basic Mamba Integration
    print("\n### DEMO 1: Basic CTM + Mamba ###")
    reasoner = CTMMambaReasoner(use_mamba=True, seed=42)
    result = reasoner.reason("Solve multi-step problem", max_steps=20)

    # Demo 2: Comparison
    print("\n\n### DEMO 2: Comparison ###")
    compare_mamba_vs_baseline()

    # Demo 3: Integration Strategies
    integration_strategy_1_mamba_per_modality()
    integration_strategy_2_shared_mamba()
    integration_strategy_3_hierarchical()

    # Demo 4: Long Context
    print("\n\n### DEMO 4: Long Context Reasoning ###")
    long_reasoner = MambaLongContextReasoner()
    long_doc = "This is a very long document..." * 100
    result = long_reasoner.analyze_long_document(long_doc, max_steps=50)

    print("\n" + "="*80)
    print("CONCLUSION: Mamba passt sehr gut zu CTM-ATM-R!")
    print("="*80)
    print("""
Key Benefits:
1. Effizienz: O(n) statt O(n²) für lange Reasoning-Trajektorien
2. Selective Mechanisms: Ähnlich wie ATM-R Gates
3. Continuous Dynamics: Passt zu Predictive Coding
4. State Persistence: Besseres Memory über Steps

Empfohlene Integration:
- Strategy 3: Hierarchical (ATM-R high-level, Mamba low-level)
- Ein Mamba pro Modalität
- Für Use Cases mit >30 Reasoning-Steps
""")
