"""
Test block parser with known Klotski representation strings
"""

import logging
logging.basicConfig(level=logging.DEBUG)

# Mock setup
class MockEnv:
    def __init__(self, representation):
        self.graph = {
            'test_hash': {
                'representation': representation
            }
        }

def test_parser():
    from core.klotski_dark_mode_coordinator import KlotskiDarkModeCoordinator

    # Create a mock coordinator just to test the parsing method
    print("=" * 80)
    print("TESTING BLOCK PARSER")
    print("=" * 80)

    # Test with example from KlotskiGraphEnv comments:
    # Format: "jafi.aehddehbbcgbbc." (14 characters for 4×5 grid minus 6 for 2×2 piece)
    test_repr = "jafi.aehddehbbcgbbc."

    print(f"\nTest representation: '{test_repr}'")
    print(f"Length: {len(test_repr)} characters")

    # Parse it character by character to understand structure
    print("\nCharacter-by-character parsing (row-major, 4 cols × 5 rows):")
    idx = 0
    for row in range(5):
        row_str = ""
        for col in range(4):
            if idx < len(test_repr):
                row_str += test_repr[idx] + " "
            else:
                row_str += "  "
            idx += 1
        print(f"  Row {row}: {row_str}")

    # Now test actual parser
    # Since we can't instantiate full coordinator without graph file,
    # let's manually test the logic

    print("\n" + "=" * 80)
    print("Analyzing piece structure:")
    print("=" * 80)

    # Simulate the parser logic
    char_to_id = {'.': 0}
    next_id = 1

    grid = [['' for _ in range(4)] for _ in range(5)]
    idx = 0

    for row in range(5):
        for col in range(4):
            if idx >= len(test_repr):
                break
            char = test_repr[idx]
            if char not in char_to_id:
                char_to_id[char] = next_id
                next_id += 1
            grid[row][col] = char
            idx += 1

    # Print grid
    print("\nParsed grid:")
    for row in range(5):
        row_str = ""
        for col in range(4):
            row_str += f"[{grid[row][col] if grid[row][col] else ' '}] "
        print(f"  {row_str}")

    # Find pieces
    pieces = {}
    for row in range(5):
        for col in range(4):
            char = grid[row][col]
            if char != '' and char != '.':
                if char not in pieces:
                    pieces[char] = []
                pieces[char].append((col, row))

    print("\nFound pieces:")
    for char in sorted(pieces.keys()):
        cells = pieces[char]
        xs = [x for x, y in cells]
        ys = [y for x, y in cells]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        width = x_max - x_min + 1
        height = y_max - y_min + 1
        print(f"  '{char}': {len(cells)} cells, {width}×{height} at ({x_min},{y_min})")
        print(f"       Cells: {cells}")

    # Check for overlaps
    print("\nChecking for overlaps...")
    occupied = set()
    overlaps = []
    for char, cells in pieces.items():
        for cell in cells:
            if cell in occupied:
                overlaps.append((char, cell))
            occupied.add(cell)

    if overlaps:
        print(f"  ERROR: Found {len(overlaps)} overlapping cells!")
        for char, cell in overlaps:
            print(f"    '{char}' overlaps at {cell}")
    else:
        print("  OK: No overlaps found!")

    # Check grid coverage
    total_occupied = len(occupied)
    total_empty = sum(1 for row in grid for cell in row if cell == '.')
    print(f"\nGrid coverage:")
    print(f"  Occupied cells: {total_occupied}")
    print(f"  Empty cells: {total_empty}")
    print(f"  Total: {total_occupied + total_empty} / 20")

if __name__ == '__main__':
    test_parser()
