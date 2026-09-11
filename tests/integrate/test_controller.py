"""The control loop.

The decision is tested next door. These are about the loop: what it writes, when
it stops, and what a user sees on the resource when something went wrong — which
is the only thing a user sees at all.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import pytest

from prama.integrate.controller import ClusterError, Controller, MemoryCluster, ResourceClient
from prama.integrate.operator import MANAGED_BY, Verb


def estate(name: str = "prod", *, tenant: str = "t1", generation: int = 3, **changes):
    datasets = changes.pop("datasets", [{"name": "positions_eod", "criticality": "critical"}])
    metadata = {"name": name, "generation": generation}
    metadata.update(changes.pop("metadata", {}))
    return {"metadata": metadata, "spec": {"tenant": tenant, "datasets": datasets}, **changes}


def controller(cluster: MemoryCluster) -> Controller:
    return Controller(cluster, cluster)


class TestAFreshEstate:
    def test_every_declared_dataset_is_created(self) -> None:
        cluster = MemoryCluster([estate()])
        [outcome] = controller(cluster).reconcile_all()
        assert outcome.applied == 1
        assert cluster.declarations("t1")[0]["name"] == "positions_eod"

    def test_what_it_writes_is_marked_as_the_operators(self) -> None:
        """Stamped on the way in. A declaration written without it reads as a
        person's, and the next reconcile reports it as a conflict against the
        manifest that created it."""
        cluster = MemoryCluster([estate()])
        controller(cluster).reconcile_all()
        assert cluster.declarations("t1")[0]["managedBy"] == MANAGED_BY

    def test_a_second_pass_changes_nothing(self) -> None:
        """Idempotence, asserted across two passes rather than assumed — which
        is what the memory cluster exists for."""
        cluster = MemoryCluster([estate()])
        loop = controller(cluster)
        loop.reconcile_all()
        [second] = loop.reconcile_all()
        assert second.applied == 0
        assert second.plan.of(Verb.UNCHANGED)
        assert cluster.condition("prod")["status"] == "True"

    def test_the_status_is_ready_when_everything_landed(self) -> None:
        cluster = MemoryCluster([estate()])
        controller(cluster).reconcile_all()
        condition = cluster.condition("prod")
        assert condition["status"] == "True"
        assert condition["reason"] == "Reconciled"


class TestStatusIsAlwaysWritten:
    def test_a_conflict_still_writes_status(self) -> None:
        """A reconcile that hit a conflict and wrote nothing leaves the
        resource looking untouched, and the operator appears not to be
        running."""
        cluster = MemoryCluster(
            [estate()],
            {"t1": [{"name": "positions_eod", "criticality": "major"}]},
        )
        [outcome] = controller(cluster).reconcile_all()
        assert outcome.plan.of(Verb.CONFLICT)
        assert cluster.status_writes == 1
        assert cluster.condition("prod")["reason"] == "NeedsDecision"

    def test_a_conflict_does_not_overwrite_the_persons_declaration(self) -> None:
        """The rule the whole module exists for."""
        cluster = MemoryCluster(
            [estate()],
            {"t1": [{"name": "positions_eod", "criticality": "major"}]},
        )
        controller(cluster).reconcile_all()
        assert cluster.declarations("t1")[0]["criticality"] == "major"

    def test_a_manifest_with_no_tenant_is_skipped_and_says_so(self) -> None:
        cluster = MemoryCluster([estate(tenant="")])
        [outcome] = controller(cluster).reconcile_all()
        assert not outcome.ran
        assert "names no tenant" in outcome.skipped
        assert cluster.status_writes == 1

    def test_the_observed_generation_is_recorded(self) -> None:
        cluster = MemoryCluster([estate(generation=7)])
        controller(cluster).reconcile_all()
        assert cluster.statuses["prod"]["observedGeneration"] == 7
        assert cluster.condition("prod")["observedGeneration"] == 7

    def test_conflicts_and_orphans_are_counted_on_the_status(self) -> None:
        """A user sees the resource and nothing else."""
        cluster = MemoryCluster(
            [estate()],
            {
                "t1": [
                    {"name": "positions_eod", "criticality": "major"},
                    {"name": "retired_table"},
                ]
            },
        )
        controller(cluster).reconcile_all()
        assert cluster.statuses["prod"]["conflicts"] == 1
        assert cluster.statuses["prod"]["orphaned"] == 1


class TestAFailedWrite:
    def datasets(self):
        return [{"name": f"table_{n}", "criticality": "critical"} for n in range(4)]

    def test_it_stops_rather_than_continuing(self) -> None:
        """Continuing produces a status that counts successes over a cluster
        holding an unknown mixture."""
        cluster = MemoryCluster([estate(datasets=self.datasets())])
        cluster.fail_on = {"table_2"}
        [outcome] = controller(cluster).reconcile_all()
        assert outcome.applied == 2
        assert outcome.failed_at == "table_2"
        assert len(cluster.declarations("t1")) == 2

    def test_the_status_says_how_far_it_got(self) -> None:
        """Twelve of forty applied and stated as twelve is recoverable; twelve
        of forty reported as forty is not."""
        cluster = MemoryCluster([estate(datasets=self.datasets())])
        cluster.fail_on = {"table_2"}
        controller(cluster).reconcile_all()
        condition = cluster.condition("prod")
        assert condition["status"] == "False"
        assert condition["reason"] == "WriteFailed"
        assert "2 of 4" in condition["message"]

    def test_it_says_the_rest_were_not_attempted(self) -> None:
        cluster = MemoryCluster([estate(datasets=self.datasets())])
        cluster.fail_on = {"table_2"}
        [outcome] = controller(cluster).reconcile_all()
        assert "not attempted" in outcome.describe()

    def test_a_later_pass_picks_up_where_it_stopped(self) -> None:
        cluster = MemoryCluster([estate(datasets=self.datasets())])
        cluster.fail_on = {"table_2"}
        loop = controller(cluster)
        loop.reconcile_all()
        cluster.fail_on = set()
        [second] = loop.reconcile_all()
        assert second.complete
        assert len(cluster.declarations("t1")) == 4


class TestDeletion:
    def test_a_terminating_resource_is_left_alone(self) -> None:
        """Its finalizers are somebody else's business, and writing status onto
        something going away does nothing at best and blocks the deletion at
        worst."""
        cluster = MemoryCluster([estate(metadata={"deletionTimestamp": "2026-09-10T00:00:00Z"})])
        [outcome] = controller(cluster).reconcile_all()
        assert not outcome.ran
        assert "being deleted" in outcome.skipped
        assert cluster.status_writes == 0
        assert cluster.declarations("t1") == []

    def test_neither_seam_offers_a_delete(self) -> None:
        """A client that could delete would make "never removes anything" a
        matter of the loop remembering not to, rather than of the seam not
        offering it."""
        from prama.integrate.controller import DeclarationStore

        assert not hasattr(ResourceClient, "delete")
        assert not hasattr(DeclarationStore, "delete")
        assert not hasattr(DeclarationStore, "remove")


class TestClusterFailures:
    def test_a_failed_list_reconciles_nothing(self) -> None:
        class Broken(MemoryCluster):
            def list_estates(self):
                raise OSError("api server unreachable")

        with pytest.raises(ClusterError, match="could not list") as caught:
            controller(Broken()).reconcile_all()
        assert "Nothing was reconciled" in caught.value.remedy

    def test_a_failed_status_write_says_the_declarations_still_landed(self) -> None:
        """The status is the part that failed, and the reconcile is
        idempotent."""

        class Broken(MemoryCluster):
            def write_status(self, name, status):
                raise OSError("conflict")

        cluster = Broken([estate()])
        with pytest.raises(ClusterError, match="could not write status") as caught:
            controller(cluster).reconcile_all()
        assert "still applied" in caught.value.remedy
        assert cluster.declarations("t1")

    def test_nothing_is_retried_here(self) -> None:
        """A retry policy belongs to the client, which knows whether the API
        server was unreachable or the request was rejected. Kubernetes already
        has a backoff for the outer loop."""
        calls = []

        class Broken(MemoryCluster):
            def list_estates(self):
                calls.append(1)
                raise OSError("no")

        with pytest.raises(ClusterError):
            controller(Broken()).reconcile_all()
        assert len(calls) == 1


class TestManyEstates:
    def test_each_is_reconciled_independently(self) -> None:
        cluster = MemoryCluster([estate("prod", tenant="t1"), estate("uat", tenant="t2")])
        outcomes = controller(cluster).reconcile_all()
        assert len(outcomes) == 2
        assert cluster.declarations("t1") and cluster.declarations("t2")

    def test_one_conflict_does_not_stop_the_others(self) -> None:
        cluster = MemoryCluster(
            [estate("prod", tenant="t1"), estate("uat", tenant="t2")],
            {"t1": [{"name": "positions_eod", "criticality": "major"}]},
        )
        outcomes = controller(cluster).reconcile_all()
        assert not outcomes[0].plan.is_settled
        assert outcomes[1].complete


class TestNoKubernetesClientIsImported:
    def test_the_loop_needs_no_cluster_to_be_tested(self) -> None:
        import ast
        import pathlib

        from prama.integrate import controller as module

        tree = ast.parse(pathlib.Path(module.__file__).read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not {"kubernetes", "kopf", "pykube", "lightkube"} & imported
