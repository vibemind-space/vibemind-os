"""
Phase 30 Dry-Run: Test SchemaDiscoverer + TaskMapper + TaskEnricher
against real WhatsApp project data.

Usage:
    python scripts/dry_run_phase30.py [--with-llm]

Without --with-llm: tests heuristic fallback only (no API key needed).
With --with-llm: uses Anthropic API for schema discovery + task mapping.
"""

import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from src.autogen.schema_discoverer import SchemaDiscoverer
from src.autogen.task_enricher import TaskEnricher
from src.autogen.task_mapper import TaskMapper


PROJECT_PATH = Path(
    r"C:\Users\User\Desktop\Coding_engine\Data\all_services"
    r"\whatsapp-messaging-service_20260211_025459"
)


class FakeTaskList:
    """Wraps a list of tasks with .tasks attribute."""
    def __init__(self, tasks, epic_id="DRY-RUN"):
        self.tasks = tasks
        self.epic_id = epic_id


class FakeTask:
    """Minimal task object for dry-run."""
    def __init__(self, data: dict):
        self.id = data.get("id", "")
        self.title = data.get("title", "")
        self.type = data.get("task_type", "development")
        self.description = data.get("description", "")
        self.acceptance_criteria = data.get("acceptance_criteria", [])
        self.parent_requirement_id = data.get("parent_requirement_id", "")
        self.parent_user_story_id = data.get("parent_user_story_id", "")
        self.parent_entity_id = data.get("parent_entity_id", "")
        self.parent_api_resource = data.get("parent_api_resource", "")
        self.parent_feature_id = data.get("parent_feature_id", "")
        self.epic_id = data.get("parent_feature_id", "UNKNOWN")
        self.status = data.get("status", "todo")
        self.dependencies = data.get("depends_on", [])
        self.estimated_minutes = data.get("estimated_hours", 0) * 60
        self.output_files = []
        self.phase = ""
        # Enrichment fields
        self.related_requirements = []
        self.related_user_stories = []
        self.enrichment_context = {}
        self.success_criteria = []


def load_tasks():
    """Load tasks from the real task_list.json."""
    task_file = PROJECT_PATH / "tasks" / "task_list.json"
    data = json.loads(task_file.read_text(encoding="utf-8"))
    tasks = []
    for feat_id, feat_tasks in data.get("features", {}).items():
        for t in feat_tasks:
            tasks.append(FakeTask(t))
    return tasks


