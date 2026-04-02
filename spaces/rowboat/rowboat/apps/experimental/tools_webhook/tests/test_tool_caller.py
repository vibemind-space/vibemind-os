# tests/test_tool_caller.py

import pytest
from tools_webhook.tool_caller import call_tool
from tools_webhook.function_map import FUNCTIONS_MAP

def test_call_tool_greet():
    # Normal case
    result = call_tool("greet", {"name": "Alice", "message": "Hello"}, FUNCTIONS_MAP)
    assert result == "Hello, Alice!"

def test_call_tool_add():
    # Normal case
    result = call_tool("add", {"a": 2, "b": 5}, FUNCTIONS_MAP)
    assert result == 7

def test_call_tool_missing_func():
    # Should raise ValueError if function is not in FUNCTIONS_MAP
    with pytest.raises(ValueError) as exc_info:
        call_tool("non_existent_func", {}, FUNCTIONS_MAP)
    assert "Function 'non_existent_func' not found" in str(exc_info.value)

def test_call_tool_missing_param():
    # greet requires `name` and `message`
    with pytest.raises(ValueError) as exc_info:
        call_tool("greet", {"name": "Alice"}, FUNCTIONS_MAP)
    assert "Missing required parameter: message" in str(exc_info.value)

def test_call_tool_unexpected_param():
    # `greet` only expects name and message
    with pytest.raises(ValueError) as exc_info:
        call_tool("greet", {"name": "Alice", "message": "Hello", "extra": "???"},
                  FUNCTIONS_MAP)
    assert "Unexpected parameter: extra" in str(exc_info.value)

def test_call_tool_type_conversion_error():
    # `add` expects integers `a` and `b`, so passing a string should fail
    with pytest.raises(ValueError) as exc_info:
        call_tool("add", {"a": "not_an_int", "b": 3}, FUNCTIONS_MAP)
    assert "Parameter 'a' must be of type int" in str(exc_info.value)
