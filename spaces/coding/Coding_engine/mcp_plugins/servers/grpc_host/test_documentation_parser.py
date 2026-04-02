#!/usr/bin/env python3
"""
Test Documentation Parser - Phase 3.5

Parst test_documentation.md und extrahiert Gherkin Features und Scenarios.

Features:
- Parst alle 126 Features mit 608 Scenarios
- Extrahiert Tags (@smoke, @regression, @happy-path, @negative, @boundary)
- Links zu User Stories (US-NNN)
- Generiert Test-spezifische Tasks
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class ScenarioType(Enum):
    SCENARIO = "scenario"
    SCENARIO_OUTLINE = "scenario_outline"


class TestCategory(Enum):
    SMOKE = "smoke"
    REGRESSION = "regression"
    HAPPY_PATH = "happy_path"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    EDGE_CASE = "edge_case"
    INTEGRATION = "integration"


@dataclass
class GherkinStep:
    """Single Gherkin step"""
    keyword: str  # Given, When, Then, And
    text: str


@dataclass
class GherkinExample:
    """Example data for Scenario Outlines"""
    headers: List[str]
    rows: List[List[str]]


@dataclass
class GherkinScenario:
    """Single Gherkin Scenario"""
    name: str
    tags: List[str] = field(default_factory=list)
    type: str = "scenario"  # scenario or scenario_outline
    steps: List[GherkinStep] = field(default_factory=list)
    examples: Optional[GherkinExample] = None
    description: str = ""

    @property
    def is_happy_path(self) -> bool:
        return any("happy" in t.lower() for t in self.tags)

    @property
    def is_negative(self) -> bool:
        return any("negative" in t.lower() for t in self.tags)

    @property
    def is_boundary(self) -> bool:
        return any("boundary" in t.lower() for t in self.tags)

    @property
    def is_smoke(self) -> bool:
        return any("smoke" in t.lower() for t in self.tags)

    @property
    def test_category(self) -> str:
        """Determine primary test category"""
        if self.is_happy_path:
            return TestCategory.HAPPY_PATH.value
        elif self.is_negative:
            return TestCategory.NEGATIVE.value
        elif self.is_boundary:
            return TestCategory.BOUNDARY.value
        elif any("edge" in t.lower() for t in self.tags):
            return TestCategory.EDGE_CASE.value
        elif self.is_smoke:
            return TestCategory.SMOKE.value
        return TestCategory.REGRESSION.value


@dataclass
class GherkinFeature:
    """Gherkin Feature with Scenarios"""
    name: str
    user_story: str  # US-NNN
    tags: List[str] = field(default_factory=list)
    description: str = ""
    background: List[GherkinStep] = field(default_factory=list)
    scenarios: List[GherkinScenario] = field(default_factory=list)

    @property
    def scenario_count(self) -> int:
        return len(self.scenarios)

    @property
    def happy_path_count(self) -> int:
        return sum(1 for s in self.scenarios if s.is_happy_path)

    @property
    def negative_count(self) -> int:
        return sum(1 for s in self.scenarios if s.is_negative)


class TestDocumentationParser:
    """
    Parst test_documentation.md und extrahiert Gherkin Features.

    Format des Markdown:
    ### Feature Name

    *User Story:* US-NNN

    ```gherkin
    @tag1 @tag2
    Feature: Feature Name
      As a ...
      I want ...
      So that ...

      Background:
        Given ...

      @happy-path
      Scenario: Scenario Name
        Given ...
        When ...
        Then ...
    ```
    """

    # Regex patterns
    FEATURE_HEADER_PATTERN = r"^### (.+)$"
    USER_STORY_PATTERN = r"\*User Story:\*\s+(US-\d{3})"
    GHERKIN_BLOCK_PATTERN = r"```gherkin\n(.*?)```"
    FEATURE_LINE_PATTERN = r"^Feature:\s*(.+)$"
    SCENARIO_PATTERN = r"^(Scenario|Scenario Outline):\s*(.+)$"
    BACKGROUND_PATTERN = r"^Background:$"
    STEP_PATTERN = r"^\s*(Given|When|Then|And|But)\s+(.+)$"
    TAG_PATTERN = r"@[\w-]+"
    EXAMPLES_PATTERN = r"^\s*Examples:$"
    TABLE_ROW_PATTERN = r"^\s*\|(.+)\|$"

    def __init__(self, project_path: str):
        """
        Args:
            project_path: Path to the input project
        """
        self.project_path = Path(project_path)
        self.test_doc_path = self.project_path / "testing" / "test_documentation.md"

        # Caches
        self._features: List[GherkinFeature] = []
        self._user_story_to_features: Dict[str, List[GherkinFeature]] = {}
        self._tag_to_scenarios: Dict[str, List[GherkinScenario]] = {}
        self._parsed = False

        logger.info(f"TestDocumentationParser initialized for: {project_path}")

    def parse_all_features(self) -> List[GherkinFeature]:
        """
        Parse all features from test_documentation.md.

        Returns:
            List of GherkinFeature objects
        """
        if self._parsed:
            return self._features

        if not self.test_doc_path.exists():
            logger.warning(f"test_documentation.md not found at {self.test_doc_path}")
            return []

        content = self.test_doc_path.read_text(encoding="utf-8")
        self._features = self._parse_features_from_content(content)
        self._build_indexes()
        self._parsed = True

        total_scenarios = sum(f.scenario_count for f in self._features)
        logger.info(f"Parsed {len(self._features)} features with {total_scenarios} scenarios")
        return self._features

    def _parse_features_from_content(self, content: str) -> List[GherkinFeature]:
        """Parse feature blocks from markdown content"""
        features = []

        # Split by feature headers (### Feature Name)
        lines = content.split('\n')
        current_feature_name = None
        current_user_story = None
        current_gherkin_block = []
        in_gherkin_block = False

        for line in lines:
            # Check for feature header
            header_match = re.match(self.FEATURE_HEADER_PATTERN, line)
            if header_match and not in_gherkin_block:
                # Process previous feature if exists
                if current_feature_name and current_gherkin_block:
                    feature = self._parse_gherkin_block(
                        current_feature_name,
                        current_user_story or "",
                        '\n'.join(current_gherkin_block)
                    )
                    if feature:
                        features.append(feature)

                current_feature_name = header_match.group(1).strip()
                current_user_story = None
                current_gherkin_block = []
                continue

            # Check for user story
            us_match = re.search(self.USER_STORY_PATTERN, line)
            if us_match:
                current_user_story = us_match.group(1)
                continue

            # Track gherkin block
            if "```gherkin" in line:
                in_gherkin_block = True
                continue
            elif "```" in line and in_gherkin_block:
                in_gherkin_block = False
                continue

            if in_gherkin_block:
                current_gherkin_block.append(line)

        # Don't forget the last feature
        if current_feature_name and current_gherkin_block:
            feature = self._parse_gherkin_block(
                current_feature_name,
                current_user_story or "",
                '\n'.join(current_gherkin_block)
            )
            if feature:
                features.append(feature)

        return features

    def _parse_gherkin_block(self, name: str, user_story: str, gherkin_content: str) -> Optional[GherkinFeature]:
        """Parse a single gherkin block into a Feature object"""
        lines = gherkin_content.split('\n')

        feature = GherkinFeature(
            name=name,
            user_story=user_story
        )

        current_scenario = None
        current_section = None  # 'background', 'scenario', 'examples'
        pending_tags = []
        example_headers = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check for tags
            tags_found = re.findall(self.TAG_PATTERN, stripped)
            if tags_found and not stripped.startswith(('Given', 'When', 'Then', 'And', 'But')):
                pending_tags.extend([t.replace('@', '') for t in tags_found])
                # If this line is only tags, continue
                if stripped == ' '.join(tags_found) or all(c in '@-_ ' or c.isalnum() for c in stripped):
                    continue

            # Check for Feature line
            feature_match = re.match(self.FEATURE_LINE_PATTERN, stripped)
            if feature_match:
                feature.tags = pending_tags.copy()
                pending_tags = []
                continue

            # Check for Background
            if re.match(self.BACKGROUND_PATTERN, stripped):
                current_section = 'background'
                current_scenario = None
                continue

            # Check for Scenario/Scenario Outline
            scenario_match = re.match(self.SCENARIO_PATTERN, stripped)
            if scenario_match:
                # Save previous scenario
                if current_scenario:
                    feature.scenarios.append(current_scenario)

                scenario_type = "scenario_outline" if "Outline" in scenario_match.group(1) else "scenario"
                current_scenario = GherkinScenario(
                    name=scenario_match.group(2).strip(),
                    type=scenario_type,
                    tags=pending_tags.copy()
                )
                pending_tags = []
                current_section = 'scenario'
                continue

            # Check for Examples
            if re.match(self.EXAMPLES_PATTERN, stripped):
                current_section = 'examples'
                example_headers = []
                continue

            # Parse steps
            step_match = re.match(self.STEP_PATTERN, stripped)
            if step_match:
                step = GherkinStep(
                    keyword=step_match.group(1),
                    text=step_match.group(2)
                )
                if current_section == 'background':
                    feature.background.append(step)
                elif current_scenario:
                    current_scenario.steps.append(step)
                continue

            # Parse example table rows
            if current_section == 'examples':
                table_match = re.match(self.TABLE_ROW_PATTERN, stripped)
                if table_match:
                    cells = [c.strip() for c in table_match.group(1).split('|')]
                    if not example_headers:
                        example_headers = cells
                    elif current_scenario:
                        if not current_scenario.examples:
                            current_scenario.examples = GherkinExample(
                                headers=example_headers,
                                rows=[]
                            )
                        current_scenario.examples.rows.append(cells)

        # Save last scenario
        if current_scenario:
            feature.scenarios.append(current_scenario)

        return feature if feature.scenarios else None

    def _build_indexes(self):
        """Build lookup indexes for fast access"""
        self._user_story_to_features = {}
        self._tag_to_scenarios = {}

        for feature in self._features:
            # Index by user story
            if feature.user_story:
                if feature.user_story not in self._user_story_to_features:
                    self._user_story_to_features[feature.user_story] = []
                self._user_story_to_features[feature.user_story].append(feature)

            # Index scenarios by tag
            for scenario in feature.scenarios:
                for tag in scenario.tags:
                    tag_lower = tag.lower()
                    if tag_lower not in self._tag_to_scenarios:
                        self._tag_to_scenarios[tag_lower] = []
                    self._tag_to_scenarios[tag_lower].append(scenario)

    def get_features_by_user_story(self, us_id: str) -> List[GherkinFeature]:
        """
        Get all features for a specific user story.

        Args:
            us_id: User Story ID (e.g., "US-001")

        Returns:
            List of matching features
        """
        if not self._parsed:
            self.parse_all_features()

        return self._user_story_to_features.get(us_id, [])

    def get_scenarios_by_tag(self, tag: str) -> List[GherkinScenario]:
        """
        Get all scenarios with a specific tag.

        Args:
            tag: Tag name (without @)

        Returns:
            List of matching scenarios
        """
        if not self._parsed:
            self.parse_all_features()

        return self._tag_to_scenarios.get(tag.lower(), [])

    def get_all_user_stories(self) -> Set[str]:
        """Get all unique user story IDs"""
        if not self._parsed:
            self.parse_all_features()

        return set(self._user_story_to_features.keys())

    def get_all_tags(self) -> Set[str]:
        """Get all unique tags"""
        if not self._parsed:
            self.parse_all_features()

        return set(self._tag_to_scenarios.keys())

    def get_scenarios_by_category(self, category: TestCategory) -> List[GherkinScenario]:
        """Get scenarios by test category"""
        if not self._parsed:
            self.parse_all_features()

        scenarios = []
        for feature in self._features:
            for scenario in feature.scenarios:
                if scenario.test_category == category.value:
                    scenarios.append(scenario)
        return scenarios

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics"""
        if not self._parsed:
            self.parse_all_features()

        total_scenarios = sum(f.scenario_count for f in self._features)
        happy_path_count = sum(f.happy_path_count for f in self._features)
        negative_count = sum(f.negative_count for f in self._features)

        return {
            "total_features": len(self._features),
            "total_scenarios": total_scenarios,
            "total_user_stories": len(self._user_story_to_features),
            "total_unique_tags": len(self._tag_to_scenarios),
            "scenarios_by_category": {
                "happy_path": happy_path_count,
                "negative": negative_count,
                "smoke": len(self.get_scenarios_by_tag("smoke")),
                "regression": len(self.get_scenarios_by_tag("regression")),
            }
        }

    def to_json(self, output_path: Optional[str] = None) -> str:
        """Export parsed features to JSON"""
        if not self._parsed:
            self.parse_all_features()

        def to_dict(obj):
            if hasattr(obj, '__dataclass_fields__'):
                result = {}
                for k, v in asdict(obj).items():
                    result[k] = to_dict(v)
                return result
            elif isinstance(obj, list):
                return [to_dict(item) for item in obj]
            return obj

        data = {
            "summary": self.get_summary(),
            "features": [to_dict(f) for f in self._features]
        }

        json_str = json.dumps(data, indent=2, ensure_ascii=False)

        if output_path:
            Path(output_path).write_text(json_str, encoding="utf-8")
            logger.info(f"Saved test features to: {output_path}")

        return json_str


