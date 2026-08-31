# Agent Memory

**Persistent, semantically searchable memory for autonomous agents — paid per call, no account required.**

🔗 **https://agent-memory-server.fly.dev**

An agent's context window forgets everything between runs. This service gives it
a memory that persists, and one it can search by *meaning*: the query
*"when can I send an item back?"* finds *"our return window is 30 days from
delivery"* despite sharing no keywords.

Payment happens in-band over [x402](https://x402.org). An agent calls an
endpoint, receives `402 Payment Required`, its wallet signs a stablecoin
payment, and it retries — no signup, no API key, no human in the loop. Memories
are namespaced by the paying wallet, so identity *is* whoever paid.

> **Status: live on Base Sepolia testnet.** Everything works end to end —
> real signed payments, real on-chain settlement — but with testnet USDC, so
> you can integrate and evaluate for free. Mainnet is next. If you'd like a
> heads-up when it flips, open an issue or use the form on the site.

---

## Quick start

### Connect over MCP

Add the server to any [MCP](https://modelcontextprotocol.io)-capable client:

```
https://agent-memory-server.fly.dev/mcp
```

With Claude Code, for example:

```bash
claude mcp add --transport http agent-memory https://agent-memory-server.fly.dev/mcp
```

Your agent then sees four tools: `get_pricing` (free), `store_memory`,
`search_memory`, and `retrieve_memory`.

### Or call it over HTTP

```bash
# free — see what's on offer
curl https://agent-memory-server.fly.dev/pricing

# paid — returns 402 with payment requirements, then serves on retry
curl -X POST https://agent-memory-server.fly.dev/search \
  -H 'content-type: application/json' \
  -d '{"query":"refund policy","top_k":3}'
```

Any x402 client library handles the 402 → pay → retry loop automatically.
`agent_client.py` in this repo is a working reference implementation in ~140
lines if you'd rather see it done by hand.

---

## Pricing

| operation | what it does | price |
|---|---|---|
| `get_pricing` | list operations and prices | **free** |
| `store_memory` | save a memory | 0.002 USDC |
| `search_memory` | semantic search over your memories | 0.01 USDC |
| `retrieve_memory` | fetch one memory by id | 0.001 USDC |

No subscription, no minimum, no account. You pay per operation, in USDC, and
only for calls that succeed — validation and rate-limit rejections happen
*before* payment is taken.

---

## API

All paid endpoints answer `402` with x402 payment requirements when called
without an `X-PAYMENT` header, then serve the result when retried with one.

### `POST /store`
```json
{ "text": "Our return window is 30 days from delivery.",
  "metadata": {"topic": "billing"} }
```
Returns the stored record and its `id`.

### `POST /search`
```json
{ "query": "when can I send an item back?", "top_k": 3 }
```
Returns matches ranked by semantic similarity, each with a `score`.

### `POST /retrieve`
```json
{ "memory_id": "2c1d2746-..." }
```

### `GET /pricing`
Free. Returns operations, prices, network, and the receiving address.

**Limits:** 60 calls/min per client · 8KB per memory · 1KB per query ·
20 results per search · 10,000 memories per wallet.

---

## How it works

```
agent ──── POST /search (no payment) ─────────────▶ server
agent ◀─── 402 + { price, payTo, network, asset } ─ server
            (agent's wallet signs an EIP-3009 authorization)
agent ──── POST /search + X-PAYMENT header ───────▶ server
                                    server ── verify + settle ──▶ facilitator
agent ◀─── 200 + ranked results ──────────────────  server
```

Under the hood: text is embedded with `all-MiniLM-L6-v2`, vectors are stored in
SQLite and searched by cosine similarity, and payments use the x402 *exact*
scheme — an EIP-3009 `transferWithAuthorization` the payer signs and a
facilitator settles on Base. Each signed payment is valid for exactly one
operation; replays are rejected.

---

## Self-hosting

This repo is the whole service. To run your own:

```bash
git clone https://github.com/eduval91/agent-memory-server
cd agent-memory-server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env     # set RECEIVING_WALLET at minimum
python tests.py          # 55 checks
python demo.py           # watch the whole loop, no crypto needed
python serve.py          # everything on http://127.0.0.1:8402
```

It ships in **mock facilitator** mode: payments are genuinely signed and
verified, but not settled on-chain — so the full loop runs with no wallet and no
risk. See `TESTNET.md` to settle real testnet payments, and `DEPLOY.md` to put
it on a public URL.

| file | what it is |
|---|---|
| `serve.py` | production entrypoint — REST + MCP + dashboard on one port |
| `memory_store.py` | the product: persistent store, search, retrieve |
| `embeddings.py` | text → vectors (local model, hosted API, or fallback) |
| `payments.py` · `x402_scheme.py` | x402 requirements, facilitators, EIP-3009 signing |
| `hardening.py` | rate limits, input caps, quotas |
| `dashboard.py` · `ledger.py` | operator dashboard and transaction ledger |
| `agent_client.py` | reference paying client |
| `tests.py` | 55-check verification suite |

Swap the SQLite vector store for pgvector/Qdrant, or the local embedder for a
hosted one, without touching anything else — both are behind small interfaces.

---

## Notes and caveats

- **Testnet.** Payments settle in Base Sepolia USDC, which has no monetary value.
- **The x402 spec is young.** The facilitator request shape and the Bazaar
  discovery extension are marked with `TODO`s where they should be re-verified
  against current docs.
- **Memories are per-wallet.** There's no sharing between agents yet, and no
  deletion endpoint exposed over the API (the store supports it internally).
- **Cold starts.** The server sleeps when idle to keep costs near zero; the
  first request after a quiet period can take ~30s while the model loads.

Issues and questions welcome. If you're building something that needs agent
memory and this doesn't quite fit, say what's missing — that's genuinely useful.

## License

MIT
