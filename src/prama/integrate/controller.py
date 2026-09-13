"""The control loop: applying a :mod:`prama.integrate.operator` plan.

The decision lives next door and needs no cluster. This is the part that does,
and it is written so that the only thing needing one is the *client* — a seam
with two implementations, one that talks to an API server and one that does not,
so the loop's behaviour is testable and only its plumbing is not.

What a reconciler has to get right, and what each rule costs if it does not:

**Status is written even when nothing else is.** A reconcile that hit a conflict
and wrote no status leaves the resource looking untouched, and the operator
appears not to be running. The status is the only thing a user sees, so it is
written first on every path including the failing ones.

**observedGeneration is set from what was read, not from what is current.** The
manifest can change while a reconcile runs. Recording the generation observed at
the top means a status saying ``Ready`` is a statement about a version somebody
can point at, rather than about whichever version happens to be current when the
write lands.

**A failed write stops the batch and reports how far it got.** Continuing past a
failure produces a resource whose status counts successes and whose cluster
holds an unknown mixture. Twelve of forty applied and *stated as twelve* is
recoverable; twelve of forty reported as forty is not.

**Nothing is retried here.** A retry policy belongs to the client, which knows
whether the API server was unreachable or the request was rejected — a loop that
retried everything would retry a rejected manifest forever, and Kubernetes
already has a backoff for the outer loop.

**A resource being deleted is left alone.** Its finalizers are somebody else's
business, and reconciling a terminating resource writes status onto something
that is going away, which at best does nothing and at worst blocks the deletion.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

from prama.core.errors import PramaError
from prama.integrate.operator import MANAGED_BY, Plan, Step, Verb, plan

__all__ = [
    "ClusterError",
    "Controller",
    "DeclarationStore",
    "MemoryCluster",
    "Outcome",
    "ResourceClient",
]


class ClusterError(PramaError):
    """The API server failed. Never swallowed, never retried here."""

    code = "OPERATOR.CLUSTER"


class ResourceClient(abc.ABC):
    """The cluster, reduced to what a reconciler needs.

    Four methods, and deliberately no ``delete``: this operator never removes
    anything, and a client that could would make that a matter of the loop
    remembering not to rather than of the seam not offering it.
    """

    @abc.abstractmethod
    def list_estates(self) -> Sequence[Mapping[str, Any]]:
        """Every ``PramaEstate`` this controller is responsible for."""

    @abc.abstractmethod
    def write_status(self, name: str, status: Mapping[str, Any]) -> None:
        """Replace one resource's status subresource."""


class DeclarationStore(abc.ABC):
    """Prama's own side. Also no delete, and for the same reason."""

    @abc.abstractmethod
    def declarations(self, tenant: str) -> Sequence[Mapping[str, Any]]:
        """What the estate already holds."""

    @abc.abstractmethod
    def apply(self, tenant: str, dataset: Mapping[str, Any]) -> None:
        """Create or amend one declaration, marked as managed by this operator."""


@dataclasses.dataclass(frozen=True, slots=True)
class Outcome:
    """What one resource's reconcile did."""

    name: str
    tenant: str
    plan: Plan
    applied: int = 0
    #: Set when a write failed. The plan says what was intended; this says where
    #: it stopped, which is the number a recovering operator needs.
    failed_at: str = ""
    failure: str = ""
    skipped: str = ""

    @property
    def ran(self) -> bool:
        return not self.skipped

    @property
    def complete(self) -> bool:
        return self.ran and not self.failure and self.applied == len(self.plan.writes)

    def describe(self) -> str:
        if self.skipped:
            return f"{self.name}: skipped — {self.skipped}"
        if self.failure:
            return (
                f"{self.name}: stopped at {self.failed_at} after {self.applied} of "
                f"{len(self.plan.writes)} write(s) — {self.failure}. The rest were "
                "not attempted, and the status says so rather than counting them."
            )
        return f"{self.name}: {self.plan.describe()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tenant": self.tenant,
            "applied": self.applied,
            "complete": self.complete,
            "failed_at": self.failed_at,
            "failure": self.failure,
            "skipped": self.skipped,
            **self.plan.to_dict(),
        }


