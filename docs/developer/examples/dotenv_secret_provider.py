"""A secret provider for ``dotenv://NAME``.

The worked example of docs/developer/secrets-and-leases.md.

A development machine often keeps its credentials in a ``.env`` file beside the
project. This provider resolves ``dotenv://WAREHOUSE_PASSWORD`` from such a file,
so a connection on that machine can be configured with a reference, exactly as
one in production is configured with ``vault://`` or ``env://``.

Three methods, and no more: resolving, saying whether it is usable here, and
saying what to do when it is not. A provider that grew write or rotate would make
Prama a secret *manager*, which it is not.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path

from prama.secrets.reference import SecretRef
from prama.secrets.spi import SecretProvider, SecretResolutionError
from prama.secrets.value import SecretValue


class DotenvSecretProvider(SecretProvider):
    """``dotenv://NAME``: a ``NAME=value`` line in one ``.env`` file."""

    scheme = "dotenv"
    description = "A NAME=value line in a .env file, for a development machine."

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path).expanduser()

    def available(self) -> bool:
        return self._path.is_file()

    def unavailable_remedy(self) -> str:
        return (
            f"There is no file at {self._path}. Create it, or reference this secret "
            "through env:// or vault:// instead."
        )

    def resolve(self, reference: SecretRef) -> SecretValue:
        if reference.key:
            raise SecretResolutionError(
                f"{reference.render()} names a field, and a .env value has none",
                remedy=f"Reference it as dotenv://{reference.location}.",
                context={"reference": reference.render()},
            )
        for line in self._path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip().removeprefix("export ").strip() == reference.location:
                value = value.strip().strip('"').strip("'")
                if not value:
                    # Never an empty value for a secret: an empty password reaches
                    # the driver and comes back as an authentication failure.
                    break
                return SecretValue(value, origin=reference.render())
        raise SecretResolutionError(
            f"{self._path} has no value for {reference.location}",
            remedy=f"Add a line {reference.location}=… to {self._path}.",
            context={"reference": reference.render()},
        )
