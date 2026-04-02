#!/usr/bin/env python3
"""
Run a coding engine job from requirements JSON.

Usage:
    python run_job.py Data/requirements_20251122_131456.json --output-dir ./output
"""
import asyncio
import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.engine.parallel_executor import ParallelExecutor, ExecutionProgress


def print_progress(progress: ExecutionProgress):
    """Print progress to console."""
    status_icons = {
        "parsing": "📄",
        "slicing": "✂️",
        "executing": "🤖",
        "assembling": "📦",
        "completed": "✅",
        "failed": "❌",
    }
    icon = status_icons.get(progress.status, "⏳")

    if progress.total_slices > 0:
        bar_length = 30
        filled = int(bar_length * progress.progress_percent / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        print(f"\r{icon} [{bar}] {progress.progress_percent:.1f}% "
              f"({progress.completed_slices}/{progress.total_slices} slices) "
              f"- {progress.status}", end="", flush=True)
    else:
        print(f"\r{icon} {progress.status}...", end="", flush=True)


async def main():
    parser = argparse.ArgumentParser(
        description="Execute coding engine job from requirements JSON"
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
        "--slice-size",
        type=int,
        default=10,
        help="Requirements per slice (default: 10)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    # Check file exists
    if not Path(args.requirements_file).exists():
        print(f"Error: File not found: {args.requirements_file}")
        sys.exit(1)

    print(f"🚀 Coding Engine - Job Executor")
    print(f"=" * 50)
    print(f"Input:       {args.requirements_file}")
    print(f"Output:      {args.output_dir}")
    print(f"Concurrency: {args.max_concurrent}")
    print(f"Slice size:  {args.slice_size}")
    print(f"=" * 50)
    print()

    # Create executor
    executor = ParallelExecutor(
        output_dir=args.output_dir,
        max_concurrent=args.max_concurrent,
        slice_size=args.slice_size,
        progress_callback=None if args.quiet else print_progress,
    )

    try:
        # Run job
        result = await executor.execute_from_file(
            args.requirements_file,
            args.job_id,
        )

        print("\n")
        print(f"=" * 50)
        print(f"📊 Job Results")
        print(f"=" * 50)
        print(f"Status:          {'✅ Success' if result.success else '❌ Failed'}")
        print(f"Total slices:    {result.total_slices}")
        print(f"Completed:       {result.completed_slices}")
        print(f"Failed:          {result.failed_slices}")
        print(f"Files generated: {len(result.all_files)}")
        print(f"Execution time:  {result.total_execution_time_ms}ms")
        print()

        if result.all_files:
            print("Generated files:")
            for f in result.all_files[:20]:  # Show first 20
                print(f"  - {f.path} ({f.language})")
            if len(result.all_files) > 20:
                print(f"  ... and {len(result.all_files) - 20} more")

        print()
        print(f"📁 Output directory: {args.output_dir}/job_{args.job_id}/")

        return 0 if result.success else 1

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
