"""
TASCHENRECHNER MIT ATM-R ROUTING

ATM-R routet zu den richtigen Operationen (+, -, *, /)
Die Operationen machen dann die eigentliche Berechnung!
"""
from thalamo_pc_adaptive import ThalamoPC6Adaptive
import numpy as np
import re

class SmartCalculator:
    """Taschenrechner mit ATM-R Routing."""

    def __init__(self):
        self.atmr = ThalamoPC6Adaptive(seed=42)

        # Map modalities zu Rechenoperationen
        self.operations = {
            'vision': self.add,       # vision = Addition
            'audio': self.subtract,   # audio = Subtraktion
            'touch': self.multiply,   # touch = Multiplikation
            'taste': self.divide,     # taste = Division
            'vestibular': self.power, # vestibular = Potenz
            'threat': self.verify     # threat = Verifikation
        }

    def calculate(self, expression: str):
        """Berechne einen Ausdruck durch Routing."""
        print("=" * 70)
        print(f"Expression: {expression}")
        print("=" * 70)

        # Parse Expression (einfach)
        numbers, operation = self._parse(expression)

        if numbers is None:
            print("ERROR: Could not parse expression")
            return None

        a, b = numbers
        print(f"Parsed: {a} {operation} {b}")
        print()

        # Encode: Welche Operation ist es?
        x = self._encode_operation(operation)

        # ATM-R routet zur richtigen Operation
        out = self.atmr.step(x, adapt=True)

        # Welche Operation wurde gewählt?
        dominant_idx = np.argmax(out['g'])
        chosen_modality = self.atmr.modalities[dominant_idx]
        confidence = out['g'][dominant_idx]

        print(f"ATM-R Routing:")
        print(f"  Chosen operation: {chosen_modality} (confidence: {confidence:.1%})")

        # Zeige Routing-Verteilung
        print(f"\n  Routing distribution:")
        for i, m in enumerate(self.atmr.modalities):
            if out['g'][i] > 0.01:
                bar = '#' * int(out['g'][i] * 40)
                op_name = self.operations[m].__name__
                print(f"    {m:12s} ({op_name:8s}): {out['g'][i]:5.1%} {bar}")

        # Führe Operation aus
        if chosen_modality in self.operations:
            operation_func = self.operations[chosen_modality]
            result = operation_func(a, b)
            print(f"\nResult: {result}")
            print("=" * 70)
            return result
        else:
            print(f"\nNo operation mapped to {chosen_modality}")
            return None

    def _parse(self, expression: str):
        """Parse expression like '1 + 6' into (1, 6, '+')."""
        # Simple regex parser
        match = re.match(r'(\d+\.?\d*)\s*([+\-*/^])\s*(\d+\.?\d*)', expression.strip())
        if match:
            a = float(match.group(1))
            op = match.group(2)
            b = float(match.group(3))
            return (a, b), op
        return None, None

    def _encode_operation(self, operation: str):
        """Encode operation type as multimodal signal."""
        # Different operations activate different modalities
        x = {}

        if operation == '+':
            # Addition -> vision
            x['vision'] = np.ones(self.atmr.d['vision']) * 3.0
        elif operation == '-':
            # Subtraktion -> audio
            x['audio'] = np.ones(self.atmr.d['audio']) * 3.0
        elif operation == '*':
            # Multiplikation -> touch
            x['touch'] = np.ones(self.atmr.d['touch']) * 3.0
        elif operation == '/':
            # Division -> taste
            x['taste'] = np.ones(self.atmr.d['taste']) * 3.0
        elif operation == '^':
            # Potenz -> vestibular
            x['vestibular'] = np.ones(self.atmr.d['vestibular']) * 3.0
        else:
            # Unknown -> equal distribution
            pass

        # Fill other modalities with noise
        for m in self.atmr.modalities:
            if m not in x:
                x[m] = np.random.randn(self.atmr.d[m]) * 0.1

        return x

    # Die eigentlichen Rechenoperationen
    # (ATM-R routet hierhin!)

    def add(self, a, b):
        """Addition."""
        print(f"\n  -> Executing: add({a}, {b})")
        return a + b

    def subtract(self, a, b):
        """Subtraktion."""
        print(f"\n  -> Executing: subtract({a}, {b})")
        return a - b

    def multiply(self, a, b):
        """Multiplikation."""
        print(f"\n  -> Executing: multiply({a}, {b})")
        return a * b

    def divide(self, a, b):
        """Division."""
        print(f"\n  -> Executing: divide({a}, {b})")
        if b == 0:
            return "Error: Division by zero"
        return a / b

    def power(self, a, b):
        """Potenz."""
        print(f"\n  -> Executing: power({a}, {b})")
        return a ** b

    def verify(self, a, b):
        """Verifikation (Dummy)."""
        print(f"\n  -> Executing: verify({a}, {b})")
        return f"Verified: {a} and {b}"


# Demo
if __name__ == "__main__":
    calc = SmartCalculator()

    # Test verschiedene Operationen
    test_cases = [
        "1 + 6",
        "10 - 3",
        "5 * 8",
        "20 / 4",
        "2 ^ 10",
    ]

    print()
    print("*" * 70)
    print("SMART CALCULATOR WITH ATM-R ROUTING")
    print("*" * 70)
    print()
    print("ATM-R routet zu den Operationen:")
    print("  vision      -> Addition (+)")
    print("  audio       -> Subtraktion (-)")
    print("  touch       -> Multiplikation (*)")
    print("  taste       -> Division (/)")
    print("  vestibular  -> Potenz (^)")
    print()
    print("*" * 70)
    print()

    for expr in test_cases:
        result = calc.calculate(expr)
        print()

    print()
    print("*" * 70)
    print("ZUSAMMENFASSUNG:")
    print("*" * 70)
    print("""
ATM-R hat die Operationen NICHT selbst ausgeführt!
ATM-R hat nur GEROUTET zu:
  - add()
  - subtract()
  - multiply()
  - divide()
  - power()

Diese Funktionen haben dann gerechnet.

Das ist wie ein Dispatcher:
  Expression kommt rein -> ATM-R routet -> Operation rechnet

Vorteile:
  - Du könntest verschiedene Implementierungen haben
    (z.B. schnelle Addition vs. genaue Addition)
  - ATM-R lernt, welche Operation für welchen Fall besser ist
  - Du könntest Operationen austauschen, ohne ATM-R zu ändern
""")