def print_section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def main():
    use_llm = "--with-llm" in sys.argv
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") if use_llm else ""

    print_section("Phase 30 Dry-Run")
    print(f"Project: {PROJECT_PATH.name}")
    print(f"LLM mode: {'ON (Anthropic API)' if use_llm else 'OFF (heuristic only)'}")

    # ── Step 1: Schema Discovery ──────────────────────────────────────
    print_section("Step 1: Schema Discovery")
    discoverer = SchemaDiscoverer(PROJECT_PATH, api_key=api_key)
    schema = discoverer.discover(force=True)

    print(f"Project name: {schema.project_name}")
    print(f"Language: {schema.language}")
    print(f"Requirement ID pattern: {schema.requirement_id_pattern}")
    print(f"Sources discovered: {len(schema.sources)}")
    for name, source in schema.sources.items():
        print(f"  {name}: file={source.file}, format={source.format}, "
              f"purpose={source.purpose}, id_pattern={source.id_pattern}")

    # ── Step 2: Load Tasks ─────────────────────────────────────────────
    print_section("Step 2: Load Tasks")
    tasks = load_tasks()
    print(f"Loaded {len(tasks)} tasks")
    from collections import Counter
    type_counts = Counter(t.type for t in tasks)
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")

    # ── Step 3: Task Mapping ───────────────────────────────────────────
    print_section("Step 3: Task Mapping")
    mapper = TaskMapper(PROJECT_PATH, schema, api_key=api_key)
    mapping_result = mapper.map_tasks(tasks)

    print(f"LLM used: {mapping_result.llm_used}")
    if mapping_result.error:
        print(f"Error: {mapping_result.error}")
    print(f"Mappings produced: {len(mapping_result.mappings)}")

    if mapping_result.mappings:
        # Show sample mappings
        for task_id, m in list(mapping_result.mappings.items())[:5]:
            print(f"\n  {task_id}: inferred_type={m.inferred_type}")
            if m.requirement_ids:
                print(f"    requirements: {m.requirement_ids[:3]}")
            if m.user_story_ids:
                print(f"    user_stories: {m.user_story_ids[:3]}")
            if m.screen_ids:
                print(f"    screens: {m.screen_ids[:3]}")
            if m.component_ids:
                print(f"    components: {m.component_ids[:3]}")
            if m.feature_files:
                print(f"    features: {m.feature_files[:3]}")

        # Stats
        types_inferred = Counter(m.inferred_type for m in mapping_result.mappings.values() if m.inferred_type)
        print(f"\n  Inferred type distribution:")
        for t, c in types_inferred.most_common():
            print(f"    {t}: {c}")

        has_reqs = sum(1 for m in mapping_result.mappings.values() if m.requirement_ids)
        has_stories = sum(1 for m in mapping_result.mappings.values() if m.user_story_ids)
        has_screens = sum(1 for m in mapping_result.mappings.values() if m.screen_ids)
        has_comps = sum(1 for m in mapping_result.mappings.values() if m.component_ids)
        has_features = sum(1 for m in mapping_result.mappings.values() if m.feature_files)
        total = len(mapping_result.mappings)
        print(f"\n  Coverage:")
        print(f"    requirements: {has_reqs}/{total} ({has_reqs*100//total}%)")
        print(f"    user_stories: {has_stories}/{total} ({has_stories*100//total}%)")
        print(f"    screens: {has_screens}/{total} ({has_screens*100//total}%)")
        print(f"    components: {has_comps}/{total} ({has_comps*100//total}%)")
        print(f"    feature_files: {has_features}/{total} ({has_features*100//total}%)")

    # ── Step 4: Task Enrichment ────────────────────────────────────────
    print_section("Step 4: Task Enrichment")
    enricher = TaskEnricher(PROJECT_PATH, task_mapping=mapping_result)
    task_list = FakeTaskList(tasks)
    enricher.enrich_all(task_list)
    stats = enricher.stats

    print(f"\nEnrichment stats:")
    print(f"  total_tasks: {stats.total_tasks}")
    print(f"  with_requirements: {stats.tasks_with_requirements}")
    print(f"  with_user_stories: {stats.tasks_with_user_stories}")
    print(f"  with_diagrams: {stats.tasks_with_diagrams}")
    print(f"  with_dtos: {stats.tasks_with_dtos}")
    print(f"  with_test_scenarios: {stats.tasks_with_test_scenarios}")
    print(f"  with_component_specs: {stats.tasks_with_component_specs}")
    print(f"  with_screen_specs: {stats.tasks_with_screen_specs}")
    print(f"  with_accessibility: {stats.tasks_with_accessibility}")
    print(f"  with_routes: {stats.tasks_with_routes}")
    print(f"  with_design_tokens: {stats.tasks_with_design_tokens}")
    print(f"  with_warnings: {stats.tasks_with_warnings}")
    print(f"  with_success_criteria: {stats.tasks_with_success_criteria}")

    # Per-task details
    enriched_count = 0
    has_context = 0
    has_criteria = 0
    has_reqs = 0
    has_stories = 0

    for task in tasks:
        if task.enrichment_context:
            has_context += 1
        if task.success_criteria:
            has_criteria += 1
        if task.related_requirements:
            has_reqs += 1
            enriched_count += 1
        if task.related_user_stories:
            has_stories += 1

    print(f"\n  Tasks with related_requirements: {has_reqs}/{len(tasks)}")
    print(f"  Tasks with related_user_stories: {has_stories}/{len(tasks)}")
    print(f"  Tasks with enrichment_context: {has_context}/{len(tasks)}")
    print(f"  Tasks with success_criteria: {has_criteria}/{len(tasks)}")

    # Show first enriched task details
    print_section("Sample Enriched Task")
    for task in tasks[:3]:
        print(f"\n  {task.id}: {task.title}")
        print(f"    type: {task.type}")
        ctx = task.enrichment_context or {}
        if ctx.get("inferred_type"):
            print(f"    inferred_type: {ctx['inferred_type']}")
        if task.related_requirements:
            print(f"    requirements: {task.related_requirements[:3]}")
        if task.related_user_stories:
            print(f"    user_stories: [{len(task.related_user_stories)} stories]")
        ctx_keys = [k for k in ctx if k != "inferred_type"]
        if ctx_keys:
            print(f"    context_keys: {ctx_keys}")
            # Show context size
            total_chars = sum(len(str(v)) for k, v in ctx.items() if k != "inferred_type")
            print(f"    context_total_chars: {total_chars}")
        if task.success_criteria:
            print(f"    success_criteria: {len(task.success_criteria)} items")
        if not ctx_keys and not task.related_requirements:
            print(f"    (no enrichment - needs LLM mapping)")

    print_section("DONE")


if __name__ == "__main__":
    main()
