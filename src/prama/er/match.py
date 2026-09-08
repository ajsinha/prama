"""Deciding whether two records describe the same thing.

`FR-ERM-001`…`009`. Entity resolution is the oldest problem in this field and
the one most often solved with a similarity threshold somebody tuned once. The
threshold approach fails in a specific and predictable way: it works on the
data it was tuned on, and the first time the population shifts — a new country,
a new naming convention, an acquisition — it fails silently, because a
similarity score has no units and nobody can tell 0.82 from 0.79.

**Fellegi-Sunter gives the score units.** The weight of a piece of evidence is
the log-ratio of two probabilities: how often that agreement happens between
records that *are* the same thing, against how often it happens by chance. A
matching surname is weak evidence in a population of Smiths and strong evidence
in a population of Nakagawas, and the arithmetic says so on its own rather than
needing somebody to notice.

**The two probabilities are estimated from the data, not assumed.** The chance
rate is measurable directly — it is how often the field agrees between random
pairs. The match rate is not, and expectation-maximisation recovers it from the
pattern of agreements without anybody labelling anything, which is the whole
reason to use this method rather than a classifier.

**Blocking is the only reason this runs at all**, and it is also where recall
is lost for good: a pair never compared can never match, so a blocking key that
is wrong loses records silently and no amount of downstream cleverness recovers
them. So blocking is on several keys at once, and the pairs each key contributes
are counted — a key contributing nothing is a key that is wrong.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import math
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

#: Log-odds above which a pair is a match, and below which a non-match. The
#: band between them is the review queue, and its existence is the point: a
#: single threshold forces every uncertain pair into a decision nobody made.
MATCH_THRESHOLD = 4.0
NON_MATCH_THRESHOLD = -2.0

#: Probabilities are clamped away from 0 and 1 before taking logs. Without
#: this a field that agreed on every training pair produces an infinite weight
#: and one disagreement outvotes every other piece of evidence forever.
EPSILON = 1e-4


class Decision(enum.Enum):
    MATCH = "match"
    #: Neither. The band between the thresholds, and the reason there are two:
    #: a single threshold forces every uncertain pair into a decision nobody
    #: made, and the uncertain ones are exactly the ones worth a person.
    REVIEW = "review"
    NON_MATCH = "non_match"


@dataclasses.dataclass(frozen=True, slots=True)
class Comparison:
    """How one field is compared, and what agreement on it is worth."""

    field: str
    compare: Callable[[Any, Any], bool] = dataclasses.field(compare=False, repr=False)
    #: P(agree | the records are the same thing). Estimated, not assumed.
    m: float = 0.9
    #: P(agree | they are different things). Measurable directly.
    u: float = 0.1
    description: str = ""

    @property
    def agreement_weight(self) -> float:
        """What agreeing on this field is worth, in log-odds.

        The number that makes a similarity score mean something: a matching
        surname among Smiths and among Nakagawas produce different weights from
        the same comparison function, because `u` differs and the arithmetic
        notices without anybody telling it.
        """
        return math.log2(_clamp(self.m) / _clamp(self.u))

    @property
    def disagreement_weight(self) -> float:
        return math.log2(_clamp(1 - self.m) / _clamp(1 - self.u))

    def agrees(self, left: Mapping[str, Any], right: Mapping[str, Any]) -> bool | None:
        """Whether the field agrees, or None when it cannot say.

        Separate from :meth:`weigh` because inferring agreement from the sign
        of the weight is wrong at exactly one point, and that point is where
        expectation-maximisation starts: with ``m == u`` the weight is zero,
        ``weight > 0`` is False, and every agreement is counted as a
        disagreement — so EM initialised at 0.5/0.5 drives both parameters to
        the floor and returns a field worth nothing.
        """
        a, b = left.get(self.field), right.get(self.field)
        if a is None or b is None or a == "" or b == "":
            return None
        return self.compare(a, b)

    def weigh(self, left: Mapping[str, Any], right: Mapping[str, Any]) -> float | None:
        """The evidence this field contributes, or None when it cannot say.

        A missing value contributes *nothing* rather than counting as
        disagreement. Counting it as disagreement is the single most common
        implementation error here, and it systematically separates exactly the
        records most likely to be duplicates — the sparse ones.
        """
        agreed = self.agrees(left, right)
        if agreed is None:
            return None
        return self.agreement_weight if agreed else self.disagreement_weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "m": round(self.m, 6),
            "u": round(self.u, 6),
            "agreement_weight": round(self.agreement_weight, 4),
            "disagreement_weight": round(self.disagreement_weight, 4),
            "description": self.description,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Judgement:
    """One pair, scored, with the evidence that produced the score."""

    left: str
    right: str
    score: float
    decision: Decision
    #: Field by field, so a disputed match can be argued with rather than
    #: appealed to.
    contributions: tuple[tuple[str, float], ...] = ()
    #: Fields that could not be compared. Reported because a match resting on
    #: two fields out of seven is a different claim from one resting on seven.
    uninformative: tuple[str, ...] = ()

    def describe(self) -> str:
        strongest = sorted(self.contributions, key=lambda item: -abs(item[1]))[:3]
        detail = ", ".join(f"{field} {weight:+.1f}" for field, weight in strongest)
        head = f"{self.left} / {self.right}: {self.score:+.1f} — {detail}"
        if self.uninformative:
            head += (
                f". {len(self.uninformative)} field(s) could not be compared "
                f"({', '.join(self.uninformative)}), so this rests on less evidence "
                f"than it looks like"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "score": round(self.score, 4),
            "decision": self.decision.value,
            "contributions": [[field, round(weight, 4)] for field, weight in self.contributions],
            "uninformative": list(self.uninformative),
            "description": self.describe(),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class BlockingKey:
    """A cheap key that brings candidate pairs together.

    Where recall is lost for good: a pair never compared can never match, so a
    wrong key loses records silently and nothing downstream recovers them.
    """

    name: str
    of: Callable[[Mapping[str, Any]], str | None] = dataclasses.field(compare=False, repr=False)

    def key(self, record: Mapping[str, Any]) -> str | None:
        return self.of(record)


@dataclasses.dataclass(frozen=True, slots=True)
class Resolution:
    """What resolving a population concluded."""

    matches: tuple[Judgement, ...] = ()
    review: tuple[Judgement, ...] = ()
    #: Pairs compared, and pairs that would have been compared without
    #: blocking. The saving, and the risk.
    compared: int = 0
    total_possible: int = 0
    #: Pairs each blocking key produced, and how many of those no other key
    #: had already found. Both, because they answer different questions: a key
    #: producing nothing at all is wrong, and a key producing plenty that
    #: another key already found is merely redundant. Reporting only the second
    #: makes every redundant key look broken, which is how somebody deletes the
    #: one that was carrying the population they had not thought about.
    by_key: Mapping[str, int] = dataclasses.field(default_factory=dict)
    unique_by_key: Mapping[str, int] = dataclasses.field(default_factory=dict)

    @property
    def reduction(self) -> float:
        return 1.0 - (self.compared / self.total_possible) if self.total_possible else 0.0

    @property
    def useless_keys(self) -> tuple[str, ...]:
        """Keys that brought no pairs together at all."""
        return tuple(name for name, count in self.by_key.items() if count == 0)

    @property
    def redundant_keys(self) -> tuple[str, ...]:
        """Keys whose every pair another key had already found.

        Not wrong, and worth knowing: a redundant key costs time and may be
        carrying a population nobody has thought about yet, so it is reported
        as redundant rather than as useless.
        """
        return tuple(
            name
            for name, count in self.by_key.items()
            if count > 0 and self.unique_by_key.get(name, 0) == 0
        )

    def describe(self) -> str:
        head = (
            f"{len(self.matches)} matches and {len(self.review)} for review from "
            f"{self.compared:,} pairs compared "
            f"({self.reduction:.2%} of the {self.total_possible:,} possible pairs "
            f"were never looked at)"
        )
        if self.useless_keys:
            head += (
                f". {', '.join(self.useless_keys)} brought no pairs together at all, "
                f"which usually means the key is wrong rather than that there is "
                f"nothing to find"
            )
        if self.redundant_keys:
            head += (
                f". {', '.join(self.redundant_keys)} found only pairs another key had "
                f"already found — redundant rather than wrong, and worth keeping if "
                f"the population it covers might grow"
            )
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "matches": [item.to_dict() for item in self.matches],
            "review": [item.to_dict() for item in self.review],
            "compared": self.compared,
            "total_possible": self.total_possible,
            "reduction": round(self.reduction, 6),
            "by_key": dict(self.by_key),
            "unique_by_key": dict(self.unique_by_key),
            "useless_keys": list(self.useless_keys),
            "redundant_keys": list(self.redundant_keys),
            "summary": self.describe(),
        }


class Resolver:
    """Fellegi-Sunter over blocked candidate pairs."""

    def __init__(
        self,
        comparisons: Sequence[Comparison],
        blocking: Sequence[BlockingKey],
        *,
        match_threshold: float = MATCH_THRESHOLD,
        non_match_threshold: float = NON_MATCH_THRESHOLD,
    ) -> None:
        self._comparisons = tuple(comparisons)
        self._blocking = tuple(blocking)
        self._match = match_threshold
        self._non_match = non_match_threshold

    def resolve(self, records: Sequence[Mapping[str, Any]], *, identity: str = "id") -> Resolution:
        pairs, by_key, unique_by_key = self._candidates(records, identity)
        matches: list[Judgement] = []
        review: list[Judgement] = []

        for left, right in pairs:
            judgement = self.judge(left, right, identity=identity)
            if judgement.decision is Decision.MATCH:
                matches.append(judgement)
            elif judgement.decision is Decision.REVIEW:
                review.append(judgement)

        total = len(records) * (len(records) - 1) // 2
        return Resolution(
            matches=tuple(sorted(matches, key=lambda item: -item.score)),
            review=tuple(sorted(review, key=lambda item: -item.score)),
            compared=len(pairs),
            total_possible=total,
            by_key=by_key,
            unique_by_key=unique_by_key,
        )

    def judge(
        self,
        left: Mapping[str, Any],
        right: Mapping[str, Any],
        *,
        identity: str = "id",
    ) -> Judgement:
        contributions: list[tuple[str, float]] = []
        uninformative: list[str] = []
        for comparison in self._comparisons:
            weight = comparison.weigh(left, right)
            if weight is None:
                uninformative.append(comparison.field)
                continue
            contributions.append((comparison.field, weight))

        score = sum(weight for _, weight in contributions)
        if score >= self._match:
            decision = Decision.MATCH
        elif score <= self._non_match:
            decision = Decision.NON_MATCH
        else:
            decision = Decision.REVIEW

        return Judgement(
            left=str(left.get(identity, "?")),
            right=str(right.get(identity, "?")),
            score=score,
            decision=decision,
            contributions=tuple(contributions),
            uninformative=tuple(uninformative),
        )

    def _candidates(
        self, records: Sequence[Mapping[str, Any]], identity: str
    ) -> tuple[
        list[tuple[Mapping[str, Any], Mapping[str, Any]]],
        dict[str, int],
        dict[str, int],
    ]:
        seen: set[tuple[str, str]] = set()
        pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        by_key: dict[str, int] = {key.name: 0 for key in self._blocking}
        unique_by_key: dict[str, int] = {key.name: 0 for key in self._blocking}

        for key in self._blocking:
            buckets: dict[str, list[Mapping[str, Any]]] = {}
            for record in records:
                value = key.key(record)
                if value:
                    buckets.setdefault(value, []).append(record)
            for bucket in buckets.values():
                for index, left in enumerate(bucket):
                    for right in bucket[index + 1 :]:
                        marker = tuple(sorted((str(left.get(identity)), str(right.get(identity)))))
                        # Counted for this key whether or not another key found
                        # it first: crediting only the first key makes every
                        # redundant key look broken, and that is how somebody
                        # deletes the one carrying a population nobody had
                        # thought about.
                        by_key[key.name] += 1
                        if marker in seen:
                            continue
                        seen.add(marker)  # type: ignore[arg-type]
                        pairs.append((left, right))
                        unique_by_key[key.name] += 1
        return pairs, by_key, unique_by_key


# ---------------------------------------------------------------------------
# Estimating m and u
# ---------------------------------------------------------------------------


def estimate_u(
    records: Sequence[Mapping[str, Any]],
    comparison: Comparison,
    *,
    sample: int = 2000,
    seed: int = 7,
) -> float:
    """How often this field agrees between records that are *not* the same.

    Measurable directly, because almost every random pair from a population is
    a non-match: with ten thousand records there are fifty million pairs and at
    most a few thousand true matches, so a random sample is a non-match sample
    to within a rounding error.
    """
    import random

    rng = random.Random(seed)
    if len(records) < 2:
        return 0.5
    agreed = compared = 0
    for _ in range(sample):
        left, right = rng.sample(range(len(records)), 2)
        agrees = comparison.agrees(records[left], records[right])
        if agrees is None:
            continue
        compared += 1
        agreed += agrees
    return _clamp(agreed / compared) if compared else 0.5


def estimate_m(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    comparison: Comparison,
) -> float:
    """How often this field agrees between records that *are* the same.

    From labelled pairs when there are any. Where there are none,
    :func:`expectation_maximisation` recovers it from the pattern of agreements
    — which is the whole reason to use this method rather than a classifier
    that needs a training set nobody has.
    """
    agreed = compared = 0
    for left, right in pairs:
        agrees = comparison.agrees(left, right)
        if agrees is None:
            continue
        compared += 1
        agreed += agrees
    return _clamp(agreed / compared) if compared else 0.9


def expectation_maximisation(
    comparisons: Sequence[Comparison],
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    *,
    rounds: int = 20,
) -> tuple[Comparison, ...]:
    """Recover m and u from the pattern of agreements, without labels.

    The classic result: given several conditionally independent comparisons,
    the mixture of matches and non-matches is identifiable from the agreement
    patterns alone. Conditional independence is the assumption, and it is
    routinely violated — first name and last name agree together more often
    than chance because of families — so the estimates are approximate, and
    treating them as exact is where this method gets a bad name.
    """
    # m == u is a saddle point, and a common way to start. With the two equal
    # every pair receives exactly the prior as its responsibility, both
    # parameters update to the same value, and the algorithm sits there for as
    # many rounds as it is given — returning fields worth zero bits and no
    # indication that anything went wrong.
    #
    # Breaking the symmetry encodes the one thing known a priori: a field
    # agreeing is evidence *for* a match rather than against. It is an
    # initialisation, not an assumption about the answer — EM moves both
    # parameters from here.
    current = [
        dataclasses.replace(comparison, m=0.9, u=0.1)
        if comparison.m <= comparison.u
        else comparison
        for comparison in comparisons
    ]
    prior = 0.1

    for _ in range(rounds):
        responsibilities: list[float] = []
        for left, right in pairs:
            match_likelihood = 1.0
            non_match_likelihood = 1.0
            for comparison in current:
                agrees = comparison.agrees(left, right)
                if agrees is None:
                    continue
                match_likelihood *= comparison.m if agrees else (1 - comparison.m)
                non_match_likelihood *= comparison.u if agrees else (1 - comparison.u)
            numerator = prior * match_likelihood
            denominator = numerator + (1 - prior) * non_match_likelihood
            responsibilities.append(numerator / denominator if denominator else 0.0)

        if not responsibilities:
            return tuple(current)
        prior = _clamp(sum(responsibilities) / len(responsibilities))

        updated: list[Comparison] = []
        for comparison in current:
            match_weight = match_agreed = 0.0
            non_weight = non_agreed = 0.0
            for (left, right), responsibility in zip(pairs, responsibilities, strict=True):
                agrees = comparison.agrees(left, right)
                if agrees is None:
                    continue
                agreed = 1.0 if agrees else 0.0
                match_weight += responsibility
                match_agreed += responsibility * agreed
                non_weight += 1 - responsibility
                non_agreed += (1 - responsibility) * agreed
            updated.append(
                dataclasses.replace(
                    comparison,
                    m=_clamp(match_agreed / match_weight) if match_weight else comparison.m,
                    u=_clamp(non_agreed / non_weight) if non_weight else comparison.u,
                )
            )
        current = updated
    return tuple(current)


# ---------------------------------------------------------------------------
# Comparison functions
# ---------------------------------------------------------------------------


def exact(left: Any, right: Any) -> bool:
    return str(left).strip().upper() == str(right).strip().upper()


def normalised(left: Any, right: Any) -> bool:
    """Equal after stripping punctuation and legal-form noise.

    "ACME Ltd." and "Acme Limited" are the same company, and a comparison that
    says otherwise makes every entity resolution over company names useless
    before the arithmetic starts.
    """
    return _normalise_name(left) == _normalise_name(right)


def similar(threshold: float = 0.85) -> Callable[[Any, Any], bool]:
    """Agreement when two strings are close enough, by trigram overlap."""

    def compare(left: Any, right: Any) -> bool:
        return _trigram_similarity(str(left), str(right)) >= threshold

    return compare


_LEGAL_FORMS = (
    "limited",
    "ltd",
    "plc",
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "llc",
    "llp",
    "gmbh",
    "ag",
    "sa",
    "nv",
    "bv",
    "spa",
    "srl",
    "pty",
    "company",
    "co",
    "holdings",
    "group",
)


def _normalise_name(value: Any) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", str(value).lower())
    words = [word for word in text.split() if word and word not in _LEGAL_FORMS]
    return " ".join(words)


def _trigram_similarity(left: str, right: str) -> float:
    a, b = _trigrams(left), _trigrams(right)
    if not a or not b:
        return 1.0 if left == right else 0.0
    return len(a & b) / len(a | b)


def _trigrams(value: str) -> set[str]:
    padded = f"  {value.lower().strip()}  "
    return {padded[index : index + 3] for index in range(len(padded) - 2)}


def _clamp(value: float) -> float:
    """Keep a probability away from 0 and 1.

    Without this a field that agreed on every observed pair produces an
    infinite weight, and one disagreement then outvotes every other piece of
    evidence forever.
    """
    return min(1 - EPSILON, max(EPSILON, value))
