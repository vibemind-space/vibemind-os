"""
Full RuntimeDebugger cycle test with Claude CLI integration.
This demonstrates the complete flow: run → detect error → Claude analysis → fix
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.validators.general_runtime_validator import (
    GeneralRuntimeValidator,
    ProjectType,
)


async def main():
    """Test full debug cycle on output_fresh."""
    print("=" * 70)
    print("FULL RUNTIME DEBUG CYCLE TEST")
    print("=" * 70)

    working_dir = str(Path(__file__).parent / "output_fresh")

    if not Path(working_dir).exists():
        print(f"ERROR: Test directory not found: {working_dir}")
        return

    print(f"\nTarget: {working_dir}")

    # Create validator
    validator = GeneralRuntimeValidator(
        project_dir=working_dir,
        timeout=15.0,
        startup_wait=3.0,
        clean_env=True,
    )

    # Detect project type
    project_type = validator.detect_project_type()
    print(f"Project Type: {project_type.value}")
    print(f"Start Command: {validator.get_start_command()}")

    # Run and debug - this uses Claude CLI for analysis
    print("\n" + "-" * 70)
    print("PHASE 1: Running project and capturing errors...")
    print("-" * 70)

    runtime_result, analysis = await validator.run_and_debug()

    print(f"\n[Runtime Result]")
    print(f"  Success: {runtime_result.success}")
    print(f"  Has Errors: {runtime_result.has_errors}")
    print(f"  Exit Code: {runtime_result.exit_code}")

    if runtime_result.stderr:
        print(f"\n[Stderr Output (first 500 chars)]:")
        print(runtime_result.stderr[:500])

    if runtime_result.error_summary:
        print(f"\n[Error Summary]: {runtime_result.error_summary}")

    if analysis:
        print("\n" + "-" * 70)
        print("PHASE 2: Claude CLI Analysis Results")
        print("-" * 70)
        print(f"\n[Error Type]: {analysis.error_type}")
        print(f"[Root Cause]: {analysis.root_cause}")

        if analysis.additional_info:
            print(f"[Additional Info]: {analysis.additional_info[:300]}")

        if analysis.fix_suggestions:
            print(f"\n[Fix Suggestions ({len(analysis.fix_suggestions)}):]")
            for i, fix in enumerate(analysis.fix_suggestions, 1):
                print(f"\n  Fix #{i}:")
                print(f"    File: {fix.file_path}")
                print(f"    Explanation: {fix.explanation[:200]}")
                print(f"    Confidence: {fix.confidence}")
                if fix.fixed_content:
                    print(f"    Fixed Content Preview:")
                    lines = fix.fixed_content.split('\n')[:10]
                    for line in lines:
                        print(f"      {line[:80]}")
                    total_lines = len(fix.fixed_content.split('\n'))
                    if total_lines > 10:
                        print(f"      ... ({total_lines - 10} more lines)")
        else:
            print("\n[No fix suggestions provided by Claude CLI]")
    else:
        print("\n[No Claude CLI analysis available]")

    print("\n" + "=" * 70)
    print("DEBUG CYCLE COMPLETE")
    print("=" * 70)

    return runtime_result, analysis


if __name__ == "__main__":
    result, analysis = asyncio.run(main())
