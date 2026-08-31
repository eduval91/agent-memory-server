"""
x402 "exact" scheme for EVM chains — the real payment cryptography.

An x402 payment in the "exact" scheme is an EIP-3009 `transferWithAuthorization`
that the payer SIGNS (but does not broadcast). The facilitator later submits it
on-chain, pulling `value` of the token from `from` to `to`. This module builds,
signs, encodes, decodes, and verifies that signed authorization.

The same helpers are used by:
  * agent_client.py     — to build and sign a payment for a 402 challenge
  * payments.py         — the MockFacilitator verifies the signature offline;
                          the real facilitator does it on-chain.

Refs: coinbase/x402 specs/schemes/exact/scheme_exact_evm.md (EIP-3009 payload:
{signature, authorization{from,to,value,validAfter,validBefore,nonce}}).
"""
from __future__ import annotations
import base64
import json
import secrets
import time

from eth_account import Account
from eth_account.messages import encode_typed_data

import config


_EIP712_DOMAIN = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]
_TRANSFER_TYPES = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}


def _typed_data(authorization: dict) -> dict:
    """Build the EIP-712 typed-data structure for an authorization.

    NOTE: `name`/`version` MUST match the token contract's EIP-712 domain or a
    real on-chain settlement will reject the signature. See config.USDC_NAME /
    USDC_VERSION and verify them against your USDC contract before mainnet.
    """
    return {
        "types": {"EIP712Domain": _EIP712_DOMAIN, **_TRANSFER_TYPES},
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": config.USDC_NAME,
            "version": config.USDC_VERSION,
            "chainId": config.chain_id(),
            "verifyingContract": config.USDC_ADDRESS,
        },
        "message": {
            "from": authorization["from"],
            "to": authorization["to"],
            "value": int(authorization["value"]),
            "validAfter": int(authorization["validAfter"]),
            "validBefore": int(authorization["validBefore"]),
            "nonce": bytes.fromhex(authorization["nonce"][2:]),
        },
    }


def build_and_sign(private_key: str, pay_to: str, value_atomic: int,
                   valid_seconds: int = 60) -> dict:
    """Sign an EIP-3009 authorization and return the full x402 payment object.

    Returns the object that goes (base64-encoded) in the X-PAYMENT header.
    """
    acct = Account.from_key(private_key)
    now = int(time.time())
    authorization = {
        "from": acct.address,
        "to": pay_to,
        "value": str(value_atomic),
        "validAfter": str(now - 5),
        "validBefore": str(now + valid_seconds),
        "nonce": "0x" + secrets.token_hex(32),
    }
    signable = encode_typed_data(full_message=_typed_data(authorization))
    signed = acct.sign_message(signable)
    return {
        "x402Version": config.X402_VERSION,
        "scheme": "exact",
        "network": config.NETWORK,
        "payload": {
            "signature": "0x" + signed.signature.hex().replace("0x", ""),
            "authorization": authorization,
        },
    }


def recover_signer(payment: dict) -> str:
    """Recover the address that signed the authorization (the payer)."""
    payload = payment["payload"]
    signable = encode_typed_data(full_message=_typed_data(payload["authorization"]))
    return Account.recover_message(signable, signature=payload["signature"])


def verify_offline(payment: dict, required_value: int, pay_to: str) -> tuple[bool, str]:
    """Offline checks the MockFacilitator uses (no chain access):
    valid signature, correct recipient, sufficient value, unexpired.
    A real facilitator additionally checks on-chain balance + settles.
    """
    try:
        auth = payment["payload"]["authorization"]
        signer = recover_signer(payment)
    except Exception as exc:
        return False, f"bad signature/payload: {exc}"
    if signer.lower() != auth["from"].lower():
        return False, "signature does not match 'from'"
    if auth["to"].lower() != pay_to.lower():
        return False, "wrong recipient (payTo)"
    if int(auth["value"]) < required_value:
        return False, f"underpaid: {auth['value']} < {required_value}"
    if int(auth["validBefore"]) < int(time.time()):
        return False, "authorization expired"
    return True, signer


def encode_header(payment: dict) -> str:
    """x402 payment object -> base64 X-PAYMENT header value."""
    return base64.b64encode(json.dumps(payment).encode()).decode()


def decode_header(header: str) -> dict:
    """base64 X-PAYMENT header value -> x402 payment object."""
    return json.loads(base64.b64decode(header))
