# tests/test_app.py

import json
import pytest
from tools_webhook.app import app  # If "sidecar" is recognized as a package

@pytest.fixture
def client():
    """
    A pytest fixture that provides a Flask test client.
    The `app.test_client()` allows us to make requests to our Flask app
    without running the server.
    """
    with app.test_client() as client:
        yield client


def test_tool_call_greet(client):
    # This matches the structure of the request in our code:
    # {
    #   "content": "...a JSON string..."
    # }

    # The content we pass is another JSON, so we have to double-escape quotes.
    request_data = {
        "content": json.dumps({
            "toolCall": {
                "function": {
                    "name": "greet",
                    "arguments": json.dumps({
                        "name": "Alice",
                        "message": "Hello"
                    })
                }
            }
        })
    }

    response = client.post(
        "/tool_call", 
        data=json.dumps(request_data), 
        content_type="application/json"
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["result"] == "Hello, Alice!"


def test_tool_call_missing_params(client):
    request_data = {
        "content": json.dumps({
            "toolCall": {
                "function": {
                    "name": "greet",
                    "arguments": json.dumps({
                        "name": "Alice"
                        # Missing "message"
                    })
                }
            }
        })
    }

    response = client.post(
        "/tool_call",
        data=json.dumps(request_data),
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "Missing required parameter: message" in data["error"]


def test_tool_call_invalid_func(client):
    request_data = {
        "content": json.dumps({
            "toolCall": {
                "function": {
                    "name": "does_not_exist",
                    "arguments": json.dumps({})
                }
            }
        })
    }

    response = client.post(
        "/tool_call", 
        data=json.dumps(request_data), 
        content_type="application/json"
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "Function 'does_not_exist' not found" in data["error"]

