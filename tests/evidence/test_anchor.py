"""Anchoring the chain outside Prama, against a real RFC 3161 time-stamp authority.

The authority is built here with OpenSSL (a CA, a TSA certificate with the
timeStamping purpose, and `openssl ts -reply`), so every token below is a real
token: Prama's request must be one OpenSSL accepts, and the auditor's check is
`openssl ts -verify`. Skipped where OpenSSL is not installed.

The case the anchor exists for is the last test: a chain rebuilt after it was
anchored verifies perfectly on its own, and fails against the receipt.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from prama.core.errors import PramaError, ValidationError
from prama.db import Database
from prama.evidence import tsp
from prama.evidence.anchor import Receipt, Rfc3161Anchor, anchor_head
from prama.evidence.ledger import Ledger
from prama.evidence.record import EvidenceRecord, SnapshotRef
from prama.evidence.retention import Archivist
from prama.security.egress import Gate, ResidencyRefused

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="needs OpenSSL")

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "scripts" / "verify_evidence.py"


@dataclasses.dataclass
class Authority:
    post: Callable[[bytes], bytes]
    ca: Path
    cert: Path


def _openssl(*args: str, cwd: Path) -> None:
    subprocess.run(["openssl", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture(scope="module")
def authority(tmp_path_factory: pytest.TempPathFactory) -> Authority:
    d = tmp_path_factory.mktemp("tsa")
    _openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        "ca.key",
        "-out",
        "ca.pem",
        "-subj",
        "/CN=Test TSA CA",
        "-days",
        "2",
        "-addext",
        "basicConstraints=critical,CA:TRUE",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
        cwd=d,
    )
    _openssl(
        "req",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        "tsa.key",
        "-out",
        "tsa.csr",
        "-subj",
        "/CN=Test TSA",
        cwd=d,
    )
    (d / "ext.cnf").write_text(
        "extendedKeyUsage=critical,timeStamping\nkeyUsage=critical,digitalSignature\n"
    )
    _openssl(
        "x509",
        "-req",
        "-in",
        "tsa.csr",
        "-CA",
        "ca.pem",
        "-CAkey",
        "ca.key",
        "-CAcreateserial",
        "-out",
        "tsa.pem",
        "-days",
        "2",
        "-extfile",
        "ext.cnf",
        cwd=d,
    )
    (d / "serial").write_text("01\n")
    (d / "tsa.cnf").write_text(
        f"[ tsa ]\ndefault_tsa = tsa1\n[ tsa1 ]\ndir = {d}\nserial = $dir/serial\n"
        "crypto_device = builtin\nsigner_cert = $dir/tsa.pem\ncerts = $dir/ca.pem\n"
        "signer_key = $dir/tsa.key\nsigner_digest = sha256\ndefault_policy = 1.2.3.4.1\n"
        "other_policies = 1.2.3.4.5\n"
        "digests = sha256\naccuracy = secs:1\nordering = yes\ntsa_name = no\n"
        "ess_cert_id_chain = no\ness_cert_id_alg = sha256\n"
    )

    def post(request: bytes) -> bytes:
        (d / "req.der").write_bytes(request)
        _openssl(
            "ts", "-reply", "-config", "tsa.cnf", "-queryfile", "req.der", "-out", "resp.der", cwd=d
        )
        return (d / "resp.der").read_bytes()

    return Authority(post=post, ca=d / "ca.pem", cert=d / "tsa.pem")


DIGEST = "a" * 64


def test_a_receipt_binds_the_digest_it_was_asked_for(authority: Authority) -> None:
    anchor = Rfc3161Anchor("https://tsa.test/tsr", post=authority.post)
    receipt = anchor.anchor(DIGEST)
    assert receipt.digest == DIGEST and receipt.witnessed_at.endswith("Z")
    assert anchor.check(receipt) == ""
    forged = dataclasses.replace(receipt, digest="b" * 64)
    assert "binds" in anchor.check(forged)


def test_a_refusal_is_raised_not_stored_as_a_receipt() -> None:
    rejection = bytes.fromhex("3005" + "3003020102")  # TimeStampResp { status rejection(2) }
    with pytest.raises(ValidationError, match="refused the request"):
        Rfc3161Anchor("https://tsa.test/tsr", post=lambda _: rejection).anchor(DIGEST)


def test_a_reply_for_another_request_is_refused(authority: Authority) -> None:
    """A replayed answer binds a different digest, or the same digest and an old nonce."""
    old = authority.post(tsp.request("c" * 64)[0])
    with pytest.raises(ValidationError, match="different request"):
        Rfc3161Anchor("https://tsa.test/tsr", post=lambda _: old).anchor(DIGEST)


def test_residency_is_consulted_before_anything_leaves(authority: Authority) -> None:
    sent: list[bytes] = []

    def post(request: bytes) -> bytes:
        sent.append(request)
        return authority.post(request)

    anchor = Rfc3161Anchor(
        "https://tsa.test/tsr", region="US", gate=Gate.for_tenant("EU", tenant_id="t1"), post=post
    )
    with pytest.raises(ResidencyRefused):
        anchor.anchor(DIGEST)
    assert not sent


def _record(index: int, tenant_id: str) -> EvidenceRecord:
    return EvidenceRecord(
        plan_id=f"ir:sha256:{index:064x}",
        control_id=f"ctl-{index}",
        dataset="positions_eod",
        binding="positions_eod",
        engine="duckdb",
        snapshot=SnapshotRef(kind="wall_clock", identifier=f"t{index}"),
        verdict="fail" if index % 2 else "pass",
        metrics={"scanned_rows": 100.0, "violating_rows": float(index % 2)},
        started_at="2026-09-28T06:00:00Z",
        finished_at="2026-09-28T06:00:01Z",
        tenant_id=tenant_id,
    )


async def test_the_head_is_anchored_once_and_a_failure_is_recorded(
    authority: Authority, started_database: Database, tenant_id: str
) -> None:
    anchor = Rfc3161Anchor("https://tsa.test/tsr", post=authority.post)
    async with started_database.unit_of_work() as uow:
        assert await anchor_head(uow, tenant_id, anchor) is None  # an empty chain
        for i in range(3):
            await uow.evidence.append(_record(i, tenant_id))
        first = await anchor_head(uow, tenant_id, anchor)
        again = await anchor_head(uow, tenant_id, anchor)
        head = await uow.evidence.head(tenant_id)
    assert first.status == "anchored" and first.sequence == 2 and first.digest == head
    assert again.id == first.id  # idempotent: not sent twice

    def unreachable(_: bytes) -> bytes:
        raise OSError("connection refused")

    down = Rfc3161Anchor("https://tsa.test/tsr", post=unreachable)
    async with started_database.unit_of_work() as uow:
        await uow.evidence.append(_record(3, tenant_id))
        failed = await anchor_head(uow, tenant_id, down)
        attempts = await uow.anchors.for_tenant(tenant_id)
    assert failed.status == "failed" and "connection refused" in failed.detail
    assert [a.status for a in attempts] == ["anchored", "failed"]


def _write(out: Path, records: list[EvidenceRecord], receipts: list[Receipt], seq: int) -> None:
    bundle = Archivist().bundle(records, tenant_id="tenant-a")
    out.mkdir(parents=True, exist_ok=True)
    for name, content in bundle.files().items():
        (out / name).write_text(content, encoding="utf-8")
    anchors = [dict(dataclasses.asdict(r), sequence=seq, status="anchored") for r in receipts]
    (out / "anchors.json").write_text(json.dumps(anchors), encoding="utf-8")


def _verify(out: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(out), *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def test_an_auditor_verifies_the_anchor_and_catches_a_rebuilt_chain(
    authority: Authority, tmp_path: Path
) -> None:
    ledger = Ledger()
    for i in range(4):
        ledger.append(_record(i, "tenant-a"))
    records = ledger.records()
    receipt = Rfc3161Anchor("https://tsa.test/tsr", post=authority.post).anchor(ledger.head)

    good = tmp_path / "good"
    _write(good, records, [receipt], records[-1].sequence)
    passed = _verify(good, "--tsa-ca", str(authority.ca), "--tsa-cert", str(authority.cert))
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert "the authority's signature verifies (openssl)" in passed.stdout
    unsigned = _verify(good)
    assert unsigned.returncode == 0 and "signature was" in unsigned.stdout

    # The rewrite: record 1's verdict flipped, and every hash after it
    # recomputed from genesis. The chain is perfectly consistent.
    rebuilt = Ledger()
    for i, record in enumerate(records):
        original = _record(i, "tenant-a")
        rebuilt.append(dataclasses.replace(original, verdict="pass") if i == 1 else original)
        del record
    forged = tmp_path / "forged"
    _write(forged, rebuilt.records(), [receipt], records[-1].sequence)
    caught = _verify(forged, "--tsa-ca", str(authority.ca), "--tsa-cert", str(authority.cert))
    assert caught.returncode == 1
    assert "rewritten after it was anchored" in caught.stdout
    # ...and without the receipt the forgery passes, which is the point of anchoring.
    (forged / "anchors.json").unlink()
    assert _verify(forged).returncode == 0


def test_a_token_that_does_not_parse_is_a_finding_not_a_crash(tmp_path: Path) -> None:
    ledger = Ledger()
    ledger.append(_record(0, "tenant-a"))
    junk = Receipt(
        kind="rfc3161",
        authority="x",
        digest=ledger.head,
        witnessed_at="",
        token=base64.b64encode(b"\x30\x01").decode(),
    )
    out = tmp_path / "junk"
    _write(out, ledger.records(), [junk], 0)
    result = _verify(out)
    assert result.returncode == 1 and "the token can be read" in result.stdout
    assert not isinstance(result, PramaError)
