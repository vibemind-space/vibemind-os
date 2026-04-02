"""Test project template system."""
import sys
sys.path.insert(0, ".")

from src.services.project_template import (
    ProjectTemplateManager,
)


def test_builtin_templates():
    """Built-in templates are registered on init."""
    mgr = ProjectTemplateManager()
    templates = mgr.list_templates()
    assert len(templates) >= 3
    names = {t["name"] for t in templates}
    assert "python-package" in names
    assert "python-api" in names
    assert "nodejs-package" in names
    print("OK: builtin templates")


def test_register_custom():
    """Register a custom template."""
    mgr = ProjectTemplateManager()
    tid = mgr.register_template(
        name="custom-app",
        description="My custom app",
        language="python",
        category="app",
        files=[
            {"path": "{{project_name}}/main.py", "content": "# {{project_name}}"},
        ],
        variables={"author": "Me"},
        tags={"custom"},
    )

    assert tid.startswith("tpl-")
    tpl = mgr.get_template("custom-app")
    assert tpl is not None
    assert tpl["name"] == "custom-app"
    assert tpl["language"] == "python"
    assert tpl["file_count"] == 1
    assert "custom" in tpl["tags"]
    print("OK: register custom")


def test_get_nonexistent():
    """Get a template that doesn't exist returns None."""
    mgr = ProjectTemplateManager()
    assert mgr.get_template("nonexistent") is None
    print("OK: get nonexistent")


def test_list_by_language():
    """Filter templates by language."""
    mgr = ProjectTemplateManager()
    python = mgr.list_templates(language="python")
    assert all(t["language"] == "python" for t in python)
    assert len(python) >= 2
    print("OK: list by language")


def test_list_by_category():
    """Filter templates by category."""
    mgr = ProjectTemplateManager()
    libs = mgr.list_templates(category="library")
    assert all(t["category"] == "library" for t in libs)
    print("OK: list by category")


def test_list_by_tags():
    """Filter templates by tags."""
    mgr = ProjectTemplateManager()
    python_tagged = mgr.list_templates(tags={"python"})
    assert len(python_tagged) >= 2
    print("OK: list by tags")


def test_create_project():
    """Create a project from template."""
    mgr = ProjectTemplateManager()
    result = mgr.create_project(
        template_name="python-package",
        project_name="my-lib",
        variables={"author": "Dev", "description": "Cool library"},
    )

    assert result.success is True
    assert result.project_name == "my-lib"
    assert result.template_name == "python-package"
    assert len(result.files_created) > 0
    assert len(result.directories_created) > 0

    # Check variable substitution happened
    assert any("my-lib" in f for f in result.files_created)
    assert result.variables_used["author"] == "Dev"
    assert result.variables_used["project_name"] == "my-lib"
    print("OK: create project")


def test_create_nonexistent_template():
    """Create from nonexistent template fails gracefully."""
    mgr = ProjectTemplateManager()
    result = mgr.create_project("nope", "my-project")

    assert result.success is False
    assert len(result.warnings) > 0
    print("OK: create nonexistent template")


def test_dry_run():
    """Dry run doesn't increment stats."""
    mgr = ProjectTemplateManager()
    before = mgr.get_stats()["total_projects_created"]

    result = mgr.create_project(
        "python-package", "test-proj", dry_run=True
    )
    assert result.success is True

    after = mgr.get_stats()["total_projects_created"]
    assert after == before
    print("OK: dry run")


def test_preview_project():
    """Preview shows file content with substitutions."""
    mgr = ProjectTemplateManager()
    preview = mgr.preview_project(
        "python-package",
        "my-lib",
        variables={"author": "TestDev", "description": "Preview test"},
    )

    assert preview is not None
    assert preview["project_name"] == "my-lib"

    # Check file content substitution
    main_file = next(
        (f for f in preview["files"] if "main.py" in f["path"]), None
    )
    assert main_file is not None
    assert "my-lib" in main_file["content"]

    # Dependencies are included
    assert len(preview["dependencies"]) > 0
    print("OK: preview project")


def test_preview_nonexistent():
    """Preview nonexistent template returns None."""
    mgr = ProjectTemplateManager()
    assert mgr.preview_project("nope", "test") is None
    print("OK: preview nonexistent")


def test_get_template_variables():
    """Get required template variables."""
    mgr = ProjectTemplateManager()
    vars_ = mgr.get_template_variables("python-package")

    assert vars_ is not None
    assert "author" in vars_
    assert "description" in vars_

    assert mgr.get_template_variables("nope") is None
    print("OK: get template variables")


def test_delete_template():
    """Delete a template."""
    mgr = ProjectTemplateManager()
    mgr.register_template("temp", files=[{"path": "f.py", "content": ""}])

    assert mgr.delete_template("temp") is True
    assert mgr.get_template("temp") is None
    assert mgr.delete_template("temp") is False
    print("OK: delete template")


def test_variable_substitution():
    """Variable placeholders are replaced throughout."""
    mgr = ProjectTemplateManager()
    mgr.register_template(
        name="var-test",
        files=[
            {
                "path": "{{project_name}}/{{module}}.py",
                "content": "# {{project_name}} - {{module}} by {{author}}\nversion = '{{version}}'",
            },
        ],
        variables={"module": "core", "author": "", "version": "1.0"},
    )

    preview = mgr.preview_project(
        "var-test", "myapp",
        variables={"module": "engine", "author": "Dev", "version": "2.0"},
    )

    assert preview is not None
    f = preview["files"][0]
    assert f["path"] == "myapp/engine.py"
    assert "myapp - engine by Dev" in f["content"]
    assert "version = '2.0'" in f["content"]
    print("OK: variable substitution")


def test_missing_variable_warning():
    """Warn about missing required variables."""
    mgr = ProjectTemplateManager()
    mgr.register_template(
        name="needs-vars",
        files=[{"path": "f.py", "content": ""}],
        variables={"required_var": ""},  # No default = required
    )

    result = mgr.create_project("needs-vars", "test")
    assert any("required_var" in w for w in result.warnings)
    print("OK: missing variable warning")


def test_stats():
    """Stats are accurate."""
    mgr = ProjectTemplateManager()
    builtin_count = len(mgr.list_templates())

    mgr.register_template("extra", files=[{"path": "f.py", "content": ""}])
    mgr.create_project("extra", "proj1")
    mgr.create_project("extra", "proj2")

    stats = mgr.get_stats()
    assert stats["total_templates"] == builtin_count + 1
    assert stats["total_projects_created"] == 2
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    mgr = ProjectTemplateManager()
    mgr.create_project("python-package", "test")
    mgr.reset()

    assert mgr.list_templates() == []
    stats = mgr.get_stats()
    assert stats["total_templates"] == 0
    assert stats["total_projects_created"] == 0
    print("OK: reset")


def main():
    print("=== Project Template Tests ===\n")
    test_builtin_templates()
    test_register_custom()
    test_get_nonexistent()
    test_list_by_language()
    test_list_by_category()
    test_list_by_tags()
    test_create_project()
    test_create_nonexistent_template()
    test_dry_run()
    test_preview_project()
    test_preview_nonexistent()
    test_get_template_variables()
    test_delete_template()
    test_variable_substitution()
    test_missing_variable_warning()
    test_stats()
    test_reset()
    print("\n=== ALL 17 TESTS PASSED ===")


if __name__ == "__main__":
    main()
