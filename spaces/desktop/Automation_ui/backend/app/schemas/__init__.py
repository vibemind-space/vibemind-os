"""Schemas package for TRAE Backend

Provides Pydantic schemas for API request/response validation.
"""

from .node_schemas import (ClickActionConfig, DelayConfig, HttpRequestConfig,
                           IfConditionConfig, LiveDesktopConfig, LoggerConfig,
                           ManualTriggerConfig, N8nWebhookConfig,
                           NodeConfigSchema, OcrRegionConfig,
                           ScreenshotActionConfig, TypeTextActionConfig,
                           WebhookTriggerConfig, WebsocketConfigSchema)

__all__ = [
    "NodeConfigSchema",
    "ClickActionConfig",
    "TypeTextActionConfig",
    "HttpRequestConfig",
    "WebhookTriggerConfig",
    "N8nWebhookConfig",
    "OcrRegionConfig",
    "IfConditionConfig",
    "DelayConfig",
    "LoggerConfig",
    "ScreenshotActionConfig",
    "ManualTriggerConfig",
    "WebsocketConfigSchema",
    "LiveDesktopConfig",
]
