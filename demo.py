"""
End-to-end demo: an autonomous agent uses the paid memory service.

Runs the WHOLE loop in-process (no server needed) so you can watch it:
  1. discover pricing (free)
  2. store a few memories — each one a paid x402 operation
  3. run a semantic search — see the 402 challenge, pay, then get ranked results

    python demo.py

Uses the mock facilitator (config.FACILITATOR=mock) so no real crypto moves.
The exact same code paths run in mcp_server.py for real agents.
"""
from __future__ import annotations
import json

import config
import payments
from memory_store import MemoryStore


def line(c="─"):
    print(c * 70)


def agent_calls(tool_name: str, store: MemoryStore, agent_key: str, **kwargs):
    """Simulate an agent calling a paid tool: first unpaid (get 402), then pay."""
    resource = f"mcp://agent-memory/{tool_name}"

    # --- attempt 1: no payment ---
    allowed, requirements, _ = payments.check_payment(tool_name, None, resource)
    if not allowed:
        price = int(requirements["accepts"][0]["maxAmountRequired"])
        print(f"  → called {tool_name} with no payment")
        print(f"  ← 402 Payment Required: {config.usdc(price)} to {requirements['accepts'][0]['payTo']}")
        # --- agent's wallet SIGNS an EIP-3009 payment and retries ---
        token = payments.sign_payment(agent_key, requirements)
        allowed, _, info = payments.check_payment(tool_name, token, resource)
        print(f"  → retried with signed X-PAYMENT; verified={allowed} payer={info.get('payer')}")
    if not allowed:
        raise RuntimeError("payment failed")

    # payment cleared — perform the actual operation
    if tool_name == "store_memory":
        return store.store(kwargs["namespace"], kwargs["text"], kwargs.get("metadata"))
    if tool_name == "search_memory":
        return store.search(kwargs["namespace"], kwargs["query"], kwargs.get("top_k", 5))
    raise ValueError(tool_name)


def main():
    store = MemoryStore()
    print(f"\nembeddings: {store.embedder.name} | "
          f"facilitator: {config.FACILITATOR} | network: {config.NETWORK}")
    if store.embedder.name.startswith("hashing"):
        print("NOTE: running the dependency-free 'hashing' embedder (lexical only).")
        print("      Install requirements.txt for real semantic matching by meaning.")
    print()
    # A throwaway agent wallet. Its address IS the agent's identity/namespace —
    # in production you'd namespace memories by the verified payer address.
    from eth_account import Account
    agent_key = payments.new_test_key()
    agent = Account.from_key(agent_key).address
    print(f"agent wallet (throwaway): {agent}\n")

    line("═")
    print("STEP 1  Discover pricing (free)")
    line()
    prices = {n: config.usdc(a) for n, a in config.PRICES_ATOMIC.items()}
    print("  " + json.dumps(prices))

    line("═")
    print("STEP 2  Agent stores memories (each a paid write)")
    line()
    facts = [
        ("Customer refunds are processed within 5 business days.", {"topic": "billing"}),
        ("The office is closed on federal holidays.", {"topic": "hr"}),
        ("To reset a password, use the 'Forgot password' link on the login page.", {"topic": "support"}),
        ("Enterprise plans include a dedicated account manager.", {"topic": "sales"}),
        ("Shipping to Canada takes 7-10 business days.", {"topic": "logistics"}),
    ]
    for text, meta in facts:
        rec = agent_calls("store_memory", store, agent_key, namespace=agent, text=text, metadata=meta)
        print(f"  stored [{rec['id'][:8]}] {rec['text']}")
        print()

    line("═")
    print("STEP 3  Agent runs a SEMANTIC search (pays once, matches by meaning)")
    line()
    query = "how long until I get my money back?"
    print(f'  query: "{query}"  (note: no shared keywords with the stored refund fact)\n')
    results = agent_calls("search_memory", store, agent_key, namespace=agent, query=query, top_k=3)
    for i, r in enumerate(results, 1):
        print(f"  {i}. score={r['score']:.3f}  {r['text']}")

    line("═")
    if store.embedder.name.startswith("hashing"):
        print("Done. (With real embeddings the refund fact ranks #1 despite sharing")
        print("no keywords with the query — that's the semantic value agents pay for.)")
    else:
        print("Done. The top hit is the refund fact — matched by MEANING, not keywords,")
        print("and the agent paid per operation over x402.")
    line("═")


if __name__ == "__main__":
    main()
