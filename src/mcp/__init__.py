"""
DSA MCP (Model Context Protocol) Server.

Exposes DSA's core stock analysis capabilities as MCP tools that can be consumed
by AI assistants (Claude Desktop, Cursor, Copilot, custom agents, etc.).

Usage:
    # Run as stdio MCP server (for AI assistant integration)
    python -m src.mcp.stdio_server

    # Embed in FastAPI (for web integration)
    from src.mcp.routes import router as mcp_router
    app.include_router(mcp_router, prefix="/api/v1/mcp")
"""

from src.mcp.tools import TOOL_REGISTRY

__all__ = ["TOOL_REGISTRY"]
