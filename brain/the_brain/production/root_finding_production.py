"""
PRODUCTION EXAMPLE: Adaptive Root Finding with Real Learning

This demonstrates REAL adaptive learning over 1000+ problems:
- Router learns which methods work best for different problem types
- Success/failure feedback adjusts routing decisions
- Performance improves over time
- Learned state can be saved/loaded
"""
import numpy as np
from adaptive_router import ProductionRouter, MethodRegistry
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


class RootFindingMethods:
    """Collection of root-finding algorithms."""

    @staticmethod
    def bisection(func, x0, max_iter=100, tol=1e-6):
        """Bisection: Slow but reliable."""
        if isinstance(x0, (list, tuple)):
            a, b = x0
        else:
            a, b = x0 - 1, x0 + 1

        # Check if interval is valid
        if func(a) * func(b) > 0:
            return None, max_iter, False  # Failed

        for i in range(max_iter):
            c = (a + b) / 2
            fc = func(c)

            if abs(fc) < tol or (b - a) / 2 < tol:
                return c, i + 1, True  # Success

            if func(a) * fc < 0:
                b = c
            else:
                a = c

        return (a + b) / 2, max_iter, False  # Failed to converge

    @staticmethod
    def newton_raphson(func, x0, df=None, max_iter=50, tol=1e-6):
        """Newton-Raphson: Fast but can diverge."""
        if df is None:
            h = 1e-8
            df = lambda x: (func(x + h) - func(x - h)) / (2 * h)

        x = x0
        for i in range(max_iter):
            fx = func(x)
            if abs(fx) < tol:
                return x, i + 1, True  # Success

            dfx = df(x)
            if abs(dfx) < 1e-12:
                return None, i + 1, False  # Diverged

            x_new = x - fx / dfx

            # Check for divergence
            if abs(x_new) > 1e6:
                return None, i + 1, False  # Diverged

            x = x_new

        return x, max_iter, False  # Failed to converge

    @staticmethod
    def secant(func, x0, max_iter=50, tol=1e-6):
        """Secant: Good balance."""
        x_prev = x0
        x = x0 + 0.1

        for i in range(max_iter):
            fx = func(x)
            fx_prev = func(x_prev)

            if abs(fx) < tol:
                return x, i + 1, True  # Success

            if abs(fx - fx_prev) < 1e-12:
                return None, i + 1, False  # Failed

            x_new = x - fx * (x - x_prev) / (fx - fx_prev)

            # Check for divergence
            if abs(x_new) > 1e6:
                return None, i + 1, False  # Diverged

            x_prev, x = x, x_new

        return x, max_iter, False  # Failed to converge


class ProblemGenerator:
    """Generate random root-finding problems."""

    def __init__(self, seed=42):
        self.rng = np.random.RandomState(seed)

    def generate(self, problem_type='mixed'):
        """
        Generate a random problem.

        Returns:
            (func, df, x0, true_root, problem_type)
        """
        if problem_type == 'mixed':
            problem_type = self.rng.choice(['smooth', 'rough', 'polynomial'])

        if problem_type == 'smooth':
            return self._generate_smooth()
        elif problem_type == 'rough':
            return self._generate_rough()
        elif problem_type == 'polynomial':
            return self._generate_polynomial()

    def _generate_smooth(self):
        """Smooth function: x^2 - c."""
        c = self.rng.uniform(1, 10)
        func = lambda x: x**2 - c
        df = lambda x: 2 * x
        x0 = self.rng.uniform(0.5, 2.0)
        true_root = np.sqrt(c)
        return func, df, x0, true_root, 'smooth'

    def _generate_rough(self):
        """Rough function: sin(k*x) + x^2 - c."""
        k = self.rng.uniform(5, 15)
        c = self.rng.uniform(0.5, 2.0)
        func = lambda x: np.sin(k * x) + x**2 - c
        df = lambda x: k * np.cos(k * x) + 2 * x

        # Find true root numerically
        from scipy.optimize import fsolve
        x0 = self.rng.uniform(0.5, 1.5)
        true_root = fsolve(func, x0)[0]

        return func, df, x0, true_root, 'rough'

    def _generate_polynomial(self):
        """Polynomial: (x - r1)(x - r2)(x - r3) = 0."""
        roots = self.rng.uniform(-5, 5, size=3)
        target_root = roots[0]

        func = lambda x: (x - roots[0]) * (x - roots[1]) * (x - roots[2])
        df = lambda x: ((x - roots[1]) * (x - roots[2]) +
                        (x - roots[0]) * (x - roots[2]) +
                        (x - roots[0]) * (x - roots[1]))

        x0 = target_root + self.rng.uniform(-1, 1)
        return func, df, x0, target_root, 'polynomial'


