"""Test pipeline template engine."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_template_engine import PipelineTemplateEngine


def test_create_template():
    """Create and retrieve template."""
    te = PipelineTemplateEngine()
    tid = te.create_template("build_pipeline", description="Standard build",
                             stages=["lint", "test", "build"],
                             parameters={"env": "string", "parallel": "bool"},
                             defaults={"env": "dev", "parallel": False},
                             tags=["ci"])
    assert tid.startswith("tmpl-")

    t = te.get_template(tid)
    assert t is not None
    assert t["name"] == "build_pipeline"
    assert t["description"] == "Standard build"
    assert len(t["stages"]) == 3
    assert t["status"] == "draft"
    assert t["version"] == 1

    assert te.remove_template(tid) is True
    assert te.remove_template(tid) is False
    print("OK: create template")


def test_invalid_template():
    """Invalid template rejected."""
    te = PipelineTemplateEngine()
    assert te.create_template("") == ""
    print("OK: invalid template")


def test_max_templates():
    """Max templates enforced."""
    te = PipelineTemplateEngine(max_templates=2)
    te.create_template("a")
    te.create_template("b")
    assert te.create_template("c") == ""
    print("OK: max templates")


def test_publish_template():
    """Publish a template."""
    te = PipelineTemplateEngine()
    tid = te.create_template("t")

    assert te.publish_template(tid) is True
    assert te.get_template(tid)["status"] == "published"
    assert te.publish_template(tid) is False  # not draft
    print("OK: publish template")


def test_archive_template():
    """Archive a template."""
    te = PipelineTemplateEngine()
    tid = te.create_template("t")

    assert te.archive_template(tid) is True
    assert te.get_template(tid)["status"] == "archived"
    assert te.archive_template(tid) is False
    print("OK: archive template")


def test_update_template():
    """Update a draft template."""
    te = PipelineTemplateEngine()
    tid = te.create_template("t", description="old")

    assert te.update_template(tid, description="new",
                              stages=["a", "b"]) is True
    t = te.get_template(tid)
    assert t["description"] == "new"
    assert t["stages"] == ["a", "b"]
    assert t["version"] == 2

    # Can't update published
    te.publish_template(tid)
    assert te.update_template(tid, description="x") is False
    print("OK: update template")


def test_instantiate():
    """Instantiate a published template."""
    te = PipelineTemplateEngine()
    tid = te.create_template("build",
                             defaults={"env": "dev", "workers": 4})
    te.publish_template(tid)

    iid = te.instantiate(tid, parameters={"env": "prod"})
    assert iid.startswith("inst-")

    i = te.get_instance(iid)
    assert i is not None
    assert i["template_id"] == tid
    assert i["template_name"] == "build"
    assert i["parameters"]["env"] == "prod"  # overridden
    assert i["parameters"]["workers"] == 4   # from defaults
    assert i["status"] == "created"
    print("OK: instantiate")


def test_cant_instantiate_draft():
    """Can't instantiate a draft template."""
    te = PipelineTemplateEngine()
    tid = te.create_template("t")  # draft
    assert te.instantiate(tid) == ""
    print("OK: cant instantiate draft")


def test_instance_lifecycle():
    """Instance lifecycle: created -> running -> completed."""
    te = PipelineTemplateEngine()
    tid = te.create_template("t")
    te.publish_template(tid)
    iid = te.instantiate(tid)

    assert te.start_instance(iid) is True
    assert te.get_instance(iid)["status"] == "running"
    assert te.start_instance(iid) is False

    assert te.complete_instance(iid, result={"output": "ok"}) is True
    assert te.get_instance(iid)["status"] == "completed"
    assert te.get_instance(iid)["result"]["output"] == "ok"
    assert te.complete_instance(iid) is False
    print("OK: instance lifecycle")


def test_fail_instance():
    """Fail an instance."""
    te = PipelineTemplateEngine()
    tid = te.create_template("t")
    te.publish_template(tid)
    iid = te.instantiate(tid)
    te.start_instance(iid)

    assert te.fail_instance(iid, error="OOM") is True
    assert te.get_instance(iid)["status"] == "failed"
    assert te.get_instance(iid)["result"]["error"] == "OOM"
    assert te.fail_instance(iid) is False
    print("OK: fail instance")


def test_cancel_instance():
    """Cancel an instance."""
    te = PipelineTemplateEngine()
    tid = te.create_template("t")
    te.publish_template(tid)
    iid = te.instantiate(tid)

    assert te.cancel_instance(iid) is True
    assert te.get_instance(iid)["status"] == "cancelled"
    assert te.cancel_instance(iid) is False
    print("OK: cancel instance")


def test_remove_instance():
    """Remove an instance."""
    te = PipelineTemplateEngine()
    tid = te.create_template("t")
    te.publish_template(tid)
    iid = te.instantiate(tid)

    assert te.remove_instance(iid) is True
    assert te.remove_instance(iid) is False
    print("OK: remove instance")


