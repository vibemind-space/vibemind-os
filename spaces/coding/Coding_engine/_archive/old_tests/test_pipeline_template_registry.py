"""Test pipeline template registry."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_template_registry import PipelineTemplateRegistry


BASIC_STEPS = [
    {"name": "build", "duration": 10.0, "dependencies": []},
    {"name": "test", "duration": 5.0, "dependencies": ["build"]},
    {"name": "deploy", "duration": 3.0, "dependencies": ["test"]},
]


def test_create():
    """Create a template."""
    reg = PipelineTemplateRegistry()
    tid = reg.create("CI Pipeline", steps=BASIC_STEPS, description="Basic CI",
                      category="ci", author="admin", tags={"ci", "default"})
    assert tid.startswith("tmpl-")

    t = reg.get(tid)
    assert t is not None
    assert t["name"] == "CI Pipeline"
    assert t["version"] == 1
    assert t["step_count"] == 3
    assert t["category"] == "ci"
    print("OK: create")


def test_versioning():
    """Same name bumps version."""
    reg = PipelineTemplateRegistry()
    t1 = reg.create("Deploy", steps=BASIC_STEPS)
    t2 = reg.create("Deploy", steps=BASIC_STEPS)

    assert reg.get(t1)["version"] == 1
    assert reg.get(t2)["version"] == 2
    print("OK: versioning")


def test_get_by_name():
    """Get template by name."""
    reg = PipelineTemplateRegistry()
    reg.create("Pipeline", steps=BASIC_STEPS)
    reg.create("Pipeline", steps=BASIC_STEPS)

    latest = reg.get_by_name("Pipeline")
    assert latest is not None
    assert latest["version"] == 2

    v1 = reg.get_by_name("Pipeline", version=1)
    assert v1 is not None
    assert v1["version"] == 1

    assert reg.get_by_name("nonexistent") is None
    assert reg.get_by_name("Pipeline", version=99) is None
    print("OK: get by name")


def test_update():
    """Update a template."""
    reg = PipelineTemplateRegistry()
    tid = reg.create("Test", steps=BASIC_STEPS, description="old")

    assert reg.update(tid, description="new", tags={"updated"}) is True
    t = reg.get(tid)
    assert "updated" in t["tags"]

    assert reg.update("fake", description="x") is False
    print("OK: update")


def test_delete():
    """Delete a template."""
    reg = PipelineTemplateRegistry()
    tid = reg.create("Temp", steps=BASIC_STEPS)
    assert reg.delete(tid) is True
    assert reg.get(tid) is None
    assert reg.delete(tid) is False
    print("OK: delete")


def test_list_templates():
    """List templates with filters."""
    reg = PipelineTemplateRegistry()
    reg.create("Alpha", steps=BASIC_STEPS, category="ci", author="admin",
               tags={"ci"})
    reg.create("Beta", steps=BASIC_STEPS, category="cd", author="dev")

    all_t = reg.list_templates()
    assert len(all_t) == 2

    ci = reg.list_templates(category="ci")
    assert len(ci) == 1

    admin = reg.list_templates(author="admin")
    assert len(admin) == 1

    tagged = reg.list_templates(tags={"ci"})
    assert len(tagged) == 1

    limited = reg.list_templates(limit=1)
    assert len(limited) == 1
    print("OK: list templates")


def test_list_categories():
    """List categories."""
    reg = PipelineTemplateRegistry()
    reg.create("A", steps=BASIC_STEPS, category="ci")
    reg.create("B", steps=BASIC_STEPS, category="cd")
    reg.create("C", steps=BASIC_STEPS, category="ci")

    cats = reg.list_categories()
    assert cats["ci"] == 2
    assert cats["cd"] == 1
    print("OK: list categories")


def test_list_names():
    """List unique template names."""
    reg = PipelineTemplateRegistry()
    reg.create("Beta", steps=BASIC_STEPS)
    reg.create("Alpha", steps=BASIC_STEPS)
    reg.create("Beta", steps=BASIC_STEPS)  # v2

    names = reg.list_names()
    assert names == ["Alpha", "Beta"]
    print("OK: list names")


def test_search():
    """Search templates."""
    reg = PipelineTemplateRegistry()
    reg.create("CI Pipeline", steps=BASIC_STEPS, description="Build and test")
    reg.create("Deploy Flow", steps=BASIC_STEPS, description="Deploy to prod")

    results = reg.search("pipeline")
    assert len(results) == 1
    assert results[0]["name"] == "CI Pipeline"

    results = reg.search("deploy")
    assert len(results) == 1
    print("OK: search")


def test_instantiate():
    """Instantiate with parameter substitution."""
    reg = PipelineTemplateRegistry()
    steps = [
        {"name": "build-${env}", "duration": 10.0, "dependencies": []},
        {"name": "deploy-${env}", "duration": 5.0, "dependencies": ["build-${env}"]},
    ]
    tid = reg.create("Parametric", steps=steps,
                      parameters={"env": "staging"})

    # Use defaults
    result = reg.instantiate(tid)
    assert result is not None
    assert result[0]["name"] == "build-staging"

    # Override params
    result = reg.instantiate(tid, params={"env": "prod"})
    assert result[0]["name"] == "build-prod"
    assert result[1]["dependencies"] == ["build-prod"]

    # Usage count incremented
    t = reg.get(tid)
    assert t["usage_count"] == 2

    assert reg.instantiate("fake") is None
    print("OK: instantiate")


def test_validate_valid():
    """Validate a valid template."""
    reg = PipelineTemplateRegistry()
    tid = reg.create("Valid", steps=BASIC_STEPS, description="Good template")

    result = reg.validate(tid)
    assert result["valid"] is True
    assert result["step_count"] == 3
    print("OK: validate valid")


def test_validate_invalid():
    """Validate an invalid template."""
    reg = PipelineTemplateRegistry()

    # Empty steps
    tid = reg.create("Empty", steps=[])
    result = reg.validate(tid)
    assert result["valid"] is False
    assert any("no steps" in e for e in result["errors"])

    # Missing dependency
    bad_steps = [
        {"name": "build", "dependencies": ["nonexistent"]},
    ]
    tid2 = reg.create("Bad", steps=bad_steps)
    result = reg.validate(tid2)
    assert result["valid"] is False
    assert any("unknown" in e for e in result["errors"])

    # Duplicate names
    dup_steps = [
        {"name": "build", "dependencies": []},
        {"name": "build", "dependencies": []},
    ]
    tid3 = reg.create("Dup", steps=dup_steps)
    result = reg.validate(tid3)
    assert result["valid"] is False

    # Nonexistent
    result = reg.validate("fake")
    assert result["valid"] is False
    print("OK: validate invalid")


def test_export_import():
    """Export and import a template."""
    reg = PipelineTemplateRegistry()
    tid = reg.create("Export Me", steps=BASIC_STEPS, category="ci",
                      description="Exportable", tags={"portable"})

    exported = reg.export_template(tid)
    assert exported is not None
    assert exported["name"] == "Export Me"

    # Import into fresh registry
    reg2 = PipelineTemplateRegistry()
    new_tid = reg2.import_template(exported)
    assert new_tid is not None

    t = reg2.get(new_tid)
    assert t["name"] == "Export Me"
    assert t["step_count"] == 3

    # Invalid import
    assert reg2.import_template({}) is None
    assert reg2.import_template({"name": "x"}) is None  # No steps

    assert reg.export_template("fake") is None
    print("OK: export import")


def test_prune():
    """Prune when over max."""
    reg = PipelineTemplateRegistry(max_templates=3)
    for i in range(6):
        reg.create(f"T-{i}", steps=BASIC_STEPS)

    assert len(reg._templates) <= 3
    print("OK: prune")


def test_stats():
    """Stats are accurate."""
    reg = PipelineTemplateRegistry()
    tid = reg.create("A", steps=BASIC_STEPS, category="ci")
    reg.create("B", steps=BASIC_STEPS, category="cd")
    reg.instantiate(tid)
    reg.delete(tid)

    stats = reg.get_stats()
    assert stats["total_created"] == 2
    assert stats["total_instantiated"] == 1
    assert stats["total_deleted"] == 1
    assert stats["total_templates"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    reg = PipelineTemplateRegistry()
    reg.create("A", steps=BASIC_STEPS)

    reg.reset()
    assert reg.list_templates() == []
    assert reg.list_names() == []
    stats = reg.get_stats()
    assert stats["total_templates"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Template Registry Tests ===\n")
    test_create()
    test_versioning()
    test_get_by_name()
    test_update()
    test_delete()
    test_list_templates()
    test_list_categories()
    test_list_names()
    test_search()
    test_instantiate()
    test_validate_valid()
    test_validate_invalid()
    test_export_import()
    test_prune()
    test_stats()
    test_reset()
    print("\n=== ALL 16 TESTS PASSED ===")


if __name__ == "__main__":
    main()
