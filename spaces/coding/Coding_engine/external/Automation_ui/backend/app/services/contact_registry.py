"""
Contact Registry for Clawdbot Integration

Resolves fuzzy names/aliases to exact contact information.
Allows users to say "send to Peter" instead of dictating phone numbers.

Usage:
    registry = ContactRegistry()
    contact = registry.resolve("peter")  # or "Pete", "pm"
    phone = contact.get("whatsapp")  # "+491234567890"
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)


class ContactRegistry:
    """Registry for contacts, variables, and message templates."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize ContactRegistry.

        Args:
            config_path: Path to clawdbot_contacts.json
        """
        if config_path is None:
            # Default path relative to backend
            base_dir = Path(__file__).parent.parent.parent.parent
            config_path = base_dir / "config" / "clawdbot_contacts.json"

        self.config_path = Path(config_path)
        self._contacts: Dict[str, Dict] = {}
        self._variables: Dict[str, str] = {}
        self._templates: Dict[str, str] = {}
        self._alias_map: Dict[str, str] = {}  # alias -> contact_key

        self._load_config()

    def _load_config(self):
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            logger.warning(f"Contact config not found: {self.config_path}")
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            self._contacts = config.get("contacts", {})
            self._variables = config.get("variables", {})
            self._templates = config.get("templates", {})

            # Build alias map for fast lookup
            self._build_alias_map()

            logger.info(f"Loaded {len(self._contacts)} contacts, "
                       f"{len(self._variables)} variables, "
                       f"{len(self._templates)} templates")

        except Exception as e:
            logger.error(f"Failed to load contact config: {e}")

    def _build_alias_map(self):
        """Build reverse lookup map from aliases to contact keys."""
        self._alias_map.clear()

        for key, contact in self._contacts.items():
            # Map the main key
            self._alias_map[key.lower()] = key

            # Map the name
            if "name" in contact:
                self._alias_map[contact["name"].lower()] = key

            # Map all aliases
            for alias in contact.get("aliases", []):
                self._alias_map[alias.lower()] = key

    def reload(self):
        """Reload configuration from file."""
        self._load_config()

    # =========================================================================
    # CONTACT RESOLUTION
    # =========================================================================

    def resolve(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a name/alias to contact information.

        Args:
            query: Name, alias, or fuzzy match (e.g., "Peter", "pete", "pm")

        Returns:
            Contact dict with name, whatsapp, telegram, email, etc.
            None if not found.
        """
        query_lower = query.lower().strip()

        # 1. Exact match in alias map
        if query_lower in self._alias_map:
            key = self._alias_map[query_lower]
            return self._contacts.get(key)

        # 2. Fuzzy match
        best_match = self._fuzzy_match(query_lower)
        if best_match:
            return self._contacts.get(best_match)

        return None

    def resolve_recipient(self, query: str, channel: str) -> Optional[str]:
        """
        Resolve query to recipient ID for specific channel.

        Args:
            query: Name or alias
            channel: whatsapp, telegram, discord, email, etc.

        Returns:
            Recipient ID (phone number, chat ID, email) or None
        """
        contact = self.resolve(query)
        if contact:
            return contact.get(channel)
        return None

    def _fuzzy_match(self, query: str, threshold: float = 0.6) -> Optional[str]:
        """
        Find best fuzzy match for query.

        Args:
            query: Search string
            threshold: Minimum similarity score (0-1)

        Returns:
            Contact key if match found, None otherwise
        """
        best_score = 0
        best_key = None

        for alias, key in self._alias_map.items():
            score = SequenceMatcher(None, query, alias).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_key = key

        if best_key:
            logger.debug(f"Fuzzy matched '{query}' -> '{best_key}' (score: {best_score:.2f})")

        return best_key

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search contacts by name/alias with fuzzy matching.

        Returns list of matches with scores.
        """
        results = []
        query_lower = query.lower()

        for key, contact in self._contacts.items():
            # Check name
            name = contact.get("name", key)
            score = SequenceMatcher(None, query_lower, name.lower()).ratio()

            # Check aliases for better score
            for alias in contact.get("aliases", []):
                alias_score = SequenceMatcher(None, query_lower, alias.lower()).ratio()
                score = max(score, alias_score)

            if score > 0.3:
                results.append({
                    "key": key,
                    "contact": contact,
                    "score": score
                })

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    # =========================================================================
    # VARIABLES
    # =========================================================================

    def get_variable(self, name: str) -> Optional[str]:
        """Get a predefined variable value."""
        return self._variables.get(name)

    def resolve_variables(self, text: str) -> str:
        """
        Replace {variable} placeholders in text.

        Args:
            text: Text with {variable} placeholders

        Returns:
            Text with variables replaced
        """
        def replace_var(match):
            var_name = match.group(1)
            return self._variables.get(var_name, match.group(0))

        return re.sub(r'\{(\w+)\}', replace_var, text)

    # =========================================================================
    # TEMPLATES
    # =========================================================================

    def get_template(self, name: str) -> Optional[str]:
        """Get a message template by name."""
        return self._templates.get(name)

    def render_template(self, name: str, **kwargs) -> Optional[str]:
        """
        Render a template with provided values.

        Args:
            name: Template name
            **kwargs: Values to substitute (overrides variables)

        Returns:
            Rendered template or None if not found
        """
        template = self._templates.get(name)
        if not template:
            return None

        # Merge variables with provided kwargs (kwargs take precedence)
        context = {**self._variables, **kwargs}

        # Replace placeholders
        def replace_placeholder(match):
            key = match.group(1)
            return str(context.get(key, match.group(0)))

        return re.sub(r'\{(\w+)\}', replace_placeholder, template)

    # =========================================================================
    # MANAGEMENT
    # =========================================================================

    def add_contact(self, key: str, contact: Dict[str, Any]) -> bool:
        """Add or update a contact."""
        self._contacts[key] = contact
        self._build_alias_map()
        return self._save_config()

    def remove_contact(self, key: str) -> bool:
        """Remove a contact."""
        if key in self._contacts:
            del self._contacts[key]
            self._build_alias_map()
            return self._save_config()
        return False

    def set_variable(self, name: str, value: str) -> bool:
        """Set a variable."""
        self._variables[name] = value
        return self._save_config()

    def _save_config(self) -> bool:
        """Save current config to file."""
        try:
            config = {
                "contacts": self._contacts,
                "variables": self._variables,
                "templates": self._templates
            }

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    def list_contacts(self) -> Dict[str, Dict]:
        """Get all contacts."""
        return self._contacts.copy()

    def list_variables(self) -> Dict[str, str]:
        """Get all variables."""
        return self._variables.copy()

    def list_templates(self) -> Dict[str, str]:
        """Get all templates."""
        return self._templates.copy()


# Global singleton
_registry: Optional[ContactRegistry] = None


def get_contact_registry() -> ContactRegistry:
    """Get the global ContactRegistry instance."""
    global _registry
    if _registry is None:
        _registry = ContactRegistry()
    return _registry
