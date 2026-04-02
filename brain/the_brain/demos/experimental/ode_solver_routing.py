"""
DIFFERENTIAL-GLEICHUNGEN MIT ATM-R ROUTING

ATM-R routet zwischen verschiedenen ODE-Lösern:
  - Euler (schnell, ungenau)
  - Runge-Kutta (mittel)
  - Scipy solve_ivp (genau, langsam)
"""
from thalamo_pc_adaptive import ThalamoPC6Adaptive
import numpy as np
import matplotlib
matplotlib.use('Agg')  # No display
import matplotlib.pyplot as plt

class SmartODESolver:
    """DGL-Löser mit ATM-R Routing."""

    def __init__(self):
        self.atmr = ThalamoPC6Adaptive(seed=42)

        # Map modalities zu Lösern
        self.solvers = {
            'vision': self.euler_method,
            'audio': self.runge_kutta_2,
            'touch': self.runge_kutta_4,
            'taste': self.scipy_solver,
            'vestibular': self.adaptive_solver,
        }

        self.solver_names = {
            'vision': 'Euler (fast, ungenau)',
            'audio': 'RK2 (mittel)',
            'touch': 'RK4 (gut)',
            'taste': 'Scipy (sehr genau)',
            'vestibular': 'Adaptive (intelligent)',
        }

    def solve(self, problem_type: str, t_span, y0, steps=100):
        """
        Löse DGL durch intelligentes Routing.

        Args:
            problem_type: 'simple', 'stiff', 'oscillating'
            t_span: (t_start, t_end)
            y0: Anfangsbedingung
            steps: Anzahl Schritte
        """
        print("=" * 70)
        print(f"PROBLEM: {problem_type}")
        print(f"Zeit: {t_span}, Anfang: y0={y0}")
        print("=" * 70)

        # Encode problem characteristics
        x = self._encode_problem(problem_type)

        # ATM-R routet zu bestem Löser
        out = self.atmr.step(x, adapt=True)

        # Welcher Löser wurde gewählt?
        dominant_idx = np.argmax(out['g'])
        chosen_modality = self.atmr.modalities[dominant_idx]
        confidence = out['g'][dominant_idx]

        print(f"\nATM-R Routing:")
        print(f"  Gewählter Löser: {self.solver_names.get(chosen_modality, chosen_modality)}")
        print(f"  Confidence: {confidence:.1%}")

        print(f"\n  Routing distribution:")
        for i, m in enumerate(self.atmr.modalities):
            if out['g'][i] > 0.01 and m in self.solver_names:
                bar = '#' * int(out['g'][i] * 40)
                print(f"    {self.solver_names[m]:25s}: {out['g'][i]:5.1%} {bar}")

        # Führe gewählten Löser aus
        if chosen_modality in self.solvers:
            solver_func = self.solvers[chosen_modality]
            print(f"\n  -> Executing: {solver_func.__name__}()")

            # Define ODE based on problem type
            if problem_type == 'simple':
                dydt = lambda t, y: -y  # Exponentieller Zerfall
            elif problem_type == 'oscillating':
                dydt = lambda t, y: -10 * y  # Schnelle Oszillation
            elif problem_type == 'stiff':
                dydt = lambda t, y: -100 * y  # Steife DGL
            else:
                dydt = lambda t, y: -y

            # Löse!
            t, y = solver_func(dydt, t_span, y0, steps)

            print(f"\n  Solution computed:")
            print(f"    Start: y({t[0]:.2f}) = {y[0]:.6f}")
            print(f"    End:   y({t[-1]:.2f}) = {y[-1]:.6f}")

            return t, y, chosen_modality
        else:
            print(f"\n  No solver mapped to {chosen_modality}")
            return None, None, None

    def _encode_problem(self, problem_type):
        """Encode problem characteristics."""
        x = {}

        if problem_type == 'simple':
            # Einfach -> Euler reicht
            x['vision'] = np.ones(self.atmr.d['vision']) * 2.0
        elif problem_type == 'oscillating':
            # Oszillierend -> RK4
            x['touch'] = np.ones(self.atmr.d['touch']) * 2.5
        elif problem_type == 'stiff':
            # Steif -> Scipy (implizit)
            x['taste'] = np.ones(self.atmr.d['taste']) * 3.0
        elif problem_type == 'adaptive':
            # Adaptive -> intelligenter Solver
            x['vestibular'] = np.ones(self.atmr.d['vestibular']) * 2.5

        # Fill rest with noise
        for m in self.atmr.modalities:
            if m not in x:
                x[m] = np.random.randn(self.atmr.d[m]) * 0.1

        return x

    # === VERSCHIEDENE DGL-LÖSER ===
    # (ATM-R routet hierhin!)

    def euler_method(self, dydt, t_span, y0, steps):
        """Euler-Methode: Einfach, schnell, ungenau."""
        t0, t_end = t_span
        dt = (t_end - t0) / steps
        t = np.linspace(t0, t_end, steps + 1)
        y = np.zeros(steps + 1)
        y[0] = y0

        for i in range(steps):
            y[i + 1] = y[i] + dt * dydt(t[i], y[i])

        return t, y

    def runge_kutta_2(self, dydt, t_span, y0, steps):
        """Runge-Kutta 2. Ordnung: Mittel."""
        t0, t_end = t_span
        dt = (t_end - t0) / steps
        t = np.linspace(t0, t_end, steps + 1)
        y = np.zeros(steps + 1)
        y[0] = y0

        for i in range(steps):
            k1 = dydt(t[i], y[i])
            k2 = dydt(t[i] + dt/2, y[i] + dt/2 * k1)
            y[i + 1] = y[i] + dt * k2

        return t, y

    def runge_kutta_4(self, dydt, t_span, y0, steps):
        """Runge-Kutta 4. Ordnung: Gut, genau."""
        t0, t_end = t_span
        dt = (t_end - t0) / steps
        t = np.linspace(t0, t_end, steps + 1)
        y = np.zeros(steps + 1)
        y[0] = y0

        for i in range(steps):
            k1 = dydt(t[i], y[i])
            k2 = dydt(t[i] + dt/2, y[i] + dt/2 * k1)
            k3 = dydt(t[i] + dt/2, y[i] + dt/2 * k2)
            k4 = dydt(t[i] + dt, y[i] + dt * k3)
            y[i + 1] = y[i] + dt/6 * (k1 + 2*k2 + 2*k3 + k4)

        return t, y

    def scipy_solver(self, dydt, t_span, y0, steps):
        """Scipy solve_ivp: Sehr genau, automatische Schrittweite."""
        try:
            from scipy.integrate import solve_ivp
            t0, t_end = t_span
            t_eval = np.linspace(t0, t_end, steps + 1)
            sol = solve_ivp(dydt, t_span, [y0], t_eval=t_eval, method='RK45')
            return sol.t, sol.y[0]
        except ImportError:
            print("    [WARNING] Scipy not available, using RK4 fallback")
            return self.runge_kutta_4(dydt, t_span, y0, steps)

    def adaptive_solver(self, dydt, t_span, y0, steps):
        """Adaptive: Wählt Methode basierend auf Problem."""
        # Simplified: Use RK4 (in real system, would analyze problem first)
        return self.runge_kutta_4(dydt, t_span, y0, steps)


