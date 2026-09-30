"""Signing a payload with an agent's key, so the control plane knows who sent it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import hmac


def sign_payload(key: bytes, payload: str) -> str:
    """HMAC-SHA256 of *payload* under *key*, hex. The same on both sides."""
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_payload(key: bytes, payload: str, signature: str) -> bool:
    """Whether *signature* is *payload* signed with *key*, in constant time."""
    return hmac.compare_digest(sign_payload(key, payload), signature)
