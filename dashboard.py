"""
The operator dashboard — open it in a browser while your server runs and watch
who's connecting and what you're earning.

Served by BOTH servers:
    http_server.py  ->  http://127.0.0.1:8402/dashboard
    mcp_server.py   ->  http://127.0.0.1:8402/dashboard

/api/metrics returns the JSON the page polls (every 4s), straight from ledger.py.
The page is a single self-contained HTML string: no build step, no CDN, works
offline, light/dark aware.
"""
from __future__ import annotations

import config
import ledger
import memory_store

_EXPLORERS = {
    "base-sepolia": "https://sepolia.basescan.org",
    "base": "https://basescan.org",
}


def metrics() -> dict:
    data = ledger.summary()
    data["memory"] = memory_store.stats()
    data["config"] = {
        "network": config.NETWORK,
        "facilitator": config.FACILITATOR,
        "wallet": config.RECEIVING_WALLET,
        "x402_enabled": config.X402_ENABLED,
        "explorer": _EXPLORERS.get(config.NETWORK, ""),
        "prices": {n: config.usdc(a) for n, a in config.PRICES_ATOMIC.items()},
    }
    return data


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Memory — Earnings</title>
<style>
  :root {
    color-scheme: light;
    --page: #f9f9f7; --surface: #fcfcfb;
    --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
    --grid: #e1e0d9; --baseline: #c3c2b7; --ring: rgba(11,11,11,0.10);
    --series: #2a78d6;
    --good: #0ca30c; --warning: #fab219; --critical: #d03b3b;
    --good-text: #006300;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      color-scheme: dark;
      --page: #0d0d0d; --surface: #1a1a19;
      --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --baseline: #383835; --ring: rgba(255,255,255,0.10);
      --series: #3987e5;
      --good-text: #0ca30c;
    }
  }
  * { box-sizing: border-box; margin: 0; }
  body {
    background: var(--page); color: var(--ink);
    font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 24px; max-width: 1060px; margin: 0 auto;
  }
  header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
  h1 { font-size: 18px; font-weight: 650; }
  .sub { color: var(--muted); font-size: 12.5px; }
  .live { color: var(--good-text); font-size: 12.5px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }
  .card, .panel {
    background: var(--surface); border: 1px solid var(--ring);
    border-radius: 10px; padding: 14px 16px;
  }
  .card .label { color: var(--ink-2); font-size: 12.5px; margin-bottom: 6px; }
  .card .value { font-size: 30px; font-weight: 600; }
  .card .hint { color: var(--muted); font-size: 12px; margin-top: 4px; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }
  @media (max-width: 760px) { .grid2 { grid-template-columns: 1fr; } }
  .panel h2 { font-size: 13px; font-weight: 600; color: var(--ink-2); margin-bottom: 12px; }
  /* horizontal bars: revenue by tool */
  .hrow { display: grid; grid-template-columns: 120px 1fr 84px; gap: 10px; align-items: center; margin: 8px 0; }
  .hrow .name { color: var(--ink-2); font-size: 12.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .htrack { height: 18px; position: relative; }
  .hbar { position: absolute; left: 0; top: 0; bottom: 0; background: var(--series);
          border-radius: 0 4px 4px 0; min-width: 2px; }
  .hrow .val { font-size: 12.5px; color: var(--ink); text-align: right; font-variant-numeric: tabular-nums; }
  /* daily columns */
  .cols { display: flex; align-items: flex-end; gap: 6px; height: 120px;
          border-bottom: 1px solid var(--baseline); padding-bottom: 0; }
  .colwrap { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-end; position: relative; }
  .col { width: 100%; max-width: 24px; background: var(--series); border-radius: 4px 4px 0 0; min-height: 2px; }
  .colwrap:hover .col { filter: brightness(1.12); }
  .cols-x { display: flex; gap: 6px; margin-top: 6px; }
  .cols-x span { flex: 1; text-align: center; color: var(--muted); font-size: 10.5px; overflow: hidden; }
  /* table */
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  th { text-align: left; color: var(--muted); font-weight: 500; padding: 6px 8px;
       border-bottom: 1px solid var(--grid); }
  td { padding: 6px 8px; border-bottom: 1px solid var(--grid); color: var(--ink-2);
       font-variant-numeric: tabular-nums; }
  td.addr { font-family: ui-monospace, monospace; font-size: 11.5px; }
  .badge { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; color: var(--ink-2); }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .k-paid .dot { background: var(--good); }
  .k-rejected .dot { background: var(--critical); }
  .k-challenge .dot { background: var(--warning); }
  .k-free .dot { background: var(--muted); }
  .empty { color: var(--muted); padding: 18px 0; text-align: center; }
  .txlink { color: var(--series); text-decoration: none; }
  .txlink:hover { text-decoration: underline; }
  #tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink);
         border: 1px solid var(--ring); border-radius: 6px; padding: 6px 9px; font-size: 12px;
         box-shadow: 0 2px 8px rgba(0,0,0,.12); display: none; z-index: 10; }
  footer { color: var(--muted); font-size: 11.5px; margin-top: 18px; }
