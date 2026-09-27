"""The sandboxed side of a delegate run: a header and rows on stdin, one answer on stdout.

Started by `prama.delegates.host` as ``python -m prama.delegates.worker`` with
resource limits already set. The first line of stdin is a JSON header naming
the delegate, where it was admitted from, its parameters and the SHA-256 of its
file; every following line is one row. Rows are handed to the delegate as a
lazy iterator, so a streaming delegate holds one row at a time however large
the dataset is.

It loads exactly the delegate it was asked for, from where the host admitted
it. A file is re-hashed and re-scanned before it is imported: if its bytes are
not the bytes the host vetted, it is refused.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any


def _load(name: str, origin: str, source_hash: str) -> Any:
    from prama.delegates.registry import DelegateRegistry

    registry = DelegateRegistry()
    kind, _, where = origin.partition(":")
    if kind in ("path", "upload"):
        import tempfile

        path = Path(where)
        body = path.read_bytes()  # read once: what is hashed is what is imported
        if source_hash and hashlib.sha256(body).hexdigest() != source_hash:
            raise RuntimeError(f"{path.name} changed since it was admitted; refusing to import it")
        private = Path(tempfile.mkdtemp(prefix="prama-delegate-"))
        (private / path.name).write_bytes(body)
        registry.load_paths([str(private)], only=path.name)
    else:
        registry.load_entry_points()
    return registry.get(name).delegate


def _rows(stream: IO[bytes]) -> Iterator[dict[str, Any]]:
    for line in stream:
        if line.strip():
            yield json.loads(line)


def main() -> int:
    stdin = sys.stdin.buffer
    try:
        header = json.loads(stdin.readline().decode("utf-8"))
        delegate = _load(
            str(header["name"]), str(header.get("origin", "")), str(header.get("source_hash", ""))
        )
        measurement = delegate.measure(_rows(stdin), header.get("params") or {})
        json.dump({"measurement": measurement.to_dict()}, sys.stdout, default=str)
    except Exception as exc:
        json.dump({"error": f"{type(exc).__name__}: {exc}"}, sys.stdout)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
