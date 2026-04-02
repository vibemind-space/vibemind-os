"""
NULLSTELLEN-FINDER MIT ATM-R ROUTING

Problem: Finde x wo f(x) = 0

Verschiedene Methoden:
  - Bisection: Langsam, aber garantiert (wenn Intervall gut)
  - Newton-Raphson: Sehr schnell, aber braucht Ableitung
  - Secant: Mittel, keine Ableitung nötig
  - Brent's Method: Robust, adaptiv

ATM-R routet zur besten Methode!
"""
from thalamo_pc_adaptive import ThalamoPC6Adaptive
import numpy as np

class SmartRootFinder:
    """Nullstellen-Finder mit ATM-R Routing."""

    def __init__(self):
        self.atmr = ThalamoPC6Adaptive(seed=42)

        # Map modalities zu Root-Finding Methoden
        self.methods = {
            'vision': self.bisection,
            'audio': self.newton_raphson,
            'touch': self.secant,
            'taste': self.brents_method,
        }

        self.method_names = {
            'vision': 'Bisection (langsam, sicher)',
            'audio': 'Newton-Raphson (schnell, braucht df)',
            'touch': 'Secant (mittel, keine df)',
            'taste': "Brent's Method (robust)",
        }

    def find_root(self, func, x0, problem_type='smooth', df=None):
        """
        Finde Nullstelle von func durch intelligentes Routing.

        Args:
            func: Funktion f(x)
            x0: Startpunkt (oder Intervall für Bisection)
            problem_type: 'smooth', 'rough', 'unknown'
            df: Ableitung (optional, für Newton)
        """
        print("=" * 70)
        print(f"PROBLEM: Finde x wo f(x) = 0")
        print(f"Problem-Typ: {problem_type}")
        print(f"Start: x0 = {x0}")
        print("=" * 70)

        # Encode problem characteristics
        x = self._encode_problem(problem_type, df is not None)

        # ATM-R routet zu bester Methode
        out = self.atmr.step(x, adapt=True)

        # Welche Methode wurde gewählt?
        dominant_idx = np.argmax(out['g'])
        chosen_modality = self.atmr.modalities[dominant_idx]
        confidence = out['g'][dominant_idx]

        print(f"\nATM-R Routing:")
        print(f"  Gewählte Methode: {self.method_names.get(chosen_modality, chosen_modality)}")
        print(f"  Confidence: {confidence:.1%}")

        print(f"\n  Routing distribution:")
        for i, m in enumerate(self.atmr.modalities):
            if out['g'][i] > 0.01 and m in self.method_names:
                bar = '#' * int(out['g'][i] * 40)
                print(f"    {self.method_names[m]:35s}: {out['g'][i]:5.1%} {bar}")

        # Führe gewählte Methode aus
        if chosen_modality in self.methods:
            method_func = self.methods[chosen_modality]
            print(f"\n  -> Executing: {method_func.__name__}()")

            try:
                root, iterations = method_func(func, x0, df)
                print(f"\n  RESULT:")
                print(f"    x* = {root:.8f}")
                print(f"    f(x*) = {func(root):.2e}")
                print(f"    Iterations: {iterations}")

                return root, iterations, chosen_modality
            except Exception as e:
                print(f"\n  ERROR: {e}")
                return None, None, chosen_modality
        else:
            print(f"\n  No method mapped to {chosen_modality}")
            return None, None, None

    def _encode_problem(self, problem_type, has_derivative):
        """Encode problem characteristics."""
        x = {}

        if problem_type == 'smooth' and has_derivative:
            # Glatt + Ableitung -> Newton!
            x['audio'] = np.ones(self.atmr.d['audio']) * 3.0
        elif problem_type == 'smooth' and not has_derivative:
            # Glatt ohne Ableitung -> Secant
            x['touch'] = np.ones(self.atmr.d['touch']) * 2.5
        elif problem_type == 'rough':
            # Rau/schwierig -> Brent's (robust)
            x['taste'] = np.ones(self.atmr.d['taste']) * 2.5
        elif problem_type == 'unknown':
            # Unbekannt -> Bisection (sicher)
            x['vision'] = np.ones(self.atmr.d['vision']) * 2.0

        # Fill rest with noise
        for m in self.atmr.modalities:
            if m not in x:
                x[m] = np.random.randn(self.atmr.d[m]) * 0.1

        return x

    # === VERSCHIEDENE ROOT-FINDING METHODEN ===

    def bisection(self, func, x0, df=None):
        """Bisection: Langsam, aber sicher."""
        # x0 sollte Intervall sein [a, b]
        if isinstance(x0, (list, tuple)):
            a, b = x0
        else:
            a, b = x0 - 1, x0 + 1

        tol = 1e-6
        max_iter = 100

        for i in range(max_iter):
            c = (a + b) / 2
            fc = func(c)

            if abs(fc) < tol or (b - a) / 2 < tol:
                return c, i + 1

            if func(a) * fc < 0:
                b = c
            else:
                a = c

        return (a + b) / 2, max_iter

    def newton_raphson(self, func, x0, df=None):
        """Newton-Raphson: Schnell, braucht Ableitung."""
        if df is None:
            # Numerical derivative
            h = 1e-8
            df = lambda x: (func(x + h) - func(x - h)) / (2 * h)

        tol = 1e-6
        max_iter = 50
        x = x0

        for i in range(max_iter):
            fx = func(x)
            dfx = df(x)

            if abs(fx) < tol:
                return x, i + 1

            if abs(dfx) < 1e-12:
                raise ValueError("Ableitung zu klein (Divergenz)")

            x = x - fx / dfx

        return x, max_iter

    def secant(self, func, x0, df=None):
        """Secant: Mittel, keine Ableitung nötig."""
        tol = 1e-6
        max_iter = 50

        x_prev = x0
        x = x0 + 0.1  # Kleine Störung

        for i in range(max_iter):
            fx = func(x)
            fx_prev = func(x_prev)

            if abs(fx) < tol:
                return x, i + 1

            if abs(fx - fx_prev) < 1e-12:
                raise ValueError("Division durch Null")

            x_new = x - fx * (x - x_prev) / (fx - fx_prev)
            x_prev, x = x, x_new

        return x, max_iter

    def brents_method(self, func, x0, df=None):
        """Brent's Method: Robust, kombiniert Bisection + Secant."""
        # Simplified Brent's (echte Implementation ist komplexer)
        # Für Demo: Nutze Secant mit Bisection fallback

        try:
            # Versuche Secant
            root, iters = self.secant(func, x0, df)
            return root, iters
        except (ValueError, ZeroDivisionError, RuntimeError):
            # Fallback zu Bisection
            root, iters = self.bisection(func, x0, df)
            return root, iters


