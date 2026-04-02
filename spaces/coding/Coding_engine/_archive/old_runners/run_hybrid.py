#!/usr/bin/env python3
"""
Entry point for running the Hybrid Coding Engine Pipeline.

This script runs the complete pipeline with:
1. Pre-analysis (Architect Agent generates contracts)
2. Parallel code generation (with contracts as context)
3. Verification and iterative recovery
4. Memory updates for learning

Usage:
    python run_hybrid.py Data/requirements.json --output-dir ./output
"""
import asyncio
import sys
from pathlib import Path

# Load .env file for environment variables (SUPERMEMORY_API_KEY, etc.)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use system env vars

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.engine.hybrid_pipeline import HybridPipeline, PipelineProgress


def print_progress(progress: PipelineProgress):
    """Print progress to console."""
    phases = {
        "starting": "[START]",
        "architect": "[ARCH]",
        "generating": "[GEN]",
        "testing": "[TEST]",
        "recovering": "[FIX]",
        "writing": "[WRITE]",
        "complete": "[DONE]",
        "failed": "[FAIL]",
    }

    phase_icon = phases.get(progress.phase, "[...]")
    overall = (progress.current_phase / progress.total_phases) * 100

    print(
        f"{phase_icon} [{progress.phase.upper():12}] "
        f"Phase {progress.current_phase}/{progress.total_phases} ({overall:.0f}%) | "
        f"Iteration {progress.iteration}/{progress.max_iterations} | "
        f"Files: {progress.files_generated} | "
        f"Tests: +{progress.tests_passed} -{progress.tests_failed}"
    )


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the Hybrid Coding Engine Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_hybrid.py Data/requirements.json
  python run_hybrid.py Data/requirements.json --output-dir ./generated --max-iterations 5
  python run_hybrid.py Data/requirements.json --max-concurrent 10 --job-id 42
        """,
    )
    parser.add_argument(
        "requirements_file",
        help="Path to requirements JSON file",
    )
    parser.add_argument(
        "--output-dir",
        default="./output",
        help="Output directory for generated files (default: ./output)",
    )
    parser.add_argument(
        "--job-id",
        type=int,
        default=1,
        help="Job ID for tracking (default: 1)",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Maximum concurrent CLI calls (default: 5)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum recovery iterations (default: 3)",
    )
    parser.add_argument(
        "--slice-size",
        type=int,
        default=3,
        help="Requirements per slice (default: 3)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("  HYBRID CODING ENGINE")
    print("=" * 70)
    print(f"  Requirements: {args.requirements_file}")
    print(f"  Output:       {args.output_dir}")
    print(f"  Job ID:       {args.job_id}")
    print(f"  Concurrent:   {args.max_concurrent}")
    print(f"  Max Iters:    {args.max_iterations}")
    print(f"  Slice Size:   {args.slice_size}")
    print("=" * 70)
    print()

    pipeline = HybridPipeline(
        output_dir=args.output_dir,
        max_concurrent=args.max_concurrent,
        max_iterations=args.max_iterations,
        slice_size=args.slice_size,
        progress_callback=None if args.quiet else print_progress,
    )

    try:
        result = await pipeline.execute_from_file(
            args.requirements_file,
            args.job_id,
        )

        print()
        print("=" * 70)
        print("  RESULTS")
        print("=" * 70)
        print(f"  Success:         {'YES' if result.success else 'NO'}")
        print(f"  Files Generated: {result.files_generated}")
        print(f"  Tests Passed:    {result.tests_passed}")
        print(f"  Tests Failed:    {result.tests_failed}")
        print(f"  Iterations:      {result.iterations}")
        print(f"  Time:            {result.execution_time_ms / 1000:.2f}s")
        print("=" * 70)

        if result.errors:
            print("\n  Errors:")
            for error in result.errors[:10]:
                print(f"    - {error[:80]}...")

        if result.success:
            print(f"\n  Output written to: {args.output_dir}/job_{args.job_id}/")
            return 0
        else:
            return 1

    except FileNotFoundError:
        print(f"ERROR: Requirements file not found: {args.requirements_file}")
        return 1
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
