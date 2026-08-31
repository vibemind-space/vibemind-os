"""
Test Script: Per-Modality Prediction Errors (Phase 2)

Demonstrates per-modality PE tracking integrated with MetaRouter.
Shows which brain areas can predict their inputs well vs. poorly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
from core.meta_router import MetaRouter
from core.conversation_trace_encoder import load_session_logs


def test_per_modality_pes():
    """Test per-modality prediction errors with real session logs"""
    print("=" * 70)
    print("TESTING PER-MODALITY PREDICTION ERRORS (Phase 2)")
    print("=" * 70)
    print()

    # Initialize meta-router with per-modality PEs enabled
    meta_router = MetaRouter(
        enable_hippocampus=True,
        enable_meta_learning=True,
        enable_per_modality_pes=True,  # Phase 2 enabled!
        seed=42
    )

    print("Meta-router initialized with per-modality PE tracking")
    print()

    # Load session logs
    log_dir = r"C:\Users\User\Desktop\sakana-desktop-assistant\data\logs\sessions"
    print(f"Loading session logs from: {log_dir}")
    traces = load_session_logs(log_dir, limit=39)
    print(f"Loaded {len(traces)} conversation traces")
    print()

    # Train on traces
    print("=" * 70)
    print("TRAINING ON TRACES")
    print("=" * 70)
    print()

    for i, trace in enumerate(traces):
        out = meta_router.process_trace(trace, adapt=True)

        # Show per-modality PEs every 10 traces
        if (i + 1) % 10 == 0:
            print(f"\nAfter {i+1} traces:")

            if 'per_modality_pes' in out:
                pes = out['per_modality_pes']

                # Sort by PE descending
                sorted_pes = sorted(pes.items(), key=lambda x: x[1], reverse=True)

                print("  Per-modality PEs (sorted by surprise):")
                for modality, pe in sorted_pes[:5]:  # Top 5
                    bar = '#' * int(pe * 10)
                    print(f"    {modality:20s} {pe:6.3f} {bar}")

                if 'surprising_modalities' in out:
                    surprising = out['surprising_modalities']
                    if surprising:
                        print(f"\n  Surprising modalities (PE > 0.5): {', '.join(surprising)}")

    # Final statistics
    print("\n" + "=" * 70)
    print("FINAL PER-MODALITY PE STATISTICS")
    print("=" * 70)
    print()

    state = meta_router.get_state()

    if 'per_modality_pes' in state:
        pe_stats = state['per_modality_pes']
        all_stats = pe_stats['all_statistics']

        print("DETAILED STATISTICS:")
        print()

        # Sort by mean PE
        sorted_modalities = sorted(
            all_stats.items(),
            key=lambda x: x[1]['mean_pe'],
            reverse=True
        )

        for modality, stats in sorted_modalities:
            print(f"{modality}:")
            print(f"  Mean PE:       {stats['mean_pe']:.4f}")
            print(f"  Std PE:        {stats['std_pe']:.4f}")
            print(f"  Min PE:        {stats['min_pe']:.4f}")
            print(f"  Max PE:        {stats['max_pe']:.4f}")
            print(f"  Recent PE:     {stats['recent_pe']:.4f}")
            print(f"  Learning rate: {stats['learning_rate']:.4f}")
            print(f"  Updates:       {stats['total_updates']}")
            print()

        # PE Ranking
        print("=" * 70)
        print("PE RANKING (Most surprising first)")
        print("=" * 70)
        print()

        pe_ranking = pe_stats['pe_ranking']
        for i, (modality, avg_pe) in enumerate(pe_ranking, 1):
            symbol = "[!]" if avg_pe > 0.5 else "[.]"
            print(f"  {i:2d}. {symbol} {modality:20s} {avg_pe:.4f}")

        # Surprising modalities
        print()
        print("SURPRISING MODALITIES (PE > 0.5):")
        surprising = pe_stats['surprising_modalities']
        if surprising:
            for modality in surprising:
                print(f"  - {modality}")
        else:
            print("  (None - all modalities are well-predicted)")

        # Visualize PE evolution
        print("\n" + "=" * 70)
        print("GENERATING VISUALIZATION")
        print("=" * 70)
        print()

        # Extract PE histories
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

        # Plot 1: PE evolution over time for top 5 modalities
        ax1.set_title('Per-Modality Prediction Error Evolution (Phase 2)', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Update Number')
        ax1.set_ylabel('Prediction Error')
        ax1.grid(True, alpha=0.3)

        colors = ['#667eea', '#764ba2', '#f093fb', '#4facfe', '#fa709a']
        for i, (modality, stats) in enumerate(sorted_modalities[:5]):
            if stats['history_length'] > 0:
                # Get PE history from the tracker
                history = meta_router.modality_pe_tracker.states[modality].pe_history
                ax1.plot(history, label=modality, linewidth=2, color=colors[i % len(colors)])

        ax1.legend(loc='upper right')

        # Plot 2: Final mean PEs (bar chart)
        ax2.set_title('Final Mean Prediction Errors by Modality', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Modality')
        ax2.set_ylabel('Mean Prediction Error')
        ax2.grid(True, alpha=0.3, axis='y')

        modality_names = [m for m, _ in sorted_modalities]
        mean_pes = [stats['mean_pe'] for _, stats in sorted_modalities]

        bars = ax2.bar(range(len(modality_names)), mean_pes, color=colors[:len(modality_names)])
        ax2.set_xticks(range(len(modality_names)))
        ax2.set_xticklabels(modality_names, rotation=45, ha='right')

        # Highlight surprising modalities
        ax2.axhline(y=0.5, color='red', linestyle='--', linewidth=2,
                   label='Surprise threshold (0.5)', alpha=0.7)
        ax2.legend()

        plt.tight_layout()
        plt.savefig('data/per_modality_pes.png', dpi=150, bbox_inches='tight')
        print("  Graph saved to: data/per_modality_pes.png")

    print("\n" + "=" * 70)
    print("TEST COMPLETE [SUCCESS]")
    print("=" * 70)
    print()
    print("KEY INSIGHTS:")
    print("1. Each modality has its own prediction quality metric (PE)")
    print("2. High PE = surprising/unpredictable input for that brain area")
    print("3. Low PE = expected/predictable input")
    print("4. Brain learns which aspects it can predict well")
    print("5. Routing can prioritize surprising modalities for attention")
    print()
    print("This is Phase 2 of 4 integration concepts from routed_brain.py!")


if __name__ == "__main__":
    test_per_modality_pes()
