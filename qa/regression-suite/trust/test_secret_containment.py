"""A secret provider must not be a way to read any file on disk.

QA round 2, `SEC-177`. `FileSecretProvider.__init__` documents the danger in
its own comment — "a reference is a stored value that an authenticated user can
edit, so without a root it would be a way to read any file the process can
read" — and then `_locate` returns `Path("/" + relative)` unconfined when no
root is set. No root is ever set: `secrets.file.root` is named in a remedy but
exists in no configuration file, and `connectivity.py` builds the resolver with
`default_resolver()` and no argument. So every deployment runs unconfined.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from prama.secrets.providers import FileSecretProvider
from prama.secrets.reference import SecretRef
from prama.secrets.resolver import SecretResolutionError


def test_an_unset_root_refuses_rather_than_reading_the_whole_filesystem(
    tmp_path: Path,
) -> None:
    """With no root configured, resolution must refuse, not widen.

    Refusing is the loud option and this codebase's house style — the shipped
    `security.session_secret` is empty on purpose so a fresh clone will not
    boot. Silently defaulting to `/` is the opposite of that: it is the most
    permissive possible reading of an absent setting.
    """
    secret = tmp_path / "not-a-secret-store" / "private.txt"
    secret.parent.mkdir()
    secret.write_text("hunter2")

    provider = FileSecretProvider(root=None)
    with pytest.raises(SecretResolutionError) as refusal:
        provider.resolve(SecretRef("file", str(secret)))

    # The refusal must name the setting that fixes it, and that setting must
    # be one a person can actually set.
    assert "secrets.file.root" in str(refusal.value)
    assert "hunter2" not in str(refusal.value)


def test_a_configured_root_still_resolves_a_secret_inside_it(tmp_path: Path) -> None:
    """The containment check must not break the thing it protects.

    A guard that also breaks ordinary reads is indistinguishable from a broken
    provider, and gets removed by whoever is debugging it at 3am.
    """
    root = tmp_path / "run" / "secrets"
    root.mkdir(parents=True)
    (root / "db-password").write_text("hunter2\n")

    provider = FileSecretProvider(root=str(root))
    assert provider.resolve(SecretRef("file", "/db-password")).reveal() == "hunter2"


def test_a_configured_root_still_refuses_an_escaping_reference(tmp_path: Path) -> None:
    """This half already worked; it is pinned so the fix cannot regress it."""
    root = tmp_path / "run" / "secrets"
    root.mkdir(parents=True)
    (tmp_path / "elsewhere.txt").write_text("hunter2")

    provider = FileSecretProvider(root=str(root))
    with pytest.raises(SecretResolutionError):
        provider.resolve(SecretRef("file", "/../elsewhere.txt"))
