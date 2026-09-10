<img src="assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

> ***pramā*** (Sanskrit **प्रमा**) — *valid knowledge: a cognition that is both true and arrived at
> by a reliable means*. Its companion ***pramāṇa*** (प्रमाण) is *the instrument by which valid
> knowledge is obtained*. Prama is that instrument for an organisation's data — it does not decide
> what is true, it is how a belief about data becomes **justified**.
>
> **Declare it. Prove it. Trust it.**


---
# 12 — Banking & Capital Markets Domain Pack

**Pack:** `prama/banking` · **Ships at:** GA · **Requirement:** `FR-PCK-002`

A Domain Pack is a versioned, signed bundle of: business concepts, semantic types and validators,
message-format parsers, rule libraries, code lists, dimension weightings, scorecard templates, and
a regulatory control catalogue with citations. Banking is Pack #1 and the reference implementation
of the mechanism by which Prama becomes industry-general ([02 §4](02-gap-analysis-and-positioning.md#4-target-segments-and-entry-sequence)).

---

## 1. Why banking first

- **The pain is priced.** UK FCA fines: ~£95M for MiFID transaction-reporting failures and ~£34.5M
  for EMIR; Goldman Sachs >£34M for 220M+ reporting errors over 9.5 years; UBS >£27M for 135M+
  errors. Data quality here is not a hygiene budget, it is a loss-avoidance budget.
- **The obligation is explicit.** BCBS 239 requires demonstrable risk-data aggregation capability;
  principles 3–6 (accuracy & integrity, completeness, timeliness, adaptability) are literally data
  quality requirements, and principles 12–14 make them supervisable.
- **The status quo is spreadsheets.** Most banks run control attestation in Excel and GRC tools
  disconnected from any execution engine. The gap between "we have an observability tool" and "we
  can evidence our controls" is exactly our wedge (GAP-5).
- **The estate is maximally heterogeneous.** Mainframes, vendor packages, file feeds, message
  standards, and modern lakehouses coexist. Breadth of connectivity (`FR-CON`) is worth more here
  than anywhere else.
- **Cross-system truth is the core problem.** Front-to-back reconciliation is a first-class control
  objective that no DQ vendor addresses (GAP-6).

---

## 2. Business concept model

Shipped as a starter ontology, extensible and overridable per tenant (`FR-MET-044`).

| Concept | Key properties | Notes |
|---|---|---|
| **Legal Entity** | LEI, legal name, jurisdiction, entity status, parent LEI, ultimate parent LEI, NACE/SIC | GLEIF-anchored; relationship hierarchy |
| **Party / Counterparty** | party ID, LEI, name, type, country of risk, sector (ESA/NACE), credit rating, sanctions status | AML/KYC and credit-risk overlap |
| **Customer** | customer ID, KYC status, risk rating, onboarding date, segment | |
| **Account** | account ID, IBAN, product, currency, status, opening/closing date, owning entity, branch | |
| **Instrument** | ISIN, CUSIP, SEDOL, FIGI, UPI, CFI, asset class, issuer LEI, currency, maturity, coupon | ANNA DSB / OpenFIGI anchored |
| **Trade** | trade ID, UTI/UPI, execution timestamp, venue (MIC), side, quantity, price, currency, counterparty, book | |
| **Position** | account, instrument, quantity, market value, notional, as-of date, book, legal entity | |
| **Transaction** | transaction ID, type, amount, currency, value date, booking date, debtor/creditor agents | Payments + card |
| **Balance** | account, balance type, amount, currency, as-of, opening/closing | Statement continuity |
| **Exposure** | counterparty, gross/net notional, EAD, PD, LGD, collateral, netting set, as-of | Credit + FRTB |
| **Collateral** | collateral ID, type, valuation, haircut, eligibility, pledged-against | |
| **Loan / Credit Facility** | contract ID, commitment, drawn, rate type, IFRS 9 stage, arrears status, forbearance | AnaCredit/FINREP |
| **Product** | product code, hierarchy, regulatory classification | |
| **Book / Desk / Cost Centre** | organisational hierarchy | Trading vs. banking book — a regulatory boundary |
| **Journal Entry / GL Account** | account code, cost centre, amount, currency, posting date | Sub-ledger↔GL recon |
| **Regulatory Return** | return ID, reporting entity, reference date, schedule, submission status | Datasets can *be* returns |
| **Reference Rate / FX Rate** | rate, currency pair, source, as-of | Normalisation for reconciliation |

---

## 3. Semantic types and validators

Deterministic, checksum-bearing types resolve without ML and anchor the whole inference cascade
([08 §2](08-ai-ml-capabilities.md#2-semantic-type-inference)):

| Type | Structure | Validation |
|---|---|---|
| **LEI** | 20 alphanumeric, ISO 17442 | Structure + **mod-97-10** check digits + GLEIF existence + status (ISSUED/LAPSED/RETIRED) + as-of validity |
| **ISIN** | 12 chars, ISO 6166 | Country prefix (ISO 3166) + **modified Luhn** check digit + ANNA/vendor master existence |
| **CUSIP** | 9 chars | Check digit + issuer/issue structure |
| **SEDOL** | 7 chars | Weighted check digit + no vowels rule |
| **FIGI** | 12 chars | Structure + check digit + OpenFIGI existence |
| **UPI / UTI** | ISO 23897 / DSB | Format + registry existence + uniqueness within reporting scope |
| **CFI** | 6 chars, ISO 10962 | Category/group/attribute validity |
| **BIC** | 8 or 11, ISO 9362 | Structure + country + SWIFT directory existence + connectivity status |
| **IBAN** | ISO 13616 | **mod-97** check + country-specific length and BBAN structure + national bank-code existence |
| **MIC** | 4 chars, ISO 10383 | Registry existence + operating/segment MIC relationship |
| **Currency** | ISO 4217 | Code list + active status + minor-unit consistency with the amount's scale |
| **Country** | ISO 3166-1 α2/α3 | Code list + sanctioned/embargoed flagging |
| **NACE / SIC / NAICS** | Sector codes | Hierarchy validity |
| **Sort code / routing number** | GB / US ABA | Structure + ABA check digit + directory |
| **PAN** | Card number | **Luhn** + BIN range + automatic sensitivity classification |
| **Account number (national)** | Per-country | Country-specific structure and check digits |

**Cross-field validators** (the checks that catch real defects that single-field validation misses):
IBAN country ↔ BIC country consistency; ISIN country ↔ issuer LEI jurisdiction plausibility;
currency ↔ amount scale (JPY has 0 minor units); MIC ↔ instrument listing; settlement date ↔
trade date + market convention on the correct settlement calendar; UTI uniqueness across a
reporting period; notional sign ↔ side.

---

## 4. Message-format support

Detail in [09 §12](09-connectivity-and-formats.md#12-financial-message-standards-domain-pack-1).
The pack ships parsers *and* rule libraries so PQL can assert on **named business fields**:

```pql
IMPORT pack 'prama/banking@2.1.0' AS bank

CHECK pacs008.creditor_agent_bic IS VALID bic
CHECK pacs008 SATISFIES bank.iban_bic_country_consistency(creditor_account_iban, creditor_agent_bic)
CHECK pacs008.interbank_settlement_date IS BUSINESS DAY CALENDAR 'TARGET2'
CHECK pacs008 CONFORMS TO bank.cbpr_plus_usage_guideline
CHECK mt940 SATISFIES bank.statement_continuity(opening_balance, entries, closing_balance)
CHECK fix_execution_report SATISFIES bank.fix_required_fields(msg_type)
CHECK emir_trade SATISFIES bank.esma_validation_rules AS OF reporting_date
```

Covered: ISO 20022/MX (pacs, pain, camt, sese, semt, setr, acmt, auth, remt, colr, reda) with CBPR+,
HVPS+ and market-practice guidelines; SWIFT MT (all categories incl. MT103, 202COV, 300, 320,
540–548, 900/910, 940/942/950) with network-validated rules; FIX/FIXML 4.2–5.0SP2 and FIX Orchestra;
FpML 5.x; FINOS/ISDA **CDM** with its prescribed validation logic and Rosetta synonym mapping;
XBRL/iXBRL (FINREP, COREP, ESEF) with calculation and dimensional consistency; SDMX; ISO 8583;
NACHA/ACH, SEPA, BACS, CHAPS, Fedwire, CHIPS; BAI2/MT940/camt.053.

### 4.1 What ships today

The list above is the design target. What is implemented in
`src/prama/packs/banking/` at this version is narrower, and a reader who takes
the target for the state of the code will size a migration wrongly:

| Format | Module | What it reads | What it deliberately does not do |
|---|---|---|---|
| SWIFT MT | `swift.py` | MT103, MT940 block/tag structure, balances, entries | Network-validated rules; the other categories |
| ISO 20022 | `iso20022.py` | pacs.008, camt.053, matched on local name | CBPR+/HVPS+ usage guidelines; XSD validation |
| COBOL | `cobol.py` | Copybooks, COMP-3, EBCDIC codepages, `REDEFINES` | `OCCURS DEPENDING ON` |
| FIX | `fix.py` | 4.2–4.4 tag=value, repeating groups, body length and checksum | FIXML; Orchestra; session-layer sequencing |
| ISO 8583 | `iso8583.py` | MTI, primary and secondary bitmaps, LLVAR/LLLVAR, PAN masked by default | Network dialects (Visa/Mastercard field meanings differ) |
| FpML | `fpml.py` | 5.x swap streams: payer, receiver, notional, currency, rate or index | Product-specific validation rules; CDM |

Every parser returns *defects* rather than raising, because one bad message in
a file of four thousand must not stop the rest being checked — that turns a
data defect into an outage, and the outage is what gets the control disabled.
`prama pack parse <file>` runs any of them from a terminal without a database.

Not started: FIXML, CDM, XBRL, SDMX, NACHA/SEPA/BACS/CHAPS/Fedwire/CHIPS, BAI2.

**Note on the ISO 20022 transition.** Swift completed migration of cross-border interbank payment
instructions to ISO 20022 in November 2025. Banks now run MT and MX in parallel across their
estates, with translation layers between them — a high-yield source of quality defects, and a
concrete beachhead use case: **MT↔MX translation-fidelity controls** expressed as
`RECONCILES_WITH` relationships between the two representations of the same payment.

---

## 5. Regulatory control catalogue

Each obligation ships as a control template set with citations, so a control's provenance is
answerable ("show me where this comes from") — precisely what an auditor asks.

### 5.1 BCBS 239 / RDARR — the anchor

| Principle | Prama capability |
|---|---|
| P1 Governance | Ownership model, approval workflows, SoD, attestation, audit trail |
| P2 Data architecture & IT infrastructure | Estate map, semantic layer, lineage + business journeys, connector inventory |
| **P3 Accuracy & integrity** | Declarative controls + reconciliation + evidence with deterministic replay |
| **P4 Completeness** | Population-completeness controls, `TOGETHER_COMPLETE` relationships, coverage reporting per CDE |
| **P5 Timeliness** | Arrival/freshness controls with settlement calendars, journey SLA, stress-period reporting |
| **P6 Adaptability** | Ad-hoc control authoring in minutes (chat/no-code) and on-demand re-examination |
| P7–P11 Reporting | Scorecards, attestation, distribution, retention |
| P12–P14 Supervisory review | Auditor role, evidence export, replay, remediation tracking |

**The deliverable:** an *RDARR control attestation pack* — every CDE, its controls, their outcomes
for the period, exceptions with justifications, and sign-off — generated, not assembled by hand.

### 5.2 Regulatory reporting

| Regime | Jurisdiction | Prama controls |
|---|---|---|
| **AnaCredit** | ECB/EU | Instruction-derived validation rules (v4.6+), counterparty reference-data consistency, LEI validity, instrument-counterparty linkage, thresholds, cross-dataset completeness |
| **FINREP / COREP** | EBA | XBRL taxonomy conformance, calculation and dimensional consistency, GL↔FINREP reconciliation, period-over-period plausibility |
| **FR Y-9C / Y-14A/Q/M, FFIEC 031/041, 2052a (LCR)** | US Fed/FFIEC | Schedule completeness, edit checks, roll-forward, sub-ledger↔return reconciliation, submission gates |
| **MiFIR / MiFID II transaction reporting** | ESMA/FCA | Field-level validation, ISIN/LEI/MIC validity, timestamp accuracy, over/under-reporting detection, T+1 completeness vs. the trade store |
| **EMIR / EMIR REFIT, SFTR, CFTC Part 43/45, ASIC/MAS/HKMA** | Global derivatives | UTI/UPI validity and uniqueness, dual-sided pairing/matching, ISO 20022 XML conformance, reconciliation with the trade repository's ack/nack |
| **FRTB / SA-CVA / IMA** | Basel | Risk-factor completeness, price-observability (RFET) data quality, market-data continuity, model-input controls |
| **IFRS 9 / CECL** | Global/US | Staging-input completeness, arrears/forbearance consistency, macro-scenario data controls |
| **IFRS 17 / Solvency II QRT** | Insurance-adjacent | Cohort data completeness, QRT validation rules |
| **Basel III/IV RWA** | Global | Exposure completeness, collateral/netting-set integrity, rating and PD/LGD coverage |
| **PSD2 / Open Banking, ISO 20022 payments** | EU/UK | Message conformance, mandatory field presence, IBAN/BIC coherence |
| **AML / KYC / sanctions (FATF, BSA, 6AMLD)** | Global | Party completeness, duplicate parties (ER), UBO chain completeness, sanctions-screening input quality, transaction-monitoring feed integrity |
| **DORA** | EU | ICT/data resilience evidence, third-party data-feed monitoring, incident records |
| **EU AI Act (from Aug 2026)** | EU | Art. 10 data-governance evidence for high-risk AI (credit scoring, fraud, KYC): dataset relevance/representativeness/error-freedom, provenance, model cards, human oversight |
| **SR 11-7 / model risk** | US | Model input data quality controls, documented validation, versioning, audit trail |
| **SOX / ICFR** | US | Financial-reporting control evidence, sub-ledger↔GL reconciliation, sign-off |
| **GDPR / CCPA / DPDP** | Privacy | PII discovery, classification, masking, residency enforcement, erasure with audit integrity |

### 5.3 Control catalogue structure

Each catalogue entry: obligation ID and citation → control objective in business language →
PQL template(s) → required attributes (mapped to concept properties) → evidence requirements →
suggested severity, dimension, and cadence → attestation template. Coverage is reportable *per
obligation*, which answers the regulator's actual question: *"Which controls address principle 4,
and did they pass?"*

---

## 6. Reference reconciliations

Shipped as relationship templates; a bank instantiates them by pointing at their datasets.

| Reconciliation | Keys | Tolerance | Break taxonomy |
|---|---|---|---|
| Front office ↔ sub-ledger | trade ID / book / date | 0 for count, materiality for value | timing, FX, fee, cancel/amend, missing |
| **Sub-ledger ↔ general ledger** | account, cost centre, date | currency-specific materiality | timing, posting, FX, rounding, mapping |
| Internal position ↔ custodian | account, instrument, date | 0 quantity, tolerance on value | corporate action, settlement timing, price source |
| Cash book ↔ bank statement (camt.053/MT940) | account, value date, reference | 0 | unpresented, in-transit, fee, FX |
| Nostro / vostro | account, value date | 0 | timing, missing advice |
| Trade repository ↔ internal trade store | UTI | field-level | rejected, unpaired, mismatched, late |
| Risk system ↔ finance | netting set / entity / date | model-tolerance | scope, valuation-date, hierarchy |
| Regulatory return ↔ feeder | schedule line / dimension | 0 | mapping, filter, aggregation |
| T ↔ T-1 roll-forward | account / instrument | 0 | opening + movements ≠ closing |
| MT ↔ MX translation | payment reference | field-level | truncation, mapping, enrichment loss |
| Legacy ↔ target during migration | business key | 0 | parallel-run divergence |

---

## 7. Calendars, conventions, and normalisation

Financial data is calendar-dominated; correct calendars are the difference between a useful monitor
and a noise generator.

- **Settlement/holiday calendars:** TARGET2, US SIFMA, UK, JPX, HKEX, per-market and per-currency,
  with year-ahead schedules and versioning.
- **Business-date derivation** with timezone and cut-off awareness (a trade at 23:50 New York is a
  different business date in Tokyo).
- **Month/quarter/year-end effects** as explicit seasonality components.
- **Day-count and settlement conventions** (T+0/T+1/T+2 per market) for date-plausibility checks.
- **FX normalisation** with a declared rate source and as-of date, so reconciliation results are
  reproducible (`FR-REC-003`).
- **Minor-unit awareness** per ISO 4217 (JPY 0, KWD 3) for scale/rounding checks.

---

## 8. Scorecard templates and dimension weightings

Banking-specific defaults, all overridable:

| Dataset class | Composite method | Dimension weights (Acc/Comp/Cons/Time/Uniq/Val) |
|---|---|---|
| Regulatory return feeder | **weakest link** | 30/25/15/15/5/10 |
| Risk aggregation | weakest link | 30/25/20/15/5/5 |
| Finance / GL | weighted mean | 35/20/20/10/5/10 |
| Payments (in-flight) | weakest link | 20/20/15/30/5/10 |
| Client / party master | weighted mean | 25/25/15/5/20/10 |
| Market/reference data | weighted mean | 30/20/15/25/5/5 |
| Analytics / BI | weighted mean | 20/25/20/25/5/5 |

Materiality is weighted by **notional / exposure value at risk** by default in this pack, not by row
count — a defect on €2bn of notional is not equal to a defect on €2k.

---

## 9. Beachhead use cases (first 90 days at a customer)

| # | Use case | Value evidenced |
|---|---|---|
| 1 | **BCBS 239 control attestation for one risk domain** | Replaces a spreadsheet process; produces regulator-ready evidence; the reference for expansion |
| 2 | **Transaction-reporting pre-submission validation (EMIR/MiFIR)** | Direct fine avoidance; measurable rejection-rate reduction |
| 3 | **Sub-ledger ↔ GL reconciliation with break workflow** | Replaces or augments a reconciliation tool at DQ prices; SOX evidence |
| 4 | **Client/counterparty duplicate and LEI-quality remediation** | AML/KYC control improvement; measurable duplicate reduction |
| 5 | **Feed-arrival and completeness controls across the risk data supply chain** | Kills the most common cause of late/wrong risk reporting |
| 6 | **ISO 20022 MT↔MX translation fidelity** | Timely, board-visible, and unaddressed by any competitor |

---

## 10. Generalising to other industries

The pack mechanism is the entire industry story. A new vertical requires **no core engineering** —
only new pack content:

| Industry | Concepts | Semantic types | Formats | Regulations |
|---|---|---|---|---|
| **Insurance** | Policy, Claim, Cover, Reinsurance Treaty, Cohort | Policy no., NAIC codes | ACORD, EDI | Solvency II, IFRS 17, NAIC |
| **Healthcare** | Patient, Encounter, Claim, Provider, Medication | NPI, ICD-10, CPT, SNOMED, LOINC, RxNorm | HL7 v2, FHIR, X12 837/835, DICOM | HIPAA, GxP, EU MDR |
| **Telco** | Subscriber, CDR, Network Element, Plan | IMSI, MSISDN, IMEI, ICCID | ASN.1 CDR, TAP3, 3GPP | Regulatory reporting, lawful intercept |
| **Retail / CPG** | Product, SKU, Order, Shipment, Store | GTIN/EAN/UPC, GLN | EDI 850/856, GS1 | FSMA traceability |
| **Energy / Utilities** | Meter, Reading, Asset, Grid Node, Contract | MPRN/MPAN, EIC | CIM, MSCONS, ESPI | REMIT, EMIR (commodities), NERC CIP |
| **Public sector** | Citizen, Case, Benefit, Entitlement | National ID schemes | Government schemas | Statutory reporting |
| **Manufacturing** | Part, BOM, Work Order, Batch | Part no., serial | ISA-95, OPC-UA | Traceability, GxP |

Prama's core — semantic layer, PQL, IR, execution, calibration, evidence, learning — is invariant.
That is what makes "banking-first, industry-general" an architecture rather than a promise.

---

<div align="center">
<img src="assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../LICENSE">LICENSE</a> and <a href="../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
