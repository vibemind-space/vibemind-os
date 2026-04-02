"""Test pipeline output formatter."""
import sys
sys.path.insert(0, ".")

from src.services.pipeline_output_formatter import PipelineOutputFormatter


def test_create_template():
    """Create and remove templates."""
    of = PipelineOutputFormatter()
    tid = of.create_template("json_output", output_format="json")
    assert tid.startswith("fmt-")

    t = of.get_template(tid)
    assert t is not None
    assert t["name"] == "json_output"
    assert t["output_format"] == "json"

    assert of.remove_template(tid) is True
    assert of.remove_template(tid) is False
    print("OK: create template")


def test_invalid_template():
    """Invalid template rejected."""
    of = PipelineOutputFormatter()
    assert of.create_template("") == ""
    assert of.create_template("x", output_format="invalid") == ""
    print("OK: invalid template")


def test_max_templates():
    """Max templates enforced."""
    of = PipelineOutputFormatter(max_templates=2)
    of.create_template("a")
    of.create_template("b")
    assert of.create_template("c") == ""
    print("OK: max templates")


def test_list_templates():
    """List templates with filter."""
    of = PipelineOutputFormatter()
    of.create_template("a", output_format="json")
    of.create_template("b", output_format="csv")
    of.create_template("c", output_format="json")

    all_t = of.list_templates()
    assert len(all_t) == 3

    json_only = of.list_templates(output_format="json")
    assert len(json_only) == 2
    print("OK: list templates")


def test_template_with_fields():
    """Template with field filtering."""
    of = PipelineOutputFormatter()
    tid = of.create_template("filtered", fields=["name", "age"])

    t = of.get_template(tid)
    assert t["fields"] == ["name", "age"]
    print("OK: template with fields")


def test_format_json():
    """Format as JSON."""
    of = PipelineOutputFormatter()
    tid = of.create_template("json_out", output_format="json")

    result = of.format_output(tid, {"name": "Alice", "age": 30})
    assert '"name": "Alice"' in result
    assert '"age": 30' in result
    print("OK: format json")


def test_format_text():
    """Format as text."""
    of = PipelineOutputFormatter()
    tid = of.create_template("text_out", output_format="text")

    result = of.format_output(tid, {"name": "Alice", "age": 30})
    assert "name: Alice" in result
    assert "age: 30" in result
    print("OK: format text")


def test_format_csv():
    """Format as CSV."""
    of = PipelineOutputFormatter()
    tid = of.create_template("csv_out", output_format="csv")

    result = of.format_output(tid, {"name": "Alice", "age": 30})
    lines = result.split("\n")
    assert "name" in lines[0]
    assert "Alice" in lines[1]
    print("OK: format csv")


def test_format_markdown():
    """Format as markdown."""
    of = PipelineOutputFormatter()
    tid = of.create_template("md_out", output_format="markdown",
                              options={"title": "Report"})

    result = of.format_output(tid, {"name": "Alice", "score": 95})
    assert "# Report" in result
    assert "**name**" in result
    print("OK: format markdown")


def test_format_summary():
    """Format as summary."""
    of = PipelineOutputFormatter()
    tid = of.create_template("sum_out", output_format="summary")

    result = of.format_output(tid, {"a": 1, "b": 2})
    assert "a=1" in result
    assert "|" in result
    print("OK: format summary")


def test_format_table():
    """Format as table."""
    of = PipelineOutputFormatter()
    tid = of.create_template("tbl_out", output_format="table")

    result = of.format_output(tid, {"name": "Alice", "age": "30"})
    assert "name" in result
    assert "Alice" in result
    assert "-" in result  # Separator line
    print("OK: format table")


def test_format_log():
    """Format as log."""
    of = PipelineOutputFormatter()
    tid = of.create_template("log_out", output_format="log",
                              options={"timestamp": "2024-01-01T00:00:00"})

    result = of.format_output(tid, {"action": "build", "status": "ok"})
    assert "[2024-01-01T00:00:00]" in result
    assert "action=build" in result
    print("OK: format log")


def test_format_with_field_filter():
    """Format filters to specified fields."""
    of = PipelineOutputFormatter()
    tid = of.create_template("filtered", output_format="json",
                              fields=["name"])

    result = of.format_output(tid, {"name": "Alice", "age": 30, "city": "NYC"})
    assert "Alice" in result
    assert "age" not in result
    assert "city" not in result
    print("OK: format with field filter")


def test_format_invalid_template():
    """Format with invalid template returns empty."""
    of = PipelineOutputFormatter()
    assert of.format_output("nonexistent", {"a": 1}) == ""
    print("OK: format invalid template")


def test_quick_format():
    """Quick format without template."""
    of = PipelineOutputFormatter()

    result = of.quick_format({"name": "Bob"}, output_format="text")
    assert "name: Bob" in result

    result = of.quick_format({"x": 1}, output_format="json")
    assert '"x": 1' in result

    assert of.quick_format({"x": 1}, output_format="invalid") == ""
    print("OK: quick format")


def test_quick_format_with_fields():
    """Quick format with field filtering."""
    of = PipelineOutputFormatter()

    result = of.quick_format({"a": 1, "b": 2, "c": 3},
                              output_format="text", fields=["a", "c"])
    assert "a: 1" in result
    assert "c: 3" in result
    assert "b:" not in result
    print("OK: quick format with fields")


