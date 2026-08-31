"""
Production entrypoint — serves EVERYTHING from one container.

    /            landing page          (humans)
    /pricing     free discovery        (agents)
    /store /search /retrieve  paid REST endpoints  (agents)
    /mcp         MCP streamable-HTTP   (agent frameworks)
    /dashboard   revenue + activity    (you, password-protected)
    /health      liveness probe        (your host)

Why this file exists: http_server.py and mcp_server.py each run standalone for
development, but a deployed service needs both on ONE public URL — the MCP
registry entry advertises /mcp while the landing page and REST endpoints live
at the same host. Both share a single memory store (see shared.py).

Composition note: this dispatches by path prefix rather than using a Starlette
Mount. Mounting the MCP app at "/mcp" makes a request to exactly "/mcp" (no
trailing slash) miss the sub-app's route — and "/mcp" with no slash is exactly
what MCP clients send. Explicit dispatch avoids that whole class of bug.

    python serve.py
"""
from __future__ import annotations

import uvicorn

import config
from http_server import app as rest_app
from mcp_server import mcp
from shared import store

# Keep FastMCP's own path (/mcp) and hand it matching requests unchanged.
mcp_app = mcp.streamable_http_app()


async def app(scope, receive, send):
    # The MCP app owns the lifespan: its session manager must be started, or
    # /mcp fails at runtime even though the route exists.
    if scope["type"] == "lifespan":
        await mcp_app(scope, receive, send)
        return

    path = scope.get("path", "")
    if path == "/mcp" or path.startswith("/mcp/"):
        await mcp_app(scope, receive, send)
    else:
        await rest_app(scope, receive, send)


if __name__ == "__main__":
    print(
        f"agent-memory  http://{config.HOST}:{config.PORT}\n"
        f"  landing   : /\n"
        f"  mcp       : /mcp\n"
        f"  rest      : /pricing /store /search /retrieve\n"
        f"  dashboard : /dashboard\n"
        f"  embeddings: {store.embedder.name}\n"
        f"  payments  : facilitator={config.FACILITATOR} network={config.NETWORK}\n"
        f"  wallet    : {config.RECEIVING_WALLET}\n"
    )
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")
