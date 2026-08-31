"""
A paying agent — the buyer side of the x402 loop.

Given a paid endpoint, this client:
  1. calls it,
  2. on `402 Payment Required`, reads the requirements,
  3. checks the price is within its budget cap,
  4. SIGNS an EIP-3009 payment with its wallet, and
  5. retries with the `X-PAYMENT` header.

This is exactly what an autonomous agent's wallet does. Point it at
http_server.py to see the whole loop. With the server on FACILITATOR=coinbase
and a funded testnet wallet, this performs a REAL testnet payment.

    export AGENT_PRIVATE_KEY=0x...        # a THROWAWAY testnet key
    python agent_client.py

⚠️  SECURITY: never put a private key that holds real funds in an env var or a
    chat. Use a fresh wallet funded only with testnet tokens. The key stays on
    YOUR machine — it is never sent anywhere; only the signature is.
"""
from __future__ import annotations
import os

import httpx

import config
import x402_scheme

# Which server to buy from. Defaults to config.PUBLIC_URL (your local server
# unless PUBLIC_URL is set), so you can point the agent at production with:
#     PUBLIC_URL=https://your-app.fly.dev python agent_client.py
BASE = os.getenv("TARGET_URL", config.PUBLIC_URL).rstrip("/")
# Max the agent will pay for any single call (atomic USDC). Its budget guardrail.
# Keep this ABOVE your most expensive operation, or the agent will refuse to
# buy it. Override per-run with MAX_PAYMENT=<atomic units>.
MAX_PAYMENT_ATOMIC = int(os.getenv("MAX_PAYMENT", "50000"))  # 0.05 USDC


def _looks_like_key(value: str) -> bool:
    """A private key is 0x + 64 hex characters. Anything else is a paste error."""
    if not value.startswith("0x") or len(value) != 66:
        return False
    try:
        int(value[2:], 16)
        return True
    except ValueError:
        return False


def _agent_key() -> str:
    """Find the agent's signing key, in order of preference:
       1. AGENT_PRIVATE_KEY environment variable
       2. the .agent-wallet file written by new_agent_wallet.py
       3. a fresh throwaway (works against the mock facilitator only)
    """
    key = (os.getenv("AGENT_PRIVATE_KEY") or "").strip()
    if key:
        if _looks_like_key(key):
            return key
        # A leftover placeholder or a mangled paste. Say so plainly and fall
        # through to the saved wallet rather than dying in a hex decoder.
        print(f"[agent] ignoring AGENT_PRIVATE_KEY — not a valid key "
              f"(length {len(key)}, expected 66). Run `unset AGENT_PRIVATE_KEY` "
              f"to clear it.")

    try:
        import new_agent_wallet
        saved = new_agent_wallet.load()
    except Exception:
        saved = None
    if saved:
        from eth_account import Account
        print(f"[agent] using saved wallet {Account.from_key(saved).address}")
        return saved

    from eth_account import Account
    key = "0x" + Account.create().key.hex()
    print("[agent] no wallet found — using an unfunded throwaway. Run "
          "`python new_agent_wallet.py` and fund it to make real payments.")
    return key


def paid_post(path: str, json_body: dict, key: str) -> dict:
    """POST to a paid endpoint, paying the 402 if one comes back."""
    with httpx.Client(base_url=BASE, timeout=90) as client:
        resp = client.post(path, json=json_body)
        if resp.status_code != 402:
            resp.raise_for_status()
            return resp.json()

        requirements = resp.json()
        acc = requirements["accepts"][0]
        price = int(acc["maxAmountRequired"])
        print(f"[agent] 402 for {path}: {config.usdc(price)} to {acc['payTo']}")

        if price > MAX_PAYMENT_ATOMIC:
            raise RuntimeError(
                f"{path} costs {config.usdc(price)} but this agent's budget cap is "
                f"{config.usdc(MAX_PAYMENT_ATOMIC)}. Raise it with "
                f"MAX_PAYMENT={price * 2} or lower the price on the server."
            )

        # sign the payment and retry
        payment = x402_scheme.build_and_sign(key, acc["payTo"], price)
        header = x402_scheme.encode_header(payment)
        print(f"[agent] signed payment as {payment['payload']['authorization']['from']}; retrying")
        resp = client.post(path, json=json_body, headers={"X-PAYMENT": header})
        resp.raise_for_status()
        return resp.json()


def main():
    key = _agent_key()

    print(f"\n[agent] target: {BASE}")
    print("[agent] discovering pricing (free)… (first call may take ~30s if the server was asleep)")
    print("  ", httpx.get(f"{BASE}/pricing", timeout=90).json()["prices"])

    print("\n[agent] storing three memories (paying per write)…")
    for text in [
        "Our return window is 30 days from delivery.",
        "Priority support responds within 2 hours.",
        "We ship to the EU on Tuesdays and Thursdays.",
    ]:
        out = paid_post("/store", {"text": text}, key)
        print("   stored:", out["memory"]["id"][:8], "-", out["memory"]["text"])

    print("\n[agent] semantic search (paying once)…")
    q = "when can I send an item back?"
    out = paid_post("/search", {"query": q, "top_k": 3}, key)
    print(f'   query: "{q}"')
    for i, r in enumerate(out["results"], 1):
        print(f"   {i}. score={r['score']:.3f}  {r['text']}")

    print("\n[agent] done.\n")


if __name__ == "__main__":
    main()
