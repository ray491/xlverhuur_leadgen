"""Stateless, JSON-only MCP Streamable HTTP transport for the Flask deployment."""
import json
import os

from flask import jsonify, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge


VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
TOOLS = [
    {"name": "start_search", "description": "Start one paid Exa search for 30 businesses. Returns a task_id; poll get_search for results. Short results remain incomplete. Do not retry automatically.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 500}}, "required": ["query"], "additionalProperties": False},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True}},
    {"name": "get_search", "description": "Check an existing search and return status, business leads and CSV when available. Refreshes the same provider run without starting another.",
     "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string", "minLength": 1, "maxLength": 100}}, "required": ["task_id"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": True}},
    {"name": "list_searches", "description": "List saved and active searches, newest first. This installation shares one search history.",
     "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}, "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
]


def register_mcp(app, start_search, get_search, list_searches):
    handlers = {"start_search": start_search, "get_search": get_search, "list_searches": list_searches}

    def error(code, message, request_id=None, status=200):
        return jsonify(jsonrpc="2.0", id=request_id, error={"code": code, "message": message}), status

    @app.route("/mcp", methods=["POST", "GET", "DELETE"], strict_slashes=False)
    def mcp():
        origin = request.headers.get("Origin")
        allowed = {item.strip() for item in os.getenv("MCP_ALLOWED_ORIGINS", "").split(",") if item.strip()}
        if origin is not None and origin not in allowed:
            return error(-32000, "Origin not allowed", status=403)
        if request.headers.get("MCP-Protocol-Version", "2025-03-26") not in VERSIONS:
            return error(-32600, "Unsupported MCP protocol version", status=400)
        if request.method != "POST":
            response, code = error(-32000, "Only POST is supported; no SSE stream or sessions", status=405)
            response.headers["Allow"] = "POST"
            return response, code
        if not all(request.accept_mimetypes[mime] > 0 for mime in ("application/json", "text/event-stream")):
            return error(-32600, "Accept must include application/json and text/event-stream", status=406)
        if request.mimetype != "application/json":
            return error(-32600, "Content-Type must be application/json", status=415)
        request.max_content_length = 65536
        try:
            message = request.get_json()
        except RequestEntityTooLarge:
            return error(-32600, "Request too large", status=413)
        except BadRequest:
            return error(-32700, "Parse error", status=400)
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return error(-32600, "Invalid JSON-RPC request", status=400)
        request_id = message.get("id")
        if "id" in message and (type(request_id) not in (str, int)):
            return error(-32600, "Invalid request id", status=400)
        method = message.get("method")
        params = message.get("params", {})
        if not isinstance(method, str) or not isinstance(params, dict):
            return error(-32600, "Invalid JSON-RPC request", request_id, 400)
        if "id" not in message:
            # Notifications never execute tools and never produce JSON-RPC replies.
            return "", 202
        if method == "initialize":
            if not isinstance(params.get("protocolVersion"), str) or not isinstance(params.get("capabilities"), dict) or not isinstance(params.get("clientInfo"), dict):
                return error(-32602, "Invalid initialization parameters", request_id)
            version = params["protocolVersion"]
            result = {"protocolVersion": version if version in VERSIONS else VERSIONS[0], "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "marketpost-leadfinder", "version": "1.0.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name = params.get("name")
            tool = next((tool for tool in TOOLS if tool["name"] == name), None)
            if tool is None:
                return error(-32602, "Unknown tool", request_id)
            arguments = params.get("arguments", {})
            schema = tool["inputSchema"]
            if not isinstance(arguments, dict) or set(arguments) - set(schema["properties"]) or any(key not in arguments for key in schema.get("required", [])):
                return error(-32602, "Invalid tool arguments", request_id)
            for key, value in arguments.items():
                field = schema["properties"][key]
                valid = (isinstance(value, str) and field["minLength"] <= len(value) <= field["maxLength"] and bool(value.strip())) if field["type"] == "string" else (type(value) is int and field["minimum"] <= value <= field["maximum"])
                if not valid:
                    return error(-32602, "Invalid argument: " + key, request_id)
            try:
                response = app.make_response(handlers[name](**arguments))
                payload = response.get_json()
                result = {"content": [{"type": "text", "text": json.dumps(payload)}], "structuredContent": payload, "isError": response.status_code >= 400}
            except Exception:
                app.logger.exception("MCP tool failed: %s", name)
                result = {"content": [{"type": "text", "text": "Tool failed. Check search history before retrying a paid search."}], "isError": True}
        else:
            return error(-32601, "Method not found", request_id)
        return jsonify(jsonrpc="2.0", id=request_id, result=result)