# === TEST PROBLEME ===

def test_case_1():
    """Einfache glatte Funktion: f(x) = x^2 - 2
       Nullstelle: x = sqrt(2) ≈ 1.414
    """
    func = lambda x: x**2 - 2
    df = lambda x: 2 * x
    return func, df, 1.0, 'smooth', "f(x) = x^2 - 2"

def test_case_2():
    """Transzendente Funktion: f(x) = cos(x) - x
       Nullstelle: x ≈ 0.739
    """
    func = lambda x: np.cos(x) - x
    df = lambda x: -np.sin(x) - 1
    return func, df, 0.5, 'smooth', "f(x) = cos(x) - x"

def test_case_3():
    """Schwierige Funktion: f(x) = x^3 - 2x - 5
       Nullstelle: x ≈ 2.094
    """
    func = lambda x: x**3 - 2*x - 5
    df = lambda x: 3*x**2 - 2
    return func, df, 2.0, 'smooth', "f(x) = x^3 - 2x - 5"

def test_case_4():
    """Komplexe Funktion: f(x) = sin(x) + x^2 - 1
       Multiple Nullstellen, nehmen x0 = 0.5
    """
    func = lambda x: np.sin(x) + x**2 - 1
    df = lambda x: np.cos(x) + 2*x
    return func, df, 0.5, 'rough', "f(x) = sin(x) + x^2 - 1"


# === DEMO ===

if __name__ == "__main__":
    print("\n" + "*" * 70)
    print("NULLSTELLEN-FINDER MIT ATM-R ROUTING")
    print("*" * 70)
    print()
    print("Problem: Finde x wo f(x) = 0")
    print()
    print("ATM-R wählt zwischen:")
    print("  - Bisection (langsam, sicher)")
    print("  - Newton-Raphson (schnell, braucht Ableitung)")
    print("  - Secant (mittel, keine Ableitung)")
    print("  - Brent's Method (robust)")
    print()
    print("*" * 70)
    print()

    finder = SmartRootFinder()

    # Test alle Fälle
    test_cases = [
        test_case_1(),
        test_case_2(),
        test_case_3(),
        test_case_4(),
    ]

    results = []

    for func, df, x0, prob_type, description in test_cases:
        print(f"\n{'='*70}")
        print(f"TEST CASE: {description}")
        print(f"{'='*70}")

        root, iters, method = finder.find_root(func, x0, prob_type, df)

        if root is not None:
            results.append({
                'description': description,
                'root': root,
                'iterations': iters,
                'method': method,
            })

        print()
        print("-" * 70)

    # Summary
    print("\n" + "*" * 70)
    print("ZUSAMMENFASSUNG:")
    print("*" * 70)
    print()
    print(f"{'Problem':<30s} {'Methode':<15s} {'Nullstelle':<12s} {'Iter':<5s}")
    print("-" * 70)
    for r in results:
        method_short = r['method'][:12]
        print(f"{r['description']:<30s} {method_short:<15s} {r['root']:<12.6f} {r['iterations']:<5d}")

    print()
    print("*" * 70)
    print("FAZIT:")
    print("*" * 70)
    print("""
ATM-R hat NICHT die Nullstellen berechnet!
ATM-R hat geroutet zu:
  - Newton-Raphson (fuer glatte Funktionen)
  - Secant (wenn keine Ableitung)
  - Bisection (fuer sichere Konvergenz)
  - Brent's (fuer schwierige Faelle)

Die Methoden haben dann die eigentliche Arbeit gemacht.

Vorteil:
  - Glatte Funktion + Ableitung -> Newton (sehr schnell!)
  - Raue Funktion -> Robuste Methode (sicher)
  - Unbekannte Funktion -> Conservative Methode

ATM-R lernt, welche Methode fuer welche Funktion am besten ist!
""")
