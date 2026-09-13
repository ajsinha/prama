"""Two places where the normal case was the broken one.

QA round 2, `BCH-051` and `OPS-014`. Two systems agreeing is what a shadow run
is *for*, and it silently lost one of them. A single-replica SQLite install is a
combination the chart explicitly allows, and it could not write its database.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from prama.bench.shadow import Blinding, Judgement, ShadowAlert, evaluate

REPO = Path(__file__).resolve().parents[3]
CHART = REPO / "deploy" / "helm" / "prama"

WINDOW = {"window_start": "2026-09-01T00:00:00Z", "window_end": "2026-09-30T00:00:00Z"}
ALERT = {
    "dataset": "trades",
    "column": "lei",
    "raised_at": "2026-09-10T06:00:00Z",
    "detail": "12% malformed",
    "reference": "r1",
}


class TestTwoSystemsAgreeingIsNotOneAlert:
    """`BCH-051`. `register` keyed a plain dict on the content hash.

    Two systems raising the identical finding — which is what agreement looks
    like, and the normal case in a shadow run — collided, the second overwrote
    the first, and one system received no credit for a finding it had
    correctly raised. A benchmark that loses a correct alert understates
    whichever system it happened to store second.
    """

    @staticmethod
    def _both() -> Blinding:
        blinding = Blinding()
        blinding.register(ShadowAlert(system="prama", **ALERT))
        blinding.register(ShadowAlert(system="incumbent", **ALERT))
        return blinding

    def test_both_registrations_survive(self) -> None:
        assert len(self._both()) == 2

    def test_both_systems_are_known(self) -> None:
        assert self._both().systems() == ("incumbent", "prama")

    def test_a_steward_still_judges_it_once(self) -> None:
        """One finding, one judgement.

        Showing it twice would waste the steward's time and hint at the
        agreement, which is the thing the blinding exists to hide.
        """
        assert len(self._both().for_adjudication()) == 1

    def test_one_judgement_credits_both(self) -> None:
        blinding = self._both()
        blind_id = blinding.for_adjudication()[0]["blind_id"]
        result = evaluate(
            blinding, [Judgement(blind_id=blind_id, verdict="real", minutes=12)], **WINDOW
        )
        assert {system.system: system.confirmed for system in result.systems} == {
            "prama": 1,
            "incumbent": 1,
        }

    def test_the_identifier_still_hides_the_system(self) -> None:
        """The counterfactual for the obvious wrong fix.

        Adding the system to the hash would make the ids distinct and would
        also make them guessable: dataset, column, time and detail are all
        visible in the adjudication view, so a steward could hash each
        candidate system name until one matched.
        """
        prama = ShadowAlert(system="prama", **ALERT)
        incumbent = ShadowAlert(system="incumbent", **ALERT)
        assert prama.blind_id == incumbent.blind_id


def _helm() -> str:
    found = shutil.which("helm")
    if not found:
        pytest.skip("helm is not installed")
    return found


def _template(*overrides: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_helm(), "template", "t", str(CHART), *overrides],
        capture_output=True,
        text=True,
        timeout=120,
    )


class TestSqliteHasSomewhereToWrite:
    """`OPS-014`. `readOnlyRootFilesystem` is on and only `/tmp` was mounted.

    The chart's own validation explicitly allows sqlite at one replica, and the
    default path was a relative `data/prama.db` resolving under the read-only
    working directory. So the combination the chart permits is the one that
    could not start.
    """

    def test_sqlite_without_storage_is_refused(self) -> None:
        result = _template(
            "--set",
            "database.dialect=sqlite",
            "--set",
            "replicaCount=1",
            "--set",
            "existingSecret=s",
        )
        assert result.returncode != 0
        assert "needs somewhere to write" in result.stderr

    def test_sqlite_with_storage_mounts_a_claim(self) -> None:
        result = _template(
            "--set",
            "database.dialect=sqlite",
            "--set",
            "replicaCount=1",
            "--set",
            "existingSecret=s",
            "--set",
            "persistence.enabled=true",
        )
        assert result.returncode == 0, result.stderr
        assert "kind: PersistentVolumeClaim" in result.stdout
        assert 'mountPath: "/var/lib/prama"' in result.stdout
        assert "PRAMA_DATABASE__SQLITE__PATH" in result.stdout

    def test_it_is_never_an_emptydir(self) -> None:
        """An emptyDir would satisfy the read-only root and start cleanly.

        It would also discard the evidence ledger on every restart: the chain
        would begin again at sequence zero, and `prama db verify` would report
        a perfectly intact chain about nothing.
        """
        result = _template(
            "--set",
            "database.dialect=sqlite",
            "--set",
            "replicaCount=1",
            "--set",
            "existingSecret=s",
            "--set",
            "persistence.enabled=true",
        )
        data_volume = result.stdout.split("- name: data")[-1]
        assert "persistentVolumeClaim" in data_volume
        assert "emptyDir" not in data_volume.split("persistentVolumeClaim")[0]

    def test_postgres_is_unaffected(self) -> None:
        """The counterfactual: the default dialect must gain nothing."""
        result = _template("--set", "existingSecret=s", "--set", "database.postgres.host=pg")
        assert result.returncode == 0, result.stderr
        assert "PersistentVolumeClaim" not in result.stdout
        assert "/var/lib/prama" not in result.stdout
