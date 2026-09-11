"""What a secret provider must do, and what Prama promises about it.

Deliberately three methods. A provider interface that grew write, rotate and
delete would make Prama a secret *manager*, and it should not be one: the
estate already has one, it is audited, and reimplementing a worse version beside
it is how credentials end up in two places with different lifetimes.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from prama.core.errors import PramaError
from prama.secrets.reference import SecretRef
from prama.secrets.value import SecretValue


class SecretResolutionError(PramaError):
    """A reference could not be resolved. Never carries the value."""

    code = "SECRET.UNRESOLVED"


class SecretProviderUnavailableError(SecretResolutionError):
    """The provider itself could not be reached or is not installed."""

    code = "SECRET.PROVIDER_UNAVAILABLE"


class SecretProvider(ABC):
    """Resolves references of one scheme."""

    #: The URI scheme this provider answers for, e.g. ``env``.
    scheme: str = ""
    #: Shown when a reference names an unknown scheme, so the message can say
    #: what *is* available rather than only what is not.
    description: str = ""

    @abstractmethod
    def resolve(self, reference: SecretRef) -> SecretValue:
        """Return the secret, or raise :class:`SecretResolutionError`.

        Never returns an empty value for a missing secret. An empty password
        reaches the driver and comes back as an authentication failure, sending
        somebody to check credentials that were never read in the first place.
        """

    def available(self) -> bool:
        """Whether this provider can be used in this deployment at all."""
        return True

    def unavailable_remedy(self) -> str:
        """What to do about being unavailable, in this provider's own terms.

        The resolver knows a provider said no; only the provider knows which
        setting is missing. A generic "check its configuration" sends somebody
        looking for a plugin that is already installed.
        """
        return "Check its configuration, or reference a secret from another provider."

    def describe(self) -> dict[str, str]:
        return {
            "scheme": self.scheme,
            "description": self.description,
            "available": "yes" if self.available() else "no",
        }
