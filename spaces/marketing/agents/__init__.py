"""Marketing-Ops backend agents."""

from .marketing_agent import (
    MARKETING_CONSUMER_GROUP,
    MarketingBackendAgent,
    get_marketing_agent,
)

__all__ = [
    "MARKETING_CONSUMER_GROUP",
    "MarketingBackendAgent",
    "get_marketing_agent",
]
