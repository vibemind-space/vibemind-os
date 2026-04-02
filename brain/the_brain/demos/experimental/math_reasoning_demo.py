"""
Mathematical Reasoning with ATM-R + CTM
"""
from thalamo_pc_adaptive import ThalamoPC6Adaptive
import numpy as np

class MathReasoner:
    """Simple math reasoning with ATM-R routing."""

    def __init__(self):
        # Map reasoning modalities to math operations
        self.modalities = ['vision', 'audio', 'touch', 'taste', 'vestibular', 'threat']
        self.reasoning_modes = {
            'vision': 'Visual Thinking',      # Pattern recognition, spatial
            'audio': 'Verbal Logic',          # Step-by-step reasoning
            'touch': 'Procedural Memory',     # Known algorithms
            'taste': 'Estimation',            # Approximate answers
            'vestibular': 'Numerical Sense',  # Number relationships
            'threat': 'Error Detection'       # Checking for mistakes
        }

        self.atmr = ThalamoPC6Adaptive(seed=42)

    def solve(self, problem: str, steps: int = 15):
        """Solve a math problem through multi-step reasoning."""
        print("=" * 70)
        print(f"PROBLEM: {problem}")
        print("=" * 70)
        print()

        # Encode problem (simplified - in reality you'd use embeddings)
        problem_state = self._encode_problem(problem)

        # Multi-step reasoning
        reasoning_trace = []
        for step in range(steps):
            # Step through reasoning
            out = self.atmr.step(problem_state, adapt=True)

            # Which mode is dominant?
            dominant_idx = np.argmax(out['g'])
            dominant_mode = self.modalities[dominant_idx]
            reasoning_type = self.reasoning_modes[dominant_mode]
            confidence = out['g'][dominant_idx]

            # Track
            reasoning_trace.append({
                'step': step,
                'mode': reasoning_type,
                'confidence': confidence
            })

            # Show progress
            if step % 3 == 0:
                print(f"Step {step:2d}: [{reasoning_type:20s}] Confidence: {confidence:.1%}")

            # Update state (simulate reasoning progress)
            problem_state = self._update_state(problem_state, out)

        print()
        print("=" * 70)
        print("REASONING SUMMARY")
        print("=" * 70)

        # Count mode usage
        from collections import Counter
        mode_usage = Counter([t['mode'] for t in reasoning_trace])

        print("\nReasoning mode distribution:")
        for mode, count in mode_usage.most_common():
            percentage = (count / len(reasoning_trace)) * 100
            bar = '#' * int(percentage / 2)
            print(f"  {mode:20s}: {count:2d} steps ({percentage:4.1f}%) {bar}")

        print("\nFinal answer: [Simulated - would be computed from reasoning trace]")
        return reasoning_trace

    def _encode_problem(self, problem: str):
        """Encode problem into multimodal state."""
        # Simplified encoding
        state = {}
        for m in self.modalities:
            if 'add' in problem.lower() or '+' in problem:
                state[m] = np.random.randn(self.atmr.d[m]) * 0.5
            elif 'multiply' in problem.lower() or '*' in problem:
                state[m] = np.random.randn(self.atmr.d[m]) * 1.0
            else:
                state[m] = np.random.randn(self.atmr.d[m]) * 0.3
        return state

    def _update_state(self, state, output):
        """Update problem state based on reasoning step."""
        # Simulate progress
        new_state = {}
        for m in self.modalities:
            new_state[m] = state[m] * 0.9 + np.random.randn(self.atmr.d[m]) * 0.1
        return new_state


# Demo
if __name__ == "__main__":
    reasoner = MathReasoner()

    # Test different math problems
    problems = [
        "Calculate: ((15 + 7) * 3) - 8 / 2",
        "Solve for x: 2x + 5 = 17",
        "What is 25% of 240?",
        "Find the area of a circle with radius 5",
    ]

    for i, problem in enumerate(problems, 1):
        print(f"\n\n### EXAMPLE {i} ###\n")
        reasoner.solve(problem, steps=12)

        if i < len(problems):
            print("\n" + "-" * 70 + "\n")
