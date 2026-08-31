"""
Terminal Monitor for Evolutionary Training

Provides rich terminal UI with live metrics, progress bars, and agent status.
Uses ANSI escape codes for colorful real-time display.

Usage:
    from core.terminal_monitor import TerminalMonitor

    monitor = TerminalMonitor()
    monitor.start()

    # Update during training
    monitor.update_episode(generation=1, episode=45, connected=True, quality=0.85)
    monitor.update_agents(beginning=(1,1), mid=(4,5), end=(6,6))

    monitor.stop()
"""

import sys
import time
import threading
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
from collections import deque


class Colors:
    """ANSI color codes"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # Bright foreground colors
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'

    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'


class TerminalMonitor:
    """
    Terminal Monitor for Evolutionary Training

    Displays:
    - Generation progress
    - Episode metrics (connections, quality, success rate)
    - Agent positions and paths
    - Heart/Brain system status
    - Reproduction alerts
    - Timeline visualization
    """

    def __init__(self, max_generations=10, episodes_per_gen=200):
        """
        Initialize terminal monitor

        Args:
            max_generations: Maximum generations
            episodes_per_gen: Episodes per generation
        """
        self.max_generations = max_generations
        self.episodes_per_gen = episodes_per_gen

        # Training state
        self.current_generation = 0
        self.current_episode = 0
        self.connections = 0
        self.best_quality = 0.0
        self.avg_quality = 0.0
        self.success_rate = 0.0
        self.difficulty = 1.0
        self.conv_penalty = -0.1
        self.total_reward = 0

        # Agent state
        self.agent_positions = {
            'beginning': (1, 1),
            'mid': (3, 4),
            'end': (6, 6)
        }
        self.agent_paths = {
            'beginning': [],
            'mid': [],
            'end': []
        }

        # Heart/Brain metrics
        self.heart_confidence = 0.70
        self.brain_confidence = 0.30
        self.heart_brain_agreement = False

        # Reproduction tracking
        self.reproductions = []
        self.extinct_generations = []

        # Performance metrics
        self.start_time = None
        self.episode_times = deque(maxlen=20)  # Last 20 episode times

        # Thread control
        self.running = False
        self.update_thread = None
        self.lock = threading.Lock()

    def start(self):
        """Start terminal monitor"""
        self.running = True
        self.start_time = datetime.now()

        # Clear screen and hide cursor
        print('\033[2J\033[H\033[?25l', end='', flush=True)

        # Start update thread
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()

    def stop(self):
        """Stop terminal monitor"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=1.0)

        # Show cursor again
        print('\033[?25h', end='', flush=True)

    def update_episode(
        self,
        generation: int,
        episode: int,
        connected: bool = False,
        quality: float = 0.0,
        reward: float = 0.0,
        episode_time: float = 0.0
    ):
        """Update episode metrics"""
        with self.lock:
            self.current_generation = generation
            self.current_episode = episode

            if connected:
                self.connections += 1
                self.best_quality = max(self.best_quality, quality)

            self.total_reward += reward

            # Update success rate
            if episode > 0:
                self.success_rate = self.connections / episode

            # Update average quality
            if self.connections > 0:
                # Simplified - should track all qualities
                self.avg_quality = (self.avg_quality * (self.connections - 1) + quality) / self.connections

            # Track episode time
            if episode_time > 0:
                self.episode_times.append(episode_time)

    def update_agents(
        self,
        beginning: Optional[Tuple[int, int]] = None,
        mid: Optional[Tuple[int, int]] = None,
        end: Optional[Tuple[int, int]] = None
    ):
        """Update agent positions"""
        with self.lock:
            if beginning is not None:
                self.agent_positions['beginning'] = beginning
                self.agent_paths['beginning'].append(beginning)
            if mid is not None:
                self.agent_positions['mid'] = mid
                self.agent_paths['mid'].append(mid)
            if end is not None:
                self.agent_positions['end'] = end
                self.agent_paths['end'].append(end)

    def update_heart_brain(
        self,
        heart_conf: float,
        brain_conf: float,
        agreement: bool
    ):
        """Update heart/brain system metrics"""
        with self.lock:
            self.heart_confidence = heart_conf
            self.brain_confidence = brain_conf
            self.heart_brain_agreement = agreement

    def update_generation(
        self,
        difficulty: float,
        conv_penalty: float
    ):
        """Update generation parameters"""
        with self.lock:
            self.difficulty = difficulty
            self.conv_penalty = conv_penalty

    def record_reproduction(self, generation: int, quality: float):
        """Record successful reproduction"""
        with self.lock:
            self.reproductions.append({
                'generation': generation,
                'quality': quality,
                'timestamp': datetime.now()
            })

    def record_extinction(self, generation: int):
        """Record extinction event"""
        with self.lock:
            self.extinct_generations.append(generation)

    def reset_for_generation(self):
        """Reset metrics for new generation"""
        with self.lock:
            self.current_episode = 0
            self.connections = 0
            self.best_quality = 0.0
            self.avg_quality = 0.0
            self.success_rate = 0.0
            self.total_reward = 0
            self.agent_paths = {'beginning': [], 'mid': [], 'end': []}

    def _update_loop(self):
        """Update loop - refreshes display every 500ms"""
        while self.running:
            self._render()
            time.sleep(0.5)

    def _render(self):
        """Render complete terminal display"""
        with self.lock:
            # Move cursor to top
            print('\033[H', end='')

            # Build display
            lines = []

            # Header
            lines.append(self._render_header())
            lines.append('')

            # Main metrics (2 columns)
            lines.extend(self._render_metrics())
            lines.append('')

            # Agent status
            lines.extend(self._render_agents())
            lines.append('')

            # Heart/Brain system
            lines.extend(self._render_heart_brain())
            lines.append('')

            # Generation timeline
            lines.extend(self._render_timeline())
            lines.append('')

            # Progress bars
            lines.extend(self._render_progress())
            lines.append('')

            # Performance metrics
            lines.extend(self._render_performance())

            # Print all lines
            output = '\n'.join(lines)
            print(output, end='', flush=True)

            # Clear rest of screen
            print('\033[J', end='', flush=True)

    def _render_header(self) -> str:
        """Render header"""
        title = "EVOLUTIONARY TRAINING MONITOR"
        subtitle = "Romantic 3-Agent System - Love in the Dark"

        header = f"{Colors.BOLD}{Colors.BRIGHT_CYAN}{'=' * 80}{Colors.RESET}\n"
        header += f"{Colors.BOLD}{Colors.BRIGHT_YELLOW}{title:^80}{Colors.RESET}\n"
        header += f"{Colors.BRIGHT_MAGENTA}{subtitle:^80}{Colors.RESET}\n"
        header += f"{Colors.BOLD}{Colors.BRIGHT_CYAN}{'=' * 80}{Colors.RESET}"

        return header

    def _render_metrics(self) -> list:
        """Render main metrics (2 columns)"""
        lines = []

        # Title
        lines.append(f"{Colors.BOLD}{Colors.BRIGHT_WHITE}TRAINING METRICS{Colors.RESET}")
        lines.append(f"{Colors.DIM}{'-' * 80}{Colors.RESET}")

        # Left column: Generation info
        left_col = [
            f"{Colors.BRIGHT_GREEN}Generation:{Colors.RESET}     {self.current_generation}/{self.max_generations}",
            f"{Colors.BRIGHT_BLUE}Episode:{Colors.RESET}        {self.current_episode}/{self.episodes_per_gen}",
            f"{Colors.BRIGHT_YELLOW}Difficulty:{Colors.RESET}     {self.difficulty:.2f}x",
            f"{Colors.BRIGHT_MAGENTA}Conv Penalty:{Colors.RESET}  {self.conv_penalty}"
        ]

        # Right column: Performance info
        right_col = [
            f"{Colors.BRIGHT_GREEN}Connections:{Colors.RESET}   {self.connections}",
            f"{Colors.BRIGHT_CYAN}Best Quality:{Colors.RESET}  {self.best_quality:.1%}",
            f"{Colors.BRIGHT_YELLOW}Success Rate:{Colors.RESET} {self.success_rate:.1%}",
            f"{Colors.BRIGHT_MAGENTA}Total Reward:{Colors.RESET} {int(self.total_reward):,}"
        ]

        # Combine columns
        for i in range(max(len(left_col), len(right_col))):
            left = left_col[i] if i < len(left_col) else ""
            right = right_col[i] if i < len(right_col) else ""

            # Calculate spacing (account for ANSI codes)
            left_clean = self._strip_ansi(left)
            spacing = 40 - len(left_clean)

            lines.append(f"  {left}{' ' * spacing}{right}")

        return lines

    def _render_agents(self) -> list:
        """Render agent status"""
        lines = []

        lines.append(f"{Colors.BOLD}{Colors.BRIGHT_WHITE}AGENT STATUS{Colors.RESET}")
        lines.append(f"{Colors.DIM}{'-' * 80}{Colors.RESET}")

        # Agent info (3 columns)
        agents = [
            ('Beginning', self.agent_positions['beginning'], len(self.agent_paths['beginning']), Colors.BRIGHT_BLUE),
            ('Mid', self.agent_positions['mid'], len(self.agent_paths['mid']), Colors.BRIGHT_YELLOW),
            ('End', self.agent_positions['end'], len(self.agent_paths['end']), Colors.BRIGHT_RED)
        ]

        agent_lines = []
        for name, pos, path_len, color in agents:
            agent_lines.append(f"  {color}{name:12}{Colors.RESET} Pos: ({pos[0]},{pos[1]})  Path: {path_len}")

        lines.extend(agent_lines)

        return lines

    def _render_heart_brain(self) -> list:
        """Render heart/brain system status"""
        lines = []

        lines.append(f"{Colors.BOLD}{Colors.BRIGHT_WHITE}HEART/BRAIN SYSTEM{Colors.RESET}")
        lines.append(f"{Colors.DIM}{'-' * 80}{Colors.RESET}")

        # Heart
        heart_bar = self._create_bar(self.heart_confidence, 30, Colors.BRIGHT_RED)
        lines.append(f"  {Colors.BRIGHT_RED}Heart (Frozen):{Colors.RESET}  {heart_bar} {self.heart_confidence:.1%}")

        # Brain
        brain_bar = self._create_bar(self.brain_confidence, 30, Colors.BRIGHT_CYAN)
        lines.append(f"  {Colors.BRIGHT_CYAN}Brain (Evolving):{Colors.RESET} {brain_bar} {self.brain_confidence:.1%}")

        # Agreement
        agreement_text = "AGREEMENT" if self.heart_brain_agreement else "DISAGREEMENT"
        agreement_color = Colors.BRIGHT_GREEN if self.heart_brain_agreement else Colors.BRIGHT_YELLOW
        lines.append(f"  Status: {agreement_color}{agreement_text}{Colors.RESET}")

        return lines

    def _render_timeline(self) -> list:
        """Render generation timeline"""
        lines = []

        lines.append(f"{Colors.BOLD}{Colors.BRIGHT_WHITE}GENERATION TIMELINE{Colors.RESET}")
        lines.append(f"{Colors.DIM}{'-' * 80}{Colors.RESET}")

        # Timeline visualization
        timeline = "  "
        for i in range(self.max_generations + 1):
            if i == self.current_generation:
                # Current generation (green)
                timeline += f"{Colors.BG_GREEN}{Colors.BLACK} {i:2d} {Colors.RESET}"
            elif i in self.extinct_generations:
                # Extinct (red)
                timeline += f"{Colors.BG_RED}{Colors.WHITE} {i:2d} {Colors.RESET}"
            elif i < self.current_generation:
                # Completed (blue)
                timeline += f"{Colors.BG_BLUE}{Colors.WHITE} {i:2d} {Colors.RESET}"
            else:
                # Future (dim)
                timeline += f"{Colors.DIM} {i:2d} {Colors.RESET}"

            if i < self.max_generations:
                timeline += " "

        lines.append(timeline)

        # Legend
        legend = f"  {Colors.BG_GREEN}{Colors.BLACK} Current {Colors.RESET} "
        legend += f"{Colors.BG_BLUE}{Colors.WHITE} Complete {Colors.RESET} "
        legend += f"{Colors.BG_RED}{Colors.WHITE} Extinct {Colors.RESET} "
        legend += f"{Colors.DIM} Future {Colors.RESET}"
        lines.append(legend)

        return lines

    def _render_progress(self) -> list:
        """Render progress bars"""
        lines = []

        lines.append(f"{Colors.BOLD}{Colors.BRIGHT_WHITE}PROGRESS{Colors.RESET}")
        lines.append(f"{Colors.DIM}{'-' * 80}{Colors.RESET}")

        # Episode progress
        episode_pct = (self.current_episode / self.episodes_per_gen) if self.episodes_per_gen > 0 else 0
        episode_bar = self._create_bar(episode_pct, 50, Colors.BRIGHT_CYAN)
        lines.append(f"  Episode:  {episode_bar} {episode_pct:.1%}")

        # Reproduction progress (based on success rate)
        repro_pct = min(1.0, self.success_rate)
        repro_bar = self._create_bar(repro_pct, 50, Colors.BRIGHT_GREEN)
        repro_status = f"{Colors.BRIGHT_GREEN}ON TRACK{Colors.RESET}" if repro_pct >= 0.60 else f"{Colors.BRIGHT_YELLOW}WORKING{Colors.RESET}"
        lines.append(f"  Reproduce: {repro_bar} {repro_pct:.1%} {repro_status}")

        return lines

    def _render_performance(self) -> list:
        """Render performance metrics"""
        lines = []

        lines.append(f"{Colors.BOLD}{Colors.BRIGHT_WHITE}PERFORMANCE{Colors.RESET}")
        lines.append(f"{Colors.DIM}{'-' * 80}{Colors.RESET}")

        # Runtime
        if self.start_time:
            elapsed = datetime.now() - self.start_time
            elapsed_str = str(elapsed).split('.')[0]  # Remove microseconds
            lines.append(f"  Runtime:  {Colors.BRIGHT_CYAN}{elapsed_str}{Colors.RESET}")

        # Average episode time
        if self.episode_times:
            avg_time = sum(self.episode_times) / len(self.episode_times)
            lines.append(f"  Avg Episode Time: {Colors.BRIGHT_YELLOW}{avg_time:.2f}s{Colors.RESET}")

            # ETA for current generation
            remaining_episodes = self.episodes_per_gen - self.current_episode
            eta_seconds = remaining_episodes * avg_time
            eta = timedelta(seconds=int(eta_seconds))
            lines.append(f"  ETA (this gen):   {Colors.BRIGHT_MAGENTA}{str(eta)}{Colors.RESET}")

        # Reproductions
        if self.reproductions:
            lines.append(f"  Reproductions: {Colors.BRIGHT_GREEN}{len(self.reproductions)}{Colors.RESET}")

        return lines

    def _create_bar(self, value: float, width: int, color: str) -> str:
        """Create progress bar (Windows-compatible)"""
        filled = int(value * width)
        empty = width - filled

        # Use ASCII characters for Windows compatibility
        bar = f"{color}{'#' * filled}{Colors.RESET}"
        bar += f"{Colors.DIM}{'.' * empty}{Colors.RESET}"

        return f"[{bar}]"

    def _strip_ansi(self, text: str) -> str:
        """Strip ANSI codes from text"""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)