def test_format_list_json():
    """Format list as JSON."""
    of = PipelineOutputFormatter()
    items = [{"name": "Alice"}, {"name": "Bob"}]

    result = of.format_list(items, output_format="json")
    assert "Alice" in result
    assert "Bob" in result
    print("OK: format list json")


def test_format_list_csv():
    """Format list as CSV."""
    of = PipelineOutputFormatter()
    items = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]

    result = of.format_list(items, output_format="csv")
    lines = result.split("\n")
    assert len(lines) == 3  # header + 2 rows
    assert "name" in lines[0]
    print("OK: format list csv")


def test_format_list_table():
    """Format list as text table."""
    of = PipelineOutputFormatter()
    items = [{"name": "Alice", "score": "95"}, {"name": "Bob", "score": "87"}]

    result = of.format_list(items, output_format="table")
    assert "name" in result
    assert "Alice" in result
    assert "-" in result
    print("OK: format list table")


def test_format_list_markdown():
    """Format list as markdown table."""
    of = PipelineOutputFormatter()
    items = [{"name": "Alice"}, {"name": "Bob"}]

    result = of.format_list(items, output_format="markdown")
    assert "| name |" in result
    assert "| --- |" in result
    assert "| Alice |" in result
    print("OK: format list markdown")


def test_format_list_text():
    """Format list as text."""
    of = PipelineOutputFormatter()
    items = [{"a": 1}, {"a": 2}]

    result = of.format_list(items, output_format="text")
    assert "Item 1" in result
    assert "Item 2" in result
    print("OK: format list text")


def test_format_list_empty():
    """Empty list returns empty."""
    of = PipelineOutputFormatter()
    assert of.format_list([], output_format="json") == ""
    print("OK: format list empty")


def test_format_list_invalid():
    """Invalid format returns empty."""
    of = PipelineOutputFormatter()
    assert of.format_list([{"a": 1}], output_format="invalid") == ""
    print("OK: format list invalid")


def test_format_list_with_fields():
    """Format list with field filtering."""
    of = PipelineOutputFormatter()
    items = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]

    result = of.format_list(items, output_format="json", fields=["name"])
    assert "Alice" in result
    assert "age" not in result
    print("OK: format list with fields")


def test_csv_separator():
    """Custom CSV separator."""
    of = PipelineOutputFormatter()
    tid = of.create_template("tsv", output_format="csv",
                              options={"separator": "\t"})

    result = of.format_output(tid, {"a": "1", "b": "2"})
    assert "\t" in result
    print("OK: csv separator")


def test_json_indent():
    """Custom JSON indent."""
    of = PipelineOutputFormatter()
    tid = of.create_template("compact", output_format="json",
                              options={"indent": 0})

    result = of.format_output(tid, {"a": 1})
    # indent=0 produces newlines but no indentation spaces
    assert '"a": 1' in result
    print("OK: json indent")


def test_callbacks():
    """Callback registration."""
    of = PipelineOutputFormatter()

    assert of.on_change("mon", lambda a, d: None) is True
    assert of.on_change("mon", lambda a, d: None) is False
    assert of.remove_callback("mon") is True
    assert of.remove_callback("mon") is False
    print("OK: callbacks")


def test_format_callback():
    """Callback fires on format."""
    of = PipelineOutputFormatter()
    tid = of.create_template("test", output_format="json")

    fired = []
    of.on_change("mon", lambda a, d: fired.append(a))

    of.format_output(tid, {"x": 1})
    assert "output_formatted" in fired
    print("OK: format callback")


def test_stats():
    """Stats are accurate."""
    of = PipelineOutputFormatter()
    tid = of.create_template("test")
    of.format_output(tid, {"a": 1})
    of.quick_format({"b": 2})

    stats = of.get_stats()
    assert stats["total_templates"] == 1
    assert stats["total_formatted"] == 2
    assert stats["current_templates"] == 1
    print("OK: stats")


def test_reset():
    """Reset clears everything."""
    of = PipelineOutputFormatter()
    of.create_template("test")

    of.reset()
    assert of.list_templates() == []
    stats = of.get_stats()
    assert stats["current_templates"] == 0
    print("OK: reset")


def main():
    print("=== Pipeline Output Formatter Tests ===\n")
    test_create_template()
    test_invalid_template()
    test_max_templates()
    test_list_templates()
    test_template_with_fields()
    test_format_json()
    test_format_text()
    test_format_csv()
    test_format_markdown()
    test_format_summary()
    test_format_table()
    test_format_log()
    test_format_with_field_filter()
    test_format_invalid_template()
    test_quick_format()
    test_quick_format_with_fields()
    test_format_list_json()
    test_format_list_csv()
    test_format_list_table()
    test_format_list_markdown()
    test_format_list_text()
    test_format_list_empty()
    test_format_list_invalid()
    test_format_list_with_fields()
    test_csv_separator()
    test_json_indent()
    test_callbacks()
    test_format_callback()
    test_stats()
    test_reset()
    print("\n=== ALL 30 TESTS PASSED ===")


if __name__ == "__main__":
    main()
