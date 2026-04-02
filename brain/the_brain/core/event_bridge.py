"""
EventBridge: Automatic Token Extraction from Event Streams

Extracts tokens from conversation events and feeds them to the TokenFrequencyAdapter
in real-time as events flow through the pipeline.

This bridges the gap between raw event text and oscillator modulation,
enabling automatic Token -> Frequency conversion without manual token processing.

Usage:
    from core.event_bridge import EventBridge, TokenExtractionConfig

    bridge = EventBridge(token_adapter)
    bridge.process_conversation_event({'text': 'Deploy the nginx container'})
    # Automatically extracts and processes: ['deploy', 'the', 'nginx', 'container']
"""

import re
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque


@dataclass
class TokenExtractionConfig:
    """Configuration for token extraction"""
    min_token_length: int = 2
    max_tokens_per_event: int = 50
    skip_punctuation_only: bool = True
    lowercase: bool = True
    preserve_case_for_entities: bool = True  # Keep case for likely entity names
    extract_numbers: bool = False  # Include numeric tokens
    split_camel_case: bool = True  # "deployContainer" -> ["deploy", "container"]


@dataclass
class TokenExtractionResult:
    """Result of token extraction from an event"""
    tokens: List[str]
    source_text: str
    event_type: str
    extraction_time_ms: float
    filtered_count: int  # Tokens filtered out


