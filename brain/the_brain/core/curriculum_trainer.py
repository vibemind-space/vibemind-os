"""
CurriculumTrainer - Progressive Difficulty Training

Implements curriculum learning for the SpeakingCTM system.
Training progresses from simple to complex tasks, allowing the
model to build foundational skills before tackling harder problems.

Curriculum Levels:
1. Definitions - Simple "What is X?" questions
2. Explanations - "Explain how X works" with more detail
3. Reasoning - Logical deduction and inference
4. Problem Solving - Multi-step complex tasks

Usage:
    from core.curriculum_trainer import CurriculumTrainer

    trainer = CurriculumTrainer(
        ctm=speaking_ctm,
        provider="anthropic",
        api_key="your-key"
    )

    history = trainer.train(
        levels=[1, 2, 3, 4],
        samples_per_level=500,
        epochs_per_level=3
    )
"""

import asyncio
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any, Callable
import random
import time

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader

try:
    from core.thought_logger import ThoughtLogger, ThoughtCorpusDataset
    from core.llm_data_collector import LLMDataCollector, get_provider
except ImportError:
    from thought_logger import ThoughtLogger, ThoughtCorpusDataset
    from llm_data_collector import LLMDataCollector, get_provider


@dataclass
class CurriculumLevel:
    """Definition of a curriculum level."""
    level: int
    name: str
    description: str
    target_certainty: float
    max_response_words: int
    task_generator: Callable[[], List[str]]


@dataclass
class LevelResult:
    """Results from training one level."""
    level: int
    name: str
    samples_collected: int
    epochs_trained: int
    final_train_loss: float
    final_val_loss: float
    avg_certainty: float
    target_certainty: float
    passed: bool


class TaskGenerators:
    """Collection of task generators for each curriculum level."""

    @staticmethod
    def definitions(count: int = 100) -> List[str]:
        """Level 1: Simple definitions."""
        base_topics = [
            "algorithm", "variable", "function", "loop", "array",
            "string", "integer", "boolean", "class", "object",
            "method", "parameter", "return value", "condition", "iteration",
            "recursion", "database", "API", "server", "client",
            "protocol", "encryption", "authentication", "cache", "memory",
            "CPU", "GPU", "compiler", "interpreter", "syntax",
            "semantics", "data structure", "binary", "hexadecimal", "ASCII",
            "machine learning", "neural network", "deep learning", "AI",
            "cloud computing", "virtualization", "container", "microservice",
        ]

        templates = [
            "What is a {topic}?",
            "Define {topic} in simple terms",
            "What does {topic} mean in computing?",
            "Explain what a {topic} is",
        ]

        tasks = []
        for _ in range(count):
            topic = random.choice(base_topics)
            template = random.choice(templates)
            tasks.append(template.format(topic=topic))

        return tasks

    @staticmethod
    def explanations(count: int = 100) -> List[str]:
        """Level 2: Explanations."""
        topics = [
            ("how sorting algorithms work", "computer science"),
            ("the concept of inheritance", "object-oriented programming"),
            ("how the internet works", "networking"),
            ("the difference between stack and queue", "data structures"),
            ("how encryption protects data", "security"),
            ("how compilers work", "programming languages"),
            ("memory management", "operating systems"),
            ("how databases store data", "database systems"),
            ("the client-server model", "distributed systems"),
            ("how version control works", "software development"),
            ("the concept of polymorphism", "OOP"),
            ("how hash tables work", "data structures"),
            ("the TCP/IP protocol", "networking"),
            ("how garbage collection works", "memory management"),
            ("the MVC architecture pattern", "software design"),
        ]

        templates = [
            "Explain {topic}",
            "How does {topic} work?",
            "Describe {topic} in detail",
            "Walk me through {topic}",
        ]

        tasks = []
        for _ in range(count):
            topic, _ = random.choice(topics)
            template = random.choice(templates)
            tasks.append(template.format(topic=topic))

        return tasks

    @staticmethod
    def reasoning(count: int = 100) -> List[str]:
        """Level 3: Logical reasoning."""
        logic_tasks = [
            "If all programmers use computers and John is a programmer, what can we conclude about John?",
            "If A implies B and B implies C, what can we say about the relationship between A and C?",
            "What comes next in the sequence: 2, 4, 8, 16, ?",
            "If some developers are designers and all designers are creative, are some developers creative?",
            "If X > Y and Y > Z, what is the relationship between X and Z?",
            "Solve: If 2x + 5 = 13, what is x?",
            "What's the logical flaw in: 'All A are B, all C are B, therefore all A are C'?",
            "If the probability of event A is 0.3, what's the probability of not A?",
            "Complete the pattern: 1, 1, 2, 3, 5, 8, ?",
            "If it takes 5 workers 5 hours to build 5 tables, how long for 10 workers to build 10 tables?",
            "Given: All mammals are warm-blooded. Whales are mammals. Conclusion?",
            "If today is Wednesday and the meeting is in 3 days, what day is the meeting?",
            "What's the next prime number after 17?",
            "If A XOR B = 1 and A = 1, what is B?",
            "Complete: North is to South as East is to ?",
        ]

        tasks = []
        for _ in range(count):
            tasks.append(random.choice(logic_tasks))

        return tasks

    @staticmethod
    def problem_solving(count: int = 100) -> List[str]:
        """Level 4: Complex problem solving."""
        problems = [
            "Design a system to handle user authentication for a web application",
            "How would you optimize a slow database query?",
            "Design a caching strategy for a high-traffic API",
            "How would you implement rate limiting for an API?",
            "Design a notification system that can handle millions of users",
            "How would you debug a memory leak in a production application?",
            "Design a search feature for a large e-commerce platform",
            "How would you scale a monolithic application?",
            "Design a recommendation system for a content platform",
            "How would you implement a real-time collaboration feature?",
            "Design an error handling strategy for a distributed system",
            "How would you migrate a legacy system to microservices?",
            "Design a logging and monitoring system for a cloud application",
            "How would you implement pagination for a large dataset?",
            "Design a backup and recovery strategy for critical data",
        ]

        tasks = []
        for _ in range(count):
            tasks.append(random.choice(problems))

        return tasks


