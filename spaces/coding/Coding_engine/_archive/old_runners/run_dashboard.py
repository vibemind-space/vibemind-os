#!/usr/bin/env python3
"""
Coding Engine Dashboard Launcher

Orchestrates the complete Coding Engine environment:
1. Starts Docker Compose stack (PostgreSQL, Redis, Engine API)
2. Launches Electron Dashboard App
3. Provides unified CLI interface

Usage:
    python run_dashboard.py              # Start everything
    python run_dashboard.py --dev        # Development mode (hot reload)
    python run_dashboard.py --stack-only # Only start Docker stack
    python run_dashboard.py --stop       # Stop all services
"""

import argparse
import subprocess
import sys
import os
import time
import signal
import platform
from pathlib import Path

# Platform detection
IS_WINDOWS = platform.system() == "Windows"

# Paths
ROOT_DIR = Path(__file__).parent.absolute()
DASHBOARD_APP_DIR = ROOT_DIR / "dashboard-app"
DOCKER_COMPOSE_FILE = ROOT_DIR / "infra" / "docker" / "docker-compose.dashboard.yml"


def check_docker():
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=10
        )
        if result.returncode != 0:
            print("❌ Docker is not running. Please start Docker Desktop.")
            return False
        return True
    except FileNotFoundError:
        print("❌ Docker is not installed. Please install Docker Desktop.")
        return False
    except subprocess.TimeoutExpired:
        print("❌ Docker is not responding. Please restart Docker Desktop.")
        return False


def check_node():
    """Check if Node.js is available."""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=5
        )
        if result.returncode == 0:
            print(f"✓ Node.js {result.stdout.strip()}")
            return True
        return False
    except FileNotFoundError:
        print("❌ Node.js is not installed. Please install Node.js 18+.")
        return False


