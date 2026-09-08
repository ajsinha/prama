"""What a column actually holds — inferred, with the evidence attached.

The inference cascade of `FR-PRF-004`: checksums, then code lists, then
patterns, then names, then embeddings, then a model adjudicating over a closed
vocabulary. The order is not a preference. It is a ranking by **what the answer
is worth**, and the cascade stops at the first stage that produces evidence.

A check digit is proof. Four hundred values satisfying ISO 6166 did not do so
by accident, and the classifier can say precisely how unlikely the accident is.
A column *name* is not proof of anything: ``isin`` is what somebody typed once,
possibly about a different column, possibly years ago. So a name is never
allowed to overrule a checksum — and where the two disagree, the disagreement
is reported rather than resolved.

That disagreement is the most valuable thing in this module. A column called
``lei`` in which 3% of values verify is not a column Prama should quietly
classify as LEIs and generate a control for; it is a finding, today, that
somebody needs to see. Classifying it would bury the discovery under a control
that alerts on 97% of rows and gets switched off by Friday.

**Nothing here decides a verdict.** A classification proposes a control; a
person approves it; the deterministic engine then decides. The model stages
cannot be auto-applied at all — see :attr:`Classification.may_auto_apply` — and
`tests/architecture/test_no_model_verdicts.py` is what keeps that true.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
import enum
import math
import re
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from prama.classify.codelists import REGISTRY as CODELISTS
from prama.classify.codelists import CodeListRegistry
from prama.classify.validators import REGISTRY as VALIDATORS
from prama.classify.validators import Expressibility, SemanticValidator, ValidatorRegistry

# ---------------------------------------------------------------------------
# The stages, in the order they are consulted
# ---------------------------------------------------------------------------


class Stage(enum.Enum):
    """Where an answer came from, which is most of what it is worth."""

    CHECKSUM = "checksum"
    CODELIST = "codelist"
    PATTERN = "pattern"
    NAME = "name"
    EMBEDDING = "embedding"
    MODEL = "model"

    @property
    def rank(self) -> int:
        return _STAGE_ORDER.index(self)

    @property
    def is_deterministic(self) -> bool:
        """Whether the answer can be recomputed identically, forever.

        The line the whole design turns on: a deterministic classification is
        evidence, and the other kind is a suggestion.
        """
        return self in (Stage.CHECKSUM, Stage.CODELIST, Stage.PATTERN)

    @property
    def is_content_based(self) -> bool:
        """Whether the answer looked at the data rather than at metadata."""
        return self in (Stage.CHECKSUM, Stage.CODELIST, Stage.PATTERN)


_STAGE_ORDER: tuple[Stage, ...] = (
    Stage.CHECKSUM,
    Stage.CODELIST,
    Stage.PATTERN,
    Stage.NAME,
    Stage.EMBEDDING,
    Stage.MODEL,
)


class Fit(enum.Enum):
    """How cleanly the column matches the type it was matched to."""

    #: Effectively every value conforms. The type is settled.
    CLEAN = "clean"
    #: A strong majority conform and a material minority do not. The type is
    #: settled *and the minority is the finding* — this is the outcome that
    #: makes classification worth doing at all.
    CONTAMINATED = "contaminated"
    #: No clear majority. Usually two things in one column, which is a worse
    #: problem than bad values and needs a person, not a control.
    MIXED = "mixed"

    @property
    def supports_a_control(self) -> bool:
        return self is not Fit.MIXED


class ConflictKind(enum.Enum):
    NAME_CONTRADICTED = "name_contradicted"
    AMBIGUOUS = "ambiguous"
    SENSITIVE_CONTENT = "sensitive_content"


@dataclasses.dataclass(frozen=True, slots=True)
class Conflict:
    """Something the classifier found that a person should decide."""

    kind: ConflictKind
    message: str
    #: The types involved, so the UI can offer them as the choice.
    candidates: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "message": self.message,
            "candidates": list(self.candidates),
        }


# ---------------------------------------------------------------------------
# Input and output
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class ColumnSample:
    """What the classifier is given: a name and some values.

    A sample rather than a column, because classification runs on a profile's
    reservoir and must never require a full scan to answer a metadata question.
    """

    name: str
    values: tuple[str | None, ...]
    dataset: str = ""
    #: The declared physical type, where the connector knew one. Used only to
    #: rule types out — a numeric column is not an ISIN however the digits fall.
    physical_type: str = ""
    comment: str = ""

    @property
    def populated(self) -> tuple[str, ...]:
        """Non-null, non-blank values. Nulls are a completeness question."""
        return tuple(v.strip() for v in self.values if v is not None and v.strip())


@dataclasses.dataclass(frozen=True, slots=True)
class Classification:
    """A proposed semantic type, with the reason it was proposed."""

    semantic_type: str
    stage: Stage
    fit: Fit
    #: Fraction of populated values that satisfy the type.
    hit_rate: float
    #: Populated values examined.
    examined: int
    #: Derived from the evidence rather than assigned. For a checksum this is a
    #: real probability: the chance that this many values satisfied the check by
    #: accident. For a name it is a prior, and says so.
    confidence: float
    rationale: str
    conflicts: tuple[Conflict, ...] = ()
    #: Types that also fit, in case the top one is wrong.
    alternatives: tuple[str, ...] = ()

    @property
    def is_evidence(self) -> bool:
        """Whether this can be relied on without a person looking.

        Confidence is part of the test, not decoration. Ten values of the right
        shape is not evidence of anything — a pattern-only type needs on the
        order of a hundred before its own derivation clears this bar, which is
        the correct amount of scepticism for a claim with no check digit behind
        it.
        """
        return (
            self.stage.is_deterministic
            and self.fit is not Fit.MIXED
            and self.confidence >= EVIDENCE_CONFIDENCE
        )

    @property
    def may_auto_apply(self) -> bool:
        """Whether a control may be generated from this without review.

        False for every non-deterministic stage, unconditionally. A model's
        guess about what a column means is a fine thing to show somebody and
        an unacceptable thing to start alerting on.
        """
        return (
            self.stage.is_deterministic
            and self.fit is Fit.CLEAN
            and not self.conflicts
            and self.confidence >= 0.99
        )

    @property
    def violating_fraction(self) -> float:
        return 1.0 - self.hit_rate

    def describe(self) -> str:
        return self.rationale

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_type": self.semantic_type,
            "stage": self.stage.value,
            "fit": self.fit.value,
            "hit_rate": round(self.hit_rate, 6),
            "examined": self.examined,
            "confidence": round(self.confidence, 6),
            "rationale": self.rationale,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "alternatives": list(self.alternatives),
            "is_evidence": self.is_evidence,
            "may_auto_apply": self.may_auto_apply,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class NoClassification:
    """The honest answer when nothing fits.

    A distinct type rather than ``None`` so the reason survives: "nothing was
    tried because the column is numeric" and "eleven types were tried and none
    fitted" are different situations, and the second one is worth showing a
    steward.
    """

    reason: str
    attempted: tuple[str, ...] = ()
    conflicts: tuple[Conflict, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_type": None,
            "reason": self.reason,
            "attempted": list(self.attempted),
            "conflicts": [c.to_dict() for c in self.conflicts],
        }


# ---------------------------------------------------------------------------
# The name lexicon — the weakest stage, kept deliberately small
# ---------------------------------------------------------------------------

#: Column-name fragments that suggest a type. Small on purpose: a large lexicon
#: is a large surface for confident wrong answers, and the name stage exists
#: only to speak when the content stages have said nothing at all.
NAME_HINTS: dict[str, tuple[str, ...]] = {
    "isin": ("isin", "instrument_id", "security_id"),
    "sedol": ("sedol",),
    "cusip": ("cusip",),
    "figi": ("figi", "bbg_id", "bloomberg_id"),
    "lei": ("lei", "legal_entity_identifier", "counterparty_lei", "entity_lei"),
    "iban": ("iban", "account_iban"),
    "bic": ("bic", "swift", "swift_code", "bic_code"),
    "mic": ("mic", "market_identifier", "venue_code", "exchange_mic"),
    "uti": ("uti", "trade_id", "transaction_identifier"),
    "upi": ("upi", "product_identifier"),
    "iso4217": ("currency", "ccy", "currency_code", "settlement_ccy"),
    "iso3166": ("country", "country_code", "domicile", "jurisdiction"),
    "email": ("email", "e_mail", "email_address", "contact_email"),
    "uuid": ("uuid", "guid"),
    "ulid": ("ulid",),
    "iso_date": ("date", "dt", "business_date", "value_date", "trade_date"),
    "ipv4": ("ip", "ip_address", "source_ip", "client_ip"),
    "gtin": ("gtin", "ean", "upc", "barcode"),
    "npi": ("npi", "provider_id"),
    "aba_routing": ("routing_number", "aba", "aba_routing"),
    "card_number": ("card_number", "pan", "credit_card"),
}

#: Types whose presence is a sensitivity finding rather than a quality one.
SENSITIVE_TYPES: frozenset[str] = frozenset({"card_number", "npi", "iban", "email"})

#: Physical types that rule out every text-shaped semantic type. A numeric
#: column cannot hold an ISIN, and testing one wastes a scan to produce a
#: guaranteed no.
_NUMERIC_PHYSICAL = re.compile(
    r"^(int|integer|bigint|smallint|numeric|decimal|real|double|float|money)", re.IGNORECASE
)

#: Below this, a hit rate is not a match at all — it is coincidence, and the
#: kind of coincidence a nine-character screen produces on any identifier
#: column of the right width.
MINIMUM_HIT_RATE = 0.5
#: Above this, the stray failures are the finding rather than evidence against
#: the type. Set where it is because operational data is never perfect and a
#: classifier that demands perfection classifies nothing in production.
CLEAN_HIT_RATE = 0.99
#: Fewer values than this and no content stage may speak. Six ISINs verifying
#: is a one-in-a-million coincidence; two is a Tuesday.
MINIMUM_SAMPLE = 8
#: Confidence below which a classification is a suggestion rather than a
#: finding, whatever stage produced it.
EVIDENCE_CONFIDENCE = 0.8


class SemanticAdjudicator(abc.ABC):
    """The seam for the embedding and model stages.

    An ABC because the cascade must run — completely, and to a useful answer —
    with no model available at all. An air-gapped deployment gets the first four
    stages and loses nothing that produces a verdict.
    """

    stage: Stage = Stage.MODEL

    @abc.abstractmethod
    def adjudicate(
        self, sample: ColumnSample, vocabulary: Sequence[str]
    ) -> Classification | NoClassification:
        """Choose from *vocabulary*, or decline. Never invent a type."""


# ---------------------------------------------------------------------------
# The classifier
# ---------------------------------------------------------------------------


class SemanticClassifier:
    """Runs the cascade and reports what it found, and how it knows."""

    def __init__(
        self,
        *,
        validators: ValidatorRegistry | None = None,
        codelists: CodeListRegistry | None = None,
        adjudicator: SemanticAdjudicator | None = None,
        as_of: date | None = None,
    ) -> None:
        self._validators = VALIDATORS if validators is None else validators
        self._codelists = CODELISTS if codelists is None else codelists
        self._adjudicator = adjudicator
        self._as_of = as_of

    # -- the cascade ------------------------------------------------------

    def classify(self, sample: ColumnSample) -> Classification | NoClassification:
        """The best-supported type for this column, or an explained refusal."""
        populated = sample.populated
        attempted: list[str] = []

        content = self._from_content(sample, populated, attempted)
        named = self._from_name(sample)

        if content is not None:
            return self._reconcile(content, named, sample)
        if named is not None:
            return named
        if self._adjudicator is not None:
            return self._adjudicator.adjudicate(sample, self._vocabulary())
        return NoClassification(
            reason=_refusal(len(populated), len(attempted)),
            attempted=tuple(attempted),
        )

    def candidates(self, sample: ColumnSample) -> tuple[Classification, ...]:
        """Every content-based type that fits, best first.

        Exposed because "it is one of these two" is a legitimate answer, and
        collapsing it to a single guess loses the useful part.
        """
        return tuple(self._content_candidates(sample, sample.populated, []))

    # -- stages 1-3: the content ------------------------------------------

    def _from_content(
        self, sample: ColumnSample, populated: tuple[str, ...], attempted: list[str]
    ) -> Classification | None:
        ranked = self._content_candidates(sample, populated, attempted)
        if not ranked:
            return None
        best = ranked[0]
        rest = tuple(c.semantic_type for c in ranked[1:])
        conflicts = list(best.conflicts)
        if rest and self._is_ambiguous(best, ranked[1]):
            conflicts.append(
                Conflict(
                    kind=ConflictKind.AMBIGUOUS,
                    message=(
                        f"{best.semantic_type} and {ranked[1].semantic_type} fit this column "
                        f"equally well ({best.hit_rate:.1%} against {ranked[1].hit_rate:.1%}); "
                        f"the shapes overlap and the data cannot separate them"
                    ),
                    candidates=(best.semantic_type, ranked[1].semantic_type),
                )
            )
        return dataclasses.replace(best, alternatives=rest, conflicts=tuple(conflicts))

    def _content_candidates(
        self, sample: ColumnSample, populated: tuple[str, ...], attempted: list[str]
    ) -> list[Classification]:
        if len(populated) < MINIMUM_SAMPLE:
            return []
        found: list[Classification] = []
        numeric = bool(_NUMERIC_PHYSICAL.match(sample.physical_type))
        for name in self._validators.names():
            validator = self._validators.get(name)
            # A numeric column cannot hold a letter-bearing identifier. Skipping
            # those is not an optimisation — testing them spends a pass to
            # produce a guaranteed no, and then reports "12 types attempted"
            # when only four were ever possible.
            if numeric and _requires_letters(validator):
                continue
            attempted.append(name)
            result = self._score_validator(validator, populated)
            if result is not None:
                found.append(result)
        for name in self._codelists.names():
            attempted.append(name)
            result = self._score_codelist(name, populated)
            if result is not None:
                found.append(result)
        found.sort(key=_ranking, reverse=True)
        return found

    def _score_validator(
        self, validator: SemanticValidator, populated: tuple[str, ...]
    ) -> Classification | None:
        hits = sum(1 for value in populated if validator.judge(value).valid)
        rate = hits / len(populated)
        if rate < MINIMUM_HIT_RATE:
            return None
        stage = (
            Stage.PATTERN if validator.expressibility is Expressibility.PATTERN else Stage.CHECKSUM
        )
        confidence = _confidence_from_chance(_chance_rate(validator), hits)
        conflicts: tuple[Conflict, ...] = ()
        if validator.name in SENSITIVE_TYPES:
            conflicts = (
                Conflict(
                    kind=ConflictKind.SENSITIVE_CONTENT,
                    message=(
                        f"this column holds {validator.label}s. Confirm the declared "
                        f"sensitivity and masking policy before any sample of it is "
                        f"retained in evidence or sent to a model"
                    ),
                    candidates=(validator.name,),
                ),
            )
        return Classification(
            semantic_type=validator.name,
            stage=stage,
            fit=_fit(rate),
            hit_rate=rate,
            examined=len(populated),
            confidence=confidence,
            rationale=_rationale(validator, hits, len(populated), stage, confidence),
            conflicts=conflicts,
        )

    def _score_codelist(self, name: str, populated: tuple[str, ...]) -> Classification | None:
        code_list = self._codelists.get(name)
        version = code_list.as_of(self._as_of)
        hits = sum(1 for value in populated if code_list.contains(value, when=self._as_of))
        rate = hits / len(populated)
        if rate < MINIMUM_HIT_RATE:
            return None
        # A code list's evidential weight comes from how small it is relative to
        # the space of values that could have appeared. Three-letter codes drawn
        # from 179 of 17,576 possibilities are not landing there by chance;
        # membership of a two-value list is nearly meaningless.
        distinct = len({v.upper() for v in populated})
        chance = min(1.0, len(version.codes) / max(_space(populated), len(version.codes)))
        confidence = _confidence_from_chance(chance, hits) if distinct > 1 else 0.5
        return Classification(
            semantic_type=name,
            stage=Stage.CODELIST,
            fit=_fit(rate),
            hit_rate=rate,
            examined=len(populated),
            confidence=confidence,
            rationale=(
                f"{hits:,} of {len(populated):,} values are members of {code_list.label} "
                f"as of {version.effective_from.isoformat()} ({len(version.codes)} codes), "
                f"across {distinct} distinct values"
            ),
        )

    # -- stage 4: the name -------------------------------------------------

    def _from_name(self, sample: ColumnSample) -> Classification | None:
        matched = _match_name(sample.name)
        if matched is None:
            return None
        known = matched in self._validators or matched in self._codelists
        if not known:
            return None
        return Classification(
            semantic_type=matched,
            stage=Stage.NAME,
            #: A name match cannot be CLEAN: nothing was measured. Calling it
            #: contaminated is the honest shape — the type is plausible and the
            #: data has not confirmed it.
            fit=Fit.CONTAMINATED,
            hit_rate=0.0,
            examined=0,
            confidence=0.4,
            rationale=(
                f"the column is called {sample.name!r}, which usually means {matched}. "
                f"No value in it confirmed this — the sample was too small, or the "
                f"values did not match — so this is a suggestion, not a finding"
            ),
        )

    # -- reconciliation, which is the point --------------------------------

    def _reconcile(
        self,
        content: Classification,
        named: Classification | None,
        sample: ColumnSample,
    ) -> Classification:
        """Content wins. Where the name disagrees, say so loudly.

        With one careful exception. When the name suggests a type that has a
        check digit, and the values *fail* that check digit, the refutation is
        the headline and the shape match is the footnote — not the other way
        round.

        The case that forced this: a column called ``isin`` full of
        ``GB0000000000``. Every value has an ISIN's shape and none has an ISIN's
        check digit, so the best-fitting content type is UPI, which is also
        twelve alphanumerics. Reporting "this column contains UPIs" is
        defensible and useless: what the reader needs to know is that a column
        somebody labelled ISIN is full of values that are not ISINs. Ranking by
        fit alone gets this exactly backwards, because the fabricated values fit
        the weaker type perfectly *by virtue of* failing the stronger one.
        """
        if named is None or named.semantic_type == content.semantic_type:
            return content
        refuted = self._measure(sample, named.semantic_type)
        if refuted is not None:
            rate, validator = refuted
            conflict = Conflict(
                kind=ConflictKind.NAME_CONTRADICTED,
                message=(
                    f"the column is called {sample.name!r}, but only {rate:.1%} of its "
                    f"values satisfy the {validator.authority or 'expected'} check digit "
                    f"that a {validator.label} carries. The values do have the right shape "
                    f"— which "
                    f"is why they also fit {content.semantic_type} — so this looks like "
                    f"fabricated or placeholder data rather than a mislabelled column"
                ),
                candidates=(named.semantic_type, content.semantic_type),
            )
            return dataclasses.replace(
                content,
                conflicts=(conflict, *content.conflicts),
                alternatives=(named.semantic_type, *content.alternatives),
            )
        conflict = Conflict(
            kind=ConflictKind.NAME_CONTRADICTED,
            message=(
                f"the column is called {sample.name!r}, which suggests "
                f"{named.semantic_type}, but {content.hit_rate:.1%} of its values are "
                f"{content.semantic_type}. Either the column is misnamed or it holds the "
                f"wrong data, and both are worth knowing before a control is written"
            ),
            candidates=(content.semantic_type, named.semantic_type),
        )
        return dataclasses.replace(content, conflicts=(*content.conflicts, conflict))

    def _measure(
        self, sample: ColumnSample, semantic_type: str
    ) -> tuple[float, SemanticValidator] | None:
        """The hit rate for a type with a check digit, when it is a poor one.

        Returns None when the type has no algorithmic check (so there is nothing
        to be refuted by) or when the values do satisfy it.
        """
        validator = self._validators.find(semantic_type)
        if validator is None or validator.expressibility is not Expressibility.ALGORITHM:
            return None
        populated = sample.populated
        if len(populated) < MINIMUM_SAMPLE:
            return None
        hits = sum(1 for value in populated if validator.judge(value).valid)
        rate = hits / len(populated)
        return None if rate >= MINIMUM_HIT_RATE else (rate, validator)

    def contradicts_declaration(self, sample: ColumnSample, declared_type: str) -> Conflict | None:
        """Whether the data refutes a declared semantic type.

        The check that runs when somebody *has* declared a type, and the most
        useful single thing this module does: a column declared ``lei`` in which
        3% of values verify is a discovery, and generating an LEI control for it
        would bury that discovery under an alert on 97% of rows.
        """
        validator = self._validators.find(declared_type)
        if validator is None:
            return None
        populated = sample.populated
        if len(populated) < MINIMUM_SAMPLE:
            return None
        hits = sum(1 for value in populated if validator.judge(value).valid)
        rate = hits / len(populated)
        if rate >= MINIMUM_HIT_RATE:
            return None
        return Conflict(
            kind=ConflictKind.NAME_CONTRADICTED,
            message=(
                f"{sample.dataset}.{sample.name} is declared as {validator.label} but only "
                f"{rate:.1%} of {len(populated):,} sampled values satisfy "
                f"{validator.authority or 'the standard'}. A control generated from this "
                f"declaration would fail on {1 - rate:.0%} of rows on its first run, so the "
                f"declaration is being questioned rather than enforced"
            ),
            candidates=(declared_type,),
        )

    def _vocabulary(self) -> tuple[str, ...]:
        """The closed set a model may choose from. It may not invent."""
        return tuple(sorted({*self._validators.names(), *self._codelists.names()}))

    @staticmethod
    def _is_ambiguous(best: Classification, runner_up: Classification) -> bool:
        """Whether the second-best fits well enough to be a real alternative.

        Only within a stage: a check digit beating a pattern is not a close
        call, however similar the hit rates, because one of them is evidence.
        """
        return best.stage is runner_up.stage and abs(best.hit_rate - runner_up.hit_rate) < 0.02


# ---------------------------------------------------------------------------
# Derivations
# ---------------------------------------------------------------------------

#: Probability that a value passing a validator's screen also satisfies its
#: check by chance. This is what makes confidence a derived number rather than
#: a taste: it is the false-positive rate of the algorithm itself.
_CHANCE_RATES: dict[str, float] = {
    "isin": 0.1,  # one check digit, base 10
    "sedol": 0.1,
    "cusip": 0.1,
    "figi": 0.1,
    "gtin": 0.1,
    "npi": 0.1,
    "card_number": 0.1,
    "aba_routing": 0.1,
    "lei": 1 / 97,  # two check characters, mod 97
    "iban": 1 / 97,
    "iso_date": 0.78,  # the screen admits month 00-99 and day 00-99
    "ipv4": 0.35,  # \d{1,3} admits values above 255 and leading zeros
}


def _chance_rate(validator: SemanticValidator) -> float:
    if validator.expressibility is Expressibility.PATTERN:
        # The screen was the whole test, so satisfying it is not independent
        # evidence. Confidence then rests on the hit rate alone, which is
        # weaker, and the type stays a PATTERN classification to say so.
        return 1.0
    return _CHANCE_RATES.get(validator.name, 0.1)


def _confidence_from_chance(chance: float, hits: int) -> float:
    """One minus the probability that this many values passed by accident.

    Derived rather than assigned. Four hundred values satisfying a mod-97 check
    is not a 0.9 — it is a number with four hundred zeros after the decimal
    point, and the honest rendering of that is 1.0. Computed in logs because the
    direct form underflows at about 320 values and would silently return a
    confidence of exactly 1 for a sample of 15.
    """
    if hits <= 0:
        return 0.0
    if chance >= 1.0:
        # No independent evidence. Confidence grows with the sample but is
        # capped well below certainty, because a shape is not a proof.
        return min(0.85, 0.5 + 0.35 * (1 - math.exp(-hits / 50)))
    log_probability = hits * math.log(chance)
    if log_probability < -36:  # e^-36 ≈ 2e-16, the edge of a float's resolution
        return 1.0
    return 1.0 - math.exp(log_probability)


def _refusal(populated: int, attempted: int) -> str:
    """Why nothing was concluded — which is not always the same reason.

    "Twelve types were tried and none fitted" and "nothing was tried because
    there were four values" are different situations, and only the first is
    about the data. Collapsing them sends a steward looking at a column that
    was never examined.
    """
    if populated == 0:
        return "the column has no populated values to test"
    if populated < MINIMUM_SAMPLE:
        return (
            f"only {populated} populated values were available; at least "
            f"{MINIMUM_SAMPLE} are needed before a match means anything, because "
            f"a handful of values fits almost any type by chance"
        )
    return f"{populated:,} values were tested against {attempted} types and none matched"


def _requires_letters(validator: SemanticValidator) -> bool:
    """Whether the type's screen can only be satisfied by letter-bearing text."""
    return any(character.isalpha() for character in validator.screen_pattern)