# Default curriculum levels
DEFAULT_LEVELS = [
    CurriculumLevel(
        level=1,
        name="Definitions",
        description="Simple 'What is X?' questions",
        target_certainty=0.5,
        max_response_words=50,
        task_generator=lambda: TaskGenerators.definitions(100)
    ),
    CurriculumLevel(
        level=2,
        name="Explanations",
        description="'Explain how X works' with more detail",
        target_certainty=0.6,
        max_response_words=100,
        task_generator=lambda: TaskGenerators.explanations(100)
    ),
    CurriculumLevel(
        level=3,
        name="Reasoning",
        description="Logical deduction and inference",
        target_certainty=0.7,
        max_response_words=150,
        task_generator=lambda: TaskGenerators.reasoning(100)
    ),
    CurriculumLevel(
        level=4,
        name="Problem Solving",
        description="Multi-step complex tasks",
        target_certainty=0.8,
        max_response_words=200,
        task_generator=lambda: TaskGenerators.problem_solving(100)
    ),
]


class CurriculumTrainer:
    """
    Curriculum learning trainer for SpeakingCTM.

    Trains the decoder progressively on increasingly difficult tasks,
    allowing foundational skills to develop before tackling complexity.

    Parameters:
        ctm: SpeakingCTM instance to train
        provider: LLM provider for data collection ('anthropic', 'openai', 'ollama', 'synthetic')
        api_key: API key for LLM provider
        log_dir: Directory for training data and checkpoints
        levels: List of CurriculumLevel definitions
        device: Torch device
    """

    def __init__(
        self,
        ctm,  # SpeakingCTM
        provider: str = "synthetic",
        api_key: Optional[str] = None,
        log_dir: str = "data/curriculum_training",
        levels: Optional[List[CurriculumLevel]] = None,
        device: str = "cpu"
    ):
        self.ctm = ctm
        self.provider = provider
        self.api_key = api_key
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.levels = levels or DEFAULT_LEVELS
        self.device = device

        # Data collector
        self.collector = LLMDataCollector(
            provider=provider,
            api_key=api_key,
            log_dir=str(self.log_dir / "corpus"),
            batch_size=5
        )

        # Training history
        self.history = {
            'levels': [],
            'total_samples': 0,
            'total_epochs': 0
        }

    def collect_level_data(
        self,
        level: CurriculumLevel,
        num_samples: int
    ) -> List[Dict[str, Any]]:
        """Collect training data for a curriculum level."""
        print(f"\n[CurriculumTrainer] Collecting data for Level {level.level}: {level.name}")
        print(f"  Description: {level.description}")
        print(f"  Samples: {num_samples}")

        # Generate tasks
        tasks = level.task_generator()
        if len(tasks) < num_samples:
            # Repeat tasks if needed
            tasks = tasks * (num_samples // len(tasks) + 1)
        tasks = tasks[:num_samples]
        random.shuffle(tasks)

        # Collect data
        results = self.collector.collect_sync(tasks, self.ctm)

        return results

    def train_level(
        self,
        level: CurriculumLevel,
        data: List[Dict[str, Any]],
        epochs: int = 3,
        batch_size: int = 8,
        learning_rate: float = 1e-4,
        val_split: float = 0.1
    ) -> LevelResult:
        """Train decoder on data for one curriculum level."""
        print(f"\n[CurriculumTrainer] Training Level {level.level}: {level.name}")
        print(f"  Epochs: {epochs}")
        print(f"  Data samples: {len(data)}")

        if len(data) < 2:
            print("  Not enough data to train!")
            return LevelResult(
                level=level.level,
                name=level.name,
                samples_collected=len(data),
                epochs_trained=0,
                final_train_loss=float('inf'),
                final_val_loss=float('inf'),
                avg_certainty=0.0,
                target_certainty=level.target_certainty,
                passed=False
            )

        # Prepare corpus format
        corpus = []
        for item in data:
            corpus.append({
                'thought_vector': item['thought_vector'].squeeze(0) if item['thought_vector'].dim() > 1 else item['thought_vector'],
                'response': item['response'],
                'certainty': item['certainty']
            })

        # Split train/val
        val_size = max(1, int(len(corpus) * val_split))
        train_corpus = corpus[val_size:]
        val_corpus = corpus[:val_size]

        # Create datasets
        train_dataset = ThoughtCorpusDataset(train_corpus, self.ctm.decoder.tokenizer)
        val_dataset = ThoughtCorpusDataset(val_corpus, self.ctm.decoder.tokenizer)

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size)

        # Optimizer
        trainable_params = [p for p in self.ctm.decoder.parameters() if p.requires_grad]
        optimizer = optim.AdamW(trainable_params, lr=learning_rate)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

        # Training loop
        train_losses = []
        val_losses = []

        for epoch in range(epochs):
            # Train
            self.ctm.decoder.train()
            train_loss = 0
            for batch in train_loader:
                thoughts = batch['thought_vector'].to(self.device)
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)

                optimizer.zero_grad()
                outputs = self.ctm.decoder(thoughts, input_ids, attention_mask)
                loss = outputs['loss']
                loss.backward()
                torch.nn.utils.clip_grad_norm_(trainable_params, 1.0)
                optimizer.step()

                train_loss += loss.item()

            train_loss /= len(train_loader)
            train_losses.append(train_loss)

            # Validate
            self.ctm.decoder.eval()
            val_loss = 0
            with torch.no_grad():
                for batch in val_loader:
                    thoughts = batch['thought_vector'].to(self.device)
                    input_ids = batch['input_ids'].to(self.device)
                    attention_mask = batch['attention_mask'].to(self.device)

                    outputs = self.ctm.decoder(thoughts, input_ids, attention_mask)
                    val_loss += outputs['loss'].item()

            val_loss /= len(val_loader)
            val_losses.append(val_loss)

            scheduler.step()

            print(f"  Epoch {epoch + 1}/{epochs} - Train: {train_loss:.4f}, Val: {val_loss:.4f}")

        # Compute average certainty
        avg_certainty = sum(item['certainty'] for item in data) / len(data)

        # Check if level passed
        passed = avg_certainty >= level.target_certainty

        result = LevelResult(
            level=level.level,
            name=level.name,
            samples_collected=len(data),
            epochs_trained=epochs,
            final_train_loss=train_losses[-1] if train_losses else float('inf'),
            final_val_loss=val_losses[-1] if val_losses else float('inf'),
            avg_certainty=avg_certainty,
            target_certainty=level.target_certainty,
            passed=passed
        )

        # Save checkpoint
        checkpoint_path = self.log_dir / f"level_{level.level}_checkpoint"
        self.ctm.decoder.save(str(checkpoint_path))

        return result

    def train(
        self,
        level_indices: Optional[List[int]] = None,
        samples_per_level: int = 500,
        epochs_per_level: int = 3,
        batch_size: int = 8,
        learning_rate: float = 1e-4,
        require_passing: bool = True
    ) -> Dict[str, Any]:
        """
        Full curriculum training.

        Args:
            level_indices: Which levels to train (1-indexed). None = all
            samples_per_level: Samples to collect per level
            epochs_per_level: Training epochs per level
            batch_size: Training batch size
            learning_rate: Learning rate
            require_passing: If True, stop if level fails

        Returns:
            Training history dict
        """
        print("=" * 60)
        print("Starting Curriculum Training")
        print("=" * 60)

        # Select levels
        if level_indices is None:
            levels_to_train = self.levels
        else:
            levels_to_train = [l for l in self.levels if l.level in level_indices]

        print(f"Training {len(levels_to_train)} levels:")
        for level in levels_to_train:
            print(f"  Level {level.level}: {level.name} (target: {level.target_certainty:.1%})")

        results = []

        for level in levels_to_train:
            print("\n" + "-" * 40)
            print(f"Level {level.level}: {level.name}")
            print("-" * 40)

            # Collect data
            data = self.collect_level_data(level, samples_per_level)

            if len(data) == 0:
                print(f"  No data collected, skipping level")
                continue

            # Train
            result = self.train_level(
                level=level,
                data=data,
                epochs=epochs_per_level,
                batch_size=batch_size,
                learning_rate=learning_rate
            )

            results.append(result)
            self.history['levels'].append(asdict(result))
            self.history['total_samples'] += result.samples_collected
            self.history['total_epochs'] += result.epochs_trained

            # Check pass/fail
            status = "PASSED" if result.passed else "FAILED"
            print(f"\n  Level {level.level} {status}")
            print(f"  Avg Certainty: {result.avg_certainty:.3f} (target: {level.target_certainty:.3f})")

            if require_passing and not result.passed:
                print(f"  Stopping: Level {level.level} did not meet target")
                break

        # Save history
        history_path = self.log_dir / "training_history.json"
        with open(history_path, 'w') as f:
            json.dump(self.history, f, indent=2)

        # Summary
        print("\n" + "=" * 60)
        print("Curriculum Training Summary")
        print("=" * 60)
        print(f"Levels completed: {len(results)}")
        print(f"Total samples: {self.history['total_samples']}")
        print(f"Total epochs: {self.history['total_epochs']}")

        for result in results:
            status = "✓" if result.passed else "✗"
            print(f"  {status} Level {result.level}: {result.name} "
                  f"(certainty: {result.avg_certainty:.3f}/{result.target_certainty:.3f})")

        return self.history


