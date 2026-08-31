"""
OPTIONAL: enforce x402 at the HTTP layer (the textbook 402 status-code loop).

mcp_server.py enforces payment *inside* each tool, which works over any
transport. If instead you want the canonical HTTP flow — the server literally
returns `402 Payment Required` and the agent retries with an `X-PAYMENT`
header — wrap the MCP ASGI app with this middleware.

It inspects each JSON-RPC `tools/call`, prices it per tool, and either returns
402 or forwards the request untouched. Discovery calls (initialize, tools/list,
ping) pass through free.

Wire it up (instead of mcp.run):

    import uvicorn
    from x402_middleware import X402Middleware
    from mcp_server import mcp
    app = X402Middleware(mcp.streamable_http_app())
    uvicorn.run(app, host=config.HOST, port=config.PORT)
"""
from __future__ import annotations
import json

from starlette.responses import JSONResponse

import config
import payments


class X402Middleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return

        # Buffer the request body so we can inspect it and still forward it.
        body = await _read_body(receive)
        tool_name = _tool_from_jsonrpc(body)

        # Not a paid tool call (handshake, discovery, notifications) -> free.
        if tool_name is None or payments.price_for(tool_name) == 0:
            await self.app(scope, _replay(body), send)
            return

        x_payment = _header(scope, b"x-payment")
        resource = _resource_from_scope(scope, tool_name)
        allowed, requirements, info = payments.check_payment(
            tool_name, x_payment, resource
        )
        if not allowed:
            response = JSONResponse(
                requirements,
                status_code=402,
                headers={"X-Payment-Required": "true"},
            )
            await response(scope, receive, send)
            return

        # Paid: forward the (replayed) request to the real MCP app.
        await self.app(scope, _replay(body), send)


# --- helpers ---------------------------------------------------------------
async def _read_body(receive) -> bytes:
    chunks = []
    while True:
        msg = await receive()
        if msg["type"] == "http.request":
            chunks.append(msg.get("body", b""))
            if not msg.get("more_body", False):
                break
        else:
            break
    return b"".join(chunks)


def _replay(body: bytes):
    """A fresh `receive` callable that yields the buffered body once."""
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


def _tool_from_jsonrpc(body: bytes) -> str | None:
    try:
        data = json.loads(body)
    except Exception:
        return None
    # A batch is a list; check each for a paid tools/call.
    items = data if isinstance(data, list) else [data]
    for item in items:
        if isinstance(item, dict) and item.get("method") == "tools/call":
            return (item.get("params") or {}).get("name")
    return None


def _header(scope, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k.lower() == name:
            return v.decode()
    return None


def _resource_from_scope(scope, tool_name: str) -> str:
    host = _header(scope, b"host") or f"{config.HOST}:{config.PORT}"
    path = scope.get("path", "/mcp")
    return f"http://{host}{path}#{tool_name}"