class EventBridge:
    """
    Bridge between event stream and TokenFrequencyAdapter

    Automatically extracts tokens from conversation events and feeds them
    to the oscillator system for frequency modulation.
    """

    def __init__(
        self,
        token_adapter: Any,  # TokenFrequencyAdapter
        config: Optional[TokenExtractionConfig] = None,
        on_token_extracted: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize EventBridge

        Args:
            token_adapter: TokenFrequencyAdapter instance to feed tokens to
            config: Token extraction configuration
            on_token_extracted: Optional callback for each extracted token
        """
        self.token_adapter = token_adapter
        self.config = config or TokenExtractionConfig()
        self.on_token_extracted = on_token_extracted

        # Statistics
        self.total_events_processed = 0
        self.total_tokens_extracted = 0
        self.total_tokens_filtered = 0

        # History (for debugging/visualization)
        self.extraction_history: deque = deque(maxlen=100)
        self.recent_tokens: deque = deque(maxlen=50)

        # Entity detection patterns (keep original case)
        self._entity_patterns = [
            r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b',  # CamelCase
            r'\b[A-Z]{2,}\b',  # ACRONYMS
            r'\b[a-z]+[-_][a-z]+\b',  # kebab-case, snake_case
        ]

        print("[EventBridge] Initialized")
        print(f"  - Min token length: {self.config.min_token_length}")
        print(f"  - Max tokens per event: {self.config.max_tokens_per_event}")

    def process_conversation_event(self, event: Dict[str, Any]) -> TokenExtractionResult:
        """
        Extract and process tokens from a conversation event

        Args:
            event: Event dictionary with 'text', 'content', or 'message' field

        Returns:
            TokenExtractionResult with extracted tokens and metadata
        """
        start_time = datetime.now()

        # Extract text from event
        text = self._extract_text(event)
        event_type = event.get('type', 'conversation')

        if not text:
            return TokenExtractionResult(
                tokens=[],
                source_text="",
                event_type=event_type,
                extraction_time_ms=0,
                filtered_count=0
            )

        # Tokenize
        raw_tokens = self._tokenize(text)
        filtered_count = len(raw_tokens)

        # Filter tokens
        tokens = self._filter_tokens(raw_tokens)
        filtered_count -= len(tokens)

        # Limit tokens
        tokens = tokens[:self.config.max_tokens_per_event]

        # Process each token through the adapter
        for token in tokens:
            self.token_adapter.process_token_sync(token)
            self.recent_tokens.append(token)

            if self.on_token_extracted:
                self.on_token_extracted(token)

        # Update statistics
        self.total_events_processed += 1
        self.total_tokens_extracted += len(tokens)
        self.total_tokens_filtered += filtered_count

        # Calculate extraction time
        extraction_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Create result
        result = TokenExtractionResult(
            tokens=tokens,
            source_text=text[:100] + "..." if len(text) > 100 else text,
            event_type=event_type,
            extraction_time_ms=extraction_time_ms,
            filtered_count=filtered_count
        )

        # Record history
        self.extraction_history.append(result)

        return result

    def process_text(self, text: str) -> List[str]:
        """
        Process raw text directly (convenience method)

        Args:
            text: Raw text to tokenize and process

        Returns:
            List of extracted tokens
        """
        return self.process_conversation_event({'text': text}).tokens

    def _extract_text(self, event: Dict[str, Any]) -> str:
        """Extract text content from event"""
        # Try different fields
        text = event.get('text') or event.get('content') or event.get('message') or ''

        # Handle nested structures
        if isinstance(text, dict):
            text = text.get('text', '') or text.get('content', '')

        return str(text).strip()

    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize text into words

        Uses regex to split on word boundaries while handling:
        - CamelCase splitting (optional)
        - Hyphenated words
        - Numbers (optional)
        """
        # Basic word tokenization
        tokens = re.findall(r'\b\w+\b', text)

        # Split CamelCase if enabled
        if self.config.split_camel_case:
            expanded = []
            for token in tokens:
                # Split on CamelCase boundaries
                parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+', token)
                if parts:
                    expanded.extend(parts)
                else:
                    expanded.append(token)
            tokens = expanded

        return tokens

    def _filter_tokens(self, tokens: List[str]) -> List[str]:
        """Filter tokens based on configuration"""
        filtered = []

        for token in tokens:
            # Check minimum length
            if len(token) < self.config.min_token_length:
                continue

            # Skip pure numbers unless enabled
            if not self.config.extract_numbers and token.isdigit():
                continue

            # Skip punctuation-only tokens
            if self.config.skip_punctuation_only and not any(c.isalnum() for c in token):
                continue

            # Apply lowercase (but preserve entities if configured)
            if self.config.lowercase:
                if self.config.preserve_case_for_entities and self._is_entity(token):
                    filtered.append(token)
                else:
                    filtered.append(token.lower())
            else:
                filtered.append(token)

        return filtered

    def _is_entity(self, token: str) -> bool:
        """Check if token is likely an entity (keep original case)"""
        # All caps (acronym)
        if token.isupper() and len(token) >= 2:
            return True

        # CamelCase
        if re.match(r'^[A-Z][a-z]+(?:[A-Z][a-z]+)+$', token):
            return True

        return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get bridge statistics"""
        return {
            'events_processed': self.total_events_processed,
            'tokens_extracted': self.total_tokens_extracted,
            'tokens_filtered': self.total_tokens_filtered,
            'avg_tokens_per_event': self.total_tokens_extracted / max(1, self.total_events_processed),
            'filter_rate': self.total_tokens_filtered / max(1, self.total_tokens_extracted + self.total_tokens_filtered),
            'recent_tokens': list(self.recent_tokens)[-10:],
            'history_size': len(self.extraction_history)
        }

    def get_recent_extractions(self, n: int = 10) -> List[TokenExtractionResult]:
        """Get n most recent extraction results"""
        return list(self.extraction_history)[-n:]

    def reset_statistics(self) -> None:
        """Reset all statistics"""
        self.total_events_processed = 0
        self.total_tokens_extracted = 0
        self.total_tokens_filtered = 0
        self.extraction_history.clear()
        self.recent_tokens.clear()
        self._tool_outcomes = {'success': 0, 'failure': 0}

    def record_tool_outcome(self, tool_name: str, success: bool) -> None:
        """
        Record a tool execution outcome.

        Args:
            tool_name: Name of the executed tool
            success: Whether the execution was successful
        """
        if not hasattr(self, '_tool_outcomes'):
            self._tool_outcomes = {'success': 0, 'failure': 0}

        if success:
            self._tool_outcomes['success'] += 1
        else:
            self._tool_outcomes['failure'] += 1

    def get_tool_outcomes(self) -> Dict[str, int]:
        """Get tool outcome statistics"""
        if not hasattr(self, '_tool_outcomes'):
            self._tool_outcomes = {'success': 0, 'failure': 0}
        return self._tool_outcomes.copy()


# Quick test
if __name__ == "__main__":
    print("=" * 60)
    print("  EVENT BRIDGE TEST")
    print("=" * 60)

    # Mock token adapter
    class MockTokenAdapter:
        def __init__(self):
            self.processed = []

        def process_token_sync(self, token: str):
            self.processed.append(token)
            print(f"    Processed: {token}")

    adapter = MockTokenAdapter()
    bridge = EventBridge(adapter)

    # Test events
    test_events = [
        {'text': 'Deploy the nginx container on port 8080'},
        {'content': 'But NOT on the production server'},
        {'message': 'Then check the deploymentStatus and verify'},
    ]

    print("\nProcessing events:")
    print("-" * 40)

    for event in test_events:
        text = event.get('text') or event.get('content') or event.get('message')
        print(f"\nInput: \"{text}\"")
        result = bridge.process_conversation_event(event)
        print(f"  Tokens: {result.tokens}")
        print(f"  Time: {result.extraction_time_ms:.2f}ms")

    print("\n" + "-" * 40)
    print("Statistics:")
    stats = bridge.get_statistics()
    print(f"  Events processed: {stats['events_processed']}")
    print(f"  Tokens extracted: {stats['tokens_extracted']}")
    print(f"  Avg tokens/event: {stats['avg_tokens_per_event']:.1f}")

    print("\n" + "=" * 60)
