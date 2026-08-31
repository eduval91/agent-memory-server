"""
Central configuration for the agent-memory server.

Everything an operator needs to tune lives here or in environment variables.
Copy .env.example to .env and adjust, or export the vars directly.
"""
from __future__ import annotations
import os
from pathlib import Path


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from a .env file next to this code, if present.

    Real environment variables win over .env values. No dependency needed.
    """
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    parsed: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # drop an inline comment (anything from ' #' onward), then unquote
        value = value.split(" #")[0].split("\t#")[0]
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            parsed[key] = value  # last occurrence in the file wins
    for key, value in parsed.items():
        if key not in os.environ:  # real environment variables still win
            os.environ[key] = value


_load_dotenv()


# ---------------------------------------------------------------------------
# Payments: is the x402 layer on, and which facilitator verifies payments?
# ---------------------------------------------------------------------------
# X402_ENABLED=false  -> memory tools are free (handy while building the logic)
# FACILITATOR=mock     -> verify payments locally, no crypto (dev / testnet demo)
# FACILITATOR=coinbase -> verify against a real on-chain facilitator (see payments.py)
X402_ENABLED: bool = os.getenv("X402_ENABLED", "true").lower() == "true"
FACILITATOR: str = os.getenv("FACILITATOR", "mock")  # "mock" | "coinbase"

# The blockchain network payments settle on.
# Start on a TESTNET (free play money). Switch to "base" for real revenue.
NETWORK: str = os.getenv("NETWORK", "base-sepolia")  # "base-sepolia" | "base"

# The stablecoin you get paid in (USDC). Addresses differ per network.
# base-sepolia USDC (testnet): 0x036CbD53842c5426634e7929541eC2318f3dCF7e
# base mainnet  USDC:          0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
# NOTE: verify these against the official USDC docs before going to mainnet.
USDC_ADDRESS: str = os.getenv(
    "USDC_ADDRESS",
    "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # base-sepolia default
)

# The x402 protocol version the facilitator expects. Coinbase's facilitator has
# used 1; the spec is moving toward 2. Confirm for the facilitator you target.
X402_VERSION: int = int(os.getenv("X402_VERSION", "1"))

# EIP-3009 signatures are checked against the token's EIP-712 domain. These MUST
# match the USDC contract you point at, or real settlements reject the signature.
#   Base mainnet USDC : name="USD Coin", version="2"
#   Base Sepolia USDC : name="USDC",     version="2"   (verify via contract name())
# For the MOCK facilitator the signer and verifier share these, so anything works.
USDC_NAME: str = os.getenv("USDC_NAME", "USDC")
USDC_VERSION: str = os.getenv("USDC_VERSION", "2")

# EVM chain id for each supported network name (used when signing EIP-712).
_CHAIN_IDS = {"base-sepolia": 84532, "base": 8453}


def chain_id() -> int:
    try:
        return _CHAIN_IDS[NETWORK]
    except KeyError:
        raise ValueError(
            f"No chain id known for NETWORK={NETWORK!r}; add it to _CHAIN_IDS."
        )

# YOUR wallet — where the money lands. REQUIRED before you take real payments.
# For the mock facilitator this can stay a placeholder.
# TODO: create a wallet (e.g. Coinbase Wallet / any EVM wallet) and paste its
#       address here, or set RECEIVING_WALLET in your environment.
RECEIVING_WALLET: str = os.getenv(
    "RECEIVING_WALLET",
    "0x0000000000000000000000000000000000000000",  # <-- replace me
)

# The facilitator service that verifies + settles payments for you so your
# server never touches blockchain code directly.
# The x402 reference facilitator supports testnets for free.
# TODO: confirm the current facilitator URL from https://x402.org before mainnet.
FACILITATOR_URL: str = os.getenv("FACILITATOR_URL", "https://x402.org/facilitator")


# ---------------------------------------------------------------------------
# Pricing — this is a per-OPERATION business. Each tool has its own price.
# ---------------------------------------------------------------------------
# Prices are in ATOMIC units of USDC. USDC has 6 decimals, so:
#     1_000_000 atomic = 1.00 USDC
#         1_000 atomic = 0.001 USDC  (a tenth of a cent)
#           500 atomic = 0.0005 USDC
#
# Rule of thumb from the field: builders undercharge by 3-5x at first. Price for
# the VALUE the agent gets (a good search result), not your compute cost.
PRICES_ATOMIC: dict[str, int] = {
    "store_memory": int(os.getenv("PRICE_STORE", "500")),      # 0.0005 USDC / write
    "search_memory": int(os.getenv("PRICE_SEARCH", "1000")),   # 0.001  USDC / query
    "retrieve_memory": int(os.getenv("PRICE_RETRIEVE", "200")),# 0.0002 USDC / fetch
}

# Tools/methods that are ALWAYS free. Discovery must be free, or agents can't
# find out what you offer or what it costs before deciding to pay.
FREE_TOOLS: set[str] = {"get_pricing"}

# JSON-RPC methods that are part of MCP's handshake / discovery — never charged.
FREE_JSONRPC_METHODS: set[str] = {
    "initialize",
    "notifications/initialized",
    "tools/list",
    "resources/list",
    "prompts/list",
    "ping",
}


# ---------------------------------------------------------------------------
# Embeddings — how memories become vectors for semantic search.
# ---------------------------------------------------------------------------
# "sentence-transformers" -> real local semantic embeddings (recommended).
# "hashing"               -> dependency-free fallback (lexical only; for dev/testing
#                            or sandboxes where the model can't be downloaded).
# "openai"                -> hosted embeddings (needs OPENAI_API_KEY); see embeddings.py.
EMBEDDINGS_PROVIDER: str = os.getenv("EMBEDDINGS_PROVIDER", "sentence-transformers")
EMBEDDINGS_MODEL: str = os.getenv("EMBEDDINGS_MODEL", "all-MiniLM-L6-v2")


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8402"))


def usdc(atomic: int) -> str:
    """Human-readable USDC amount, for logs and payment descriptions."""
    return f"{atomic / 1_000_000:.6f} USDC"
