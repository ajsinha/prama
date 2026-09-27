#!/usr/bin/env python3
"""Verify a Prama evidence bundle without Prama.

An audit trail that can only be checked by the tool that produced it is that
tool's own account of itself, which is the one thing an auditor is there not to
accept. So this script imports nothing from Prama — nothing from anywhere
outside the Python standard library — and implements the algorithm from the
prose in the bundle's own ``manifest.json``.

That independence is the entire point, and it is worth stating what it does and
does not buy. It proves the records are internally consistent and that the file
is the one the manifest describes. It does **not** prove the records are true:
a system that wrote a false record honestly, and chained it correctly, produces
a bundle that verifies. Chain integrity answers "has this been altered since it
was written", not "was it right when it was written". Anyone presenting a green
result as the second thing is overstating it.

    usage:  python3 verify_evidence.py <bundle-directory>
            python3 verify_evidence.py manifest.json evidence.ndjson

    exit 0  every check passed
    exit 1  at least one check failed
    exit 2  the bundle could not be read at all

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Licensed for use by auditors and their clients in verifying Prama evidence.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

USAGE = """usage:  python3 verify_evidence.py <bundle-directory>
        python3 verify_evidence.py manifest.json evidence.ndjson"""

GENESIS = "0" * 64

#: Fields excluded from the content hash, because they *are* the hashes.
NOT_CONTENT = ("previous_hash", "content_hash", "record_hash")


def canonical(payload: dict) -> bytes:
    """The exact bytes the content hash is taken over.

    ``sort_keys`` at every level and no insignificant whitespace. Both matter:
    two JSON documents with the same meaning and different key order hash
    differently, and a verifier that got this wrong would report every record
    as forged.
    """
    body = {k: v for k, v in payload.items() if k not in NOT_CONTENT}
    # UTF-8, not \uXXXX escapes: Prama writes `münchen.positionen` as its
    # UTF-8 bytes, and escaping it here made every non-ASCII record read as
    # altered (QA C4, EVD-006).
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merkle_root(hashes: list[str]) -> str:
    """One hash standing for the whole set.

    An odd node at any level is *promoted*, not duplicated. Duplicating it is
    the well-known construction that lets two different sets produce the same
    root, so a verifier that duplicated would accept a forged set.
    """
    if not hashes:
        return GENESIS
    level = list(hashes)
    while len(level) > 1:
        nxt = [
            sha256_hex((level[i] + level[i + 1]).encode("ascii"))
            for i in range(0, len(level) - 1, 2)
        ]
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0]


class Unreadable(Exception):
    """The bundle could not be read at all.

    Distinct from a failed verification, and exits with a different code. "I
    could not read it" and "it is wrong" are different findings, and an auditor
    scripting this needs to tell them apart — the first is a broken transfer,
    the second is a broken claim.
    """


class Report:
    """What was checked, and what failed."""

    def __init__(self) -> None:
        self.checks: list[tuple[str, bool, str]] = []

    def record(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append((name, passed, detail))

    @property
    def ok(self) -> bool:
        return all(passed for _, passed, _ in self.checks)

    def render(self) -> str:
        lines = []
        for name, passed, detail in self.checks:
            mark = "PASS" if passed else "FAIL"
            lines.append(f"  [{mark}] {name}")
            if detail:
                for line in detail.splitlines():
                    lines.append(f"         {line}")
        return "\n".join(lines)


def read_records(path: Path) -> list[dict]:
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise Unreadable(f"evidence line {number} is not JSON: {exc}") from exc
    return records


def verify_chain(records: list[dict], report: Report) -> list[str]:
    """The four steps from the manifest, in order. Returns the record hashes."""
    hashes: list[str] = []
    content_failures: list[str] = []
    link_failures: list[str] = []
    sequence_failures: list[str] = []
    tombstone_failures: list[str] = []
    erased = 0

    # `None` until the first record is read. A bundle is a *range* — its
    # manifest carries from_sequence and to_sequence — so the first record in
    # a legitimate export links to one that is not in the file. Seeding this
    # with GENESIS made every window that did not start at zero report itself
    # as a broken chain (QA finding Q-57).
    previous: str | None = None
    expected_sequence: int | None = None

    for index, payload in enumerate(records):
        sequence = payload.get("sequence")
        stored_content = payload.get("content_hash", "")
        stored_record = payload.get("record_hash", "")
        stored_previous = payload.get("previous_hash", "")

        if expected_sequence is None:
            expected_sequence = sequence
        elif sequence != expected_sequence:
            # A gap is a missing record, and no hash can reveal it: the chain
            # of the records present is perfectly valid without them.
            sequence_failures.append(f"expected sequence {expected_sequence}, found {sequence}")
        if isinstance(expected_sequence, int):
            expected_sequence += 1

        if payload.get("tombstone"):
            # Erased content. Its stored content_hash is the hash the content
            # *had*, so the bytes cannot be rehashed — but the erasure itself
            # is sealed, and that is checkable. Until it was (finding H4),
            # rewriting who erased a record and under what authority left every
            # check here passing: the record announced both and nothing covered
            # either.
            erased += 1
            stone = dict(payload["tombstone"])
            claimed_seal = str(stone.pop("seal", ""))
            recomputed = sha256_hex(canonical(stone))
            if not claimed_seal:
                tombstone_failures.append(
                    f"record {sequence}: erased, and the tombstone carries no seal"
                )
            elif recomputed != claimed_seal:
                tombstone_failures.append(
                    f"record {sequence}: tombstone seal is {claimed_seal[:12]}…, "
                    f"its fields give {recomputed[:12]}…"
                )
            if stone.get("original_content_hash") != stored_content:
                tombstone_failures.append(
                    f"record {sequence}: the tombstone names a different original "
                    "content hash than the record carries"
                )
        else:
            computed = sha256_hex(canonical(payload))
            if computed != stored_content:
                content_failures.append(
                    f"record {sequence}: content_hash is {stored_content[:12]}…, "
                    f"the bytes give {computed[:12]}…"
                )

        computed_record = sha256_hex((stored_previous + stored_content).encode("ascii"))
        if computed_record != stored_record:
            link_failures.append(
                f"record {sequence}: record_hash is {stored_record[:12]}…, "
                f"previous+content give {computed_record[:12]}…"
            )
        if previous is not None and stored_previous != previous:
            link_failures.append(
                f"record {sequence}: previous_hash does not match the record before it"
            )
        if index == 0 and stored_previous != GENESIS and sequence == 0:
            link_failures.append("the first record does not start from sixty-four zeros")

        previous = stored_record
        hashes.append(stored_record)

    report.record(
        "every record's content hashes to its stored content_hash",
        not content_failures,
        "\n".join(content_failures[:5]),
    )
    report.record(
        "every record links to the one before it",
        not link_failures,
        "\n".join(link_failures[:5]),
    )
    report.record(
        "sequence numbers are contiguous",
        not sequence_failures,
        "\n".join(sequence_failures[:5]),
    )
    if erased:
        report.record(
            f"{erased} record(s) carry a tombstone whose seal holds",
            not tombstone_failures,
            "\n".join(tombstone_failures[:5])
            or (
                "Their content cannot be verified, only their place and the "
                "erasure itself — who erased it, when, and under what authority. "
                "That is what erasure with an intact audit trail means."
            ),
        )
    return hashes


def verify_manifest(
    manifest: dict, records: list[dict], payload: str, hashes: list[str], report: Report
) -> None:
    stated = manifest.get("records")
    report.record(
        f"the manifest's record count ({stated}) matches the file ({len(records)})",
        stated == len(records),
        "A truncated file is the failure an archive actually suffers, and only "
        "the count reveals it — the remaining chain is perfectly valid."
        if stated != len(records)
        else "",
    )

    stated_digest = manifest.get("payload_digest", "")
    computed_digest = sha256_hex(payload.encode("utf-8"))
    report.record(
        "the evidence file is the one the manifest describes",
        stated_digest == computed_digest,
        f"manifest says {stated_digest[:16]}…, file is {computed_digest[:16]}…"
        if stated_digest != computed_digest
        else "",
    )

    stated_root = manifest.get("merkle_root", "")
    computed_root = merkle_root(hashes)
    report.record(
        "the Merkle root matches the records",
        stated_root == computed_root,
        f"manifest says {stated_root[:16]}…, records give {computed_root[:16]}…"
        if stated_root != computed_root
        else "",
    )

    stated_head = manifest.get("chain_head", "")
    actual_head = hashes[-1] if hashes else GENESIS
    report.record(
        "the chain head matches the last record",
        stated_head == actual_head,
        f"manifest says {stated_head[:16]}…, last record is {actual_head[:16]}…"
        if stated_head != actual_head
        else "",
    )


def locate(argv: list[str]) -> tuple[Path, Path]:
    if len(argv) == 1:
        directory = Path(argv[0])
        if not directory.is_dir():
            raise Unreadable(f"not a directory: {directory}")
        return directory / "manifest.json", directory / "evidence.ndjson"
    if len(argv) == 2:
        return Path(argv[0]), Path(argv[1])
    raise Unreadable(USAGE)


def main(argv: list[str]) -> int:
    try:
        manifest_path, evidence_path = locate(argv)
        for path in (manifest_path, evidence_path):
            if not path.is_file():
                raise Unreadable(f"no such file: {path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = evidence_path.read_text(encoding="utf-8")
        records = read_records(evidence_path)
    except Unreadable as exc:
        print(exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"could not read the bundle: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"manifest.json is not JSON: {exc}", file=sys.stderr)
        return 2

    report = Report()

    print(f"Bundle:   {manifest_path.parent}")
    print(f"Tenant:   {manifest.get('tenant_id') or '(none stated)'}")
    print(
        f"Period:   sequence {manifest.get('from_sequence')} to "
        f"{manifest.get('to_sequence')}, written {manifest.get('written_at')}"
    )
    print(f"Records:  {len(records)}")
    print()

    hashes = verify_chain(records, report)
    verify_manifest(manifest, records, payload, hashes, report)

    print(report.render())
    print()
    if report.ok:
        print("Every check passed.")
        print()
        # Printed on success, because success is where the overstatement
        # happens. Nobody misreads a failure.
        print("This says the records have not been altered since they were written,")
        print("and that this file is the one the manifest describes. It does not say")
        print("the records are true: a false record, honestly written and correctly")
        print("chained, produces a bundle that verifies exactly like this one.")
        return 0

    print("At least one check FAILED. This bundle is not what its manifest claims.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