class Controller:
    """One reconcile pass over every estate the client can see."""

    def __init__(self, client: ResourceClient, store: DeclarationStore) -> None:
        self._client = client
        self._store = store

    def reconcile_all(self) -> tuple[Outcome, ...]:
        try:
            resources = list(self._client.list_estates())
        except Exception as exc:
            raise ClusterError(
                "could not list PramaEstate resources",
                remedy=(
                    "Nothing was reconciled and nothing was written. Check the "
                    "API server and the controller's RBAC; Kubernetes will call "
                    "this again."
                ),
                context={"error": type(exc).__name__},
            ) from exc
        # Every estate is attempted, and *then* the failure is raised. It used
        # to propagate out of a generator expression, abandoning every resource
        # after the first failure — so one estate whose status write was
        # refused, by an RBAC gap or a conflict, stopped the other nine from
        # being reconciled at all (QA finding INT-041).
        #
        # An operator with ten estates then saw one error and nine that
        # silently did not run, which reads as a broken controller rather than
        # one broken estate. Raising afterwards keeps the error the operator
        # needs — Kubernetes retries on it, and the reconcile is idempotent —
        # while the other nine are already done by the time it arrives.
        outcomes: list[Outcome] = []
        failures: list[ClusterError] = []
        for resource in resources:
            try:
                outcomes.append(self.reconcile(resource))
            except ClusterError as exc:
                failures.append(exc)
        if failures:
            if len(failures) == 1:
                raise failures[0]
            names = ", ".join(sorted(str(e.context.get("resource", "?")) for e in failures))
            raise ClusterError(
                f"{len(failures)} estate(s) could not be reconciled: {names}",
                remedy=(
                    "Every other estate was reconciled before this was raised. The "
                    "declarations that landed are still applied; Kubernetes will call "
                    "this again, and the reconcile is idempotent."
                ),
                context={"resources": names, "failed": str(len(failures))},
                cause=failures[0],
            )
        return tuple(outcomes)

    def reconcile(self, resource: Mapping[str, Any]) -> Outcome:
        metadata = resource.get("metadata") or {}
        name = str(metadata.get("name", ""))
        spec = resource.get("spec") or {}
        tenant = str(spec.get("tenant", ""))

        if metadata.get("deletionTimestamp"):
            # Writing status onto something that is going away does nothing at
            # best and blocks the deletion at worst.
            return Outcome(
                name=name,
                tenant=tenant,
                plan=Plan(tenant=tenant),
                skipped="the resource is being deleted",
            )

        # Read once, at the top. The manifest can change while this runs, and a
        # status saying Ready about "whichever version is current when the write
        # lands" is a statement nobody can point at.
        generation = int(metadata.get("generation", 0) or 0)

        if not tenant:
            outcome = Outcome(
                name=name,
                tenant="",
                plan=Plan(tenant=""),
                skipped="the manifest names no tenant",
            )
            self._write_status(name, outcome, generation)
            return outcome

        stored = self._store.declarations(tenant)
        decided = plan(spec, stored)

        applied = 0
        failed_at = ""
        failure = ""
        for step in decided.writes:
            try:
                self._store.apply(tenant, self._payload(spec, step))
            except Exception as exc:
                # Stop. Continuing produces a status that counts successes over
                # a cluster holding an unknown mixture.
                failed_at = step.dataset
                failure = f"{type(exc).__name__}: {exc}"
                break
            applied += 1

        outcome = Outcome(
            name=name,
            tenant=tenant,
            plan=decided,
            applied=applied,
            failed_at=failed_at,
            failure=failure,
        )
        self._write_status(name, outcome, generation)
        return outcome

    def _payload(self, spec: Mapping[str, Any], step: Step) -> dict[str, Any]:
        empty: Mapping[str, Any] = {}
        declared = next(
            (d for d in spec.get("datasets", []) if str(d.get("name", "")) == step.dataset),
            empty,
        )
        # Stamped on the way in, not afterwards. A declaration written without
        # it reads as a person's and the next reconcile reports it as a
        # conflict against the manifest that created it.
        return {**declared, "managedBy": MANAGED_BY}

    def _write_status(self, name: str, outcome: Outcome, generation: int) -> None:
        """Status first on every path, including the failing ones.

        A reconcile that hit a conflict and wrote nothing leaves the resource
        looking untouched, and the operator appears not to be running.
        """
        applied: int | None = outcome.applied
        conditions = outcome.plan.conditions(generation=generation, applied=applied)
        if outcome.failure:
            conditions[0]["reason"] = "WriteFailed"
            conditions[0]["status"] = "False"
            conditions[0]["message"] = outcome.describe()
        try:
            self._client.write_status(
                name,
                {
                    "conditions": conditions,
                    "observedGeneration": generation,
                    "applied": outcome.applied,
                    "conflicts": len(outcome.plan.of(Verb.CONFLICT)),
                    "orphaned": len(outcome.plan.of(Verb.ORPHANED)),
                },
            )
        except Exception as exc:
            raise ClusterError(
                f"could not write status for {name}",
                remedy=(
                    "The declarations that landed are still applied — the status "
                    "is the part that failed. Kubernetes will call this again, "
                    "and the reconcile is idempotent."
                ),
                context={"resource": name, "error": type(exc).__name__},
            ) from exc


class MemoryCluster(ResourceClient, DeclarationStore):
    """Both seams, in memory. The reference the loop is developed against.

    One class rather than two so a test reads as one cluster, and because the
    interesting behaviour is how the two sides move together across successive
    reconciles — which is exactly what a controller has to get right and what a
    single pass cannot show.
    """

    def __init__(
        self,
        resources: Sequence[Mapping[str, Any]] = (),
        stored: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> None:
        self.resources = [dict(r) for r in resources]
        self.stored: dict[str, list[dict[str, Any]]] = {
            tenant: [dict(d) for d in items] for tenant, items in (stored or {}).items()
        }
        self.statuses: dict[str, dict[str, Any]] = {}
        self.status_writes = 0
        self.fail_on: set[str] = set()

    def list_estates(self) -> Sequence[Mapping[str, Any]]:
        return list(self.resources)

    def write_status(self, name: str, status: Mapping[str, Any]) -> None:
        self.status_writes += 1
        self.statuses[name] = dict(status)

    def declarations(self, tenant: str) -> Sequence[Mapping[str, Any]]:
        return list(self.stored.get(tenant, []))

    def apply(self, tenant: str, dataset: Mapping[str, Any]) -> None:
        name = str(dataset.get("name", ""))
        if name in self.fail_on:
            raise RuntimeError("the store rejected this declaration")
        held = self.stored.setdefault(tenant, [])
        for index, existing in enumerate(held):
            if existing.get("name") == name:
                held[index] = dict(dataset)
                return
        held.append(dict(dataset))

    def condition(self, name: str) -> dict[str, Any]:
        condition: dict[str, Any] = self.statuses[name]["conditions"][0]
        return condition
