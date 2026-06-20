#!/usr/bin/env python3
"""
DSA MCP Server - Model Context Protocol for Stock Analysis.

Exposes DSA's core stock analysis capabilities as MCP tools that can be
consumed by AI assistants (Claude Desktop, Cursor, Copilot, etc.).

Usage:
    # Run as stdio MCP server
    python dsa_mcp_server.py

    # Integrate with Claude Desktop (claude_desktop_config.json):
    {
        "mcpServers": {
            "dsa": {
                "command": "python",
                "args": ["dsa_mcp_server.py"],
                "env": {
                    "DSA_ROOT": "/path/to/daily_stock_analysis"
                }
            }
        }
    }

    # Test available tools
    echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python dsa_mcp_server.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


def _ensure_project_root() -> None:
    """Ensure project root is in sys.path for imports."""
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main() -> None:
    """Entry point for the MCP stdio server."""
    _ensure_project_root()

    import logging
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    from src.mcp.stdio_server import run_stdio_server
    asyncio.run(run_stdio_server())


if __name__ == "__main__":
    main()
