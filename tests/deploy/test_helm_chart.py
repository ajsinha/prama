"""The Helm chart, rendered.

A chart is YAML nobody type-checks, so its guarantees regress silently: a
`securityContext` block deleted to make a pod start on somebody's cluster looks
like a whitespace change in review. These tests render the chart with `helm
template` and assert the properties a container review actually asks about.

Skipped — loudly — when helm is not installed, because a chart nobody rendered
is a chart nobody has checked.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

CHART = Path(__file__).resolve().parents[2] / "deploy" / "helm" / "prama"

pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None,
    reason=(
        "helm is not installed, so the chart was NOT rendered or checked. "
        "Install it to run these: https://helm.sh/docs/intro/install/"
    ),
)


def render(*settings: str) -> list[dict]:
    """The chart's manifests, or a failure carrying helm's own message."""
    command = ["helm", "template", "t", str(CHART)]
    for setting in settings:
        command += ["--set", setting]
    finished = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if finished.returncode != 0:
        raise AssertionError(finished.stderr.strip())
    return [doc for doc in yaml.safe_load_all(finished.stdout) if doc]


def refusal(*settings: str) -> str:
    command = ["helm", "template", "t", str(CHART)]
    for setting in settings:
        command += ["--set", setting]
    finished = subprocess.run(command, capture_output=True, text=True, timeout=120)
    assert finished.returncode != 0, "expected the chart to refuse and it rendered"
    return finished.stderr


WORKING = ("existingSecret=my-secret", "database.postgres.host=pg")


class TestItRefusesRatherThanDefaulting:
    def test_no_session_secret_fails_the_install(self) -> None:
        """A chart shipping a default secret means every installation that did
        not read the documentation runs on a key public in a git repository —
        and nothing about the running system looks wrong."""
        message = refusal("database.postgres.host=pg")
        assert "no default session secret" in message

    def test_sqlite_with_two_replicas_fails_the_install(self) -> None:
        """Two pods writing one file is corruption, not high availability, and
        it is the configuration somebody reaches for to get an HA tick."""
        message = refusal("existingSecret=s", "database.dialect=sqlite", "replicaCount=2")
        assert "corruption, not high availability" in message

    def test_postgres_without_a_host_fails_the_install(self) -> None:
        message = refusal("existingSecret=s", "database.dialect=postgres")
        assert "needs database.postgres.host" in message

    def test_sqlite_with_one_replica_is_allowed_once_it_has_a_volume(self) -> None:
        """It is the right shape for an evaluation, so refusing it outright
        would make the chart useless for the first thing anybody does.

        It is not refused outright: it needs one flag, and the refusal below
        names that flag. This asserted a bare sqlite install rendered until
        `OPS-014` — `readOnlyRootFilesystem` is on, so sqlite had nowhere to
        write, and the chart started a pod that would lose the evidence ledger
        on its first restart. For an evidence-first product, starting and
        silently losing the ledger is the worse failure.
        """
        docs = render(
            "existingSecret=s",
            "database.dialect=sqlite",
            "replicaCount=1",
            "persistence.enabled=true",
        )
        assert any(doc["kind"] == "Deployment" for doc in docs)
        assert any(doc["kind"] == "PersistentVolumeClaim" for doc in docs), (
            "sqlite rendered without a volume to write to, which is the state OPS-014 was about"
        )

    def test_sqlite_without_a_volume_says_which_flag_to_set(self) -> None:
        """A refusal that does not name the remedy is a wall.

        The counterpart to the test above, and the reason changing it is not
        merely accepting whatever the chart now does: the evaluation path has
        to stay one obvious step away, and "obvious" means the message says the
        flag rather than leaving the reader to find it.
        """
        message = refusal("existingSecret=s", "database.dialect=sqlite", "replicaCount=1")
        assert "persistence.enabled=true" in message
        assert "lose the evidence ledger" in message


class TestTheSecurityPropertiesSurviveRendering:
    def _container(self) -> tuple[dict, dict]:
        docs = render(*WORKING)
        deployment = next(d for d in docs if d["kind"] == "Deployment")
        spec = deployment["spec"]["template"]["spec"]
        return spec, spec["containers"][0]

    def test_it_runs_as_a_non_root_user(self) -> None:
        """A control plane reading a bank's data as root fails the first
        container review."""
        spec, _ = self._container()
        assert spec["securityContext"]["runAsNonRoot"] is True
        assert spec["securityContext"]["runAsUser"] == 10001

    def test_the_root_filesystem_is_read_only(self) -> None:
        _, container = self._container()
        assert container["securityContext"]["readOnlyRootFilesystem"] is True

    def test_every_capability_is_dropped(self) -> None:
        _, container = self._container()
        assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]

    def test_privilege_escalation_is_off(self) -> None:
        _, container = self._container()
        assert container["securityContext"]["allowPrivilegeEscalation"] is False

    def test_a_writable_mount_exists_for_the_read_only_root(self) -> None:
        """Turning the flag off to avoid this would trade a real security
        property for one line of YAML."""
        spec, container = self._container()
        assert any(mount["mountPath"] == "/tmp" for mount in container["volumeMounts"])
        assert any(volume["name"] == "tmp" for volume in spec["volumes"])


class TestTheSecretIsNeverInline:
    def test_it_comes_from_a_secret_reference(self) -> None:
        docs = render(*WORKING)
        deployment = next(d for d in docs if d["kind"] == "Deployment")
        env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
        secret = next(e for e in env if e["name"] == "PRAMA_SECURITY__SESSION_SECRET")
        assert "value" not in secret
        assert secret["valueFrom"]["secretKeyRef"]["name"] == "my-secret"

    def test_no_secret_object_is_created_when_one_was_named(self) -> None:
        """Creating a second would leave two keys and no statement about which
        is live."""
        docs = render(*WORKING)
        assert not any(doc["kind"] == "Secret" for doc in docs)

    def test_a_literal_creates_one_only_when_asked(self) -> None:
        docs = render("createSecretFrom=not-for-production", "database.postgres.host=pg")
        secret = next(doc for doc in docs if doc["kind"] == "Secret")
        assert secret["stringData"]["session-secret"] == "not-for-production"


class TestProbes:
    def test_liveness_and_readiness_ask_different_questions(self) -> None:
        """Liveness asks whether the process answers; readiness whether it can work.

        A database outage makes every pod unready, so traffic stops, and must
        not make them unlive, so Kubernetes does not restart healthy pods: a
        restart cannot repair a database, it turns one incident into two
        (docs/operations/observability.md). This test once asserted both probes
        used one endpoint; that was the design before probes existed, and it
        never ran here until helm was installed.
        """
        from prama.api.routes import probes

        docs = render(*WORKING)
        container = next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"][
            "containers"
        ][0]
        assert container["livenessProbe"]["httpGet"]["path"] == "/livez"
        assert container["readinessProbe"]["httpGet"]["path"] == "/readyz"
        served = {getattr(route, "path", "") for route in probes.router.routes}
        assert {"/livez", "/readyz"} <= served  # the chart probes what the app answers

    def test_liveness_starts_later_than_readiness(self) -> None:
        """A liveness probe that fires during startup restarts a pod that was
        about to become ready, forever."""
        docs = render(*WORKING)
        container = next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"][
            "containers"
        ][0]
        assert (
            container["livenessProbe"]["initialDelaySeconds"]
            > container["readinessProbe"]["initialDelaySeconds"]
        )


class TestOptionalPieces:
    def test_no_ingress_unless_asked(self) -> None:
        assert not any(doc["kind"] == "Ingress" for doc in render(*WORKING))

    def test_an_ingress_renders_with_tls(self) -> None:
        docs = render(
            *WORKING, "ingress.enabled=true", "ingress.host=prama.example", "ingress.tls=true"
        )
        ingress = next(doc for doc in docs if doc["kind"] == "Ingress")
        assert ingress["spec"]["rules"][0]["host"] == "prama.example"
        assert ingress["spec"]["tls"]

    def test_the_chart_lints_clean(self) -> None:
        finished = subprocess.run(
            [
                "helm",
                "lint",
                str(CHART),
                "--set",
                "existingSecret=s",
                "--set",
                "database.postgres.host=pg",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert finished.returncode == 0, finished.stdout
