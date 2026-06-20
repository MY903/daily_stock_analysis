"""
MCP stdio transport server.

Implements the Model Context Protocol (MCP) over standard input/output for
AI assistant integration. Supports tools/list, tools/call, initialize, and ping.

Usage:
    python -m src.mcp.stdio_server
    # Then connect from Claude Desktop / Cursor via:
    # "mcpServers": { "dsa": { "command": "python", "args": ["-m", "src.mcp.stdio_server"] } }
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Optional

from src.mcp.tools import list_tools, call_tool

logger = logging.getLogger(__name__)

# Server metadata
SERVER_INFO = {
    "name": "dsa-mcp-server",
    "version": "1.0.0",
    "description": "DSA Stock Analysis - MCP Server for AI assistants",
}

# Protocol capabilities
CAPABILITIES = {
    "tools": {},
}


async def _handle_request(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Handle a single JSON-RPC request.

    Args:
        request: Parsed JSON-RPC request dict.

    Returns:
        Response dict, or None for notifications.
    """
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {}) or {}

    # Notifications (no id) don't get a response
    if req_id is None:
        return None

    error: Optional[Dict[str, Any]] = None
    result: Any = None

    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "serverInfo": SERVER_INFO,
                "capabilities": CAPABILITIES,
            }
        elif method == "ping":
            result = {"status": "ok"}
        elif method == "tools/list":
            result = {"tools": list_tools()}
        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            # Handle both "name" and method-based invocation
            result = await call_tool(tool_name, arguments)
        else:
            error = {
                "code": -32601,
                "message": f"Method not found: {method}",
            }
    except Exception as e:
        logger.exception("Request handler error: %s", e)
        error = {
            "code": -32603,
            "message": f"Internal error: {str(e)}",
        }

    response: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": req_id,
    }
    if error:
        response["error"] = error
    else:
        response["result"] = result
    return response


async def run_stdio_server() -> None:
    """Run the MCP server in stdio mode.

    Reads JSON-RPC messages from stdin, processes them, and writes
    responses to stdout.
    """
    logger.info("MCP stdio server starting")

    # Signal readiness to the host (used by some MCP clients)
    print(json.dumps({"jsonrpc": "2.0", "method": "log", "params": {
        "level": "info",
        "data": "DSA MCP Server ready",
    }}), file=sys.stderr)
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON-RPC message: %s", e)
            continue

        response = await _handle_request(request)
        if response is not None:
            print(json.dumps(response))
            sys.stdout.flush()

    logger.info("MCP stdio server shutting down")


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(run_stdio_server())
