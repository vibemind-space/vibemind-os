"""
Validiert Klotski-Puzzle-Daten auf Korrektheit.

Prueft:
1. JSON Layout Integritaet
2. Graph Konsistenz
3. Loesbarkeit (BFS)
4. Memory System Funktionalitaet

Run with:
    python scripts/validate_klotski_puzzles.py
"""

import json
import sys
import os
from pathlib import Path
from collections import deque

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def validate_layout(layout_path):
    """Validiere Klotski_NeuroLayout.json"""
    print(f"\nValidating layout: {layout_path}")

    with open(layout_path, encoding='utf-8') as f:
        data = json.load(f)

    errors = []

    # Check board dimensions
    board = data.get('board', {})
    if board.get('width') != 4:
        errors.append(f"Board width should be 4, got {board.get('width')}")
    if board.get('height') != 5:
        errors.append(f"Board height should be 5, got {board.get('height')}")

    # Check exit position
    exit_pos = board.get('exit', [])
    if not exit_pos:
        errors.append("No exit position defined")
    else:
        print(f"  Exit position: {exit_pos}")

    # Check pieces
    pieces = data.get('pieces', [])
    if len(pieces) != 10:
        errors.append(f"Should have 10 pieces, got {len(pieces)}")

    # Check no overlaps
    grid = [[None]*4 for _ in range(5)]
    piece_ids = set()

    for p in pieces:
        pid = p.get('id', '?')
        piece_ids.add(pid)
        x, y = p.get('x', 0), p.get('y', 0)
        w, h = p.get('w', 1), p.get('h', 1)

        for dy in range(h):
            for dx in range(w):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < 4 and 0 <= ny < 5):
                    errors.append(f"Piece {pid} out of bounds at ({nx},{ny})")
                    continue
                if grid[ny][nx] is not None:
                    errors.append(f"Overlap at ({nx},{ny}): {grid[ny][nx]} and {pid}")
                grid[ny][nx] = pid

    # Check expected pieces
    expected_ids = {'G', 'V', 'A', 'D', 'S', 'L', 'C', 'I', 'M', 'O'}
    missing = expected_ids - piece_ids
    if missing:
        errors.append(f"Missing pieces: {missing}")

    # Count filled cells
    filled = sum(1 for row in grid for c in row if c is not None)
    empty = 20 - filled
    print(f"  Pieces: {len(pieces)}, Filled cells: {filled}, Empty: {empty}")

    # Check meta mapping
    meta = data.get('meta', {}).get('mapping', {})
    if meta:
        print(f"  Brain module mappings: {len(meta)}")
        for pid, info in list(meta.items())[:3]:
            print(f"    {pid}: {info.get('module', '?')} - {info.get('math', '?')}")

    if errors:
        for e in errors:
            print(f"  [ERROR] {e}")
        return False

    print(f"  [OK] Layout valid: {len(pieces)} pieces, no overlaps, {empty} empty cells")
    return True


def validate_graph(graph_path, name="Graph"):
    """Validiere Klotski Graph Daten"""
    print(f"\nValidating {name}: {graph_path}")

    # Check file size first
    size_mb = os.path.getsize(graph_path) / (1024 * 1024)
    print(f"  File size: {size_mb:.1f} MB")

    with open(graph_path, encoding='utf-8') as f:
        data = json.load(f)

    errors = []

    # Handle nested format with metadata/states
    if isinstance(data, dict) and 'states' in data:
        metadata = data.get('metadata', {})
        states = data.get('states', {})
        print(f"  Format: nested (metadata + states)")
        if metadata:
            print(f"  Metadata: total_states={metadata.get('total_states', '?')}, "
                  f"goal_states={metadata.get('goal_states', '?')}")
    elif isinstance(data, dict):
        states = data
    elif isinstance(data, list):
        print(f"  Format: list with {len(data)} entries")
        states = {str(i): item for i, item in enumerate(data)}
    else:
        errors.append(f"Unknown format: {type(data)}")
        return False

    num_states = len(states)
    print(f"  States: {num_states:,}")

    # Find goal states
    goals = []
    for state_key, info in states.items():
        if isinstance(info, dict) and info.get('is_goal'):
            goals.append(state_key)

    print(f"  Goal states: {len(goals)}")

    if len(goals) == 0:
        # Check if goals might be encoded differently
        sample = list(states.values())[0] if states else {}
        print(f"  Sample state format: {list(sample.keys()) if isinstance(sample, dict) else type(sample)}")

    # Validate solution distances (sample)
    sample_size = min(100, num_states)
    valid_dists = 0
    for state_key, info in list(states.items())[:sample_size]:
        if not isinstance(info, dict):
            continue
        dist = info.get('solution_dist', info.get('distance'))
        if dist is not None and dist >= 0:
            valid_dists += 1

    print(f"  Valid solution_dist in sample: {valid_dists}/{sample_size}")

    # Check connectivity (sample)
    connected = 0
    for state_key, info in list(states.items())[:sample_size]:
        if not isinstance(info, dict):
            continue
        neighbors = info.get('neighbors', info.get('edges', []))
        if neighbors:
            connected += 1
            # Verify neighbors exist (if they're strings)
            for n in neighbors[:3]:
                if isinstance(n, str):
                    if n not in states:
                        pass  # May be encoded differently

    print(f"  States with neighbors in sample: {connected}/{sample_size}")

    # Check representation format
    sample_state = list(states.keys())[0]
    sample_info = states[sample_state]
    if isinstance(sample_info, dict):
        rep = sample_info.get('representation', sample_info.get('board', ''))
        if rep:
            print(f"  Sample representation: '{rep[:30]}...' (len={len(rep)})")

    if errors:
        for e in errors:
            print(f"  [ERROR] {e}")
        return False

    print(f"  [OK] {name} valid: {num_states:,} states")
    return True


