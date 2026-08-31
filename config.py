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
#        10_000 atomic = 0.01  USDC  (one cent)
#         1_000 atomic = 0.001 USDC  (a tenth of a cent)
#
# WHAT REVENUE THESE PRICES IMPLY (search is the money-maker):
#     $0.01/search -> $2,500/mo needs   250,000 searches/mo (~8,300/day)
#     $0.05/search -> $2,500/mo needs    50,000 searches/mo (~1,700/day)
#     $0.25/search -> $2,500/mo needs    10,000 searches/mo (~330/day)
# Do this arithmetic before changing a price. The earlier defaults here were
# demo pennies chosen to make the mechanics visible — not a business.
#
# Price for the VALUE the agent gets (a good answer from its own memory), not
# your compute cost. Field rule of thumb: builders undercharge by 3-5x at first.
PRICES_ATOMIC: dict[str, int] = {
    "store_memory": int(os.getenv("PRICE_STORE", "2000")),      # $0.002 / write
    "search_memory": int(os.getenv("PRICE_SEARCH", "10000")),   # $0.01  / query
    "retrieve_memory": int(os.getenv("PRICE_RETRIEVE", "1000")),# $0.001 / fetch
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


# ---------------------------------------------------------------------------
# Discovery — how agents FIND you.
# ---------------------------------------------------------------------------
# Your public URL once deployed (e.g. https://memory.yourdomain.com). Used in
# the landing page, the MCP registry entry, and the x402 Bazaar listing.
PUBLIC_URL: str = os.getenv("PUBLIC_URL", f"http://{os.getenv('HOST','127.0.0.1')}:{os.getenv('PORT','8402')}")

# x402 Bazaar metadata. Attaching this to your payment requirements is what
# makes the service discoverable — agents query the facilitator's
# /discovery/resources endpoint and search these fields in natural language.
SERVICE_NAME: str = os.getenv("SERVICE_NAME", "Agent Memory")  # max 32 chars
SERVICE_DESCRIPTION: str = os.getenv(
    "SERVICE_DESCRIPTION",
    "Persistent, semantically searchable memory for autonomous agents. "
    "Store facts and retrieve them later by meaning, not keywords. "
    "Pay per operation with x402 — no account, no API key.",
)
SERVICE_TAGS: list[str] = (
    os.getenv("SERVICE_TAGS", "memory,search,embeddings,storage,agents").split(",")
)[:5]  # Bazaar allows up to 5
SERVICE_ICON_URL: str = os.getenv("SERVICE_ICON_URL", "")  # optional https URL


# ---------------------------------------------------------------------------
# Dashboard access control
# ---------------------------------------------------------------------------
# The dashboard exposes revenue, customer wallet addresses, and landing-page
# enquiries. It is unprotected on localhost (your laptop is the boundary) and
# REQUIRES a password whenever the server binds to a public interface.
# Set this before deploying:  fly secrets set DASHBOARD_PASSWORD=...
DASHBOARD_USER: str = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "")


# ---------------------------------------------------------------------------
# Hardening — limits that keep one misbehaving agent from hurting the service.
# Rejections happen BEFORE payment, so agents never pay for refused calls.
# ---------------------------------------------------------------------------
RATE_LIMIT_PER_MIN: int = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))   # calls/min per client
MAX_TEXT_BYTES: int = int(os.getenv("MAX_TEXT_BYTES", "8192"))         # per stored memory
MAX_QUERY_BYTES: int = int(os.getenv("MAX_QUERY_BYTES", "1024"))       # per search query
MAX_METADATA_BYTES: int = int(os.getenv("MAX_METADATA_BYTES", "2048")) # serialized metadata
MAX_TOP_K: int = int(os.getenv("MAX_TOP_K", "20"))                     # results per search
MAX_MEMORIES_PER_AGENT: int = int(os.getenv("MAX_MEMORIES_PER_AGENT", "10000"))
MAX_BODY_BYTES: int = int(os.getenv("MAX_BODY_BYTES", "65536"))        # raw HTTP body cap


def usdc(atomic: int) -> str:
    """Human-readable USDC amount, for logs and payment descriptions."""
    return f"{atomic / 1_000_000:.6f} USDC"


def usdc_short(atomic: int) -> str:
    """Price as a buyer would read it: 0.01 USDC, not 0.010000 USDC."""
    s = f"{atomic / 1_000_000:.6f}".rstrip("0").rstrip(".")
    return f"{s or '0'} USDC"
