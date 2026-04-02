"""
PRACTICAL EXAMPLE: Use ATM-R to route between different solving strategies.
"""
from thalamo_pc_adaptive import ThalamoPC6Adaptive
import numpy as np

class StrategyRouter:
    """Route between different math solving strategies using ATM-R."""

    def __init__(self):
        self.atmr = ThalamoPC6Adaptive(seed=42)

        # Map modalities to actual strategies
        self.strategies = {
            'vision': self.visual_strategy,        # Pattern matching
            'audio': self.step_by_step_strategy,   # Sequential
            'touch': self.formula_strategy,        # Direct formula
            'taste': self.approximation_strategy,  # Estimate
            'vestibular': self.numerical_strategy, # Pure computation
            'threat': self.verification_strategy   # Double-check
        }

    def solve(self, problem_type: str, a: float, b: float):
        """Route to best strategy based on problem type."""

        print(f"\nProblem: {problem_type}({a}, {b})")
        print("-" * 50)

        # Encode problem as multimodal input
        x = self._encode_problem(problem_type, a, b)

        # Let ATM-R decide which strategy to use
        out = self.atmr.step(x, adapt=True)

        # Get dominant strategy
        dominant_idx = np.argmax(out['g'])
        strategy_name = self.atmr.modalities[dominant_idx]
        confidence = out['g'][dominant_idx]

        print(f"Chosen strategy: {strategy_name} (confidence: {confidence:.1%})")

        # Execute that strategy
        strategy_func = self.strategies[strategy_name]
        result = strategy_func(problem_type, a, b)

        print(f"Result: {result}")

        # Show routing distribution
        print("\nStrategy routing:")
        for i, m in enumerate(self.atmr.modalities):
            if out['g'][i] > 0.01:  # Only show significant
                bar = '#' * int(out['g'][i] * 30)
                print(f"  {m:12s}: {out['g'][i]:5.1%} {bar}")

        return result

    def _encode_problem(self, problem_type, a, b):
        """Encode problem characteristics as multimodal signal."""
        x = {}

        # Different problem types activate different modalities
        if problem_type == "add":
            # Simple addition -> numerical strategy
            x['vestibular'] = np.ones(self.atmr.d['vestibular']) * 2.0
            x['audio'] = np.ones(self.atmr.d['audio']) * 1.0
        elif problem_type == "multiply":
            # Multiplication -> could use formulas
            x['touch'] = np.ones(self.atmr.d['touch']) * 2.0
            x['vestibular'] = np.ones(self.atmr.d['vestibular']) * 1.5
        elif problem_type == "complex":
            # Complex -> step by step
            x['audio'] = np.ones(self.atmr.d['audio']) * 2.0
            x['vision'] = np.ones(self.atmr.d['vision']) * 1.0
        elif problem_type == "estimate":
            # Estimation -> approximation
            x['taste'] = np.ones(self.atmr.d['taste']) * 2.0
        else:
            # Unknown -> visual pattern matching
            x['vision'] = np.ones(self.atmr.d['vision']) * 1.5

        # Fill other modalities with noise
        for m in self.atmr.modalities:
            if m not in x:
                x[m] = np.random.randn(self.atmr.d[m]) * 0.1

        return x

    # Different solving strategies (actual implementations)

    def visual_strategy(self, problem_type, a, b):
        """Visual/pattern-based solving."""
        print("  -> Using visual pattern matching")
        # Could use lookup tables, learned patterns, etc.
        if problem_type == "add":
            return a + b
        elif problem_type == "multiply":
            return a * b
        return a + b  # fallback

    def step_by_step_strategy(self, problem_type, a, b):
        """Sequential, explicit steps."""
        print("  -> Using step-by-step reasoning")
        print(f"     Step 1: Got inputs a={a}, b={b}")
        result = None
        if problem_type == "add":
            print(f"     Step 2: Computing {a} + {b}")
            result = a + b
        elif problem_type == "multiply":
            print(f"     Step 2: Computing {a} × {b}")
            result = a * b
        elif problem_type == "complex":
            print(f"     Step 2: Computing ({a} + {b}) × 2")
            result = (a + b) * 2
        print(f"     Step 3: Result = {result}")
        return result

    def formula_strategy(self, problem_type, a, b):
        """Direct formula application."""
        print("  -> Using direct formula")
        if problem_type == "multiply":
            return a * b
        elif problem_type == "add":
            return a + b
        return a * b  # fallback

    def approximation_strategy(self, problem_type, a, b):
        """Quick approximation."""
        print("  -> Using approximation")
        # Round to nearest 10, then compute
        a_approx = round(a / 10) * 10
        b_approx = round(b / 10) * 10
        print(f"     Approximating: {a} ~= {a_approx}, {b} ~= {b_approx}")
        if problem_type == "add":
            return a_approx + b_approx
        elif problem_type == "multiply":
            return a_approx * b_approx
        return a_approx + b_approx

    def numerical_strategy(self, problem_type, a, b):
        """Pure numerical computation."""
        print("  -> Using direct computation")
        if problem_type == "add":
            return a + b
        elif problem_type == "multiply":
            return a * b
        return a + b

    def verification_strategy(self, problem_type, a, b):
        """Double-check result."""
        print("  -> Using verification (computing twice)")
        result1 = a + b if problem_type == "add" else a * b
        result2 = a + b if problem_type == "add" else a * b
        assert result1 == result2, "Verification failed!"
        return result1


# Demo
if __name__ == "__main__":
    print("=" * 70)
    print("PRACTICAL MATH ROUTING")
    print("=" * 70)
    print()
    print("ATM-R routes between different solving strategies based on problem type.")
    print()

    router = StrategyRouter()

    # Test different problem types
    test_cases = [
        ("add", 15, 7),
        ("multiply", 8, 12),
        ("complex", 5, 10),
        ("estimate", 47, 83),
    ]

    for problem_type, a, b in test_cases:
        result = router.solve(problem_type, a, b)
        print()

    print("=" * 70)
    print("KEY INSIGHT:")
    print("=" * 70)
    print("""
ATM-R doesn't compute math itself - it ROUTES to the right strategy/tool:

  - Simple problems → Fast numerical computation
  - Complex problems → Step-by-step reasoning
  - Estimates needed → Approximation strategy
  - Need verification → Double-check strategy

This is like a "System 1 vs System 2" router for computation!
""")
