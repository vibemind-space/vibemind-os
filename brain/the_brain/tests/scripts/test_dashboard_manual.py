"""
Manual test - send data to Klotski dashboard
"""

from web.klotski_dashboard_server import KlotskiDashboardClient
import time

def test_manual_update():
    print("[TEST] Creating dashboard client...")
    client = KlotskiDashboardClient()

    print("[TEST] Sending test data to dashboard...")

    # Test blocks (10 brain modules)
    test_blocks = [
        {'id': 'G', 'x': 1, 'y': 0, 'w': 2, 'h': 2, 'module': 'DMN', 'color': '#9b59b6'},
        {'id': 'V', 'x': 0, 'y': 0, 'w': 2, 'h': 1, 'module': 'VIS', 'color': '#3498db'},
        {'id': 'A', 'x': 0, 'y': 1, 'w': 1, 'h': 1, 'module': 'AUD', 'color': '#f39c12'},
        {'id': 'S', 'x': 3, 'y': 1, 'w': 1, 'h': 1, 'module': 'SOM', 'color': '#2ecc71'},
        {'id': 'L', 'x': 0, 'y': 2, 'w': 1, 'h': 1, 'module': 'LAN', 'color': '#e67e22'},
        {'id': 'D', 'x': 1, 'y': 2, 'w': 2, 'h': 1, 'module': 'DLPFC', 'color': '#e74c3c'},
        {'id': 'C', 'x': 3, 'y': 2, 'w': 1, 'h': 2, 'module': 'ACC', 'color': '#1abc9c'},
        {'id': 'I', 'x': 0, 'y': 3, 'w': 1, 'h': 1, 'module': 'INS', 'color': '#8e44ad'},
        {'id': 'M', 'x': 1, 'y': 3, 'w': 2, 'h': 1, 'module': 'MTL', 'color': '#16a085'},
        {'id': 'O', 'x': 0, 'y': 4, 'w': 1, 'h': 1, 'module': 'OFC', 'color': '#e91e63'}
    ]

    # Test module activations
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
        episodes=1,
        success_rate=0.33,
        connections=0,
        extinctions=0
    )

    # Update beginning agent
    print("[TEST] Updating BEGINNING agent...")
    client.update_agent(
        agent='beginning',
        status='WORKING',
        steps=15,
        moves=8,
        distance=42,
        conv_cost=0,
        blocks=test_blocks,
        modules=test_modules,
        heart=0.70,
        brain=0.30
    )

    # Update mid agent
    print("[TEST] Updating MID agent...")
    client.update_agent(
        agent='mid',
        status='WAITING',
        steps=0,
        moves=0,
        distance=81,
        conv_cost=0,
        blocks=test_blocks,
        modules={k: v * 0.5 for k, v in test_modules.items()},
        heart=0.70,
        brain=0.30
    )

    # Update end agent
    print("[TEST] Updating END agent...")
    client.update_agent(
        agent='end',
        status='SOLVED',
        steps=25,
        moves=12,
        distance=0,
        conv_cost=2,
        blocks=test_blocks,
        modules={k: v * 1.2 for k, v in test_modules.items()},
        heart=0.70,
        brain=0.30
    )

    print("[TEST] ✓ Data sent successfully!")
    print("[TEST] Open http://localhost:5004 to see the dashboard")
    print("[TEST] Dashboard should now show blocks and module activations")

if __name__ == '__main__':
    test_manual_update()