# =============================================================================
# Test
# =============================================================================

def test_test_documentation_parser():
    """Test the TestDocumentationParser"""
    print("=== Test Documentation Parser Test ===\n")

    # Test project path
    test_path = Path(__file__).parent.parent.parent.parent / "Data" / "all_services" / "unnamed_project_20260204_165411"

    if not test_path.exists():
        print(f"Test project not found: {test_path}")
        return

    parser = TestDocumentationParser(str(test_path))

    # Test 1: Parse all features
    print("1. Parsing all features:")
    features = parser.parse_all_features()
    print(f"   Found {len(features)} features")

    # Test 2: Get summary
    print("\n2. Summary:")
    summary = parser.get_summary()
    print(f"   Total features: {summary['total_features']}")
    print(f"   Total scenarios: {summary['total_scenarios']}")
    print(f"   User Stories: {summary['total_user_stories']}")
    print(f"   Categories: {summary['scenarios_by_category']}")

    # Test 3: Show first 3 features
    print("\n3. First 3 features:")
    for feature in features[:3]:
        print(f"\n   {feature.name}")
        print(f"      User Story: {feature.user_story}")
        print(f"      Tags: {feature.tags}")
        print(f"      Scenarios: {feature.scenario_count}")
        if feature.scenarios:
            for scenario in feature.scenarios[:2]:
                print(f"         - {scenario.name} ({scenario.test_category})")

    # Test 4: Get features by user story
    print("\n4. Features for US-001:")
    us001_features = parser.get_features_by_user_story("US-001")
    print(f"   Found {len(us001_features)} features")
    for f in us001_features:
        print(f"      {f.name}")

    # Test 5: Get scenarios by tag
    print("\n5. Scenarios with @happy-path tag:")
    happy_scenarios = parser.get_scenarios_by_tag("happy-path")
    print(f"   Found {len(happy_scenarios)} scenarios")

    # Test 6: Get all tags
    print("\n6. All unique tags:")
    tags = parser.get_all_tags()
    print(f"   Found {len(tags)} unique tags")
    print(f"   Sample: {list(tags)[:10]}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_test_documentation_parser()
