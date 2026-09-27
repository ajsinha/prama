"""AWS Signature Version 4, with the standard library only.

For Amazon Bedrock, without pulling `botocore` into every installation.
Verified against AWS's published worked example (the IAM `ListUsers` request
in "Examples of the complete Signature Version 4 signing process"), so what
is tested is agreement with AWS rather than with this file's own arithmetic.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import hmac
import urllib.parse
from collections.abc import Mapping


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret: str, date: str, region: str, service: str) -> bytes:
    """The derived key for one day, region and service."""
    key = _hmac(("AWS4" + secret).encode("utf-8"), date)
    key = _hmac(key, region)
    key = _hmac(key, service)
    return _hmac(key, "aws4_request")


def canonical_request(
    method: str, path: str, query: str, headers: Mapping[str, str], payload_hash: str
) -> tuple[str, str]:
    """The canonical request and its signed-headers list."""
    names = sorted(h.lower() for h in headers)
    lowered = {k.lower(): " ".join(str(v).split()) for k, v in headers.items()}
    canonical_headers = "".join(f"{name}:{lowered[name]}\n" for name in names)
    signed = ";".join(names)
    pairs = sorted(urllib.parse.parse_qsl(query, keep_blank_values=True))
    canonical_query = "&".join(
        f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
        for k, v in pairs
    )
    canonical_path = urllib.parse.quote(path or "/", safe="/-_.~")
    return (
        "\n".join(
            (method, canonical_path, canonical_query, canonical_headers, signed, payload_hash)
        ),
        signed,
    )


def sign(
    *,
    method: str,
    host: str,
    path: str,
    query: str = "",
    headers: Mapping[str, str],
    payload: bytes,
    access_key: str,
    secret_key: str,
    region: str,
    service: str,
    amz_date: str,
    session_token: str = "",
) -> dict[str, str]:
    """Headers to add to the request: Authorization, x-amz-date, and so on."""
    payload_hash = hashlib.sha256(payload).hexdigest()
    all_headers = {**headers, "host": host, "x-amz-date": amz_date}
    if session_token:
        all_headers["x-amz-security-token"] = session_token
    request, signed = canonical_request(method, path, query, all_headers, payload_hash)
    date = amz_date[:8]
    scope = f"{date}/{region}/{service}/aws4_request"
    to_sign = "\n".join(
        ("AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(request.encode("utf-8")).hexdigest())
    )
    signature = hmac.new(
        signing_key(secret_key, date, region, service), to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    out = {
        "x-amz-date": amz_date,
        "authorization": (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={signed}, Signature={signature}"
        ),
    }
    if session_token:
        out["x-amz-security-token"] = session_token
    return out
