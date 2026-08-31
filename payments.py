"""
The x402 pay-per-operation layer.

x402 revives the dormant HTTP 402 "Payment Required" status code so an
autonomous agent can pay mid-request, with no account and no API key:

    1. Agent calls a paid operation.
    2. Server replies 402 with *payment requirements* (price, your wallet,
       network, which stablecoin).
    3. The agent's wallet builds a payment and retries with an `X-PAYMENT` header.
    4. Server verifies the payment (via a facilitator) and serves the result.

You never write blockchain code: a *facilitator* verifies and settles for you.
This module ships two:
  - MockFacilitator     : accepts a well-formed mock payment. No crypto. For
                          local dev and understanding the loop end-to-end.
  - CoinbaseX402Facilitator : calls a real hosted facilitator (testnet or
                          mainnet). Wired with the right shapes + TODO markers.

Swap between them with FACILITATOR=mock|coinbase in config.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

import httpx

import config
import x402_scheme


# ---------------------------------------------------------------------------
# Payment requirements — the body of a 402 response (x402 "accepts" shape).
# ---------------------------------------------------------------------------
# Human-readable descriptions of each operation. These are what an agent reads
# in the Bazaar when deciding whether to buy — write them for a buyer, not a
# developer.
_TOOL_DESCRIPTIONS = {
    "store_memory": "Store a text memory for later semantic retrieval.",
    "search_memory": "Search your stored memories by MEANING and get ranked results.",
    "retrieve_memory": "Fetch one previously stored memory by its id.",
}


def _bazaar_extension(tool_name: str) -> dict:
    """x402 Bazaar discovery metadata.

    Attaching this to payment requirements is what lists the service in the
    Bazaar — agents then find it via the facilitator's /discovery/resources
    endpoint or a natural-language search. No separate registration step.

    TODO: confirm the exact placement/field names for the bazaar extension
    against https://docs.x402.org/extensions/bazaar for the version your
    facilitator runs — the discovery layer is newer than the core spec.
    """
    return {
        "serviceName": config.SERVICE_NAME[:32],
        "description": f"{config.SERVICE_DESCRIPTION} — {_TOOL_DESCRIPTIONS.get(tool_name, tool_name)}",
        "tags": config.SERVICE_TAGS,
        **({"iconUrl": config.SERVICE_ICON_URL} if config.SERVICE_ICON_URL else {}),
    }


def build_requirements(tool_name: str, price_atomic: int, resource: str) -> dict:
    """The 402 body telling an agent exactly how to pay for this operation."""
    return {
        "x402Version": config.X402_VERSION,
        "accepts": [
            {
                "scheme": "exact",
                "network": config.NETWORK,
                "maxAmountRequired": str(price_atomic),  # atomic USDC units
                "resource": resource,
                "description": f"{tool_name} — {config.usdc(price_atomic)}",
                "mimeType": "application/json",
                "payTo": config.RECEIVING_WALLET,
                "asset": config.USDC_ADDRESS,
                "maxTimeoutSeconds": 60,
                "extra": {"name": "USDC", "version": "2"},
                "extensions": {"bazaar": _bazaar_extension(tool_name)},
            }
        ],
    }


@dataclass
class VerifyResult:
    ok: bool
    reason: str = ""
    payer: str = ""


# ---------------------------------------------------------------------------
# Facilitators
# ---------------------------------------------------------------------------
class Facilitator(Protocol):
    def verify(self, x_payment: str, requirements: dict) -> VerifyResult: ...
    def settle(self, x_payment: str, requirements: dict) -> dict: ...


class MockFacilitator:
    """Verifies a REAL signed x402 payment offline. NO on-chain settlement.

    It runs the same checks a facilitator does off-chain — recovers the EIP-3009
    signature, confirms the recipient and amount, checks it hasn't expired — but
    skips the on-chain balance check and the actual token transfer. That means
    demo.py, tests.py and agent_client.py all build genuine signed payments; only
    settlement is stubbed. Swap FACILITATOR=coinbase to settle for real.
    """

    def verify(self, x_payment: str, requirements: dict) -> VerifyResult:
        try:
            payment = x402_scheme.decode_header(x_payment)
        except Exception as exc:
            return VerifyResult(False, f"undecodable X-PAYMENT: {exc}")
        acc = requirements["accepts"][0]
        ok, info = x402_scheme.verify_offline(
            payment, int(acc["maxAmountRequired"]), acc["payTo"]
        )
        if not ok:
            return VerifyResult(False, info)
        return VerifyResult(True, "signature ok", payer=info)  # info == signer

    def settle(self, x_payment: str, requirements: dict) -> dict:
        # In mock mode "settlement" is a no-op — no funds move.
        return {"success": True, "network": config.NETWORK, "mock": True}


class CoinbaseX402Facilitator:
    """Verifies + settles against a real hosted x402 facilitator.

    This is the production path. The facilitator does the on-chain work; you
    just POST the agent's payment + your requirements and read the verdict.

    TODO before you rely on this:
      * Confirm the facilitator base URL and request/response schema for the
        version you target (see https://x402.org and the x402 GitHub repo).
        The field names below follow the reference facilitator; double-check
        them, as the spec is still moving.
      * Make sure RECEIVING_WALLET and USDC_ADDRESS in config.py are set for
        your NETWORK.
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or config.FACILITATOR_URL).rstrip("/")

    def _body(self, x_payment: str, requirements: dict) -> dict:
        # Current CDP facilitator takes the decoded paymentPayload object.
        # Some facilitators instead accept {"paymentHeader": x_payment}; if
        # yours does, send that instead of "paymentPayload".
        return {
            "x402Version": config.X402_VERSION,
            "paymentPayload": x402_scheme.decode_header(x_payment),
            "paymentRequirements": requirements["accepts"][0],
        }

    def verify(self, x_payment: str, requirements: dict) -> VerifyResult:
        try:
            resp = httpx.post(
                f"{self.base_url}/verify", json=self._body(x_payment, requirements),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return VerifyResult(False, f"facilitator verify failed: {exc}")
        if data.get("isValid") or data.get("valid"):
            return VerifyResult(True, "verified", payer=data.get("payer", ""))
        return VerifyResult(False, data.get("invalidReason", "invalid payment"))

    def settle(self, x_payment: str, requirements: dict) -> dict:
        # Settlement actually moves the funds on-chain (the facilitator submits
        # the signed transferWithAuthorization). Returns a tx hash on success.
        resp = httpx.post(
            f"{self.base_url}/settle", json=self._body(x_payment, requirements),
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()


def get_facilitator() -> Facilitator:
    if config.FACILITATOR == "mock":
        return MockFacilitator()
    if config.FACILITATOR == "coinbase":
        return CoinbaseX402Facilitator()
    raise ValueError(f"Unknown FACILITATOR: {config.FACILITATOR!r}")


# ---------------------------------------------------------------------------
# Client helper — build a REAL signed X-PAYMENT header from a 402's
# requirements. Used by the demo & tests (with a throwaway key) and usable by
# any agent. This is the same code an agent's wallet runs.
# ---------------------------------------------------------------------------
def sign_payment(private_key: str, requirements: dict) -> str:
    acc = requirements["accepts"][0]
    payment = x402_scheme.build_and_sign(
        private_key, acc["payTo"], int(acc["maxAmountRequired"])
    )
    return x402_scheme.encode_header(payment)


def new_test_key() -> str:
    """A throwaway EVM private key for demos/tests. Never use for real funds."""
    from eth_account import Account
    return "0x" + Account.create().key.hex()


# ---------------------------------------------------------------------------
# The reusable guard: given a tool name and the incoming X-PAYMENT header,
# decide whether to allow the call or demand payment.
# ---------------------------------------------------------------------------
_facilitator = get_facilitator()


def price_for(tool_name: str) -> int:
    """Atomic price of a tool. 0 means free."""
    if not config.X402_ENABLED:
        return 0
    if tool_name in config.FREE_TOOLS:
        return 0
    return config.PRICES_ATOMIC.get(tool_name, 0)


def check_payment(tool_name: str, x_payment: str | None, resource: str):
    """Returns (allowed: bool, requirements: dict|None, info: dict).

    - allowed True  -> serve the operation. info may include the payer.
    - allowed False -> respond 402 with `requirements`.

    Every outcome is recorded in the ledger (see ledger.py / the dashboard).
    """
    import ledger

    price = price_for(tool_name)
    if price == 0:
        ledger.record("free", tool_name)
        return True, None, {"free": True}

    requirements = build_requirements(tool_name, price, resource)
    if not x_payment:
        ledger.record("challenge", tool_name, amount_atomic=0,
                      network=config.NETWORK, detail=f"quoted {price}")
        return False, requirements, {"reason": "payment required"}

    result = _facilitator.verify(x_payment, requirements)
    if not result.ok:
        ledger.record("rejected", tool_name, payer=result.payer or None,
                      network=config.NETWORK, detail=result.reason)
        return False, requirements, {"reason": result.reason}

    # Replay guard: each signed authorization carries a unique nonce and may
    # buy exactly ONE operation. (On-chain settlement also enforces this, but
    # we refuse replays ourselves so the mock path is safe too and a replayed
    # header never reaches settlement.)
    nonce = _nonce_of(x_payment)
    if nonce is not None:
        with _nonce_lock:
            if nonce in _seen_nonces:
                reason = "replayed payment (nonce already used)"
                ledger.record("rejected", tool_name, payer=result.payer or None,
                              network=config.NETWORK, detail=reason)
                return False, requirements, {"reason": reason}
            _seen_nonces.add(nonce)

    # Payment is valid. Settle it (moves funds; no-op for the mock). A
    # settlement failure must never serve the result OR crash the server.
    try:
        settlement = _facilitator.settle(x_payment, requirements)
    except Exception as exc:
        reason = f"settlement failed: {exc}"
        ledger.record("rejected", tool_name, payer=result.payer or None,
                      network=config.NETWORK, detail=reason)
        return False, requirements, {"reason": reason}
    tx = settlement.get("transaction") or settlement.get("txHash") or \
        ("mock" if settlement.get("mock") else None)
    ledger.record("paid", tool_name, payer=result.payer,
                  amount_atomic=price, network=config.NETWORK, detail=tx)
    return True, None, {"payer": result.payer, "settlement": settlement}


# Nonces already spent in this process. On-chain settlement enforces
# uniqueness durably; this set additionally protects the mock path and stops
# replays before they reach the facilitator.
_seen_nonces: set[str] = set()
from threading import Lock as _Lock  # noqa: E402
_nonce_lock = _Lock()


def _nonce_of(x_payment: str) -> str | None:
    try:
        payment = x402_scheme.decode_header(x_payment)
        return payment["payload"]["authorization"]["nonce"]
    except Exception:
        return None
