# Taking a real payment on Base Sepolia (testnet)

This walks you from the mock loop to a **real on-chain payment** using free
testnet money. Nothing here risks real funds. Budget ~20 minutes.

> ⚠️ **Security first.** You'll create a *throwaway* wallet used only for
> testnet. Never paste a seed phrase or a private key that holds real money into
> a terminal, an env file you sync, or a chat. The agent's private key stays on
> your machine and is only ever used locally to *sign*; it is never transmitted.

---

## 1. Create two throwaway wallets

You need two identities: your **service** (receives money) and a **test agent**
(pays). Any EVM wallet works — e.g. Coinbase Wallet, or generate keys locally:

```bash
python -c "from eth_account import Account; a=Account.create(); print('addr', a.address); print('key ', '0x'+a.key.hex())"
```

Run it twice. Keep one as the **service** (you only need its address) and one as
the **agent** (you need its private key to sign).

## 2. Fund the agent wallet with testnet tokens

The agent needs a little Base Sepolia ETH (for gas the facilitator estimates)
and some Base Sepolia USDC (to pay you). Get both from faucets:

- Base Sepolia ETH: the Coinbase Developer / Base faucet
- Base Sepolia USDC: Circle's testnet faucet

Search "Base Sepolia faucet" and "Circle USDC testnet faucet" — send both to the
**agent** address from step 1.

## 3. Point the server at your wallet + the real facilitator

In `.env` (copy from `.env.example`):

```bash
FACILITATOR=coinbase
NETWORK=base-sepolia
RECEIVING_WALLET=0xYOUR_SERVICE_ADDRESS        # from step 1
USDC_ADDRESS=0x036CbD53842c5426634e7929541eC2318f3dCF7e   # Base Sepolia USDC
USDC_NAME=USDC                                 # must match the token's EIP-712 domain
USDC_VERSION=2
FACILITATOR_URL=https://x402.org/facilitator   # confirm current URL at x402.org
```

> **Two things to verify against current docs** (the spec is young and moving):
> 1. the **facilitator URL and request schema** (`payments.py` sends
>    `{x402Version, paymentPayload, paymentRequirements}` to `/verify` and
>    `/settle` — some facilitators want `paymentHeader` instead), and
> 2. the **USDC EIP-712 `name`/`version`** for the exact contract you use — a
>    mismatch makes real signatures fail to settle. Check the token's `name()`
>    on a block explorer.

## 4. Run the server and pay it for real

```bash
# terminal 1 — your paid service
python http_server.py

# terminal 2 — the paying agent (real testnet payment)
export AGENT_PRIVATE_KEY=0xYOUR_AGENT_KEY       # throwaway, from step 1
python agent_client.py
```

**What success looks like:** the agent gets a `402`, signs, retries, and the
server's `settle` call returns a **transaction hash**. Paste that hash into
https://sepolia.basescan.org to see the USDC move from the agent to your service
wallet. That's a real (testnet) pay-per-call transaction — the whole business,
proven.

---

## 5. Go to mainnet

When the testnet loop works, flip three things and start with tiny prices:

```bash
NETWORK=base
USDC_ADDRESS=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913   # Base mainnet USDC
USDC_NAME="USD Coin"                                        # mainnet USDC domain name
```

Before real traffic, add: request-size limits, rate limiting / per-agent
quotas, persistent storage for memories, monitoring, and a real vector DB (see
the README "production-grade" section). Then list your server in MCP registries
and x402 directories so agents can find it.
