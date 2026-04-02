"""
Vision API routes for Claude Vision screenshot analysis.

Provides endpoints for analyzing UI screenshots with Claude Vision,
used for the Review Gate feature to process user feedback.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog
import os

from src.llm_config import get_model

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/vision", tags=["vision"])


class VisionAnalyzeRequest(BaseModel):
    """Request body for vision analysis."""
    image: str  # Base64 encoded image (data:image/png;base64,...)
    prompt: str
    max_tokens: int = 1024


class VisionAnalyzeResponse(BaseModel):
    """Response from vision analysis."""
    analysis: str
    success: bool = True
    error: Optional[str] = None


@router.post("/analyze", response_model=VisionAnalyzeResponse)
async def analyze_screenshot(request: VisionAnalyzeRequest):
    """
    Analyze a screenshot with Claude Vision.

    Takes a base64-encoded image and a prompt, returns Claude's analysis.
    Used for the Review Gate feature to analyze VNC screenshots.
    """
    try:
        from anthropic import Anthropic

        client = Anthropic()

        # Extract base64 data (remove data:image/png;base64, prefix if present)
        image_data = request.image
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]

        # Determine media type
        media_type = "image/png"
        if request.image.startswith("data:image/jpeg"):
            media_type = "image/jpeg"
        elif request.image.startswith("data:image/webp"):
            media_type = "image/webp"

        response = client.messages.create(
            model=get_model("primary"),
            max_tokens=request.max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        }
                    },
                    {
                        "type": "text",
                        "text": request.prompt
                    }
                ]
            }]
        )

        analysis = response.content[0].text if response.content else ""

        logger.info(
            "vision_analysis_complete",
            prompt_length=len(request.prompt),
            analysis_length=len(analysis),
        )

        return VisionAnalyzeResponse(analysis=analysis, success=True)

    except ImportError:
        logger.error("anthropic_not_installed")
        raise HTTPException(
            status_code=503,
            detail="Anthropic SDK not installed"
        )
    except Exception as e:
        logger.error("vision_analysis_failed", error=str(e))
        return VisionAnalyzeResponse(
            analysis="",
            success=False,
            error=str(e)
        )


@router.post("/analyze-ui-feedback")
async def analyze_ui_feedback(request: VisionAnalyzeRequest):
    """
    Analyze a screenshot specifically for UI feedback.

    Uses a specialized prompt for identifying UI issues and suggesting fixes.
    """
    # Wrap the user's feedback in a structured analysis prompt
    structured_prompt = f"""User Feedback: "{request.prompt}"

Analyze the screenshot and identify:
1. The UI element the user is referring to
2. Visible problems or issues
3. Specific code changes needed to address the feedback

Be concise and actionable. Focus on what needs to change.
If you can identify specific CSS properties, component names, or file locations, mention them.
"""

    try:
        from anthropic import Anthropic

        client = Anthropic()

        # Extract base64 data
        image_data = request.image
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]

        # Determine media type
        media_type = "image/png"
        if request.image.startswith("data:image/jpeg"):
            media_type = "image/jpeg"

        response = client.messages.create(
            model=get_model("primary"),
            max_tokens=request.max_tokens,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        }
                    },
                    {
                        "type": "text",
                        "text": structured_prompt
                    }
                ]
            }]
        )

        analysis = response.content[0].text if response.content else ""

        logger.info(
            "ui_feedback_analysis_complete",
            user_feedback_length=len(request.prompt),
            analysis_length=len(analysis),
        )

        return VisionAnalyzeResponse(analysis=analysis, success=True)

    except Exception as e:
        logger.error("ui_feedback_analysis_failed", error=str(e))
        return VisionAnalyzeResponse(
            analysis="",
            success=False,
            error=str(e)
        )
