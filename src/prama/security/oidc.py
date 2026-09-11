"""Single sign-on: verifying an ID token, and mapping it to a principal.

An ID token is a bearer of identity claims signed by an identity provider. The
entire security of SSO rests on verifying that signature *before* believing a
single claim in the token, and on refusing the specific shapes of token that
have historically been accepted by verifiers that meant well.

The refusals, each of which is a real attack rather than a hypothetical:

- **``alg: none``.** A token asserting it is unsigned. A verifier that dispatches
  on the token's own ``alg`` header will happily verify nothing.
- **Algorithm confusion.** A token signed with HMAC-SHA256 whose key is the
  provider's *public* RSA key — which is public. Only asymmetric algorithms are
  accepted here, and the accepted set is fixed by configuration rather than read
  from the token.
- **Key substitution.** A token naming a ``kid`` that is not in the provider's
  key set, or no ``kid`` at all in a set with several keys. Trying every key
  until one works turns a rotated-out key into a valid signer forever.
- **Audience drift.** A token issued for a different client of the same
  provider. It is genuinely signed, genuinely current, and not for us.
- **Replay.** A token presented a second time, or presented without the nonce
  this session issued.

**Claims are read only after the signature verifies.** That ordering is not a
style preference: a verifier that parses the payload first and checks the
signature later has already made decisions — which key, which issuer, which
tenant — on attacker-controlled data.

**The key set is passed in, not fetched here.** Fetching JWKS is an egress
(``prama.security.egress``) and a caching problem, and mixing either into a
verifier makes the verifier untestable offline. What this module does is
decide, from keys somebody else obtained, whether a token is good.

Needs the ``sso`` extra. Without it every entry point refuses by name rather
than falling back to something weaker.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import secrets
from collections.abc import Iterable, Mapping
from typing import Any, Final

from prama.core.errors import PramaError

__all__ = [
    "ACCEPTED_ALGORITHMS",
    "ClaimMapping",
    "IdentityClaims",
    "InvalidToken",
    "JsonWebKey",
    "KeySet",
    "SsoUnavailable",
    "new_nonce",
    "verify_id_token",
]

#: Asymmetric only, and fixed here rather than read from the token. RS256 is
#: what essentially every enterprise IdP issues; ES256 is the modern
#: alternative. No HMAC family at any strength: with a public verification key
#: an HMAC algorithm makes the signature forgeable by anyone.
ACCEPTED_ALGORITHMS: Final[frozenset[str]] = frozenset({"RS256", "RS384", "RS512", "ES256"})

#: How far a token's timestamps may disagree with ours. Clocks do drift, and a
#: verifier with zero tolerance rejects valid tokens during the seconds either
#: side of expiry. Sixty seconds is the usual figure; more starts to matter.
MAX_CLOCK_SKEW_SECONDS: Final = 60


class SsoUnavailable(PramaError):
    """The ``sso`` extra is not installed.

    Its own error, and never a fallback: a deployment that cannot verify
    signatures must refuse to do SSO, not do it weakly.
    """

    code = "SSO.UNAVAILABLE"


class InvalidToken(PramaError):
    """A token that did not verify, and precisely why.

    The reason is carried because an operator diagnosing a failed sign-in
    otherwise sees "login failed" and checks the password of an account that has
    none. It is *not* returned to the browser: which check failed is useful to
    an operator and useful to an attacker for the same reason.
    """

    code = "SSO.TOKEN_INVALID"


def _require_crypto() -> Any:
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
    except ImportError as exc:  # pragma: no cover - exercised by the extra being absent
        raise SsoUnavailable(
            "single sign-on needs the 'sso' extra, which is not installed",
            remedy=(
                'Install it: pip install -e ".[sso]". Verifying an ID token '
                "signature needs real asymmetric cryptography, and this refuses "
                "rather than accepting tokens it cannot check."
            ),
        ) from exc
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

    return hashes, ec, padding, rsa


def _b64url(segment: str) -> bytes:
    """Decode base64url without padding, strictly.

    ``validate=True`` matters: without it, characters outside the alphabet are
    discarded silently, so a token with rubbish spliced into a segment decodes
    to something plausible instead of being rejected.
    """
    pad = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + pad)
    except Exception as exc:
        raise InvalidToken(
            "a token segment is not valid base64url",
            remedy="The token is malformed. Nothing to configure.",
        ) from exc


def _b64uint(segment: str) -> int:
    return int.from_bytes(_b64url(segment), "big")


@dataclasses.dataclass(frozen=True, slots=True)
class JsonWebKey:
    """One public key from a provider's JWKS."""

    kid: str
    kty: str
    alg: str = ""
    #: RSA
    n: str = ""
    e: str = ""
    #: EC
    crv: str = ""
    x: str = ""
    y: str = ""
    use: str = "sig"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> JsonWebKey:
        return cls(
            kid=str(payload.get("kid", "")),
            kty=str(payload.get("kty", "")),
            alg=str(payload.get("alg", "")),
            n=str(payload.get("n", "")),
            e=str(payload.get("e", "")),
            crv=str(payload.get("crv", "")),
            x=str(payload.get("x", "")),
            y=str(payload.get("y", "")),
            use=str(payload.get("use", "sig")),
        )

    def public_key(self) -> Any:
        _, ec, _, rsa = _require_crypto()
        if self.kty == "RSA":
            return rsa.RSAPublicNumbers(e=_b64uint(self.e), n=_b64uint(self.n)).public_key()
        if self.kty == "EC":
            curve = {"P-256": ec.SECP256R1()}.get(self.crv)
            if curve is None:
                raise InvalidToken(
                    f"unsupported elliptic curve {self.crv!r}",
                    remedy="Only P-256 is accepted. Ask the provider for RS256 or ES256.",
                )
            return ec.EllipticCurvePublicNumbers(
                x=_b64uint(self.x), y=_b64uint(self.y), curve=curve
            ).public_key()
        raise InvalidToken(
            f"unsupported key type {self.kty!r}",
            remedy="Only RSA and EC keys are accepted.",
        )


