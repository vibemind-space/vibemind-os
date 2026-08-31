"""
Supabase Visual Memory Connector

Reads screen/desktop data from Supabase desktop_icons table.
This data comes from an external screen capture system.

Features:
- Query latest screen state
- Query screen history by time window
- Extract visual context for memory formation
- Filter by window/application
"""

import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from supabase import create_client, Client


class SupabaseVisualConnector:
    """
    Connector to read visual/screen data from Supabase.

    The desktop_icons table is populated by an external screen capture system
    that runs every 5 minutes and records:
    - Window titles
    - OCR text from screen
    - File paths
    - Application states
    - Desktop icon positions
    """

    def __init__(
        self,
        project_url: str = None,
        secret_key: str = None,
        table_name: str = "desktop_icons"
    ):
        """
        Initialize Supabase client.

        Args:
            project_url: Supabase project URL (or from env var SUPABASE_URL)
            secret_key: Service role key (or from env var SUPABASE_SECRET_KEY)
            table_name: Table name (default: desktop_icons)
        """
        self.project_url = project_url or os.getenv('SUPABASE_URL')
        self.secret_key = secret_key or os.getenv('SUPABASE_SECRET_KEY')
        self.table_name = table_name

        if not self.project_url or not self.secret_key:
            raise ValueError(
                "Supabase credentials not provided. "
                "Set SUPABASE_URL and SUPABASE_SECRET_KEY environment variables "
                "or pass them to the constructor."
            )

        # Create Supabase client
        self.client: Client = create_client(self.project_url, self.secret_key)

    def get_latest_screen_state(self, limit: int = 10) -> List[Dict]:
        """
        Get the most recent screen state.

        Args:
            limit: Number of recent items to return

        Returns:
            List of screen data entries, most recent first
        """
        try:
            response = (
                self.client.table(self.table_name)
                .select("*")
                .order("captured_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data
        except Exception as e:
            print(f"[SupabaseVisualConnector] Error fetching latest state: {e}")
            return []

    def get_screen_by_time_window(
        self,
        minutes_ago: int = 5,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get screen data from the last N minutes.

        Args:
            minutes_ago: How many minutes back to query
            limit: Maximum number of items

        Returns:
            List of screen data entries
        """
        try:
            # Calculate timestamp
            time_threshold = datetime.now() - timedelta(minutes=minutes_ago)
            timestamp_ms = int(time_threshold.timestamp() * 1000)

            response = (
                self.client.table(self.table_name)
                .select("*")
                .gte("captured_at", timestamp_ms)
                .order("captured_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data
        except Exception as e:
            print(f"[SupabaseVisualConnector] Error fetching by time window: {e}")
            return []

    def get_screen_by_window_title(
        self,
        window_title: str,
        limit: int = 20
    ) -> List[Dict]:
        """
        Get screen data filtered by window title.

        Args:
            window_title: Window title to search for (case-insensitive contains)
            limit: Maximum number of items

        Returns:
            List of screen data entries
        """
        try:
            response = (
                self.client.table(self.table_name)
                .select("*")
                .ilike("window_title", f"%{window_title}%")
                .order("captured_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data
        except Exception as e:
            print(f"[SupabaseVisualConnector] Error fetching by window: {e}")
            return []

    def search_ocr_text(
        self,
        search_term: str,
        limit: int = 20
    ) -> List[Dict]:
        """
        Search screen data by OCR text content.

        Args:
            search_term: Term to search for in OCR text
            limit: Maximum number of items

        Returns:
            List of screen data entries containing the search term
        """
        try:
            response = (
                self.client.table(self.table_name)
                .select("*")
                .ilike("ocr_text", f"%{search_term}%")
                .order("captured_at", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data
        except Exception as e:
            print(f"[SupabaseVisualConnector] Error searching OCR text: {e}")
            return []

    def get_visual_context_summary(self, minutes_ago: int = 5) -> Dict:
        """
        Get a summary of recent visual context.

        Args:
            minutes_ago: How many minutes back to analyze

        Returns:
            Dict with:
                - active_windows: List of window titles
                - visible_files: List of file paths
                - ocr_highlights: Key OCR text fragments
                - applications: List of active applications
                - timestamp_range: (oldest, newest)
        """
        screen_data = self.get_screen_by_time_window(minutes_ago, limit=50)

        if not screen_data:
            return {
                'active_windows': [],
                'visible_files': [],
                'ocr_highlights': [],
                'applications': [],
                'timestamp_range': (None, None)
            }

        # Extract unique values
        windows = set()
        files = set()
        ocr_fragments = []
        apps = set()

        for item in screen_data:
            if item.get('window_title'):
                windows.add(item['window_title'])
            if item.get('file_path'):
                files.add(item['file_path'])
            if item.get('ocr_text'):
                # Take first 100 chars of OCR text as highlight
                text = item['ocr_text'][:100]
                if text and text not in ocr_fragments:
                    ocr_fragments.append(text)

            # Extract application from window_class or window_title
            if item.get('window_class'):
                apps.add(item['window_class'])

        # Get timestamp range
        timestamps = [item.get('captured_at') for item in screen_data if item.get('captured_at')]
        timestamp_range = (min(timestamps), max(timestamps)) if timestamps else (None, None)

        return {
            'active_windows': sorted(list(windows)),
            'visible_files': sorted(list(files)),
            'ocr_highlights': ocr_fragments[:5],  # Top 5 highlights
            'applications': sorted(list(apps)),
            'timestamp_range': timestamp_range
        }

    def format_for_llm(self, visual_context: Dict) -> str:
        """
        Format visual context as a string for LLM consumption.

        Args:
            visual_context: Dict from get_visual_context_summary()

        Returns:
            Human-readable string describing visual context
        """
        parts = ["Current Visual Context:"]

        if visual_context['active_windows']:
            parts.append(f"Active Windows: {', '.join(visual_context['active_windows'][:3])}")

        if visual_context['visible_files']:
            parts.append(f"Visible Files: {', '.join(visual_context['visible_files'][:3])}")

        if visual_context['applications']:
            parts.append(f"Applications: {', '.join(visual_context['applications'][:3])}")

        if visual_context['ocr_highlights']:
            parts.append("Screen Text Visible:")
            for i, text in enumerate(visual_context['ocr_highlights'][:2], 1):
                parts.append(f"  {i}. {text}...")

        return "\n".join(parts)

    def test_connection(self) -> bool:
        """
        Test Supabase connection.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.client.table(self.table_name).select("id").limit(1).execute()
            print(f"[SupabaseVisualConnector] Connection test successful!")
            print(f"  Project: {self.project_url}")
            print(f"  Table: {self.table_name}")
            return True
        except Exception as e:
            print(f"[SupabaseVisualConnector] Connection test failed: {e}")
            return False


# Example usage
if __name__ == "__main__":
    # Test with provided credentials
    PROJECT_URL = "https://YOUR-PROJECT.supabase.co"
    SECRET_KEY = "your-secret-key"

    connector = SupabaseVisualConnector(
        project_url=PROJECT_URL,
        secret_key=SECRET_KEY
    )

    # Test connection
    if connector.test_connection():
        print("\n" + "="*70)
        print("VISUAL CONTEXT TEST")
        print("="*70)

        # Get latest screen state
        latest = connector.get_latest_screen_state(limit=5)
        print(f"\nLatest {len(latest)} screen entries:")
        for item in latest:
            print(f"  - {item.get('window_title', 'Unknown')} at {item.get('captured_at')}")

        # Get visual context summary
        context = connector.get_visual_context_summary(minutes_ago=30)
        print(f"\nVisual Context (last 30 min):")
        print(f"  Windows: {len(context['active_windows'])}")
        print(f"  Files: {len(context['visible_files'])}")
        print(f"  Apps: {len(context['applications'])}")

        # Format for LLM
        print("\n" + "="*70)
        print("LLM-READY FORMAT:")
        print("="*70)
        print(connector.format_for_llm(context))
