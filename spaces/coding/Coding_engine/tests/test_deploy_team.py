#!/usr/bin/env python3
"""
Test Script für DeployTestTeam.

Testet das komplette Deploy & Test System gegen ein bestehendes Projekt.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


async def test_entrypoint_detector():
    """Test the EntrypointDetector."""
    from src.agents.entrypoint_detector import EntrypointDetector
    
    print("\n" + "=" * 60)
    print("TEST: EntrypointDetector")
    print("=" * 60)
    
    # Test gegen full-test-runtime Projekt
    project_dir = Path("output/full-test-runtime")
    
    if not project_dir.exists():
        print(f"⚠ Projekt nicht gefunden: {project_dir}")
        return None
    
    detector = EntrypointDetector(str(project_dir))
    
    print(f"\n📂 Analysiere: {project_dir}")
    print("⏳ Claude CLI wird aufgerufen...")
    
    try:
        config = await detector.detect()
        
        print(f"\n✅ Detection erfolgreich!")
        print(f"   Stack: {config.detected_stack}")
        
        if config.frontend:
            print(f"\n   Frontend:")
            print(f"     Install: {config.frontend.install_cmd}")
            print(f"     Dev: {config.frontend.dev_cmd}")
            print(f"     Port: {config.frontend.port}")
        
        if config.backend:
            print(f"\n   Backend:")
            print(f"     Install: {config.backend.install_cmd}")
            print(f"     Dev: {config.backend.dev_cmd}")
            print(f"     Port: {config.backend.port}")
            print(f"     Dir: {config.backend.working_dir}")
        
        print(f"\n   Routes: {config.routes}")
        
        return config
        
    except Exception as e:
        print(f"\n❌ Detection fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_parallel_runner(config):
    """Test the ParallelRunner."""
    from src.agents.parallel_runner import ParallelRunner
    
    print("\n" + "=" * 60)
    print("TEST: ParallelRunner")
    print("=" * 60)
    
    if not config:
        print("⚠ Keine Config - überspringe ParallelRunner Test")
        return None
    
    project_dir = Path("output/full-test-runtime")
    
    def on_log(service: str, line: str):
        # Nur Errors loggen
        if "error" in line.lower() or "Error" in line:
            print(f"   [{service}] {line[:100]}")
    
    runner = ParallelRunner(
        str(project_dir),
        config,
        startup_timeout=30.0,
        on_log=on_log,
    )
    
    print("\n⏳ Starte Services...")
    
    try:
        result = await runner.start()
        
        print(f"\n{'✅' if result.success else '❌'} Runner Result:")
        print(f"   Success: {result.success}")
        
        if result.frontend:
            status = "🟢 Running" if result.frontend.running else "🔴 Stopped"
            health = "✓ Healthy" if result.frontend.health_ok else "✗ Unhealthy"
            print(f"   Frontend: {status} | Port {result.frontend.port} | {health}")
        
        if result.backend:
            status = "🟢 Running" if result.backend.running else "🔴 Stopped"
            health = "✓ Healthy" if result.backend.health_ok else "✗ Unhealthy"
            print(f"   Backend: {status} | Port {result.backend.port} | {health}")
        
        if result.all_errors:
            print(f"\n   Errors ({len(result.all_errors)}):")
            for error in result.all_errors[:5]:
                print(f"     • {error[:80]}")
        
        return runner, result
        
    except Exception as e:
        print(f"\n❌ Runner fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return None, None


async def test_full_team():
    """Test the full DeployTestTeam."""
    from src.agents.deploy_test_team import DeployTestTeam
    
    print("\n" + "=" * 60)
    print("TEST: DeployTestTeam (Full Integration)")
    print("=" * 60)
    
    project_dir = Path("output/full-test-runtime")
    
    if not project_dir.exists():
        print(f"⚠ Projekt nicht gefunden: {project_dir}")
        return
    
    def on_progress(phase: str, data: dict):
        status = data.get("status", "")
        if status == "starting":
            print(f"\n⏳ Phase: {phase}...")
        elif status == "complete" or status == "success":
            print(f"   ✅ {phase} abgeschlossen")
        elif status == "failed":
            print(f"   ❌ {phase} fehlgeschlagen")
        elif status == "running":
            if "iteration" in data:
                print(f"   🔄 Iteration {data['iteration']}...")
    
    team = DeployTestTeam(
        str(project_dir),
        max_fix_iterations=2,
        startup_timeout=30.0,
        on_progress=on_progress,
    )
    
    print(f"\n📂 Projekt: {project_dir}")
    print("⏳ Starte Deploy & Test...")
    
    try:
        result = await team.run()
        
        print(f"\n{'✅' if result.success else '❌'} Team Result:")
        print(f"   Success: {result.success}")
        print(f"   Stack: {result.detected_stack}")
        print(f"   Frontend: {'🟢' if result.frontend_running else '🔴'} Port {result.frontend_port}")
        print(f"   Backend: {'🟢' if result.backend_running else '🔴'} Port {result.backend_port}")
        print(f"   Routes tested: {result.routes_tested}")
        print(f"   Console Errors: {result.console_errors}")
        print(f"   Network Errors: {result.network_errors}")
        print(f"   Backend Errors: {result.backend_errors}")
        print(f"   Fixes: {result.fixes_successful}/{result.fixes_attempted}")
        print(f"   Time: {result.execution_time_ms}ms")
        
        if result.all_errors:
            print(f"\n   All Errors ({len(result.all_errors)}):")
            for error in result.all_errors[:10]:
                print(f"     • {error[:80]}")
        
    except Exception as e:
        print(f"\n❌ Team fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("DeployTestTeam Test Suite")
    print("=" * 60)
    
    # Test 1: EntrypointDetector
    config = await test_entrypoint_detector()
    
    # Test 2: ParallelRunner (nur Startup, dann stoppen)
    runner, runner_result = await test_parallel_runner(config)
    
    if runner:
        print("\n⏳ Stoppe Services...")
        await runner.stop()
        print("   ✅ Services gestoppt")
    
    # Test 3: Full Team Integration
    # Kommentiert da es länger dauert
    # await test_full_team()
    
    print("\n" + "=" * 60)
    print("Tests abgeschlossen!")
    print("=" * 60)
    
    print("\nUm den vollständigen Team-Test auszuführen:")
    print("  Entkommentiere 'await test_full_team()' in main()")


if __name__ == "__main__":
    asyncio.run(main())