if __name__ == "__main__":
    print("=" * 60)
    print("Testing CurriculumTrainer")
    print("=" * 60)

    # Test task generators
    print("\n" + "-" * 40)
    print("Testing Task Generators:")
    print("-" * 40)

    for name, generator in [
        ("Definitions", TaskGenerators.definitions),
        ("Explanations", TaskGenerators.explanations),
        ("Reasoning", TaskGenerators.reasoning),
        ("Problem Solving", TaskGenerators.problem_solving)
    ]:
        tasks = generator(5)
        print(f"\n{name}:")
        for task in tasks[:3]:
            print(f"  - {task[:60]}...")

    # Test with mock CTM
    print("\n" + "-" * 40)
    print("Testing CurriculumTrainer (mock):")
    print("-" * 40)

    class MockCTM:
        def __init__(self):
            self.decoder = MockDecoder()

        def think(self, task):
            class Output:
                thought_vector = torch.randn(1, 2048)
                certainties = torch.tensor([[random.uniform(0.4, 0.9)]])
                reasoning_steps = 10
            return Output()

    class MockDecoder:
        def __init__(self):
            self.tokenizer = None
            self._params = [torch.nn.Parameter(torch.randn(10, 10))]

        def parameters(self):
            return iter(self._params)

        def train(self):
            pass

        def eval(self):
            pass

        def __call__(self, thoughts, input_ids, attention_mask):
            return {'loss': torch.tensor(random.uniform(1.0, 3.0), requires_grad=True)}

        def save(self, path):
            pass

    try:
        # Create mock tokenizer
        from transformers import GPT2Tokenizer
        MockDecoder.tokenizer = GPT2Tokenizer.from_pretrained('gpt2')
        MockDecoder.tokenizer.pad_token = MockDecoder.tokenizer.eos_token

        import tempfile
        temp_dir = tempfile.mkdtemp()

        mock_ctm = MockCTM()
        mock_ctm.decoder.tokenizer = MockDecoder.tokenizer

        trainer = CurriculumTrainer(
            ctm=mock_ctm,
            provider="synthetic",
            log_dir=temp_dir
        )

        # Train just level 1 with few samples
        history = trainer.train(
            level_indices=[1],
            samples_per_level=10,
            epochs_per_level=1,
            require_passing=False
        )

        print(f"\nHistory: {json.dumps(history, indent=2)}")

        import shutil
        shutil.rmtree(temp_dir)

    except ImportError as e:
        print(f"Skipping integration test: {e}")

    print("\n" + "=" * 60)
    print("CurriculumTrainer tests completed!")
    print("=" * 60)