if __name__ == "__main__":
    # Test terminal monitor
    print("Terminal Monitor Test - 10 seconds")

    monitor = TerminalMonitor(max_generations=10, episodes_per_gen=200)
    monitor.start()

    try:
        # Simulate training
        for gen in range(3):
            monitor.reset_for_generation()
            monitor.update_generation(difficulty=1.5 ** gen, conv_penalty=-0.1 * (gen + 1))

            for ep in range(50):
                # Simulate episode
                time.sleep(0.1)

                connected = (ep % 5 == 0)
                quality = min(1.0, 0.3 + ep * 0.01 + gen * 0.1)
                reward = 10000 * (quality ** 2) if connected else -10

                monitor.update_episode(
                    generation=gen,
                    episode=ep + 1,
                    connected=connected,
                    quality=quality,
                    reward=reward,
                    episode_time=0.1
                )

                # Update agent positions
                if ep % 10 == 0:
                    monitor.update_agents(
                        beginning=(1, 1),
                        mid=(min(7, 3 + ep // 10), 4),
                        end=(6, 6)
                    )

                # Update heart/brain
                monitor.update_heart_brain(
                    heart_conf=0.70,
                    brain_conf=0.30 + ep * 0.002,
                    agreement=(ep % 3 == 0)
                )

            # Record reproduction
            if gen < 2:
                monitor.record_reproduction(gen, quality)

    finally:
        monitor.stop()
        print("\n\nTerminal Monitor Test Complete")
