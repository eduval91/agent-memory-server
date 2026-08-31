# Getting found — the discovery checklist

Code is roughly 20% of this business. **Discovery is most of the rest.** An
agent cannot pay a service it cannot find. Work this list top to bottom; the
first item is the highest-leverage and takes the least effort.

Prerequisite: a deployed HTTPS URL (see DEPLOY.md). Everything below needs it.

---

## 1. x402 Bazaar — the one that matters most

The Bazaar is the discovery layer agents actually query when shopping for paid
services: `GET {facilitator}/discovery/resources`, plus natural-language search
like *"memory for agents"*. This is where an autonomous buyer finds you with no
human involved.

**You're already wired for it.** `payments.py` attaches a `bazaar` extension to
every payment requirement — service name, description, and tags from your
`.env`. Listing happens automatically as payments settle; there's no form.

What to do:

- Set `SERVICE_NAME`, `SERVICE_DESCRIPTION`, and `SERVICE_TAGS` in `.env` — these
  are what agents search against, so write the description for a *buyer*
  ("remembers things for your agent between runs") not a developer.
- Deploy, then make one real payment against the deployed server.
- Verify you appear: `curl "{facilitator}/discovery/resources?type=http"` and
  look for your resource URL.
- ⚠️ Confirm the extension's exact field placement against
  https://docs.x402.org/extensions/bazaar — the discovery layer is newer than
  the core spec, and the code carries a `TODO` at that spot.

## 2. Official MCP Registry

`server.json` in this folder is ready. Before submitting:

- Replace `YOUR_GITHUB_USERNAME` and `YOUR-APP.fly.dev` throughout.
- Push the project to a public GitHub repo (the registry verifies namespace
  ownership via GitHub auth for `io.github.*` names).
- Publish with the registry's `mcp-publisher` CLI and authenticate with GitHub.
- Docs: https://github.com/modelcontextprotocol/registry

## 3. The MCP directories people actually browse

These drive the human discovery that leads to integrations. Each takes minutes:

- **Glama** (glama.ai/mcp/servers) — submit your repo
- **Smithery** (smithery.ai) — supports remote servers
- **PulseMCP** (pulsemcp.com) — directory + newsletter
- **mcp.so** — large public index
- **awesome-mcp-servers** on GitHub — open a PR adding your entry

Use the same one-line description everywhere so your service reads as one thing.

## 4. Where the humans are

Registries are passive. These are where the people building agents talk:

- The x402 developer community (Discord/Telegram linked from x402.org) — say
  what you built; working x402 services are still rare enough to be interesting.
- r/mcp and r/LocalLLaMA — a "here's what I built and what it cost" post does
  well when it's concrete.
- Hacker News **Show HN** — best after your service has run for a bit and you
  can show real numbers.
- Direct outreach: find 10 people shipping agent frameworks and message them.
  Ten specific messages beat a thousand impressions.

## 5. Make the traffic tell you something

Your `/dashboard` shows **Inbound interest** from the landing-page form, and
every `/pricing` hit is logged as a free call. So you can distinguish:

- **nobody arrives** → a distribution problem; work items 3–4 harder.
- **they arrive and read pricing but never pay** → a pricing or trust problem;
  the interest notes will usually tell you which.
- **they pay once and don't return** → a product problem; look at what they
  searched and whether the results were good.

Those three cases need completely different fixes. Guessing between them is the
most common way builders waste months.

---

## A calibration note

The honest picture: the agent-payments economy is early. There is not yet a
large population of funded autonomous agents shopping for services, which means
low competition *and* thin demand today. Being listed everywhere is necessary
but not sufficient — the fastest signal will almost certainly come from item 4,
talking to people directly, not from waiting on a registry.