</style>
</head>
<body>
<header>
  <h1>Agent Memory — Earnings</h1>
  <span class="sub" id="cfg">…</span>
  <span class="live" id="live"></span>
</header>

<div class="cards">
  <div class="card"><div class="label">Settled revenue</div><div class="value" id="m-rev">–</div><div class="hint" id="m-revsub"></div></div>
  <div class="card"><div class="label">Paid calls</div><div class="value" id="m-calls">–</div><div class="hint" id="m-callssub"></div></div>
  <div class="card"><div class="label">Unique paying agents</div><div class="value" id="m-payers">–</div><div class="hint">by wallet address</div></div>
  <div class="card"><div class="label">Memories stored</div><div class="value" id="m-mem">–</div><div class="hint" id="m-memsub"></div></div>
  <div class="card"><div class="label">Revenue today</div><div class="value" id="m-today">–</div><div class="hint" id="m-todaysub"></div></div>
</div>

<div class="grid2">
  <div class="panel"><h2>Revenue by operation</h2><div id="bytool"><div class="empty">no paid calls yet</div></div></div>
  <div class="panel"><h2>Daily revenue — last 14 days</h2><div id="daily"><div class="empty">no paid calls yet</div></div></div>
</div>

<div class="panel" style="margin-bottom:12px">
  <h2>Top paying agents</h2>
  <div id="payers"><div class="empty">no paid calls yet</div></div>
</div>

<div class="panel" style="margin-bottom:12px">
  <h2>Inbound interest <span style="font-weight:400;color:var(--muted)">— from the landing page</span></h2>
  <div id="interest"><div class="empty">no enquiries yet</div></div>
</div>

<div class="panel">
  <h2>Recent activity</h2>
  <div id="recent"><div class="empty">nothing yet — point an agent at the server</div></div>
</div>

<div id="tip"></div>
<footer>Auto-refreshes every 4 seconds from /api/metrics. Amounts in USDC.</footer>

<script>
const num = a => (a / 1e6).toLocaleString(undefined, {minimumFractionDigits: 4, maximumFractionDigits: 6});
const usdc = a => num(a) + " USDC";
const short = a => a ? a.slice(0, 8) + "…" + a.slice(-4) : "—";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const tip = document.getElementById("tip");
function showTip(e, html) { tip.innerHTML = html; tip.style.display = "block"; moveTip(e); }
function moveTip(e) { tip.style.left = Math.min(e.clientX + 14, innerWidth - 180) + "px"; tip.style.top = (e.clientY + 14) + "px"; }
function hideTip() { tip.style.display = "none"; }

