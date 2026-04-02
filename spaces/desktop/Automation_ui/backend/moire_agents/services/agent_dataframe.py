"""
AgentDataFrame - Performanter DataFrame für Desktop Automation Agents

Features:
- O(1) Lookup via Name/Text/ID Dictionaries
- Fuzzy-Matching für ungenaue Namen
- Räumlicher Index für schnelle Region-Queries
- LLM-freundliche Context-Generierung
- State-Differenz für Action Validation
- Dynamische Kategorien aus CategoryRegistry

Usage:
    df = AgentDataFrame.from_scan(analyzer_result)
    
    # Schneller Zugriff O(1)
    chrome = df["Chrome Browser"]  # by name
    coords = df.click("Save Button")  # returns (x, y)
    
    # Fuzzy-Suche
    elements = df.search("chrom")  # findet "Chrome Browser"
    
    # Region-Query
    toolbar = df.in_region(0, 0, 1920, 50)
    
    # Dynamische Kategorien
    browser_icons = df.by_category_tree("icon")  # inkl. browser_icon, editor_icon, etc.
    
    # Für LLM
    context = df.to_context()
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple, Union, Any, Set
from dataclasses import dataclass
from difflib import SequenceMatcher
import json

# Import CategoryRegistry für dynamische Kategorien
try:
    from services.category_registry import get_category_registry, CategoryRegistry
    HAS_CATEGORY_REGISTRY = True
except ImportError:
    HAS_CATEGORY_REGISTRY = False
    CategoryRegistry = None


def _get_registry_categories() -> Tuple[List[str], Dict[str, List[str]]]:
    """
    Lädt Kategorien und Hierarchie aus der Registry.
    
    Returns:
        Tuple: (alle_kategorien, hierarchie_dict)
    """
    if not HAS_CATEGORY_REGISTRY:
        return [], {}
    
    try:
        registry = get_category_registry()
        categories = list(registry.data.get("categories", {}).keys())
        
        # Build hierarchy: parent -> children
        hierarchy: Dict[str, List[str]] = {}
        for cat_name, cat_def in registry.data.get("categories", {}).items():
            parent = cat_def.get("parent")
            if parent:
                if parent not in hierarchy:
                    hierarchy[parent] = []
                hierarchy[parent].append(cat_name)
        
        return categories, hierarchy
    except Exception:
        return [], {}


def _get_category_descendants(category: str, hierarchy: Dict[str, List[str]]) -> Set[str]:
    """
    Gibt alle Nachkommen einer Kategorie zurück (rekursiv).
    
    Args:
        category: Parent-Kategorie
        hierarchy: Hierarchie-Dict
        
    Returns:
        Set aller Nachkommen-Kategorien
    """
    descendants = {category}
    children = hierarchy.get(category, [])
    
    for child in children:
        descendants.add(child)
        # Rekursiv für Sub-Children
        descendants.update(_get_category_descendants(child, hierarchy))
    
    return descendants


@dataclass
class UIElement:
    """Schneller Zugriff auf Element-Daten."""
    id: str
    name: str
    category: str
    text: str
    x: int
    y: int
    width: int
    height: int
    center_x: int
    center_y: int
    confidence: float
    
    def click_coords(self) -> Tuple[int, int]:
        """Gibt Klick-Koordinaten zurück."""
        return (self.center_x, self.center_y)
    
    def bounds(self) -> Tuple[int, int, int, int]:
        """Gibt Bounding Box zurück (x, y, width, height)."""
        return (self.x, self.y, self.width, self.height)
    
    def contains(self, px: int, py: int) -> bool:
        """Prüft ob Punkt im Element liegt."""
        return (self.x <= px < self.x + self.width and 
                self.y <= py < self.y + self.height)
    
    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'text': self.text,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'center': (self.center_x, self.center_y)
        }


class AgentDataFrame:
    """
    Performanter DataFrame für Desktop Automation Agents.
    
    Indices für O(1) Zugriff:
    - _by_id: element_id -> UIElement
    - _by_name: name (lowercase) -> UIElement
    - _by_text: text (lowercase) -> List[UIElement]
    - _by_category: category -> List[UIElement]
    
    Räumlicher Index:
    - _grid: 100x100 Grid für schnelle Region-Queries
    
    Dynamische Kategorien:
    - Kategorien werden aus CategoryRegistry geladen
    - Hierarchische Abfragen mit by_category_tree()
    """
    
    GRID_SIZE = 100  # Pixel pro Grid-Zelle
    
    def __init__(self, df: pd.DataFrame):
        """
        Initialisiert AgentDataFrame mit internen Indizes.
        
        Args:
            df: Pandas DataFrame mit UI-Elementen
        """
        self._df = df.copy()
        self._elements: List[UIElement] = []
        
        # O(1) Lookup Indices
        self._by_id: Dict[str, UIElement] = {}
        self._by_name: Dict[str, UIElement] = {}  # lowercase key
        self._by_text: Dict[str, List[UIElement]] = {}  # lowercase key
        self._by_category: Dict[str, List[UIElement]] = {}
        
        # Räumlicher Index (Grid)
        self._grid: Dict[Tuple[int, int], List[UIElement]] = {}
        self._screen_width = 1920
        self._screen_height = 1080
        
        # Dynamische Kategorien aus Registry
        self._registry_categories, self._category_hierarchy = _get_registry_categories()
        
        # Build indices
        self._build_indices()
    
    def _build_indices(self):
        """Baut alle Lookup-Indizes auf."""
        for _, row in self._df.iterrows():
            elem = UIElement(
                id=str(row.get('element_id', '')),
                name=str(row.get('name', '')),
                category=str(row.get('category', 'unknown')),
                text=str(row.get('ocr_text', '') or ''),
                x=int(row.get('x', 0)),
                y=int(row.get('y', 0)),
                width=int(row.get('width', 0)),
                height=int(row.get('height', 0)),
                center_x=int(row.get('center_x', 0)),
                center_y=int(row.get('center_y', 0)),
                confidence=float(row.get('confidence', 0.0))
            )
            
            self._elements.append(elem)
            
            # ID Index
            self._by_id[elem.id] = elem
            
            # Name Index (lowercase für case-insensitive lookup)
            name_lower = elem.name.lower()
            if name_lower not in self._by_name:
                self._by_name[name_lower] = elem
            
            # Text Index
            if elem.text:
                text_lower = elem.text.lower()
                if text_lower not in self._by_text:
                    self._by_text[text_lower] = []
                self._by_text[text_lower].append(elem)
            
            # Category Index
            if elem.category not in self._by_category:
                self._by_category[elem.category] = []
            self._by_category[elem.category].append(elem)
            
            # Spatial Grid Index
            self._add_to_grid(elem)
    
    def _add_to_grid(self, elem: UIElement):
        """Fügt Element zum räumlichen Grid hinzu."""
        # Berechne Grid-Zellen die das Element überlappt
        x1 = elem.x // self.GRID_SIZE
        y1 = elem.y // self.GRID_SIZE
        x2 = (elem.x + elem.width) // self.GRID_SIZE
        y2 = (elem.y + elem.height) // self.GRID_SIZE
        
        for gx in range(x1, x2 + 1):
            for gy in range(y1, y2 + 1):
                cell = (gx, gy)
                if cell not in self._grid:
                    self._grid[cell] = []
                self._grid[cell].append(elem)
    
    # ==================== Fast Lookup Methods O(1) ====================
    
    def __getitem__(self, key: str) -> Optional[UIElement]:
        """
        Schneller Zugriff via Name oder ID.
        
        Usage:
            elem = df["Chrome Browser"]
            elem = df["box_42"]
        """
        # Try ID first
        if key in self._by_id:
            return self._by_id[key]
        
        # Try name (case-insensitive)
        key_lower = key.lower()
        if key_lower in self._by_name:
            return self._by_name[key_lower]
        
        return None
    
    def __contains__(self, key: str) -> bool:
        """Prüft ob Element existiert."""
        return key in self._by_id or key.lower() in self._by_name
    
    def __len__(self) -> int:
        """Anzahl Elemente."""
        return len(self._elements)
    
    def __iter__(self):
        """Iteriert über alle Elemente."""
        return iter(self._elements)
    
    def get(self, key: str, default: Optional[UIElement] = None) -> Optional[UIElement]:
        """Sicherer Zugriff mit Default."""
        result = self[key]
        return result if result is not None else default
    
    def click(self, name_or_id: str) -> Optional[Tuple[int, int]]:
        """
        Gibt Klick-Koordinaten für Element zurück.
        
        Usage:
            x, y = df.click("Save Button")
            await agent.click(x, y)
        """
        elem = self[name_or_id]
        return elem.click_coords() if elem else None
    
    def by_id(self, element_id: str) -> Optional[UIElement]:
        """Direkter Zugriff via ID O(1)."""
        return self._by_id.get(element_id)
    
    def by_name(self, name: str) -> Optional[UIElement]:
        """Direkter Zugriff via Name O(1)."""
        return self._by_name.get(name.lower())
    
    # ==================== Text Search Methods ====================
    
    def by_text(self, text: str, exact: bool = False) -> List[UIElement]:
        """
        Findet Elemente anhand OCR-Text.
        
        Args:
            text: Suchtext
            exact: Wenn True, nur exakte Matches
            
        Returns:
            Liste passender Elemente
        """
        text_lower = text.lower()
        
        if exact:
            return self._by_text.get(text_lower, [])
        
        # Fuzzy search - alle Texte die den Suchtext enthalten
        results = []
        for key, elements in self._by_text.items():
            if text_lower in key or key in text_lower:
                results.extend(elements)
        
        return results
    
    def search(self, query: str, threshold: float = 0.6) -> List[UIElement]:
        """
        Fuzzy-Suche über Namen und Text.
        
        Args:
            query: Suchbegriff
            threshold: Minimale Ähnlichkeit (0-1)
            
        Returns:
            Liste passender Elemente, sortiert nach Relevanz
        """
        query_lower = query.lower()
        results = []
        
        for elem in self._elements:
            # Check name
            name_score = SequenceMatcher(None, query_lower, elem.name.lower()).ratio()
            
            # Check text
            text_score = 0.0
            if elem.text:
                text_score = SequenceMatcher(None, query_lower, elem.text.lower()).ratio()
            
            best_score = max(name_score, text_score)
            
            # Bonus für exakte Substring-Matches
            if query_lower in elem.name.lower() or query_lower in elem.text.lower():
                best_score = max(best_score, 0.8)
            
            if best_score >= threshold:
                results.append((elem, best_score))
        
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return [elem for elem, _ in results]
    
    # ==================== Category Filters ====================
    
    def by_category(self, category: str) -> List[UIElement]:
        """Alle Elemente einer Kategorie O(1)."""
        return self._by_category.get(category, [])
    
    def by_category_tree(self, parent_category: str) -> List[UIElement]:
        """
        Alle Elemente einer Kategorie inkl. aller Sub-Kategorien.
        
        Beispiel:
            df.by_category_tree("icon")  # findet icon, browser_icon, editor_icon, etc.
        
        Args:
            parent_category: Parent-Kategorie
            
        Returns:
            Liste aller Elemente in Kategorie und Sub-Kategorien
        """
        # Hole alle Nachkommen
        all_categories = _get_category_descendants(parent_category, self._category_hierarchy)
        
        # Sammle Elemente aus allen Kategorien
        results = []
        seen_ids = set()
        
        for cat in all_categories:
            for elem in self._by_category.get(cat, []):
                if elem.id not in seen_ids:
                    seen_ids.add(elem.id)
                    results.append(elem)
        
        return results
    
    def get_available_categories(self) -> List[str]:
        """
        Gibt alle verfügbaren Kategorien aus der Registry zurück.
        
        Returns:
            Liste aller Kategorie-Namen
        """
        if self._registry_categories:
            return self._registry_categories
        return list(self._by_category.keys())
    
    def get_category_hierarchy(self) -> Dict[str, List[str]]:
        """
        Gibt die Kategorie-Hierarchie zurück.
        
        Returns:
            Dict: parent -> [children]
        """
        return self._category_hierarchy.copy()
    
    def get_leaf_categories(self) -> List[str]:
        """
        Gibt alle Leaf-Kategorien zurück (ohne Kinder).
        
        Returns:
            Liste der Leaf-Kategorien
        """
        all_cats = set(self.get_available_categories())
        parents = set(self._category_hierarchy.keys())
        return list(all_cats - parents)
    
    def buttons(self) -> List[UIElement]:
        """Alle Buttons (inkl. Sub-Typen)."""
        return self.by_category_tree('button')
    
    def inputs(self) -> List[UIElement]:
        """Alle Input-Felder."""
        return self.by_category_tree('input')
    
    def icons(self) -> List[UIElement]:
        """Alle Icons (inkl. browser_icon, editor_icon, etc.)."""
        return self.by_category_tree('icon')
    
    def text_elements(self) -> List[UIElement]:
        """Alle Text-Elemente."""
        return self.by_category_tree('text')
    
    def links(self) -> List[UIElement]:
        """Alle Links."""
        return self.by_category_tree('link')
    
    def containers(self) -> List[UIElement]:
        """Alle Container."""
        return self.by_category_tree('container')
    
    def categories(self) -> List[str]:
        """Liste aller verwendeten Kategorien im DataFrame."""
        return list(self._by_category.keys())
    
    def category_stats(self) -> Dict[str, Any]:
        """
        Gibt Statistiken über Kategorien zurück.
        
        Returns:
            Dict mit Statistiken
        """
        used_cats = {cat: len(elems) for cat, elems in self._by_category.items() if elems}
        available_cats = self.get_available_categories()
        
        return {
            'used_categories': used_cats,
            'unused_categories': [c for c in available_cats if c not in used_cats],
            'total_available': len(available_cats),
            'total_used': len(used_cats),
            'hierarchy': self._category_hierarchy
        }
    
    # ==================== Dynamic Category Accessor ====================
    
    def __getattr__(self, name: str) -> Any:
        """
        Dynamischer Zugriff auf Kategorien als Methoden.
        
        Beispiel:
            df.browser_icon()  # Equivalent zu by_category("browser_icon")
            df.taskbar_item()  # Equivalent zu by_category("taskbar_item")
        """
        # Check if it's a valid category name
        if name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        # Check registry categories
        available = self.get_available_categories() if hasattr(self, '_registry_categories') else []
        
        if name in available or name in getattr(self, '_by_category', {}):
            def category_getter(tree: bool = False) -> List[UIElement]:
                if tree:
                    return self.by_category_tree(name)
                return self.by_category(name)
            return category_getter
        
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
    
    # ==================== Spatial Queries ====================
    
    def at_point(self, x: int, y: int) -> List[UIElement]:
        """
        Elemente an einem Punkt.
        
        Args:
            x, y: Koordinaten
            
        Returns:
            Liste der Elemente die diesen Punkt enthalten
        """
        gx = x // self.GRID_SIZE
        gy = y // self.GRID_SIZE
        cell_key = (gx, gy)
        
        if cell_key not in self._grid:
            return []
        
        result = []
        seen_ids = set()
        for elem in self._grid[cell_key]:
            if elem.id in seen_ids:
                continue
            seen_ids.add(elem.id)
            # Check if point is within element bounds
            if (elem.x <= x <= elem.x + elem.width and
                elem.y <= y <= elem.y + elem.height):
                result.append(elem)
        
        return result
    
    def in_region(self, x: int, y: int, width: int, height: int) -> List[UIElement]:
        """Get all elements within a rectangular region using spatial index.
        
        Uses O(grid_cells) lookup instead of O(n) full scan.
        
        Args:
            x: Left edge of region
            y: Top edge of region
            width: Width of region
            height: Height of region
            
        Returns:
            List of UIElement within the region
        """
        # Find all grid cells that overlap with region
        start_gx = x // self.GRID_SIZE
        end_gx = (x + width) // self.GRID_SIZE
        start_gy = y // self.GRID_SIZE
        end_gy = (y + height) // self.GRID_SIZE
        
        # Collect candidate elements from overlapping cells
        seen_ids = set()
        candidates = []
        for gx in range(start_gx, end_gx + 1):
            for gy in range(start_gy, end_gy + 1):
                cell_key = (gx, gy)
                if cell_key in self._grid:
                    for elem in self._grid[cell_key]:
                        if elem.id not in seen_ids:
                            seen_ids.add(elem.id)
                            candidates.append(elem)
        
        # Filter to elements actually within region
        result = []
        for elem in candidates:
            # Check if element center is within region
            if (x <= elem.center_x <= x + width and 
                y <= elem.center_y <= y + height):
                result.append(elem)
        
        return result
    
    def nearest(
        self, 
        x: int, 
        y: int, 
        category: Optional[str] = None,
        max_distance: int = 500
    ) -> Optional[UIElement]:
        """
        Nächstes Element zu einem Punkt.
        
        Args:
            x, y: Referenzpunkt
            category: Optional - nur diese Kategorie
            max_distance: Maximale Distanz
            
        Returns:
            Nächstes Element oder None
        """
        best_elem = None
        best_dist = float('inf')
        
        elements = self._by_category.get(category, self._elements) if category else self._elements
        
        for elem in elements:
            dist = ((elem.center_x - x) ** 2 + (elem.center_y - y) ** 2) ** 0.5
            if dist < best_dist and dist <= max_distance:
                best_dist = dist
                best_elem = elem
        
        return best_elem
    
    def toolbar(self) -> List[UIElement]:
        """Elemente im typischen Toolbar-Bereich (oben)."""
        return self.in_region(0, 0, self._screen_width, 80)
    
    def taskbar(self) -> List[UIElement]:
        """Elemente im Taskbar-Bereich (unten)."""
        return self.in_region(0, self._screen_height - 60, self._screen_width, 60)
    
    # ==================== LLM Context Generation ====================
    
    def to_context(
        self, 
        max_elements: int = 50,
        include_coords: bool = True,
        focus_region: Optional[Tuple[int, int, int, int]] = None,
        group_by_category: bool = False
    ) -> str:
        """
        Kompakter Context-String für LLM.
        
        Args:
            max_elements: Maximale Anzahl Elemente
            include_coords: Koordinaten einschließen
            focus_region: Optional - Fokus auf Region (x, y, w, h)
            group_by_category: Elemente nach Kategorie gruppieren
            
        Returns:
            Kompakter String für LLM-Prompts
        """
        if focus_region:
            elements = self.in_region(*focus_region)[:max_elements]
        else:
            elements = self._elements[:max_elements]
        
        if group_by_category:
            # Gruppiere nach Kategorie
            by_cat: Dict[str, List[UIElement]] = {}
            for elem in elements:
                if elem.category not in by_cat:
                    by_cat[elem.category] = []
                by_cat[elem.category].append(elem)
            
            lines = [f"UI Elements ({len(elements)} of {len(self._elements)}):"]
            for cat, cat_elements in sorted(by_cat.items()):
                lines.append(f"\n[{cat.upper()}] ({len(cat_elements)} elements):")
                for elem in cat_elements:
                    line = f"  - {elem.name}"
                    if elem.text and elem.text != elem.name:
                        line += f" [{elem.text}]"
                    if include_coords:
                        line += f" @({elem.center_x},{elem.center_y})"
                    lines.append(line)
        else:
            lines = [f"UI Elements ({len(elements)} of {len(self._elements)}):"]
            
            for elem in elements:
                line = f"- {elem.name}"
                if elem.text and elem.text != elem.name:
                    line += f" [{elem.text}]"
                if include_coords:
                    line += f" @({elem.center_x},{elem.center_y})"
                lines.append(line)
        
        if len(self._elements) > max_elements:
            lines.append(f"... and {len(self._elements) - max_elements} more elements")
        
        return "\n".join(lines)
    
    def to_json(self, max_elements: Optional[int] = None) -> str:
        """Konvertiert zu JSON String."""
        elements = self._elements[:max_elements] if max_elements else self._elements
        return json.dumps([e.to_dict() for e in elements], indent=2)
    
    def summary(self) -> str:
        """Kurze Zusammenfassung für Logging."""
        cat_counts = {cat: len(elems) for cat, elems in self._by_category.items()}
        registry_info = f", registry: {len(self._registry_categories)} categories" if self._registry_categories else ""
        return f"AgentDataFrame: {len(self)} elements, used: {cat_counts}{registry_info}"
    
    def category_summary(self) -> str:
        """Kurze Zusammenfassung der Kategorien."""
        stats = self.category_stats()
        used = sorted(stats['used_categories'].items(), key=lambda i: i[1], reverse=True)
        used_str = ", ".join(f"{cat}: {count}" for cat, count in used)
        total_notifications = stats.get('notifications', 0)
        min_elem = min(stats.get('min_elements', 0), len(self._elements))
        max_elem = max(stats.get('max_elements', 0), len(self._elements))
        avg_elem = stats.get('avg_elements', 0)
        return (f"Categories: {len(self._registry_categories)} / {len(self._by_category)} (used), "
                f"elements: {min_elem}-{max_elem} ({avg_elem}), "
                f"notifications: {total_notifications}")
    
    def category_lost_items(self) -> str:
        """Listet alle verfügbaren Kategorien auf, die nicht im DataFrame vorkommen."""
        available = set(self.get_available_categories())
        used = set(self._by_category.keys())
        lost = available - used
        return ", ".join(sorted(lost)) if lost else "none"
    
    def category_missing_counts(self) -> Dict[str, int]:
        """Gibt ein Dict mit Anzahl seiner Elemente für jeder verfügbare Kategorie zurück."""
        available = set(self.get_available_categories())
        used = set(self._by_category.keys())
        missing = available - used
        missing_counts = {}
        for cat in available:
            count = len(self._by_category.get(cat, []))
            missing_counts[cat] = count
        return missing_counts
    
    # ==================== State Comparison ====================
    
    def diff(self, other: 'AgentDataFrame') -> Dict[str, Any]:
        """
        Vergleicht mit anderem AgentDataFrame.
        
        Args:
            other: Anderer AgentDataFrame (z.B. nach Action)
            
        Returns:
            Dictionary mit Änderungen
        """
        old_ids = set(self._by_id.keys())
        new_ids = set(other._by_id.keys())
        
        added = new_ids - old_ids
        removed = old_ids - new_ids
        
        # Text changes in gemeinsamen Elementen
        text_changes = []
        for elem_id in old_ids & new_ids:
            old_elem = self._by_id[elem_id]
            new_elem = other._by_id[elem_id]
            
            if old_elem.text != new_elem.text:
                text_changes.append({
                    'id': elem_id,
                    'old_text': old_elem.text,
                    'new_text': new_elem.text
                })
        
        return {
            'added': list(added),
            'removed': list(removed),
            'text_changes': text_changes,
            'total_old': len(self),
            'total_new': len(other),
            'changed': bool(added or removed or text_changes)
        }
    
    # ==================== Factory Methods ====================
    
    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> 'AgentDataFrame':
        """Erstellt AgentDataFrame aus Pandas DataFrame."""
        return cls(df)
    
    @classmethod
    def from_elements(cls, elements: List[Dict[str, Any]]) -> 'AgentDataFrame':
        """Erstellt AgentDataFrame aus Element-Liste."""
        df = pd.DataFrame(elements)
        return cls(df)
    
    @property
    def df(self) -> pd.DataFrame:
        """Zugriff auf underlying DataFrame."""
        return self._df
    
    @property
    def all_elements(self) -> List[UIElement]:
        """Alle Elemente als Liste."""
        return self._elements


# ==================== Convenience Functions ====================

def make_agent_df(df: pd.DataFrame) -> AgentDataFrame:
    """Kurzer Factory-Aufruf."""
    return AgentDataFrame.from_dataframe(df)