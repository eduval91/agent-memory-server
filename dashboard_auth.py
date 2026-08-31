"""
Access control for the operator dashboard.

The dashboard shows your revenue, your customers' wallet addresses, and the
contact details of everyone who filled in the landing-page form. On a public
URL that is all one guessed path away from being someone else's business
intelligence — so once the server is reachable from the internet, the
dashboard requires a password.

Policy (deliberately fails CLOSED):
  * Bound to localhost  -> no password needed; your laptop is the boundary.
  * Bound to 0.0.0.0    -> DASHBOARD_PASSWORD is REQUIRED. If it isn't set,
                           the dashboard refuses to render at all rather than
                           quietly exposing your numbers.

Uses HTTP Basic auth: the browser shows its own login prompt, no session or
cookie handling, and it works identically for `curl -u`.
"""
from __future__ import annotations
import base64
import secrets

import config

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_public() -> bool:
    """True when the server is reachable beyond this machine."""
    return config.HOST not in _LOCAL_HOSTS


def required() -> bool:
    """Whether a password must be presented for dashboard access."""
    return is_public()


def misconfigured() -> bool:
    """Public server with no password set — refuse to serve the dashboard."""
    return required() and not config.DASHBOARD_PASSWORD


def check(auth_header: str | None) -> bool:
    """Validate an Authorization header. Timing-safe."""
    if not required():
        return True
    if not config.DASHBOARD_PASSWORD:
        return False
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        user, _, password = base64.b64decode(auth_header[6:]).decode().partition(":")
    except Exception:
        return False
    # Compare both halves with compare_digest so a wrong password can't be
    # discovered by timing how long the check takes.
    ok_user = secrets.compare_digest(user, config.DASHBOARD_USER)
    ok_pass = secrets.compare_digest(password, config.DASHBOARD_PASSWORD)
    return ok_user and ok_pass


UNAUTHORIZED_HEADERS = {"WWW-Authenticate": 'Basic realm="Agent Memory dashboard"'}

MISCONFIGURED_MESSAGE = (
    "Dashboard disabled: this server is publicly reachable but DASHBOARD_PASSWORD "
    "is not set. Set it (e.g. `fly secrets set DASHBOARD_PASSWORD=...`) and "
    "redeploy. Refusing to expose revenue and customer data without a password."
)
