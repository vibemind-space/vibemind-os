"""MCP Bridge Router - Connects Automation_ui with Moire MCP Tools

This router exposes the MCP Handoff Tools as REST API endpoints,
allowing the Visual Node Workflow system to use MCP automation.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import sys
import os

# Add MCP Tools path
MCP_TOOLS_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "..", "mcp_tools", "MoireTracker_v2", "python"
)
if os.path.exists(MCP_TOOLS_PATH):
    sys.path.insert(0, MCP_TOOLS_PATH)

router = APIRouter()

# Request Models
class ClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"

class TypeRequest(BaseModel):
    text: str
    interval: float = 0.0

class ShellRequest(BaseModel):
    command: str
    timeout: int = 30
    shell: str = "auto"

class FindElementRequest(BaseModel):
    text: Optional[str] = None
    element_type: Optional[str] = None
    near_text: Optional[str] = None

class ScrollRequest(BaseModel):
    direction: str = "down"
    amount: int = 3
    x: Optional[int] = None
    y: Optional[int] = None

class DocScanRequest(BaseModel):
    max_pages: int = 20
    scroll_amount: int = 800
    detect_structure: bool = True

class DocEditRequest(BaseModel):
    document_id: str
    page: int
    section_index: int
    new_text: str
    operation: str = "replace"


# Lazy import MCP handlers
_mcp_handlers = None

def get_mcp_handlers():
    """Lazy load MCP handlers to avoid import errors on startup"""
    global _mcp_handlers
    if _mcp_handlers is None:
        try:
            from mcp_server_handoff import (
                handle_click, handle_type, handle_shell,
                handle_find_element, handle_scroll, handle_scroll_to,
                handle_doc_scan, handle_doc_edit, handle_doc_apply,
                handle_doc_export, handle_read_screen
            )
            _mcp_handlers = {
                "click": handle_click,
                "type": handle_type,
                "shell": handle_shell,
                "find_element": handle_find_element,
                "scroll": handle_scroll,
                "scroll_to": handle_scroll_to,
                "doc_scan": handle_doc_scan,
                "doc_edit": handle_doc_edit,
                "doc_apply": handle_doc_apply,
                "doc_export": handle_doc_export,
                "read_screen": handle_read_screen,
            }
        except ImportError as e:
            _mcp_handlers = {"error": str(e)}
    return _mcp_handlers


# ============= Desktop Automation Endpoints =============

@router.post("/click")
async def mcp_click(req: ClickRequest):
    """Execute a click action using MCP Handoff"""
    handlers = get_mcp_handlers()
    if "error" in handlers:
        raise HTTPException(status_code=503, detail=f"MCP not available: {handlers['error']}")

    result = await handlers["click"](req.x, req.y, req.button)
    return result


@router.post("/type")
async def mcp_type(req: TypeRequest):
    """Type text using MCP Handoff"""
    handlers = get_mcp_handlers()
    if "error" in handlers:
        raise HTTPException(status_code=503, detail=f"MCP not available: {handlers['error']}")

    result = await handlers["type"](req.text)
    return result


@router.post("/shell")
async def mcp_shell(req: ShellRequest):
    """Execute shell command using MCP Handoff"""
    handlers = get_mcp_handlers()
    if "error" in handlers:
        raise HTTPException(status_code=503, detail=f"MCP not available: {handlers['error']}")

    result = await handlers["shell"](req.command, timeout=req.timeout, shell=req.shell)
    return result


@router.post("/find-element")
async def mcp_find_element(req: FindElementRequest):
    """Find UI element by text and/or type"""
    handlers = get_mcp_handlers()
    if "error" in handlers:
        raise HTTPException(status_code=503, detail=f"MCP not available: {handlers['error']}")

    result = await handlers["find_element"](
        text=req.text,
        element_type=req.element_type,
        near_text=req.near_text
    )
    return result


@router.post("/scroll")
async def mcp_scroll(req: ScrollRequest):
    """Scroll the mouse wheel"""
    handlers = get_mcp_handlers()
    if "error" in handlers:
        raise HTTPException(status_code=503, detail=f"MCP not available: {handlers['error']}")

    result = await handlers["scroll"](
        direction=req.direction,
        amount=req.amount,
        x=req.x,
        y=req.y
    )
    return result


@router.post("/scroll-to")
async def mcp_scroll_to(target: str, element_type: Optional[str] = None, then_click: bool = False):
    """Scroll until target element is found"""
    handlers = get_mcp_handlers()
    if "error" in handlers:
        raise HTTPException(status_code=503, detail=f"MCP not available: {handlers['error']}")

    result = await handlers["scroll_to"](
        target=target,
        element_type=element_type,
        then_click=then_click
    )
    return result


@router.get("/read-screen")
async def mcp_read_screen():
    """Capture screenshot and read text from screen"""
    handlers = get_mcp_handlers()
    if "error" in handlers:
        raise HTTPException(status_code=503, detail=f"MCP not available: {handlers['error']}")

    result = await handlers["read_screen"]()
    return result


# ============= Document Scanner Endpoints =============

@router.post("/doc/scan")
async def mcp_doc_scan(req: DocScanRequest):
    """Scan document and extract structured text"""
    handlers = get_mcp_handlers()
    if "error" in handlers:
        raise HTTPException(status_code=503, detail=f"MCP not available: {handlers['error']}")

    result = await handlers["doc_scan"](
        max_pages=req.max_pages,
        scroll_amount=req.scroll_amount,
        detect_structure=req.detect_structure
    )
    return result


@router.post("/doc/edit")
async def mcp_doc_edit(req: DocEditRequest):
    """Edit document section virtually"""
    handlers = get_mcp_handlers()
    if "error" in handlers:
        raise HTTPException(status_code=503, detail=f"MCP not available: {handlers['error']}")

    result = await handlers["doc_edit"](
        document_id=req.document_id,
        page=req.page,
        section_index=req.section_index,
        new_text=req.new_text,
        operation=req.operation
    )
    return result


@router.post("/doc/apply/{document_id}")
async def mcp_doc_apply(document_id: str, dry_run: bool = False):
    """Apply virtual edits to real document"""
    handlers = get_mcp_handlers()
    if "error" in handlers:
        raise HTTPException(status_code=503, detail=f"MCP not available: {handlers['error']}")

    result = await handlers["doc_apply"](document_id=document_id, dry_run=dry_run)
    return result


@router.get("/doc/export/{document_id}")
async def mcp_doc_export(document_id: str, format: str = "json"):
    """Export document structure"""
    handlers = get_mcp_handlers()
    if "error" in handlers:
        raise HTTPException(status_code=503, detail=f"MCP not available: {handlers['error']}")

    result = await handlers["doc_export"](document_id=document_id, format=format)
    return result


# ============= Health Check =============

@router.get("/health")
async def mcp_health():
    """Check MCP Bridge health status"""
    handlers = get_mcp_handlers()

    if "error" in handlers:
        return {
            "status": "degraded",
            "mcp_available": False,
            "error": handlers["error"],
            "mcp_path": MCP_TOOLS_PATH
        }

    return {
        "status": "healthy",
        "mcp_available": True,
        "available_handlers": list(handlers.keys()),
        "mcp_path": MCP_TOOLS_PATH
    }