def start_docker_stack(env_vars: dict = None):
    """Start the Docker Compose stack."""
    print("\n🐳 Starting Docker stack...")

    if not DOCKER_COMPOSE_FILE.exists():
        print(f"❌ Docker Compose file not found: {DOCKER_COMPOSE_FILE}")
        return False

    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)

    # Pull images first
    print("   Pulling images...")
    subprocess.run(
        ["docker-compose", "-f", str(DOCKER_COMPOSE_FILE), "pull"],
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    # Start services
    print("   Starting services...")
    result = subprocess.run(
        ["docker-compose", "-f", str(DOCKER_COMPOSE_FILE), "up", "-d"],
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    if result.returncode != 0:
        print(f"❌ Failed to start Docker stack:\n{result.stderr}")
        return False

    print("✓ Docker stack started")

    # Wait for services to be healthy
    print("   Waiting for services to be healthy...")
    for i in range(30):
        result = subprocess.run(
            ["docker-compose", "-f", str(DOCKER_COMPOSE_FILE), "ps", "--format", "json"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env
        )
        time.sleep(2)

        # Simple check - just wait a bit for services to start
        if i >= 5:
            break

    print("✓ Services ready")
    return True


def stop_docker_stack():
    """Stop the Docker Compose stack."""
    print("\n🛑 Stopping Docker stack...")

    result = subprocess.run(
        ["docker-compose", "-f", str(DOCKER_COMPOSE_FILE), "down"],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    if result.returncode == 0:
        print("✓ Docker stack stopped")
        return True
    else:
        print(f"⚠ Warning: {result.stderr}")
        return False


def install_dashboard_deps():
    """Install dashboard app dependencies."""
    if not DASHBOARD_APP_DIR.exists():
        print(f"❌ Dashboard app not found: {DASHBOARD_APP_DIR}")
        return False

    node_modules = DASHBOARD_APP_DIR / "node_modules"
    if not node_modules.exists():
        print("\n📦 Installing dashboard dependencies...")
        result = subprocess.run(
            "npm install" if IS_WINDOWS else ["npm", "install"],
            cwd=str(DASHBOARD_APP_DIR),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            shell=IS_WINDOWS
        )
        if result.returncode != 0:
            print(f"❌ npm install failed:\n{result.stderr}")
            return False
        print("✓ Dependencies installed")

    return True


def start_dashboard(dev_mode: bool = False):
    """Start the Electron dashboard app."""
    print("\n🚀 Starting Coding Engine Dashboard...")

    if not install_dashboard_deps():
        return None

    cmd = "npm run dev" if dev_mode else "npm run preview"
    cmd_list = ["npm", "run", "dev"] if dev_mode else ["npm", "run", "preview"]

    # For dev mode, run in foreground
    # For production, electron-vite build + preview
    if dev_mode:
        print("   Starting in development mode (hot reload enabled)...")
        process = subprocess.Popen(
            cmd if IS_WINDOWS else cmd_list,
            cwd=str(DASHBOARD_APP_DIR),
            stdout=sys.stdout,
            stderr=sys.stderr,
            shell=IS_WINDOWS
        )
        return process
    else:
        # Build first
        print("   Building dashboard...")
        build_result = subprocess.run(
            "npm run build" if IS_WINDOWS else ["npm", "run", "build"],
            cwd=str(DASHBOARD_APP_DIR),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            shell=IS_WINDOWS
        )
        if build_result.returncode != 0:
            print(f"❌ Build failed:\n{build_result.stderr}")
            return None

        print("   Starting dashboard...")
        process = subprocess.Popen(
            "npm run start" if IS_WINDOWS else ["npm", "run", "start"],
            cwd=str(DASHBOARD_APP_DIR),
            stdout=sys.stdout,
            stderr=sys.stderr,
            shell=IS_WINDOWS
        )
        return process


def print_status():
    """Print current status of all services."""
    print("\n📊 Service Status:")
    print("=" * 50)

    # Docker stack status
    result = subprocess.run(
        ["docker-compose", "-f", str(DOCKER_COMPOSE_FILE), "ps"],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    if result.returncode == 0:
        print(result.stdout)
    else:
        print("Docker stack: Not running")

    print("\n📌 Endpoints:")
    print("   API:        http://localhost:8000")
    print("   API Docs:   http://localhost:8000/docs")
    print("   WebSocket:  ws://localhost:8000/ws")
    print("   PostgreSQL: localhost:5433")
    print("   Redis:      localhost:6380")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Coding Engine Dashboard Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_dashboard.py              Start dashboard and Docker stack
  python run_dashboard.py --dev        Development mode with hot reload
  python run_dashboard.py --stack-only Only start Docker services
  python run_dashboard.py --stop       Stop all services
  python run_dashboard.py --status     Show service status
        """
    )

    parser.add_argument(
        "--dev", "-d",
        action="store_true",
        help="Development mode with hot reload"
    )
    parser.add_argument(
        "--stack-only", "-s",
        action="store_true",
        help="Only start Docker stack (no Electron app)"
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop all services"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show status of all services"
    )
    parser.add_argument(
        "--no-docker",
        action="store_true",
        help="Skip Docker stack (for development without backend)"
    )
    parser.add_argument(
        "--projects-dir",
        type=str,
        default="./output",
        help="Directory for generated projects (default: ./output)"
    )

    args = parser.parse_args()

    print("=" * 50)
    print("  Coding Engine Dashboard")
    print("=" * 50)

    # Handle --stop
    if args.stop:
        stop_docker_stack()
        print("\n✓ All services stopped")
        return 0

    # Handle --status
    if args.status:
        print_status()
        return 0

    # Check prerequisites
    if not args.no_docker:
        if not check_docker():
            return 1

    if not args.stack_only:
        if not check_node():
            return 1

    # Prepare environment
    env_vars = {
        "PROJECTS_DIR": str(Path(args.projects_dir).absolute())
    }

    # Start Docker stack
    if not args.no_docker:
        if not start_docker_stack(env_vars):
            return 1

    # Start dashboard
    dashboard_process = None
    if not args.stack_only:
        dashboard_process = start_dashboard(dev_mode=args.dev)
        if dashboard_process is None:
            print("❌ Failed to start dashboard")
            return 1

    print_status()

    if dashboard_process:
        print("\n✨ Dashboard is running!")
        print("   Press Ctrl+C to stop\n")

        # Handle graceful shutdown
        def signal_handler(sig, frame):
            print("\n\n🛑 Shutting down...")
            if dashboard_process:
                dashboard_process.terminate()
                dashboard_process.wait(timeout=10)
            if not args.no_docker:
                stop_docker_stack()
            print("✓ Goodbye!")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Wait for dashboard process
        try:
            dashboard_process.wait()
        except KeyboardInterrupt:
            signal_handler(None, None)
    else:
        print("\n✨ Docker stack is running!")
        print("   Run 'python run_dashboard.py --stop' to stop")

    return 0


if __name__ == "__main__":
    sys.exit(main())
