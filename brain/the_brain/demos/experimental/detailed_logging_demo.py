"""
Detailed Logging Demo - Save all inputs/outputs to file
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import numpy as np
from datetime import datetime
from core.multi_brain_swarm import MultiBrainSwarm
from core.semantic_coherence import SemanticEncoder

class DetailedLogger:
    """Logs every step of semantic coherence computation"""

    def __init__(self, log_file="semantic_coherence_log.json"):
        self.log_file = log_file
        self.logs = []

    def log_decision(self, task, decision, brain_answers, embeddings, similarities):
        """Log a complete decision with all intermediate steps"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "task": task,
            "brain_answers": [
                {
                    "brain_id": ans.brain_id,
                    "text": ans.text,
                    "decision_type": ans.decision_type,
                    "confidence": ans.confidence,
                    "embedding_preview": ans.embedding[:5].tolist() if ans.embedding is not None else None
                }
                for ans in brain_answers
            ],
            "similarities": {
                "pairwise": [
                    {
                        "brain_i": i,
                        "brain_j": j,
                        "similarity": float(sim)
                    }
                    for i, j, sim in similarities
                ],
                "matrix": "see separate file"
            },
            "coherence_metrics": {
                "K": float(decision.coherence_K),
                "U": float(decision.disagreement_U),
                "truth_stability": float(decision.truth_stability)
            },
            "decision": {
                "consensus": decision.consensus_decision,
                "mechanism": decision.consensus_mechanism,
                "voting_score": float(decision.consensus_confidence),
                "status": decision.semantic_status
            },
            "votes": {
                brain_id: vote
                for brain_id, vote in decision.brain_votes.items()
            }
        }

        self.logs.append(log_entry)

    def save(self):
        """Save logs to JSON file"""
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.logs, f, indent=2, ensure_ascii=False)
        print(f"\n[+] Logs saved to: {self.log_file}")

def main():
    print("="*70)
    print("DETAILED LOGGING DEMO - Saves all inputs/outputs")
    print("="*70)

    # Create logger
    logger = DetailedLogger("data/logs/semantic_coherence_detailed.json")

    # Create swarm
    swarm = MultiBrainSwarm(
        num_brains=5,
        enable_semantic_coherence=True,
        k_min=0.55,
        green_threshold=0.75,
        alpha=0.5
    )

    # Enable neural embeddings
    if swarm.semantic_layer:
        swarm.semantic_layer.encoder = SemanticEncoder(use_simple=False)
        print("[+] Neural embeddings enabled")

    # Test tasks
    tasks = [
        ("Deploy Docker container with monitoring", "docker"),
        ("Fix GitHub merge conflict", "github"),
        ("Read system logs", "filesystem"),
        ("Execute shell command", "terminal"),
        ("Configure network settings", "network")
    ]

    print(f"\nProcessing {len(tasks)} tasks with detailed logging...\n")

    for i, (task, domain) in enumerate(tasks, 1):
        print(f"{i}. {task}")

        # Make decision
        decision = swarm.collect_brain_votes(
            task_description=task,
            task_type=domain,
            available_decisions=["suggest", "retry", "wait", "terminate"]
        )

        # Get brain answers and compute similarities
        if swarm.semantic_layer and swarm.semantic_layer.consensus_history:
            consensus = swarm.semantic_layer.consensus_history[-1]
            brain_answers = consensus.brain_answers

            # Compute pairwise similarities for logging
            similarities = []
            n = len(brain_answers)
            for i in range(n):
                for j in range(i+1, n):
                    if brain_answers[i].embedding is not None and brain_answers[j].embedding is not None:
                        sim = np.dot(
                            brain_answers[i].embedding,
                            brain_answers[j].embedding
                        )
                        similarities.append((i, j, sim))

            embeddings = [ans.embedding for ans in brain_answers]

            # Log everything
            logger.log_decision(task, decision, brain_answers, embeddings, similarities)

            print(f"   Decision: {decision.consensus_decision} | "
                  f"K={decision.coherence_K:.3f} | "
                  f"Status={decision.semantic_status}")
        else:
            print(f"   (No semantic history available)")

    # Save logs
    logger.save()

    # Print log location and structure
    print("\n" + "="*70)
    print("LOG FILE STRUCTURE")
    print("="*70)
    print("""
The log file contains for each decision:
{
  "timestamp": "2025-10-20T...",
  "task": "Deploy Docker container...",
  "brain_answers": [
    {
      "brain_id": "brain_0",
      "text": "retry because...",
      "decision_type": "retry",
      "confidence": 0.85,
      "embedding_preview": [0.042, 0.103, ...]
    },
    ...
  ],
  "similarities": {
    "pairwise": [
      {"brain_i": 0, "brain_j": 1, "similarity": 0.82},
      ...
    ]
  },
  "coherence_metrics": {
    "K": 0.806,
    "U": 0.003,
    "truth_stability": 0.725
  },
  "decision": {
    "consensus": "suggest",
    "mechanism": "weighted",
    "voting_score": 0.80,
    "status": "GREEN"
  },
  "votes": {
    "brain_0": "suggest",
    "brain_1": "suggest",
    ...
  }
}
    """)

    print("\nYou can now:")
    print("  1. Open data/logs/semantic_coherence_detailed.json")
    print("  2. Inspect every decision step-by-step")
    print("  3. See embeddings, similarities, voting")
    print("  4. Analyze coherence metrics")

    print("\n" + "="*70)

if __name__ == "__main__":
    main()
