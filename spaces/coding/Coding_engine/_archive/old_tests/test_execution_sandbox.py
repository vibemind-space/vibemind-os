"""Test execution sandbox for generated code testing."""
import sys
import os
sys.path.insert(0, ".")

from src.services.execution_sandbox import (
    ExecutionSandbox,
    ExecutionStatus,
    Language,
)


def test_run_python():
    """Run Python code in sandbox."""
    sb = ExecutionSandbox()
    result = sb.run_python("print('Hello from sandbox')")

    assert result.success is True
    assert result.exit_code == 0
    assert "Hello from sandbox" in result.stdout
    assert result.language == "python"
    assert result.duration_ms > 0
    print("OK: run python")


def test_run_python_error():
    """Python code with error returns failure."""
    sb = ExecutionSandbox()
    result = sb.run_python("raise ValueError('test error')")

    assert result.success is False
    assert result.exit_code != 0
    assert "ValueError" in result.stderr
    assert result.status == ExecutionStatus.FAILED
    print("OK: run python error")


def test_run_python_syntax_error():
    """Python syntax error is captured."""
    sb = ExecutionSandbox()
    result = sb.run_python("def broken(")

    assert result.success is False
    assert "SyntaxError" in result.stderr
    print("OK: run python syntax error")


def test_run_python_with_imports():
    """Python code with standard library imports."""
    sb = ExecutionSandbox()
    result = sb.run_python(
        "import json\n"
        "data = {'key': 'value', 'num': 42}\n"
        "print(json.dumps(data, sort_keys=True))"
    )

    assert result.success is True
    assert '"key": "value"' in result.stdout
    assert '"num": 42' in result.stdout
    print("OK: run python with imports")


def test_timeout():
    """Long-running code times out."""
    sb = ExecutionSandbox(default_timeout=1.0)
    result = sb.run_python("import time; time.sleep(10)")

    assert result.timed_out is True
    assert result.status == ExecutionStatus.TIMEOUT
    print("OK: timeout")


def test_run_shell():
    """Run shell command."""
    sb = ExecutionSandbox()
    result = sb.run_shell("echo hello world")

    assert result.success is True
    assert "hello world" in result.stdout
    assert result.language == "shell"
    print("OK: run shell")


def test_run_command():
    """Run arbitrary command."""
    sb = ExecutionSandbox()
    result = sb.run_command(
        ["python", "-c", "import sys; print(sys.version_info[:2])"],
        language=Language.PYTHON,
    )

    assert result.success is True
    assert "(" in result.stdout  # Should contain version tuple
    print("OK: run command")


def test_command_not_found():
    """Nonexistent command returns error."""
    sb = ExecutionSandbox()
    result = sb.run_command(["nonexistent_program_xyz"])

    assert result.status == ExecutionStatus.ERROR
    assert "not found" in result.stderr.lower() or "not found" in result.stderr
    print("OK: command not found")


def test_execution_result_to_dict():
    """ExecutionResult serializes properly."""
    sb = ExecutionSandbox()
    result = sb.run_python("print(42)")

    d = result.to_dict()
    assert d["status"] == "success"
    assert d["exit_code"] == 0
    assert d["success"] is True
    assert "execution_id" in d
    assert "duration_ms" in d
    print("OK: execution result to dict")


def test_write_and_read_file():
    """Write and read files in sandbox."""
    sb = ExecutionSandbox()
    path = sb.write_file("test_data.txt", "Hello sandbox")

    content = sb.read_file("test_data.txt")
    assert content == "Hello sandbox"

    # Nonexistent file
    assert sb.read_file("nonexistent.txt") is None

    # Cleanup
    sb.cleanup()
    assert sb.read_file("test_data.txt") is None
    print("OK: write and read file")


def test_write_and_run():
    """Write a file then execute it."""
    sb = ExecutionSandbox()
    sb.write_file("calculator.py", "result = 2 + 3\nprint(f'Result: {result}')")

    result = sb.run_python_file(str(sb.work_dir / "calculator.py"))
    assert result.success is True
    assert "Result: 5" in result.stdout

    sb.cleanup()
    print("OK: write and run")


def test_list_files():
    """List files in sandbox."""
    sb = ExecutionSandbox()
    sb.write_file("a.py", "# file a")
    sb.write_file("b.py", "# file b")
    sb.write_file("sub/c.py", "# file c")

    files = sb.list_files()
    assert len(files) >= 3

    py_files = sb.list_files("*.py")
    assert len(py_files) >= 2

    sb.cleanup()
    print("OK: list files")


def test_env_variables():
    """Environment variables are passed to execution."""
    sb = ExecutionSandbox()
    result = sb.run_python(
        "import os; print(os.environ.get('TEST_VAR', 'not set'))",
        env={"TEST_VAR": "sandbox_value"},
    )

    assert result.success is True
    assert "sandbox_value" in result.stdout
    print("OK: env variables")


