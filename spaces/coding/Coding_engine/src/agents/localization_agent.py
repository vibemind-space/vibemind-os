"""
Localization Agent - Autonomous agent for i18n setup and translation management.

Manages internationalization including:
- i18n library setup (next-intl, react-i18next)
- String extraction from source code
- Translation key generation
- Locale file management

Publishes:
- I18N_SETUP_STARTED: i18n configuration initiated
- I18N_CONFIGURED: i18n successfully configured
- TRANSLATION_KEYS_EXTRACTED: Translation keys extracted from code
- TRANSLATION_NEEDED: New strings need translation
- LOCALIZATION_COMPLETE: Localization setup complete
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

from ..mind.event_bus import (
    EventBus, Event, EventType,
    i18n_setup_started_event,
    localization_complete_event,
    i18n_configured_event,
    translation_needed_event,
    translation_keys_extracted_event,
)
from ..mind.shared_state import SharedState
from ..tools.claude_code_tool import ClaudeCodeTool
from .autonomous_base import AutonomousAgent


logger = structlog.get_logger(__name__)


# i18n library detection patterns
I18N_LIBRARIES = {
    "next-intl": {
        "package": "next-intl",
        "config_file": "i18n.ts",
        "messages_dir": "messages",
    },
    "react-i18next": {
        "package": "react-i18next",
        "config_file": "i18n.ts",
        "messages_dir": "locales",
    },
    "vue-i18n": {
        "package": "vue-i18n",
        "config_file": "i18n.js",
        "messages_dir": "locales",
    },
    "svelte-i18n": {
        "package": "svelte-i18n",
        "config_file": "i18n.js",
        "messages_dir": "locales",
    },
}

# Patterns for extracting translatable strings
STRING_PATTERNS = {
    # React/Next.js patterns
    "t_function": r"(?:t|i18n\.t)\s*\(\s*['\"`]([^'\"`]+)['\"`]",
    "useTranslation": r"useTranslation\s*\(\s*['\"`]([^'\"`]*)['\"`]",
    "trans_component": r"<Trans[^>]*i18nKey=['\"`]([^'\"`]+)['\"`]",

    # next-intl patterns
    "useTranslations": r"useTranslations\s*\(\s*['\"`]([^'\"`]*)['\"`]",
    "getTranslations": r"getTranslations\s*\(\s*['\"`]([^'\"`]*)['\"`]",

    # Hardcoded strings that might need translation
    "jsx_text": r">\s*([A-Z][a-z]+(?:\s+[a-z]+)*)\s*<",
    "placeholder": r'placeholder=["\']([^"\']+)["\']',
    "aria_label": r'aria-label=["\']([^"\']+)["\']',
    "title_attr": r'title=["\']([^"\']+)["\']',
    "alt_text": r'alt=["\']([^"\']+)["\']',
}

# Common locales
COMMON_LOCALES = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
}


class LocalizationAgent(AutonomousAgent):
    """
    Autonomous agent for i18n setup and translation management.

    Triggers on:
    - CONTRACTS_GENERATED: Check if i18n is required
    - GENERATION_COMPLETE: Extract strings for translation

    Manages:
    - i18n library configuration
    - Translation key extraction
    - Locale file generation
    """

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedState,
        working_dir: str,
        claude_tool: Optional[ClaudeCodeTool] = None,
        default_locale: str = "en",
        target_locales: Optional[list[str]] = None,
        extract_strings: bool = True,
        generate_keys: bool = True,
        i18n_library: Optional[str] = None,
    ):
        """
        Initialize LocalizationAgent.

        Args:
            event_bus: EventBus for pub/sub
            shared_state: SharedState for metrics
            working_dir: Project directory
            claude_tool: Optional Claude tool for AI assistance
            default_locale: Default/fallback locale
            target_locales: List of target locales to support
            extract_strings: Whether to extract translatable strings
            generate_keys: Whether to generate translation keys
            i18n_library: Force specific i18n library
        """
        super().__init__(
            name="LocalizationAgent",
            event_bus=event_bus,
            shared_state=shared_state,
            working_dir=working_dir,
        )
        self.working_dir = Path(working_dir)
        self.claude_tool = claude_tool
        self.default_locale = default_locale
        self.target_locales = target_locales or ["en"]
        self.extract_strings = extract_strings
        self.generate_keys = generate_keys
        self.forced_library = i18n_library

        self._last_extraction: Optional[datetime] = None
        self._detected_library: Optional[str] = None
        self._extracted_keys: dict[str, list[str]] = {}  # namespace -> keys

    @property
    def subscribed_events(self) -> list[EventType]:
        """Events this agent listens for."""
        return [
            EventType.CONTRACTS_GENERATED,
            EventType.GENERATION_COMPLETE,
        ]

    async def should_act(self, events: list[Event]) -> bool:
        """
        Determine if agent should act on this event.

        Acts when:
        - Contracts generated (check if i18n needed)
        - Generation complete (extract strings)
        """
        for event in events:
            if event.type not in self.subscribed_events:
                continue

            # Rate limit: Don't extract more than once per 60 seconds
            if self._last_extraction:
                elapsed = (datetime.now() - self._last_extraction).total_seconds()
                if elapsed < 60:
                    logger.debug(
                        "localization_skipped",
                        reason="rate_limited",
                        seconds_since_last=elapsed,
                    )
                    continue

            return True

        return False

    async def act(self, events: list[Event]) -> None:
        """
        Manage localization setup.

        Steps:
        1. Detect i18n library
        2. Check/create i18n configuration
        3. Extract translatable strings
        4. Generate translation keys
        5. Create locale files
        """
        # Find the first matching event
        event = next(
            (e for e in events if e.type in self.subscribed_events),
            None
        )
        if not event:
            return

        self._last_extraction = datetime.now()
        self._extracted_keys = {}

        logger.info(
            "localization_started",
            working_dir=str(self.working_dir),
            trigger_event=event.type.value,
        )

        # Publish start event
        await self.event_bus.publish(i18n_setup_started_event(
            source=self.name,
            working_dir=str(self.working_dir),
            default_locale=self.default_locale,
            target_locales=self.target_locales,
        ))

        # Step 1: Detect i18n library
        library = await self._detect_i18n_library()
        self._detected_library = library

        if not library:
            # Check if i18n is required based on contracts
            i18n_required = await self._check_i18n_required(event)
            if i18n_required:
                logger.info("i18n_required_but_not_configured")
                # Could trigger setup here
            else:
                logger.info("i18n_not_required")
                return

        # Step 2: Verify/create i18n configuration
        await self._ensure_i18n_config(library)

        # Step 3: Extract translatable strings
        if self.extract_strings:
            await self._extract_translatable_strings()

        # Step 4: Generate translation keys
        if self.generate_keys and self._extracted_keys:
            await self._generate_locale_files()

        # Publish completion event
        total_keys = sum(len(keys) for keys in self._extracted_keys.values())
        await self.event_bus.publish(localization_complete_event(
            source=self.name,
            library=library or "unknown",
            locales=self.target_locales,
            keys_extracted=total_keys,
            namespaces=list(self._extracted_keys.keys()),
        ))

        logger.info(
            "localization_complete",
            library=library,
            keys_extracted=total_keys,
        )

    async def _detect_i18n_library(self) -> Optional[str]:
        """Detect which i18n library is being used."""

        if self.forced_library:
            return self.forced_library

        # Check package.json
        package_json = self.working_dir / "package.json"
        if package_json.exists():
            try:
                content = json.loads(package_json.read_text())
                deps = {
                    **content.get("dependencies", {}),
                    **content.get("devDependencies", {}),
                }

                for lib_name, lib_config in I18N_LIBRARIES.items():
                    if lib_config["package"] in deps:
                        return lib_name
            except json.JSONDecodeError:
                pass

        # Check for config files
        for lib_name, lib_config in I18N_LIBRARIES.items():
            config_file = self.working_dir / lib_config["config_file"]
            if config_file.exists():
                return lib_name

            # Also check src directory
            config_file = self.working_dir / "src" / lib_config["config_file"]
            if config_file.exists():
                return lib_name

        return None

    async def _check_i18n_required(self, event: Event) -> bool:
        """Check if i18n is required based on contracts or requirements."""

        # Check event data for i18n requirements
        data = event.data or {}
        requirements = data.get("requirements", [])

        for req in requirements:
            if isinstance(req, dict):
                desc = req.get("description", "").lower()
                name = req.get("name", "").lower()
            else:
                desc = str(req).lower()
                name = ""

            if any(keyword in desc or keyword in name for keyword in [
                "i18n", "internationalization", "localization", "translation",
                "multi-language", "multilingual", "locale"
            ]):
                return True

        return False

    async def _ensure_i18n_config(self, library: Optional[str]) -> None:
        """Ensure i18n configuration exists."""

        if not library:
            return

        lib_config = I18N_LIBRARIES.get(library, {})
        messages_dir = self.working_dir / lib_config.get("messages_dir", "locales")

        # Create messages directory if it doesn't exist
        if not messages_dir.exists():
            messages_dir.mkdir(parents=True, exist_ok=True)
            logger.info("messages_directory_created", path=str(messages_dir))

        # Publish config event
        await self.event_bus.publish(i18n_configured_event(
            source=self.name,
            library=library,
            messages_dir=str(messages_dir),
        ))

    async def _extract_translatable_strings(self) -> None:
        """Extract translatable strings from source code."""

        # Source directories to scan
        src_dirs = [
            self.working_dir / "src",
            self.working_dir / "app",
            self.working_dir / "pages",
            self.working_dir / "components",
        ]

        files_to_scan = []
        for src_dir in src_dirs:
            if src_dir.exists():
                files_to_scan.extend(src_dir.rglob("*.tsx"))
                files_to_scan.extend(src_dir.rglob("*.jsx"))
                files_to_scan.extend(src_dir.rglob("*.ts"))
                files_to_scan.extend(src_dir.rglob("*.js"))

        all_keys = set()
        hardcoded_strings = []

        for file_path in files_to_scan:
            try:
                content = file_path.read_text(encoding="utf-8")

                # Extract existing translation keys
                for pattern_name, pattern in STRING_PATTERNS.items():
                    if pattern_name in ["jsx_text", "placeholder", "aria_label", "title_attr", "alt_text"]:
                        # These are potential hardcoded strings
                        matches = re.findall(pattern, content)
                        for match in matches:
                            if len(match) > 2 and not match.startswith("{"):
                                hardcoded_strings.append({
                                    "file": str(file_path.relative_to(self.working_dir)),
                                    "string": match,
                                    "type": pattern_name,
                                })
                    else:
                        # These are existing translation keys
                        matches = re.findall(pattern, content)
                        all_keys.update(matches)

            except Exception as e:
                logger.debug("file_scan_error", file=str(file_path), error=str(e))

        # Organize keys by namespace
        for key in all_keys:
            if "." in key:
                namespace, subkey = key.split(".", 1)
            else:
                namespace = "common"
                subkey = key

            if namespace not in self._extracted_keys:
                self._extracted_keys[namespace] = []
            if subkey not in self._extracted_keys[namespace]:
                self._extracted_keys[namespace].append(subkey)

        # Report hardcoded strings that need translation
        if hardcoded_strings:
            await self.event_bus.publish(translation_needed_event(
                source=self.name,
                hardcoded_strings=hardcoded_strings[:50],  # Limit to 50
                count=len(hardcoded_strings),
            ))

        logger.info(
            "strings_extracted",
            existing_keys=len(all_keys),
            hardcoded_strings=len(hardcoded_strings),
            namespaces=len(self._extracted_keys),
        )

        # Publish extraction event
        await self.event_bus.publish(translation_keys_extracted_event(
            source=self.name,
            keys=sum(len(keys) for keys in self._extracted_keys.values()),
            namespaces=list(self._extracted_keys.keys()),
            hardcoded_count=len(hardcoded_strings),
        ))

    async def _generate_locale_files(self) -> None:
        """Generate locale files for extracted keys."""

        if not self._detected_library:
            return

        lib_config = I18N_LIBRARIES.get(self._detected_library, {})
        messages_dir = self.working_dir / lib_config.get("messages_dir", "locales")
        messages_dir.mkdir(parents=True, exist_ok=True)

        for locale in self.target_locales:
            locale_dir = messages_dir / locale
            locale_dir.mkdir(exist_ok=True)

            for namespace, keys in self._extracted_keys.items():
                locale_file = locale_dir / f"{namespace}.json"

                # Load existing translations
                existing = {}
                if locale_file.exists():
                    try:
                        existing = json.loads(locale_file.read_text())
                    except json.JSONDecodeError:
                        pass

                # Add new keys (don't overwrite existing)
                for key in keys:
                    if key not in existing:
                        if locale == self.default_locale:
                            # For default locale, use the key as placeholder
                            existing[key] = self._key_to_placeholder(key)
                        else:
                            # For other locales, mark as needing translation
                            existing[key] = f"[{locale.upper()}] {self._key_to_placeholder(key)}"

                # Write locale file
                locale_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

        logger.info(
            "locale_files_generated",
            locales=self.target_locales,
            namespaces=list(self._extracted_keys.keys()),
        )

    def _key_to_placeholder(self, key: str) -> str:
        """Convert a translation key to a placeholder value."""
        # Convert snake_case or camelCase to Title Case
        # e.g., "submit_button" -> "Submit Button"
        # e.g., "submitButton" -> "Submit Button"

        # Handle snake_case
        words = key.replace("_", " ").replace("-", " ")

        # Handle camelCase
        words = re.sub(r"([a-z])([A-Z])", r"\1 \2", words)

        return words.title()

    async def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("localization_agent_cleanup_complete")
