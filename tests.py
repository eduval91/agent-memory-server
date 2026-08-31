"""
Verification suite — run it to confirm the whole system works:

    python tests.py

Covers:
  1. Semantic memory: ranking is correct and namespaces are isolated.
  2. Payment logic: unpaid -> 402 requirements; paid -> allowed.
  3. HTTP x402 middleware: real 402 status on an unpaid tools/call, free
     discovery calls pass, paid retry is forwarded to the downstream app.

No network and no real crypto — uses the mock facilitator.
"""
from __future__ import annotations
import json
import os
import tempfile

# Isolate the test run: use throwaway DB files so tests never touch the real
# ledger or memories. Must happen BEFORE importing the modules that read these.
_tmp = tempfile.mkdtemp(prefix="agent-memory-tests-")
os.environ["LEDGER_DB"] = os.path.join(_tmp, "ledger.db")
os.environ["MEMORY_DB"] = os.path.join(_tmp, "memories.db")

import config
import payments
from memory_store import MemoryStore
from embeddings import HashingEmbedder
from eth_account import Account


passed = 0


def check(name, cond):
    global passed
    assert cond, f"FAILED: {name}"
    passed += 1
    print(f"  ✓ {name}")


# ---------------------------------------------------------------------------
print("\n[1] semantic memory")
# Use the hashing embedder so this test is deterministic and dependency-free.
store = MemoryStore(embedder=HashingEmbedder())
ns = "agentA"
store.store(ns, "Refunds are processed within five business days", {"t": "billing"})
store.store(ns, "The office is closed on public holidays", {"t": "hr"})
mid = store.store(ns, "Reset your password from the login page", {"t": "support"})["id"]

res = store.search(ns, "money back refund processed", top_k=3)
check("search returns results", len(res) == 3)
check("best match is the refund memory", "Refund" in res[0]["text"])
check("scores are sorted descending", res[0]["score"] >= res[1]["score"] >= res[2]["score"])
check("retrieve by id works", store.retrieve(ns, mid)["text"].startswith("Reset"))
check("namespaces are isolated", store.search("agentB", "refund") == [])
check("delete works", store.delete(ns, mid) and store.retrieve(ns, mid) is None)

# persistence: a NEW store instance (fresh process, conceptually) sees the data
store2 = MemoryStore(embedder=HashingEmbedder())
check("memories survive a restart", store2.count(ns) == 2)
res2 = store2.search(ns, "money back refund processed", top_k=1)
check("search works after restart", "Refund" in res2[0]["text"])
check("deleted memory stays deleted after restart", store2.retrieve(ns, mid) is None)

import memory_store as _ms
st = _ms.stats()
check("stats reports totals for the dashboard", st["memories"] == 2 and st["namespaces"] == 1)

# ---------------------------------------------------------------------------
print("\n[2] payment logic (mock facilitator)")
assert config.FACILITATOR == "mock", "run tests with FACILITATOR=mock (the default)"
resource = "mcp://agent-memory/search_memory"
price = payments.price_for("search_memory")
check("search_memory has a nonzero price", price > 0)

allowed, req, _ = payments.check_payment("search_memory", None, resource)
check("unpaid call is rejected", not allowed)
check("402 requirements name the price", req["accepts"][0]["maxAmountRequired"] == str(price))
check("402 requirements name your wallet", req["accepts"][0]["payTo"] == config.RECEIVING_WALLET)

key = payments.new_test_key()  # throwaway agent wallet

# underpaid: sign an authorization for less than the required amount
cheap = {"accepts": [{**req["accepts"][0], "maxAmountRequired": str(price - 1)}]}
underpaid = payments.sign_payment(key, cheap)
allowed, _, info = payments.check_payment("search_memory", underpaid, resource)
check("underpayment is rejected", not allowed)

# tampered: a valid signature but for the wrong recipient must be rejected
wrong_to = {"accepts": [{**req["accepts"][0], "payTo": "0x" + "de" * 20}]}
bad_recipient = payments.sign_payment(key, wrong_to)
allowed, _, _ = payments.check_payment("search_memory", bad_recipient, resource)
check("payment to wrong recipient is rejected", not allowed)

# correct: a genuine signed EIP-3009 payment for the full price
token = payments.sign_payment(key, req)
allowed, _, info = payments.check_payment("search_memory", token, resource)
check("correct signed payment is accepted", allowed)
check("recovered payer == signer address", info["payer"] == Account.from_key(key).address)

check("free discovery tool is never charged", payments.price_for("get_pricing") == 0)

# replay protection: the same signed payment may buy exactly one operation
replay = payments.sign_payment(key, req)
allowed1, _, _ = payments.check_payment("search_memory", replay, resource)
allowed2, _, info2 = payments.check_payment("search_memory", replay, resource)
check("first use of a payment is accepted", allowed1)
check("replayed payment is rejected", not allowed2 and "replay" in info2["reason"])

# ---------------------------------------------------------------------------
print("\n[3] HTTP x402 middleware (canonical 402 loop)")
from starlette.testclient import TestClient
from x402_middleware import X402Middleware


async def downstream(scope, receive, send):
    """A stand-in for the real MCP app: echoes 200 so we can prove forwarding."""
    await receive()  # drain body
    body = json.dumps({"ok": True, "forwarded": True}).encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})


client = TestClient(X402Middleware(downstream))

# free discovery call passes through
r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
check("tools/list passes free (200)", r.status_code == 200 and r.json()["forwarded"])

