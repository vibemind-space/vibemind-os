# app.py

import hashlib
import json
import logging
import os
from functools import wraps

import jwt
from flask import Flask, jsonify, request
from jwt import InvalidTokenError

from .function_map import FUNCTIONS_MAP
from .tool_caller import call_tool

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def require_signed_request(f):
    """
    If SIGNING_SECRET is set, verifies the request content's SHA256 hash
    matches 'bodyHash' in the 'X-Signature-Jwt' header using HS256.
    If no SIGNING_SECRET is configured, skip the validation entirely.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        signing_secret = os.environ.get("SIGNING_SECRET", "").strip()

        # 1) If no signing secret is set, skip validation
        if not signing_secret:
            return f(*args, **kwargs)

        # 2) Attempt to retrieve the JWT from the header
        signature_jwt = request.headers.get("X-Signature-Jwt")
        if not signature_jwt:
            logger.error("Missing X-Signature-Jwt header")
            return jsonify({"error": "Missing X-Signature-Jwt header"}), 401

        # 3) Decode/verify the token with PyJWT, ignoring audience/issuer
        try:
            decoded = jwt.decode(
                signature_jwt,
                signing_secret,
                algorithms=["HS256"],
                options={
                    "require": ["bodyHash"],   # must have bodyHash
                    "verify_aud": False,       # disable audience check
                    "verify_iss": False,       # disable issuer check
                }
            )
        except InvalidTokenError as e:
            logger.error("Invalid token: %s", e)
            return jsonify({"error": f"Invalid token: {str(e)}"}), 401

        # 4) Compare bodyHash to SHA256(content)
        request_data = request.get_json() or {}
        content_str = request_data.get("content", "")
        actual_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()

        if decoded["bodyHash"] != actual_hash:
            logger.error("bodyHash mismatch")
            return jsonify({"error": "bodyHash mismatch"}), 403

        return f(*args, **kwargs)
    return decorated

@app.route("/tool_call", methods=["POST"])
@require_signed_request
def tool_call():
    """
    1) Parse the incoming JSON (including 'content' as a JSON string).
    2) Extract function name and arguments.
    3) Use call_tool(...) to invoke the function.
    4) Return JSON response with result or error.
    """
    req_data = request.get_json()
    if not req_data:
        logger.warning("No JSON data provided in request body.")
        return jsonify({"error": "No JSON data provided"}), 400

    content_str = req_data.get("content")
    if not content_str:
        logger.warning("Missing 'content' in request data.")
        return jsonify({"error": "Missing 'content' in request data"}), 400

    # Parse the JSON string in "content"
    try:
        parsed_content = json.loads(content_str)
    except json.JSONDecodeError as e:
        logger.error("Unable to parse 'content' as JSON: %s", e)
        return jsonify({"error": f"Unable to parse 'content' as JSON: {str(e)}"}), 400

    # Extract function info
    tool_call_data = parsed_content.get("toolCall", {})
    function_data = tool_call_data.get("function", {})

    function_name = function_data.get("name")
    arguments_str = function_data.get("arguments")

    if not function_name:
        logger.warning("No function name provided.")
        return jsonify({"error": "No function name provided"}), 400
    if not arguments_str:
        logger.warning("No arguments string provided.")
        return jsonify({"error": "No arguments string provided"}), 400

    # Parse the arguments, which is also a JSON string
    try:
        parameters = json.loads(arguments_str)
    except json.JSONDecodeError as e:
        logger.error("Unable to parse 'arguments' as JSON: %s", e)
        return jsonify({"error": f"Unable to parse 'arguments' as JSON: {str(e)}"}), 400

    try:
        result = call_tool(function_name, parameters, FUNCTIONS_MAP)
        return jsonify({"result": result}), 200
    except ValueError as val_err:
        logger.warning("ValueError in call_tool: %s", val_err)
        return jsonify({"error": str(val_err)}), 400
    except Exception as e:
        logger.exception("Unexpected error in /tool_call route")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