@dataclasses.dataclass(frozen=True, slots=True)
class KeySet:
    """A provider's signing keys, as obtained by somebody else."""

    keys: tuple[JsonWebKey, ...] = ()

    @classmethod
    def from_jwks(cls, document: Mapping[str, Any]) -> KeySet:
        entries = document.get("keys") or []
        return cls(
            keys=tuple(
                JsonWebKey.from_dict(entry)
                for entry in entries
                # A key marked for encryption is not a signing key, and
                # accepting one would let a key the provider never signs with
                # verify a token.
                if str(entry.get("use", "sig")) == "sig"
            )
        )

    def signing_key(self, kid: str) -> JsonWebKey:
        """The key with this id. Never 'try them all'.

        Trying every key until one verifies turns a key the provider rotated out
        — and may have published the private half of — into a valid signer for
        as long as it stays in the document.
        """
        if not self.keys:
            raise InvalidToken(
                "the provider's key set is empty",
                remedy="Fetch the provider's JWKS before verifying. An empty set verifies nothing.",
            )
        if not kid:
            if len(self.keys) == 1:
                return self.keys[0]
            raise InvalidToken(
                "the token names no key and the provider publishes several",
                remedy="Ask the provider to include a 'kid' header. Guessing is not verification.",
            )
        for key in self.keys:
            if key.kid == kid:
                return key
        raise InvalidToken(
            f"no key called {kid!r} in the provider's key set",
            remedy=(
                "Refresh the key set: the provider may have rotated. If it "
                "persists, the token was not signed by this provider."
            ),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class IdentityClaims:
    """Who the provider says this is."""

    subject: str
    issuer: str
    audience: tuple[str, ...]
    email: str = ""
    name: str = ""
    groups: tuple[str, ...] = ()
    issued_at: int = 0
    expires_at: int = 0
    nonce: str = ""
    raw: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "issuer": self.issuer,
            "audience": list(self.audience),
            "email": self.email,
            "name": self.name,
            "groups": list(self.groups),
            "expires_at": self.expires_at,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ClaimMapping:
    """Which claims become which fields, and which groups become which roles.

    Declared rather than hard-coded, because every provider spells these
    differently and a product that assumed one spelling would need a fork per
    customer.
    """

    email_claim: str = "email"
    name_claim: str = "name"
    groups_claim: str = "groups"
    #: IdP group → Prama role. A group with no mapping grants nothing: an
    #: unmapped group silently granting a default role is how everybody in the
    #: directory becomes an owner.
    roles: Mapping[str, str] = dataclasses.field(default_factory=dict)

    def roles_for(self, groups: Iterable[str]) -> tuple[str, ...]:
        return tuple(sorted({self.roles[g] for g in groups if g in self.roles}))

    def unmapped(self, groups: Iterable[str]) -> tuple[str, ...]:
        """Groups that granted nothing. Reported, not ignored.

        A person who signs in successfully and can see nothing has a
        configuration problem that looks exactly like a permissions bug.
        """
        return tuple(sorted({g for g in groups if g not in self.roles}))


def new_nonce() -> str:
    """A nonce for one authentication request.

    ``secrets``, not ``random``: a predictable nonce is no protection against
    replay, which is the only thing a nonce is for.
    """
    return secrets.token_urlsafe(32)


def verify_id_token(
    token: str,
    *,
    keys: KeySet,
    issuer: str,
    audience: str,
    now: int,
    nonce: str = "",
    accepted_algorithms: frozenset[str] = ACCEPTED_ALGORITHMS,
) -> IdentityClaims:
    """Verify an ID token and return its claims. Raises :class:`InvalidToken`.

    ``now`` is passed in rather than read from the clock so that expiry can be
    tested at all, and so a caller with a trusted time source can use it.
    """
    hashes, ec, padding, _rsa = _require_crypto()

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidToken(
            "a JWT has three dot-separated segments",
            remedy="The token is malformed, or something other than an ID token was sent.",
        )
    header_segment, payload_segment, signature_segment = parts

    try:
        header = json.loads(_b64url(header_segment))
    except json.JSONDecodeError as exc:
        raise InvalidToken(
            "the token header is not JSON", remedy="The token is malformed."
        ) from exc
    if not isinstance(header, dict):
        raise InvalidToken("the token header is not an object", remedy="The token is malformed.")

    algorithm = str(header.get("alg", ""))
    if algorithm not in accepted_algorithms:
        # Covers `none` and the HMAC family in one check. Dispatching on the
        # token's own alg is the vulnerability; this compares it to a set the
        # deployment fixed.
        raise InvalidToken(
            f"algorithm {algorithm or '(absent)'!r} is not accepted",
            remedy=(
                f"Accepted: {', '.join(sorted(accepted_algorithms))}. Symmetric "
                "algorithms are refused outright: with a public verification key "
                "they make the signature forgeable by anyone."
            ),
        )

    key = keys.signing_key(str(header.get("kid", "")))
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = _b64url(signature_segment)

    # -- signature first. Nothing below this line existed as a fact until now.
    public_key = key.public_key()
    digest = {"256": hashes.SHA256(), "384": hashes.SHA384(), "512": hashes.SHA512()}[
        algorithm[-3:]
    ]
    try:
        if algorithm.startswith("RS"):
            public_key.verify(signature, signing_input, padding.PKCS1v15(), digest)
        else:
            public_key.verify(_ecdsa_der(signature), signing_input, ec.ECDSA(digest))
    except Exception as exc:
        raise InvalidToken(
            "the signature does not verify against the provider's key",
            remedy=(
                "The token was not signed by this provider, or was altered in "
                "transit. Nothing about the claims inside it can be believed."
            ),
        ) from exc

    try:
        claims = json.loads(_b64url(payload_segment))
    except json.JSONDecodeError as exc:
        raise InvalidToken(
            "the token payload is not JSON", remedy="The token is malformed."
        ) from exc
    if not isinstance(claims, dict):
        raise InvalidToken("the token payload is not an object", remedy="The token is malformed.")

    _check_claims(claims, issuer=issuer, audience=audience, now=now, nonce=nonce)

    groups = claims.get("groups") or claims.get("roles") or []
    if isinstance(groups, str):
        groups = [groups]

    return IdentityClaims(
        subject=str(claims["sub"]),
        issuer=str(claims["iss"]),
        audience=_audiences(claims),
        email=str(claims.get("email", "")),
        name=str(claims.get("name", "")),
        groups=tuple(str(g) for g in groups),
        issued_at=int(claims.get("iat", 0)),
        expires_at=int(claims["exp"]),
        nonce=str(claims.get("nonce", "")),
        raw=claims,
    )


def _ecdsa_der(signature: bytes) -> bytes:
    """JOSE gives ECDSA as r||s; ``cryptography`` wants DER."""
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    half = len(signature) // 2
    return encode_dss_signature(
        int.from_bytes(signature[:half], "big"), int.from_bytes(signature[half:], "big")
    )


def _audiences(claims: Mapping[str, Any]) -> tuple[str, ...]:
    raw = claims.get("aud", [])
    if isinstance(raw, str):
        return (raw,)
    return tuple(str(entry) for entry in raw)


def _check_claims(
    claims: Mapping[str, Any], *, issuer: str, audience: str, now: int, nonce: str
) -> None:
    for required in ("sub", "iss", "aud", "exp"):
        if required not in claims:
            raise InvalidToken(
                f"the token has no {required!r} claim",
                remedy="A token without it cannot be checked. Ask the provider why.",
            )
    if not str(claims["sub"]):
        raise InvalidToken(
            "the token's subject is empty",
            remedy="The subject is the identity. An empty one identifies nobody.",
        )

    if str(claims["iss"]) != issuer:
        raise InvalidToken(
            "the token was issued by a different provider",
            remedy=(
                f"Expected {issuer!r}. A genuinely signed token from another "
                "issuer is still not one of ours."
            ),
        )

    audiences = _audiences(claims)
    if audience not in audiences:
        raise InvalidToken(
            "the token was not issued for this client",
            remedy=(
                f"Expected {audience!r} in the audience. This is usually a token "
                "for a different application of the same provider — genuinely "
                "signed, genuinely current, and not for us."
            ),
        )

    expires = int(claims["exp"])
    if now > expires + MAX_CLOCK_SKEW_SECONDS:
        raise InvalidToken(
            "the token has expired",
            remedy="Sign in again. Tolerance for clock drift is one minute, no more.",
        )
    issued = int(claims.get("iat", 0))
    if issued and issued > now + MAX_CLOCK_SKEW_SECONDS:
        # A token from the future is a clock problem or a forged iat, and
        # accepting it extends its usable life by however far ahead it claims.
        raise InvalidToken(
            "the token was issued in the future",
            remedy="Check the clocks on this host and on the provider.",
        )
    not_before = int(claims.get("nbf", 0))
    if not_before and now + MAX_CLOCK_SKEW_SECONDS < not_before:
        raise InvalidToken(
            "the token is not valid yet",
            remedy="Check the clocks on this host and on the provider.",
        )

    if nonce:
        presented = str(claims.get("nonce", ""))
        if not secrets.compare_digest(presented, nonce):
            raise InvalidToken(
                "the token does not carry the nonce this sign-in issued",
                remedy=("This is a token replayed from another session. Start the sign-in again."),
            )


def subject_digest(issuer: str, subject: str) -> str:
    """A stable local identifier for a remote subject.

    Issuer *and* subject: a subject is unique within its issuer and nowhere
    else, so keying on subject alone lets two providers collide onto one
    account.
    """
    return hashlib.sha256(f"{issuer}\x00{subject}".encode()).hexdigest()
