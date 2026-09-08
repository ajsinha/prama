"""GitOps: the semantic layer as reviewable files.

The estate is authored in a UI by business people and reviewed in Git by
engineers, and both must be the same thing. That is the whole requirement, and
it has two halves:

* **Round-trip fidelity.** Export, edit, re-apply must be lossless. A serialiser
  that quietly drops a field turns a review into a data-loss event.
* **Drift is bidirectional.** Someone edits the UI; someone else edits the YAML.
  Both are legitimate, and the disagreement must be visible rather than resolved
  by whoever writes last.

What is deliberately *not* serialised: the bitemporal machinery. A Git file
describes the declaration as it stands, not its version history — history
belongs to the store, which is append-only and cannot be reconstructed from a
file anyone can edit. Re-applying a file therefore produces an *amendment*, with
provenance naming the commit, rather than rewriting the past.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

import yaml

from prama.core.errors import ValidationError
from prama.version import SCHEMA_VERSION

#: Bumped when the on-disk layout changes in a way older files cannot satisfy.
GITOPS_VERSION = "1"


class DriftDirection(enum.Enum):
    """Which side holds something the other does not."""

    ONLY_IN_STORE = "only_in_store"
    ONLY_IN_GIT = "only_in_git"
    DIFFERENT = "different"

    @property
    def summary(self) -> str:
        return {
            DriftDirection.ONLY_IN_STORE: "declared in Prama, absent from Git",
            DriftDirection.ONLY_IN_GIT: "present in Git, not declared in Prama",
            DriftDirection.DIFFERENT: "declared differently in Prama and Git",
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Drift:
    """One disagreement between the store and the repository."""

    direction: DriftDirection
    kind: str
    identifier: str
    fields: tuple[str, ...] = ()

    def render(self) -> str:
        detail = f" ({', '.join(self.fields)})" if self.fields else ""
        return f"{self.kind} {self.identifier}: {self.direction.summary}{detail}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction.value,
            "kind": self.kind,
            "identifier": self.identifier,
            "fields": list(self.fields),
            "message": self.render(),
        }


class EstateSerialiser:
    """Renders the semantic layer to files, and reads them back.

    Field order is fixed and keys are not sorted alphabetically: the file is
    read by humans in review, so ``name`` and ``owner`` belong at the top and
    the machinery belongs at the bottom. A diff that reorders on every export is
    a diff nobody reads.
    """

    DATASET_FIELDS = (
        "name",
        "slug",
        "description",
        "purpose",
        "owner_id",
        "steward_id",
        "custodian_id",
        "criticality",
        "shape",
        "domain_id",
        "grain",
        "rhythm",
        "temporality",
        "authoritativeness",
        "source_of_truth_id",
        "sensitivity",
        "jurisdiction",
        "retention_days",
        "lifecycle_state",
        "tags",
    )
    RELATIONSHIP_FIELDS = (
        "kind",
        "from_dataset",
        "to_dataset",
        "name",
        "description",
        "match_keys",
        "compare",
        "cardinality",
        "tolerance",
        "offset",
        "filter_expression",
        "owner_id",
        "criticality",
        "status",
    )

    # -- rendering ---------------------------------------------------------

    def dataset_document(
        self, version: Any, attributes: list[Any], *, slug_of: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """One dataset and its attributes, as a reviewable document."""
        slugs = slug_of or {}
        document: dict[str, Any] = {
            "apiVersion": f"prama/v{GITOPS_VERSION}",
            "kind": "Dataset",
            "metadata": {"slug": version.slug, "name": version.name},
            "spec": _compact_mapping(
                {
                    "description": version.description,
                    "purpose": version.purpose,
                    "owner": version.owner_id,
                    "steward": version.steward_id,
                    "criticality": version.criticality,
                    "shape": version.shape,
                    "domain": slugs.get(version.domain_id or "", version.domain_id),
                    "grain": version.grain_json,
                    "rhythm": version.rhythm_json,
                    "temporality": version.temporality,
                    "authoritativeness": version.authoritativeness,
                    "sensitivity": version.sensitivity,
                    "jurisdiction": version.jurisdiction,
                    "retention_days": version.retention_days,
                    "lifecycle": version.lifecycle_state,
                    "tags": list(version.tags_json or []),
                }
            ),
            "attributes": [self.attribute_document(a) for a in attributes],
        }
        return document

    def attribute_document(self, version: Any) -> dict[str, Any]:
        return _compact_mapping(
            {
                "name": version.name,
                "definition": version.definition,
                "interpretation": version.interpretation,
                "semantic_type": version.semantic_type,
                "unit": version.unit,
                "currency_attribute": version.currency_attribute,
                "precision": version.numeric_precision,
                "scale": version.numeric_scale,
                "value_domain": version.value_domain_json,
                "optionality": version.optionality,
                "optionality_condition": version.optionality_condition,
                "cde": version.is_cde or None,
                "obligations": list(version.obligations_json or []) or None,
                "sensitivity": version.sensitivity,
                "concept_property": version.concept_property_id,
                "glossary_term": version.glossary_term,
            }
        )

    def relationship_document(
        self, version: Any, *, slug_of: dict[str, str] | None = None
    ) -> dict[str, Any]:
        slugs = slug_of or {}
        left = slugs.get(version.from_dataset_id, version.from_dataset_id)
        right = slugs.get(version.to_dataset_id, version.to_dataset_id)
        return {
            "apiVersion": f"prama/v{GITOPS_VERSION}",
            "kind": "Relationship",
            # A short, stable name a reviewer can scan; the full sentence the
            # declaration renders to belongs in the description, where wrapping
            # it is harmless.
            "metadata": {"name": f"{left}_{version.kind}_{right}"[:120]},
            "spec": _compact_mapping(
                {
                    "kind": version.kind,
                    "from": left,
                    "to": right,
                    "description": version.description or version.name,
                    "match_keys": list(version.match_keys_json or []),
                    "compare": list(version.compare_json or []),
                    "cardinality": version.cardinality,
                    "tolerance": version.tolerance_json,
                    "offset": version.offset_json,
                    "filter": version.filter_expression,
                    "owner": version.owner_id,
                    "criticality": version.criticality,
                    "status": version.status,
                }
            ),
        }

    def journey_document(
        self, version: Any, *, slug_of: dict[str, str] | None = None
    ) -> dict[str, Any]:
        slugs = slug_of or {}
        steps = []
        for step in version.steps_json or []:
            rendered = dict(step)
            if rendered.get("dataset_id"):
                rendered["dataset"] = slugs.get(rendered["dataset_id"], rendered["dataset_id"])
                rendered.pop("dataset_id")
            steps.append(rendered)
        return {
            "apiVersion": f"prama/v{GITOPS_VERSION}",
            "kind": "Journey",
            "metadata": {"slug": version.slug, "name": version.name},
            "spec": _compact_mapping(
                {
                    "description": version.description,
                    "owner": version.owner_id,
                    "criticality": version.criticality,
                    "sla": version.sla_json,
                    "steps": steps,
                }
            ),
        }

    def connection_document(self, version: Any) -> dict[str, Any]:
        """A connection, with its credential reference and never its secret."""
        return {
            "apiVersion": f"prama/v{GITOPS_VERSION}",
            "kind": "Connection",
            "metadata": {"slug": version.slug, "name": version.name},
            "spec": _compact_mapping(
                {
                    "source_type": version.source_type,
                    "description": version.description,
                    "config": version.config_json,
                    # A vault reference, never a secret. The pre-commit hook
                    # refuses a tracked file containing one, and this is why
                    # that hook can be trusted.
                    "credential_ref": version.credential_ref,
                    "read_policy": version.read_policy_json,
                    "budget": version.budget_json,
                    "owner": version.owner_id,
                }
            ),
        }

    # -- files -------------------------------------------------------------

    @staticmethod
    def path_for(kind: str, slug: str, *, domain: str | None = None) -> str:
        """The documented on-disk layout (docs/14 §5)."""
        folder = {
            "Dataset": "datasets",
            "Relationship": "relationships",
            "Journey": "journeys",
            "Connection": "connections",
            "Concept": "concepts",
            "Domain": "domains",
        }[kind]
        if kind in ("Dataset", "Relationship") and domain:
            return f"prama/domains/{domain}/{folder}/{slug}.yaml"
        return f"prama/{folder}/{slug}.yaml"

    @staticmethod
    def dump(document: dict[str, Any]) -> str:
        """YAML with insertion order preserved, so diffs stay readable."""
        return yaml.safe_dump(
            document, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100
        )

    @staticmethod
    def load(text: str) -> dict[str, Any]:
        try:
            document = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValidationError(
                f"invalid YAML: {exc}",
                remedy="Fix the syntax reported above and re-apply.",
                cause=exc,
            ) from exc
        if not isinstance(document, dict):
            raise ValidationError(
                "a Prama document must be a mapping",
                remedy="Wrap the document in apiVersion / kind / metadata / spec keys.",
            )
        for required in ("apiVersion", "kind", "metadata"):
            if required not in document:
                raise ValidationError(
                    f"document is missing {required!r}",
                    remedy=(
                        "Every Prama document declares apiVersion, kind and metadata. "
                        "Export an existing object to see the shape."
                    ),
                    context={"missing": required},
                )
        version = str(document["apiVersion"]).removeprefix("prama/v")
        if version != GITOPS_VERSION:
            raise ValidationError(
                f"document uses layout version {version}, this build expects {GITOPS_VERSION}",
                remedy="Re-export the estate with this version of Prama, then re-apply.",
                context={"found": version, "expected": GITOPS_VERSION},
            )
        return document

    def manifest(self, *, tenant: str, counts: dict[str, int]) -> str:
        """A lock file recording what an export contained."""
        return self.dump(
            {
                "apiVersion": f"prama/v{GITOPS_VERSION}",
                "kind": "Manifest",
                "metadata": {"tenant": tenant, "schema_version": SCHEMA_VERSION},
                "contents": dict(sorted(counts.items())),
            }
        )


class DriftDetector:
    """Compares the store's view with the repository's, in both directions.

    Neither side wins automatically. A UI edit and a YAML edit are both
    legitimate, and silently resolving in favour of one is how a governance tool
    loses a declaration somebody made deliberately.
    """

    #: Fields excluded from comparison because they are the store's business,
    #: not the repository's: identity, versioning and derived state.
    IGNORED = frozenset(
        {
            "id",
            "version",
            "recorded_at",
            "superseded_at",
            "valid_from",
            "valid_to",
            "authored_by",
            "approved_by",
            "approved_at",
            "change_reason",
        }
    )

    def compare(
        self,
        store: dict[str, dict[str, Any]],
        repository: dict[str, dict[str, Any]],
        *,
        kind: str,
    ) -> list[Drift]:
        """Compare two mappings of identifier to specification."""
        drifts: list[Drift] = []
        for identifier in sorted(set(store) - set(repository)):
            drifts.append(Drift(DriftDirection.ONLY_IN_STORE, kind, identifier))
        for identifier in sorted(set(repository) - set(store)):
            drifts.append(Drift(DriftDirection.ONLY_IN_GIT, kind, identifier))
        for identifier in sorted(set(store) & set(repository)):
            differing = self._differing_fields(store[identifier], repository[identifier])
            if differing:
                drifts.append(Drift(DriftDirection.DIFFERENT, kind, identifier, tuple(differing)))
        return drifts

    def _differing_fields(self, left: dict[str, Any], right: dict[str, Any]) -> list[str]:
        keys = (set(left) | set(right)) - self.IGNORED
        return sorted(
            key for key in keys if _normalise(left.get(key)) != _normalise(right.get(key))
        )

    @staticmethod
    def summarise(drifts: list[Drift]) -> str:
        if not drifts:
            return "in sync: no drift between Prama and the repository"
        return "\n".join([f"{len(drifts)} difference(s):", *(f"  - {d.render()}" for d in drifts)])


def _compact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """``_compact`` at the top level, typed as the mapping it always returns."""
    compacted = _compact(mapping)
    assert isinstance(compacted, dict)
    return compacted


def _compact(value: Any) -> Any:
    """Drop empty values, at every depth, so a file shows what was declared.

    A document full of ``null`` is a document nobody reads, and it makes every
    diff noisier than the change it contains. Recursion matters: the noise lives
    in the nested value objects — a tolerance carrying ``relative: null`` and a
    match key carrying ``right: null`` are exactly what a reviewer has to read
    past to find the change.
    """
    if isinstance(value, dict):
        cleaned = {k: _compact(v) for k, v in value.items()}
        return {k: v for k, v in cleaned.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    return value


def _normalise(value: Any) -> Any:
    """Compare by content, not by representation.

    An absent key, an explicit null and an empty list all mean the same thing to
    a reviewer, so they must mean the same thing to the comparison. The empty
    check comes first for that reason: an empty list normalised as an empty
    tuple would not equal None, and every export would show phantom drift.
    """
    if value is None or (isinstance(value, (str, list, tuple, dict)) and not value):
        return None
    if isinstance(value, dict):
        return tuple(sorted((k, _normalise(v)) for k, v in value.items() if v not in (None, "")))
    if isinstance(value, (list, tuple)):
        return tuple(_normalise(v) for v in value)
    return value
