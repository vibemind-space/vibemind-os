#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coding Engine — CLI Entry Point

Launches the Master Orchestrator which:
  1. Reads requirements.json from the project path
  2. Registers AI agents in Minibook (collaboration platform)
  3. Each agent thinks via Ollama (qwen2.5-coder, local LLM)
  4. Agents communicate by posting/commenting in Minibook
  5. Orchestrator drives phases: Architecture → Code → DB → Test → Fix → Review → Infra
  6. Output: Complete project written to output/ directory

Prerequisites:
  - Ollama running:   ollama serve
  - Model pulled:     ollama pull qwen2.5-coder:7b
  - Minibook running: cd ../minibook && python run.py

Usage:
    python run_engine.py --project Data/all_services/whatsapp
    python run_engine.py --project Data/all_services/whatsapp --model qwen2.5-coder:14b
    python run_engine.py --project Data/all_services/whatsapp --output ./my_output
"""
import argparse
import logging
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.engine.master_orchestrator import MasterOrchestrator


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Coding Engine — AI-powered code generation via Minibook + Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_engine.py --project Data/all_services/whatsapp
  python run_engine.py --project Data/all_services/whatsapp --model qwen2.5-coder:14b
  python run_engine.py --project Data/all_services/whatsapp --minibook-url http://192.168.1.10:3456
        """,
    )

    parser.add_argument(
        "--project", "-p",
        required=True,
        help="Path to project directory containing requirements.json",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory for generated files (default: output/<project-name>)",
    )
    parser.add_argument(
        "--model", "-m",
        default="qwen2.5-coder:7b",
        help="Ollama model to use (default: qwen2.5-coder:7b)",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama server URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--minibook-url",
        default="http://localhost:8080",
        help="Minibook server URL (default: http://localhost:3456)",
    )
    parser.add_argument(
        "--max-fix-rounds",
        type=int,
        default=3,
        help="Max bug-fix iterations (default: 3)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Run orchestrator
    orchestrator = MasterOrchestrator(
        project_path=args.project,
        minibook_url=args.minibook_url,
        ollama_model=args.model,
        ollama_url=args.ollama_url,
        output_dir=args.output,
        max_fix_rounds=args.max_fix_rounds,
    )

    success = orchestrator.run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
