#!/usr/bin/env python3
"""
CLI entry point for Cross-Layer Validation (Phase 23).

Validates frontend-backend consistency in generated projects:
- API route alignment (FE fetch URLs vs BE controller routes)
- DTO field alignment (FE interfaces vs BE DTOs)
- Security consistency (bcrypt hash/compare patterns)
- Import resolution (relative imports resolve to real files)

Usage:
    python run_cross_layer_validation.py --project-dir Data/all_services/whatsapp/output
    python run_cross_layer_validation.py --project-dir output --mode routes --dry-run
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path


async def main():
    parser = argparse.ArgumentParser(
        description="Cross-Layer Validation: Frontend ↔ Backend consistency checks"
    )
    parser.add_argument(
        "--project-dir",
        required=True,
        help="Path to generated project directory (must contain src/)",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "routes", "dtos", "security", "imports"],
        default="full",
        help="Validation mode (default: full)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report findings, do not publish CODE_FIX_NEEDED events",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output report as JSON",
    )
    args = parser.parse_args()

    # Validate project dir
    project_dir = Path(args.project_dir)
    if not project_dir.exists():
        print(f"ERROR: Project directory not found: {project_dir}")
        sys.exit(1)

    # Import service
    from src.services.cross_layer_validation_service import (
        CrossLayerCheckMode,
        CrossLayerValidationService,
        FindingSeverity,
    )

    # Map CLI mode to enum
    mode_map = {
        "full": CrossLayerCheckMode.FULL,
        "routes": CrossLayerCheckMode.API_ROUTE_ALIGNMENT,
        "dtos": CrossLayerCheckMode.DTO_FIELD_ALIGNMENT,
        "security": CrossLayerCheckMode.SECURITY_CONSISTENCY,
        "imports": CrossLayerCheckMode.IMPORT_RESOLUTION,
    }
    mode = mode_map[args.mode]

    # Create and start service
    service = CrossLayerValidationService(
        project_dir=str(project_dir),
    )

    started = await service.start()
    if not started:
        print(f"ERROR: Failed to start service (check project directory structure)")
        sys.exit(1)

    print(f"Scanning: {project_dir}")
    print(f"Mode: {args.mode}")
    print(f"Frontend files: {len(service._frontend_files)}")
    print(f"Backend files: {len(service._backend_files)}")
    print()

    # Run validation
    report = await service.run_validation(mode=mode)

    # Output
    if args.json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        # Human-readable output
        print("=" * 60)
        print(f"CROSS-LAYER VALIDATION REPORT")
        print("=" * 60)
        print(f"Alignment Score: {report.alignment_score:.1f}%")
        print(f"Total Findings:  {len(report.findings)}")
        print()

        if report.routes_checked > 0:
            print(f"API Routes: {report.routes_aligned}/{report.routes_checked} aligned")
        if report.dtos_checked > 0:
            print(f"DTOs:       {report.dtos_aligned}/{report.dtos_checked} aligned")
        if report.security_issues > 0:
            print(f"Security:   {report.security_issues} issues")
        if report.import_issues > 0:
            print(f"Imports:    {report.import_issues} broken")

        if report.findings:
            print()
            print("-" * 60)

            # Group by severity
            for severity in [FindingSeverity.CRITICAL, FindingSeverity.HIGH, FindingSeverity.MEDIUM, FindingSeverity.LOW]:
                findings = [f for f in report.findings if f.severity == severity]
                if not findings:
                    continue

                print(f"\n[{severity.value.upper()}] ({len(findings)} findings)")
                for i, f in enumerate(findings, 1):
                    print(f"  {i}. {f.description}")
                    print(f"     FE: {f.frontend_file}")
                    print(f"     BE: {f.backend_file}")
                    print(f"     Fix: {f.suggestion}")
                    print()
        else:
            print("\nNo issues found! Frontend and backend are aligned.")

    await service.stop()

    # Exit code: 1 if critical findings, 0 otherwise
    critical_count = sum(1 for f in report.findings if f.severity == FindingSeverity.CRITICAL)
    sys.exit(1 if critical_count > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