def test_execution_history():
    """Execution history is tracked."""
    sb = ExecutionSandbox()
    sb.run_python("print('one')")
    sb.run_python("print('two')")
    sb.run_python("raise Exception('three')")

    history = sb.get_history()
    assert len(history) == 3
    assert history[0]["status"] == "failed"  # Most recent first
    assert history[1]["status"] == "success"
    assert history[2]["status"] == "success"

    # Filter by status
    failures = sb.get_history(status="failed")
    assert len(failures) == 1

    # Limit
    limited = sb.get_history(limit=1)
    assert len(limited) == 1
    print("OK: execution history")


def test_get_result():
    """Look up specific execution result."""
    sb = ExecutionSandbox()
    result = sb.run_python("print('lookup')")

    fetched = sb.get_result(result.execution_id)
    assert fetched is not None
    assert fetched["execution_id"] == result.execution_id
    assert fetched["success"] is True

    # Nonexistent
    assert sb.get_result("exec-nonexistent") is None
    print("OK: get result")


def test_stats():
    """Sandbox stats are accurate."""
    sb = ExecutionSandbox()
    sb.run_python("print('ok')")
    sb.run_python("print('ok2')")
    sb.run_python("raise Exception('fail')")

    stats = sb.get_stats()
    assert stats["total_executions"] == 3
    assert stats["total_successes"] == 2
    assert stats["total_failures"] == 1
    assert stats["total_timeouts"] == 0
    assert stats["success_rate"] == round(2/3 * 100, 1)
    print("OK: stats")


def test_metadata():
    """Execution carries metadata."""
    sb = ExecutionSandbox()
    result = sb.run_python(
        "print('meta')",
        metadata={"task_id": "build-123", "agent": "Builder"},
    )

    info = sb.get_result(result.execution_id)
    assert info["metadata"]["task_id"] == "build-123"
    assert info["metadata"]["agent"] == "Builder"
    print("OK: metadata")


def test_run_tests_generic():
    """Run tests with generic parser."""
    sb = ExecutionSandbox()
    sb.write_file("simple_tests.py", (
        "print('OK: test_one')\n"
        "print('OK: test_two')\n"
        "print('FAIL: test_three')\n"
        "print('OK: test_four')\n"
    ))

    result = sb.run_command(
        ["python", str(sb.work_dir / "simple_tests.py")],
        language=Language.PYTHON,
    )

    # Manually parse using generic parser
    from src.services.execution_sandbox import TestResult
    test_result = TestResult(
        duration_ms=result.duration_ms,
        test_output=result.output,
        framework="generic",
    )
    lines = result.output.split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("OK:"):
            test_result.passed += 1
        elif stripped.startswith("FAIL:"):
            test_result.failed += 1
            test_result.failure_details.append(stripped)
    test_result.total = test_result.passed + test_result.failed
    test_result.success = test_result.failed == 0

    assert test_result.total == 4
    assert test_result.passed == 3
    assert test_result.failed == 1
    assert test_result.success is False

    d = test_result.to_dict()
    assert d["pass_rate"] == 75.0
    print("OK: run tests generic")


def test_history_limit():
    """History respects max_history limit."""
    sb = ExecutionSandbox(max_history=3)

    for i in range(5):
        sb.run_python(f"print({i})")

    history = sb.get_history()
    assert len(history) == 3
    print("OK: history limit")


def test_reset():
    """Reset clears everything."""
    sb = ExecutionSandbox()
    sb.run_python("print('x')")
    sb.write_file("data.txt", "content")

    sb.reset()
    assert sb.get_stats()["total_executions"] == 0
    assert len(sb.get_history()) == 0
    assert sb.read_file("data.txt") is None
    print("OK: reset")


def test_combined_output():
    """Combined output property."""
    sb = ExecutionSandbox()
    result = sb.run_python(
        "import sys\n"
        "print('stdout line')\n"
        "print('stderr line', file=sys.stderr)\n"
    )

    assert "stdout line" in result.output
    assert "stderr line" in result.output
    print("OK: combined output")


def main():
    print("=== Execution Sandbox Tests ===\n")
    test_run_python()
    test_run_python_error()
    test_run_python_syntax_error()
    test_run_python_with_imports()
    test_timeout()
    test_run_shell()
    test_run_command()
    test_command_not_found()
    test_execution_result_to_dict()
    test_write_and_read_file()
    test_write_and_run()
    test_list_files()
    test_env_variables()
    test_execution_history()
    test_get_result()
    test_stats()
    test_metadata()
    test_run_tests_generic()
    test_history_limit()
    test_reset()
    test_combined_output()
    print("\n=== ALL 21 TESTS PASSED ===")


if __name__ == "__main__":
    main()
