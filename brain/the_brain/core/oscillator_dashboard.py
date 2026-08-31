"""
Oscillator Dashboard: Real-time Terminal Visualization

Displays oscillator state, synchrony, regime, and token processing stats
using ANSI colors for a rich terminal experience.

Usage:
    from core.layer4_temporal_router import Layer4TemporalRouter
    from core.oscillator_dashboard import OscillatorDashboard

    router = Layer4TemporalRouter()
    router.process_tokens("Deploy the container".split())

    dashboard = OscillatorDashboard(router)
    dashboard.display()  # Single display

    # Or run live loop
    dashboard.live_loop(interval=0.5)
"""

import os
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


class Colors:
    """ANSI color codes for terminal output"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'

    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'

    # Background colors
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'

    @staticmethod
    def disable():
        """Disable colors (for non-ANSI terminals)"""
        Colors.RESET = ''
        Colors.BOLD = ''
        Colors.DIM = ''
        Colors.UNDERLINE = ''
        Colors.BLACK = ''
        Colors.RED = ''
        Colors.GREEN = ''
        Colors.YELLOW = ''
        Colors.BLUE = ''
        Colors.MAGENTA = ''
        Colors.CYAN = ''
        Colors.WHITE = ''
        Colors.BG_RED = ''
        Colors.BG_GREEN = ''
        Colors.BG_YELLOW = ''
        Colors.BG_BLUE = ''


@dataclass
class DashboardConfig:
    """Dashboard configuration"""
    width: int = 60
    bar_width: int = 30
    show_phase: bool = True
    show_synchrony: bool = True
    show_token_stats: bool = True
    show_recent_tokens: bool = True
    recent_tokens_count: int = 5
    use_unicode_bars: bool = True


class OscillatorDashboard:
    """
    Terminal-based oscillator visualization

    Provides real-time display of:
    - A/B/C oscillator amplitudes (colored bars)
    - Dominant channel indicator
    - Phase information
    - Synchrony/coherence metrics
    - Token processing statistics
    - Recent tokens processed
    """

    def __init__(
        self,
        router: Any,  # Layer4TemporalRouter
        config: Optional[DashboardConfig] = None
    ):
        """
        Initialize dashboard

        Args:
            router: Layer4TemporalRouter instance
            config: Dashboard configuration
        """
        self.router = router
        self.config = config or DashboardConfig()
        self.refresh_count = 0
        self.start_time = datetime.now()

        # Check if terminal supports colors
        if not self._supports_ansi():
            Colors.disable()

    def _supports_ansi(self) -> bool:
        """Check if terminal supports ANSI escape codes"""
        # Windows Terminal, ConEmu, etc. support ANSI
        if os.name == 'nt':
            return os.environ.get('TERM_PROGRAM') or os.environ.get('WT_SESSION')
        return True

    def render(self) -> str:
        """
        Render current oscillator state to string

        Returns:
            Formatted string for terminal display
        """
        try:
            osc = self.router.get_oscillator_state()
            sync = self.router.get_synchrony_vector()
            dominant = self.router.get_dominant_channel()
            stats = self.router.get_statistics()
        except Exception as e:
            return f"{Colors.RED}Error getting state: {e}{Colors.RESET}"

        lines = []
        w = self.config.width

        # Header
        lines.append(f"{Colors.BOLD}{'=' * w}{Colors.RESET}")
        lines.append(self._center_text("OSCILLATOR DASHBOARD", w, Colors.CYAN))
        lines.append(f"{Colors.DIM}[{datetime.now().strftime('%H:%M:%S')}] Refresh #{self.refresh_count}{Colors.RESET}")
        lines.append(f"{'=' * w}")

        # Oscillator Channels
        lines.append(f"\n{Colors.BOLD}Oscillator Channels:{Colors.RESET}")
        lines.append(self._render_bar("A (Advance)", osc.A.amplitude, Colors.GREEN))
        lines.append(self._render_bar("B (Explore)", osc.B.amplitude, Colors.BLUE))
        lines.append(self._render_bar("C (Correct)", osc.C.amplitude, Colors.RED))

        # Phase information
        if self.config.show_phase:
            lines.append(f"\n{Colors.BOLD}Phase (radians):{Colors.RESET}")
            lines.append(f"  A: {osc.A.phase:6.3f}  B: {osc.B.phase:6.3f}  C: {osc.C.phase:6.3f}")

        # Dominant channel with highlight
        dominant_color = {
            'advance': Colors.GREEN,
            'explore': Colors.BLUE,
            'correct': Colors.RED
        }.get(dominant.value, Colors.WHITE)

        lines.append(f"\n{Colors.BOLD}Dominant Channel:{Colors.RESET} {dominant_color}{Colors.BOLD}{dominant.value.upper()}{Colors.RESET}")

        # Synchrony
        if self.config.show_synchrony:
            lines.append(f"\n{Colors.BOLD}Synchrony:{Colors.RESET}")
            coherence = sync.mean_coherence
            coherence_color = Colors.GREEN if coherence > 0.7 else (Colors.YELLOW if coherence > 0.4 else Colors.RED)
            lines.append(f"  Mean Coherence: {coherence_color}{coherence:.3f}{Colors.RESET}")

            # Phase differences if available
            if hasattr(sync, 'phase_diffs'):
                lines.append(f"  Phase Diffs: AB={sync.phase_diffs[0]:.2f} AC={sync.phase_diffs[1]:.2f} BC={sync.phase_diffs[2]:.2f}")

        # Token processing stats
        if self.config.show_token_stats:
            token_stats = stats.get('token_adapter', {})
            lines.append(f"\n{Colors.BOLD}Token Processing:{Colors.RESET}")
            lines.append(f"  Tokens Processed: {token_stats.get('tokens_processed', 0)}")

            hit_rate = token_stats.get('local_hit_rate', 0)
            hit_color = Colors.GREEN if hit_rate > 0.8 else (Colors.YELLOW if hit_rate > 0.5 else Colors.RED)
            lines.append(f"  Local Hit Rate:   {hit_color}{hit_rate:.1%}{Colors.RESET}")

            cache_rate = token_stats.get('cache_hit_rate', 0)
            lines.append(f"  Cache Hit Rate:   {cache_rate:.1%}")

        # Recent tokens
        if self.config.show_recent_tokens:
            recent = self._get_recent_tokens(stats)
            if recent:
                lines.append(f"\n{Colors.BOLD}Recent Tokens:{Colors.RESET}")
                lines.append(f"  {Colors.DIM}{', '.join(recent[-self.config.recent_tokens_count:])}{Colors.RESET}")

        # EventBridge stats if available
        event_bridge_stats = stats.get('event_bridge', {})
        if event_bridge_stats:
            lines.append(f"\n{Colors.BOLD}EventBridge:{Colors.RESET}")
            lines.append(f"  Events: {event_bridge_stats.get('events_processed', 0)}")
            lines.append(f"  Avg tokens/event: {event_bridge_stats.get('avg_tokens_per_event', 0):.1f}")

        # Footer
        lines.append(f"\n{'=' * w}")
        uptime = (datetime.now() - self.start_time).total_seconds()
        lines.append(f"{Colors.DIM}Uptime: {uptime:.0f}s | Press Ctrl+C to exit{Colors.RESET}")

        return '\n'.join(lines)

    def _supports_unicode(self) -> bool:
        """Check if terminal supports Unicode"""
        try:
            # Test if we can encode Unicode
            '\u2588'.encode(sys.stdout.encoding or 'utf-8')
            return True
        except (UnicodeEncodeError, LookupError, AttributeError):
            return False

    def _render_bar(self, label: str, value: float, color: str) -> str:
        """Render a colored progress bar"""
        bw = self.config.bar_width
        value = max(0, min(1, value))  # Clamp to [0, 1]
        filled = int(value * bw)
        empty = bw - filled

        # Use ASCII for Windows compatibility
        if self.config.use_unicode_bars and self._supports_unicode():
            bar = '\u2588' * filled + '\u2591' * empty  # Full block + light shade
        else:
            bar = '#' * filled + '-' * empty

        return f"  {label:12} [{color}{bar}{Colors.RESET}] {value:.3f}"

    def _center_text(self, text: str, width: int, color: str = '') -> str:
        """Center text with optional color"""
        padding = (width - len(text)) // 2
        return f"{' ' * padding}{color}{Colors.BOLD}{text}{Colors.RESET}"

    def _get_recent_tokens(self, stats: Dict) -> List[str]:
        """Get recent tokens from stats"""
        # Try event_bridge first
        event_bridge = stats.get('event_bridge', {})
        if 'recent_tokens' in event_bridge:
            return event_bridge['recent_tokens']

        # Try token_adapter
        token_adapter = stats.get('token_adapter', {})
        if 'recent_tokens' in token_adapter:
            return token_adapter['recent_tokens']

        return []

    def display(self) -> None:
        """Clear screen and display dashboard"""
        # Clear screen (cross-platform)
        if os.name == 'nt':
            os.system('cls')
        else:
            os.system('clear')

        print(self.render())
        self.refresh_count += 1

    def render_compact(self) -> str:
        """Render a compact single-line status"""
        try:
            osc = self.router.get_oscillator_state()
            dominant = self.router.get_dominant_channel()
            sync = self.router.get_synchrony_vector()
        except Exception:
            return f"{Colors.RED}[Error]{Colors.RESET}"

        dom_color = {
            'advance': Colors.GREEN,
            'explore': Colors.BLUE,
            'correct': Colors.RED
        }.get(dominant.value, Colors.WHITE)

        return (
            f"[OSC] A:{osc.A.amplitude:.2f} B:{osc.B.amplitude:.2f} C:{osc.C.amplitude:.2f} "
            f"| {dom_color}{dominant.value.upper()}{Colors.RESET} "
            f"| Coh:{sync.mean_coherence:.2f}"
        )

    def live_loop(self, interval: float = 0.5) -> None:
        """
        Run live dashboard update loop

        Args:
            interval: Refresh interval in seconds
        """
        print(f"{Colors.CYAN}Starting live dashboard (Ctrl+C to stop)...{Colors.RESET}")
        time.sleep(1)

        try:
            while True:
                self.display()
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Dashboard stopped.{Colors.RESET}")

    def live_compact_loop(self, interval: float = 0.2) -> None:
        """
        Run compact status line loop (doesn't clear screen)

        Args:
            interval: Refresh interval in seconds
        """
        try:
            while True:
                # Move cursor to beginning of line and clear
                sys.stdout.write('\r' + ' ' * 80 + '\r')
                sys.stdout.write(self.render_compact())
                sys.stdout.flush()
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Stopped.{Colors.RESET}")


# Demo function
def demo_dashboard():
    """Demo the dashboard with mock data"""
    print("=" * 60)
    print("  OSCILLATOR DASHBOARD DEMO")
    print("=" * 60)

    # Try to import real router
    try:
        import sys
        sys.path.insert(0, '.')
        from core.layer4_temporal_router import Layer4TemporalRouter

        router = Layer4TemporalRouter(
            strict_security=True,
            timing_threshold=0.5,
            enable_deep_reasoning=False
        )

        # Process some tokens
        tokens = "Deploy the nginx container but not on port 8080".split()
        router.process_tokens(tokens)

        # Create and display dashboard
        dashboard = OscillatorDashboard(router)
        dashboard.display()

        print(f"\n{Colors.GREEN}Dashboard displayed successfully!{Colors.RESET}")
        print(f"\nCompact view: {dashboard.render_compact()}")

    except ImportError as e:
        print(f"{Colors.RED}Could not import router: {e}{Colors.RESET}")
        print("Run from the_brain directory.")


if __name__ == "__main__":
    demo_dashboard()
