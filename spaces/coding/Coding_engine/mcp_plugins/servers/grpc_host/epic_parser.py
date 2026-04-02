#!/usr/bin/env python3
"""
Epic Parser - Phase 3, Iteration 6

Parst Epics aus dem Input-Projekt und extrahiert strukturierte Daten
fuer die Task-Generierung.

Features:
- Parst user_stories.md fuer alle Epics
- Extrahiert User Stories, Requirements, Entities, APIs
- Cross-Referenziert mit data_dictionary.md und api_documentation.md
- Speichert epics.json fuer Dashboard-Anzeige
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class UserStory:
    """Einzelne User Story"""
    id: str
    title: str
    priority: str  # MUST, SHOULD, COULD, WONT
    linked_requirement: str
    description: str = ""
    acceptance_criteria: List[str] = field(default_factory=list)


@dataclass
class Epic:
    """Ein Epic mit allen zugehoerigen Daten"""
    id: str  # "EPIC-001"
    name: str  # "Identity, Auth & Device Access"
    description: str
    status: str = "pending"  # pending, running, completed, failed
    progress_percent: float = 0.0
    user_stories: List[str] = field(default_factory=list)  # ["US-001", ...]
    requirements: List[str] = field(default_factory=list)  # ["WA-AUTH-001", ...]
    entities: List[str] = field(default_factory=list)  # ["User", "AuthMethod", ...]
    api_endpoints: List[str] = field(default_factory=list)  # ["/auth/register", ...]
    last_run_at: Optional[str] = None
    run_count: int = 0


@dataclass
class EpicSummary:
    """Zusammenfassung aller Epics"""
    project_path: str
    total_epics: int
    total_user_stories: int
    total_requirements: int
    total_entities: int
    generated_at: str
    epics: List[Epic] = field(default_factory=list)


class EpicParser:
    """
    Parst Epics aus dem Input-Projekt.

    Extrahiert strukturierte Daten aus:
    - user_stories/user_stories.md
    - data/data_dictionary.md
    - api/api_documentation.md
    """

    # Regex Patterns fuer das Parsen
    EPIC_HEADER_PATTERN = r"^# (EPIC-\d{3}): (.+)$"
    EPIC_STATUS_PATTERN = r"\*\*Status:\*\* (\w+)"
    REQUIREMENTS_PATTERN = r"^- (WA-[A-Z]+-\d{3})$"
    USER_STORY_PATTERN = r"^- (US-\d{3})$"
    ENTITY_REQ_PATTERN = r"\*Source Requirements:\* (.+)"
    API_ENDPOINT_PATTERN = r"((?:GET|POST|PUT|DELETE|PATCH)\s+)?(/[a-z0-9/{}_-]+)"

    def __init__(self, project_path: str):
        """
        Args:
            project_path: Pfad zum Input-Projekt
        """
        self.project_path = Path(project_path)
        self._validate_project_structure()

        # Caches fuer geparste Daten
        self._requirement_to_entities: Dict[str, List[str]] = {}
        self._requirement_to_apis: Dict[str, List[str]] = {}
        self._user_stories_data: Dict[str, UserStory] = {}

        logger.info(f"EpicParser initialized for: {self.project_path}")

    def _validate_project_structure(self):
        """Validiert die erwartete Projektstruktur"""
        required_files = [
            "user_stories/user_stories.md",
        ]

        optional_files = [
            "data/data_dictionary.md",
            "api/api_documentation.md",
        ]

        for file in required_files:
            if not (self.project_path / file).exists():
                raise FileNotFoundError(
                    f"Required file not found: {self.project_path / file}"
                )

        for file in optional_files:
            if not (self.project_path / file).exists():
                logger.warning(f"Optional file not found: {file}")

    def parse_all_epics(self) -> List[Epic]:
        """
        Parst alle Epics aus user_stories.md.

        Returns:
            Liste aller Epic-Objekte
        """
        # 1. Erst optionale Referenz-Daten laden
        self._load_entity_mappings()
        self._load_api_mappings()

        # 2. User Stories Markdown lesen
        user_stories_path = self.project_path / "user_stories" / "user_stories.md"
        content = user_stories_path.read_text(encoding="utf-8")

        # 3. Epics parsen
        epics = self._parse_epics_from_content(content)

        # 4. User Stories Details parsen
        self._parse_user_stories(content)

        # 5. Entities und APIs zu Epics zuordnen
        for epic in epics:
            epic.entities = self._find_entities_for_requirements(epic.requirements)
            epic.api_endpoints = self._find_apis_for_requirements(epic.requirements)

        logger.info(f"Parsed {len(epics)} epics with {sum(len(e.user_stories) for e in epics)} user stories")

        return epics

    def _parse_epics_from_content(self, content: str) -> List[Epic]:
        """Parst Epic-Bloecke aus dem Markdown-Content"""
        epics = []

        # Split by Epic headers
        lines = content.split('\n')
        current_epic = None
        current_section = None

        for line in lines:
            # Check for Epic header
            header_match = re.match(self.EPIC_HEADER_PATTERN, line)
            if header_match:
                # Save previous epic
                if current_epic:
                    epics.append(current_epic)

                # Start new epic
                epic_id = header_match.group(1)
                epic_name = header_match.group(2).strip()
                current_epic = Epic(
                    id=epic_id,
                    name=epic_name,
                    description=""
                )
                current_section = None
                continue

            if not current_epic:
                continue

            # Check for status
            status_match = re.search(self.EPIC_STATUS_PATTERN, line)
            if status_match:
                # Epic status from file is always "draft" initially
                continue

            # Check for section headers
            if line.startswith("## Description"):
                current_section = "description"
                continue
            elif line.startswith("## Linked Requirements"):
                current_section = "requirements"
                continue
            elif line.startswith("## User Stories"):
                current_section = "user_stories"
                continue
            elif line.startswith("## ") or line.startswith("# "):
                current_section = None
                continue
            elif line.startswith("---"):
                # Section separator - save current epic
                if current_epic and current_epic.id:
                    epics.append(current_epic)
                    current_epic = None
                current_section = None
                continue

            # Parse content based on current section
            if current_section == "description" and line.strip():
                if current_epic.description:
                    current_epic.description += " " + line.strip()
                else:
                    current_epic.description = line.strip()

            elif current_section == "requirements":
                req_match = re.match(self.REQUIREMENTS_PATTERN, line.strip())
                if req_match:
                    current_epic.requirements.append(req_match.group(1))

            elif current_section == "user_stories":
                us_match = re.match(self.USER_STORY_PATTERN, line.strip())
                if us_match:
                    current_epic.user_stories.append(us_match.group(1))

        # Don't forget the last epic
        if current_epic and current_epic.id:
            # Check if not already added
            if not epics or epics[-1].id != current_epic.id:
                epics.append(current_epic)

        return epics

    def _parse_user_stories(self, content: str):
        """Parst User Story Details aus dem Markdown"""
        # Pattern fuer User Story Bloecke
        us_pattern = r"## (US-\d{3}): (.+?)\n\n\*\*Priority:\*\* (\w+)\n\*\*Linked Requirement:\*\* (WA-[A-Z]+-\d{3})"

        for match in re.finditer(us_pattern, content):
            us_id = match.group(1)
            title = match.group(2).strip()
            priority = match.group(3)
            requirement = match.group(4)

            self._user_stories_data[us_id] = UserStory(
                id=us_id,
                title=title,
                priority=priority,
                linked_requirement=requirement
            )

    def _load_entity_mappings(self):
        """Laedt Entity-zu-Requirement Mappings aus data_dictionary.md"""
        data_dict_path = self.project_path / "data" / "data_dictionary.md"

        if not data_dict_path.exists():
            logger.warning("data_dictionary.md not found, skipping entity mapping")
            return

        content = data_dict_path.read_text(encoding="utf-8")

        # Parse entities with their source requirements
        current_entity = None

        for line in content.split('\n'):
            # Entity header: ### EntityName
            if line.startswith("### ") and not line.startswith("### Attribute"):
                current_entity = line[4:].strip()
                continue

            # Source requirements
            if current_entity and line.startswith("*Source Requirements:*"):
                req_match = re.search(self.ENTITY_REQ_PATTERN, line)
                if req_match:
                    reqs = [r.strip() for r in req_match.group(1).split(",")]
                    for req in reqs:
                        if req not in self._requirement_to_entities:
                            self._requirement_to_entities[req] = []
                        self._requirement_to_entities[req].append(current_entity)

        logger.info(f"Loaded entity mappings for {len(self._requirement_to_entities)} requirements")

    def _load_api_mappings(self):
        """Laedt API-zu-Requirement Mappings aus api_documentation.md"""
        api_doc_path = self.project_path / "api" / "api_documentation.md"

        if not api_doc_path.exists():
            logger.warning("api_documentation.md not found, skipping API mapping")
            return

        content = api_doc_path.read_text(encoding="utf-8")

        # Parse API endpoints with their requirements
        current_endpoint = None

        for line in content.split('\n'):
            # Endpoint pattern: ### GET /path or ### POST /path
            endpoint_match = re.search(r"###\s+(GET|POST|PUT|DELETE|PATCH)\s+(/[^\s]+)", line)
            if endpoint_match:
                current_endpoint = f"{endpoint_match.group(1)} {endpoint_match.group(2)}"
                continue

            # Source requirements in endpoint section
            if current_endpoint:
                for req in re.findall(r"WA-[A-Z]+-\d{3}", line):
                    if req not in self._requirement_to_apis:
                        self._requirement_to_apis[req] = []
                    if current_endpoint not in self._requirement_to_apis[req]:
                        self._requirement_to_apis[req].append(current_endpoint)

        logger.info(f"Loaded API mappings for {len(self._requirement_to_apis)} requirements")

    def _find_entities_for_requirements(self, requirements: List[str]) -> List[str]:
        """Findet alle Entities die zu den Requirements gehoeren"""
        entities = set()
        for req in requirements:
            if req in self._requirement_to_entities:
                entities.update(self._requirement_to_entities[req])
        return sorted(list(entities))

    def _find_apis_for_requirements(self, requirements: List[str]) -> List[str]:
        """Findet alle APIs die zu den Requirements gehoeren"""
        apis = set()
        for req in requirements:
            if req in self._requirement_to_apis:
                apis.update(self._requirement_to_apis[req])
        return sorted(list(apis))

    def get_epic_by_id(self, epic_id: str) -> Optional[Epic]:
        """
        Gibt einen spezifischen Epic zurueck.

        Args:
            epic_id: z.B. "EPIC-001"

        Returns:
            Epic oder None
        """
        epics = self.parse_all_epics()
        for epic in epics:
            if epic.id == epic_id:
                return epic
        return None

    def get_user_story(self, us_id: str) -> Optional[UserStory]:
        """Gibt eine spezifische User Story zurueck"""
        if not self._user_stories_data:
            # Parse if not already done
            content = (self.project_path / "user_stories" / "user_stories.md").read_text(encoding="utf-8")
            self._parse_user_stories(content)

        return self._user_stories_data.get(us_id)

    def create_epic_summary(self, epics: Optional[List[Epic]] = None) -> EpicSummary:
        """
        Erstellt eine Zusammenfassung aller Epics.

        Args:
            epics: Optional vorgeparste Epics

        Returns:
            EpicSummary Objekt
        """
        if epics is None:
            epics = self.parse_all_epics()

        all_requirements = set()
        all_entities = set()
        all_user_stories = set()

        for epic in epics:
            all_requirements.update(epic.requirements)
            all_entities.update(epic.entities)
            all_user_stories.update(epic.user_stories)

        return EpicSummary(
            project_path=str(self.project_path),
            total_epics=len(epics),
            total_user_stories=len(all_user_stories),
            total_requirements=len(all_requirements),
            total_entities=len(all_entities),
            generated_at=datetime.now().isoformat(),
            epics=epics
        )

    def save_epics_json(self, output_path: Optional[str] = None) -> str:
        """
        Speichert alle Epics als epics.json.

        Args:
            output_path: Ziel-Pfad. Default: {project}/tasks/epics.json

        Returns:
            Pfad zur erstellten Datei
        """
        if output_path is None:
            output_path = self.project_path / "tasks" / "epics.json"
        else:
            output_path = Path(output_path)

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Parse and create summary
        epics = self.parse_all_epics()
        summary = self.create_epic_summary(epics)

        # Convert to dict (handles nested dataclasses)
        def to_dict(obj):
            if hasattr(obj, '__dataclass_fields__'):
                return {k: to_dict(v) for k, v in asdict(obj).items()}
            elif isinstance(obj, list):
                return [to_dict(item) for item in obj]
            return obj

        output_data = to_dict(summary)

        # Write JSON
        output_path.write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        logger.info(f"Saved epics.json to: {output_path}")
        return str(output_path)

    def save_epic_tasks_json(self, epic_id: str, tasks: List[Dict], output_path: Optional[str] = None) -> str:
        """
        Speichert Tasks fuer einen spezifischen Epic.

        Args:
            epic_id: z.B. "EPIC-001"
            tasks: Liste von Task-Dicts
            output_path: Ziel-Pfad. Default: {project}/tasks/epic-001-tasks.json

        Returns:
            Pfad zur erstellten Datei
        """
        if output_path is None:
            epic_lower = epic_id.lower().replace("_", "-")
            output_path = self.project_path / "tasks" / f"{epic_lower}-tasks.json"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        epic = self.get_epic_by_id(epic_id)

        output_data = {
            "epic_id": epic_id,
            "epic_name": epic.name if epic else "",
            "tasks": tasks,
            "total_tasks": len(tasks),
            "run_count": 0,
            "last_run_at": None,
            "created_at": datetime.now().isoformat()
        }

        output_path.write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        logger.info(f"Saved {epic_id} tasks to: {output_path}")
        return str(output_path)


# =============================================================================
# Test
# =============================================================================

def test_epic_parser():
    """Test der EpicParser Funktionalitaet"""
    print("=== Epic Parser Test ===\n")

    # Test project path
    test_path = Path(__file__).parent.parent.parent.parent / "Data" / "all_services" / "unnamed_project_20260204_165411"

    if not test_path.exists():
        print(f"Test project not found: {test_path}")
        return

    parser = EpicParser(str(test_path))

    # Test 1: Parse all epics
    print("1. Parsing all epics:")
    epics = parser.parse_all_epics()
    print(f"   Found {len(epics)} epics")

    for epic in epics:
        print(f"\n   {epic.id}: {epic.name}")
        print(f"      User Stories: {len(epic.user_stories)}")
        print(f"      Requirements: {len(epic.requirements)}")
        print(f"      Entities: {len(epic.entities)}")
        print(f"      APIs: {len(epic.api_endpoints)}")

    # Test 2: Get specific epic
    print("\n2. Get EPIC-001:")
    epic_001 = parser.get_epic_by_id("EPIC-001")
    if epic_001:
        print(f"   Name: {epic_001.name}")
        print(f"   Description: {epic_001.description[:100]}...")
        print(f"   User Stories: {epic_001.user_stories}")
        print(f"   Entities: {epic_001.entities}")

    # Test 3: Create summary
    print("\n3. Epic Summary:")
    summary = parser.create_epic_summary(epics)
    print(f"   Total Epics: {summary.total_epics}")
    print(f"   Total User Stories: {summary.total_user_stories}")
    print(f"   Total Requirements: {summary.total_requirements}")
    print(f"   Total Entities: {summary.total_entities}")

    # Test 4: Save epics.json (optional)
    print("\n4. Save test (dry run):")
    print(f"   Would save to: {test_path / 'tasks' / 'epics.json'}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_epic_parser()
