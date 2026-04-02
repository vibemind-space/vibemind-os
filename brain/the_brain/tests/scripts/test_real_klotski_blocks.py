"""
Test dashboard with REAL Klotski blocks parsed from representation string
"""

from web.klotski_dashboard_server import KlotskiDashboardClient
import time

def create_mock_coordinator_with_parser():
    """Create a mock that has the actual parser method"""

    # Manually implement the fixed parser
    def parse_blocks_from_repr(representation):
        # Character to module mapping
        char_to_module = {
            'a': ('G', 'DMN', '#9b59b6'),
            'b': ('V', 'VIS', '#3498db'),
            'c': ('A', 'AUD', '#f39c12'),
            'd': ('S', 'SOM', '#2ecc71'),
            'e': ('L', 'LAN', '#e67e22'),
            'f': ('D', 'DLPFC', '#e74c3c'),
            'g': ('C', 'ACC', '#1abc9c'),
            'h': ('I', 'INS', '#8e44ad'),
            'i': ('M', 'MTL', '#16a085'),
            'j': ('O', 'OFC', '#e91e63')
        }

        # Parse grid from representation (20 chars, 4×5 row-major)
        grid = [['' for _ in range(4)] for _ in range(5)]
        idx = 0

        for row in range(5):
            for col in range(4):
                if idx >= len(representation):
                    break
                char = representation[idx]
                grid[row][col] = char
                idx += 1

        # Find all unique pieces
        pieces = {}
        for row in range(5):
            for col in range(4):
                char = grid[row][col]
                if char != '' and char != '.':
                    if char not in pieces:
                        pieces[char] = []
                    pieces[char].append((col, row))  # (x, y)

        # Convert pieces to block format
        blocks = []
        for char, cells in sorted(pieces.items()):
            if char not in char_to_module:
                continue

            block_id, module, color = char_to_module[char]

            # Calculate bounding box
            xs = [x for x, y in cells]
            ys = [y for x, y in cells]
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)

            width = x_max - x_min + 1
            height = y_max - y_min + 1

            blocks.append({
                'id': block_id,
                'x': x_min,
                'y': y_min,
                'w': width,
                'h': height,
                'module': module,
                'color': color
            })

        return blocks

    return parse_blocks_from_repr

def test_real_blocks():
    print("[TEST] Testing dashboard with REAL parsed Klotski blocks")
    print("=" * 80)

    # Use the example representation from KlotskiGraphEnv
    test_repr = "jafi.aehddehbbcgbbc."
    print(f"Representation: '{test_repr}'")

    # Parse blocks using the real parser
    parser = create_mock_coordinator_with_parser()
    blocks = parser(test_repr)

    print(f"\nParsed {len(blocks)} blocks:")
    for block in blocks:
        print(f"  {block['id']} ({block['w']}×{block['h']}) at ({block['x']},{block['y']}) - {block['module']}")

    # Check for overlaps manually
    print("\nChecking for overlaps...")
    occupied = {}
    overlaps = []
    for block in blocks:
        for dy in range(block['h']):
            for dx in range(block['w']):
                cell = (block['x'] + dx, block['y'] + dy)
                if cell in occupied:
                    overlaps.append((block['id'], cell, occupied[cell]))
                else:
                    occupied[cell] = block['id']

    if overlaps:
        print(f"  ERROR: Found {len(overlaps)} overlapping cells!")
        for block_id, cell, other_id in overlaps:
            print(f"    Block '{block_id}' overlaps with '{other_id}' at {cell}")
        return False
    else:
        print("  OK: No overlaps!")

    # Send to dashboard
    print("\nSending to dashboard...")
    client = KlotskiDashboardClient()

    test_modules = {
        'VIS': 0.72,
        'AUD': 0.35,
        'SOM': 0.58,
        'LAN': 0.81,
        'DLPFC': 0.93,
        'OFC': 0.41,
        'ACC': 0.62,
        'INS': 0.54,
        'MTL': 0.39,
        'DMN': 0.85
    }

    client.update_generation(
        generation=0,
        episodes=1,
        success_rate=0.0,
        connections=0,
        extinctions=0
    )

    client.update_agent(
        agent='beginning',
        status='WORKING',
        steps=10,
        moves=5,
        distance=45,
        conv_cost=0,
        blocks=blocks,  # REAL parsed blocks!
        modules=test_modules,
        heart=0.70,
        brain=0.30
    )

    print("\n[TEST] REAL blocks sent to dashboard!")
    print("[TEST] Check http://localhost:5004 - blocks should NOT overlap!")
    print("=" * 80)

if __name__ == '__main__':
    test_real_blocks()
