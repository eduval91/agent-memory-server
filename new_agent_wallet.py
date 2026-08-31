"""
Create a throwaway TESTNET agent wallet and save it safely.

Generates a fresh wallet, writes the private key to `.agent-wallet` (owner-only
permissions, git-ignored, never in the Docker image) and prints only the public
address. agent_client.py reads that file automatically, so you never copy-paste
a private key again.

    python new_agent_wallet.py

⚠️  TESTNET ONLY. This stores a private key in plaintext on your disk, which is
    fine for a wallet that holds nothing but faucet play-money and completely
    unacceptable for real funds. Never send real money to this wallet. For real
    funds use a proper wallet app and never write the key to a file.
"""
from __future__ import annotations
import os
import stat
from pathlib import Path

from eth_account import Account

WALLET_FILE = Path(__file__).resolve().parent / ".agent-wallet"


def load() -> str | None:
    """Read the saved key, if there is one."""
    if not WALLET_FILE.exists():
        return None
    key = WALLET_FILE.read_text().strip()
    return key or None


def main() -> None:
    if WALLET_FILE.exists():
        existing = load()
        if existing:
            addr = Account.from_key(existing).address
            print(f"A wallet already exists: {addr}")
            reply = input("Replace it? The old key will be LOST. [y/N] ").strip().lower()
            if reply != "y":
                print("Keeping the existing wallet.")
                return

    acct = Account.create()
    WALLET_FILE.write_text("0x" + acct.key.hex() + "\n")
    os.chmod(WALLET_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 0600: only you can read it

    print(f"\n  New testnet agent wallet")
    print(f"  address : {acct.address}")
    print(f"  key     : saved to {WALLET_FILE.name} (not shown, not in git)\n")
    print(f"  Fund this address from a Base Sepolia USDC faucet, then run:")
    print(f"      PUBLIC_URL=https://agent-memory-server.fly.dev python agent_client.py\n")
    print(f"  TESTNET ONLY — never send real funds to this wallet.\n")


if __name__ == "__main__":
    main()
