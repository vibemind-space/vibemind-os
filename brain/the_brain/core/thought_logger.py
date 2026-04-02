"""
ThoughtLogger - Training Data Collection for Text Decoder

Collects pairs of (thought_vector, llm_response) for training the
Text Decoder to convert CTM reasoning into natural language.

The ThoughtLogger provides:
1. Session management for organizing data collection
2. Efficient storage format (JSONL with base64 tensors)
3. Corpus statistics and quality metrics
4. Data loading utilities for training

Usage:
    from core.thought_logger import ThoughtLogger

    # Start logging session
    logger = ThoughtLogger(log_dir="data/thought_corpus")
    logger.start_session()

    # Log thought-response pairs
    logger.log(
        thought_vector=ctm_output.thought_vector,
        llm_response="The solution involves...",
        task="Explain the algorithm",
        metadata={"certainty": 0.87}
    )

    # Get statistics
    stats = logger.get_corpus_stats()
    print(f"Total pairs: {stats['total_pairs']}")

    # Load corpus for training
    corpus = ThoughtLogger.load_corpus("data/thought_corpus")
"""

import json
import base64
import gzip
import torch
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any, Union, Iterator
from dataclasses import dataclass, asdict
import hashlib
import threading


@dataclass
class ThoughtLogEntry:
    """
    A single thought-response pair entry.

    Attributes:
        thought_vector_b64: Base64-encoded numpy array of thought vector
        response: The LLM/target response text
        task: The original task/query
        certainty: CTM certainty score at end of reasoning
        reasoning_steps: Number of reasoning iterations
        timestamp: ISO timestamp when logged
        session_id: Session identifier
        metadata: Additional metadata dict
    """
    thought_vector_b64: str
    response: str
    task: str
    certainty: float
    reasoning_steps: int
    timestamp: str
    session_id: str
    metadata: Optional[Dict[str, Any]] = None


