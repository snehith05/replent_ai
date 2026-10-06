"""Confirm a crawler is who it claims to be.

A user-agent is a claim, not an identity. Trusting the substring "googlebot"
meant that appending one word to any user-agent bought a full bypass of every
other check -- including, absurdly, for a user-agent that also announced itself
as GPTBot.

Real verification is the method the crawler operators themselves document: a
reverse DNS lookup on the connecting address, confirm the hostname belongs to
their domain, then a forward lookup to confirm that hostname resolves back to
the same address. A forged user-agent cannot survive it, because the attacker
does not control the operator's DNS.
"""
from __future__ import annotations

import os
import socket
from functools import lru_cache

# The domains each operator publishes for exactly this check.
CRAWLER_DOMAINS: dict[str, tuple[str, ...]] = {
    "googlebot": ("googlebot.com", "google.com"),
    "bingbot": ("search.msn.com",),
    "duckduckbot": ("duckduckgo.com",),
}

# DNS in the request path can hang, and there is no portable per-call timeout for
# gethostbyaddr. Verification is therefore opt-in, and when it is off an
# unverified claim is not trusted -- it simply falls through to normal scoring,
# which a genuine search crawler passes on its own merits anyway.
DNS_ENABLED = os.environ.get("REPELNT_VERIFY_DNS") == "1"


@lru_cache(maxsize=4096)
def verify(ip: str, token: str) -> bool:
    """True only if `ip` really belongs to the operator behind `token`."""
    domains = CRAWLER_DOMAINS.get(token)
    if not domains or not DNS_ENABLED:
        return False
    try:
        host = socket.gethostbyaddr(ip)[0].lower()
    except (OSError, socket.herror, socket.gaierror):
        return False
    if not any(host == d or host.endswith("." + d) for d in domains):
        return False
    try:
        return ip in socket.gethostbyname_ex(host)[2]
    except (OSError, socket.gaierror):
        return False


def status(ip: str, token: str | None) -> str:
    """A short description for the trace and the dashboard."""
    if token is None:
        return "no search-engine claim"
    if not DNS_ENABLED:
        return f"claims {token}, not verified (REPELNT_VERIFY_DNS is off)"
    return (f"claims {token}, confirmed by reverse DNS" if verify(ip, token)
            else f"claims {token}, FAILED reverse DNS")
