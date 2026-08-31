"""
HTTP facade — the canonical x402 loop over plain REST.

This serves the SAME memory product as mcp_server.py, but as simple HTTP
endpoints that return a real `402 Payment Required` and accept a real
`X-PAYMENT` header. It's the cleanest way to:
  * see the textbook x402 status-code loop, and
  * test against a REAL facilitator on testnet (set FACILITATOR=coinbase),
    driven by agent_client.py.

Endpoints:
  GET  /pricing            free — discover operations and prices
  POST /store    {text, metadata?}     paid — store a memory
  POST /search   {query, top_k?}       paid — semantic search
  POST /retrieve {memory_id}           paid — fetch by id

Memories are namespaced by the VERIFIED PAYER address — identity is whoever
paid, so no accounts and no spoofing.

Run:
    python http_server.py          # http://127.0.0.1:8402
"""
from __future__ import annotations
import json

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

import config
import dashboard
import dashboard_auth
import hardening
import landing
import ledger
import payments
from shared import store


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse({"status": "error", "error": message}, status_code=status)


async def _read_body(request: Request):
    """Rate-limit, cap, and parse the request body. Returns (body, None) or
    (None, error-response). Runs BEFORE payment so refused calls cost nothing."""
    client = request.client.host if request.client else "unknown"
    if not hardening.limiter.allow(client):
        return None, _err(429, f"rate limited: max {config.RATE_LIMIT_PER_MIN} calls/min")
    raw = await request.body()
    if len(raw) > config.MAX_BODY_BYTES:
        return None, _err(413, f"request too large (max {config.MAX_BODY_BYTES} bytes)")
    try:
        return json.loads(raw), None
    except Exception:
        return None, _err(400, "body must be valid JSON")


async def _guard(request: Request, tool_name: str):
    """Enforce payment. Returns (payer_address, None) or (None, JSONResponse-402)."""
    resource = str(request.url)
    x_payment = request.headers.get("x-payment")
    allowed, requirements, info = payments.check_payment(tool_name, x_payment, resource)
    if allowed:
        return info.get("payer", "anonymous"), None
    return None, JSONResponse(requirements, status_code=402,
                              headers={"X-Payment-Required": "true"})


async def pricing(request: Request):
    return JSONResponse({
        "service": "agent-native searchable memory",
        "network": config.NETWORK,
        "asset": "USDC",
        "pay_to": config.RECEIVING_WALLET,
        "prices": {n: {"atomic": a, "usdc": config.usdc(a)}
                   for n, a in config.PRICES_ATOMIC.items()},
    })


async def store_ep(request: Request):
    body, err = await _read_body(request)
    if err:
        return err
    if (msg := hardening.check_store(body.get("text"), body.get("metadata"))):
        return _err(400, msg)
    payer, err = await _guard(request, "store_memory")
    if err:
        return err
    if (msg := hardening.check_quota(store, payer)):
        return _err(403, msg)
    rec = store.store(payer, body["text"], body.get("metadata"))
    return JSONResponse({"status": "ok", "memory": rec})


async def search_ep(request: Request):
    body, err = await _read_body(request)
    if err:
        return err
    if (msg := hardening.check_search(body.get("query"), body.get("top_k", 5))):
        return _err(400, msg)
    payer, err = await _guard(request, "search_memory")
    if err:
        return err
    results = store.search(payer, body["query"], top_k=body.get("top_k", 5))
    return JSONResponse({"status": "ok", "query": body["query"], "results": results})


async def retrieve_ep(request: Request):
    body, err = await _read_body(request)
    if err:
        return err
    if not isinstance(body.get("memory_id"), str):
        return _err(400, "memory_id must be a string")
    payer, err = await _guard(request, "retrieve_memory")
    if err:
        return err
    rec = store.retrieve(payer, body["memory_id"])
    if rec is None:
        return JSONResponse({"status": "not_found"}, status_code=404)
    return JSONResponse({"status": "ok", "memory": rec})


def _dashboard_gate(request: Request):
    """Returns an error response when dashboard access isn't allowed."""
    if dashboard_auth.misconfigured():
        return _err(503, dashboard_auth.MISCONFIGURED_MESSAGE)
    if not dashboard_auth.check(request.headers.get("authorization")):
        return JSONResponse({"status": "error", "error": "authentication required"},
                            status_code=401,
                            headers=dashboard_auth.UNAUTHORIZED_HEADERS)
    return None


async def dashboard_page(request: Request):
    if (blocked := _dashboard_gate(request)):
        return blocked
    return HTMLResponse(dashboard.DASHBOARD_HTML)


async def dashboard_metrics(request: Request):
    if (blocked := _dashboard_gate(request)):
        return blocked
    return JSONResponse(dashboard.metrics())


async def home(request: Request):
    """Public landing page — what a human sees at your URL."""
    return HTMLResponse(landing.page())


async def health(request: Request):
    """Liveness probe for your host's health checks."""
    return JSONResponse({"status": "ok", "service": config.SERVICE_NAME})


async def interest(request: Request):
    """Demand capture from the landing page — lands in the ledger + dashboard."""
    body, err = await _read_body(request)
    if err:
        return err
    contact = str(body.get("contact", ""))[:200].replace("\n", " ")
    note = str(body.get("note", ""))[:1000].replace("\n", " ")
    if not contact.strip():
        return _err(400, "contact is required")
    ledger.record("interest", "landing_page", payer=contact, detail=note)
    return JSONResponse({"status": "ok"})


app = Starlette(routes=[
    Route("/", home, methods=["GET"]),
    Route("/health", health, methods=["GET"]),
    Route("/pricing", pricing, methods=["GET"]),
    Route("/store", store_ep, methods=["POST"]),
    Route("/search", search_ep, methods=["POST"]),
    Route("/retrieve", retrieve_ep, methods=["POST"]),
    Route("/interest", interest, methods=["POST"]),
    Route("/dashboard", dashboard_page, methods=["GET"]),
    Route("/api/metrics", dashboard_metrics, methods=["GET"]),
])


if __name__ == "__main__":
    print(
        f"agent-memory HTTP server  http://{config.HOST}:{config.PORT}\n"
        f"  dashboard : http://{config.HOST}:{config.PORT}/dashboard\n"
        f"  embeddings: {store.embedder.name}\n"
        f"  payments  : x402_enabled={config.X402_ENABLED} "
        f"facilitator={config.FACILITATOR} network={config.NETWORK}\n"
        f"  wallet    : {config.RECEIVING_WALLET}\n"
    )
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")
