"""
Training Script for SpeakingCTM

This script provides utilities to:
1. Collect training data using external LLM
2. Train the CTM on meaningful tasks
3. Train the Decoder on collected (thought, response) pairs

Usage:
    # Phase 1: Collect data (requires API key)
    python scripts/train_speaking_ctm.py collect --num_samples 1000

    # Phase 2: Train decoder on collected data
    python scripts/train_speaking_ctm.py train_decoder --corpus data/thought_corpus

    # Phase 3: End-to-end evaluation
    python scripts/train_speaking_ctm.py evaluate
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime
import random

sys.path.insert(0, str(Path(__file__).parent.parent))

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader

from core.speaking_ctm import SpeakingCTM
from core.thought_logger import ThoughtLogger, ThoughtCorpusDataset
from core.hybrid_ctm import HybridNeuroSymbolicCTM


# ============================================================
# Training Tasks - Diverse set for learning
# ============================================================

TRAINING_TASKS = [
    # Logic/Reasoning
    "If all cats have tails and Fluffy is a cat, what can we conclude?",
    "What comes next in the sequence: 2, 4, 8, 16, ?",
    "A is taller than B, B is taller than C. Who is shortest?",

    # Explanation
    "Explain how a computer stores data",
    "Why does the sky appear blue?",
    "How does photosynthesis work?",

    # Definition
    "What is recursion in programming?",
    "Define machine learning in simple terms",
    "What is the difference between RAM and ROM?",

    # Problem Solving
    "How would you sort a list of numbers efficiently?",
    "Design a system to track user logins",
    "What algorithm finds the shortest path in a graph?",

    # Creative
    "Describe a sunset over the ocean",
    "Write a short poem about learning",
    "Imagine a world without electricity",

    # Factual
    "What is the capital of Germany?",
    "When was the first computer invented?",
    "What programming language was Python named after?",
]


# ============================================================
# Synthetic Response Generator (for testing without LLM)
# ============================================================

class SyntheticResponseGenerator:
    """
    Generates synthetic responses for training without external LLM.

    These are template-based and not as good as real LLM responses,
    but useful for testing the training pipeline.
    """

    TEMPLATES = {
        "explain": "This concept involves {topic}. The key aspects are: 1) {aspect1}, 2) {aspect2}. In summary, {conclusion}.",
        "define": "{term} is defined as {definition}. It is commonly used in {context}.",
        "logic": "Based on the given premises, we can logically conclude that {conclusion}. This follows from {reasoning}.",
        "default": "The answer to this question involves understanding {topic}. Key points include {point1} and {point2}."
    }

    def generate(self, task: str) -> str:
        """Generate a synthetic response for a task."""
        task_lower = task.lower()

        if "explain" in task_lower or "how" in task_lower:
            template = self.TEMPLATES["explain"]
            return template.format(
                topic="the underlying mechanisms",
                aspect1="the fundamental principles",
                aspect2="practical applications",
                conclusion="this forms a coherent system"
            )
        elif "what is" in task_lower or "define" in task_lower:
            template = self.TEMPLATES["define"]
            words = task.split()
            term = " ".join(words[-3:]) if len(words) > 3 else task
            return template.format(
                term=term,
                definition="a concept in this domain",
                context="technical and practical applications"
            )
        elif "if" in task_lower or "conclude" in task_lower:
            template = self.TEMPLATES["logic"]
            return template.format(
                conclusion="the logical inference follows",
                reasoning="the stated premises and logical rules"
            )
        else:
            template = self.TEMPLATES["default"]
            return template.format(
                topic="the subject matter",
                point1="foundational concepts",
                point2="practical implications"
            )


# ============================================================
# Data Collection
# ============================================================

def collect_training_data(
    num_samples: int = 1000,
    log_dir: str = "data/thought_corpus",
    use_synthetic: bool = True,
    device: str = "cpu"
):
    """
    Collect training data for the decoder.

    Args:
        num_samples: Number of samples to collect
        log_dir: Directory for logging
        use_synthetic: Use synthetic responses (True) or require LLM API (False)
        device: Torch device
    """
    print("=" * 60)
    print("Collecting Training Data")
    print("=" * 60)

    # Create CTM
    ctm = SpeakingCTM(
        feature_dim=256,
        thought_dim=2048,
        max_iterations=30,
        enable_logging=True,
        log_dir=log_dir,
        device=device
    )

    # Response generator
    if use_synthetic:
        generator = SyntheticResponseGenerator()
        print("Using synthetic response generator")
    else:
        # TODO: Integrate with actual LLM API
        raise NotImplementedError("LLM API integration not implemented yet")

    # Collect samples
    tasks = TRAINING_TASKS * (num_samples // len(TRAINING_TASKS) + 1)
    random.shuffle(tasks)
    tasks = tasks[:num_samples]

    collected = 0
    for i, task in enumerate(tasks):
        try:
            # Think
            ctm_output = ctm.think(task)

            # Generate response
            response = generator.generate(task)

            # Log
            ctm.logger.log(
                thought_vector=ctm_output.thought_vector,
                llm_response=response,
                task=task,
                certainty=ctm_output.certainties[:, -1].mean().item(),
                reasoning_steps=ctm_output.reasoning_steps
            )
            collected += 1

            if (i + 1) % 100 == 0:
                print(f"  Collected {collected}/{num_samples} samples")

        except Exception as e:
            print(f"  Error on sample {i}: {e}")

    # End session
    summary = ctm.logger.end_session()
    print(f"\nCollection complete!")
    print(f"  Total collected: {collected}")
    print(f"  Log file: {summary['log_file']}")

    return summary


# ============================================================
# Decoder Training
# ============================================================

def train_decoder(
    corpus_path: str = "data/thought_corpus",
    epochs: int = 10,
    batch_size: int = 8,
    learning_rate: float = 1e-4,
    unfreeze_layers: int = 0,
    save_path: str = "data/thought_decoder_checkpoints",
    device: str = "cpu"
):
    """
    Train the ThoughtDecoder on collected corpus.

    Args:
        corpus_path: Path to thought corpus
        epochs: Number of training epochs
        batch_size: Training batch size
        learning_rate: Learning rate
        unfreeze_layers: Number of GPT-2 layers to unfreeze
        save_path: Where to save checkpoints
        device: Torch device
    """
    print("=" * 60)
    print("Training ThoughtDecoder")
    print("=" * 60)

    # Load corpus
    corpus = ThoughtLogger.load_corpus(corpus_path)
    if not corpus:
        print(f"No data found in {corpus_path}")
        print("Run 'collect' first to gather training data")
        return

    print(f"Loaded {len(corpus)} training pairs")

    # Split train/val
    val_size = min(100, len(corpus) // 10)
    train_corpus = corpus[val_size:]
    val_corpus = corpus[:val_size]

    print(f"  Train: {len(train_corpus)}")
    print(f"  Val: {len(val_corpus)}")

    # Create CTM with decoder
    ctm = SpeakingCTM(
        feature_dim=256,
        thought_dim=2048,
        device=device
    )

    # Optionally unfreeze GPT-2 layers
    if unfreeze_layers > 0:
        ctm.decoder.unfreeze_top_layers(unfreeze_layers)
        print(f"Unfroze top {unfreeze_layers} GPT-2 layers")

    # Create datasets
    train_dataset = ThoughtCorpusDataset(train_corpus, ctm.decoder.tokenizer)
    val_dataset = ThoughtCorpusDataset(val_corpus, ctm.decoder.tokenizer)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size)

    # Optimizer
    trainable_params = [p for p in ctm.decoder.parameters() if p.requires_grad]
    optimizer = optim.AdamW(trainable_params, lr=learning_rate)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    # Training loop
    history = {'train_loss': [], 'val_loss': []}
    best_val_loss = float('inf')

    for epoch in range(epochs):
        # Train
        ctm.decoder.train()
        train_loss = 0
        for batch in train_loader:
            thoughts = batch['thought_vector'].to(device)
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)

            optimizer.zero_grad()
            outputs = ctm.decoder(thoughts, input_ids, attention_mask)
            loss = outputs['loss']
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable_params, 1.0)
            optimizer.step()

            train_loss += loss.item()

        train_loss /= len(train_loader)
        history['train_loss'].append(train_loss)

        # Validate
        ctm.decoder.eval()
        val_loss = 0
        with torch.no_grad():
            for batch in val_loader:
                thoughts = batch['thought_vector'].to(device)
                input_ids = batch['input_ids'].to(device)
                attention_mask = batch['attention_mask'].to(device)

                outputs = ctm.decoder(thoughts, input_ids, attention_mask)
                val_loss += outputs['loss'].item()

        val_loss /= len(val_loader)
        history['val_loss'].append(val_loss)

        scheduler.step()

        print(f"Epoch {epoch + 1}/{epochs} - Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")

        # Save best
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            ctm.decoder.save(save_path)
            print(f"  -> Saved best model (val_loss: {val_loss:.4f})")

    # Save final
    ctm.decoder.save(f"{save_path}_final")

    # Save history
    history_path = Path(save_path) / "training_history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with open(history_path, 'w') as f:
        json.dump(history, f, indent=2)

    print(f"\nTraining complete!")
    print(f"  Best val loss: {best_val_loss:.4f}")
    print(f"  Saved to: {save_path}")

    return history


# ============================================================
# Evaluation
# ============================================================

def evaluate(
    ctm_checkpoint: str = None,
    decoder_checkpoint: str = "data/thought_decoder_checkpoints",
    device: str = "cpu"
):
    """
    Evaluate the trained SpeakingCTM.
    """
    print("=" * 60)
    print("Evaluating SpeakingCTM")
    print("=" * 60)

    # Load trained CTM
    ctm = SpeakingCTM(
        feature_dim=256,
        thought_dim=2048,
        decoder_checkpoint=decoder_checkpoint if Path(decoder_checkpoint).exists() else None,
        device=device
    )

    # Test tasks
    test_tasks = [
        "What is machine learning?",
        "Explain how sorting algorithms work",
        "If it rains, the ground gets wet. It rained. What happened?",
        "What is the capital of France?",
        "Describe the process of photosynthesis",
    ]

    print("\nTest Results:")
    print("-" * 40)

    for task in test_tasks:
        result = ctm.think_and_speak(task, max_new_tokens=50)

        print(f"\nTask: {task}")
        print(f"  Certainty: {result.certainty:.4f}")
        print(f"  Steps: {result.reasoning_steps}")
        print(f"  Response: {result.response[:150]}...")

    print("\n" + "=" * 60)


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Train SpeakingCTM')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Collect command
    collect_parser = subparsers.add_parser('collect', help='Collect training data')
    collect_parser.add_argument('--num_samples', type=int, default=1000)
    collect_parser.add_argument('--log_dir', type=str, default='data/thought_corpus')
    collect_parser.add_argument('--device', type=str, default='cpu')

    # Train decoder command
    train_parser = subparsers.add_parser('train_decoder', help='Train the decoder')
    train_parser.add_argument('--corpus', type=str, default='data/thought_corpus')
    train_parser.add_argument('--epochs', type=int, default=10)
    train_parser.add_argument('--batch_size', type=int, default=8)
    train_parser.add_argument('--lr', type=float, default=1e-4)
    train_parser.add_argument('--unfreeze_layers', type=int, default=0)
    train_parser.add_argument('--save_path', type=str, default='data/thought_decoder_checkpoints')
    train_parser.add_argument('--device', type=str, default='cpu')

    # Evaluate command
    eval_parser = subparsers.add_parser('evaluate', help='Evaluate the system')
    eval_parser.add_argument('--decoder', type=str, default='data/thought_decoder_checkpoints')
    eval_parser.add_argument('--device', type=str, default='cpu')

    args = parser.parse_args()

    if args.command == 'collect':
        collect_training_data(
            num_samples=args.num_samples,
            log_dir=args.log_dir,
            device=args.device
        )
    elif args.command == 'train_decoder':
        train_decoder(
            corpus_path=args.corpus,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            unfreeze_layers=args.unfreeze_layers,
            save_path=args.save_path,
            device=args.device
        )
    elif args.command == 'evaluate':
        evaluate(
            decoder_checkpoint=args.decoder,
            device=args.device
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
