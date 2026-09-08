"""The providers that need nothing installed.

Environment variables and mounted files cover the deployments Prama actually
has to work in on day one — a container with secrets injected, a Kubernetes pod
with a secret volume, a systemd unit with an environment file. Both are the
mechanism the platform already uses, which is the point: Prama reads what the
estate's own secret management put there rather than becoming a second place
credentials live.

Providers for HashiCorp Vault, AWS Secrets Manager and Azure Key Vault register
themselves the same way and ship as separate packages, because each drags in a
cloud SDK that a bank running on-premise should not be made to install.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from prama.core.log import get_logger
from prama.secrets.reference import SecretRef
from prama.secrets.spi import SecretProvider, SecretResolutionError
from prama.secrets.value import SecretValue

_log = get_logger(__name__)


class EnvironmentSecretProvider(SecretProvider):
    """``env://VARIABLE_NAME``."""

    scheme = "env"
    description = "An environment variable, as injected by the container platform."

    def resolve(self, reference: SecretRef) -> SecretValue:
        name = reference.location
        raw = os.environ.get(name)
        if raw is None:
            raise SecretResolutionError(
                f"the environment variable {name} is not set",
                remedy=(
                    f"Set {name} wherever Prama runs — the container's environment, "
                    f"the systemd unit, or the deployment manifest. Prama does not "
                    f"store the credential itself, only this reference to it."
                ),
                context={"reference": reference.render()},
            )
        if reference.key:
            raw = _field_of(raw, reference.key, reference)
        return SecretValue(raw, origin=reference.render())


class FileSecretProvider(SecretProvider):
    """``file:///run/secrets/name`` — a mounted secret.

    The Kubernetes and Docker answer, and the one an on-premise bank is most
    likely to already be using. The file's permissions are checked and a
    world-readable secret is reported: it will still be used, because refusing
    to start is a worse outcome than a warning somebody can act on, but it is
    never allowed to pass silently.
    """

    scheme = "file"
    description = "A file on disk, as mounted by Kubernetes or Docker secrets."

    def __init__(self, *, root: str | None = None) -> None:
        #: When set, resolution is confined to this directory. A reference is a
        #: stored value that an authenticated user can edit, so without a root
        #: it would be a way to read any file the process can read.
        self._root = Path(root).resolve() if root else None

    def resolve(self, reference: SecretRef) -> SecretValue:
        path = self._locate(reference)
        if not path.is_file():
            raise SecretResolutionError(
                f"no secret file at {path}",
                remedy=(
                    "Check the mount path. In Kubernetes this is the secret volume's "
                    "mountPath plus the key name."
                ),
                context={"reference": reference.render()},
            )
        self._warn_if_readable(path)
        raw = path.read_text(encoding="utf-8")
        # A secret written with a trailing newline is the normal case — echo,
        # kubectl and every editor add one — and it is not part of the password.
        raw = raw.rstrip("\r\n")
        if reference.key:
            raw = _field_of(raw, reference.key, reference)
        return SecretValue(raw, origin=reference.render())

    def _locate(self, reference: SecretRef) -> Path:
        relative = reference.location.lstrip("/")
        if self._root is None:
            return Path("/" + relative)
        candidate = (self._root / relative).resolve()
        if not candidate.is_relative_to(self._root):
            raise SecretResolutionError(
                "that secret reference points outside the configured secrets directory",
                remedy=(
                    f"References are confined to {self._root}. Move the secret there, "
                    f"or change secrets.file.root."
                ),
                context={"reference": reference.render()},
            )
        return candidate

    @staticmethod
    def _warn_if_readable(path: Path) -> None:
        try:
            mode = path.stat().st_mode
        except OSError:  # pragma: no cover - racing with a mount change
            return
        if mode & 0o044:
            _log.warning(
                "secret file %s is readable by group or other (mode %o); "
                "tighten it to 0400 or 0600",
                path,
                mode & 0o777,
            )


class MemorySecretProvider(SecretProvider):
    """``memory://name`` — for tests and single-process evaluation.

    Not a default. A provider that silently produced secrets from nowhere would
    make a misconfigured deployment look like a working one.
    """

    scheme = "memory"
    description = "In-process secrets. For tests and evaluation only."

    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets = dict(secrets or {})

    def put(self, name: str, value: str) -> None:
        self._secrets[name] = value

    def resolve(self, reference: SecretRef) -> SecretValue:
        raw = self._secrets.get(reference.location)
        if raw is None:
            raise SecretResolutionError(
                f"no in-memory secret named {reference.location!r}",
                remedy="This provider is for tests; register the secret first.",
                context={"reference": reference.render()},
            )
        if reference.key:
            raw = _field_of(raw, reference.key, reference)
        return SecretValue(raw, origin=reference.render())


def _field_of(raw: str, key: str, reference: SecretRef) -> str:
    """Pull one field out of a JSON document.

    Most vaults store a document per path — ``{"username": ..., "password":
    ...}`` — so a reference names the entry and the fragment names the field.
    """
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SecretResolutionError(
            f"the secret is not a JSON document, so it has no field {key!r}",
            remedy=(
                f"Drop the #{key} from the reference to use the whole value, or store "
                f"a JSON document at that location."
            ),
            context={"reference": reference.render()},
        ) from exc
    if not isinstance(document, dict) or key not in document:
        available = sorted(document) if isinstance(document, dict) else []
        raise SecretResolutionError(
            f"the secret document has no field {key!r}",
            remedy=(
                f"Fields present: {', '.join(available) or '(none)'}. "
                f"Correct the fragment on the reference."
            ),
            context={"reference": reference.render(), "fields": available},
        )
    value = document[key]
    return value if isinstance(value, str) else json.dumps(value)