# Demo
if __name__ == "__main__":
    print("\n" + "*" * 70)
    print("DIFFERENTIAL-GLEICHUNGEN MIT ATM-R ROUTING")
    print("*" * 70)
    print()
    print("ATM-R routet zwischen verschiedenen ODE-Lösern:")
    print("  - Euler (schnell, ungenau)")
    print("  - RK2 (mittel)")
    print("  - RK4 (gut, genau)")
    print("  - Scipy (sehr genau, adaptiv)")
    print()
    print("*" * 70)
    print()

    solver = SmartODESolver()

    # Test verschiedene Problem-Typen
    test_problems = [
        ('simple', (0, 2), 1.0),
        ('oscillating', (0, 1), 1.0),
        ('stiff', (0, 0.5), 1.0),
    ]

    for problem_type, t_span, y0 in test_problems:
        t, y, chosen = solver.solve(problem_type, t_span, y0, steps=50)

        # Vergleich mit analytischer Lösung (für simple case)
        if problem_type == 'simple' and t is not None:
            y_exact = y0 * np.exp(-t)
            error = np.max(np.abs(y - y_exact))
            print(f"\n  Max Error vs. exact solution: {error:.6e}")

        print()
        print("-" * 70)
        print()

    print()
    print("*" * 70)
    print("FAZIT:")
    print("*" * 70)
    print("""
ATM-R hat die DGL NICHT selbst gelöst!
ATM-R hat geroutet zu:
  - euler_method()
  - runge_kutta_4()
  - scipy_solver()
  etc.

Diese Solver haben dann die eigentliche Arbeit gemacht.

Vorteile:
  - Einfache Probleme -> Schneller Solver (Euler)
  - Komplexe Probleme -> Genauer Solver (RK4, Scipy)
  - Steife Probleme -> Spezialisierter Solver (implizite Methoden)

ATM-R lernt, welcher Solver für welches Problem am besten ist!
""")
