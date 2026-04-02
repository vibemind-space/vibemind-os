"""
Test dashboard with real puzzle states and actions
"""

from web.klotski_dashboard_server import KlotskiDashboardClient
import time

def test_with_actions():
    print("[TEST] Creating dashboard client...")
    client = KlotskiDashboardClient()

    # Initial blocks configuration
    blocks_state1 = [
        {'id': 'G', 'x': 1, 'y': 0, 'w': 2, 'h': 2, 'module': 'DMN', 'color': '#9b59b6'},  # 2x2 at (1,0)
        {'id': 'V', 'x': 0, 'y': 0, 'w': 1, 'h': 2, 'module': 'VIS', 'color': '#3498db'},  # Vertical at (0,0)
        {'id': 'A', 'x': 3, 'y': 0, 'w': 1, 'h': 2, 'module': 'AUD', 'color': '#f39c12'},  # Vertical at (3,0)
        {'id': 'S', 'x': 1, 'y': 2, 'w': 2, 'h': 1, 'module': 'SOM', 'color': '#2ecc71'},  # Horizontal at (1,2)
        {'id': 'L', 'x': 0, 'y': 2, 'w': 1, 'h': 1, 'module': 'LAN', 'color': '#e67e22'},
        {'id': 'D', 'x': 3, 'y': 2, 'w': 1, 'h': 1, 'module': 'DLPFC', 'color': '#e74c3c'},
        {'id': 'C', 'x': 0, 'y': 3, 'w': 1, 'h': 1, 'module': 'ACC', 'color': '#1abc9c'},
        {'id': 'I', 'x': 1, 'y': 3, 'w': 1, 'h': 1, 'module': 'INS', 'color': '#8e44ad'},
        {'id': 'M', 'x': 2, 'y': 3, 'w': 1, 'h': 1, 'module': 'MTL', 'color': '#16a085'},
        {'id': 'O', 'x': 3, 'y': 3, 'w': 1, 'h': 1, 'module': 'OFC', 'color': '#e91e63'}
    ]

    # After G moves down
    blocks_state2 = [
        {'id': 'G', 'x': 1, 'y': 1, 'w': 2, 'h': 2, 'module': 'DMN', 'color': '#9b59b6'},  # Moved down!
        {'id': 'V', 'x': 0, 'y': 0, 'w': 1, 'h': 2, 'module': 'VIS', 'color': '#3498db'},
        {'id': 'A', 'x': 3, 'y': 0, 'w': 1, 'h': 2, 'module': 'AUD', 'color': '#f39c12'},
        {'id': 'S', 'x': 1, 'y': 3, 'w': 2, 'h': 1, 'module': 'SOM', 'color': '#2ecc71'},  # Moved down too
        {'id': 'L', 'x': 0, 'y': 2, 'w': 1, 'h': 1, 'module': 'LAN', 'color': '#e67e22'},
        {'id': 'D', 'x': 3, 'y': 2, 'w': 1, 'h': 1, 'module': 'DLPFC', 'color': '#e74c3c'},
        {'id': 'C', 'x': 0, 'y': 3, 'w': 1, 'h': 1, 'module': 'ACC', 'color': '#1abc9c'},
        {'id': 'I', 'x': 1, 'y': 0, 'w': 1, 'h': 1, 'module': 'INS', 'color': '#8e44ad'},  # Filled gap
        {'id': 'M', 'x': 2, 'y': 0, 'w': 1, 'h': 1, 'module': 'MTL', 'color': '#16a085'},
        {'id': 'O', 'x': 3, 'y': 3, 'w': 1, 'h': 1, 'module': 'OFC', 'color': '#e91e63'}
    ]

    # After V moves right
    blocks_state3 = [
        {'id': 'G', 'x': 1, 'y': 1, 'w': 2, 'h': 2, 'module': 'DMN', 'color': '#9b59b6'},
        {'id': 'V', 'x': 1, 'y': 0, 'w': 1, 'h': 2, 'module': 'VIS', 'color': '#3498db'},  # Moved right!
        {'id': 'A', 'x': 3, 'y': 0, 'w': 1, 'h': 2, 'module': 'AUD', 'color': '#f39c12'},
        {'id': 'S', 'x': 1, 'y': 3, 'w': 2, 'h': 1, 'module': 'SOM', 'color': '#2ecc71'},
        {'id': 'L', 'x': 0, 'y': 2, 'w': 1, 'h': 1, 'module': 'LAN', 'color': '#e67e22'},
        {'id': 'D', 'x': 3, 'y': 2, 'w': 1, 'h': 1, 'module': 'DLPFC', 'color': '#e74c3c'},
        {'id': 'C', 'x': 0, 'y': 3, 'w': 1, 'h': 1, 'module': 'ACC', 'color': '#1abc9c'},
        {'id': 'I', 'x': 2, 'y': 0, 'w': 1, 'h': 1, 'module': 'INS', 'color': '#8e44ad'},
        {'id': 'M', 'x': 0, 'y': 0, 'w': 1, 'h': 1, 'module': 'MTL', 'color': '#16a085'},
        {'id': 'O', 'x': 3, 'y': 3, 'w': 1, 'h': 1, 'module': 'OFC', 'color': '#e91e63'}
    ]

    test_modules = {
        'VIS': 0.85,
        'AUD': 0.45,
        'SOM': 0.62,
        'LAN': 0.73,
        'DLPFC': 0.91,
        'OFC': 0.38,
        'ACC': 0.56,
        'INS': 0.67,
        'MTL': 0.42,
        'DMN': 0.79
    }

    # Update generation stats
    print("[TEST] Updating generation stats...")
    client.update_generation(
        generation=0,
        episodes=3,
        success_rate=0.0,
        connections=0,
        extinctions=0
    )

    # Send initial state
    print("[TEST] Sending initial state (BEGINNING)...")
    client.update_agent(
        agent='beginning',
        status='WORKING',
        steps=0,
        moves=0,
        distance=50,
        conv_cost=0,
        blocks=blocks_state1,
        modules=test_modules,
        heart=0.70,
        brain=0.30
    )

    time.sleep(2)  # Wait for user to see

    # Send state after G moves down
    print("[TEST] Sending action: G moved DOWN...")
    client.update_agent(
        agent='beginning',
        status='WORKING',
        steps=1,
        moves=1,
        distance=49,
        conv_cost=0,
        blocks=blocks_state2,
        modules=test_modules,
        heart=0.70,
        brain=0.30,
        action={'block_id': 'G', 'direction': 'down', 'from_pos': (1, 0), 'to_pos': (1, 1)}
    )

    time.sleep(3)  # Let animation play

    # Send state after V moves right
    print("[TEST] Sending action: V moved RIGHT...")
    client.update_agent(
        agent='beginning',
        status='WORKING',
        steps=2,
        moves=2,
        distance=48,
        conv_cost=0,
        blocks=blocks_state3,
        modules=test_modules,
        heart=0.70,
        brain=0.30,
        action={'block_id': 'V', 'direction': 'right', 'from_pos': (0, 0), 'to_pos': (1, 0)}
    )

    print("[TEST] Data sent successfully!")
    print("[TEST] Check http://localhost:5004 to see blocks and action labels")

if __name__ == '__main__':
    test_with_actions()
