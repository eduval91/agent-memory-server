"""
The MCP server agents connect to.

Exposes agent-native searchable memory as MCP tools:
    get_pricing       (free)  — discover what's on offer and what it costs
    store_memory      (paid)  — save a memory
    search_memory     (paid)  — semantic search over an agent's memories
    retrieve_memory   (paid)  — fetch one memory by id

PAYMENT MODEL (in-tool x402)
----------------------------
Each paid tool accepts an optional `payment` argument: the agent's X-PAYMENT
token. On the first call the agent omits it, so the tool returns a
`payment_required` response containing x402 payment requirements (price, your
wallet, network, stablecoin). The agent's wallet builds a payment and calls the
tool again with `payment=<token>`. We verify + settle via the facilitator, then
serve the result.

This "in-tool" style works over any MCP transport (stdio or HTTP). If you prefer
enforcement at the HTTP layer (the textbook 402 status-code loop), see
x402_middleware.py — it wraps this same app and uses the same payments module.

Run it:
    python mcp_server.py            # streamable-HTTP on config.HOST:config.PORT
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import config
import hardening
import payments
from shared import store

mcp = FastMCP("agent-memory", host=config.HOST, port=config.PORT)


def _resource(tool_name: str) -> str:
    return f"mcp://agent-memory/{tool_name}"


def _precheck(agent_id: str, *, error: str | None = None):
    """Validation + rate limiting, run BEFORE payment (refused calls are free).
    Returns an error dict to return to the agent, or None when all is well."""
    msg = hardening.check_agent_id(agent_id) or error
    if msg:
        return {"status": "error", "error": msg}
    if not hardening.limiter.allow(agent_id):
        return {"status": "error",
                "error": f"rate limited: max {config.RATE_LIMIT_PER_MIN} calls/min"}
    return None


def _guard(tool_name: str, payment: str | None):
    """Returns (allowed, payment_required_response, info).

    If not allowed, payment_required_response is the dict to return to the agent.
    """
    allowed, requirements, info = payments.check_payment(
        tool_name, payment, _resource(tool_name)
    )
    if allowed:
        return True, None, info
    response = {
        "status": "payment_required",
        "message": (
            f"This operation costs {config.usdc(payments.price_for(tool_name))}. "
            f"Pay per the x402 requirements below, then call again with the "
            f"`payment` argument set to your X-PAYMENT token."
        ),
        "x402": requirements,
    }
    return False, response, info


# ---------------------------------------------------------------------------
# Free discovery tool — agents (and their developers) can see the menu + prices
# before spending anything.
# ---------------------------------------------------------------------------
@mcp.tool()
def get_pricing() -> dict:
    """List the available operations and their per-call price. Free to call."""
    return {
        "service": "agent-native searchable memory",
        "network": config.NETWORK,
        "asset": "USDC",
        "pay_to": config.RECEIVING_WALLET,
        "x402_enabled": config.X402_ENABLED,
        "prices": {
            name: {
                "atomic": atomic,
                "usdc": config.usdc(atomic),
            }
            for name, atomic in config.PRICES_ATOMIC.items()
        },
        "how_to_pay": (
            "Call a paid tool without `payment` to receive x402 requirements, "
            "then call again with `payment` set to your X-PAYMENT token."
        ),
    }


# ---------------------------------------------------------------------------
# Paid tools
# ---------------------------------------------------------------------------
@mcp.tool()
def store_memory(
    agent_id: str,
    text: str,
    metadata: dict | None = None,
    payment: str | None = None,
) -> dict:
    """Store a memory for an agent. Returns the stored record (with its id).

    agent_id : namespace — an agent only ever sees its own memories.
    text     : the content to remember.
    metadata : optional structured tags (e.g. {"topic": "billing"}).
    payment  : X-PAYMENT token; omit first to receive payment requirements.
    """
    if (err := _precheck(agent_id, error=hardening.check_store(text, metadata))):
        return err
    allowed, need_pay, _info = _guard("store_memory", payment)
    if not allowed:
        return need_pay
    if (msg := hardening.check_quota(store, agent_id)):
        return {"status": "error", "error": msg}
    record = store.store(agent_id, text, metadata)
    return {"status": "ok", "memory": record}


@mcp.tool()
def search_memory(
    agent_id: str,
    query: str,
    top_k: int = 5,
    payment: str | None = None,
) -> dict:
    """Semantic search over an agent's memories. Returns ranked matches.

    Matches by MEANING, not keywords — this is the value the agent pays for.
    payment : X-PAYMENT token; omit first to receive payment requirements.
    """
    if (err := _precheck(agent_id, error=hardening.check_search(query, top_k))):
        return err
    allowed, need_pay, _info = _guard("search_memory", payment)
    if not allowed:
        return need_pay
    results = store.search(agent_id, query, top_k=top_k)
    return {"status": "ok", "query": query, "results": results}


@mcp.tool()
def retrieve_memory(
    agent_id: str,
    memory_id: str,
    payment: str | None = None,
) -> dict:
    """Fetch a single memory by id.

    payment : X-PAYMENT token; omit first to receive payment requirements.
    """
    if (err := _precheck(agent_id)):
        return err
    allowed, need_pay, _info = _guard("retrieve_memory", payment)
    if not allowed:
        return need_pay
    record = store.retrieve(agent_id, memory_id)
    if record is None:
        return {"status": "not_found", "memory_id": memory_id}
    return {"status": "ok", "memory": record}


# ---------------------------------------------------------------------------
# Operator dashboard (plain HTTP, not MCP): open /dashboard in a browser while
# the server runs to watch connections and revenue live.
# ---------------------------------------------------------------------------
from starlette.requests import Request  # noqa: E402
from starlette.responses import HTMLResponse, JSONResponse  # noqa: E402

import dashboard  # noqa: E402


import dashboard_auth  # noqa: E402


def _dashboard_gate(request: Request):
    """Returns an error response when dashboard access isn't allowed."""
    if dashboard_auth.misconfigured():
        return JSONResponse({"status": "error",
                             "error": dashboard_auth.MISCONFIGURED_MESSAGE},
                            status_code=503)
    if not dashboard_auth.check(request.headers.get("authorization")):
        return JSONResponse({"status": "error", "error": "authentication required"},
                            status_code=401,
                            headers=dashboard_auth.UNAUTHORIZED_HEADERS)
    return None


@mcp.custom_route("/dashboard", methods=["GET"])
async def dashboard_page(request: Request):
    if (blocked := _dashboard_gate(request)):
        return blocked
    return HTMLResponse(dashboard.DASHBOARD_HTML)


@mcp.custom_route("/api/metrics", methods=["GET"])
async def dashboard_metrics(request: Request):
    if (blocked := _dashboard_gate(request)):
        return blocked
    return JSONResponse(dashboard.metrics())


if __name__ == "__main__":
    print(
        f"agent-memory MCP server\n"
        f"  transport : streamable-http at http://{config.HOST}:{config.PORT}/mcp\n"
        f"  dashboard : http://{config.HOST}:{config.PORT}/dashboard\n"
        f"  embeddings: {store.embedder.name}\n"
        f"  payments  : x402_enabled={config.X402_ENABLED} "
        f"facilitator={config.FACILITATOR} network={config.NETWORK}\n"
        f"  wallet    : {config.RECEIVING_WALLET}\n"
    )
    mcp.run(transport="streamable-http")
