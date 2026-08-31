"""
ATM-R Real-Time Monitoring Dashboard

Provides live visualization of:
- Gate weights (attention allocation)
- Agent activity over time
- Prediction errors (novelty)
- System health metrics
- Decision confidence
"""

import numpy as np
from collections import deque
import time
from datetime import datetime
import os
import sys

class ATMRMonitor:
    """
    Real-time monitoring for ATM-R routing decisions.

    Usage:
        monitor = ATMRMonitor(atmr_instance)

        # In your processing loop:
        out = atmr.step(x_t)
        monitor.update(out)
        monitor.display()  # Terminal dashboard
    """

    def __init__(self, atmr, history_length=100):
        self.atmr = atmr
        self.modalities = atmr.modalities
        self.M = len(self.modalities)

        # History buffers
        self.history_length = history_length
        self.gate_history = deque(maxlen=history_length)
        self.pe_history = deque(maxlen=history_length)
        self.confidence_history = deque(maxlen=history_length)
        self.dominant_history = deque(maxlen=history_length)

        # Statistics
        self.total_steps = 0
        self.start_time = time.time()

        # Current state
        self.current_gates = None
        self.current_pe = None
        self.current_dominant = None
        self.current_confidence = 0.0

    def update(self, atmr_output):
        """Update monitor with new ATM-R output."""
        gates = atmr_output['g']
        pe = atmr_output.get('pe', {m: 0.0 for m in self.modalities})

        # Update current state
        self.current_gates = gates.copy()
        self.current_pe = pe
        self.current_dominant = self.modalities[np.argmax(gates)]
        self.current_confidence = float(np.max(gates))

        # Update history
        self.gate_history.append(gates.copy())
        self.pe_history.append([pe[m] for m in self.modalities])
        self.confidence_history.append(self.current_confidence)
        self.dominant_history.append(self.current_dominant)

        self.total_steps += 1

    def display(self, clear_screen=True):
        """Display terminal-based dashboard."""
        if clear_screen:
            os.system('cls' if os.name == 'nt' else 'clear')

        # Header
        runtime = time.time() - self.start_time
        print("="*80)
        print(f"ATM-R MONITORING DASHBOARD".center(80))
        print(f"Runtime: {runtime:.1f}s | Steps: {self.total_steps} | {datetime.now().strftime('%H:%M:%S')}".center(80))
        print("="*80)

        if self.current_gates is None:
            print("\nWaiting for data...")
            return

        # Current Gates (Bar Chart)
        print("\n[CURRENT GATE WEIGHTS - Agent Attention Allocation]")
        print("-"*80)

        for i, mod in enumerate(self.modalities):
            gate_val = self.current_gates[i]
            bar_length = int(gate_val * 50)
            bar = "#" * bar_length

            # Color coding (simulate with symbols)
            status = ""
            if gate_val > 0.5:
                status = "<<< DOMINANT"
            elif gate_val > 0.2:
                status = "<-- ACTIVE"
            elif gate_val > 0.05:
                status = "- active"

            print(f"  {mod:12s} [{gate_val:5.1%}] {bar:50s} {status}")

        print(f"\n  Dominant Agent: {self.current_dominant.upper()}")
        print(f"  Confidence: {self.current_confidence:.1%}")

        # Prediction Errors (Novelty)
        print("\n[PREDICTION ERRORS - Novelty/Surprise Signals]")
        print("-"*80)

        for i, mod in enumerate(self.modalities):
            pe_val = self.current_pe.get(mod, 0.0)
            bar_length = int(min(pe_val / 5.0, 1.0) * 30)  # Scale to 0-5
            bar = "*" * bar_length

            alert = " <!> HIGH NOVELTY" if pe_val > 3.0 else ""
            print(f"  {mod:12s} [{pe_val:6.2f}] {bar:30s}{alert}")

        # Agent Activity Over Time
        if len(self.gate_history) > 10:
            print("\n[AGENT ACTIVITY TIMELINE - Last 50 steps]")
            print("-"*80)

            # Show last 50 steps as mini sparkline
            recent_gates = list(self.gate_history)[-50:]

            for i, mod in enumerate(self.modalities):
                timeline = ""
                for gates in recent_gates:
                    if gates[i] > 0.5:
                        timeline += "#"
                    elif gates[i] > 0.2:
                        timeline += "="
                    elif gates[i] > 0.05:
                        timeline += "-"
                    else:
                        timeline += "."

                avg_attention = np.mean([g[i] for g in recent_gates])
                print(f"  {mod:12s} [{avg_attention:5.1%}] {timeline}")

            print(f"                        {'Past':>25}{'Present':>23}")

        # Statistics
        print("\n[STATISTICS]")
        print("-"*80)

        if len(self.gate_history) > 1:
            # Average gates
            avg_gates = np.mean(np.array(list(self.gate_history)), axis=0)

            # Compute metrics
            avg_confidence = np.mean(list(self.confidence_history))
            gate_entropy = self._compute_entropy(self.current_gates)
            avg_entropy = np.mean([self._compute_entropy(g) for g in self.gate_history])

            # Agent usage distribution
            from collections import Counter
            dominant_counts = Counter(self.dominant_history)

            print(f"  Average Confidence:  {avg_confidence:.1%}")
            print(f"  Current Entropy:     {gate_entropy:.2f} bits")
            print(f"  Average Entropy:     {avg_entropy:.2f} bits (higher = more distributed)")
            print(f"  Steps/second:        {self.total_steps/runtime:.1f}")

            print("\n  Agent Usage Distribution:")
            for mod in self.modalities:
                count = dominant_counts.get(mod, 0)
                pct = count / len(self.dominant_history) * 100
                bar = "=" * int(pct / 2)
                print(f"    {mod:12s}: {pct:5.1f}% {bar}")

            print("\n  Average Attention Allocation:")
            for i, mod in enumerate(self.modalities):
                print(f"    {mod:12s}: {avg_gates[i]:5.1%}")

        # Health Indicators
        print("\n[HEALTH INDICATORS]")
        print("-"*80)

        health_checks = []

        # Check 1: Gates sum to 1.0
        gate_sum = np.sum(self.current_gates)
        if np.isclose(gate_sum, 1.0, atol=1e-6):
            health_checks.append(("[OK]", f"Gate normalization: {gate_sum:.10f}"))
        else:
            health_checks.append(("[WARN]", f"Gate sum off: {gate_sum:.10f}"))

        # Check 2: No NaN/Inf
        has_nan = np.any(np.isnan(self.current_gates))
        has_inf = np.any(np.isinf(self.current_gates))
        if not has_nan and not has_inf:
            health_checks.append(("[OK]", "No NaN/Inf values"))
        else:
            health_checks.append(("[ERROR]", "NaN or Inf detected!"))

        # Check 3: Reasonable diversity
        if gate_entropy > 0.5:
            health_checks.append(("[OK]", f"Good diversity (entropy={gate_entropy:.2f})"))
        elif gate_entropy > 0.1:
            health_checks.append(("[WARN]", f"Low diversity (entropy={gate_entropy:.2f})"))
        else:
            health_checks.append(("[WARN]", f"Collapsed attention (entropy={gate_entropy:.2f})"))

        # Check 4: Confidence level
        if self.current_confidence > 0.7:
            health_checks.append(("[OK]", f"High confidence ({self.current_confidence:.1%})"))
        elif self.current_confidence > 0.4:
            health_checks.append(("[OK]", f"Medium confidence ({self.current_confidence:.1%})"))
        else:
            health_checks.append(("[WARN]", f"Low confidence ({self.current_confidence:.1%})"))

        for status, message in health_checks:
            print(f"  {status:8s} {message}")

        print("\n" + "="*80)
        print("Press Ctrl+C to stop monitoring")
        print("="*80)

    def _compute_entropy(self, gates):
        """Compute Shannon entropy of gate distribution."""
        # Add small epsilon to avoid log(0)
        p = gates + 1e-10
        return -np.sum(p * np.log2(p))

    def get_stats(self):
        """Get statistics dictionary for logging or API."""
        if not self.gate_history:
            return {}

        avg_gates = np.mean(np.array(list(self.gate_history)), axis=0)

        return {
            'total_steps': self.total_steps,
            'runtime': time.time() - self.start_time,
            'current_dominant': self.current_dominant,
            'current_confidence': self.current_confidence,
            'current_entropy': self._compute_entropy(self.current_gates),
            'average_gates': {mod: float(avg_gates[i]) for i, mod in enumerate(self.modalities)},
            'average_confidence': float(np.mean(list(self.confidence_history))),
            'health': {
                'gates_normalized': bool(np.isclose(np.sum(self.current_gates), 1.0)),
                'no_nan_inf': bool(not np.any(np.isnan(self.current_gates)) and not np.any(np.isinf(self.current_gates))),
            }
        }

    def export_csv(self, filename='monitor_log.csv'):
        """Export monitoring data to CSV."""
        import csv

        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            header = ['step'] + [f'gate_{m}' for m in self.modalities] + \
                     [f'pe_{m}' for m in self.modalities] + ['confidence', 'dominant']
            writer.writerow(header)

            # Data
            for step, (gates, pe, conf, dom) in enumerate(zip(
                self.gate_history, self.pe_history,
                self.confidence_history, self.dominant_history
            )):
                row = [step] + list(gates) + pe + [conf, dom]
                writer.writerow(row)

        print(f"\n[Export] Saved to {filename}")


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    from thalamo_pc_adaptive import ThalamoPC6Adaptive

    print("="*80)
    print("ATM-R MONITORING DASHBOARD DEMO")
    print("="*80)
    print("\nStarting simulation with random multimodal inputs...")
    print("Watch the dashboard update in real-time!\n")
    time.sleep(2)

    # Create ATM-R
    atmr = ThalamoPC6Adaptive(seed=42)

    # Create monitor
    monitor = ATMRMonitor(atmr)

    try:
        # Simulate processing loop
        for step in range(200):
            # Generate random multimodal input
            x_t = {mod: np.random.randn(atmr.d[mod]) for mod in atmr.modalities}

            # Occasionally boost different modalities
            if step % 30 == 0:
                # Boost vision
                x_t['vision'] *= 3.0
            elif step % 30 == 10:
                # Boost audio
                x_t['audio'] *= 3.0
            elif step % 30 == 20:
                # Boost threat (simulate alert)
                x_t['threat'] *= 5.0

            # ATM-R processing
            out = atmr.step(x_t, adapt=True)

            # Update monitor
            monitor.update(out)

            # Display dashboard (refresh every step)
            monitor.display(clear_screen=True)

            # Sleep for visibility
            time.sleep(0.1)

        # Export data
        monitor.export_csv('monitor_demo_log.csv')

        print("\n\nDemo complete!")
        print("Check monitor_demo_log.csv for full data export.")

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user.")
        monitor.export_csv('monitor_log.csv')
        print("\nFinal statistics:")
        stats = monitor.get_stats()
        for key, val in stats.items():
            print(f"  {key}: {val}")
