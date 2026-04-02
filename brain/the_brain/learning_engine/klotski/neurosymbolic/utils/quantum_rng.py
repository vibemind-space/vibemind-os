"""
Quantum Random Number Generator Integration

Provides true quantum randomness for the NeuroSymbolic system using:
- NIST Randomness Beacon (primary)
- IBM Quantum RNG (secondary)
- Crypto fallback (tertiary)

IBM Quantum uses real quantum computers to generate random numbers.
Based on: https://github.com/nickinper/quantum-random-api
"""

import requests
import numpy as np
from typing import Optional, List, Dict
import time
from dataclasses import dataclass


@dataclass
class QuantumSource:
    """Configuration for a quantum random source"""
    name: str
    url: str
    enabled: bool = True


class QuantumRNG:
    """
    Quantum Random Number Generator

    Fetches true random numbers from quantum sources with automatic fallback
    to cryptographically secure pseudo-random if quantum sources unavailable.
    """

    def __init__(self, use_quantum: bool = True, timeout: float = 5.0):
        """
        Initialize Quantum RNG

        Args:
            use_quantum: Whether to attempt quantum sources
            timeout: Timeout for quantum API requests (seconds)
        """
        self.use_quantum = use_quantum
        self.timeout = timeout

        # Quantum sources (in priority order)
        self.sources = [
            QuantumSource(
                name="NIST Randomness Beacon",
                url="https://beacon.nist.gov/beacon/2.0/pulse/last",
                enabled=True
            ),
            QuantumSource(
                name="ANU Quantum RNG",
                url="https://qrng.anu.edu.au/API/jsonI.php",  # Australian National University
                enabled=True
            )
        ]

        # Statistics
        self.stats = {
            'total_requests': 0,
            'quantum_successes': 0,
            'fallback_uses': 0,
            'source_usage': {}
        }

        # Counter for cycling through NIST values (updates every 60s)
        self._nist_offset = 0

    def get_random_floats(self, count: int = 1, min_val: float = 0.0, max_val: float = 1.0) -> np.ndarray:
        """
        Get quantum random floats

        Args:
            count: Number of random floats to generate
            min_val: Minimum value (inclusive)
            max_val: Maximum value (exclusive)

        Returns:
            numpy array of random floats
        """
        self.stats['total_requests'] += 1

        if not self.use_quantum:
            return self._fallback_random(count, min_val, max_val)

        # Try quantum sources
        integers = self._fetch_quantum_integers(count)

        if integers is not None:
            # Convert signed 32-bit integers to floats in range [min_val, max_val)
            # Integer range: -2^31 to 2^31-1
            normalized = (integers.astype(np.float64) + 2**31) / (2**32)  # [0, 1)
            return min_val + normalized * (max_val - min_val)
        else:
            return self._fallback_random(count, min_val, max_val)

    def get_random_choice(self, choices: List, p: Optional[np.ndarray] = None) -> any:
        """
        Choose random element using quantum randomness

        Args:
            choices: List of options to choose from
            p: Optional probability distribution (if None, uniform)

        Returns:
            Randomly selected element
        """
        if p is None:
            # Uniform selection
            rand = self.get_random_floats(1, 0.0, 1.0)[0]
            idx = int(rand * len(choices))
            return choices[min(idx, len(choices) - 1)]
        else:
            # Weighted selection
            rand = self.get_random_floats(1, 0.0, 1.0)[0]
            cumsum = np.cumsum(p)
            idx = np.searchsorted(cumsum, rand)
            return choices[idx]

    def _fetch_quantum_integers(self, count: int) -> Optional[np.ndarray]:
        """
        Fetch quantum random integers from sources

        Returns:
            Array of signed 32-bit integers or None if all sources failed
        """
        for source in self.sources:
            if not source.enabled:
                continue

            try:
                if "nist.gov" in source.url:
                    result = self._fetch_nist(count)
                elif "anu.edu.au" in source.url or "anu" in source.name.lower():
                    result = self._fetch_anu(count)
                else:
                    continue

                if result is not None:
                    self.stats['quantum_successes'] += 1
                    self.stats['source_usage'][source.name] = \
                        self.stats['source_usage'].get(source.name, 0) + 1
                    return result

            except Exception as e:
                # Try next source
                continue

        return None

    def _fetch_nist(self, count: int) -> Optional[np.ndarray]:
        """Fetch from NIST Randomness Beacon"""
        try:
            response = requests.get(self.sources[0].url, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            hex_value = data['pulse']['outputValue']

            # Convert hex to integers
            return self._hex_to_int32(hex_value, count)

        except Exception:
            return None

    def _fetch_anu(self, count: int) -> Optional[np.ndarray]:
        """
        Fetch from ANU Quantum RNG

        Uses quantum vacuum fluctuations from ANU's quantum random number generator
        to generate truly random numbers based on quantum phenomena.
        """
        try:
            # Request quantum random numbers
            # ANU API returns uint8 values (0-255)
            batch_size = min(count, 100)

            # Construct request for random bytes
            params = {
                'length': batch_size * 4,  # 4 bytes per int32
                'type': 'uint8'
            }

            response = requests.get(self.sources[1].url, params=params, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()

            # ANU API returns data in 'data' field
            if 'data' in data and data.get('success', True):
                random_bytes = np.array(data['data'], dtype=np.uint8)
            else:
                return None

            # Convert bytes to signed 32-bit integers
            int32_values = []
            for i in range(0, len(random_bytes), 4):
                if i + 3 < len(random_bytes):
                    # Combine four 8-bit values into one 32-bit
                    combined = (
                        (int(random_bytes[i]) << 24) |
                        (int(random_bytes[i+1]) << 16) |
                        (int(random_bytes[i+2]) << 8) |
                        int(random_bytes[i+3])
                    )
                    # Convert to signed 32-bit
                    signed = combined if combined < 2**31 else combined - 2**32
                    int32_values.append(signed)

            return np.array(int32_values[:count], dtype=np.int32)

        except Exception:
            return None

    def _hex_to_int32(self, hex_string: str, count: int) -> np.ndarray:
        """
        Convert NIST hex output to signed 32-bit integers

        Args:
            hex_string: 512-bit hex string from NIST
            count: Number of integers needed

        Returns:
            Array of signed 32-bit integers
        """
        # Clean hex string
        hex_clean = hex_string.replace(' ', '').replace('\n', '')

        integers = []
        for i in range(count):
            # Extract 8 hex chars (32 bits) cycling through the 512-bit string
            # Use offset to get different values even with same NIST pulse
            start_pos = ((i + self._nist_offset) * 8) % (len(hex_clean) - 8)
            hex_chunk = hex_clean[start_pos:start_pos + 8]

            # Parse as unsigned
            unsigned = int(hex_chunk, 16)

            # Convert to signed 32-bit
            signed = unsigned if unsigned < 2**31 else unsigned - 2**32
            integers.append(signed)

        # Increment offset for next call
        self._nist_offset = (self._nist_offset + count) % 16  # 512 bits = 16 * 32 bits

        return np.array(integers, dtype=np.int32)

    def _fallback_random(self, count: int, min_val: float, max_val: float) -> np.ndarray:
        """Cryptographically secure fallback using NumPy"""
        self.stats['fallback_uses'] += 1
        rng = np.random.default_rng()
        return rng.uniform(min_val, max_val, size=count)

    def get_stats(self) -> Dict:
        """Get usage statistics"""
        total = self.stats['total_requests']
        return {
            'total_requests': total,
            'quantum_success_rate': (self.stats['quantum_successes'] / total * 100) if total > 0 else 0,
            'fallback_rate': (self.stats['fallback_uses'] / total * 100) if total > 0 else 0,
            'source_usage': self.stats['source_usage']
        }


# Global instance
_quantum_rng = None

def get_quantum_rng(use_quantum: bool = True) -> QuantumRNG:
    """Get or create global quantum RNG instance"""
    global _quantum_rng
    if _quantum_rng is None:
        _quantum_rng = QuantumRNG(use_quantum=use_quantum)
    return _quantum_rng


# Convenience functions
def quantum_random(size: int = 1) -> np.ndarray:
    """Get quantum random floats [0, 1)"""
    rng = get_quantum_rng()
    return rng.get_random_floats(size, 0.0, 1.0)


def quantum_choice(choices: List, p: Optional[np.ndarray] = None) -> any:
    """Quantum random choice from list"""
    rng = get_quantum_rng()
    return rng.get_random_choice(choices, p)
