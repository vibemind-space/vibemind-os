#!/usr/bin/env python3
"""
End-to-End Code Generation Orchestrator

Coordinates the full autonomous workflow:
1. Project Creation (via external API)
2. Deployment Infrastructure (Docker)
3. Initial Code Generation (society_hybrid)
4. Continuous Testing Loop
5. Autonomous Verification
6. User Review Gate
7. Production Deployment (Git Push)

Usage:
    python run_orchestrator.py Data/requirements.json Data/tech_stack.json
    python run_orchestrator.py Data/requirements.json Data/tech_stack.json --auto-approve
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    # Input files
    requirements_file: str
    tech_stack_file: str
    
    # Output
    project_name: str = "generated-app"
    output_dir: str = "./output"
    
    # External APIs
    project_create_api: str = "http://localhost:8087"
    coding_engine_api: str = "http://localhost:8000"
    
    # Docker
    docker_compose_dir: str = "./infra"
    start_docker: bool = True
    
    # Phase 1 - Skip project creation
    skip_project_create: bool = False
    
    # Code Generation
    run_mode: str = "society_hybrid"  # or "hybrid"
    max_time: int = 3600  # 1 hour
    max_iterations: int = 200
    min_test_rate: float = 100.0
    slice_size: int = 3
    
    # Testing
    continuous_sandbox: bool = True
    sandbox_interval: int = 30
    enable_vnc: bool = True
    vnc_port: int = 6080
    
    # User Gate
    auto_approve: bool = False
    
    # Git
    git_push: bool = True
    git_private: bool = True
    github_token: Optional[str] = field(default_factory=lambda: os.getenv("GITHUB_TOKEN"))


@dataclass
class PhaseResult:
    """Result of a phase execution."""
    phase: str
    success: bool
    message: str
    duration_seconds: float = 0.0
    data: dict = field(default_factory=dict)


# ============================================================================
# Phase 1: Project Creation
# ============================================================================

async def phase_create_project(config: OrchestratorConfig) -> PhaseResult:
    """Call external Project-Create API to scaffold the project."""
    print("\n" + "=" * 60)
    print("📁 PHASE 1: PROJECT CREATION")
    print("=" * 60)
    
    start_time = time.time()
    
    # Check if we should skip this phase
    if config.skip_project_create:
        print("  ⏭️  Project creation skipped (--skip-create)")
        # Create output directory manually
        project_path = str(Path(config.output_dir) / config.project_name)
        Path(project_path).mkdir(parents=True, exist_ok=True)
        print(f"  📂 Created directory: {project_path}")
        return PhaseResult(
            phase="create_project",
            success=True,
            message="Project creation skipped - directory created manually",
            duration_seconds=time.time() - start_time,
            data={"project_path": project_path},
        )
    
    # Load tech stack to get template_id
    try:
        with open(config.tech_stack_file, "r", encoding="utf-8") as f:
            tech_stack = json.load(f)
    except Exception as e:
        return PhaseResult(
            phase="create_project",
            success=False,
            message=f"Failed to load tech stack: {e}",
        )
    
    # Get raw template_id from tech_stack
    raw_template_id = tech_stack.get("tech_stack", {}).get("id", "01-web-app")
    
    # Load template aliases and resolve the template_id
    template_id = raw_template_id
    aliases_path = Path("Data/template_aliases.json")
    if aliases_path.exists():
        try:
            with open(aliases_path, "r", encoding="utf-8") as f:
                aliases_data = json.load(f)
            aliases = aliases_data.get("aliases", {})
            # Map alias to official template ID if exists
            template_id = aliases.get(raw_template_id, raw_template_id)
            if template_id != raw_template_id:
                print(f"  📋 Template alias resolved: {raw_template_id} → {template_id}")
        except Exception as e:
            print(f"  ⚠️  Could not load template aliases: {e}")
    
    # Prepare API request - Project-Create API expects only these fields
    payload = {
        "template_id": template_id,
        "project_name": config.project_name,
        "output_path": str(Path(config.output_dir).absolute()),
    }
    
    print(f"  API: {config.project_create_api}/api/v1/techstack/create")
    print(f"  Template: {template_id}")
    print(f"  Project: {config.project_name}")
    print(f"  Output: {payload['output_path']}")

    # Call API
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{config.project_create_api}/api/v1/techstack/create",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("success"):
                duration = time.time() - start_time
                print(f"\n  ✅ Project created at: {result.get('path')}")
                print(f"  📄 Files created: {result.get('files_created', 0)}")
                
                return PhaseResult(
                    phase="create_project",
                    success=True,
                    message=f"Project created with {result.get('files_created', 0)} files",
                    duration_seconds=duration,
                    data={"project_path": result.get("path")},
                )
            else:
                return PhaseResult(
                    phase="create_project",
                    success=False,
                    message=f"API returned failure: {result}",
                )
                
    except httpx.ConnectError:
        return PhaseResult(
            phase="create_project",
            success=False,
            message=f"Cannot connect to Project-Create API at {config.project_create_api}. Is it running?",
        )
    except Exception as e:
        return PhaseResult(
            phase="create_project",
            success=False,
            message=f"API call failed: {e}",
        )


# ============================================================================
# Phase 2: Deployment Infrastructure
# ============================================================================

async def phase_start_docker(config: OrchestratorConfig) -> PhaseResult:
    """Start Docker containers for the coding engine."""
    print("\n" + "=" * 60)
    print("🐳 PHASE 2: DEPLOYMENT INFRASTRUCTURE")
    print("=" * 60)
    
    if not config.start_docker:
        print("  ⏭️  Docker start skipped (--no-docker)")
        return PhaseResult(
            phase="start_docker",
            success=True,
            message="Docker start skipped",
        )
    
    start_time = time.time()
    compose_dir = Path(config.docker_compose_dir)
    
    if not (compose_dir / "docker-compose.yml").exists():
        return PhaseResult(
            phase="start_docker",
            success=False,
            message=f"docker-compose.yml not found in {compose_dir}",
        )
    
    print(f"  Directory: {compose_dir}")
    print("  Starting docker-compose...")
    
    try:
        # Start docker-compose in background
        process = subprocess.Popen(
            ["docker-compose", "up", "-d", "--build"],
            cwd=str(compose_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        stdout, stderr = process.communicate(timeout=300)  # 5 min timeout
        
        if process.returncode != 0:
            return PhaseResult(
                phase="start_docker",
                success=False,
                message=f"Docker-compose failed: {stderr.decode()}",
            )
        
        # Wait for services to be ready
        print("  Waiting for services to be ready...")
        await asyncio.sleep(10)
        
        # Health check
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(30):
                try:
                    response = await client.get(f"{config.coding_engine_api}/api/health")
                    if response.status_code == 200:
                        print(f"  ✅ Control API ready at {config.coding_engine_api}")
                        break
                except:
                    pass
                await asyncio.sleep(2)
            else:
                return PhaseResult(
                    phase="start_docker",
                    success=False,
                    message="Services did not become ready in time",
                )
        
        duration = time.time() - start_time
        
        vnc_url = f"http://localhost:{config.vnc_port}/vnc.html" if config.enable_vnc else None
        print(f"  🖥️  VNC Preview: {vnc_url}")
        
        return PhaseResult(
            phase="start_docker",
            success=True,
            message="Docker services started",
            duration_seconds=duration,
            data={"vnc_url": vnc_url},
        )
        
    except subprocess.TimeoutExpired:
        return PhaseResult(
            phase="start_docker",
            success=False,
            message="Docker-compose timed out",
        )
    except FileNotFoundError:
        return PhaseResult(
            phase="start_docker",
            success=False,
            message="docker-compose not found. Is Docker installed?",
        )
    except Exception as e:
        return PhaseResult(
            phase="start_docker",
            success=False,
            message=f"Docker start failed: {e}",
        )


# ============================================================================
# Phase 3: Code Generation
# ============================================================================

async def phase_generate_code(config: OrchestratorConfig, project_path: str) -> PhaseResult:
    """Run society_hybrid or hybrid for initial code generation."""
    print("\n" + "=" * 60)
    print("🚀 PHASE 3: CODE GENERATION")
    print("=" * 60)
    
    start_time = time.time()
    
    # Determine which runner to use
    runner_script = f"run_{config.run_mode}.py"
    
    if not Path(runner_script).exists():
        return PhaseResult(
            phase="generate_code",
            success=False,
            message=f"Runner script not found: {runner_script}",
        )
    
    print(f"  Mode: {config.run_mode}")
    print(f"  Requirements: {config.requirements_file}")
    print(f"  Tech Stack: {config.tech_stack_file}")
    print(f"  Output: {project_path}")
    print(f"  Max Time: {config.max_time}s ({config.max_time // 60} min)")
    
    # Build command
    cmd = [
        sys.executable,
        runner_script,
        config.requirements_file,
        "--output-dir", project_path,
        "--max-time", str(config.max_time),
        "--slice-size", str(config.slice_size),
    ]
    
    # Add tech stack parameter for society_hybrid
    if config.run_mode == "society_hybrid" and config.tech_stack_file:
        cmd.extend(["--tech-stack", config.tech_stack_file])
    
    if config.run_mode == "society_hybrid":
        cmd.extend([
            "--autonomous",
            "--max-iterations", str(config.max_iterations),
            "--min-test-rate", str(config.min_test_rate),
        ])
        
        if config.continuous_sandbox:
            cmd.extend([
                "--continuous-sandbox",
                "--sandbox-interval", str(config.sandbox_interval),
            ])
        
        if config.enable_vnc:
            cmd.extend([
                "--enable-vnc",
                "--vnc-port", str(config.vnc_port),
            ])
    
    print(f"  Command: {' '.join(cmd[:5])}...")
    print()
    
    try:
        # Run the code generation
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        
        # Stream output
        for line in process.stdout:
            print(f"  {line}", end="")
        
        process.wait()
        
        duration = time.time() - start_time
        
        if process.returncode == 0:
            return PhaseResult(
                phase="generate_code",
                success=True,
                message="Code generation completed successfully",
                duration_seconds=duration,
            )
        else:
            return PhaseResult(
                phase="generate_code",
                success=False,
                message=f"Code generation failed with exit code {process.returncode}",
                duration_seconds=duration,
            )
            
    except Exception as e:
        return PhaseResult(
            phase="generate_code",
            success=False,
            message=f"Code generation error: {e}",
        )


# ============================================================================
# Phase 4: Continuous Testing Loop
# ============================================================================

async def phase_testing_loop(config: OrchestratorConfig, project_path: str) -> PhaseResult:
    """Run continuous build/test/fix loop until success."""
    print("\n" + "=" * 60)
    print("🔄 PHASE 4: CONTINUOUS TESTING LOOP")
    print("=" * 60)
    
    # This phase is handled within society_hybrid if --continuous-sandbox is enabled
    # For standalone testing, we can poll the Control API
    
    print("  Testing loop is managed by society_hybrid --continuous-sandbox")
    print("  Checking final status via Control API...")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{config.coding_engine_api}/api/status")
            if response.status_code == 200:
                status = response.json()
                
                return PhaseResult(
                    phase="testing_loop",
                    success=status.get("state") == "completed",
                    message=f"Tests completed - State: {status.get('state')}",
                    data=status,
                )
    except Exception as e:
        pass
    
    return PhaseResult(
        phase="testing_loop",
        success=True,
        message="Testing loop completed (inline with code generation)",
    )


# ============================================================================
# Phase 5: Autonomous Verification
# ============================================================================

async def phase_verification(config: OrchestratorConfig, project_path: str) -> PhaseResult:
    """Verify that all quality criteria are met."""
    print("\n" + "=" * 60)
    print("✅ PHASE 5: AUTONOMOUS VERIFICATION")
    print("=" * 60)
    
    checks = {
        "project_exists": False,
        "has_package_json_or_requirements": False,
        "has_source_files": False,
        "build_artifacts_exist": False,
    }
    
    project = Path(project_path)
    
    # Check project exists
    if project.exists():
        checks["project_exists"] = True
        print(f"  ✅ Project directory exists: {project}")
    else:
        print(f"  ❌ Project directory missing: {project}")
        return PhaseResult(
            phase="verification",
            success=False,
            message="Project directory does not exist",
            data=checks,
        )
    
    # Check for package.json or requirements.txt
    if (project / "package.json").exists():
        checks["has_package_json_or_requirements"] = True
        print("  ✅ package.json found")
    elif (project / "requirements.txt").exists():
        checks["has_package_json_or_requirements"] = True
        print("  ✅ requirements.txt found")
    else:
        print("  ⚠️  No package.json or requirements.txt")
    
    # Check for source files
    src_patterns = ["*.ts", "*.tsx", "*.js", "*.jsx", "*.py", "*.vue", "*.svelte"]
    source_files = []
    for pattern in src_patterns:
        source_files.extend(project.rglob(pattern))
    
    if source_files:
        checks["has_source_files"] = True
        print(f"  ✅ Source files found: {len(source_files)}")
    else:
        print("  ⚠️  No source files found")
    
    # Check for build artifacts (node_modules, dist, etc.)
    if (project / "node_modules").exists() or (project / "dist").exists() or (project / "build").exists():
        checks["build_artifacts_exist"] = True
        print("  ✅ Build artifacts present")
    else:
        print("  ⚠️  No build artifacts yet")
    
    # Determine overall success
    # Require at least project + source files
    success = checks["project_exists"] and checks["has_source_files"]
    
    return PhaseResult(
        phase="verification",
        success=success,
        message="Verification complete" if success else "Verification failed",
        data=checks,
    )


# ============================================================================
# Phase 6: User Review Gate
# ============================================================================

async def phase_user_review(config: OrchestratorConfig, project_path: str) -> PhaseResult:
    """Wait for user approval before proceeding to production."""
    print("\n" + "=" * 60)
    print("👤 PHASE 6: USER REVIEW GATE")
    print("=" * 60)
    
    if config.auto_approve:
        print("  ⏭️  Auto-approve enabled, skipping user review")
        return PhaseResult(
            phase="user_review",
            success=True,
            message="Auto-approved",
        )
    
    print(f"\n  📂 Project ready at: {project_path}")
    
    if config.enable_vnc:
        print(f"  🖥️  Preview at: http://localhost:{config.vnc_port}/vnc.html")
    
    print(f"  🎛️  Control API: {config.coding_engine_api}")
    
    print("\n" + "-" * 40)
    print("  Please review the generated code.")
    print("-" * 40)
    
    while True:
        response = input("\n  ➡️  Approve and proceed to production? [y/n/r(review)]: ").strip().lower()
        
        if response == "y":
            return PhaseResult(
                phase="user_review",
                success=True,
                message="User approved",
            )
        elif response == "n":
            return PhaseResult(
                phase="user_review",
                success=False,
                message="User rejected",
            )
        elif response == "r":
            print(f"\n  Opening {project_path} for review...")
            # Try to open in file explorer
            if sys.platform == "win32":
                os.startfile(project_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", project_path])
            else:
                subprocess.run(["xdg-open", project_path])
        else:
            print("  Invalid input. Please enter y, n, or r.")


# ============================================================================
# Phase 7: Production Deployment
# ============================================================================

async def phase_git_push(config: OrchestratorConfig, project_path: str) -> PhaseResult:
    """Push the generated code to GitHub."""
    print("\n" + "=" * 60)
    print("🚀 PHASE 7: PRODUCTION DEPLOYMENT")
    print("=" * 60)
    
    if not config.git_push:
        print("  ⏭️  Git push disabled")
        return PhaseResult(
            phase="git_push",
            success=True,
            message="Git push skipped",
        )
    
    if not config.github_token:
        print("  ⚠️  No GITHUB_TOKEN set, skipping Git push")
        return PhaseResult(
            phase="git_push",
            success=True,
            message="Git push skipped (no token)",
        )
    
    print(f"  Repository: {config.project_name}")
    print(f"  Private: {config.git_private}")
    
    # Call the Control API to push
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{config.coding_engine_api}/api/git/push",
                params={"output_dir": project_path},
                json={
                    "repo_name": config.project_name,
                    "private": config.git_private,
                },
            )
            
            if response.status_code == 200:
                result = response.json()
                repo_url = result.get("repo_url", "")
                print(f"\n  ✅ Code pushed to: {repo_url}")
                
                return PhaseResult(
                    phase="git_push",
                    success=True,
                    message=f"Pushed to {repo_url}",
                    data={"repo_url": repo_url},
                )
            else:
                return PhaseResult(
                    phase="git_push",
                    success=False,
                    message=f"Git push failed: {response.text}",
                )
                
    except Exception as e:
        return PhaseResult(
            phase="git_push",
            success=False,
            message=f"Git push error: {e}",
        )


# ============================================================================
# Main Orchestrator
# ============================================================================

async def run_orchestrator(config: OrchestratorConfig) -> bool:
    """Run the full orchestration pipeline."""
    print()
    print("=" * 60)
    print("🎯 END-TO-END CODE GENERATION ORCHESTRATOR")
    print("=" * 60)
    print(f"  Started: {datetime.now().isoformat()}")
    print(f"  Requirements: {config.requirements_file}")
    print(f"  Tech Stack: {config.tech_stack_file}")
    print(f"  Output: {config.output_dir}/{config.project_name}")
    print(f"  Mode: {config.run_mode}")
    print("=" * 60)
    
    results: list[PhaseResult] = []
    project_path = str(Path(config.output_dir) / config.project_name)
    
    total_start = time.time()
    
    # Phase 1: Project Creation
    result = await phase_create_project(config)
    results.append(result)
    if not result.success:
        print(f"\n❌ Phase 1 failed: {result.message}")
        return False
    project_path = result.data.get("project_path", project_path)
    
    # Phase 2: Docker Infrastructure
    result = await phase_start_docker(config)
    results.append(result)
    if not result.success:
        print(f"\n❌ Phase 2 failed: {result.message}")
        return False
    
    # Phase 3: Code Generation
    result = await phase_generate_code(config, project_path)
    results.append(result)
    if not result.success:
        print(f"\n❌ Phase 3 failed: {result.message}")
        # Continue anyway to let user review partial results
    
    # Phase 4: Testing Loop
    result = await phase_testing_loop(config, project_path)
    results.append(result)
    
    # Phase 5: Verification
    result = await phase_verification(config, project_path)
    results.append(result)
    if not result.success:
        print(f"\n⚠️  Phase 5 verification incomplete: {result.message}")
    
    # Phase 6: User Review
    result = await phase_user_review(config, project_path)
    results.append(result)
    if not result.success:
        print(f"\n❌ User rejected. Stopping.")
        return False
    
    # Phase 7: Git Push
    result = await phase_git_push(config, project_path)
    results.append(result)
    
    # Final Summary
    total_duration = time.time() - total_start
    
    print()
    print("=" * 60)
    print("📊 ORCHESTRATION SUMMARY")
    print("=" * 60)
    
    for r in results:
        status = "✅" if r.success else "❌"
        print(f"  {status} {r.phase}: {r.message} ({r.duration_seconds:.1f}s)")
    
    print("-" * 60)
    print(f"  Total Time: {total_duration:.1f}s ({total_duration / 60:.1f} min)")
    
    success = all(r.success for r in results)
    print(f"  Final Status: {'SUCCESS' if success else 'PARTIAL'}")
    print("=" * 60)
    
    return success


# ============================================================================
# CLI
# ============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="End-to-End Code Generation Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Full pipeline
    python run_orchestrator.py Data/requirements.json Data/tech_stack.json

    # With auto-approval (no user input required)
    python run_orchestrator.py Data/requirements.json Data/tech_stack.json --auto-approve

    # Skip Docker start (already running)
    python run_orchestrator.py Data/requirements.json Data/tech_stack.json --no-docker

    # Custom project name
    python run_orchestrator.py Data/requirements.json Data/tech_stack.json --project my-app
        """,
    )
    
    parser.add_argument(
        "requirements_file",
        help="Path to requirements.json",
    )
    parser.add_argument(
        "tech_stack_file",
        help="Path to tech_stack.json",
    )
    parser.add_argument(
        "--project", "-p",
        default="generated-app",
        help="Project name (default: generated-app)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./output",
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--mode",
        choices=["hybrid", "society_hybrid"],
        default="society_hybrid",
        help="Code generation mode (default: society_hybrid)",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip user review gate",
    )
    parser.add_argument(
        "--no-docker",
        action="store_true",
        help="Don't start Docker containers (assume already running)",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Skip Git push",
    )
    parser.add_argument(
        "--max-time",
        type=int,
        default=3600,
        help="Max code generation time in seconds (default: 3600)",
    )
    parser.add_argument(
        "--vnc-port",
        type=int,
        default=6080,
        help="VNC port (default: 6080)",
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    # Validate files
    if not Path(args.requirements_file).exists():
        print(f"Error: Requirements file not found: {args.requirements_file}")
        return 1
    
    if not Path(args.tech_stack_file).exists():
        print(f"Error: Tech stack file not found: {args.tech_stack_file}")
        return 1
    
    # Build config
    config = OrchestratorConfig(
        requirements_file=args.requirements_file,
        tech_stack_file=args.tech_stack_file,
        project_name=args.project,
        output_dir=args.output_dir,
        run_mode=args.mode,
        auto_approve=args.auto_approve,
        start_docker=not args.no_docker,
        git_push=not args.no_git,
        max_time=args.max_time,
        vnc_port=args.vnc_port,
    )
    
    # Run
    try:
        success = asyncio.run(run_orchestrator(config))
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n⚠️  Orchestration interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())