def test_search_templates():
    """Search templates with filters."""
    te = PipelineTemplateEngine()
    te.create_template("a", tags=["ci"])
    t2 = te.create_template("b")
    te.publish_template(t2)

    all_t = te.search_templates()
    assert len(all_t) == 2

    by_status = te.search_templates(status="published")
    assert len(by_status) == 1

    by_tag = te.search_templates(tag="ci")
    assert len(by_tag) == 1
    print("OK: search templates")


def test_list_instances():
    """List instances with filters."""
    te = PipelineTemplateEngine()
    t1 = te.create_template("a")
    te.publish_template(t1)
    t2 = te.create_template("b")
    te.publish_template(t2)

    i1 = te.instantiate(t1)
    i2 = te.instantiate(t2)
    te.start_instance(i1)

    all_i = te.list_instances()
    assert len(all_i) == 2

    by_tmpl = te.list_instances(template_id=t1)
    assert len(by_tmpl) == 1

    by_status = te.list_instances(status="running")
    assert len(by_status) == 1
    print("OK: list instances")


def test_template_usage():
    """Get most-used templates."""
    te = PipelineTemplateEngine()
    t1 = te.create_template("popular")
    te.publish_template(t1)
    t2 = te.create_template("rare")
    te.publish_template(t2)

    te.instantiate(t1)
    te.instantiate(t1)
    te.instantiate(t1)
    te.instantiate(t2)

    usage = te.get_template_usage()
    assert len(usage) == 2
    assert usage[0]["name"] == "popular"
    assert usage[0]["instance_count"] == 3
    print("OK: template usage")


def test_success_rate():
    """Get instance success rate."""
    te = PipelineTemplateEngine()
    tid = te.create_template("t")
    te.publish_template(tid)

    i1 = te.instantiate(tid)
    te.start_instance(i1)
    te.complete_instance(i1)

    i2 = te.instantiate(tid)
    te.start_instance(i2)
    te.fail_instance(i2)

    rate = te.get_success_rate()
    assert rate["total"] == 2
    assert rate["completed"] == 1
    assert rate["failed"] == 1
    assert rate["success_rate"] == 50.0

    rate_tmpl = te.get_success_rate(template_id=tid)
    assert rate_tmpl["total"] == 2
    print("OK: success rate")


def test_template_callback():
    """Callback fires on template create."""
    te = PipelineTemplateEngine()
    fired = []
    te.on_change("mon", lambda a, d: fired.append(a))

    te.create_template("t")
    assert "template_created" in fired
    print("OK: template callback")


def test_instance_callback():
    """Callback fires on instantiate."""
    te = PipelineTemplateEngine()
    fired = []
    te.on_change("mon", lambda a, d: fired.append(a))

    tid = te.create_template("t")
    te.publish_template(tid)
    te.instantiate(tid)
    assert "instance_created" in fired
    print("OK: instance callback")


def test_callbacks():
    """Callback registration."""
    te = PipelineTemplateEngine()
    assert te.on_change("mon", lambda a, d: None) is True
    assert te.on_change("mon", lambda a, d: None) is False
    assert te.remove_callback("mon") is True
    assert te.remove_callback("mon") is False
    print("OK: callbacks")


def test_stats():
    """Stats are accurate."""
    te = PipelineTemplateEngine()
    t1 = te.create_template("a")
    te.publish_template(t1)
    t2 = te.create_template("b")
    te.archive_template(t2)

    i1 = te.instantiate(t1)
    te.start_instance(i1)
    te.complete_instance(i1)

    i2 = te.instantiate(t1)
    te.start_instance(i2)
    te.fail_instance(i2)

    stats = te.get_stats()
    assert stats["total_templates_created"] == 2
    assert stats["total_published"] == 1
    assert stats["total_archived"] == 1
    assert stats["total_instances_created"] == 2
    assert stats["total_completed"] == 1
    assert stats["total_failed"] == 1
    assert stats["current_templates"] == 2
    assert stats["published_templates"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    te = PipelineTemplateEngine()
    te.create_template("t")
    tid = te.create_template("t2")
    te.publish_template(tid)
    te.instantiate(tid)

    te.reset()
    assert te.search_templates() == []
    assert te.list_instances() == []
    stats = te.get_stats()
    assert stats["current_templates"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Template Engine Tests ===\n")
    test_create_template()
    test_invalid_template()
    test_max_templates()
    test_publish_template()
    test_archive_template()
    test_update_template()
    test_instantiate()
    test_cant_instantiate_draft()
    test_instance_lifecycle()
    test_fail_instance()
    test_cancel_instance()
    test_remove_instance()
    test_search_templates()
    test_list_instances()
    test_template_usage()
    test_success_rate()
    test_template_callback()
    test_instance_callback()
    test_callbacks()
    test_stats()
    test_reset()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
