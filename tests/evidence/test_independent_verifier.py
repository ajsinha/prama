"""The auditor's script, run against a real bundle.

The claim `scripts/verify_evidence.py` makes is that an auditor can check a
Prama bundle *without Prama*. A test that imported the script and called its
functions alongside Prama's own would not test that claim — it would test that
two functions in one process agree. So these run the script as a subprocess,
the way an auditor would, and the first test is that it imports nothing of ours.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from prama.evidence.ledger import Ledger
from prama.evidence.record import EvidenceRecord, SnapshotRef
from prama.evidence.retention import Archivist

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_evidence.py"


def _ledger() -> Ledger:
    ledger = Ledger()
    for index in range(6):
        ledger.append(
            EvidenceRecord(
                plan_id=f"ir:sha256:{index:064x}",
                control_id=f"ctl-{index}",
                dataset="positions_eod",
                binding="pg://RISK.POSITIONS",
                engine="postgresql",
                snapshot=SnapshotRef(kind="lsn", identifier=f"0/{1000 + index}", exact=True),
                verdict="pass" if index % 2 else "fail",
                metrics={"scanned_rows": 50000.0, "violating_rows": float(index)},
                started_at="2026-04-02T06:31:00Z",
                finished_at="2026-04-02T06:31:02Z",
                duration_ms=2100,
                tenant_id="tenant-a",
            )
        )
    return ledger


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    ledger = _ledger()
    bundle = Archivist().bundle(ledger.records(), tenant_id="tenant-a")
    out = tmp_path / "bundle"
    out.mkdir()
    for name, content in bundle.files().items():
        (out / name).write_text(content, encoding="utf-8")
    return out


def run_verifier(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestItIsGenuinelyIndependent:
    def test_it_imports_nothing_from_prama(self) -> None:
        """The whole claim. An audit trail checkable only by the tool that
        produced it is that tool's own account of itself."""
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "prama" not in imported

    def test_it_imports_only_the_standard_library(self) -> None:
        """A third-party dependency is a thing an auditor has to install, trust
        and pin — and one more place for the verification to be wrong."""
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported <= set(sys.stdlib_module_names)

    def test_it_runs_without_prama_importable(self, bundle_dir: Path, tmp_path: Path) -> None:
        """Run from a directory where `import prama` fails, which is the
        auditor's actual situation."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(bundle_dir)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""},
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestItAcceptsAGenuineBundle:
    def test_a_good_bundle_passes_every_check(self, bundle_dir: Path) -> None:
        result = run_verifier(str(bundle_dir))
        assert result.returncode == 0, result.stdout
        assert "Every check passed." in result.stdout
        assert "FAIL" not in result.stdout

    def test_it_accepts_the_two_files_named_separately(self, bundle_dir: Path) -> None:
        result = run_verifier(
            str(bundle_dir / "manifest.json"), str(bundle_dir / "evidence.ndjson")
        )
        assert result.returncode == 0, result.stdout

    def test_it_says_what_a_pass_does_not_mean(self, bundle_dir: Path) -> None:
        """Printed on success, because success is where the overstatement
        happens — nobody misreads a failure."""
        result = run_verifier(str(bundle_dir))
        assert "does not say" in result.stdout
        assert "a false record, honestly written" in result.stdout


class TestItRejectsTampering:
    """The counterfactual, five ways. A verifier that cannot fail is worth
    nothing, and each of these is a different thing an archive suffers."""

    def test_an_altered_payload_is_caught(self, bundle_dir: Path) -> None:
        path = bundle_dir / "evidence.ndjson"
        lines = path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[2])
        record["verdict"] = "pass"
        lines[2] = json.dumps(record, sort_keys=True, separators=(",", ":"))
        path.write_text("\n".join(lines), encoding="utf-8")

        result = run_verifier(str(bundle_dir))
        assert result.returncode == 1
        assert "content_hash" in result.stdout

    def test_a_truncated_file_is_caught(self, bundle_dir: Path) -> None:
        """The failure an archive actually suffers. The remaining chain is
        perfectly valid — only the manifest's count reveals it."""
        path = bundle_dir / "evidence.ndjson"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:-2]), encoding="utf-8")

        result = run_verifier(str(bundle_dir))
        assert result.returncode == 1
        assert "record count" in result.stdout

    def test_a_removed_middle_record_is_caught(self, bundle_dir: Path) -> None:
        path = bundle_dir / "evidence.ndjson"
        lines = path.read_text(encoding="utf-8").splitlines()
        del lines[2]
        path.write_text("\n".join(lines), encoding="utf-8")

        result = run_verifier(str(bundle_dir))
        assert result.returncode == 1

    def test_a_reordered_pair_is_caught(self, bundle_dir: Path) -> None:
        path = bundle_dir / "evidence.ndjson"
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[2], lines[3] = lines[3], lines[2]
        path.write_text("\n".join(lines), encoding="utf-8")

        result = run_verifier(str(bundle_dir))
        assert result.returncode == 1

    def test_a_doctored_manifest_is_caught(self, bundle_dir: Path) -> None:
        """Rewriting the manifest to match a doctored payload still fails: the
        Merkle root and the chain head come from the records."""
        path = bundle_dir / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["merkle_root"] = "0" * 64
        path.write_text(json.dumps(manifest), encoding="utf-8")

        result = run_verifier(str(bundle_dir))
        assert result.returncode == 1
        assert "Merkle root" in result.stdout

    def test_a_green_run_is_not_vacuous(self, bundle_dir: Path) -> None:
        """The counterfactual's counterfactual: the same bundle, untouched,
        must pass — otherwise the failures above prove nothing."""
        assert run_verifier(str(bundle_dir)).returncode == 0


class TestItsRefusals:
    def test_a_missing_directory_exits_two(self, tmp_path: Path) -> None:
        """Distinct from a failed verification: 'I could not read it' and 'it is
        wrong' are different findings."""
        result = run_verifier(str(tmp_path / "nowhere"))
        assert result.returncode == 2

    def test_a_missing_file_exits_two(self, bundle_dir: Path) -> None:
        (bundle_dir / "evidence.ndjson").unlink()
        result = run_verifier(str(bundle_dir))
        assert result.returncode == 2

    def test_no_arguments_prints_the_usage(self) -> None:
        result = run_verifier()
        assert result.returncode == 2
        assert "usage" in (result.stdout + result.stderr)