# paid tool call with no payment -> 402
call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "search_memory", "arguments": {"agent_id": "a", "query": "x"}}}
r = client.post("/mcp", json=call)
check("unpaid tools/call returns HTTP 402", r.status_code == 402)
check("402 body carries x402 requirements", r.json()["accepts"][0]["description"].startswith("search_memory"))

# same call, now paying -> forwarded (200)
http_req = payments.build_requirements("search_memory", payments.price_for("search_memory"), "http")
signed = payments.sign_payment(key, http_req)
r = client.post("/mcp", json=call, headers={"X-PAYMENT": signed})
check("paid tools/call is forwarded (200)", r.status_code == 200 and r.json()["forwarded"])

# ---------------------------------------------------------------------------
print("\n[4] hardening (rate limits, input caps, quotas)")
import hardening

check("oversized text is rejected",
      hardening.check_store("x" * (config.MAX_TEXT_BYTES + 1), None) is not None)
check("normal text passes", hardening.check_store("hello world", {"a": 1}) is None)
check("oversized metadata is rejected",
      hardening.check_store("hi", {"blob": "y" * config.MAX_METADATA_BYTES}) is not None)
check("bad top_k is rejected", hardening.check_search("q", config.MAX_TOP_K + 1) is not None)
check("empty query is rejected", hardening.check_search("   ", 5) is not None)
check("bad agent_id is rejected", hardening.check_agent_id("evil\nid") is not None)

rl = hardening.RateLimiter(per_minute=2)
check("rate limiter allows within budget", rl.allow("a") and rl.allow("a"))
check("rate limiter refuses the burst", not rl.allow("a"))
check("rate limiter isolates clients", rl.allow("b"))

_old_quota = config.MAX_MEMORIES_PER_AGENT
config.MAX_MEMORIES_PER_AGENT = 2
qstore = MemoryStore(embedder=HashingEmbedder())
qstore.store("quota-agent", "one")
qstore.store("quota-agent", "two")
check("quota blocks the agent at the cap",
      hardening.check_quota(qstore, "quota-agent") is not None)
check("quota doesn't block other agents",
      hardening.check_quota(qstore, "other-agent") is None)
config.MAX_MEMORIES_PER_AGENT = _old_quota

# HTTP layer: caps enforced before payment (rejected calls cost nothing)
import http_server
hclient = TestClient(http_server.app)
r = hclient.post("/store", json={"text": "x" * (config.MAX_TEXT_BYTES + 1)})
check("HTTP rejects oversized text with 400 (no 402 first)", r.status_code == 400)
r = hclient.post("/search", content=b"not json", headers={"content-type": "application/json"})
check("HTTP rejects malformed JSON with 400", r.status_code == 400)
r = hclient.post("/store", content=b"x" * (config.MAX_BODY_BYTES + 1))
check("HTTP rejects oversized body with 413", r.status_code == 413)

# ---------------------------------------------------------------------------
print("\n[5] dashboard access control")
import base64, importlib
import dashboard_auth


def _basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


_orig_host, _orig_pw = config.HOST, config.DASHBOARD_PASSWORD

# localhost: open, for local development convenience
config.HOST, config.DASHBOARD_PASSWORD = "127.0.0.1", ""
importlib.reload(dashboard_auth)
check("localhost needs no password", not dashboard_auth.required())
check("localhost is not flagged misconfigured", not dashboard_auth.misconfigured())

# public with no password: must fail closed
config.HOST, config.DASHBOARD_PASSWORD = "0.0.0.0", ""
importlib.reload(dashboard_auth)
check("public server requires a password", dashboard_auth.required())
check("public + no password = misconfigured (fails closed)", dashboard_auth.misconfigured())
check("no credentials are accepted while misconfigured", not dashboard_auth.check(None))

# public with a password: only the right credentials pass
config.HOST, config.DASHBOARD_PASSWORD = "0.0.0.0", "s3cret"
importlib.reload(dashboard_auth)
check("missing credentials rejected", not dashboard_auth.check(None))
check("malformed header rejected", not dashboard_auth.check("Bearer xyz"))
check("wrong password rejected", not dashboard_auth.check(_basic("admin", "nope")["Authorization"]))
check("wrong user rejected", not dashboard_auth.check(_basic("root", "s3cret")["Authorization"]))
check("correct credentials accepted", dashboard_auth.check(_basic(config.DASHBOARD_USER, "s3cret")["Authorization"]))

# the HTTP layer enforces it, and public endpoints stay open
hclient2 = TestClient(http_server.app)
check("HTTP /dashboard returns 401 without credentials",
      hclient2.get("/dashboard").status_code == 401)
check("HTTP /api/metrics returns 401 without credentials",
      hclient2.get("/api/metrics").status_code == 401)
check("HTTP /dashboard serves with credentials",
      hclient2.get("/dashboard", headers=_basic(config.DASHBOARD_USER, "s3cret")).status_code == 200)
check("landing page stays public", hclient2.get("/").status_code == 200)
check("pricing stays public (agents must see it)", hclient2.get("/pricing").status_code == 200)
check("paid endpoints still answer 402 when locked down",
      hclient2.post("/search", json={"query": "x"}).status_code == 402)

config.HOST, config.DASHBOARD_PASSWORD = _orig_host, _orig_pw
importlib.reload(dashboard_auth)

# ---------------------------------------------------------------------------
print(f"\nALL PASSED ({passed} checks)\n")
