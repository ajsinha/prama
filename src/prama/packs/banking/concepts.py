"""The banking business concept model — a starter ontology (``FR-MET-044``).

Seventeen concepts a bank already talks about: Account, Trade, Position,
Exposure, Loan. A dataset is *recognised as* one of them, and from the concept
follow the properties that ought to be present, the semantic type each one
carries, and the reconciliations it can take part in.

Three things this deliberately does not do.

**It does not guess.** Position, Balance and Exposure all carry an amount, a
currency and an as-of date. A matcher that counts overlapping properties calls
a table all three, at which point the concept model is worse than nothing: it
has produced a confident answer nobody checked. Recognition here turns on
*identifying* properties — the ones that make a table that concept rather than
a neighbouring one — and returns three states, the third of which is "I cannot
tell", not a low score.

**It does not restate the semantic types.** Every property that carries one
names a validator in :mod:`prama.classify.validators`, and the name is checked
at import. A property naming a validator that does not exist is a loud failure
here rather than a property that silently never matches.

**It does not adjudicate.** Recognition is column names against a fixed
vocabulary — deterministic, reviewable, and wrong in ways a steward can see.
What it produces is a *proposal* (``CON-007``).

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import enum
import re
from collections.abc import Iterable
from typing import Final

from prama.classify import VALIDATORS
from prama.core.errors import ValidationError

__all__ = [
    "CONCEPTS",
    "Concept",
    "Property",
    "Recognition",
    "Role",
    "Standing",
    "concept",
    "identify",
    "recognise",
]


class Role(enum.Enum):
    """What a property contributes to recognising the concept."""

    #: Without this, the table is not this concept. An Account without an
    #: account identifier is a report about accounts, not a set of accounts.
    IDENTIFYING = "identifying"
    #: Carries the concept's meaning. Their absence is a finding about the
    #: dataset — an Exposure with no counterparty cannot be aggregated for
    #: large-exposure reporting — but it does not refute the recognition.
    DEFINING = "defining"
    #: Present in most instances, absent without alarm.
    DESCRIPTIVE = "descriptive"


class Standing(enum.Enum):
    """How firmly a dataset is recognised as a concept.

    Three states, because the two-state version collapses "this is not an
    Account" and "this might be an Account and I cannot tell" into one answer,
    and they call for opposite actions: the first is a dead end, the second is
    a question for whoever owns the data.
    """

    RECOGNISED = "recognised"
    POSSIBLE = "possible"
    NOT_RECOGNISED = "not_recognised"


@dataclasses.dataclass(frozen=True, slots=True)
class Property:
    """One property of a concept.

    ``semantic_type`` names a validator rather than carrying a pattern, so the
    check that a column really holds LEIs lives in exactly one place and this
    ontology cannot drift from it.
    """

    name: str
    role: Role = Role.DESCRIPTIVE
    semantic_type: str = ""
    aliases: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if self.semantic_type and self.semantic_type not in VALIDATORS.names():
            raise ValueError(
                f"property {self.name!r} names semantic type {self.semantic_type!r}, "
                f"which no validator provides. Known: {', '.join(VALIDATORS.names())}"
            )

    @property
    def vocabulary(self) -> tuple[str, ...]:
        """Every spelling that means this property."""
        return (_normalise(self.name), *(_normalise(a) for a in self.aliases))


@dataclasses.dataclass(frozen=True, slots=True)
class Concept:
    """A business concept, and the boundary that keeps it from its neighbours."""

    name: str
    description: str
    properties: tuple[Property, ...]
    #: What this concept is *not*. Written because the concepts that get
    #: confused in practice — Position with Balance, Exposure with Position —
    #: are confused by people, not only by matchers.
    boundary: str = ""
    #: Why a regulator cares. Empty where none does.
    relevance: str = ""

    def __post_init__(self) -> None:
        if not self.identifying:
            # A concept with no identifying property matches every table with
            # the right shape, and would be reported as a confident match.
            raise ValueError(f"concept {self.name!r} has no identifying property")
        seen: set[str] = set()
        for prop in self.properties:
            for spelling in prop.vocabulary:
                if spelling in seen:
                    raise ValueError(
                        f"concept {self.name!r}: {spelling!r} spells two properties, "
                        "so a column carrying it would be counted twice"
                    )
                seen.add(spelling)

    @property
    def identifying(self) -> tuple[Property, ...]:
        return tuple(p for p in self.properties if p.role is Role.IDENTIFYING)

    @property
    def defining(self) -> tuple[Property, ...]:
        return tuple(p for p in self.properties if p.role is Role.DEFINING)

    @property
    def semantic_types(self) -> tuple[str, ...]:
        return tuple(sorted({p.semantic_type for p in self.properties if p.semantic_type}))

    def property_for(self, column: str) -> Property | None:
        """The property a column name spells, if any."""
        wanted = _normalise(column)
        for prop in self.properties:
            if wanted in prop.vocabulary:
                return prop
        return None


@dataclasses.dataclass(frozen=True, slots=True)
class Recognition:
    """What a set of columns was recognised as, and what is missing from it."""

    concept: str
    standing: Standing
    matched: tuple[tuple[str, str], ...]
    missing_identifying: tuple[str, ...]
    missing_defining: tuple[str, ...]
    unmatched_columns: tuple[str, ...]
    reason: str

    def __bool__(self) -> bool:
        return self.standing is Standing.RECOGNISED

    @property
    def expected_types(self) -> tuple[tuple[str, str], ...]:
        """Column to semantic type, for the columns that matched.

        This is the output the rest of the platform uses: the concept model's
        practical value is that recognising a table as a Trade tells you which
        column ought to validate as an ISIN.
        """
        found = concept(self.concept)
        pairs = []
        for column, name in self.matched:
            prop = next((p for p in found.properties if p.name == name), None)
            if prop is not None and prop.semantic_type:
                pairs.append((column, prop.semantic_type))
        return tuple(pairs)

    def to_dict(self) -> dict[str, object]:
        return {
            "concept": self.concept,
            "standing": self.standing.value,
            "matched": [{"column": c, "property": p} for c, p in self.matched],
            "missing_identifying": list(self.missing_identifying),
            "missing_defining": list(self.missing_defining),
            "expected_types": [{"column": c, "type": t} for c, t in self.expected_types],
            "reason": self.reason,
        }


_NOISE: Final = re.compile(r"[^a-z0-9]+")


def _normalise(name: str) -> str:
    """A column name reduced to comparable form.

    Case and separators are discarded entirely, so ``ACCT-NO`` from a copybook,
    ``account_no`` from a warehouse and ``AccountNo`` from an extract are one
    spelling. They are one spelling to every person who reads them, and a
    concept model that distinguished them would report a mainframe extract as
    unrecognisable.

    Deliberately no stemming and no edit distance beyond that.
    ``settlement_amount`` and ``settled_amount`` are the same thing to a reader
    and different things here, because the fix is an alias somebody wrote down
    — which is reviewable — rather than a threshold nobody can predict.
    """
    return _NOISE.sub("", name.strip().lower())


def recognise(name: str, columns: Iterable[str]) -> Recognition:
    """Recognise a set of column names as one concept."""
    found = concept(name)
    seen = list(columns)

    matched: list[tuple[str, str]] = []
    claimed: set[str] = set()
    for column in seen:
        prop = found.property_for(column)
        if prop is not None and prop.name not in claimed:
            matched.append((column, prop.name))
            claimed.add(prop.name)

    missing_id = tuple(p.name for p in found.identifying if p.name not in claimed)
    missing_def = tuple(p.name for p in found.defining if p.name not in claimed)
    unmatched = tuple(c for c in seen if found.property_for(c) is None)

    if missing_id:
        standing = Standing.NOT_RECOGNISED
        reason = (
            f"no column spells {' or '.join(repr(m) for m in missing_id)}, "
            f"without which this is not {found.name}"
        )
    elif not matched:
        standing = Standing.NOT_RECOGNISED
        reason = "no column matched any property"
    elif len(claimed) < 2:
        # One identifying column and nothing else. `account_id` alone appears
        # on a payment, a fee, a statement line and an audit record.
        standing = Standing.POSSIBLE
        reason = (
            "only the identifier matched, and an identifier appears on every "
            f"table that references {found.name} as well as on {found.name} itself"
        )
    elif missing_def:
        standing = Standing.POSSIBLE
        reason = f"missing {', '.join(repr(m) for m in missing_def)}"
    else:
        standing = Standing.RECOGNISED
        reason = f"every identifying and defining property of {found.name} is present"

    return Recognition(
        concept=found.name,
        standing=standing,
        matched=tuple(matched),
        missing_identifying=missing_id,
        missing_defining=missing_def,
        unmatched_columns=unmatched,
        reason=reason,
    )


def identify(columns: Iterable[str]) -> tuple[Recognition, ...]:
    """Every concept these columns could be, best first.

    Returns *all* candidates rather than a winner. Two concepts can genuinely
    both fit — a table of settled trades is a Trade and, grouped, a Position —
    and picking one silently is how a control ends up asserting a Position rule
    on trade rows.
    """
    seen = list(columns)
    results = [recognise(c.name, seen) for c in CONCEPTS]
    ranked = sorted(
        (r for r in results if r.standing is not Standing.NOT_RECOGNISED),
        key=lambda r: (r.standing is not Standing.RECOGNISED, -len(r.matched), r.concept),
    )
    return tuple(ranked)


def concept(name: str) -> Concept:
    """The concept by name, case-insensitively."""
    wanted = _normalise(name)
    for entry in CONCEPTS:
        if _normalise(entry.name) == wanted:
            return entry
    # Not KeyError: this is reached from the CLI with a name somebody typed,
    # and a traceback is not an answer to a typo.
    raise ValidationError(
        f"no such concept: {name!r}",
        remedy=f"One of: {', '.join(c.name for c in CONCEPTS)}.",
    )


def _p(
    name: str,
    role: Role = Role.DESCRIPTIVE,
    semantic_type: str = "",
    *spellings: str,
    aliases: tuple[str, ...] = (),
    note: str = "",
) -> Property:
    """Terse constructor for the table below.

    Alternative spellings can be positional or keyword; both end up in the same
    tuple. The table is long enough that the noise of `aliases=(...)` on every
    line hides the structure it is meant to show.
    """
    return Property(
        name=name,
        role=role,
        semantic_type=semantic_type,
        aliases=(*spellings, *aliases),
        note=note,
    )


_ID = Role.IDENTIFYING
_DEF = Role.DEFINING

#: The starter ontology. Extensible and overridable per tenant: a bank's own
#: vocabulary wins, and this exists so that the first day is not spent typing
#: out what every bank already agrees on.
CONCEPTS: Final[tuple[Concept, ...]] = (
    Concept(
        name="Legal Entity",
        description="A legally constituted body that can hold obligations.",
        boundary=(
            "Not a business unit. A desk or a branch has no LEI and cannot be a "
            "counterparty; consolidating on it produces exposure figures that do "
            "not tie to any reporting entity."
        ),
        relevance="GLEIF-anchored; the reporting boundary for almost every return.",
        properties=(
            _p("lei", _ID, "lei", "legal_entity_identifier", "entity_lei"),
            _p("legal_name", _DEF, "", "entity_name", "registered_name"),
            _p("jurisdiction", _DEF, "", "country_of_incorporation", "domicile"),
            _p("entity_status", role=_DEF, aliases=("status", "registration_status")),
            _p("parent_lei", semantic_type="lei", aliases=("direct_parent_lei",)),
            _p("ultimate_parent_lei", semantic_type="lei"),
            _p("nace_code", aliases=("sic_code", "sector_code", "naics_code")),
        ),
    ),
    Concept(
        name="Party",
        description="A counterparty or other named participant in a transaction.",
        boundary=(
            "A Party need not be a Legal Entity: a natural person is a Party and "
            "has no LEI. Requiring one turns every retail customer into a defect."
        ),
        relevance="AML/KYC and credit risk read the same record for different purposes.",
        properties=(
            _p("party_id", _ID, "", "counterparty_id", "cpty_id"),
            _p("party_name", _DEF, "", "counterparty_name", "cpty_name"),
            _p("party_type", _DEF, "", "counterparty_type", "entity_type"),
            _p("party_lei", semantic_type="lei", aliases=("counterparty_lei",)),
            _p("country_of_risk", aliases=("risk_country",)),
            _p("sector", aliases=("esa_sector", "nace_sector")),
            _p("credit_rating", aliases=("rating", "internal_rating")),
            _p("sanctions_status", aliases=("sanction_flag", "screening_status")),
        ),
    ),
    Concept(
        name="Customer",
        description="A party the bank has onboarded and holds a relationship with.",
        boundary=(
            "A Customer is a Party the bank chose to onboard. A counterparty on a "
            "single trade is not one, and counting it as one overstates the "
            "population every KYC-coverage metric divides by."
        ),
        properties=(
            _p("customer_id", _ID, "", "cust_id", "client_id"),
            _p("kyc_status", _DEF, "", "kyc_state", "cdd_status"),
            _p("risk_rating", _DEF, "", "customer_risk_rating", "aml_risk_rating"),
            _p("onboarding_date", aliases=("relationship_start_date", "onboarded_on")),
            _p("segment", aliases=("customer_segment", "client_segment")),
        ),
    ),
    Concept(
        name="Account",
        description="A ledger a balance is held on.",
        boundary=(
            "Not a Balance. An Account is the thing; a Balance is its value at an "
            "instant. A table with one row per account per day is Balance."
        ),
        properties=(
            _p("account_id", _ID, "", "acct_id", "account_number", "acct_no", "account_no"),
            _p("currency", _DEF, "", "account_currency", "ccy"),
            _p("account_status", _DEF, "", "status", "acct_status"),
            _p("iban", semantic_type="iban"),
            _p("product", aliases=("product_code", "account_type")),
            _p("opening_date", aliases=("opened_on", "account_open_date")),
            _p("closing_date", aliases=("closed_on", "account_close_date")),
            _p("owning_entity", aliases=("owning_lei", "booking_entity")),
            _p("branch", aliases=("branch_code", "sort_code")),
        ),
    ),
    Concept(
        name="Instrument",
        description="A financial instrument that can be held, traded or valued.",
        boundary=(
            "Identifiers are not interchangeable. One instrument has several, and "
            "joining two datasets on different ones silently drops the rows where "
            "only one is populated."
        ),
        relevance="ANNA DSB / OpenFIGI anchored; the join key for most reporting.",
        properties=(
            _p("isin", _ID, "isin", "instrument_isin", "security_isin"),
            _p("asset_class", _DEF, "", "instrument_type", "product_class"),
            _p("currency", _DEF, "", "instrument_currency", "denomination_ccy"),
            _p("cusip", semantic_type="cusip"),
            _p("sedol", semantic_type="sedol"),
            _p("figi", semantic_type="figi"),
            _p("upi", semantic_type="upi"),
            _p("cfi_code", aliases=("cfi",)),
            _p("issuer_lei", semantic_type="lei", aliases=("issuer_id",)),
            _p("maturity_date", aliases=("maturity", "redemption_date")),
            _p("coupon", aliases=("coupon_rate",)),
        ),
    ),
    Concept(
        name="Trade",
        description="An executed transaction in an instrument.",
        boundary=(
            "A Trade is an event; a Position is a state. Summing trade quantities "
            "gives a position only if every lifecycle event is present, which is "
            "the assumption that breaks."
        ),
        relevance="EMIR/MiFIR transaction reporting; UTI uniqueness within a period.",
        properties=(
            _p("trade_id", _ID, "", "trade_reference", "deal_id"),
            _p("execution_timestamp", _DEF, "", "execution_time", "trade_timestamp"),
            _p("side", _DEF, "", "buy_sell", "direction", "buy_sell_indicator"),
            _p("quantity", _DEF, "", "trade_quantity", "notional_quantity"),
            _p("price", _DEF, "", "trade_price", "execution_price"),
            _p("currency", _DEF, "", "trade_currency", "settlement_currency"),
            _p("uti", semantic_type="uti", aliases=("unique_transaction_identifier",)),
            _p("upi", semantic_type="upi"),
            _p("venue", semantic_type="mic", aliases=("mic", "trading_venue", "venue_mic")),
            _p("counterparty", aliases=("counterparty_id", "cpty")),
            _p("book", aliases=("book_id", "trading_book", "portfolio")),
            _p("isin", semantic_type="isin"),
        ),
    ),
    Concept(
        name="Position",
        description="A holding in an instrument, as at a point in time.",
        boundary=(
            "Not a Balance and not an Exposure. A Position is a holding; a Balance "
            "is cash on a ledger; an Exposure is what is at risk after netting and "
            "collateral. All three carry an amount, a currency and an as-of date, "
            "and that shared shape is why they get conflated."
        ),
        properties=(
            _p("as_of_date", _ID, "", "position_date", "as_at_date", "valuation_date"),
            _p("instrument_id", _ID, "", "isin", "instrument", "security_id"),
            _p("quantity", _DEF, "", "holding_quantity", "position_quantity"),
            _p("market_value", _DEF, "", "mv", "market_val", "position_value"),
            _p("currency", _DEF, "", "position_currency", "valuation_currency"),
            _p("account_id", aliases=("account", "acct_id")),
            _p("notional", aliases=("notional_amount",)),
            _p("book", aliases=("book_id", "portfolio")),
            _p("legal_entity", aliases=("entity", "booking_entity", "legal_entity_id")),
        ),
    ),
    Concept(
        name="Transaction",
        description="A movement of value across accounts — payment or card.",
        boundary=(
            "Not a Trade. A Trade creates an obligation; a Transaction settles "
            "one. A payments table joined into a trade population double-counts."
        ),
        properties=(
            _p("transaction_id", _ID, "", "txn_id", "transaction_reference", "end_to_end_id"),
            _p("amount", _DEF, "", "transaction_amount", "txn_amount"),
            _p("currency", _DEF, "", "transaction_currency", "txn_currency"),
            _p("value_date", _DEF, "", "settlement_date", "val_date"),
            _p("transaction_type", aliases=("txn_type", "type")),
            _p("booking_date", aliases=("posting_date", "book_date")),
            _p("debtor_agent", semantic_type="bic", aliases=("debtor_agent_bic", "sender_bic")),
            _p(
                "creditor_agent",
                semantic_type="bic",
                aliases=("creditor_agent_bic", "receiver_bic"),
            ),
        ),
    ),
    Concept(
        name="Balance",
        description="The value on an account at an instant.",
        boundary=(
            "Opening and closing balances of adjacent periods must agree; that "
            "continuity is the whole point of the concept, and a table without a "
            "balance type cannot express it."
        ),
        properties=(
            _p("account_id", _ID, "", "acct_id", "account_number"),
            _p("as_of_date", _ID, "", "balance_date", "statement_date", "as_at_date"),
            _p("balance_type", _DEF, "", "bal_type", "balance_kind"),
            _p("amount", _DEF, "", "balance", "balance_amount"),
            _p("currency", _DEF, "", "balance_currency", "ccy"),
        ),
    ),
    Concept(
        name="Exposure",
        description="What is at risk to a counterparty, after netting and collateral.",
        boundary=(
            "Gross notional is not exposure. Reporting it as such overstates "
            "large-exposure breaches; reporting net without naming the netting "
            "set understates them, and the second error is the dangerous one."
        ),
        relevance="Large exposures, CRR/CRD, FRTB and IRB inputs.",
        properties=(
            _p("counterparty_id", _ID, "", "cpty_id", "obligor_id", "party_id"),
            _p("as_of_date", _ID, "", "exposure_date", "reporting_date", "as_at_date"),
            _p("net_notional", _DEF, "", "net_exposure", "net_amount"),
            _p("netting_set", _DEF, "", "netting_set_id", "netting_agreement_id"),
            _p("gross_notional", aliases=("gross_exposure", "gross_amount")),
            _p("ead", aliases=("exposure_at_default",)),
            _p("pd", aliases=("probability_of_default",)),
            _p("lgd", aliases=("loss_given_default",)),
            _p("collateral_value", aliases=("collateral", "collateral_amount")),
        ),
    ),
    Concept(
        name="Collateral",
        description="An asset pledged against an obligation.",
        boundary=(
            "A haircut that is stored but never applied is the common defect: the "
            "valuation looks right and the eligible amount is overstated."
        ),
        properties=(
            _p(
                "collateral_id",
                _ID,
                "",
                "collateral_reference",
            ),
            _p("collateral_type", _DEF, "", "type", "asset_type"),
            _p("valuation", _DEF, "", "collateral_value", "market_value"),
            _p("haircut", _DEF, "", "haircut_pct", "valuation_haircut"),
            _p("eligibility", aliases=("eligible", "eligibility_status")),
            _p("pledged_against", aliases=("pledged_to", "netting_set_id")),
        ),
    ),
    Concept(
        name="Loan",
        description="A credit facility and its drawn position.",
        boundary=(
            "Commitment and drawn are different numbers and both are called "
            "'amount' somewhere upstream. Undrawn commitment carries capital, so "
            "conflating them changes the RWA."
        ),
        relevance="AnaCredit, FINREP, IFRS 9 staging.",
        properties=(
            _p("contract_id", _ID, "", "facility_id", "loan_id", "loan_reference"),
            _p("commitment", _DEF, "", "commitment_amount", "facility_amount"),
            _p("drawn", _DEF, "", "drawn_amount", "outstanding_amount", "utilised_amount"),
            _p("currency", _DEF, "", "loan_currency", "facility_currency"),
            _p("rate_type", aliases=("interest_rate_type",)),
            _p("ifrs9_stage", aliases=("stage", "impairment_stage")),
            _p("arrears_status", aliases=("days_past_due", "arrears")),
            _p("forbearance", aliases=("forbearance_flag", "forborne")),
        ),
    ),
    Concept(
        name="Product",
        description="What the bank sells, and how a regulator classifies it.",
        properties=(
            _p("product_code", _ID, "", "product_id"),
            _p("product_name", _DEF, "", "product_description"),
            _p("product_hierarchy", aliases=("product_family", "product_group")),
            _p("regulatory_classification", aliases=("reg_class", "regulatory_product_type")),
        ),
    ),
    Concept(
        name="Book",
        description="An organisational unit that positions are booked to.",
        boundary=(
            "Trading book against banking book is a regulatory boundary, not a "
            "reporting convenience. A position in the wrong one is a capital "
            "misstatement, and the field is usually free text."
        ),
        relevance="The trading/banking book boundary drives the capital treatment.",
        properties=(
            _p("book_id", _ID, "", "book", "book_code", "desk_id"),
            _p("book_type", _DEF, "", "trading_banking_book", "regulatory_book"),
            _p("desk", aliases=("desk_name", "trading_desk")),
            _p("cost_centre", aliases=("cost_center", "cc_code")),
            _p("legal_entity", aliases=("entity", "owning_entity")),
        ),
    ),
    Concept(
        name="Journal Entry",
        description="A posting to the general ledger.",
        boundary=(
            "The sub-ledger and the GL are two records of one fact, and the "
            "reconciliation between them is the concept's reason to exist."
        ),
        properties=(
            _p("gl_account", _ID, "", "gl_account_code", "account_code", "ledger_account"),
            _p("posting_date", _ID, "", "post_date", "gl_date", "accounting_date"),
            _p("amount", _DEF, "", "posting_amount", "gl_amount"),
            _p("currency", _DEF, "", "posting_currency", "gl_currency"),
            _p("cost_centre", aliases=("cost_center",)),
            _p("journal_id", aliases=("journal_reference", "voucher_id")),
        ),
    ),
    Concept(
        name="Regulatory Return",
        description="A submission to a supervisor. A dataset can *be* a return.",
        boundary=(
            "Submitted is not accepted. A return whose status stops at 'submitted' "
            "has told nobody whether the supervisor took it."
        ),
        relevance="The artefact the whole estate exists to produce correctly.",
        properties=(
            _p("return_id", _ID, "", "return_code", "submission_id"),
            _p("reference_date", _ID, "", "reporting_date", "as_of_date", "period_end"),
            _p("reporting_entity", _DEF, "", "reporting_lei", "submitting_entity"),
            _p("submission_status", _DEF, "", "status", "return_status"),
            _p("schedule", aliases=("template", "return_schedule", "form")),
        ),
    ),
    Concept(
        name="Rate",
        description="A reference or FX rate used to normalise for comparison.",
        boundary=(
            "A rate without its source and as-of is not reproducible, and a "
            "reconciliation that used it cannot be re-run to the same answer."
        ),
        properties=(
            _p("rate", _ID, "", "rate_value", "fx_rate", "exchange_rate"),
            _p("as_of_date", _ID, "", "rate_date", "quote_date", "valuation_date"),
            _p("currency_pair", _DEF, "", "ccy_pair", "pair"),
            _p("source", _DEF, "", "rate_source", "provider"),
            _p("rate_type", aliases=("quote_type", "tenor")),
        ),
    ),
)