class ThoughtLogger:
    """
    Logger for collecting CTM thought vectors paired with LLM responses.

    Features:
    - Session-based organization
    - JSONL format for streaming writes
    - Optional gzip compression
    - Thread-safe logging
    - Quality filters (min certainty, response length)

    Parameters:
        log_dir: Directory for log files
        compress: Whether to gzip compress log files
        min_certainty: Minimum certainty to log (quality filter)
        min_response_length: Minimum response length to log
    """

    def __init__(
        self,
        log_dir: str = "data/thought_corpus",
        compress: bool = False,
        min_certainty: float = 0.0,
        min_response_length: int = 10
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.compress = compress
        self.min_certainty = min_certainty
        self.min_response_length = min_response_length

        self.session_id: Optional[str] = None
        self.session_file: Optional[Path] = None
        self.session_count: int = 0

        self._lock = threading.Lock()
        self._file_handle = None

    def start_session(self, session_name: Optional[str] = None) -> str:
        """
        Start a new logging session.

        Args:
            session_name: Optional custom session name

        Returns:
            session_id: Unique session identifier
        """
        with self._lock:
            # Close previous session if open
            self._close_file()

            # Generate session ID
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if session_name:
                self.session_id = f"{session_name}_{timestamp}"
            else:
                self.session_id = f"session_{timestamp}"

            # Create session file
            ext = ".jsonl.gz" if self.compress else ".jsonl"
            self.session_file = self.log_dir / f"{self.session_id}{ext}"
            self.session_count = 0

            # Open file
            if self.compress:
                self._file_handle = gzip.open(self.session_file, 'wt', encoding='utf-8')
            else:
                self._file_handle = open(self.session_file, 'w', encoding='utf-8')

            print(f"[ThoughtLogger] Started session: {self.session_id}")
            print(f"[ThoughtLogger] Log file: {self.session_file}")

            return self.session_id

    def _close_file(self):
        """Close current file handle if open."""
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None

    def log(
        self,
        thought_vector: torch.Tensor,
        llm_response: str,
        task: str,
        certainty: Optional[float] = None,
        reasoning_steps: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log a thought-response pair.

        Args:
            thought_vector: (batch, thought_dim) or (thought_dim,) tensor
            llm_response: The LLM response text
            task: The original task/query
            certainty: CTM certainty (if not provided, extracted from metadata)
            reasoning_steps: Number of reasoning steps
            metadata: Additional metadata

        Returns:
            bool: True if logged, False if filtered out
        """
        # Validate session
        if self.session_id is None:
            raise RuntimeError("No active session. Call start_session() first.")

        # Extract certainty from metadata if not provided
        if certainty is None:
            certainty = metadata.get('certainty', 0.0) if metadata else 0.0

        # Quality filters
        if certainty < self.min_certainty:
            return False
        if len(llm_response.strip()) < self.min_response_length:
            return False

        # Convert tensor to base64
        if thought_vector.dim() > 1:
            thought_vector = thought_vector[0]  # Take first batch item
        thought_np = thought_vector.detach().cpu().numpy().astype(np.float32)
        thought_b64 = base64.b64encode(thought_np.tobytes()).decode('ascii')

        # Create entry
        entry = ThoughtLogEntry(
            thought_vector_b64=thought_b64,
            response=llm_response,
            task=task,
            certainty=certainty,
            reasoning_steps=reasoning_steps or 0,
            timestamp=datetime.now().isoformat(),
            session_id=self.session_id,
            metadata=metadata
        )

        # Write to file
        with self._lock:
            if self._file_handle is None:
                raise RuntimeError("Session file not open.")

            self._file_handle.write(json.dumps(asdict(entry)) + '\n')
            self._file_handle.flush()
            self.session_count += 1

        return True

    def end_session(self) -> Dict[str, Any]:
        """
        End current session and return summary.

        Returns:
            dict with session statistics
        """
        with self._lock:
            if self.session_id is None:
                return {}

            summary = {
                'session_id': self.session_id,
                'entries_logged': self.session_count,
                'log_file': str(self.session_file)
            }

            self._close_file()
            print(f"[ThoughtLogger] Ended session: {self.session_id}")
            print(f"[ThoughtLogger] Entries logged: {self.session_count}")

            self.session_id = None
            self.session_file = None
            self.session_count = 0

            return summary

    def get_corpus_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the entire corpus.

        Returns:
            dict with corpus statistics
        """
        total_entries = 0
        total_chars = 0
        certainties = []
        sessions = []

        for file in self.log_dir.iterdir():
            if file.suffix == '.jsonl' or file.name.endswith('.jsonl.gz'):
                sessions.append(file.stem.replace('.jsonl', ''))
                entries = list(self._read_file(file))
                total_entries += len(entries)

                for entry in entries:
                    total_chars += len(entry.get('response', ''))
                    cert = entry.get('certainty', 0)
                    if cert > 0:
                        certainties.append(cert)

        return {
            'total_pairs': total_entries,
            'num_sessions': len(sessions),
            'total_response_chars': total_chars,
            'avg_response_length': total_chars / max(total_entries, 1),
            'avg_certainty': np.mean(certainties) if certainties else 0.0,
            'min_certainty': min(certainties) if certainties else 0.0,
            'max_certainty': max(certainties) if certainties else 0.0,
            'log_dir': str(self.log_dir)
        }

    def _read_file(self, filepath: Path) -> Iterator[Dict]:
        """Read entries from a log file."""
        open_fn = gzip.open if filepath.name.endswith('.gz') else open
        with open_fn(filepath, 'rt', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    @staticmethod
    def decode_thought_vector(b64_string: str, thought_dim: int = 2048) -> torch.Tensor:
        """
        Decode base64 thought vector back to tensor.

        Args:
            b64_string: Base64 encoded string
            thought_dim: Expected dimension

        Returns:
            torch.Tensor of shape (thought_dim,)
        """
        data = base64.b64decode(b64_string)
        arr = np.frombuffer(data, dtype=np.float32)
        return torch.from_numpy(arr.copy())

    @classmethod
    def load_corpus(
        cls,
        log_dir: str,
        min_certainty: float = 0.0,
        max_entries: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Load entire corpus from log directory.

        Args:
            log_dir: Path to log directory
            min_certainty: Filter by minimum certainty
            max_entries: Maximum entries to load

        Returns:
            List of dicts with decoded thought vectors
        """
        log_path = Path(log_dir)
        if not log_path.exists():
            return []

        corpus = []
        for file in log_path.iterdir():
            if file.suffix == '.jsonl' or file.name.endswith('.jsonl.gz'):
                open_fn = gzip.open if file.name.endswith('.gz') else open
                with open_fn(file, 'rt', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        entry = json.loads(line)
                        if entry.get('certainty', 0) < min_certainty:
                            continue

                        # Decode thought vector
                        entry['thought_vector'] = cls.decode_thought_vector(
                            entry['thought_vector_b64']
                        )
                        del entry['thought_vector_b64']

                        corpus.append(entry)

                        if max_entries and len(corpus) >= max_entries:
                            return corpus

        return corpus

    def __enter__(self):
        """Context manager entry."""
        if self.session_id is None:
            self.start_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.end_session()
        return False


class ThoughtCorpusDataset(torch.utils.data.Dataset):
    """
    PyTorch Dataset for thought-response pairs.

    Used for training the ThoughtDecoder.
    """

    def __init__(
        self,
        corpus: List[Dict[str, Any]],
        tokenizer=None,
        max_length: int = 256
    ):
        self.corpus = corpus
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.corpus)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        entry = self.corpus[idx]

        item = {
            'thought_vector': entry['thought_vector'],
            'certainty': torch.tensor(entry.get('certainty', 0.0)),
        }

        # Tokenize response if tokenizer provided
        if self.tokenizer is not None:
            tokens = self.tokenizer(
                entry['response'],
                max_length=self.max_length,
                truncation=True,
                padding='max_length',
                return_tensors='pt'
            )
            item['input_ids'] = tokens['input_ids'].squeeze(0)
            item['attention_mask'] = tokens['attention_mask'].squeeze(0)
        else:
            item['response'] = entry['response']

        return item


if __name__ == "__main__":
    # Test the ThoughtLogger
    print("=" * 60)
    print("Testing ThoughtLogger")
    print("=" * 60)

    import tempfile
    import shutil

    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    log_dir = Path(temp_dir) / "test_corpus"

    try:
        # Test basic logging
        print("\n" + "-" * 40)
        print("Basic logging test:")
        print("-" * 40)

        logger = ThoughtLogger(log_dir=str(log_dir))
        session_id = logger.start_session("test_session")
        print(f"Session ID: {session_id}")

        # Log some entries
        for i in range(10):
            thought = torch.randn(2048)
            response = f"This is response number {i}. " * 5
            task = f"Task {i}: Explain something"
            certainty = 0.5 + i * 0.05

            logged = logger.log(
                thought_vector=thought,
                llm_response=response,
                task=task,
                certainty=certainty,
                reasoning_steps=15 + i,
                metadata={'index': i}
            )
            print(f"  Entry {i}: logged={logged}, certainty={certainty:.2f}")

        summary = logger.end_session()
        print(f"\nSession summary: {summary}")

        # Test corpus stats
        print("\n" + "-" * 40)
        print("Corpus statistics:")
        print("-" * 40)

        stats = logger.get_corpus_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")

        # Test loading corpus
        print("\n" + "-" * 40)
        print("Loading corpus:")
        print("-" * 40)

        corpus = ThoughtLogger.load_corpus(str(log_dir))
        print(f"Loaded {len(corpus)} entries")

        if corpus:
            entry = corpus[0]
            print(f"  First entry keys: {list(entry.keys())}")
            print(f"  thought_vector shape: {entry['thought_vector'].shape}")
            print(f"  response preview: {entry['response'][:50]}...")

        # Test context manager
        print("\n" + "-" * 40)
        print("Context manager test:")
        print("-" * 40)

        with ThoughtLogger(log_dir=str(log_dir)) as logger:
            logger.log(
                thought_vector=torch.randn(2048),
                llm_response="Context manager test response " * 3,
                task="Test task",
                certainty=0.9
            )
            print("  Logged entry in context manager")

        # Test dataset
        print("\n" + "-" * 40)
        print("Dataset test:")
        print("-" * 40)

        dataset = ThoughtCorpusDataset(corpus)
        print(f"Dataset length: {len(dataset)}")

        sample = dataset[0]
        print(f"Sample keys: {list(sample.keys())}")
        print(f"Thought vector shape: {sample['thought_vector'].shape}")

        # Test quality filter
        print("\n" + "-" * 40)
        print("Quality filter test:")
        print("-" * 40)

        filtered_logger = ThoughtLogger(
            log_dir=str(log_dir),
            min_certainty=0.7,
            min_response_length=50
        )
        filtered_logger.start_session("filtered_test")

        logged_count = 0
        for i in range(10):
            logged = filtered_logger.log(
                thought_vector=torch.randn(2048),
                llm_response="Short" if i < 5 else "This is a longer response " * 5,
                task=f"Task {i}",
                certainty=0.3 + i * 0.1
            )
            if logged:
                logged_count += 1

        filtered_logger.end_session()
        print(f"  Logged {logged_count}/10 entries (filtered by quality)")

        print("\n" + "=" * 60)
        print("ThoughtLogger tests PASSED!")
        print("=" * 60)

    finally:
        # Cleanup
        shutil.rmtree(temp_dir)
