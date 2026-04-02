"""
Video Backend Agent

Listens to the events:tasks:video Redis stream and executes
video.* event types via vibevideo + vibevideo-deepfake tools.

Follows the BaseBackendAgent pattern from base_agent.py.
"""

import logging
from typing import Dict, Callable, Optional

from swarm.backend_agents.base_agent import BaseBackendAgent

logger = logging.getLogger(__name__)


class VideoBackendAgent(BaseBackendAgent):
    """
    Backend agent for the Video Production Space.

    Handles video.* event types:
    - video.status:         Check installed tools and submodules
    - video.team_status:    Team pipeline status
    - video.team_run:       Run team video pipeline step
    - video.vision:         Generate Her-style vision video (Sora AI)
    - video.demo_analyze:   Analyze screenrecording for demo
    - video.demo_build:     Build demo video from config
    - video.lipsync:        Run lip sync (MuseTalk)
    - video.lipsync_analyze: Quality analysis on lip sync
    - video.voice_clone:    Extract reference audio (Chatterbox, local)
    - video.voice_tts:      Generate TTS voiceover
    """

    EVENT_TO_TOOL: Dict[str, str] = {
        "video.status":          "video_status",
        "video.team_status":     "team_pipeline_status",
        "video.team_run":        "team_run_step",
        "video.vision":          "vision_generate",
        "video.demo_analyze":    "demo_analyze",
        "video.demo_build":      "demo_build",
        "video.lipsync":         "lipsync_run",
        "video.lipsync_analyze": "lipsync_analyze",
        "video.voice_clone":     "voice_clone",
        "video.voice_tts":       "voice_tts",
        "video.publish":         "publish_videos_to_rowboat",
    }

    PARAM_MAPPING: Dict[str, Dict[str, str]] = {
        "video.team_run": {
            "schritt": "step",
            "stufe": "step",
        },
        "video.lipsync": {
            "name": "person",
            "person": "person",
        },
        "video.voice_tts": {
            "name": "person",
            "person": "person",
        },
        "video.demo_analyze": {
            "datei": "input_file",
            "file": "input_file",
            "video": "input_file",
            "dauer": "target_duration",
        },
        "video.demo_build": {
            "config": "config_path",
            "datei": "config_path",
        },
    }

    @property
    def name(self) -> str:
        return "VideoAgent"

    @property
    def stream(self) -> str:
        return "events:tasks:video"

    def _load_tools(self) -> Dict[str, Callable]:
        """Load video production tools."""
        tools = {}
        try:
            from spaces.video.tools.video_tools import (
                video_status,
                team_pipeline_status,
                team_run_step,
                vision_generate,
                demo_analyze,
                demo_build,
                lipsync_run,
                lipsync_analyze,
                voice_clone,
                voice_tts,
                publish_videos_to_rowboat,
            )

            tools.update({
                "video_status": video_status,
                "team_pipeline_status": team_pipeline_status,
                "team_run_step": team_run_step,
                "vision_generate": vision_generate,
                "demo_analyze": demo_analyze,
                "demo_build": demo_build,
                "lipsync_run": lipsync_run,
                "lipsync_analyze": lipsync_analyze,
                "voice_clone": voice_clone,
                "voice_tts": voice_tts,
                "publish_videos_to_rowboat": publish_videos_to_rowboat,
            })
            logger.info(f"{self.name}: Loaded {len(tools)} tools")

        except ImportError as e:
            logger.warning(f"{self.name}: Could not load tools: {e}")

        return tools

    def _get_tool_name(self, event_type: str) -> Optional[str]:
        """Map event type to tool function name."""
        return self.EVENT_TO_TOOL.get(event_type)


# Singleton
_video_agent: Optional[VideoBackendAgent] = None


def get_video_agent() -> VideoBackendAgent:
    """Get or create the VideoBackendAgent singleton."""
    global _video_agent
    if _video_agent is None:
        _video_agent = VideoBackendAgent()
    return _video_agent


__all__ = ["VideoBackendAgent", "get_video_agent"]
