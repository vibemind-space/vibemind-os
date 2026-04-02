"""
CategoryRegistry - Dynamisches Kategorie-System für MoireTracker

Features:
- Lädt/Speichert Kategorien aus categories.json
- Hierarchische Kategorien (Parent-Child)
- Auto-Approve für neue Kategorien nach N Vorschlägen
- Dynamische LLM Prompt Generierung
- Statistik-Tracking pro Kategorie

Usage:
    registry = CategoryRegistry()
    
    # Alle Kategorien
    categories = registry.get_all_categories()
    
    # Nur leaf categories (für Classification)
    leaf_cats = registry.get_leaf_categories()
    
    # LLM Prompt generieren
    prompt = registry.build_classification_prompt()
    
    # Neue Kategorie vorschlagen
    registry.suggest_category("social_icon", "Social media application icons", parent="icon")
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any, Set
from dataclasses import dataclass, field, asdict
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Category:
    """Eine UI-Element Kategorie."""
    name: str
    description: str
    examples: List[str] = field(default_factory=list)
    parent: Optional[str] = None
    usage_count: int = 0
    created_by_llm: bool = False
    created_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "examples": self.examples,
            "parent": self.parent,
            "usageCount": self.usage_count,
            "createdByLlm": self.created_by_llm,
            "createdAt": self.created_at
        }


@dataclass
class PendingCategory:
    """Eine vorgeschlagene, noch nicht genehmigte Kategorie."""
    name: str
    description: str
    suggested_by: str  # Model name
    parent: Optional[str] = None
    examples: List[str] = field(default_factory=list)
    votes: int = 1
    first_suggested: str = ""
    last_suggested: str = ""
    contexts: List[str] = field(default_factory=list)  # Element-Kontexte die zur Suggestion führten
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "suggestedBy": self.suggested_by,
            "parent": self.parent,
            "examples": self.examples,
            "votes": self.votes,
            "firstSuggested": self.first_suggested,
            "lastSuggested": self.last_suggested,
            "contexts": self.contexts[:10]  # Max 10 Kontexte speichern
        }


class CategoryRegistry:
    """
    Zentrale Registry für alle UI-Element Kategorien.
    
    Unterstützt:
    - Hierarchische Kategorien
    - Auto-Approve für neue Kategorien
    - Dynamische LLM Prompt Generierung
    """
    
    DEFAULT_PATH = "config/categories.json"
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialisiert die CategoryRegistry.
        
        Args:
            config_path: Pfad zur categories.json, oder None für Default
        """
        if config_path:
            self._path = Path(config_path)
        else:
            # Suche relativ zum Projekt-Root
            base = Path(__file__).parent.parent.parent
            self._path = base / self.DEFAULT_PATH
        
        self._categories: Dict[str, Category] = {}
        self._pending: Dict[str, PendingCategory] = {}
        self._settings: Dict[str, Any] = {
            "autoApproveThreshold": 3,
            "enableHierarchy": True,
            "maxPendingCategories": 50
        }
        self._version = "1.0.0"
        self._last_updated = datetime.now().isoformat()
        
        # Cache für Hierarchie
        self._children_cache: Dict[str, List[str]] = {}
        
        self._load()
    
    # ==================== Load/Save ====================
    
    def _load(self) -> bool:
        """Lädt Kategorien aus JSON-Datei."""
        if not self._path.exists():
            logger.warning(f"Categories file not found: {self._path}")
            self._create_default()
            return False
        
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._version = data.get("version", "1.0.0")
            self._settings = data.get("settings", self._settings)
            self._last_updated = data.get("lastUpdated", datetime.now().isoformat())
            
            # Lade Kategorien
            for name, cat_data in data.get("categories", {}).items():
                self._categories[name] = Category(
                    name=name,
                    description=cat_data.get("description", ""),
                    examples=cat_data.get("examples", []),
                    parent=cat_data.get("parent"),
                    usage_count=cat_data.get("usageCount", 0),
                    created_by_llm=cat_data.get("createdByLlm", False),
                    created_at=cat_data.get("createdAt")
                )
            
            # Lade Pending Categories
            for pending_data in data.get("pendingCategories", []):
                name = pending_data.get("name")
                if name:
                    self._pending[name] = PendingCategory(
                        name=name,
                        description=pending_data.get("description", ""),
                        suggested_by=pending_data.get("suggestedBy", "unknown"),
                        parent=pending_data.get("parent"),
                        examples=pending_data.get("examples", []),
                        votes=pending_data.get("votes", 1),
                        first_suggested=pending_data.get("firstSuggested", ""),
                        last_suggested=pending_data.get("lastSuggested", ""),
                        contexts=pending_data.get("contexts", [])
                    )
            
            # Build hierarchy cache
            self._build_hierarchy_cache()
            
            logger.info(f"CategoryRegistry geladen: {len(self._categories)} Kategorien, {len(self._pending)} pending")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load categories: {e}")
            return False
    
    def _save(self) -> bool:
        """Speichert Kategorien in JSON-Datei."""
        try:
            self._last_updated = datetime.now().isoformat()
            
            data = {
                "version": self._version,
                "created": self._categories.get("button", Category("", "")).created_at or datetime.now().isoformat(),
                "lastUpdated": self._last_updated,
                "settings": self._settings,
                "categories": {
                    name: cat.to_dict() for name, cat in self._categories.items()
                },
                "pendingCategories": [
                    pending.to_dict() for pending in self._pending.values()
                ],
                "categoryHistory": []  # TODO: Implementiere History
            }
            
            # Ensure directory exists
            self._path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self._path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"CategoryRegistry gespeichert: {self._path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save categories: {e}")
            return False
    
    def _create_default(self):
        """Erstellt Default-Kategorien."""
        defaults = [
            ("button", "Clickable UI element that triggers an action", None),
            ("icon", "Small graphical symbol", None),
            ("input", "Text input field or form control", None),
            ("text", "Static text or label", None),
            ("link", "Clickable link element", None),
            ("container", "Layout container grouping elements", None),
            ("unknown", "Unidentified UI element", None),
        ]
        
        for name, desc, parent in defaults:
            self._categories[name] = Category(
                name=name,
                description=desc,
                parent=parent,
                created_at=datetime.now().isoformat()
            )
        
        self._save()
    
    def _build_hierarchy_cache(self):
        """Baut Cache für Parent-Child Beziehungen."""
        self._children_cache.clear()
        
        for name, cat in self._categories.items():
            if cat.parent:
                if cat.parent not in self._children_cache:
                    self._children_cache[cat.parent] = []
                self._children_cache[cat.parent].append(name)
    
    # ==================== Category Access ====================
    
    def get_all_categories(self) -> List[str]:
        """Gibt alle Kategorie-Namen zurück."""
        return list(self._categories.keys())
    
    def get_category(self, name: str) -> Optional[Category]:
        """Gibt eine Kategorie nach Name zurück."""
        return self._categories.get(name)
    
    def get_leaf_categories(self) -> List[str]:
        """
        Gibt nur Blatt-Kategorien zurück (ohne Kinder).
        Diese werden für Classification verwendet.
        """
        parents = set(cat.parent for cat in self._categories.values() if cat.parent)
        return [name for name in self._categories.keys() if name not in parents]
    
    def get_parent_categories(self) -> List[str]:
        """Gibt nur Parent-Kategorien zurück."""
        parents = set(cat.parent for cat in self._categories.values() if cat.parent)
        return list(parents)
    
    def get_children(self, parent: str) -> List[str]:
        """Gibt alle Kinder einer Parent-Kategorie zurück."""
        return self._children_cache.get(parent, [])
    
    def get_hierarchy_path(self, name: str) -> List[str]:
        """
        Gibt den Hierarchie-Pfad einer Kategorie zurück.
        
        Beispiel: get_hierarchy_path("browser_icon") -> ["icon", "browser_icon"]
        """
        path = []
        current = name
        
        while current:
            path.insert(0, current)
            cat = self._categories.get(current)
            current = cat.parent if cat else None
        
        return path
    
    def category_exists(self, name: str) -> bool:
        """Prüft ob Kategorie existiert."""
        return name in self._categories
    
    def is_valid_category(self, name: str) -> bool:
        """Prüft ob Name als Klassifikations-Ergebnis valide ist."""
        return name in self._categories or name == "NEW_CATEGORY"
    
    # ==================== Category Management ====================
    
    def add_category(
        self,
        name: str,
        description: str,
        examples: List[str] = None,
        parent: Optional[str] = None,
        created_by_llm: bool = False
    ) -> bool:
        """
        Fügt eine neue Kategorie hinzu.
        
        Args:
            name: Kategorie-Name (snake_case)
            description: Beschreibung
            examples: Beispiele
            parent: Parent-Kategorie (für Hierarchie)
            created_by_llm: Ob vom LLM vorgeschlagen
            
        Returns:
            True wenn erfolgreich
        """
        if name in self._categories:
            logger.warning(f"Kategorie '{name}' existiert bereits")
            return False
        
        # Validate parent
        if parent and parent not in self._categories:
            logger.warning(f"Parent-Kategorie '{parent}' existiert nicht")
            return False
        
        self._categories[name] = Category(
            name=name,
            description=description,
            examples=examples or [],
            parent=parent,
            created_by_llm=created_by_llm,
            created_at=datetime.now().isoformat()
        )
        
        # Update cache
        if parent:
            if parent not in self._children_cache:
                self._children_cache[parent] = []
            self._children_cache[parent].append(name)
        
        # Remove from pending if exists
        if name in self._pending:
            del self._pending[name]
        
        self._save()
        logger.info(f"Kategorie hinzugefügt: {name} (parent: {parent})")
        return True
    
    def increment_usage(self, name: str) -> None:
        """Erhöht den Usage-Counter einer Kategorie."""
        if name in self._categories:
            self._categories[name].usage_count += 1
            # Nicht bei jedem Increment speichern - periodic save stattdessen
    
    def save_usage_stats(self) -> None:
        """Speichert alle Usage-Statistiken."""
        self._save()
    
    # ==================== Pending Categories (Auto-Approve) ====================
    
    def suggest_category(
        self,
        name: str,
        description: str,
        suggested_by: str = "gemini-2.0-flash",
        parent: Optional[str] = None,
        examples: List[str] = None,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Schlägt eine neue Kategorie vor.
        
        Wenn die Kategorie bereits N mal vorgeschlagen wurde (autoApproveThreshold),
        wird sie automatisch hinzugefügt.
        
        Args:
            name: Vorgeschlagener Name (snake_case)
            description: Beschreibung
            suggested_by: Model das die Suggestion machte
            parent: Optionale Parent-Kategorie
            examples: Optionale Beispiele
            context: Kontext der zur Suggestion führte
            
        Returns:
            Status-Dictionary mit action: "approved", "pending", oder "exists"
        """
        name = name.lower().replace(" ", "_").replace("-", "_")
        now = datetime.now().isoformat()
        
        # Existiert bereits?
        if name in self._categories:
            return {"action": "exists", "category": name}
        
        # Max pending erreicht?
        if len(self._pending) >= self._settings.get("maxPendingCategories", 50):
            # Remove oldest
            oldest = min(self._pending.values(), key=lambda p: p.first_suggested)
            del self._pending[oldest.name]
        
        # Bereits pending?
        if name in self._pending:
            pending = self._pending[name]
            pending.votes += 1
            pending.last_suggested = now
            if context and context not in pending.contexts:
                pending.contexts.append(context)
            if examples:
                for ex in examples:
                    if ex not in pending.examples:
                        pending.examples.append(ex)
            
            # Auto-Approve Threshold erreicht?
            threshold = self._settings.get("autoApproveThreshold", 3)
            if pending.votes >= threshold:
                self.add_category(
                    name=name,
                    description=pending.description,
                    examples=pending.examples,
                    parent=pending.parent,
                    created_by_llm=True
                )
                logger.info(f"Kategorie auto-approved: {name} (votes: {pending.votes})")
                return {
                    "action": "approved",
                    "category": name,
                    "votes": pending.votes,
                    "description": pending.description
                }
            else:
                self._save()
                return {
                    "action": "pending",
                    "category": name,
                    "votes": pending.votes,
                    "threshold": threshold
                }
        
        # Neue pending Kategorie
        self._pending[name] = PendingCategory(
            name=name,
            description=description,
            suggested_by=suggested_by,
            parent=parent,
            examples=examples or [],
            votes=1,
            first_suggested=now,
            last_suggested=now,
            contexts=[context] if context else []
        )
        
        self._save()
        return {
            "action": "pending",
            "category": name,
            "votes": 1,
            "threshold": self._settings.get("autoApproveThreshold", 3)
        }
    
    def get_pending_categories(self) -> List[PendingCategory]:
        """Gibt alle pending categories zurück."""
        return list(self._pending.values())
    
    def approve_pending(self, name: str) -> bool:
        """Genehmigt eine pending Kategorie manuell."""
        if name not in self._pending:
            return False
        
        pending = self._pending[name]
        return self.add_category(
            name=name,
            description=pending.description,
            examples=pending.examples,
            parent=pending.parent,
            created_by_llm=True
        )
    
    def reject_pending(self, name: str) -> bool:
        """Lehnt eine pending Kategorie ab."""
        if name not in self._pending:
            return False
        
        del self._pending[name]
        self._save()
        return True
    
    # ==================== LLM Prompt Generation ====================
    
    def build_classification_prompt(
        self,
        include_new_category_option: bool = True,
        include_examples: bool = True,
        max_examples_per_category: int = 3
    ) -> str:
        """
        Baut den System-Prompt für LLM Classification dynamisch.
        
        Args:
            include_new_category_option: Ob NEW_CATEGORY erlaubt sein soll
            include_examples: Ob Beispiele inkludiert werden sollen
            max_examples_per_category: Max Beispiele pro Kategorie
            
        Returns:
            System-Prompt String
        """
        # Kategorien sortiert: Parent-Categories zuerst, dann alphabetisch
        sorted_cats = sorted(
            self._categories.values(),
            key=lambda c: (0 if c.parent else 1, c.name)
        )
        
        # Build category list
        cat_lines = []
        for cat in sorted_cats:
            if cat.name == "unknown":
                continue  # Unknown am Ende
            
            line = f"- **{cat.name}**: {cat.description}"
            if cat.parent:
                line += f" (child of: {cat.parent})"
            
            if include_examples and cat.examples:
                examples = cat.examples[:max_examples_per_category]
                line += f"\n  Examples: {', '.join(examples)}"
            
            cat_lines.append(line)
        
        # Add unknown at end
        if "unknown" in self._categories:
            cat_lines.append(f"- **unknown**: {self._categories['unknown'].description}")
        
        categories_text = "\n".join(cat_lines)
        
        # Build prompt
        prompt = f"""You are a specialized UI element classifier for desktop applications.

## Available Categories:
{categories_text}

## Task:
Analyze the provided UI element image and classify it into the most specific matching category.

## Response Format:
Return ONLY a valid JSON object:
```json
{{
  "category": "category_name",
  "semantic_name": "Human-readable name like Chrome Browser or Save Button",
  "confidence": 0.95,
  "description": "Brief description of the element"
}}
```
"""

        if include_new_category_option:
            prompt += """
## NEW CATEGORY Option:
If NO existing category fits well (confidence < 70%), you may suggest a new one:
```json
{
  "category": "NEW_CATEGORY",
  "new_category_name": "suggested_name_snake_case",
  "new_category_description": "What this category represents",
  "new_category_parent": "parent_category_if_applicable",
  "semantic_name": "Human-readable name for this specific element",
  "confidence": 0.85
}
```

Rules for new categories:
- Use snake_case for category names
- Provide clear, concise description
- Specify parent category if the new category is a sub-type
- Only suggest if truly distinct from existing categories
"""

        prompt += """
## Important:
- Choose the MOST SPECIFIC category that applies
- If element is a browser icon, use "browser_icon" not just "icon"
- Always provide a meaningful semantic_name
- Respond with valid JSON only, no additional text
"""
        
        return prompt
    
    def get_category_list_for_prompt(self) -> str:
        """Gibt eine einfache Kategorie-Liste für Prompts zurück."""
        cats = self.get_leaf_categories()
        return ", ".join(sorted(cats))
    
    # ==================== Statistics ====================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Gibt Statistiken über die Registry zurück."""
        total_usage = sum(cat.usage_count for cat in self._categories.values())
        llm_created = sum(1 for cat in self._categories.values() if cat.created_by_llm)
        
        return {
            "totalCategories": len(self._categories),
            "leafCategories": len(self.get_leaf_categories()),
            "parentCategories": len(self.get_parent_categories()),
            "pendingCategories": len(self._pending),
            "totalUsage": total_usage,
            "llmCreatedCategories": llm_created,
            "settings": self._settings,
            "topCategories": sorted(
                [(cat.name, cat.usage_count) for cat in self._categories.values()],
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }


# ==================== Singleton ====================

_registry_instance: Optional[CategoryRegistry] = None


def get_category_registry(config_path: Optional[str] = None) -> CategoryRegistry:
    """Gibt die Singleton-Instanz der CategoryRegistry zurück."""
    global _registry_instance
    
    if _registry_instance is None:
        _registry_instance = CategoryRegistry(config_path)
    
    return _registry_instance


def reset_category_registry() -> None:
    """Setzt die Singleton-Instanz zurück (für Tests)."""
    global _registry_instance
    _registry_instance = None


# ==================== CLI Test ====================

if __name__ == "__main__":
    registry = get_category_registry()
    
    print("\n" + "="*60)
    print("CategoryRegistry Test")
    print("="*60)
    
    print(f"\nStatistics:")
    stats = registry.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print(f"\nLeaf Categories ({len(registry.get_leaf_categories())}):")
    for cat in sorted(registry.get_leaf_categories()):
        c = registry.get_category(cat)
        parent_info = f" (parent: {c.parent})" if c.parent else ""
        print(f"  - {cat}{parent_info}: {c.description[:50]}...")
    
    print(f"\nParent Categories:")
    for parent in registry.get_parent_categories():
        children = registry.get_children(parent)
        print(f"  - {parent}: {children}")
    
    print(f"\n" + "="*60)
    print("Generated LLM Prompt:")
    print("="*60)
    print(registry.build_classification_prompt()[:2000] + "...")
    
    print(f"\n" + "="*60)
    print("TEST: Suggest new category")
    print("="*60)
    result = registry.suggest_category(
        "social_icon",
        "Desktop icons for social media applications",
        parent="icon",
        examples=["Discord", "Slack", "Teams"]
    )
    print(f"Result: {result}")