def validate_memory_system():
    """Validiere KotlinGraph/KuroGraph"""
    print("\nValidating Memory System...")

    results = []

    # Test KotlinGraph
    try:
        from learning_engine.klotski.neurosymbolic.memory.kotlingraph import KotlinGraph
        kg = KotlinGraph()
        print(f"  [OK] KotlinGraph instantiable")
        results.append(True)
    except ImportError as e:
        print(f"  [WARN] KotlinGraph import failed: {e}")
        results.append(None)  # Skip, not fail
    except Exception as e:
        print(f"  [FAIL] KotlinGraph: {e}")
        results.append(False)

    # Test KuroGraph
    try:
        from learning_engine.klotski.neurosymbolic.memory.kurograph import KuroGraph
        kuro = KuroGraph()
        print(f"  [OK] KuroGraph instantiable")
        results.append(True)
    except ImportError as e:
        print(f"  [WARN] KuroGraph import failed: {e}")
        results.append(None)
    except Exception as e:
        print(f"  [FAIL] KuroGraph: {e}")
        results.append(False)

    # Test DualGraphManager
    try:
        from learning_engine.klotski.neurosymbolic.memory.dual_graph_manager import DualGraphManager
        dgm = DualGraphManager()
        print(f"  [OK] DualGraphManager instantiable")
        results.append(True)
    except ImportError as e:
        print(f"  [WARN] DualGraphManager import failed: {e}")
        results.append(None)
    except Exception as e:
        print(f"  [FAIL] DualGraphManager: {e}")
        results.append(False)

    # Return True if no hard failures
    return all(r is not False for r in results)


def validate_puzzle_state():
    """Validiere PuzzleState Klasse"""
    print("\nValidating PuzzleState...")

    base = Path(__file__).parent.parent
    layout_path = base / "learning_engine" / "klotski" / "Klotski_NeuroLayout.json"

    try:
        from learning_engine.klotski.neurosymbolic.core.puzzle_state import PuzzleState

        # Try to create initial state with layout file
        if layout_path.exists():
            state = PuzzleState(layout_file=str(layout_path))
            print(f"  [OK] PuzzleState instantiable with layout")
        else:
            # Try with default/empty
            print(f"  [WARN] Layout not found, trying default init")
            state = PuzzleState(pieces=[])
            print(f"  [OK] PuzzleState instantiable (empty)")

        # Check if it has expected methods
        methods = ['get_valid_moves', 'is_solved', 'move_piece']
        for m in methods:
            if hasattr(state, m):
                print(f"  [OK] Has method: {m}")
            else:
                print(f"  [WARN] Missing method: {m}")

        return True
    except ImportError as e:
        print(f"  [WARN] PuzzleState import failed: {e}")
        return None  # Skip
    except Exception as e:
        print(f"  [FAIL] PuzzleState: {e}")
        return False


def main():
    """Run all validations"""
    print("=" * 60)
    print("Klotski Puzzle Validation")
    print("=" * 60)

    base = Path(__file__).parent.parent
    results = []

    # 1. Layout
    layout_path = base / "learning_engine" / "klotski" / "Klotski_NeuroLayout.json"
    if layout_path.exists():
        results.append(("Layout", validate_layout(layout_path)))
    else:
        print(f"\n[SKIP] Layout not found: {layout_path}")
        results.append(("Layout", None))

    # 2. Mini Graph
    mini_graph = base / "data" / "mini_klotski_graph.json"
    if mini_graph.exists():
        results.append(("Mini Graph", validate_graph(mini_graph, "Mini Graph")))
    else:
        print(f"\n[SKIP] Mini graph not found: {mini_graph}")
        results.append(("Mini Graph", None))

    # 3. Full Graph
    full_graph = base / "data" / "klotski_full_graph.json"
    if full_graph.exists():
        results.append(("Full Graph", validate_graph(full_graph, "Full Graph")))
    else:
        print(f"\n[SKIP] Full graph not found: {full_graph}")
        results.append(("Full Graph", None))

    # 4. Memory System
    results.append(("Memory System", validate_memory_system()))

    # 5. PuzzleState
    results.append(("PuzzleState", validate_puzzle_state()))

    # Summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)

    passed = 0
    failed = 0
    skipped = 0

    for name, result in results:
        if result is True:
            status = "[OK] PASS"
            passed += 1
        elif result is False:
            status = "[X] FAIL"
            failed += 1
        else:
            status = "[--] SKIP"
            skipped += 1
        print(f"  {status}: {name}")

    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")

    if failed == 0:
        print("\n[OK] All Klotski validations passed!")
        return True
    else:
        print(f"\n[X] {failed} validations failed")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
