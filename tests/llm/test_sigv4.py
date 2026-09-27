"""SigV4 agrees with AWS's own published example, not with itself.

The request, credentials and expected values are AWS's worked example for
IAM ListUsers (Signature Version 4 documentation, date 2015-08-30).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib

from prama.llm.sigv4 import canonical_request, sign, signing_key

SECRET = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"
HEADERS = {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"}


def test_the_canonical_request_hashes_to_awss_value() -> None:
    request, signed = canonical_request(
        "GET",
        "/",
        "Action=ListUsers&Version=2010-05-08",
        {**HEADERS, "host": "iam.amazonaws.com", "x-amz-date": "20150830T123600Z"},
        hashlib.sha256(b"").hexdigest(),
    )
    assert signed == "content-type;host;x-amz-date"
    assert hashlib.sha256(request.encode()).hexdigest() == (
        "f536975d06c0309214f805bb90ccff089219ecd68b2577efef23edd43b7e1a59"
    )


def test_the_signing_key_matches_awss_example() -> None:
    assert signing_key(SECRET, "20150830", "us-east-1", "iam").hex() == (
        "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9"
    )


def test_the_signature_matches_awss_example() -> None:
    out = sign(
        method="GET",
        host="iam.amazonaws.com",
        path="/",
        query="Action=ListUsers&Version=2010-05-08",
        headers=HEADERS,
        payload=b"",
        access_key="AKIDEXAMPLE",
        secret_key=SECRET,
        region="us-east-1",
        service="iam",
        amz_date="20150830T123600Z",
    )
    assert out["authorization"].endswith(
        "Signature=5d672d79c15b13162d9279b0855cfba6789a8edb4c82c400e06b5924a6f2b5d7"
    )
    # The control: one changed byte of payload changes the signature.
    other = sign(
        method="GET",
        host="iam.amazonaws.com",
        path="/",
        query="Action=ListUsers&Version=2010-05-08",
        headers=HEADERS,
        payload=b"x",
        access_key="AKIDEXAMPLE",
        secret_key=SECRET,
        region="us-east-1",
        service="iam",
        amz_date="20150830T123600Z",
    )
    assert other["authorization"] != out["authorization"]
