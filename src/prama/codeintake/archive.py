"""Receiving a ZIP of application code without trusting it.

Every refusal names its reason. Checked from the central directory *before*
anything is written, then re-checked while streaming each entry, because a
ZIP's headers can claim sizes its contents do not keep to:

* **Zip-slip**: an absolute path, a drive letter, a `..` segment, a NUL byte,
  or anything that would resolve outside the extraction root.
* **Symlinks** are recorded and never created: a link to `/` is how an
  extraction becomes a read of the host.
* **Bombs**: total and per-file uncompressed size, entry count, and the
  compression ratio of each entry.

Nothing extracted is ever executed, imported or rendered.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
import stat
import zipfile
from pathlib import Path, PurePosixPath

from prama.core.errors import ValidationError


class IntakeRefused(ValidationError):
    """An archive or repository that Prama will not read."""

    code = "CODE.INTAKE_REFUSED"


@dataclasses.dataclass(frozen=True, slots=True)
class Limits:
    """How much untrusted code one intake may bring in."""

    max_compressed: int = 200 * 1024 * 1024
    max_uncompressed: int = 1024 * 1024 * 1024
    max_entries: int = 50_000
    max_file: int = 20 * 1024 * 1024
    max_ratio: float = 100.0


@dataclasses.dataclass(frozen=True, slots=True)
class Snapshot:
    """What was received: path to (sha256, size), and what was set aside."""

    root: Path
    files: dict[str, tuple[str, int]]
    symlinks: tuple[str, ...] = ()

    @property
    def digest(self) -> str:
        body = "\n".join(f"{p}\t{h}" for p, (h, _) in sorted(self.files.items()))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _refuse(reason: str, entry: str = "") -> IntakeRefused:
    return IntakeRefused(
        f"archive refused: {reason}" + (f" ({entry[:120]!r})" if entry else ""),
        remedy="Send an archive of the application's source, without links or oddities.",
        context={"entry": entry[:200]},
    )


def _safe_name(name: str) -> str:
    """The entry's relative path, or a refusal saying why it is not safe."""
    if "\x00" in name:
        raise _refuse("an entry name contains a NUL byte", name)
    cleaned = name.replace("\\", "/")
    if cleaned.startswith("/") or (len(cleaned) > 1 and cleaned[1] == ":"):
        raise _refuse("an entry has an absolute path", name)
    parts = PurePosixPath(cleaned).parts
    if any(part == ".." for part in parts):
        raise _refuse("an entry climbs out of the archive with '..'", name)
    return "/".join(part for part in parts if part not in ("", "."))


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def inspect(path: Path, limits: Limits) -> list[zipfile.ZipInfo]:
    """The entries worth extracting, after every check the central directory allows."""
    if path.stat().st_size > limits.max_compressed:
        raise _refuse("the archive is larger than the intake limit")
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise _refuse("this is not a ZIP archive") from exc
    with archive:
        entries = archive.infolist()
    if len(entries) > limits.max_entries:
        raise _refuse(f"{len(entries)} entries is more than the {limits.max_entries} allowed")
    total = 0
    for info in entries:
        _safe_name(info.filename)
        if info.is_dir() or _is_symlink(info):
            continue
        if info.file_size > limits.max_file:
            raise _refuse("an entry is larger than the per-file limit", info.filename)
        if info.compress_size and info.file_size / info.compress_size > limits.max_ratio:
            raise _refuse("an entry compresses too well to be source code (a bomb)", info.filename)
        total += info.file_size
        if total > limits.max_uncompressed:
            raise _refuse("the archive expands beyond the intake limit")
    return entries


def extract(path: Path, root: Path, limits: Limits | None = None) -> Snapshot:
    """Extract *path* under *root*, safely, and describe what arrived."""
    limits = limits or Limits()
    entries = inspect(path, limits)
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    files: dict[str, tuple[str, int]] = {}
    links: list[str] = []
    written = 0
    with zipfile.ZipFile(path) as archive:
        for info in entries:
            name = _safe_name(info.filename)
            if not name or info.is_dir():
                continue
            if _is_symlink(info):
                links.append(name)  # recorded, never created
                continue
            target = (root / name).resolve()
            if root not in target.parents:
                raise _refuse("an entry resolves outside the extraction root", info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, size = hashlib.sha256(), 0
            with archive.open(info) as source, target.open("wb") as sink:
                while chunk := source.read(1 << 16):
                    size += len(chunk)
                    written += len(chunk)
                    # Re-checked while streaming: the header's size is a claim.
                    if size > limits.max_file or written > limits.max_uncompressed:
                        sink.close()
                        target.unlink(missing_ok=True)
                        raise _refuse("an entry is larger than its header said", info.filename)
                    digest.update(chunk)
                    sink.write(chunk)
            target.chmod(0o640)  # nothing received is executable
            files[name] = (digest.hexdigest(), size)
    return Snapshot(root=root, files=files, symlinks=tuple(links))
