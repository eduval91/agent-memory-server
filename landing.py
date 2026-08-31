"""
The public landing page — served at / on your deployed server.

Two jobs:
  1. Explain the service to a human evaluating it (usually the developer of an
     agent that would pay you), with prices and copy-pasteable connection info.
  2. Capture demand: a short interest form posts to /interest, which lands in
     your ledger and shows up on the dashboard. Traffic becomes information.

Self-contained HTML — no build step, no CDN, light/dark aware.
"""
from __future__ import annotations

import config


def page() -> str:
    prices = "".join(
        f"<tr><td><code>{name}</code></td><td>{_desc(name)}</td>"
        f"<td class='num'>{config.usdc_short(atomic)}</td></tr>"
        for name, atomic in config.PRICES_ATOMIC.items()
    )
    base = config.PUBLIC_URL.rstrip("/")
    return _HTML.replace("{{PRICES}}", prices) \
                .replace("{{BASE}}", base) \
                .replace("{{NAME}}", config.SERVICE_NAME) \
                .replace("{{DESC}}", config.SERVICE_DESCRIPTION) \
                .replace("{{NETWORK}}", config.NETWORK)


def _desc(name: str) -> str:
    return {
        "store_memory": "Save a memory",
        "search_memory": "Semantic search over your memories",
        "retrieve_memory": "Fetch one memory by id",
    }.get(name, name)


_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{NAME}} — pay-per-call memory for AI agents</title>
<style>
  :root {
    color-scheme: light;
    --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e;
    --muted:#898781; --ring:rgba(11,11,11,0.10); --accent:#2a78d6;
    --code-bg:#f2f1ed;
  }
  @media (prefers-color-scheme: dark) {
    :root { color-scheme: dark;
      --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink-2:#c3c2b7;
      --muted:#898781; --ring:rgba(255,255,255,0.10); --accent:#3987e5;
      --code-bg:#232322; }
  }
  * { box-sizing:border-box; margin:0; }
  body { background:var(--page); color:var(--ink);
    font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;
    padding:32px 20px 64px; max-width:820px; margin:0 auto; }
  h1 { font-size:30px; font-weight:650; letter-spacing:-0.02em; margin-bottom:10px; }
  h2 { font-size:15px; font-weight:600; margin:32px 0 12px; }
  .lede { color:var(--ink-2); font-size:17px; margin-bottom:8px; }
  .chip { display:inline-block; font-size:12px; color:var(--ink-2);
    border:1px solid var(--ring); border-radius:999px; padding:3px 10px; margin-top:14px; }
  .panel { background:var(--surface); border:1px solid var(--ring);
    border-radius:10px; padding:16px 18px; margin:12px 0; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th { text-align:left; color:var(--muted); font-weight:500; padding:6px 8px;
       border-bottom:1px solid var(--ring); font-size:12.5px; }
  td { padding:8px; border-bottom:1px solid var(--ring); color:var(--ink-2); }
  td.num { text-align:right; color:var(--ink); font-variant-numeric:tabular-nums; white-space:nowrap; }
  code { background:var(--code-bg); padding:1px 5px; border-radius:4px;
    font:13px ui-monospace,monospace; }
  pre { background:var(--code-bg); border-radius:8px; padding:12px 14px;
    overflow-x:auto; font:12.5px/1.5 ui-monospace,monospace; color:var(--ink); }
  ol { padding-left:20px; color:var(--ink-2); } ol li { margin:6px 0; }
  input, textarea { width:100%; font:14px system-ui,sans-serif; color:var(--ink);
    background:var(--page); border:1px solid var(--ring); border-radius:7px;
    padding:9px 11px; margin-top:8px; }
  button { margin-top:10px; background:var(--accent); color:#fff; border:0;
    border-radius:7px; padding:9px 16px; font:600 14px system-ui,sans-serif; cursor:pointer; }
  button:hover { filter:brightness(1.08); }
  .ok { color:#0ca30c; font-size:13.5px; margin-top:8px; }
  footer { color:var(--muted); font-size:12.5px; margin-top:40px; }
  a { color:var(--accent); }
</style>
</head>
<body>
  <h1>{{NAME}}</h1>
  <p class="lede">{{DESC}}</p>
  <span class="chip">x402 · pay per call · {{NETWORK}}</span>

  <h2>Why agents use it</h2>
  <div class="panel">
    An agent's context window forgets everything between runs. This service gives it a
    memory that persists — and one it can search by <em>meaning</em>, so
    “when can I send an item back?” finds “our return window is 30 days” without
    sharing a single keyword. Memories are private per paying wallet.
  </div>

  <h2>Pricing</h2>
  <div class="panel">
    <table>
      <tr><th>operation</th><th>what it does</th><th style="text-align:right">price</th></tr>
      {{PRICES}}
    </table>
    <p style="color:var(--muted);font-size:12.5px;margin-top:10px">
      No subscription, no minimum, no account. Payment settles per call in USDC over x402.
    </p>
  </div>

  <h2>Connect an agent</h2>
  <div class="panel">
    <p style="color:var(--ink-2);margin-bottom:10px"><strong>MCP</strong> — add this server:</p>
    <pre>{{BASE}}/mcp</pre>
    <p style="color:var(--ink-2);margin:14px 0 10px"><strong>HTTP</strong> — call it directly:</p>
    <pre>curl {{BASE}}/pricing

# paid endpoints answer 402 with payment requirements,
# then serve the result when you retry with an X-PAYMENT header
curl -X POST {{BASE}}/search -d '{"query":"refund policy"}'</pre>
    <p style="color:var(--muted);font-size:12.5px;margin-top:10px">
      Any x402 client library handles the 402 → pay → retry loop for you.
    </p>
  </div>

  <h2>How paying works</h2>
  <ol>
    <li>Your agent calls an endpoint with no payment.</li>
    <li>It gets <code>402 Payment Required</code> with the price and address.</li>
    <li>Its wallet signs the payment and retries with an <code>X-PAYMENT</code> header.</li>
    <li>The result comes back. Total added latency: one round trip.</li>
  </ol>

  <h2>Get in touch</h2>
  <div class="panel">
    <p style="color:var(--ink-2)">Building something that needs agent memory? Tell me what you need —
      I read every message.</p>
    <form id="f">
      <input name="contact" placeholder="Email or handle" required>
      <textarea name="note" rows="3" placeholder="What are you building, and what would you need from a memory service?"></textarea>
      <button type="submit">Send</button>
      <div class="ok" id="ok" hidden>Thanks — got it.</div>
    </form>
  </div>

  <footer>Runs on the open <a href="https://x402.org">x402</a> payment protocol and the
    <a href="https://modelcontextprotocol.io">Model Context Protocol</a>.</footer>

<script>
document.getElementById("f").addEventListener("submit", async e => {
  e.preventDefault();
  const f = e.target;
  try {
    await fetch("/interest", {
      method: "POST", headers: {"content-type": "application/json"},
      body: JSON.stringify({contact: f.contact.value, note: f.note.value})
    });
    f.reset();
    document.getElementById("ok").hidden = false;
  } catch (_) {
    document.getElementById("ok").textContent = "Couldn't send — please try again.";
    document.getElementById("ok").hidden = false;
  }
});
</script>
</body>
</html>
"""
