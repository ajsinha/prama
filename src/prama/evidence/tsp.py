"""RFC 3161 time-stamp requests and tokens, in the standard library.

A time-stamp authority (TSA) signs a statement: *this digest existed at this
time*. Prama asks for one over the evidence chain's head, so a chain rebuilt
later (by somebody with write access to the database, say) cannot carry a
token for its new head dated before the rebuild. The token is verified with the
authority's certificate by any RFC 3161 tool; `openssl ts -verify` is the one
an auditor is likely to have already.

Only what that needs is here: DER encoding of a `TimeStampReq`, and reading a
`TimeStampResp` far enough to take its token, the hash it binds (the
*message imprint*) and the authority's time. Signature verification is not
reimplemented: a hand-written CMS verifier is how forged signatures get
accepted, and the auditor's own tool is the better judge anyway.

    TimeStampReq ::= SEQUENCE { version INTEGER (1),
        messageImprint SEQUENCE { hashAlgorithm AlgorithmIdentifier,
                                  hashedMessage OCTET STRING },
        nonce INTEGER, certReq BOOLEAN }

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import secrets
from datetime import UTC, datetime

from prama.core.errors import ValidationError

#: 2.16.840.1.101.3.4.2.1, id-sha256, as DER.
SHA256_OID = bytes.fromhex("0609608648016503040201")
#: 1.2.840.113549.1.9.16.1.4, id-ct-TSTInfo.
TSTINFO_OID = bytes.fromhex("060b2a864886f70d0109100104")

_SEQUENCE, _INTEGER, _OCTETS, _NULL, _BOOLEAN = 0x30, 0x02, 0x04, 0x05, 0x01
_GENERALIZED_TIME = 0x18


def _length(size: int) -> bytes:
    if size < 0x80:
        return bytes([size])
    body = size.to_bytes((size.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def _tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _length(len(content)) + content


def _integer(value: int) -> bytes:
    body = value.to_bytes(max(1, (value.bit_length() + 8) // 8), "big")  # sign bit clear
    return _tlv(_INTEGER, body)


def request(digest_hex: str, *, nonce: int | None = None) -> tuple[bytes, int]:
    """A DER `TimeStampReq` for a SHA-256 digest, and the nonce it carries."""
    digest = bytes.fromhex(digest_hex)
    if len(digest) != 32:
        raise ValidationError(
            "a time-stamp request needs a SHA-256 digest (64 hex characters)",
            remedy="Anchor the chain head's record hash.",
            context={"digest": digest_hex},
        )
    nonce = nonce if nonce is not None else secrets.randbits(63)
    algorithm = _tlv(_SEQUENCE, SHA256_OID + _tlv(_NULL, b""))
    imprint = _tlv(_SEQUENCE, algorithm + _tlv(_OCTETS, digest))
    body = _integer(1) + imprint + _integer(nonce) + _tlv(_BOOLEAN, b"\xff")
    return _tlv(_SEQUENCE, body), nonce


# -- reading ----------------------------------------------------------------


def _read(data: bytes, at: int) -> tuple[int, int, int]:
    """(tag, start of content, end of content) of the element at *at*."""
    if at + 2 > len(data):
        raise ValueError("truncated DER")
    tag, first = data[at], data[at + 1]
    at += 2
    if first < 0x80:
        size = first
    else:
        count = first & 0x7F
        if not 0 < count <= 4 or at + count > len(data):
            raise ValueError("bad DER length")
        size = int.from_bytes(data[at : at + count], "big")
        at += count
    if at + size > len(data):
        raise ValueError("DER length past the end")
    return tag, at, at + size


def _children(data: bytes, start: int, end: int) -> list[tuple[int, int, int]]:
    out, at = [], start
    while at < end:
        tag, content, stop = _read(data, at)
        out.append((tag, content, stop))
        at = stop
    return out


@dataclasses.dataclass(frozen=True, slots=True)
class Token:
    """What a time-stamp token says, as far as binding needs."""

    der: bytes
    #: The digest the authority signed, hex.
    imprint: str
    #: The authority's time, UTC.
    at: datetime
    nonce: int | None


def token_of(response: bytes) -> bytes:
    """The token (a CMS `ContentInfo`) from a `TimeStampResp`, or a refusal."""
    try:
        _, start, end = _read(response, 0)
        parts = _children(response, start, end)
        status = _children(response, parts[0][1], parts[0][2])
        _, s_start, s_end = status[0]
        code = int.from_bytes(response[s_start:s_end], "big")
    except (ValueError, IndexError) as exc:
        raise ValidationError(
            "the time-stamp authority's reply is not an RFC 3161 response",
            remedy="Check the configured URL points at a TSA, not a web page.",
            context={"detail": str(exc)},
        ) from None
    if code not in (0, 1) or len(parts) < 2:  # granted, grantedWithMods
        raise ValidationError(
            f"the time-stamp authority refused the request (status {code})",
            remedy="Check the authority accepts SHA-256 requests from this host.",
            context={"status": code},
        )
    # The whole TLV that follows the status, header included: that is the
    # token a verifier reads.
    return response[parts[0][2] : parts[1][2]]


def read_token(der: bytes) -> Token:
    """The imprint, time and nonce inside a token."""
    try:
        _, start, end = _read(der, 0)  # ContentInfo
        content_type, signed = _children(der, start, end)[:2]
        del content_type
        _, sd_start, sd_end = _read(der, signed[1])  # [0] EXPLICIT -> SignedData
        signed_data = _children(der, sd_start, sd_end)
        encap = signed_data[2]  # version, digestAlgorithms, encapContentInfo
        e_type, e_content = _children(der, encap[1], encap[2])[:2]
        if der[e_type[1] - 2 : e_type[2]] != TSTINFO_OID:
            raise ValueError("the token does not carry a TSTInfo")
        _, o_start, o_end = _read(der, e_content[1])  # [0] EXPLICIT -> OCTET STRING
        info = der[o_start:o_end]
        _, i_start, i_end = _read(info, 0)
        fields = _children(info, i_start, i_end)
        imprint_fields = _children(info, fields[2][1], fields[2][2])
        hashed = info[imprint_fields[1][1] : imprint_fields[1][2]]
        stamp = info[fields[4][1] : fields[4][2]].decode("ascii")
        nonce = None
        for tag, f_start, f_end in fields[5:]:
            if tag == _INTEGER:
                nonce = int.from_bytes(info[f_start:f_end], "big")
                break
    except (ValueError, IndexError, UnicodeDecodeError) as exc:
        raise ValidationError(
            "the time-stamp token could not be read",
            remedy="The token is not an RFC 3161 token, or it was damaged in storage.",
            context={"detail": str(exc)},
        ) from None
    return Token(der=der, imprint=hashed.hex(), at=_generalized(stamp), nonce=nonce)


def _generalized(text: str) -> datetime:
    """``YYYYMMDDHHMMSS[.fff]Z``, as an aware UTC datetime."""
    whole, _, fraction = text.rstrip("Z").partition(".")
    moment = datetime.strptime(whole, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    if fraction:
        moment = moment.replace(microsecond=int(fraction[:6].ljust(6, "0")))
    return moment
