"""CLI entry point for the new pipeline."""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

from src.engine.spec_parser import SpecParser
from src.engine.service_orchestrator import ServiceOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="DaveFelix Pipeline v2")
    parser.add_argument("spec_dir", help="Path to service specification directory")
    parser.add_argument("--output-dir", "-o", default="./output", help="Output directory")
    parser.add_argument("--service", help="Generate only this service")
    parser.add_argument("--all", action="store_true", help="Generate all services")
    parser.add_argument("--skeleton-only", action="store_true", help="Only generate skeleton, no agent fill")
    parser.add_argument("--validate-only", action="store_true", help="Only run validation")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--refill", action="store_true", help="Re-generate service (clear + re-fill)")

    args = parser.parse_args()
    spec_dir = Path(args.spec_dir)
    output_dir = Path(args.output_dir)

    logger.info("Parsing spec from %s", spec_dir)
    spec = SpecParser(spec_dir).parse()
    logger.info("Parsed: %d services, %d endpoints, %d stories",
                len(spec.services),
                sum(len(s.endpoints) for s in spec.services.values()),
                sum(len(s.stories) for s in spec.services.values()))

    orchestrator = ServiceOrchestrator(spec, output_dir)

    if args.skeleton_only:
        results = orchestrator.run_skeleton_only()
        for name, path in results.items():
            logger.info("Skeleton: %s -> %s", name, path)
        logger.info("Done. %d service skeletons generated.", len(results))
    elif args.service:
        if args.refill:
            import shutil
            svc_dir = output_dir / args.service
            if svc_dir.exists():
                shutil.rmtree(svc_dir)
        result = asyncio.run(orchestrator.run_single(args.service))
        logger.info("Result: %s — %s", result.service_name, result.status)
    elif args.all or args.resume:
        results = asyncio.run(orchestrator.run_all())
        for name, result in results.items():
            logger.info("  %s: %s", name, result.status)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
