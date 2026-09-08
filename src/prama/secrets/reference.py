"""References to secrets, which are what Prama actually stores.

A connection record holds ``env://PRAMA_WAREHOUSE_PASSWORD``, never a password.
That single decision is what lets the whole semantic layer be exported to Git,
diffed in a pull request, shown in the UI and copied between environments: there
is nothing in it that must not be seen.

The shape is a URI because that is the form people already recognise, and
because the scheme names the provider — so adding a vault means registering a
scheme rather than changing anything that stores or displays a reference.

    env://PRAMA_PG_PASSWORD
    file:///run/secrets/warehouse_password
    hashicorp://secret/data/prod/warehouse#password

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import re

from prama.core.errors import ValidationError

#: ``scheme://location[#key]``. The fragment names one field within an entry,
#: because most vaults store a JSON document per path rather than a bare string.
_REFERENCE = re.compile(r"^(?P<scheme>[a-z][a-z0-9+.-]*)://(?P<location>[^#]*)(?:#(?P<key>.+))?$")

#: Anything that looks like a credential rather than a reference to one. Used to
#: give a useful error instead of trying to resolve a password as a URI.
_LOOKS_LIKE_A_SECRET = re.compile(r"^[^:]*$|^[a-z]+://$", re.IGNORECASE)


@dataclasses.dataclass(frozen=True, slots=True)
class SecretRef:
    """Where a secret lives. Never the secret."""

    scheme: str
    location: str
    key: str = ""

    @classmethod
    def parse(cls, reference: str) -> SecretRef:
        text = (reference or "").strip()
        if not text:
            raise ValidationError(
                "a secret reference is empty",
                remedy=(
                    "Give a reference such as env://PRAMA_DB_PASSWORD. Prama stores "
                    "the reference, never the credential itself."
                ),
            )
        match = _REFERENCE.match(text)
        if match is None:
            raise ValidationError(
                "that is not a secret reference",
                remedy=(
                    "Use scheme://location, for example env://PRAMA_DB_PASSWORD or "
                    "file:///run/secrets/db_password. If you pasted a password, store "
                    "it in your secret manager and reference it instead — Prama will "
                    "not keep a credential in a connection record."
                ),
                # Deliberately no context: the offending text may *be* the
                # password somebody pasted, and this error gets logged.
            )
        location = match.group("location")
        if not location:
            raise ValidationError(
                f"the secret reference names no location after {match.group('scheme')}://",
                remedy="Give the variable, path or vault entry holding the secret.",
                context={"scheme": match.group("scheme")},
            )
        return cls(
            scheme=match.group("scheme").lower(),
            location=location,
            key=match.group("key") or "",
        )

    @classmethod
    def try_parse(cls, reference: str | None) -> SecretRef | None:
        if not reference:
            return None
        try:
            return cls.parse(reference)
        except ValidationError:
            return None

    def render(self) -> str:
        suffix = f"#{self.key}" if self.key else ""
        return f"{self.scheme}://{self.location}{suffix}"

    def __str__(self) -> str:
        return self.render()
