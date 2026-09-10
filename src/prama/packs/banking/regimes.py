"""Reporting regimes beyond BCBS 239.

The catalogue in :mod:`prama.packs.banking.obligations` is the anchor. This is
the breadth around it: transaction reporting, granular credit, large exposures,
financial crime, and the two horizontal regimes — financial-reporting control
and data protection — that reach every dataset in the estate.

**On citations.** Every entry is cited at the level of an article or a section,
because that is the level at which the reference is stable and checkable. None
of them is cited at paragraph level, and none is marked ``confirmed``: nobody
has yet checked these against the published texts. That is recorded on the
:class:`~prama.packs.banking.regulatory.Citation` itself rather than in a
footnote, because an examiner's next question after any finding is where it
comes from, and a wrong article number costs more than an absent one. A bank's
compliance function confirms them; the flag is there so the work is visible and
so a coverage report can say which obligations rest on unverified references.

**On scope.** These are the obligations a *data quality control* can discharge.
Transaction reporting has hundreds of validation rules; what is here is the
handful whose failure is a data defect rather than a business decision. The
rest are supported and not discharged, and :data:`SUPPORTED_NOT_DISCHARGED`
in the anchor catalogue says so for BCBS 239. The same restraint applies here:
an obligation absent from this module is absent because no control discharges
it, not because it was overlooked.

Placeholders are **concept properties** (see
:mod:`prama.packs.banking.concepts`), so binding a template to an estate is the
same act as recognising its tables.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Final

from prama.packs.banking.regulatory import (
    Citation,
    Obligation,
    RelationshipRequirement,
    Template,
)
from prama.semantic.relationships import RelationshipKind

__all__ = [
    "AML",
    "ANACREDIT",
    "EMIR",
    "GDPR",
    "LARGE_EXPOSURES",
    "MIFIR",
    "REGIME_OBLIGATIONS",
    "REGIME_SCOPE",
    "SOX",
]

MIFIR = "MiFIR transaction reporting"
EMIR = "EMIR REFIT"
ANACREDIT = "AnaCredit"
LARGE_EXPOSURES = "Large exposures (CRR)"
AML = "AML customer due diligence"
SOX = "SOX ICFR"
GDPR = "GDPR"

#: What each regime's entries here cover, and what they leave alone. Printed by
#: ``prama pack claims``: a regime named in a catalogue reads as a regime
#: handled, and for every one of these that is false.
REGIME_SCOPE: Final[dict[str, str]] = {
    MIFIR: (
        "Identifier validity and T+1 completeness against the trade store. Not "
        "the RTS 22 field-level rule set, and not over-reporting detection, "
        "which needs the ARM's own acknowledgements."
    ),
    EMIR: (
        "UTI presence and uniqueness within a reporting period, and notional "
        "sign against side. Not dual-sided pairing, which needs the "
        "counterparty's submission, and not the trade repository's rejections."
    ),
    ANACREDIT: (
        "Counterparty reference-data completeness and the instrument-to-"
        "counterparty link. Not the ECB's full validation-check set, and not "
        "the reporting thresholds, which are a policy decision per bank."
    ),
    LARGE_EXPOSURES: (
        "Completeness of the inputs an exposure figure is built from. Whether "
        "the resulting figure breaches a limit is the risk function's "
        "calculation, not a data quality control."
    ),
    AML: (
        "The quality of screening and monitoring *inputs*: party completeness, "
        "identifier validity, feed continuity. Not whether an alert should "
        "have been raised, which is an adjudication (CON-007)."
    ),
    SOX: (
        "Sub-ledger to general ledger reconciliation and its evidence. Not the "
        "assessment of internal control, which is management's."
    ),
    GDPR: (
        "Accuracy and retention as testable properties of data, plus the "
        "records that show a control ran. Not lawfulness of processing, and "
        "not consent."
    ),
}


def _c(document: str, clause: str, authority: str, url: str = "") -> Citation:
    """A citation, unconfirmed by construction.

    There is no shortcut here that marks one confirmed, because confirmation
    means a person read the published text and that cannot be done by a
    default argument.
    """
    return Citation(document=document, clause=clause, authority=authority, url=url)


REGIME_OBLIGATIONS: Final[tuple[Obligation, ...]] = (
    # -- MiFIR transaction reporting ---------------------------------------
    Obligation(
        identity="MIFIR-ART26-IDENTIFIERS",
        regime=MIFIR,
        principle="P3",
        citation=_c(
            "Regulation (EU) No 600/2014",
            "Article 26",
            "European Parliament and Council",
        ),
        objective=(
            "Every reported transaction carries identifiers that resolve: an "
            "instrument, a venue, and a legal entity. A report whose LEI has "
            "lapsed is rejected, and a rejected report is an unreported "
            "transaction — the regulator's view is that it never arrived."
        ),
        templates=(
            Template(
                identity="mifir-isin-valid",
                pql=(
                    "CHECK {dataset}.{isin} IS VALID isin "
                    "SEVERITY critical DIMENSION validity "
                    "BECAUSE 'a transaction report is rejected on an invalid ISIN'"
                ),
                requires=("dataset", "isin"),
                dimension="validity",
            ),
            Template(
                identity="mifir-lei-valid",
                pql=(
                    "CHECK {dataset}.{lei} IS VALID lei "
                    "SEVERITY critical DIMENSION validity "
                    "BECAUSE 'the reporting entity and buyer/seller LEIs must resolve'"
                ),
                requires=("dataset", "lei"),
                dimension="validity",
            ),
            Template(
                identity="mifir-venue-valid",
                pql=(
                    "CHECK {dataset}.{venue} IS VALID mic "
                    "SEVERITY major DIMENSION validity "
                    "BECAUSE 'the execution venue must be a registered MIC'"
                ),
                requires=("dataset", "venue"),
                dimension="validity",
            ),
        ),
    ),
    Obligation(
        identity="MIFIR-ART26-T1-COMPLETE",
        regime=MIFIR,
        principle="P5",
        citation=_c(
            "Regulation (EU) No 600/2014",
            "Article 26(1), reporting no later than the close of the following working day",
            "European Parliament and Council",
        ),
        objective=(
            "Every reportable transaction executed on a business day appears in "
            "the next day's submission. Under-reporting is invisible from the "
            "report alone — it can only be found by counting against the trade "
            "store, which is why this is a reconciliation and not a field check."
        ),
        templates=(
            Template(
                identity="mifir-t1-every-trade-reported",
                pql=(
                    "CHECK {trade_store}.{trade_id} REFERENCES {dataset}.{report_trade_id} "
                    "SEVERITY critical DIMENSION completeness "
                    "BECAUSE 'a trade absent from the report is an unreported transaction'"
                ),
                requires=("trade_store", "trade_id", "dataset", "report_trade_id"),
                dimension="completeness",
                note=(
                    "The direction is the control. Checking that every reported "
                    "trade exists in the store finds over-reporting and cannot "
                    "find under-reporting, which is the breach — so the check "
                    "runs on the trade store and points at the report."
                ),
            ),
            Template(
                identity="mifir-t1-report-arrives",
                pql=(
                    "CHECK {dataset} IS FRESH WITHIN {window} "
                    "SEVERITY critical DIMENSION timeliness "
                    "BECAUSE 'reporting is due by close of the following working day'"
                ),
                requires=("dataset", "window"),
                dimension="timeliness",
            ),
        ),
        not_discharged=(
            "Over-reporting — transactions reported that were not reportable — "
            "needs the ARM's acknowledgements, which are not a dataset in the "
            "estate."
        ),
    ),
    # -- EMIR REFIT --------------------------------------------------------
    Obligation(
        identity="EMIR-ART9-UTI",
        regime=EMIR,
        principle="P3",
        citation=_c(
            "Regulation (EU) No 648/2012",
            "Article 9",
            "European Parliament and Council",
        ),
        objective=(
            "Every derivative report carries a unique transaction identifier, "
            "and it is unique within the reporting period. A UTI reused across "
            "two trades pairs one of them with the wrong counterparty report, "
            "and the mismatch surfaces as the other side's problem."
        ),
        templates=(
            Template(
                identity="emir-uti-valid",
                pql=(
                    "CHECK {dataset}.{uti} IS VALID uti "
                    "SEVERITY critical DIMENSION validity "
                    "BECAUSE 'the UTI is the key both sides pair on'"
                ),
                requires=("dataset", "uti"),
                dimension="validity",
            ),
            Template(
                identity="emir-uti-unique",
                pql=(
                    "CHECK {dataset}.{uti} IS UNIQUE "
                    "SEVERITY critical DIMENSION uniqueness "
                    "BECAUSE 'a reused UTI pairs a trade with the wrong report'"
                ),
                requires=("dataset", "uti"),
                dimension="uniqueness",
            ),
        ),
    ),
    Obligation(
        identity="EMIR-NOTIONAL-SIGN",
        regime=EMIR,
        principle="P3",
        citation=_c(
            "Commission Delegated Regulation (EU) 2022/1855",
            "reporting technical standards",
            "European Commission",
        ),
        objective=(
            "The sign of a notional agrees with the reported side. A buy "
            "carrying a negative notional nets against the position it should "
            "add to, and the total remains plausible."
        ),
        templates=(
            Template(
                identity="emir-notional-sign",
                pql=(
                    "CHECK {dataset} SATISFIES NOTIONAL_SIGN_MATCHES_SIDE("
                    "{notional}, {side}) "
                    "SEVERITY critical DIMENSION consistency "
                    "BECAUSE 'a wrong-signed notional nets against what it should add to'"
                ),
                requires=("dataset", "notional", "side"),
                dimension="consistency",
            ),
        ),
    ),
    # -- AnaCredit ---------------------------------------------------------
    Obligation(
        identity="ANACREDIT-COUNTERPARTY-REFERENCE",
        regime=ANACREDIT,
        principle="P4",
        citation=_c(
            "Regulation (EU) 2016/867 (ECB/2016/13)",
            "Annex I, counterparty reference data",
            "European Central Bank",
        ),
        objective=(
            "Every counterparty on a reported instrument has its reference data "
            "present. AnaCredit is a granular return: a missing counterparty "
            "attribute does not degrade an aggregate, it rejects the record, "
            "and the loan disappears from the submission entirely."
        ),
        templates=(
            Template(
                identity="anacredit-counterparty-lei",
                pql=(
                    "CHECK {dataset}.{lei} IS VALID lei "
                    "SEVERITY critical DIMENSION validity "
                    "BECAUSE 'a legal-entity counterparty is identified by its LEI'"
                ),
                requires=("dataset", "lei"),
                dimension="validity",
                note=(
                    "Only for counterparties that are legal entities. A natural "
                    "person has no LEI, and applying this to a retail book turns "
                    "every borrower into a defect."
                ),
            ),
            Template(
                identity="anacredit-counterparty-complete",
                pql=(
                    "CHECK {dataset}.{counterparty_id} IS NOT NULL "
                    "SEVERITY critical DIMENSION completeness "
                    "BECAUSE 'an instrument with no counterparty is rejected outright'"
                ),
                requires=("dataset", "counterparty_id"),
                dimension="completeness",
            ),
        ),
    ),
    Obligation(
        identity="ANACREDIT-INSTRUMENT-LINK",
        regime=ANACREDIT,
        principle="P4",
        citation=_c(
            "Regulation (EU) 2016/867 (ECB/2016/13)",
            "Annex I, instrument-counterparty linkage",
            "European Central Bank",
        ),
        objective=(
            "Every instrument links to a counterparty that exists in the "
            "counterparty dataset. The two datasets are submitted together and "
            "validated against each other, so a link to an absent counterparty "
            "fails at the ECB rather than at the bank."
        ),
        templates=(
            Template(
                identity="anacredit-link-resolves",
                pql=(
                    "CHECK {dataset}.{counterparty_id} REFERENCES "
                    "{counterparty_dataset}.{counterparty_key} "
                    "SEVERITY critical DIMENSION consistency "
                    "BECAUSE 'the two datasets are validated against each other'"
                ),
                requires=(
                    "dataset",
                    "counterparty_id",
                    "counterparty_dataset",
                    "counterparty_key",
                ),
                dimension="consistency",
            ),
        ),
    ),
    # -- Large exposures ---------------------------------------------------
    Obligation(
        identity="CRR-ART394-EXPOSURE-COMPLETE",
        regime=LARGE_EXPOSURES,
        principle="P4",
        citation=_c(
            "Regulation (EU) No 575/2013",
            "Article 394",
            "European Parliament and Council",
        ),
        objective=(
            "Every exposure to a counterparty is present before the aggregate is "
            "taken. A large-exposure figure computed over an incomplete "
            "population understates, and understatement is the direction that "
            "hides a breach rather than raising a false one."
        ),
        relationships=(
            RelationshipRequirement(
                kind=RelationshipKind.TOGETHER_COMPLETE,
                between="{sources} together cover {dataset}",
                note=(
                    "Whether a set of feeds covers the book is a statement about "
                    "the set, not a check on any one of them. Declared, so the "
                    "generator derives the controls; written as PQL it would be "
                    "syntax the language does not have."
                ),
            ),
        ),
        templates=(
            Template(
                identity="crr-netting-set-present",
                pql=(
                    "CHECK {dataset}.{netting_set} IS NOT NULL "
                    "SEVERITY critical DIMENSION completeness "
                    "BECAUSE 'a net figure without its netting set cannot be defended'"
                ),
                requires=("dataset", "netting_set"),
                dimension="completeness",
            ),
        ),
    ),
    # -- AML ---------------------------------------------------------------
    Obligation(
        identity="FATF-R10-PARTY-COMPLETE",
        regime=AML,
        principle="P4",
        citation=_c(
            "FATF Recommendations",
            "Recommendation 10, customer due diligence",
            "Financial Action Task Force",
        ),
        objective=(
            "The attributes screening and monitoring depend on are present for "
            "every customer. A sanctions screen against a null name returns no "
            "hit, which is indistinguishable in the output from a clean result."
        ),
        templates=(
            Template(
                identity="aml-screening-inputs",
                pql=(
                    "CHECK {dataset}.{party_name} IS NOT NULL "
                    "SEVERITY critical DIMENSION completeness "
                    "BECAUSE 'a screen against a null name returns a clean result'"
                ),
                requires=("dataset", "party_name"),
                dimension="completeness",
            ),
            Template(
                identity="aml-feed-continuity",
                pql=(
                    "CHECK {dataset} IS FRESH WITHIN {window} "
                    "SEVERITY critical DIMENSION timeliness "
                    "BECAUSE 'a monitoring feed that did not arrive raised no alerts'"
                ),
                requires=("dataset", "window"),
                dimension="timeliness",
                note=(
                    "The failure mode this exists for is silent: a feed that "
                    "stops produces zero alerts, which looks like a quiet day."
                ),
            ),
        ),
    ),
    # -- SOX ---------------------------------------------------------------
    Obligation(
        identity="SOX-404-SUBLEDGER-GL",
        regime=SOX,
        principle="P3",
        citation=_c(
            "Sarbanes-Oxley Act of 2002",
            "Section 404",
            "United States Congress",
        ),
        objective=(
            "The sub-ledger agrees with the general ledger, and the agreement is "
            "evidenced rather than asserted. This is the reconciliation an "
            "external auditor asks to see performed, and 'it reconciles' without "
            "a record of the run is not evidence."
        ),
        relationships=(
            RelationshipRequirement(
                kind=RelationshipKind.RECONCILES_WITH,
                between="{dataset} reconciles with {gl} on {gl_account}, {posting_date}",
                note=(
                    "Keyed and toleranced by the reconciliation template "
                    "`subledger-to-gl`. An aggregate agreement between two "
                    "populations is a relationship, not a predicate on a row."
                ),
            ),
        ),
        templates=(
            Template(
                identity="sox-posting-complete",
                pql=(
                    "CHECK {dataset}.{gl_account} IS NOT NULL "
                    "SEVERITY critical DIMENSION completeness "
                    "BECAUSE 'a posting with no GL account cannot be reconciled at all'"
                ),
                requires=("dataset", "gl_account"),
                dimension="completeness",
                cadence="monthly",
            ),
        ),
    ),
    # -- GDPR --------------------------------------------------------------
    Obligation(
        identity="GDPR-ART5-ACCURACY",
        regime=GDPR,
        principle="P3",
        citation=_c(
            "Regulation (EU) 2016/679",
            "Article 5(1)(d), accuracy",
            "European Parliament and Council",
        ),
        objective=(
            "Personal data is accurate and kept up to date. The testable part is "
            "narrow — contact details that fail their own format, records not "
            "touched since a stale date — and claiming the principle in full "
            "would be claiming to know the world outside the database."
        ),
        templates=(
            Template(
                identity="gdpr-contact-well-formed",
                pql=(
                    "CHECK {dataset}.{email} IS VALID email "
                    "SEVERITY major DIMENSION validity "
                    "BECAUSE 'a malformed contact detail cannot be accurate'"
                ),
                requires=("dataset", "email"),
                dimension="validity",
                cadence="weekly",
                note=(
                    "Well-formed is not accurate. This finds the subset that is "
                    "provably wrong; it says nothing about the rest."
                ),
            ),
        ),
    ),
    Obligation(
        identity="GDPR-ART5-RETENTION",
        regime=GDPR,
        principle="P3",
        citation=_c(
            "Regulation (EU) 2016/679",
            "Article 5(1)(e), storage limitation",
            "European Parliament and Council",
        ),
        objective=(
            "Personal data is not held past its retention period. The control is "
            "a floor on age, and it is the rare control whose failure means "
            "there is *too much* data rather than too little."
        ),
        templates=(
            Template(
                identity="gdpr-retention-floor",
                pql=(
                    "CHECK {dataset}.{created_date} >= "
                    "DATE_SUB(CURRENT_DATE, {retention_days}) "
                    "SEVERITY critical DIMENSION validity "
                    "BECAUSE 'personal data held past its retention period is a breach'"
                ),
                requires=("dataset", "created_date", "retention_days"),
                dimension="validity",
                cadence="monthly",
            ),
        ),
    ),
)
