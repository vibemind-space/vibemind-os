"""
Brain (Tahlamus) — Neuroscience-inspired cognitive routing system.

Standalone microservices:
- Brain Server     (port 5000)
- Swarm Server     (port 5002)
- Memory API       (port 8001)
- Production API   (port 5001)
"""

from brain.brain_seeder import BrainSeeder

__all__ = ["BrainSeeder"]
