"""Correlating datasets through what their attributes *mean*, not what they are called.

Two columns in two datasets are the same thing when the business says so: both
bound to one concept property, or to one glossary term. That is a stronger
signal than any name match, and it needs no data access. From it follow three
things:

* **Groups.** The attributes across the estate that carry one meaning, each
  with the signals that put it there. A semantic type alone (two columns both
  of type `currency`) groups for consistency only: every table has a currency,
  and that is not a relationship.
* **Reference proposals.** Within a group bound by concept or term, when
  exactly one dataset declares the attribute as its key (its grain, or its
  `key` metadata), every other member should reference it:
  `CHECK trades.counterparty_lei REFERENCES counterparties.lei`. Proposed, for a
  person to accept, like every derived control.
* **Consistency findings.** The same meaning held differently: validated as an
  ISIN in one place and free text in another, marked personal data here and not
  there, a different list of allowed values, a CDE in one dataset and not its
  copy. These are findings for a steward, not controls, because which side is
  right is a business decision.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

#: Semantic types too common to say two columns are the same thing.
GENERIC_TYPES = frozenset({"currency", "iso_date", "date", "timestamp", "country", "boolean"})

#: Metadata fields whose difference within one meaning is worth a finding.
COMPARED_METADATA = ("allowed_values", "pattern", "pii", "minimum", "maximum")


@dataclasses.dataclass(frozen=True, slots=True)
class AttributeFact:
    dataset: str
    attribute: str
    concept_property: str = ""
    terms: tuple[str, ...] = ()
    semantic_type: str = ""
    is_key: bool = False
    is_cde: bool = False
    sensitivity: str = ""
    metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    described: bool = True

    @property
    def qualified(self) -> str:
        return f"{self.dataset}.{self.attribute}"


@dataclasses.dataclass(frozen=True, slots=True)
class Group:
    meaning: str
    by: str
    members: tuple[AttributeFact, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class Finding:
    meaning: str
    aspect: str
    detail: str
    members: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True)
class ReferenceProposal:
    identity: str
    dataset: str
    pql: str
    sentence: str
    rule: str = "correlation_reference"


def groups(facts: Iterable[AttributeFact]) -> list[Group]:
    """Attributes sharing a meaning, strongest signal first. An attribute joins the
    group of its strongest signal only, so one pair is not reported three times."""
    facts = list(facts)
    placed: set[str] = set()
    out: list[Group] = []
    for by in ("concept", "term", "semantic type"):
        buckets: dict[str, list[AttributeFact]] = {}
        for fact in facts:
            if fact.qualified in placed:
                continue
            for key in _keys(fact, by):
                buckets.setdefault(key, []).append(fact)
        for key, members in sorted(buckets.items()):
            datasets = {m.dataset for m in members}
            if len(datasets) < 2:
                continue
            fresh = [m for m in members if m.qualified not in placed]
            if len({m.dataset for m in fresh}) < 2:
                continue
            out.append(Group(meaning=key, by=by, members=tuple(fresh)))
            placed.update(m.qualified for m in fresh)
    return out


def _keys(fact: AttributeFact, by: str) -> list[str]:
    if by == "concept":
        return [fact.concept_property] if fact.concept_property else []
    if by == "term":
        return list(fact.terms)
    return [fact.semantic_type] if fact.semantic_type else []


def references(group: Group) -> list[ReferenceProposal]:
    """Every member references the one dataset that owns the meaning as its key."""
    from prama.pql.ast import quote_dataset

    if group.by == "semantic type" or group.meaning in GENERIC_TYPES:
        return []
    owners = [m for m in group.members if m.is_key]
    if len({o.dataset for o in owners}) != 1:
        return []  # nobody owns it, or two datasets claim to: a question, not a check
    owner = owners[0]
    out = []
    for member in group.members:
        if member.dataset == owner.dataset:
            continue
        pql = (
            f"CHECK {quote_dataset(member.dataset)}.{member.attribute} REFERENCES "
            f"{quote_dataset(owner.dataset)}.{owner.attribute} "
            f"BECAUSE 'both mean {group.meaning} ({group.by}); {owner.dataset} is keyed by it'"
        )
        identity = (
            "correlation-"
            + hashlib.sha256(f"{member.qualified}|{owner.qualified}".encode()).hexdigest()[:24]
        )
        out.append(
            ReferenceProposal(
                identity=identity,
                dataset=member.dataset,
                pql=pql,
                sentence=(
                    f"{member.qualified} and {owner.qualified} both mean {group.meaning} "
                    f"(same {group.by}), and {owner.dataset} is keyed by it, so every "
                    f"{member.attribute} should exist there."
                ),
            )
        )
    return out


def findings(group: Group) -> list[Finding]:
    """Where one meaning is held differently across the group's members."""
    out: list[Finding] = []

    def differs(aspect: str, value_of: Any, render: Any = str) -> None:
        values: dict[str, list[str]] = {}
        for member in group.members:
            values.setdefault(render(value_of(member)), []).append(member.qualified)
        if len(values) > 1:
            detail = "; ".join(
                f"{v or '(none)'}: {', '.join(m)}" for v, m in sorted(values.items())
            )
            out.append(
                Finding(group.meaning, aspect, detail, tuple(m.qualified for m in group.members))
            )

    if group.by != "semantic type":
        differs("semantic type", lambda m: m.semantic_type)
    differs("sensitivity", lambda m: m.sensitivity)
    differs("critical data element", lambda m: "CDE" if m.is_cde else "not a CDE")
    for name in COMPARED_METADATA:
        if any(name in m.metadata for m in group.members):
            differs(
                name,
                lambda m, n=name: m.metadata.get(n),
                lambda v: (
                    ", ".join(map(str, v)) if isinstance(v, list) else "" if v is None else str(v)
                ),
            )
    undescribed = [m.qualified for m in group.members if not m.described]
    if undescribed and len(undescribed) < len(group.members):
        out.append(
            Finding(
                group.meaning,
                "description",
                f"described elsewhere but not in {', '.join(undescribed)}",
                tuple(m.qualified for m in group.members),
            )
        )
    return out