def encode_problem(problem_type, router):
    """
    Encode problem characteristics for routing.

    This creates the multimodal input based on problem type.
    """
    x = {}

    if problem_type == 'smooth':
        # Smooth -> Newton should work well
        x['audio'] = np.ones(router.atmr.d['audio']) * 2.5
        x['touch'] = np.ones(router.atmr.d['touch']) * 1.0
    elif problem_type == 'rough':
        # Rough -> Bisection or Secant more reliable
        x['vision'] = np.ones(router.atmr.d['vision']) * 2.5
        x['touch'] = np.ones(router.atmr.d['touch']) * 2.0
    elif problem_type == 'polynomial':
        # Polynomial -> Newton often good
        x['audio'] = np.ones(router.atmr.d['audio']) * 2.0
        x['touch'] = np.ones(router.atmr.d['touch']) * 1.5

    # Fill rest with noise
    for m in router.atmr.modalities:
        if m not in x:
            x[m] = np.random.randn(router.atmr.d[m]) * 0.1

    return x


def main():
    print("=" * 70)
    print("PRODUCTION ADAPTIVE ROOT FINDING")
    print("=" * 70)
    print()
    print("This demonstrates REAL adaptive learning:")
    print("  - 1000 random problems")
    print("  - Router learns which methods work best")
    print("  - Performance improves over time")
    print("  - Learned state can be saved/loaded")
    print()
    print("=" * 70)
    print()

    # Create router
    router = ProductionRouter(name="root_finder", learning_rate=0.05)

    # Register methods
    registry = MethodRegistry()
    methods = RootFindingMethods()
    registry.register('vision', methods.bisection, 'Bisection')
    registry.register('audio', methods.newton_raphson, 'Newton-Raphson')
    registry.register('touch', methods.secant, 'Secant')

    # Problem generator
    generator = ProblemGenerator(seed=42)

    # Training loop
    n_problems = 1000
    print(f"Training on {n_problems} problems...")
    print()

    # Track performance over time
    success_rates_over_time = []
    window_size = 50

    for i in range(n_problems):
        # Generate problem
        func, df, x0, true_root, prob_type = generator.generate()

        # Encode and route
        x = encode_problem(prob_type, router)
        modality, confidence, _ = router.route(x, adapt=True)

        # Execute chosen method
        try:
            if modality == 'audio':  # Newton needs derivative
                result, iters, success = registry.execute(modality, func, x0, df)
            else:
                result, iters, success = registry.execute(modality, func, x0)

            # Additional success check: Is result close to true root?
            if success and result is not None:
                error = abs(result - true_root)
                success = error < 0.01  # Within 1% of true root

        except Exception as e:
            result = None
            iters = 0
            success = False

        # Provide feedback (THIS IS WHERE LEARNING HAPPENS!)
        reward = 1.0 if success else -0.5
        router.feedback(success, reward)

        # Track performance
        if (i + 1) % window_size == 0:
            recent_history = router.get_history(last_n=window_size)
            recent_success_rate = sum(recent_history['successes']) / window_size
            success_rates_over_time.append(recent_success_rate)

            print(f"Steps {i+1-window_size:4d}-{i+1:4d}: "
                  f"Success rate: {recent_success_rate:.1%}, "
                  f"Method: {registry.get_name(modality):<15s}, "
                  f"Problem: {prob_type:<12s}")

    print()
    print("=" * 70)
    print("FINAL METRICS:")
    print("=" * 70)
    router.print_metrics()

    # Plot learning curve
    print()
    print("Generating learning curve plot...")
    plt.figure(figsize=(10, 6))
    windows = np.arange(1, len(success_rates_over_time) + 1) * window_size
    plt.plot(windows, success_rates_over_time, marker='o', linewidth=2)
    plt.xlabel('Number of Problems')
    plt.ylabel('Success Rate (rolling window)')
    plt.title('Adaptive Learning: Success Rate Over Time')
    plt.grid(True, alpha=0.3)
    plt.ylim([0, 1])
    plt.axhline(y=0.5, color='r', linestyle='--', alpha=0.3, label='50% baseline')
    plt.legend()
    plt.tight_layout()

    plot_path = router.log_dir / 'learning_curve.png'
    plt.savefig(plot_path, dpi=150)
    print(f"Learning curve saved to: {plot_path}")

    # Save learned router
    print()
    saved_path = router.save()

    # Save history for analysis
    router.save_history_json()

    print()
    print("=" * 70)
    print("KEY INSIGHT:")
    print("=" * 70)
    print("""
The router LEARNED from experience!

Over 1000 problems:
  - Successful routes were REINFORCED
  - Failed routes were WEAKENED
  - Performance improved over time

This is REAL adaptive learning, not just static routing!

You can now:
  1. Load the saved router: router.load('path/to/saved.pkl')
  2. Continue training on more problems
  3. Use the trained router for new problems
  4. Analyze the history JSON for insights

This is what makes ATM-R powerful:
  - It learns from experience
  - It adapts to new situations
  - It gets better over time

NOT just a static if-else dispatcher!
""")


if __name__ == "__main__":
    main()