def _fit(rate: float) -> Fit:
    if rate >= CLEAN_HIT_RATE:
        return Fit.CLEAN
    if rate >= 0.8:
        return Fit.CONTAMINATED
    return Fit.MIXED


def _space(values: Iterable[str]) -> int:
    """How many values *could* have appeared, given their observed width.

    Crude on purpose. It exists to stop a two-member code list claiming the
    same evidential weight as ISO 4217, and any monotone estimate does that.
    """
    widths = {len(v) for v in values}
    width = max(widths) if widths else 1
    # Capped because the estimate only has to be monotone, and 36**20 is a
    # number no ratio needs.
    return min(int(36**width), 1_000_000_000)


def _ranking(candidate: Classification) -> tuple[int, float, float]:
    """Best first: stronger stage, then better fit, then more confident."""
    return (-candidate.stage.rank, candidate.hit_rate, candidate.confidence)


def _rationale(
    validator: SemanticValidator, hits: int, examined: int, stage: Stage, confidence: float
) -> str:
    authority = validator.authority or "the standard"
    if stage is Stage.PATTERN:
        return (
            f"{hits:,} of {examined:,} values have the shape {authority} requires. "
            f"This type has no check digit, so the shape is all the evidence there is"
        )
    odds = "effectively zero" if confidence >= 1.0 else f"about {1 - confidence:.2g}"
    return (
        f"{hits:,} of {examined:,} values satisfy the {authority} check digit. "
        f"The chance of that happening to values that are not {validator.label}s is {odds}"
    )


def _match_name(column_name: str) -> str | None:
    """The type a column name suggests, preferring the longest hint matched.

    Longest wins because ``counterparty_lei`` contains ``lei`` and also
    ``country`` contains no useful hint at all — but ``currency_code`` contains
    both ``currency`` and ``code``, and the specific one is the right answer.
    """
    normalised = re.sub(r"[^a-z0-9]+", "_", column_name.lower()).strip("_")
    parts = set(normalised.split("_"))
    best: tuple[int, str] | None = None
    for semantic_type, hints in NAME_HINTS.items():
        for hint in hints:
            matched = hint == normalised or hint in parts or ("_" in hint and hint in normalised)
            if matched and (best is None or len(hint) > best[0]):
                best = (len(hint), semantic_type)
    return best[1] if best else None