async function refresh() {
  let d;
  try { d = await (await fetch("/api/metrics")).json(); }
  catch { document.getElementById("live").textContent = "· disconnected"; return; }
  document.getElementById("live").textContent = "· live";
  const c = d.config;
  document.getElementById("cfg").textContent =
    c.network + " · " + c.facilitator + " facilitator · pay-to " + short(c.wallet);

  const settled = d.revenue_atomic - d.revenue_mock_atomic;
  document.getElementById("m-rev").textContent = num(settled);
  document.getElementById("m-revsub").textContent = "USDC on-chain" +
    (d.revenue_mock_atomic > 0 ? " · +" + num(d.revenue_mock_atomic) + " mock (excluded)" : "") +
    " · " + d.rejected + " rejected";
  document.getElementById("m-calls").textContent = d.paid_calls.toLocaleString();
  document.getElementById("m-callssub").textContent = d.paid_calls_today + " today" +
    (d.paid_calls_mock > 0 ? " · " + d.paid_calls_mock + " mock" : "");
  document.getElementById("m-payers").textContent = d.unique_payers.toLocaleString();
  document.getElementById("m-mem").textContent = d.memory.memories.toLocaleString();
  document.getElementById("m-memsub").textContent = "across " + d.memory.namespaces + " agent" + (d.memory.namespaces === 1 ? "" : "s");
  document.getElementById("m-today").textContent = num(d.revenue_today_atomic);
  document.getElementById("m-todaysub").textContent = "USDC on-chain · last 24 hours";

  // revenue by tool — horizontal bars, one measure, direct value labels
  const bt = document.getElementById("bytool");
  if (d.by_tool.length) {
    const max = Math.max(...d.by_tool.map(r => r.revenue), 1);
    bt.innerHTML = d.by_tool.map(r =>
      `<div class="hrow" data-tip="${esc(r.tool)}: ${usdc(r.revenue)} over ${r.calls} calls">
         <div class="name">${esc(r.tool)}</div>
         <div class="htrack"><div class="hbar" style="width:${Math.max(100 * r.revenue / max, 1)}%"></div></div>
         <div class="val">${usdc(r.revenue)}</div>
       </div>`).join("");
  } else bt.innerHTML = '<div class="empty">no paid calls yet</div>';

  // daily columns
  const dv = document.getElementById("daily");
  if (d.daily.length) {
    const max = Math.max(...d.daily.map(r => r.revenue), 1);
    dv.innerHTML =
      '<div class="cols">' + d.daily.map(r =>
        `<div class="colwrap" data-tip="${r.day}: ${usdc(r.revenue)} (${r.calls} calls)">
           <div class="col" style="height:${Math.max(100 * r.revenue / max, 2)}%"></div>
         </div>`).join("") + "</div>" +
      '<div class="cols-x">' + d.daily.map(r => `<span>${r.day.slice(5)}</span>`).join("") + "</div>";
  } else dv.innerHTML = '<div class="empty">no paid calls yet</div>';

  // top payers
  const tp = document.getElementById("payers");
  tp.innerHTML = d.top_payers.length
    ? "<table><tr><th>agent (wallet)</th><th>calls</th><th>revenue</th></tr>" +
      d.top_payers.map(r => {
        const who = c.explorer && /^0x[0-9a-fA-F]{40}$/.test(r.payer ?? "")
          ? `<a class="txlink" href="${c.explorer}/address/${r.payer}" target="_blank" rel="noopener">${esc(short(r.payer))} ↗</a>`
          : esc(short(r.payer));
        return `<tr><td class="addr">${who}</td><td>${r.calls}</td><td>${usdc(r.revenue)}</td></tr>`;
      }).join("") +
      "</table>"
    : '<div class="empty">no paid calls yet</div>';

  // inbound interest (demand signal)
  const iv = document.getElementById("interest");
  iv.innerHTML = (d.interest && d.interest.length)
    ? "<table><tr><th>when</th><th>contact</th><th>what they said</th></tr>" +
      d.interest.map(r =>
        `<tr><td>${new Date(r.ts * 1000).toLocaleDateString()}</td>
             <td>${esc(r.contact)}</td><td>${esc(r.note || "—")}</td></tr>`).join("") +
      "</table>"
    : '<div class="empty">no enquiries yet</div>';

  // recent events
  const rc = document.getElementById("recent");
  rc.innerHTML = d.recent.length
    ? "<table><tr><th>time</th><th>event</th><th>operation</th><th>agent</th><th>amount</th><th>detail</th></tr>" +
      d.recent.map(r => {
        const t = new Date(r.ts * 1000).toLocaleTimeString();
        const amt = r.kind === "paid" ? usdc(r.amount_atomic) : "—";
        let detail = esc(r.detail ?? "");
        if (c.explorer && /^0x[0-9a-fA-F]{64}$/.test(r.detail ?? "")) {
          detail = `<a class="txlink" href="${c.explorer}/tx/${r.detail}" target="_blank" rel="noopener">${esc(r.detail.slice(0, 10))}… ↗</a>`;
        }
        return `<tr>
          <td>${t}</td>
          <td><span class="badge k-${esc(r.kind)}"><span class="dot"></span>${esc(r.kind)}</span></td>
          <td>${esc(r.tool)}</td>
          <td class="addr">${esc(short(r.payer))}</td>
          <td>${amt}</td>
          <td>${detail}</td></tr>`;
      }).join("") + "</table>"
    : '<div class="empty">nothing yet — point an agent at the server</div>';

  // wire tooltips
  document.querySelectorAll("[data-tip]").forEach(el => {
    el.onmousemove = e => { showTip(e, esc(el.dataset.tip)); };
    el.onmouseleave = hideTip;
  });
}
refresh();
setInterval(refresh, 4000);
</script>
</body>
</html>
"""
