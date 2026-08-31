# Deploying — from `127.0.0.1` to a URL agents can pay

Right now your server answers only your own laptop. Agents can't buy from a
service they can't reach. This gets you a public HTTPS URL.

**Stay on testnet for the first deploy.** Get the deployment working with
play money, then flip to mainnet (last section). Nothing here risks real funds.

---

## What you're deploying

A container that runs `serve.py`, which serves BOTH interfaces on one URL:

| path | who it's for |
|---|---|
| `/` | humans evaluating your service (landing page) |
| `/mcp` | agents connecting over MCP (streamable-HTTP) |
| `/pricing`, `/store`, `/search`, `/retrieve` | agents paying per call over REST |
| `/dashboard` | **you** — revenue and activity (password-protected) |
| `/health` | your host's health checks |

`http_server.py` and `mcp_server.py` still run standalone for local development;
`serve.py` combines them for deployment so one public URL offers both, backed by
a single shared memory store.

---

## Two things to get right before you push

**1. Memory needs ~1GB RAM.** The embedding model loads into memory. A 512MB
instance will be killed by the OS. Pick at least **1GB** (2GB comfortable).
If you'd rather run tiny and cheap, set `EMBEDDINGS_PROVIDER=openai` with an
`OPENAI_API_KEY` — the container drops to ~150MB and starts in seconds, at a
cost of roughly $0.00002 per embedding (negligible against a $0.01 search).

**2. Your data must live on a volume.** Memories and your ledger are SQLite
files in `/app/data`. Without a mounted persistent volume, **every redeploy
erases your customers' memories and your revenue history.** The Dockerfile
declares the volume; your host still needs to attach one.

---

## Recommended: Fly.io

Good fit because it gives you a persistent volume and HTTPS automatically on a
small paid instance.

```bash
# one-time
brew install flyctl
fly auth signup

cd ~/Documents/agent-memory-server
fly launch --no-deploy          # name the app, pick a region near your users
fly volumes create data --size 1 --region <your-region>
```

In the generated `fly.toml`, mount the volume and set the port:

```toml
[[mounts]]
  source = "data"
  destination = "/app/data"

[http_service]
  internal_port = 8402
  force_https = true
```

Set your configuration as secrets (never bake `.env` into an image):

```bash
fly secrets set \
  RECEIVING_WALLET=0x2279e4aC60A1746fa7526e902C00Cf8F2373B350 \
  FACILITATOR=coinbase \
  NETWORK=base-sepolia \
  USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e \
  PUBLIC_URL=https://<your-app>.fly.dev \
  SERVICE_NAME="Agent Memory" \
  DASHBOARD_PASSWORD='<a long random password>' 

fly deploy
```

Then open `https://<your-app>.fly.dev` — landing page — and
`https://<your-app>.fly.dev/dashboard`.

**Alternatives:** Railway and Render work the same way (connect the repo, add a
persistent disk mounted at `/app/data`, set the same env vars). A plain VPS
(DigitalOcean, Hetzner) also works — run the container behind Caddy or nginx for
HTTPS. The requirements are identical everywhere: ≥1GB RAM, a persistent volume
at `/app/data`, HTTPS, and the env vars above.

---

## Test it like a customer

```bash
curl https://<your-app>.fly.dev/health
curl https://<your-app>.fly.dev/pricing

# should answer 402 with your payment requirements
curl -X POST https://<your-app>.fly.dev/search -d '{"query":"test"}'
```

Then point `agent_client.py` at it by setting `PUBLIC_URL` locally, and run a
real testnet payment against the deployed server. When that transaction appears
on your deployed dashboard, deployment is genuinely done.

---

## Locking it down before real money

- **Set `DASHBOARD_PASSWORD`.** The dashboard shows your revenue, your
  customers' wallet addresses, and every landing-page enquiry. Once the server
  binds publicly it demands HTTP Basic auth, and if no password is set it
  **refuses to render at all** rather than leaking your numbers — so a missing
  password shows up as a broken dashboard, never as a silent exposure:

  ```bash
  fly secrets set DASHBOARD_PASSWORD='<a long random password>'
  ```

  Log in with user `admin` (change via `DASHBOARD_USER`). On localhost no
  password is needed, so your local workflow is unchanged.
- Set `RATE_LIMIT_PER_MIN` for real traffic (default 60/min per client).
- Keep `.env` out of git — it's already in `.dockerignore`.
- Back up `/app/data` on a schedule; it holds every memory you've been paid for.
- Watch `fly logs` (or your host's equivalent) for `rejected` payment reasons.

---

## Going to mainnet

Only after a deployed testnet payment works end to end:

```bash
fly secrets set \
  NETWORK=base \
  USDC_ADDRESS=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  USDC_NAME="USD Coin"
```

Verify the mainnet USDC address against Circle's official docs before you set
it — sending real payments to a wrong contract address is unrecoverable. Start
with your current prices and adjust once you see real usage.
