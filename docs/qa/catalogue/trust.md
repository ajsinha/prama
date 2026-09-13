# Evidence, security and scoring

The parts of Prama that decide whether a claim can be believed: the hash-chained
ledger and its independent verifier, the residency and egress gates, customer-
managed keys, SSO, secrets, the composite score and the calibration that gives a
monitor's dial a meaning.

These packages make the strongest claims in the product — *immutable*,
*cannot*, *never*, *proof* — and round 1 established that the strong claims are
where the defects are. Two of them were already caught by the adversarial
review: the HMAC seals were verified only by recomputing them with the function
under test (T6), and the tombstone sat outside the hash whose docstring said
nothing is excluded from it (H4). Both are re-asserted here as regressions,
because a finding without a case is a finding that comes back.

Written from the code under `src/prama/evidence`, `src/prama/security`,
`src/prama/secrets`, `src/prama/score`, `src/prama/calibrate` and
`scripts/verify_evidence.py`. Nothing was executed.

| Area | Cases | P1 | P2 | P3 |
|---|---:|---:|---:|---:|
| Evidence — the record and its content hash | 22 | 10 | 8 | 4 |
| Evidence — erasure, tombstones and what survives | 16 | 8 | 6 | 2 |
| Evidence — the chain | 24 | 12 | 7 | 5 |
| Evidence — the Merkle root and the seal | 12 | 6 | 6 | 0 |
| Evidence — the recorder and the sample store | 14 | 4 | 8 | 2 |
| Evidence — replay and divergence | 14 | 7 | 7 | 0 |
| Evidence — retention, tiering and the WORM bundle | 22 | 11 | 8 | 3 |
| Evidence — the independent verifier | 24 | 15 | 7 | 2 |
| Security — scopes | 14 | 10 | 3 | 1 |
| Security — residency | 16 | 8 | 5 | 3 |
| Security — egress | 14 | 6 | 6 | 2 |
| Security — customer-managed keys | 22 | 15 | 7 | 0 |
| Security — OIDC | 31 | 18 | 11 | 2 |
| Security — SCIM provisioning | 15 | 7 | 7 | 1 |
| Security — SIEM export | 16 | 7 | 5 | 4 |
| Security — SOC 2 readiness | 7 | 2 | 4 | 1 |
| Security — the offline bundle | 32 | 16 | 13 | 3 |
| Secrets — references, providers, resolution and redaction | 49 | 23 | 21 | 5 |
| Scoring — composites, materiality and coverage | 30 | 12 | 13 | 5 |
| Scoring — trust propagation | 22 | 12 | 10 | 0 |
| Calibration — conformal p-values | 24 | 13 | 10 | 1 |
| Calibration — adaptive levels | 12 | 7 | 4 | 1 |
| Calibration — validity monitoring | 18 | 9 | 9 | 0 |
| Calibration — selection and the budget dial | 26 | 14 | 7 | 5 |
| **Total** | **496** | **252** | **192** | **52** |

---

## Evidence — the record and its content hash

### EVD-001 · The content hash covers every field of the record
- **Area:** `evidence/record.py::EvidenceRecord.content`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** take `dataclasses.fields(EvidenceRecord)`, subtract `previous_hash`
  and `tombstone`, and compare against the keys `content()` returns for a record
  written at the current `EVIDENCE_VERSION`
- **Expected:** the two sets are equal; a field added to the dataclass and not to
  `content()` fails this case
- **Why:** the docstring says "nothing is excluded for convenience: a field left
  out of the hash is a field somebody can change without detection". The one
  field that *was* excluded was the tombstone, and it took an adversarial review
  to find it. This is the check that would have found it first.

### EVD-002 · A field outside the hash is named, and its exclusion is justified
- **Area:** `evidence/record.py::EvidenceRecord.content`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** enumerate every dataclass field absent from `content()` and require
  a docstring sentence explaining it
- **Expected:** `previous_hash` (it is a hash) and `tombstone` (sealed
  separately, per `Tombstone.seal`) are the only two, each with a reason
- **Why:** finding H4 was exactly a field outside the hash with no statement
  that it was outside; the absence was invisible because nothing enumerated it.

### EVD-003 · `record_hash` is `sha256(previous_hash || content_hash)` over ASCII
- **Area:** `evidence/record.py::EvidenceRecord.record_hash`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** build a record with known field values, compute
  `hashlib.sha256((previous + content).encode("ascii")).hexdigest()` by hand in
  the test, compare
- **Expected:** identical, and pinned as a literal constant in the test
- **Why:** the chain rule is reimplemented in `scripts/verify_evidence.py`, in
  `Manifest.verification`, and in the runbook. A known-answer vector is what
  stops the four drifting apart.

### EVD-004 · The content hash does not depend on dict insertion order
- **Area:** `evidence/record.py::EvidenceRecord.content` · `core/pjson.py::canonical`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** build two identical records whose `metrics` and `parameters` were
  inserted in opposite orders; compare `content_hash`
- **Expected:** equal
- **Why:** a hash that depends on insertion order is not a hash of the content,
  and the difference would present as estate-wide tampering after a refactor.

### EVD-005 · The content hash does not depend on whether orjson is installed
- **Area:** `core/pjson.py::canonical` · `evidence/record.py::EvidenceRecord.content_hash`
- **Type:** contract
- **Priority:** P1
- **Precondition:** run the suite twice — once with `orjson` importable, once
  with it masked so `HAVE_ORJSON` is false
- **Steps:** hash the same record under both backends, including a metric of
  `1e16`, one of `0.1 + 0.2`, an integer beyond 2^53, and a unicode dataset name
- **Expected:** byte-identical `canonical()` output and identical `content_hash`
- **Why:** a chain whose hashes depend on which JSON library resolved is a chain
  that breaks when one host has a wheel another does not, and the failure
  arrives as "the evidence has been tampered with".

### EVD-006 · A record carrying non-ASCII text hashes the same in both implementations
- **Area:** `core/pjson.py::canonical` vs `scripts/verify_evidence.py::canonical`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a record whose `dataset` is `münchen.positionen` or whose
  `detail` contains a non-ASCII character
- **Steps:** compute the content hash with Prama, then with the independent
  verifier's `canonical()`
- **Expected:** equal
- **Why:** Prama's `dumpb` serialises with `ensure_ascii=False`; the verifier
  calls `json.dumps(..., sort_keys=True, separators=(",", ":"))` and takes the
  **default** `ensure_ascii=True`, which escapes every non-ASCII character to
  `\uXXXX`. If that reading is right, the independent verifier reports every
  record with a non-ASCII character as altered — on the estates most likely to
  have them. This case fails, or the reading is wrong; either outcome is worth
  knowing.

### EVD-007 · A metric of 8 and a metric of 8.0 hash identically
- **Area:** `evidence/record.py::_number`
- **Type:** regression
- **Priority:** P2
- **Precondition:** none
- **Steps:** record the same run twice, once with `{"rows": 8}` and once with
  `{"rows": 8.0}`
- **Expected:** the same `content_hash`
- **Why:** the docstring's own reason — a driver upgrade that starts returning
  integers as floats must not break every chain written before it.

### EVD-008 · A non-finite metric is serialised as null, and two of them collide
- **Area:** `evidence/record.py::_number` · `core/pjson.py::_sanitise`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** hash a record with `{"ratio": float("nan")}` and the same record
  with `{"ratio": float("inf")}`
- **Expected:** both serialise to `null`, so the two hash identically — assert
  the collision exists and is documented, or that such a metric is refused
- **Why:** two materially different run outcomes producing one hash is a hole
  in "the hash covers the content", however narrow. It should be a stated
  limitation rather than a surprise.

### EVD-009 · `detail` beyond 300 characters is outside the hash
- **Area:** `evidence/record.py::DETAIL_LIMIT` · `EvidenceRecord.content`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** build two records identical except for characters 301 onwards of
  `detail`; compare `content_hash`; then compare `to_dict()["detail"]`
- **Expected:** the hashes are equal and the serialised detail is truncated, so
  the stored record and the hashed record agree
- **Why:** truncation inside `content()` and not inside the field is how a
  record could carry 4 KB of detail that no hash covers. The case pins that the
  truncation happens on the way out as well as on the way into the hash.

### EVD-010 · A 1.0 record read by a 1.1 build still hashes to its stored value
- **Area:** `evidence/record.py::FIELDS_SINCE` · `EvidenceRecord.content`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a stored record payload with `evidence_version: "1.0"` and
  no `dimensions` or `criticality` keys
- **Steps:** `EvidenceRecord.from_dict(payload)`, recompute `content_hash`,
  compare with the stored one
- **Expected:** equal; `content()` emits neither new field
- **Why:** emitting a new field unconditionally breaks every hash after the
  first and presents as an estate-wide tampering alert the morning after a
  deploy. The module says so; this is the case that holds it.

### EVD-011 · A 1.1 record emits both fields added in 1.1
- **Area:** `evidence/record.py::EvidenceRecord.content`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** hash a record at `evidence_version = "1.1"` carrying dimensions and
  criticality; assert both keys appear in `content()`
- **Expected:** `dimensions` as a list, `criticality` as an int
- **Why:** the version gate must not be so conservative that a new field is
  never hashed at all, which is the other way to get it wrong.

### EVD-012 · `1.10` sorts after `1.9`
- **Area:** `evidence/record.py::_version_tuple`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `_version_tuple("1.10") > _version_tuple("1.9")`
- **Expected:** true
- **Why:** string comparison gets this backwards, and the consequence is a
  future field silently omitted from the hash of every record that should carry
  it.

### EVD-013 · An unparsable evidence version degrades to hashing the 1.0 field set
- **Area:** `evidence/record.py::_version_tuple`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a payload with `evidence_version: "banana"`
- **Steps:** read it back, recompute the content hash
- **Expected:** `(0, 0)`, so no versioned field is emitted — and the record's
  stored hash will therefore not match unless it really was written that way;
  the breach is reported as `content`, not swallowed
- **Why:** a garbage version must not become a way to choose which fields are
  hashed. An attacker who can set `evidence_version` can drop `dimensions` and
  `criticality` out of the hash; this case establishes what happens when they
  do.

### EVD-014 · An unknown key added to a stored record is invisible to Prama's own verifier
- **Area:** `evidence/ledger.py::verify` · `evidence/record.py::EvidenceRecord.from_dict`
- **Type:** security
- **Priority:** P1
- **Precondition:** a valid exported chain
- **Steps:** add `"note": "approved by treasury"` to one record's JSON, leaving
  every hash untouched; run `Ledger.verify` over the payloads; then run
  `scripts/verify_evidence.py` over the same file
- **Expected:** both report a breach
- **Why:** `from_dict` drops keys it does not know, so Prama's `verify()`
  rehashes a record that no longer resembles the bytes on disk, while the
  independent verifier hashes the payload as it found it. The two
  implementations disagree about a forged record — and the one that is wrong is
  the one shipped inside the product.

### EVD-015 · The snapshot is inside the hash
- **Area:** `evidence/record.py::SnapshotRef` · `EvidenceRecord.content`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** flip `snapshot.exact` from false to true on a stored record,
  leaving hashes alone; verify
- **Expected:** a `content` breach
- **Why:** `exact` is what the replay report uses to tell "this was never
  replayable" from "something is wrong we cannot see". Being able to flip it
  after the fact turns an unexplained divergence into an excused one.

### EVD-016 · `claim` states a narrow verdict narrowly
- **Area:** `evidence/record.py::EvidenceRecord.claim`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `claim` for `coverage="full"`, `"incremental"` and `"forward_only"`
- **Expected:** the bare verdict for `full`; `"<verdict> over the rows examined"`
  for the other two
- **Why:** a `pass` after an incremental run says only that the rows examined
  were sound. A product that rendered the two the same lets the narrow claim be
  read as the wide one, which is the misreading a scorecard makes by default.

### EVD-017 · Coverage is inside the hash
- **Area:** `evidence/record.py::EvidenceRecord.content`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** change a stored record's `coverage` from `incremental` to `full`
- **Expected:** a `content` breach
- **Why:** it is the single field that changes how wide the recorded claim is,
  and it is exactly the field somebody would want to widen.

### EVD-018 · A record round-trips through `to_dict`/`from_dict` unchanged
- **Area:** `evidence/record.py::EvidenceRecord.to_dict` · `from_dict`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a record with every optional field populated, including a
  tombstone
- **Steps:** `from_dict(record.to_dict())`, compare hashes and every field
- **Expected:** identical record, identical `content_hash` and `record_hash`
- **Why:** the ledger is written and read through this pair; a lossy field here
  is a chain that breaks on restart.

### EVD-019 · Reading a record with fields missing applies the documented defaults
- **Area:** `evidence/record.py::EvidenceRecord.from_dict`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `{}`
- **Steps:** `EvidenceRecord.from_dict({})`
- **Expected:** `verdict="error"`, `criticality=4`, `coverage="full"`,
  `triggered_by="schedule"`, `previous_hash=GENESIS`,
  `evidence_version=EVIDENCE_VERSION`
- **Why:** the default verdict being `error` rather than `pass` is a deliberate
  safety property and must not drift.

### EVD-020 · A metric that arrives as a string is coerced or refused, not silently dropped
- **Area:** `evidence/record.py::EvidenceRecord.from_dict`
- **Type:** negative
- **Priority:** P3
- **Precondition:** a payload with `"metrics": {"rows": "eight"}`
- **Steps:** read it back
- **Expected:** a typed failure naming the record and the metric — not a
  `ValueError` traceback out of `float()`
- **Why:** reading a corrupt ledger is an operator's task, and an unhandled
  `ValueError` tells them nothing about which record to look at.

### EVD-021 · A record stays inside its stated size budget
- **Area:** `evidence/record.py::EvidenceRecord.size_bytes`
- **Type:** performance
- **Priority:** P3
- **Precondition:** a representative record: four metrics, three parameters, a
  256-character detail
- **Steps:** `size_bytes`
- **Expected:** under the two kilobytes the `detail` docstring names as the
  record's budget
- **Why:** the whole separation of samples from records exists to keep this
  number small, and the number is stated in a docstring nothing checks.

### EVD-022 · `GENESIS` is sixty-four zeros and nothing else
- **Area:** `evidence/record.py::GENESIS`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare `GENESIS` with `"0" * 64`, and with the constant in
  `scripts/verify_evidence.py`
- **Expected:** equal in both places
- **Why:** two copies of a constant that must agree, in two files that must not
  import each other.

## Evidence — erasure, tombstones and what survives

### EVD-023 · Erasing a record keeps the chain verifiable across it
- **Area:** `evidence/record.py::EvidenceRecord.erase` · `evidence/ledger.py::verify`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a chain of five records
- **Steps:** erase record 2, write the chain back, verify
- **Expected:** intact, `erased == 1`, and records 3-5 still link
- **Why:** the whole design exists so that a right-to-erasure request does not
  destroy the audit trail. If this fails, the lawful option is to break the
  chain.

### EVD-024 · The erased record's content hash is the hash the content had
- **Area:** `evidence/record.py::EvidenceRecord.content_hash`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a record with known content
- **Steps:** capture `content_hash`, erase, compare
- **Expected:** unchanged, and taken from `tombstone.original_content_hash`
  rather than recomputed
- **Why:** it is the one value that keeps the chain linking, and recomputing it
  from the emptied fields would break every record after it.

### EVD-025 · Exactly the documented fields survive an erasure
- **Area:** `evidence/record.py::EvidenceRecord.erase`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a fully populated record
- **Steps:** erase it and enumerate every field that is still non-default
- **Expected:** the surviving set is exactly `sequence`, `control_version`,
  `engine`, `coverage`, `verdict`, `started_at`, `finished_at`, `duration_ms`,
  `triggered_by`, `tenant_id`, `criticality`, `previous_hash`,
  `evidence_version` — and each is justified as "the shape of the fact"
- **Steps (second half):** confirm `plan_id`, `control_id`, `dataset`,
  `binding`, `parameters`, `metrics`, `samples_digest`, `sample_count`,
  `detail`, `dimensions` and the snapshot are cleared
- **Why:** "what is lost is exactly what was asked to be lost, and nothing
  else" is a legal claim. `verdict`, `tenant_id` and `criticality` surviving may
  well be right; nothing currently states that they do.

### EVD-026 · Erasing an already-erased record is a no-op
- **Area:** `evidence/record.py::EvidenceRecord.erase`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an erased record
- **Steps:** `erase(by="other", authority="other")` again
- **Expected:** the same record returned unchanged; the original erasure's
  author and authority are not overwritten
- **Why:** a second erasure that replaced the first would let anybody rewrite
  who erased a record by erasing it again.

### EVD-027 · The tombstone's seal is a hash of the tombstone's own fields
- **Area:** `evidence/record.py::Tombstone.seal`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** compute `sha256(canonical({original_content_hash, erased_at,
  erased_by, authority, reason}))` independently and compare with `seal`
- **Expected:** equal, pinned as a literal in the test
- **Why:** finding H4. The seal is the only thing covering who erased a record
  and under what authority.

### EVD-028 · Rewriting `erased_by` invalidates the seal
- **Area:** `evidence/record.py::Tombstone` · `scripts/verify_evidence.py::verify_chain`
- **Type:** security
- **Priority:** P1
- **Precondition:** a sealed bundle containing one erased record
- **Steps:** rewrite the record's `tombstone.erased_by` to `mallory` and its
  `authority` to `"no authority at all"`, leaving the seal as written; re-seal
  the manifest so the payload digest matches; run the independent verifier
- **Expected:** exit 1, naming the tombstone seal
- **Why:** this is the exact reproduction from the adversarial review, including
  the re-sealed manifest — without which the payload digest catches it for the
  wrong reason and the real gap stays hidden.

### EVD-029 · A tombstone with its seal stripped is refused
- **Area:** `scripts/verify_evidence.py::verify_chain`
- **Type:** security
- **Priority:** P1
- **Precondition:** as EVD-028
- **Steps:** delete the `seal` key from the tombstone entirely; re-seal the
  manifest; verify
- **Expected:** exit 1, "erased, and the tombstone carries no seal"
- **Why:** an attacker who cannot forge a seal removes it, and a check that runs
  only when a seal is present checks nothing. The review says this in as many
  words.

### EVD-030 · A tombstone cannot be lifted from one record onto another
- **Area:** `evidence/record.py::Tombstone.seal` · `scripts/verify_evidence.py`
- **Type:** security
- **Priority:** P1
- **Precondition:** a chain with one erased record and one intact record
- **Steps:** copy the erased record's tombstone wholesale onto the intact one
  and set that record's `content_hash` to the tombstone's
  `original_content_hash`; re-seal; verify
- **Expected:** a failure — the link check, because the record hash no longer
  follows from `previous + content`
- **Why:** the seal covers `original_content_hash` precisely so a tombstone is
  bound to one record. This is the case that proves the binding does something.

### EVD-031 · Prama's own `verify()` does not check the tombstone seal
- **Area:** `evidence/ledger.py::verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** a chain in the database with one erased record
- **Steps:** rewrite `erased_by` and `authority` in storage; call
  `Ledger.verify()` and `prama` whatever surfaces it; then run the independent
  verifier over an export of the same records
- **Expected:** both report a breach
- **Why:** `verify()` reads `record.is_erased`, counts it, and compares
  `content_hash` against the tombstone's own `original_content_hash` — which the
  attacker did not need to touch. The seal is checked in
  `scripts/verify_evidence.py` and, as far as this reading goes, nowhere inside
  the product. The fix for H4 may have landed in one of the two implementations
  only.

### EVD-032 · The erasure records who, when and under what authority
- **Area:** `evidence/record.py::Tombstone`
- **Type:** functional
- **Priority:** P2
- **Precondition:** none
- **Steps:** `erase(by="dpo@bank", authority="DSAR-2026-114")`, serialise
- **Expected:** all three present plus `reason` defaulting to "right to
  erasure"; the erasure timestamp comes from the archivist's clock, not the
  record's
- **Why:** an erasure with no authority recorded is indistinguishable from a
  deletion somebody performed on their own initiative.

### EVD-033 · The tombstone holds no subject identity
- **Area:** `evidence/record.py::Tombstone`
- **Type:** security
- **Priority:** P2
- **Precondition:** none
- **Steps:** inspect every field of a tombstone after an erasure
- **Expected:** nothing identifying the data subject; `authority` names the
  request, not the person
- **Why:** the docstring's own point — recording who was erased in order to
  prove they were erased is absurd, and it is the kind of thing an
  implementation adds for convenience.

### EVD-034 · `Tombstone.from_dict` ignores a supplied seal
- **Area:** `evidence/record.py::Tombstone.from_dict`
- **Type:** security
- **Priority:** P2
- **Precondition:** a tombstone payload with a forged `seal` value
- **Steps:** read it back and re-serialise
- **Expected:** the seal is recomputed from the fields, so the forged value
  never survives a round trip; and any check on it compares the *stored* seal
  against the recomputation rather than the recomputation against itself
- **Why:** this is the T6 shape — a seal checked by recomputing it with the code
  under test can never fail. The verifier does it correctly by popping the
  stored seal first; anything inside the product must do the same.

### EVD-035 · Verification reports erased records rather than absorbing them
- **Area:** `evidence/ledger.py::Verification.render`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a chain with three erased records
- **Steps:** render the verification
- **Expected:** the count and the sentence saying their place is verified and
  their contents are gone
- **Why:** an auditor must be told, and a silent erasure is a hole nobody can
  account for.

### EVD-036 · Erasing a sequence that is not in the ledger is refused or reported
- **Area:** `evidence/retention.py::Archivist.erase`
- **Type:** negative
- **Priority:** P3
- **Precondition:** a ledger of five records
- **Steps:** `erase(ledger, [99], by="dpo")`
- **Expected:** either a `ValidationError` naming the missing sequence, or a
  returned result stating that nothing was erased
- **Why:** as written, the sequence is simply not matched and the caller gets
  the ledger back unchanged, having believed it satisfied a legal request.

### EVD-037 · An erasure applied to hot storage does not retroactively alter a written bundle
- **Area:** `evidence/retention.py::Archivist.erase`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a bundle written to WORM before the erasure request
- **Steps:** erase in hot storage; verify the previously written bundle
- **Expected:** the bundle still verifies and still holds the content; the
  divergence between the two copies is documented as a legal decision the caller
  makes, not a defect
- **Why:** `erase` returns records for the caller to write back precisely
  because propagating into WORM is a legal question. The product must not imply
  the erasure was complete.

### EVD-038 · A ledger that is entirely erased still verifies
- **Area:** `evidence/ledger.py::verify`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** every record erased
- **Steps:** verify
- **Expected:** intact, `erased == records`, and the rendered summary says the
  contents of all of them are gone
- **Why:** the degenerate case of the conflict this design resolves; it should
  read as "nothing can be checked but the shape", not as a pass.

## Evidence — the chain

### EVD-039 · The first record starts from genesis
- **Area:** `evidence/ledger.py::Ledger.append`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an empty ledger
- **Steps:** append one record
- **Expected:** `sequence == 0`, `previous_hash == GENESIS`, `head ==
  record.record_hash`
- **Why:** the anchor of every later check.

### EVD-040 · The ledger sets the sequence and the previous hash, not the caller
- **Area:** `evidence/ledger.py::Ledger.append`
- **Type:** security
- **Priority:** P1
- **Precondition:** a ledger with three records
- **Steps:** append a record constructed with `sequence=0` and
  `previous_hash="ff"*32`
- **Expected:** both are overwritten with the ledger's own values
- **Why:** a caller that could choose them could write a record that looked
  linked and was not, and the guarantee would rest on every caller being
  careful.

### EVD-041 · Sequence numbers are contiguous across many appends
- **Area:** `evidence/ledger.py::Ledger.next_sequence`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** append a thousand records; collect sequences
- **Expected:** `0..999` with no gaps or repeats
- **Why:** a gap is the only way a missing record is visible; no hash reveals
  one.

### EVD-042 · `head` on an empty ledger is genesis, not an error
- **Area:** `evidence/ledger.py::Ledger.head`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** empty ledger
- **Steps:** read `head`, `next_sequence`, `verify()`, `merkle_root()`
- **Expected:** `GENESIS`, `0`, an intact verification of zero records, and a
  Merkle root of `GENESIS`
- **Why:** the empty case is what a fresh install has, and a crash here is a
  first-run failure.

### EVD-043 · An edited record is reported as `content`
- **Area:** `evidence/ledger.py::verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** an exported chain of ten records
- **Steps:** change record 4's `verdict` from `fail` to `pass`, leaving all
  hashes untouched; verify
- **Expected:** a `content` breach at sequence 4 saying the record has been
  altered — and also a `link` breach, because the record hash no longer follows
- **Why:** the first thing anybody tries.

### EVD-044 · A record replaced wholesale with a self-consistent hash is caught by the link
- **Area:** `evidence/ledger.py::verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** as above
- **Steps:** replace record 4 with a fabricated record whose own `content_hash`
  and `record_hash` are correctly computed, leaving records 5-9 alone
- **Expected:** no `content` breach on record 4, a `link` breach on record 5
- **Why:** internally consistent forgery is the level above naive tampering, and
  the chain is what is supposed to stop it.

### EVD-045 · A fully re-chained forgery verifies, and only a published root catches it
- **Area:** `evidence/ledger.py::verify` · `merkle_root`
- **Type:** security
- **Priority:** P1
- **Precondition:** a chain whose Merkle root was published externally
- **Steps:** edit record 4 and recompute every hash from 4 to the end; verify;
  then compare `merkle_root()` and `head` with the published values
- **Expected:** `verify()` reports intact — and the root and head both differ
  from the published ones, which is the only detection
- **Why:** this is the honest limit of a self-contained chain and the entire
  reason the Merkle root exists. A product that implied `verify()` catches this
  would be overstating.

### EVD-046 · A record removed from the middle is a gap and a broken link
- **Area:** `evidence/ledger.py::verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** a ten-record chain
- **Steps:** delete record 4 from the export; verify
- **Expected:** a `gap` breach naming sequence 5 and saying one record is
  missing, plus a `link` breach
- **Why:** deletion is the tampering that leaves the remaining chain valid; only
  the sequence reveals it.

### EVD-047 · Two records swapped are reported as out of order
- **Area:** `evidence/ledger.py::verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** a ten-record chain
- **Steps:** swap records 4 and 5 in the file; verify
- **Expected:** a `gap` breach whose detail reads "records are out of order",
  plus link breaches
- **Why:** the reordering case has its own message because the remedy differs —
  a reordered export is usually a bad writer, a missing record usually is not.

### EVD-048 · Truncation at the end is invisible to the chain
- **Area:** `evidence/ledger.py::verify` · `evidence/retention.py::Bundle.check`
- **Type:** security
- **Priority:** P1
- **Precondition:** a ten-record bundle
- **Steps:** delete the last three lines of `evidence.ndjson`; run
  `Bundle.check()`; then run `verify()` over the lines alone
- **Expected:** `verify()` reports intact — and `check()` fails on the
  manifest's record count
- **Why:** truncation is the failure an archive actually suffers, and the
  manifest count is the only thing that reveals it. The case has to assert both
  halves or it teaches the wrong lesson.

### EVD-049 · A chain whose first record is not sequence zero is not treated as forged
- **Area:** `evidence/ledger.py::verify`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a window of the ledger, sequences 100 to 199, as
  `Archivist.bundle` produces for a warm or cold tier
- **Steps:** `verify(records)`
- **Expected:** no breach — the window is a legitimate export, its first
  record's `previous_hash` is record 99's hash, and `from_sequence` in the
  manifest says so
- **Why:** as read, `verify` initialises `previous_hash = GENESIS` and then
  compares the first record's `previous_hash` against it unconditionally, so
  **every bundle that does not begin at sequence 0 reports a broken chain at its
  own first record**. `Archivist.bundle` computes its manifest with the same
  function, so it would seal a bundle whose `check()` fails. The identical
  construction sits in `scripts/verify_evidence.py::verify_chain`. This is the
  highest-value case in the file.

### EVD-050 · The genesis check fires only for a record claiming to be the first
- **Area:** `evidence/ledger.py::verify`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a record with `sequence == 0` and a non-genesis
  `previous_hash`
- **Steps:** verify
- **Expected:** a `genesis` breach saying the first record does not start the
  chain
- **Why:** a chain spliced onto another chain's head, presented as a whole
  ledger, is exactly this shape.

### EVD-051 · A single record on its own verifies only against itself
- **Area:** `evidence/ledger.py::verify`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** one record, exported alone
- **Steps:** verify it
- **Expected:** whatever the answer is, it is stated plainly — a lone record
  proves its own content hash and nothing about its position
- **Why:** finding T11: `verify([record.to_dict()])` was "intact for any content
  whatsoever", because the record supplies both sides of every comparison. The
  case exists so nobody builds a test on that footing again.

### EVD-052 · Concurrent appends produce a contiguous, singly-linked chain
- **Area:** `evidence/ledger.py::Ledger.append`
- **Type:** concurrency
- **Priority:** P1
- **Precondition:** one `Ledger`, eight threads
- **Steps:** append 500 records per thread; verify
- **Expected:** either 4,000 records forming an intact chain, or a documented
  refusal to be used from several threads — not a chain with duplicate sequences
- **Why:** `append` reads `next_sequence` and `head` and then mutates a list,
  with no lock. Two writers interleaving produce two records claiming the same
  previous hash, and the product records evidence from a worker pool.

### EVD-053 · The storage seam is two methods and nothing else leaks through it
- **Area:** `evidence/ledger.py::Ledger`
- **Type:** contract
- **Priority:** P3
- **Precondition:** none
- **Steps:** enumerate `Ledger`'s public surface
- **Expected:** append and iterate, plus derived readers; nothing that assumes a
  table, a file or an object store
- **Why:** the docstring's claim. A ledger that knew where records live would
  have to be reimplemented per deployment.

### EVD-054 · `since` and `find` do not renumber or relink
- **Area:** `evidence/ledger.py::Ledger.since` · `Ledger.find`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a chain of twenty records, three sharing a plan id
- **Steps:** `since(10)` and `find(plan_id)`
- **Expected:** the right subsets, each record carrying its original sequence
  and previous hash
- **Why:** a slice that renumbered would produce a chain that verifies and is
  not the one that was written.

### EVD-055 · The export is newline-delimited JSON, one record per line
- **Area:** `evidence/ledger.py::Ledger.export`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a chain containing a record whose `detail` holds a newline
  and a unicode character
- **Steps:** export; count lines; parse each
- **Expected:** exactly one line per record, every line parsing on its own, no
  embedded raw newline
- **Why:** the format's whole justification is that a truncated file leaves
  every complete line readable. One record carrying a literal newline destroys
  that, and `detail` is free text from an exception.

### EVD-056 · The export does not end with a blank line the verifier miscounts
- **Area:** `evidence/ledger.py::Ledger.export` · `scripts/verify_evidence.py::read_records`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a ten-record chain
- **Steps:** export, write to a file, count records the verifier reads, compare
  with the manifest count
- **Expected:** ten in both, whether or not a trailing newline was added by
  whatever wrote the file
- **Why:** the verifier skips blank lines and the manifest's `payload_digest`
  covers the exact bytes, so a trailing newline added by a copy tool fails the
  digest and not the count. The two must be exercised together.

### EVD-057 · A breach names the record and says what to do about it
- **Area:** `evidence/ledger.py::Breach.render`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** one breach of each kind: `content`, `link`, `gap`, `order`,
  `genesis`
- **Steps:** render each
- **Expected:** each names the sequence and reads as a sentence an operator can
  act on; the five kinds map onto the five entries in the runbook's "the chain
  does not verify" table
- **Why:** the runbook tells an operator to read these; the mapping is a
  documented contract and nothing checks it.

### EVD-058 · `Verification.to_dict` reports the breach kinds a script can branch on
- **Area:** `evidence/ledger.py::Verification.to_dict`
- **Type:** contract
- **Priority:** P3
- **Precondition:** a chain with two distinct breaches
- **Steps:** serialise
- **Expected:** `intact: false`, both breaches with `kind`, `sequence`,
  `detail`, plus `head`, `merkle_root`, `erased`
- **Why:** this is the machine-readable half of the verification and the shape a
  CI gate consumes.

### EVD-059 · The verification's head is the last record's hash
- **Area:** `evidence/ledger.py::verify`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a chain of ten
- **Steps:** compare `verify().head` with `ledger.head`
- **Expected:** equal
- **Why:** the head is what gets signed and published; two ways of computing it
  must agree.

### EVD-060 · A breach does not stop verification early
- **Area:** `evidence/ledger.py::verify`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a chain with tampering at records 2 and 7
- **Steps:** verify
- **Expected:** both reported
- **Why:** an auditor needs the full extent of the damage, not the first
  instance of it.

### EVD-061 · Verification of a large chain is linear and streams
- **Area:** `evidence/ledger.py::verify`
- **Type:** performance
- **Priority:** P3
- **Precondition:** one million records as a generator of payloads
- **Steps:** verify
- **Expected:** completes without materialising the whole chain; the only list
  retained is the record hashes for the Merkle root
- **Why:** seven years at millions a day is the stated scale, and `verify`
  accumulates `hashes` for every record it sees.

### EVD-062 · Verifying the same bundle twice gives the same answer
- **Area:** `evidence/ledger.py::verify`
- **Type:** functional
- **Priority:** P3
- **Precondition:** any bundle
- **Steps:** verify twice, in two processes with different `PYTHONHASHSEED`
- **Expected:** identical head, root and breach list
- **Why:** hash-order dependence in a verification result is the subtlest way
  for an audit answer to become non-reproducible.

## Evidence — the Merkle root and the seal

### EVD-063 · The root of an empty set is genesis
- **Area:** `evidence/ledger.py::merkle_root`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `merkle_root([])`
- **Expected:** `GENESIS`
- **Why:** it must be a value, and it must be one a reader can tell from a real
  root.

### EVD-064 · The root of one hash is that hash
- **Area:** `evidence/ledger.py::merkle_root`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `merkle_root([h])`
- **Expected:** `h` itself
- **Why:** the loop never runs; an implementation that hashed the singleton
  would disagree with the independent verifier.

### EVD-065 · The root of two hashes is the hash of their concatenation
- **Area:** `evidence/ledger.py::merkle_root`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** compare with `sha256((a + b).encode("ascii")).hexdigest()`
- **Expected:** equal, pinned as a literal
- **Why:** the base case of a construction reimplemented in two files.

### EVD-066 · An odd node is promoted, not duplicated
- **Area:** `evidence/ledger.py::merkle_root`
- **Type:** security
- **Priority:** P1
- **Precondition:** three record hashes `[a, b, c]`
- **Steps:** compute `merkle_root([a, b, c])` and `merkle_root([a, b, c, c])`
- **Expected:** different roots
- **Why:** duplicating the odd node is the well-known construction that lets two
  different sets produce one root. Under it those two calls are equal, and a set
  with a record appended twice publishes as the original. The module says it
  promotes; this is what proves it.

### EVD-067 · Reordering the records changes the root
- **Area:** `evidence/ledger.py::merkle_root`
- **Type:** security
- **Priority:** P2
- **Precondition:** four hashes
- **Steps:** swap two and recompute
- **Expected:** a different root
- **Why:** a root insensitive to order would let a day's evidence be reshuffled
  under a published value.

### EVD-068 · Both Merkle implementations agree on every size from 0 to 33
- **Area:** `evidence/ledger.py::merkle_root` vs `scripts/verify_evidence.py::merkle_root`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** for each n in 0..33, build n distinct hashes and compare the two
  functions
- **Expected:** equal at every n, including the odd sizes where promotion
  happens at more than one level
- **Why:** the odd-node rule bites at levels above the first for n = 5, 9, 11
  and 13, and a disagreement there surfaces as an unverifiable bundle once a
  year.

### EVD-069 · The chain head is signed with HMAC, pinned to an independent vector
- **Area:** `evidence/ledger.py::sign`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a fixed key and a fixed head
- **Steps:** compare `sign(head, key)` with an HMAC written out from RFC 2104
  over `hashlib` alone, in a test that does not import `hmac`
- **Expected:** equal
- **Why:** finding T6 — every test of every seal was `sign` agreeing with
  `sign`, and replacing HMAC with a length-extension-vulnerable prefix MAC
  produced zero failures. This is the shape that catches that.

### EVD-070 · `verify_signature` refuses a wrong key, a wrong head and a truncated signature
- **Area:** `evidence/ledger.py::verify_signature`
- **Type:** security
- **Priority:** P1
- **Precondition:** a valid head, key and signature
- **Steps:** vary each of the three in turn, including a signature truncated to
  32 hex characters and one with a single character changed
- **Expected:** false in every case
- **Why:** a prefix-comparison bug passes the truncation case, and a
  comparison-by-`==` passes everything the happy path covers.

### EVD-071 · The comparison is constant-time, asserted by reading the code
- **Area:** `evidence/ledger.py::verify_signature`
- **Type:** security
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse the function and require `hmac.compare_digest`
- **Expected:** present; `==` against a signature fails the case
- **Why:** the review's own approach — a timing test on a laptop measures the
  laptop.

### EVD-072 · Signing with an empty key is refused
- **Area:** `evidence/ledger.py::sign`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `sign(head, b"")`
- **Expected:** a refusal naming the empty key
- **Why:** `hmac.new` accepts an empty key happily and returns a
  respectable-looking hex string that anybody can reproduce. The shipped
  `security.session_secret` is empty on purpose, so an empty key is the value a
  misconfigured deployment actually has.

### EVD-073 · What the signature proves is stated wherever it is shown
- **Area:** `evidence/ledger.py::sign` docstring · CLI and API surfaces that render it
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** grep every surface that prints the word "signed" over a chain head
- **Expected:** each carries the sentence that an HMAC says nothing to somebody
  who does not hold the key
- **Why:** the module is careful about this and the carefulness has to survive
  the trip to the screen, which is where the word is read.

### EVD-074 · A published root plus a signed head detects the re-chained forgery
- **Area:** `evidence/ledger.py::merkle_root` · `sign`
- **Type:** security
- **Priority:** P1
- **Precondition:** the forged chain from EVD-045 and the signature over the
  original head
- **Steps:** `verify_signature(forged_head, key, original_signature)`
- **Expected:** false
- **Why:** this closes the loop on the one attack the chain alone cannot see,
  and it is the procedure the product should be telling auditors to run.

## Evidence — the recorder and the sample store

### EVD-075 · A recorded run lands in the ledger, linked
- **Area:** `evidence/recorder.py::Recorder.record`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a compiled plan and a control result
- **Steps:** record it
- **Expected:** the returned record has the ledger's next sequence and the
  previous head; `ledger.verify()` is intact
- **Why:** the seam between execution and evidence; everything else assumes it.

### EVD-076 · The control id defaults to the plan's PQL hash
- **Area:** `evidence/recorder.py::Recorder.record`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a plan with provenance
- **Steps:** record without `control_id`
- **Expected:** `control_id == plan.provenance.pql_hash`
- **Why:** the record must name what was checked, not merely which row pointed
  at it — a control row can be edited, a hash cannot.

### EVD-077 · Dimensions come from the plan and cannot be supplied by the caller
- **Area:** `evidence/recorder.py::Recorder.record`
- **Type:** security
- **Priority:** P2
- **Precondition:** a plan declaring completeness
- **Steps:** inspect the signature; attempt to pass dimensions
- **Expected:** no such parameter; the record carries the plan's dimensions
- **Why:** a run that could label its own results would let two records of the
  same control score against different dimensions, and a scorecard is built by
  dimension.

### EVD-078 · Criticality *is* supplied by the caller, and that asymmetry is deliberate
- **Area:** `evidence/recorder.py::Recorder.record`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** record the same plan twice with `criticality=1` and `criticality=4`
- **Expected:** both accepted; the difference is visible in the record and in
  the weighted score; the reason the tier is trusted from the caller while
  dimensions are not is stated
- **Why:** criticality weights a Tier 1 control sixteen times a Tier 4 one. If a
  caller can choose it, a caller can choose the score.

### EVD-079 · A run with no snapshot is marked inexact rather than stamped with the clock
- **Area:** `evidence/recorder.py::_snapshot_ref`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a source that cannot identify its state
- **Steps:** record with `snapshot=None`
- **Expected:** `kind="none"`, `identifier=""`, `exact=False`
- **Why:** filling it in from the clock makes every record look replayable and
  destroys the replay report's ability to tell an unidentifiable source from a
  disagreeing one.

### EVD-080 · A source's own snapshot is carried verbatim
- **Area:** `evidence/recorder.py::_snapshot_ref`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a source reporting a file digest and `exact=True`
- **Steps:** record
- **Expected:** kind, identifier and the exact flag mirrored, with the enum
  value unwrapped to its string
- **Why:** the replay diagnosis turns entirely on these three fields.

### EVD-081 · A negative duration is clamped, not recorded
- **Area:** `evidence/recorder.py::Recorder.record`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a clock whose `now()` is before `started_at`
- **Steps:** record
- **Expected:** `duration_ms == 0`
- **Why:** clocks step backwards, and a negative duration in evidence is a
  number nobody can explain to an auditor.

### EVD-082 · A metric the engine did not return is absent, not zero
- **Area:** `evidence/recorder.py::Recorder.record`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a result whose metrics omit `violating_rows`
- **Steps:** record; inspect the stored metrics
- **Expected:** the key is absent
- **Why:** the module's stated rule. A zero is a measurement; an absence is the
  truth, and the difference decides whether a scorecard counts the control.

### EVD-083 · Samples are stored only when rows were given
- **Area:** `evidence/recorder.py::Recorder.record` · `SampleStore.put`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a failing result with no rows retained
- **Steps:** record
- **Expected:** `samples_digest == ""`, `sample_count == 0`, nothing in the
  store
- **Why:** an empty digest must mean "no sample kept" rather than "a sample of
  nothing".

### EVD-084 · Two identical sample sets share one digest, and forgetting one forgets both
- **Area:** `evidence/recorder.py::SampleStore.put` · `forget`
- **Type:** negative
- **Priority:** P2
- **Precondition:** two runs producing byte-identical failing rows
- **Steps:** store both, then `forget` the digest once; look up the other
  record's samples
- **Expected:** the behaviour is defined — either reference counting, or a
  statement that sample sets are content-addressed and shared
- **Why:** content addressing is right for storage and surprising for retention:
  expiring one record's samples silently expires another's, and that record's
  own retention said they were still kept.

### EVD-085 · The sample digest is truncated to 128 bits, and that is stated
- **Area:** `evidence/recorder.py::SampleStore.put`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** inspect the digest format — `sha256:` plus 32 hex characters
- **Expected:** documented as a 128-bit content address, not as a full SHA-256
- **Why:** it is referenced from an evidence record as a hash; a reader is
  entitled to know how much collision resistance it carries.

### EVD-086 · Forgetting a sample leaves the record that names it intact
- **Area:** `evidence/recorder.py::SampleStore.forget`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a record with 50 samples
- **Steps:** forget the digest; verify the chain; read the record
- **Expected:** the chain is intact, `sample_count` still reads 50, the rows are
  gone
- **Why:** this is the entire justification for separating the two lifetimes —
  the evidence still says what was found and says honestly that the rows are
  gone.

### EVD-087 · Which columns were masked is lost when the sample expires
- **Area:** `evidence/recorder.py::SampleSet.masked` · `evidence/record.py::EvidenceRecord`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a sample stored with `masked=("iban", "name")`
- **Steps:** forget the sample; read the record; ask which columns were masked
- **Expected:** the answer is available, or its absence is documented
- **Why:** `SampleSet.masked` exists "so a reader knows what they are not
  seeing", and the record carries only the digest and the count. Once the
  sample expires nothing records that anything was masked at all.

### EVD-088 · An empty ledger passed to the recorder is used, not replaced
- **Area:** `evidence/recorder.py::Recorder.__init__`
- **Type:** regression
- **Priority:** P2
- **Precondition:** an empty `Ledger` and an empty `SampleStore`
- **Steps:** construct a `Recorder` with both; record; check the caller's
  objects
- **Expected:** the caller's ledger holds the record
- **Why:** both define `__len__`, so an empty one is falsy and `or` would
  silently substitute a fresh object. The caller would hold a ledger that never
  fills and evidence that goes nowhere.

## Evidence — replay and divergence

### EVD-089 · An exact replay is reported as identical
- **Area:** `evidence/replay.py::compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two records identical in plan, snapshot, engine, coverage,
  parameters, verdict and metrics
- **Steps:** compare
- **Expected:** `Cause.IDENTICAL`, `answer_held` true, no differences
- **Why:** the base case, and the one the compliance claim is built on.

### EVD-090 · Inputs that moved with an unchanged answer are `STABLE`, not a divergence
- **Area:** `evidence/replay.py::compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a replay against a later snapshot, same verdict and metrics
- **Steps:** compare
- **Expected:** `Cause.STABLE`, `is_divergence` false, and a rendering that says
  the control reached the same conclusion about different data
- **Why:** a nightly replay against fresh data would otherwise report every
  record as diverged and bury the two that matter.

### EVD-091 · A changed plan is reported as the control changing, even when the data moved too
- **Area:** `evidence/replay.py::compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a replay whose `plan_id`, snapshot and verdict all differ
- **Steps:** compare
- **Expected:** `Cause.CONTROL_CHANGED`
- **Why:** the ordering is the whole design — if the control moved, the answers
  were never comparable and no amount of looking at the data explains it.

### EVD-092 · A changed control version is a control change
- **Area:** `evidence/replay.py::_input_differences`
- **Type:** functional
- **Priority:** P2
- **Precondition:** same plan id, `control_version` 1 → 2, different verdict
- **Steps:** compare
- **Expected:** `Cause.CONTROL_CHANGED`
- **Why:** a version bump with an unchanged plan hash means the declaration
  moved even if the compiled plan did not, and the two must be reported alike.

### EVD-093 · Changed parameters are named before the data
- **Area:** `evidence/replay.py::compare`
- **Type:** functional
- **Priority:** P2
- **Precondition:** same plan, different `parameters`, different verdict
- **Steps:** compare
- **Expected:** `Cause.PARAMETERS_CHANGED`
- **Why:** a different scope was examined; blaming the data sends somebody
  looking for a restatement that did not happen.

### EVD-094 · Changed coverage is checked before the snapshot
- **Area:** `evidence/replay.py::compare`
- **Type:** regression
- **Priority:** P2
- **Precondition:** a replay that ran `full` where the original ran
  `incremental`, with a different snapshot as well
- **Steps:** compare
- **Expected:** `Cause.COVERAGE_CHANGED`
- **Why:** two runs that read different amounts of the table were never
  comparable, and the ordering comment says so. A reordering of the `elif` chain
  would break it silently.

### EVD-095 · A moved snapshot with an exact source is a data change
- **Area:** `evidence/replay.py::compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `snapshot.exact` true, identifier moved, verdict changed
- **Steps:** compare
- **Expected:** `Cause.DATA_CHANGED`, not escalated
- **Why:** the ordinary and most common case; escalating it is how the report
  becomes noise.

### EVD-096 · An inexact snapshot excuses a divergence, and says the run was never replayable
- **Area:** `evidence/replay.py::compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** identical identifiers, `exact=False`, different verdict
- **Steps:** compare
- **Expected:** `Cause.SNAPSHOT_NOT_EXACT`, with the explanation that the
  original record said so
- **Why:** without it an estate of file-digest sources generates unexplained
  divergences every night until nobody reads them.

### EVD-097 · An inexact snapshot masks an engine disagreement
- **Area:** `evidence/replay.py::compare`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `snapshot.exact` false, same identifier, **different
  engine**, different verdict
- **Steps:** compare
- **Expected:** the engine change is reported, or the report says both are true
- **Why:** the `elif` order puts the inexactness test before the engine test, so
  two engines genuinely disagreeing about the same plan are excused as "the
  source could not identify its state" — and the engine case is the one the
  module calls the portability failure worth escalating.

### EVD-098 · An engine disagreement escalates
- **Area:** `evidence/replay.py::Cause.needs_escalation`
- **Type:** functional
- **Priority:** P1
- **Precondition:** same plan, same exact snapshot, different engine, different
  verdict
- **Steps:** compare; render
- **Expected:** `Cause.ENGINE_CHANGED`, `needs_escalation` true, and the rendered
  line saying this is not an ordinary divergence
- **Why:** it means the conformance suite missed something, which is a release
  gate failure rather than a data question.

### EVD-099 · An unexplained divergence is reported as alarming
- **Area:** `evidence/replay.py::compare`
- **Type:** functional
- **Priority:** P1
- **Precondition:** every input identical, exact snapshot, different verdict
- **Steps:** compare
- **Expected:** `Cause.UNEXPLAINED`, escalated, `all_accounted_for` false on a
  report containing it
- **Why:** it is the one case that should not be possible, and smoothing it into
  one of the others is the temptation the module was written against.

### EVD-100 · A metric difference with an unchanged verdict is still a divergence
- **Area:** `evidence/replay.py::_answer_differences` · `Divergence.render`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** same verdict, `violating_rows` 12 → 19
- **Steps:** compare; render
- **Expected:** a divergence whose headline reads "<verdict>, with different
  numbers", `verdict_changed` false
- **Why:** the verdict holding while the count moves is the shape of a threshold
  that is about to be crossed.

### EVD-101 · Timings and sequence numbers are not reported as differences
- **Area:** `evidence/replay.py::_input_differences`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a replay a month later, taking twice as long
- **Steps:** compare an otherwise identical pair
- **Expected:** `Cause.IDENTICAL`, no differences
- **Why:** a replay always happens later and always takes a different length of
  time; reporting that buries the differences that matter.

### EVD-102 · A replay report counts by cause and lists only the escalations
- **Area:** `evidence/replay.py::ReplayReport`
- **Type:** functional
- **Priority:** P2
- **Precondition:** 100 divergences: 60 identical, 20 stable, 15 data changed,
  4 engine changed, 1 unexplained
- **Steps:** render and serialise
- **Expected:** `held == 80`, `identical == 60`, `all_accounted_for` false,
  five escalations listed in full and the rest counted
- **Why:** the acceptance criterion is that nothing diverges without a named
  cause, and the report is where a release gate reads it.

## Evidence — retention, tiering and the WORM bundle

### EVD-103 · Tiers out of order are refused at construction
- **Area:** `evidence/retention.py::RetentionPolicy.__post_init__`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `RetentionPolicy(hot_days=400, warm_days=100)`
- **Expected:** `ValidationError` with the remedy about evidence moving outward
  and the three values in the context
- **Why:** a policy whose tiers run backwards would age a record into a tier it
  has already left, and nothing downstream would notice.

### EVD-104 · Equal tier lengths are allowed
- **Area:** `evidence/retention.py::RetentionPolicy.__post_init__`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** none
- **Steps:** `RetentionPolicy(hot_days=90, warm_days=90, cold_days=90)`
- **Expected:** accepted — the check is `<=`
- **Why:** "hot and warm are the same length" is a legitimate policy for an
  estate that keeps everything online.

### EVD-105 · A record exactly at a tier boundary stays in the wider tier
- **Area:** `evidence/retention.py::RetentionPolicy.tier_at`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** the default policy
- **Steps:** `tier_at(90.0)`, `tier_at(90.0001)`, `tier_at(365.0)`,
  `tier_at(365.0001)`
- **Expected:** HOT, WARM, WARM, COLD
- **Why:** off-by-one at a retention boundary moves evidence out of the
  queryable tier a day early, and the symptom is a dashboard that lost
  yesterday.

### EVD-106 · Past the cold window with expiry off, evidence stays cold
- **Area:** `evidence/retention.py::RetentionPolicy.tier_at`
- **Type:** security
- **Priority:** P1
- **Precondition:** `expire=False` (the default)
- **Steps:** `tier_at(10_000)`
- **Expected:** `Tier.COLD`
- **Why:** deletion because a record ran off the end of its own table is
  accidental, silent and permanent — the worst kind of data loss, and the reason
  the default is not to expire.

### EVD-107 · Expiry happens only when it was asked for
- **Area:** `evidence/retention.py::RetentionPolicy.tier_at`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `expire=True`
- **Steps:** `tier_at(cold_days)` and `tier_at(cold_days + 1)`
- **Expected:** COLD then EXPIRED
- **Why:** the boundary at which evidence is deleted is the most consequential
  boundary in the module.

### EVD-108 · A record with no finish time stays hot
- **Area:** `evidence/retention.py::Archivist.tier_of`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a record with `finished_at == ""`
- **Steps:** `tier_of`
- **Expected:** `Tier.HOT`
- **Why:** ageing a record out on a guess is deleting evidence because a field
  was blank.

### EVD-109 · A record with an unparsable finish time stays hot
- **Area:** `evidence/retention.py::Archivist.tier_of`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `finished_at = "yesterday"`
- **Steps:** `tier_of`
- **Expected:** `Tier.HOT`, no exception
- **Why:** stated in the code — deleting evidence because its date did not parse
  is not a trade anybody would make deliberately.

### EVD-110 · A record with a naive timestamp does not crash the archivist
- **Area:** `evidence/retention.py::Archivist.tier_of`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `finished_at = "2026-01-01T00:00:00"` — no offset, as a
  record written by another system or imported from an older format would carry
- **Steps:** `tier_of`
- **Expected:** a tier, or a typed refusal naming the record
- **Why:** `datetime.fromisoformat` parses it happily into a *naive* datetime
  and the subtraction from an aware `clock.now()` raises `TypeError`, which the
  `except ValueError` does not catch. One such record stops the whole retention
  sweep.

### EVD-111 · The tier plan accounts for every record exactly once
- **Area:** `evidence/retention.py::Archivist.plan`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a ledger spanning four tiers
- **Steps:** `plan`; sum the bucket lengths
- **Expected:** equals `len(ledger)`; every tier key present even when empty
- **Why:** a record that falls out of the plan is a record nothing will ever
  move or delete.

### EVD-112 · The retention report describes the policy in words
- **Area:** `evidence/retention.py::RetentionPolicy.describe` · `Archivist.report`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** both `expire=True` and `expire=False`
- **Steps:** describe
- **Expected:** "kept indefinitely beyond N days" versus "deleted after N days",
  with thousands separators
- **Why:** this sentence is what a compliance officer reads to decide whether
  the configuration matches the obligation.

### EVD-113 · Bundling nothing is refused
- **Area:** `evidence/retention.py::Archivist.bundle`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an empty record list
- **Steps:** bundle
- **Expected:** `ValidationError` with the remedy explaining that an empty
  bundle claims nothing ran
- **Why:** "a period in which nothing ran" is a different and much more alarming
  claim than "nobody exported anything", and an empty bundle makes the first one
  silently.

### EVD-114 · The residency gate is consulted before a bundle is built
- **Area:** `evidence/retention.py::Archivist.bundle`
- **Type:** security
- **Priority:** P1
- **Precondition:** a tenant whose residency is `EU` and an archive region of
  `US`
- **Steps:** bundle with the gate
- **Expected:** `ResidencyRefused` naming the egress point, the tenant, the
  destination and the jurisdiction; no bundle produced
- **Why:** this is the last point that knows whose evidence this is; a transport
  handed a finished string has nothing left to decide with.

### EVD-115 · A refused bundle is refused wholesale, never partially
- **Area:** `evidence/retention.py::Archivist.bundle`
- **Type:** security
- **Priority:** P1
- **Precondition:** a record set spanning two jurisdictions
- **Steps:** bundle under a rule permitting one of them
- **Expected:** the whole call fails; no bundle containing the permitted subset
- **Why:** a bundle missing the records that could not cross verifies perfectly
  and is missing records — the one failure the manifest's count exists to catch,
  defeated by the export itself.

### EVD-116 · The manifest describes the payload it was built from
- **Area:** `evidence/retention.py::Archivist.bundle` · `Manifest`
- **Type:** functional
- **Priority:** P1
- **Precondition:** ten records, two of them erased
- **Steps:** bundle; inspect the manifest
- **Expected:** `records=10`, `erased=2`, `from_sequence`/`to_sequence` matching
  the first and last, `payload_digest` matching the payload bytes,
  `chain_head` matching the last record, `bundle_version` and
  `evidence_version` present
- **Why:** every one of these is a check the independent verifier performs, and
  all of them are written here.

### EVD-117 · `Bundle.check` passes on a bundle as built
- **Area:** `evidence/retention.py::Bundle.check`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a freshly built bundle of a window that starts at sequence 0
- **Steps:** check
- **Expected:** `(True, "...chain intact...")`
- **Why:** the happy path, and the control against which EVD-049 is the
  counterfactual.

### EVD-118 · `Bundle.check` fails on a truncated payload
- **Area:** `evidence/retention.py::Bundle.check`
- **Type:** security
- **Priority:** P1
- **Precondition:** a ten-record bundle
- **Steps:** drop the last two lines of the payload without touching the
  manifest; check
- **Expected:** false, naming the count mismatch and calling the bundle
  incomplete
- **Why:** the manifest's count is the only thing that reveals truncation.

### EVD-119 · `Bundle.check` fails on a payload that does not match the digest
- **Area:** `evidence/retention.py::Bundle.check`
- **Type:** security
- **Priority:** P1
- **Precondition:** a bundle
- **Steps:** change one character of one record and re-count the lines so the
  count still matches; check
- **Expected:** false on the digest, before any chain work
- **Why:** it is the cheapest check and the one that catches a corrupted
  transfer.

### EVD-120 · `Bundle.check` fails when the head does not match the manifest
- **Area:** `evidence/retention.py::Bundle.check`
- **Type:** security
- **Priority:** P2
- **Precondition:** a bundle whose manifest head was edited
- **Steps:** check
- **Expected:** false, "the chain head does not match the manifest"
- **Why:** the head is the value published or signed elsewhere; a mismatch
  between the manifest and the records is the whole reason to state it twice.

### EVD-121 · A bundle writes exactly two files, neither hiding the other
- **Area:** `evidence/retention.py::Bundle.files`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a bundle
- **Steps:** `files()`
- **Expected:** `manifest.json` and `evidence.ndjson`, the names the independent
  verifier looks for when given a directory
- **Why:** two names duplicated across two files that must not import each
  other.

### EVD-122 · The manifest's verification prose matches what the verifier does
- **Area:** `evidence/retention.py::Manifest.verification` vs `scripts/verify_evidence.py`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the prose against the implementation, check by check
- **Expected:** every check the verifier performs is described, and every
  description is performed
- **Why:** the prose is what somebody reimplements from in ten years. As read it
  describes the content hash, the record hash, the link and the tombstone's
  meaning — and mentions neither the **tombstone seal** nor the **Merkle root**
  nor the **payload digest**, all of which the verifier checks. A
  reimplementation from the manifest alone would not check who erased a record.

### EVD-123 · The bundle version is recorded and read back
- **Area:** `evidence/retention.py::BUNDLE_VERSION`
- **Type:** contract
- **Priority:** P3
- **Precondition:** none
- **Steps:** build a bundle; read `manifest["bundle_version"]`
- **Expected:** `"1.0"`, and a bundle carrying an unknown future version is
  reported rather than parsed optimistically
- **Why:** a bundle opened in ten years has to name the algorithm that checks
  it.

### EVD-124 · Nothing in the product actually exports an evidence bundle
- **Area:** `evidence/retention.py::Archivist.bundle` · `cli/` · `api/`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a clean install with evidence in the ledger
- **Steps:** look for a command or a route that writes `manifest.json` and
  `evidence.ndjson` to disk; follow the runbook's "an auditor wants to verify a
  bundle"
- **Expected:** a documented way to produce the bundle the runbook tells
  auditors to verify
- **Why:** round-1 finding Q-34. `Archivist.bundle` exists and no CLI group
  reaches it; `prama bundle` is the *offline install* bundle, which is a
  different artefact with a different manifest. The runbook's evidence
  procedure begins at a file nothing creates.

## Evidence — the independent verifier

### EVD-125 · The verifier imports nothing from Prama and nothing outside the stdlib
- **Area:** `scripts/verify_evidence.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse the file with `ast`, collect every import, compare against
  `sys.stdlib_module_names`
- **Expected:** only `hashlib`, `json`, `sys`, `pathlib` — nothing named
  `prama`, nothing third-party
- **Why:** independence is the entire point. An import added for convenience
  turns the second implementation into the first one wearing a hat, and the
  agreement between them stops meaning anything.

### EVD-126 · The verifier runs on a bare interpreter with Prama uninstalled
- **Area:** `scripts/verify_evidence.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a Python 3 interpreter with no site-packages from this
  project
- **Steps:** `python3 verify_evidence.py <bundle>` from a directory that is not
  the repository
- **Expected:** it runs and reports
- **Why:** the auditor's machine is not a development machine, and the whole
  claim is "check it with nothing but a SHA-256 implementation".

### EVD-127 · A good bundle exits 0 with every check listed
- **Area:** `scripts/verify_evidence.py::main`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a valid bundle
- **Steps:** run it
- **Expected:** exit 0; PASS lines for content, links, sequence, count, payload
  digest, Merkle root and chain head
- **Why:** the checks have to be *named* on the happy path, or nobody can tell
  which ones ran.

### EVD-128 · A failed check exits 1
- **Area:** `scripts/verify_evidence.py::main`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a bundle with one edited record
- **Steps:** run it
- **Expected:** exit 1 and "this bundle is not what its manifest claims"
- **Why:** the runbook documents this code, and an auditor scripts against it.

### EVD-129 · An unreadable bundle exits 2, distinctly
- **Area:** `scripts/verify_evidence.py::Unreadable`
- **Type:** negative
- **Priority:** P1
- **Precondition:** four cases — a missing directory, a directory with no
  `manifest.json`, a `manifest.json` that is not JSON, and an
  `evidence.ndjson` line that is not JSON
- **Steps:** run each
- **Expected:** exit 2 in all four, with a message naming the file
- **Why:** "I could not read it" and "it is wrong" are different findings — a
  broken transfer versus a broken claim — and the runbook says so.

### EVD-130 · An unreadable file exits 2 and not 1
- **Area:** `scripts/verify_evidence.py::main`
- **Type:** negative
- **Priority:** P2
- **Precondition:** an `evidence.ndjson` with no read permission
- **Steps:** run it
- **Expected:** exit 2 via the `OSError` branch
- **Why:** a permission problem reported as a failed verification sends an
  auditor to accuse the sender.

### EVD-131 · Wrong argument counts exit 2 with the usage
- **Area:** `scripts/verify_evidence.py::locate`
- **Type:** negative
- **Priority:** P3
- **Precondition:** none
- **Steps:** run with zero arguments and with three
- **Expected:** exit 2 and the two-line usage
- **Why:** on an air-gapped host there is nobody to ask what the arguments are.

### EVD-132 · Both invocation forms work
- **Area:** `scripts/verify_evidence.py::locate`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a bundle directory
- **Steps:** run with the directory, then with the two file paths explicitly
- **Expected:** identical output
- **Why:** the second form is what somebody uses when the files arrived
  separately, which on a disk they often do.

### EVD-133 · The verifier catches an edited record
- **Area:** `scripts/verify_evidence.py::verify_chain`
- **Type:** security
- **Priority:** P1
- **Precondition:** a bundle whose record 4 has a changed verdict, with the
  manifest re-sealed so the payload digest matches
- **Steps:** run
- **Expected:** the content check fails, naming record 4 and both hash prefixes
- **Why:** re-sealing the manifest is what anybody with write access does; the
  case has to be run that way or the payload digest catches it for the wrong
  reason.

### EVD-134 · The verifier catches a broken link
- **Area:** `scripts/verify_evidence.py::verify_chain`
- **Type:** security
- **Priority:** P1
- **Precondition:** a bundle with one record removed and the manifest count
  adjusted, digest re-taken
- **Steps:** run
- **Expected:** link and sequence checks both fail
- **Why:** the attacker who adjusts the count is the attacker this is for.

### EVD-135 · The verifier reports the sequence gap separately from the link
- **Area:** `scripts/verify_evidence.py::verify_chain`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a bundle of records 0-4 and 6-9, re-linked so every hash is
  consistent
- **Steps:** run
- **Expected:** the link check passes and the sequence check fails
- **Why:** it is the case where no hash can reveal the missing record, which is
  why the sequence check exists at all.

### EVD-136 · The verifier checks the tombstone seal, and refuses a missing one
- **Area:** `scripts/verify_evidence.py::verify_chain`
- **Type:** security
- **Priority:** P1
- **Precondition:** the bundles from EVD-028 and EVD-029
- **Steps:** run both
- **Expected:** exit 1 in both, one for a seal that does not match and one for a
  seal that is absent
- **Why:** finding H4's fix lives here, and the absent-seal branch is the half
  an attacker would reach for.

### EVD-137 · The verifier checks the tombstone against the record's content hash
- **Area:** `scripts/verify_evidence.py::verify_chain`
- **Type:** security
- **Priority:** P1
- **Precondition:** a record whose tombstone's `original_content_hash` differs
  from the record's stored `content_hash`
- **Steps:** run
- **Expected:** the tombstone check fails with "names a different original
  content hash"
- **Why:** it is what stops a valid tombstone being moved between records.

### EVD-138 · An erased record's presence is reported, not silently passed
- **Area:** `scripts/verify_evidence.py::verify_chain`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a bundle with two erased records, all seals holding
- **Steps:** run
- **Expected:** exit 0, with a line saying two records carry a tombstone whose
  seal holds and that their contents cannot be verified, only their place and
  the erasure
- **Why:** the runbook promises this exact behaviour: a tombstoned record is not
  a failure and is not counted as an ordinary pass.

### EVD-139 · The manifest count check catches truncation
- **Area:** `scripts/verify_evidence.py::verify_manifest`
- **Type:** security
- **Priority:** P1
- **Precondition:** a bundle with the last three lines removed
- **Steps:** run
- **Expected:** the count check fails and says the remaining chain is perfectly
  valid without them
- **Why:** it is the failure an archive actually suffers, and the explanation is
  what stops the operator dismissing it.

### EVD-140 · The payload digest check catches any byte change
- **Area:** `scripts/verify_evidence.py::verify_manifest`
- **Type:** security
- **Priority:** P1
- **Precondition:** a bundle with one whitespace character added
- **Steps:** run
- **Expected:** the digest check fails
- **Why:** the coarse check that catches what the per-record checks would
  otherwise have to notice individually.

### EVD-141 · The Merkle root check catches a substituted record set
- **Area:** `scripts/verify_evidence.py::verify_manifest`
- **Type:** security
- **Priority:** P1
- **Precondition:** a bundle whose records were replaced with a different,
  internally consistent chain and whose count and digest were updated
- **Steps:** run
- **Expected:** the Merkle root and chain head checks both fail against the
  original manifest values
- **Why:** this is the re-chained forgery again, caught here only because the
  manifest was not regenerated — and the case makes plain that regenerating it
  defeats every check but a published root.

### EVD-142 · An empty bundle is refused rather than passed
- **Area:** `scripts/verify_evidence.py::main` · `verify_manifest`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a hand-made bundle with an empty `evidence.ndjson` and a
  manifest stating zero records, a matching digest, `merkle_root` of genesis and
  `chain_head` of genesis
- **Steps:** run
- **Expected:** a stated outcome — not "Every check passed" on a file with no
  evidence in it
- **Why:** every check is vacuously satisfied. `Archivist.bundle` refuses to
  build one; nothing stops somebody producing one by hand, and it would verify
  green in front of an auditor.

### EVD-143 · The success text states what the green result does not mean
- **Area:** `scripts/verify_evidence.py::main`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a good bundle
- **Steps:** read the output
- **Expected:** the four lines saying this does not establish the records were
  true when written
- **Why:** printed on success because success is where the overstatement
  happens. If the wording drifts, the product starts claiming more than chain
  integrity delivers.

### EVD-144 · The two implementations agree on a corpus of adversarial bundles
- **Area:** `evidence/ledger.py::verify` vs `scripts/verify_evidence.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a corpus: intact, edited, truncated, reordered, gapped,
  re-chained, erased-and-sealed, erased-and-tampered, extra-key, non-ASCII,
  window-not-starting-at-zero
- **Steps:** run both over each
- **Expected:** the same verdict on every one
- **Why:** the agreement between them is the claim. Cases EVD-006, EVD-014,
  EVD-031 and EVD-049 each predict a disagreement; this is where they are
  collected.

### EVD-145 · The verifier's `canonical` excludes exactly the three hash fields
- **Area:** `scripts/verify_evidence.py::NOT_CONTENT`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** compare `NOT_CONTENT` against the fields Prama's `content()`
  omits
- **Expected:** `previous_hash`, `content_hash`, `record_hash` — and the
  `tombstone` key, which `content()` also omits and the verifier does not
- **Why:** for an erased record the verifier pops the tombstone's seal and
  hashes separately, so the exclusion sets differ in a way that is correct and
  entirely undocumented. For a *non*-erased record carrying a stray `tombstone`
  key the two implementations would disagree.

### EVD-146 · The verifier caps its output rather than printing a million failures
- **Area:** `scripts/verify_evidence.py::verify_chain`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a bundle where every record fails the content check
- **Steps:** run
- **Expected:** the first five per check, with the totals still visible
- **Why:** an auditor scrolling a million lines learns nothing; the `[:5]`
  slices exist and nothing pins them.

### EVD-147 · A record whose sequence is absent does not crash the verifier
- **Area:** `scripts/verify_evidence.py::verify_chain`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a record JSON with no `sequence` key
- **Steps:** run
- **Expected:** a reported failure, not a `TypeError` from `expected_sequence + 1`
- **Why:** `payload.get("sequence")` returns `None`, the comparison with an int
  is fine, and the `isinstance` guard covers the increment — but the first
  record sets `expected_sequence = None`, which then never increments. The
  behaviour on a malformed record should be a finding, not silence.

### EVD-148 · The verifier's report distinguishes a check that failed from one that did not run
- **Area:** `scripts/verify_evidence.py::Report`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a bundle with no erased records
- **Steps:** run; read the checks
- **Expected:** the tombstone check is absent rather than shown as passing
- **Why:** a PASS line for a check that had nothing to check is how a reader
  concludes that erasure was verified when no erasure was present.

## Security — scopes

### SEC-001 · The vocabulary is one list, and it is the one the roles grant from
- **Area:** `security/scopes.py::SCOPES` · `cli/principal.py::BUILTIN_ROLES`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** expand every role's grants and check each against `SCOPES`,
  allowing one-level wildcards
- **Expected:** every grant names a scope that exists
- **Why:** finding H5 was two vocabularies a comment insisted were one, and the
  first fix for S4 briefly made it three. A role granting a permission no route
  recognises is a credential that cannot be satisfied — worse than one that is
  not enforced, because it fails in production rather than in review.

### SEC-002 · No route requires a permission no role can hold
- **Area:** `security/scopes.py::SCOPES` · the API routing table
- **Type:** contract
- **Priority:** P1
- **Precondition:** the app built
- **Steps:** walk every route's declared scope; check some built-in role grants
  it
- **Expected:** every required scope is reachable
- **Why:** the other direction of the same contract, and the one that produces
  a screen nobody can use.

### SEC-003 · Every scope carries a sentence a person can read in an audit log
- **Area:** `security/scopes.py::SCOPES`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** assert each value is a non-empty sentence, not a restatement of the
  key
- **Expected:** all sixteen
- **Why:** the dict is the product's own explanation of its permission model.

### SEC-004 · An exact grant permits exactly its own scope
- **Area:** `security/scopes.py::permits`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `permits(["control:approve"], "control:approve")` and
  `permits(["control:approve"], "control:propose")`
- **Expected:** true, then false
- **Why:** the base case of the only authorisation decision in the product.

### SEC-005 · A wildcard matches one level and no more
- **Area:** `security/scopes.py::permits`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** none
- **Steps:** `permits(["control:*"], "control:approve")` → true;
  `permits(["control:*"], "incident:read")` → false;
  `permits(["con:*"], "control:approve")`
- **Expected:** true, false, and the third case examined closely
- **Why:** the implementation tests `wanted.startswith(grant[:-1])`, so
  `"con:*"` becomes the prefix `"con:"` — which `"control:approve"` does not
  start with, so it is false. But `"control:*"` reduces to `"control:"` and any
  scope beginning with that string matches, including a hypothetical
  `control:approve:all`. The one-level claim needs a case that pins the
  boundary.

### SEC-006 · The bare wildcard permits everything
- **Area:** `security/scopes.py::WILDCARD`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `permits(["*"], s)` for every scope in `SCOPES`
- **Expected:** true for all
- **Why:** it is what `admin` holds, so a break here locks out the only account
  that can fix it.

### SEC-007 · An empty grant permits nothing
- **Area:** `security/scopes.py::permits`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** `permits([], s)` for every scope
- **Expected:** false for all
- **Why:** "no scopes recorded" is not "no restriction". The opposite default is
  how every credential minted before scopes were enforced becomes a superuser on
  the day they are switched on.

### SEC-008 · An invented scope is never satisfied and is caught at minting
- **Area:** `security/scopes.py::unknown`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `unknown(["semantic:read", "control:read"])`
- **Expected:** `["semantic:read"]`, and the key-minting path refuses rather
  than issuing a key that will be denied on first use
- **Why:** a scope that does not exist can never be satisfied, so granting one
  is a silent denial discovered by a user at the worst moment.

### SEC-009 · `unknown` ignores wildcards rather than rejecting them
- **Area:** `security/scopes.py::unknown`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `unknown(["*", "control:*", "nonsense:*"])`
- **Expected:** empty — and the third entry examined, because `nonsense:*`
  names a family that does not exist and is silently accepted
- **Why:** the check exists to catch typos, and a typo in the prefix of a
  wildcard grant passes straight through it.

### SEC-010 · Scope matching is case-sensitive and does not trim
- **Area:** `security/scopes.py::permits`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** `permits(["Control:Approve"], "control:approve")` and
  `permits([" control:approve"], "control:approve")`
- **Expected:** false in both, and the minting path normalises or refuses
- **Why:** a grant that differs from the requirement by a space is a permission
  nobody can hold, stored in a record that reads as though they can.

### SEC-011 · One matcher serves both callers
- **Area:** `security/scopes.py::permits` · `db` principal permission check · API key scopes
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** grep for any second implementation of wildcard scope matching
- **Expected:** exactly one
- **Why:** the module's stated reason for existing — the rule had been written
  once and was about to be written twice, and a rule restated drifts in the
  flattering direction.

### SEC-012 · A read-only key cannot perform a write, on every scoped route
- **Area:** `security/scopes.py::permits` · API route dependencies
- **Type:** security
- **Priority:** P1
- **Precondition:** a key holding only `declaration:read`
- **Steps:** attempt every write route
- **Expected:** 403 on all of them, with a remedy quoting the vocabulary
- **Why:** finding S4 — the key record, the admin screen and the audit log all
  read as though an authorisation decision were being made, and none was.

### SEC-013 · Authorisation is decided before the request body is parsed
- **Area:** API dependency order · `security/scopes.py`
- **Type:** security
- **Priority:** P2
- **Precondition:** a read-only key
- **Steps:** POST a deliberately invalid body to a write route
- **Expected:** 403, not 422
- **Why:** round-1 finding Q-46 — a read-only key can enumerate the write schema
  through validation errors when the order is the other way round.

### SEC-014 · The steward role can do the things the console offers a steward
- **Area:** `cli/principal.py::BUILTIN_ROLES` · console route guards
- **Type:** regression
- **Priority:** P1
- **Precondition:** a principal with the `steward` role
- **Steps:** attempt every console action the UI presents to them
- **Expected:** each permitted
- **Why:** round-1 finding Q-21 — 45 of 48 console routes gate on
  `declaration:*` alone, so the steward is refused every write the console
  offers them. This is the role↔route contract failing in the direction that
  ships.

## Security — residency

### SEC-015 · A tenant with no rule is unrestricted, and the decision says so
- **Area:** `security/residency.py::Policy.decide`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `Policy.of(None)`
- **Steps:** decide any movement
- **Expected:** `Verdict.UNRESTRICTED`, `may_proceed` true, and a description
  ending "That is an absence of a rule, not an approval"
- **Why:** most deployments have no residency obligation, and a product that
  refused everything until a rule was written is one nobody finishes
  installing — but the sentence must not read as an approval.

### SEC-016 · A movement inside the rule is permitted and names the rule
- **Area:** `security/residency.py::Policy.decide`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `Policy.of("EU,EEA")`, destination `eu`, jurisdiction `EU`
- **Steps:** decide
- **Expected:** `PERMITTED`, and a sentence naming both
- **Why:** an operator must be able to argue with a decision, including one that
  went their way.

### SEC-017 · A destination outside the rule is refused
- **Area:** `security/residency.py::Policy.decide`
- **Type:** security
- **Priority:** P1
- **Precondition:** `Policy.of("EU")`, destination `US`, jurisdiction `EU`
- **Steps:** decide
- **Expected:** `REFUSED`, naming the jurisdiction, the destination and the rule
- **Why:** the case the whole module exists for.

### SEC-018 · Data whose jurisdiction is inside the rule but whose destination is not, and vice versa
- **Area:** `security/residency.py::Policy.decide`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `Policy.of("EU")`
- **Steps:** decide (destination `EU`, jurisdiction `US`) and (destination `US`,
  jurisdiction `EU`)
- **Expected:** refused in both — the code requires *both* to be in the allowed
  set
- **Why:** moving US-owned data into the EU estate is a residency question too,
  and an implementation checking only the destination would permit it.

### SEC-019 · Undeclared jurisdiction is refused, not assumed unrestricted
- **Area:** `security/residency.py::Verdict.UNDECLARED`
- **Type:** security
- **Priority:** P1
- **Precondition:** `Policy.of("EU")`, destination `EU`, jurisdiction `""`
- **Steps:** decide
- **Expected:** `UNDECLARED`, refused, `is_undeclared` true
- **Why:** the module's own argument — treating undeclared as unrestricted is
  how the one table nobody got round to declaring is the one that leaves the
  region.

### SEC-020 · An undeclared refusal carries a different remedy from a destination refusal
- **Area:** `security/egress.py::_remedy_for`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** the three refusal shapes
- **Steps:** read the remedy on each
- **Expected:** declare the jurisdiction · state the destination · send it
  somewhere permitted
- **Why:** the remedy is the whole value of a policy refusal, and the three
  actions are genuinely different people.

### SEC-021 · A movement with no destination is refused, not passed
- **Area:** `security/residency.py::Policy.decide` · `Decision.destination_unstated`
- **Type:** security
- **Priority:** P1
- **Precondition:** `Policy.of("EU")`, destination `""`
- **Steps:** decide
- **Expected:** `REFUSED`, destination rendered as `(unstated)`,
  `destination_unstated` true
- **Why:** a check that cannot be made is a refusal. The alternative is a
  connector with an unset region exporting freely.

### SEC-022 · A movement with no destination under *no* rule is permitted
- **Area:** `security/residency.py::Policy.decide`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `Policy.of(None)`, destination `""`
- **Steps:** decide
- **Expected:** `UNRESTRICTED` with `(unstated)` as the destination, and the
  asymmetry with SEC-021 stated
- **Why:** the unrestricted branch runs before the missing-destination branch,
  so an unconfigured region is checked in one deployment and not in another.

### SEC-023 · A rule accepts both the comma string and the list form
- **Area:** `security/residency.py::Policy.of`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** `Policy.of("eu, eea ")` and `Policy.of(["EU", "EEA"])`
- **Expected:** identical policies, upper-cased, trimmed, deduplicated, sorted
- **Why:** a form produces one and an API produces the other; accepting only one
  means the rule silently does not apply for half the ways it can be set.

### SEC-024 · An empty or whitespace-only rule is unrestricted
- **Area:** `security/residency.py::Policy.of`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** `Policy.of("")`, `Policy.of(" , ")`, `Policy.of([])`
- **Expected:** unrestricted in all three
- **Why:** the fail-open direction, which is the right default here and must be
  the *only* way to reach it — a rule of `","` must not be mistaken for a rule.

### SEC-025 · Comparison is case- and whitespace-insensitive on both sides
- **Area:** `security/residency.py::Policy.decide`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `Policy.of("EU")`
- **Steps:** decide with destination `" eu "` and jurisdiction `"Eu"`
- **Expected:** permitted
- **Why:** a region string arriving from configuration with a stray space must
  not become a refusal nobody can explain.

### SEC-026 · Every decision carries the sentence an operator reads
- **Area:** `security/residency.py::Decision.describe`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** one decision of each verdict
- **Steps:** describe each
- **Expected:** four distinct sentences, each naming the subject, the
  destination and the rule
- **Why:** a bare refusal produces an outage nobody can diagnose, and the first
  hour goes to the network team.

### SEC-027 · `refusals` returns only what was blocked
- **Area:** `security/residency.py::refusals`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a mixed list of decisions
- **Steps:** filter
- **Expected:** only the two refused ones, in order
- **Why:** a residency report is about what was blocked; a list of everything is
  a list nobody reads.

### SEC-028 · A residency decision serialises with everything needed to argue
- **Area:** `security/residency.py::Decision.to_dict`
- **Type:** contract
- **Priority:** P3
- **Precondition:** a refusal
- **Steps:** serialise
- **Expected:** verdict, may_proceed, destination, rule, jurisdiction, subject,
  message
- **Why:** this is what an audit event and an API response carry, and a missing
  field turns a reviewable refusal into an opaque one.

### SEC-029 · A self-hosted or in-region exemption is expressed as a rule, not a bypass
- **Area:** `security/residency.py::Policy`
- **Type:** security
- **Priority:** P2
- **Precondition:** a deployment where the model runs inside the tenant's own
  region
- **Steps:** look for any code path that skips the gate because a destination is
  "internal" or "self-hosted"
- **Expected:** none — an exemption is a jurisdiction in the allowed list
- **Why:** a bypass predicate is how a policy engine ends up permitting
  everything, and it fails silently.

### SEC-030 · The policy describes itself in one line
- **Area:** `security/residency.py::Policy.describe`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** both rule shapes
- **Steps:** describe
- **Expected:** "no residency rule: data may go anywhere" or "data must stay in
  EU, EEA"
- **Why:** it is what `prama config show` and the tenant screen render, and it
  is the sentence a compliance officer checks against the obligation.

## Security — egress

### SEC-031 · Every registered egress point consults the gate
- **Area:** `security/egress.py::EGRESS_POINTS` · `tests/architecture/test_egress.py`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** for each of the seven points, parse the named module's source and
  require it to reach `Gate.require`
- **Expected:** all seven
- **Why:** finding T1 — the guard passed on *prose*, and `llm/providers` never
  consulted the gate at all. A policy engine nothing calls permits everything.

### SEC-032 · Deleting a `require` call turns its point red
- **Area:** `tests/architecture/test_egress.py`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a working tree
- **Steps:** remove the `gate.require(...)` call from
  `connect/sources/rest.py`, leaving every comment about it intact; run the
  guard
- **Expected:** `source-read` fails
- **Why:** the counterfactual the review performed. Against the old matcher it
  stayed green, which is the failure the guard exists to prevent, committed by
  the guard.

### SEC-033 · Each of the seven points is exercised end to end under a refusing policy
- **Area:** `security/egress.py::EGRESS_POINTS`
- **Type:** security
- **Priority:** P1
- **Precondition:** a tenant with residency `EU` and each destination set to
  `US`
- **Steps:** drive model inference, catalogue write-back, SIEM export, evidence
  export, secret fetch, source read and alert delivery
- **Expected:** `ResidencyRefused` from every one, naming its own egress point
- **Why:** the source scan proves the call exists; only this proves it refuses.

### SEC-034 · An unregistered egress name is refused at the gate
- **Area:** `security/egress.py::point`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `gate.require("siem_export", ...)` — underscore instead of hyphen
- **Expected:** `ValidationError` listing the known names
- **Why:** resolving the name is what stops a typo becoming an egress point that
  quietly checks nothing.

### SEC-035 · `decide` does not enforce and `require` does
- **Area:** `security/egress.py::Gate.decide` · `Gate.require`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a refusing policy
- **Steps:** call both
- **Expected:** `decide` returns a refused decision; `require` raises
- **Why:** a returned decision can be ignored, and the call site where somebody
  forgets is the one that matters. Both must exist and they must not be
  confused.

### SEC-036 · The refusal is its own exception type
- **Area:** `security/egress.py::ResidencyRefused`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a refusal
- **Steps:** catch it
- **Expected:** `ResidencyRefused`, code `RESIDENCY.REFUSED`, distinct from
  `ValidationError`
- **Why:** an operator triaging a failed export needs "the data may not go
  there" separate from "the request was malformed".

### SEC-037 · The refusal context names the egress, the tenant, the destination and the jurisdiction
- **Area:** `security/egress.py::Gate.require`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** an undeclared-jurisdiction refusal
- **Steps:** inspect `exc.context`
- **Expected:** all four, with `(undeclared)` rendered rather than an empty
  string
- **Why:** these four are what an audit event records, and an empty string in a
  log reads as a missing field rather than a missing declaration.

### SEC-038 · The registry describes what leaves and where the destination comes from
- **Area:** `security/egress.py::EgressPoint`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** for each point, assert `what`, `destination_from` and
  `jurisdiction_from` are non-empty and specific
- **Expected:** all seven complete
- **Why:** this registry is what a bank's security reviewer reads when asked
  "what leaves this system?" — it is a deliverable, not a comment.

### SEC-039 · Every point knows its subject's home, not only its destination
- **Area:** `security/egress.py::EgressPoint.jurisdiction_from`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** check each point's call site actually passes a jurisdiction
- **Expected:** every `require` passes a non-empty jurisdiction wherever one
  exists
- **Why:** the stated common defect — an egress that knows its destination and
  not its subject's home — and under a residency rule a missing jurisdiction is
  `UNDECLARED`, so getting it wrong blocks work rather than leaking, which is
  the safe direction and still a defect.

### SEC-040 · The Vault fetch passes its region as both destination and jurisdiction
- **Area:** `secrets/vault.py::VaultSecretProvider.resolve` · `EGRESS_POINTS["secret-fetch"]`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a gated Vault provider with region `US` under an `EU` rule
- **Steps:** resolve a reference
- **Expected:** refused, and the reasoning — that a credential belongs wherever
  its store is and there is no separate subject — is what the registry says
- **Why:** it is the one point where the two arguments are deliberately the same
  value, which reads like a bug unless it is pinned as a decision.

### SEC-041 · A new module performing a network write without a registry entry is a build failure
- **Area:** `security/egress.py::EGRESS_POINTS` · `tests/architecture/test_egress.py`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a scratch module that posts to an HTTP endpoint
- **Steps:** add it; run the architecture suite
- **Expected:** a failure telling the author to register it
- **Why:** "egress points are enumerated, not discovered at the call site" is
  only true if adding one unenumerated fails.

### SEC-042 · A gate built for a tenant carries the tenant into the refusal
- **Area:** `security/egress.py::Gate.for_tenant`
- **Type:** functional
- **Priority:** P3
- **Precondition:** `Gate.for_tenant("EU", tenant_id="01ACME")`
- **Steps:** trigger a refusal
- **Expected:** the tenant id in the context
- **Why:** in a multi-tenant estate, a refusal that does not say whose data it
  was is not actionable.

### SEC-043 · The subject defaults to the egress point's own name
- **Area:** `security/egress.py::Gate.decide`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a refusal raised without a `subject`
- **Steps:** read the message
- **Expected:** the point's name rather than "this data"
- **Why:** a generic subject in a refusal makes every refusal in the log look
  the same.

### SEC-044 · An egress refusal is audited
- **Area:** `security/egress.py::Gate.require` · the audit trail
- **Type:** security
- **Priority:** P2
- **Precondition:** a refused export
- **Steps:** look for an audit event
- **Expected:** an event recording the attempted movement, its destination and
  the refusal
- **Why:** a blocked exfiltration attempt that leaves no record is a control
  that worked and cannot be shown to have worked.

## Security — customer-managed keys

### SEC-045 · Encrypt then decrypt returns the plaintext
- **Area:** `security/cmk.py::encrypt` · `decrypt`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the `sso` extra installed; a `LocalTestKeyProvider`
- **Steps:** round-trip a payload
- **Expected:** identical bytes
- **Why:** the base case; everything else is a refusal.

### SEC-046 · The data key is fresh for every encryption
- **Area:** `security/cmk.py::encrypt`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** encrypt the same plaintext twice under one provider; compare
  ciphertexts, nonces and wrapped keys
- **Expected:** all three differ
- **Why:** a data key reused across payloads makes the envelope a single point
  of compromise, and an identical ciphertext for identical plaintext leaks
  equality.

### SEC-047 · The nonce is 96 bits, generated here, and never supplied
- **Area:** `security/cmk.py::NONCE_BYTES` · `encrypt`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** inspect the signature for any nonce parameter; check the length
- **Expected:** no parameter; 12 bytes
- **Why:** reusing a nonce under one key in GCM leaks the XOR of the plaintexts
  and permits forgery. A caller that could supply one would eventually reuse
  one.

### SEC-048 · The data key is AES-256 and the length is not configurable
- **Area:** `security/cmk.py::DATA_KEY_BYTES`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** check the constant and that nothing reads a key length from
  configuration
- **Expected:** 32, with no knob
- **Why:** a key length knob is how AES-128 arrives in production because
  somebody changed a default years ago.

### SEC-049 · A ciphertext moved between tenants fails to decrypt
- **Area:** `security/cmk.py::decrypt`
- **Type:** security
- **Priority:** P1
- **Precondition:** an envelope sealed for tenant A
- **Steps:** `decrypt(envelope, provider=p, tenant_id="B")` — the whole
  serialised envelope copied into B's row, context and all
- **Expected:** `KeyRevoked` naming the estate mismatch, raised **before** the
  provider is asked to unwrap
- **Why:** finding S6. The AAD binds ciphertext to context, but the context
  travels inside the envelope, so rebuilding the AAD from the envelope verified
  the envelope against itself. The pair moving together is the attack the
  module's own sentence describes.

### SEC-050 · A caller that names no tenant gets no cross-tenant protection, visibly
- **Area:** `security/cmk.py::decrypt`
- **Type:** security
- **Priority:** P1
- **Precondition:** the same moved envelope
- **Steps:** `decrypt(envelope, provider=p)` with `tenant_id=None`
- **Expected:** it decrypts — and every call site in the product is enumerated
  and shown to pass a tenant
- **Why:** the parameter is optional, so the guarantee is only as good as the
  callers. A call site that cannot name the tenant is the hole S6 left open on
  purpose, and it needs to be a short, reviewed list.

### SEC-051 · A purpose mismatch is refused
- **Area:** `security/cmk.py::decrypt`
- **Type:** security
- **Priority:** P1
- **Precondition:** an envelope sealed with purpose `samples`
- **Steps:** decrypt with `purpose="evidence"`
- **Expected:** `KeyRevoked` naming the purpose, before unwrapping
- **Why:** a key scoped to one purpose must not open another's data, and the
  purpose is the only thing separating two stores under one tenant.

### SEC-052 · Editing the stored context breaks decryption
- **Area:** `security/cmk.py::_aad` · `decrypt`
- **Type:** security
- **Priority:** P1
- **Precondition:** a serialised envelope
- **Steps:** change `context.tenant` in the stored JSON and decrypt as that
  tenant
- **Expected:** failure — the AAD no longer matches what was sealed
- **Why:** storing the tenant alongside rather than authenticating it would let
  a moved ciphertext decrypt cleanly into the wrong tenant, which is the failure
  that looks like nothing at all.

### SEC-053 · A tampered ciphertext is refused
- **Area:** `security/cmk.py::decrypt`
- **Type:** security
- **Priority:** P1
- **Precondition:** an envelope
- **Steps:** flip one bit of the ciphertext; decrypt
- **Expected:** `KeyRevoked` with the message about the envelope not decrypting
  under its own data key
- **Why:** GCM's authentication is the point of choosing it; a mode without it
  would return plausible garbage.

### SEC-054 · A tampered wrapped key is refused
- **Area:** `security/cmk.py::LocalTestKeyProvider.unwrap`
- **Type:** security
- **Priority:** P1
- **Precondition:** an envelope
- **Steps:** flip one bit of `wrapped_key`; decrypt
- **Expected:** `KeyRevoked`, with the remedy distinguishing a rotated key from
  a wrong tenant
- **Why:** the unwrap failure is the one an operator will see most often and the
  one most likely to be misread as a bug.

### SEC-055 · A wrong customer key cannot unwrap
- **Area:** `security/cmk.py::decrypt`
- **Type:** security
- **Priority:** P1
- **Precondition:** two providers with different keys
- **Steps:** encrypt with one, decrypt with the other
- **Expected:** `KeyRevoked`
- **Why:** the arrangement's whole claim is that Prama cannot read without the
  customer's key.

### SEC-056 · A revoked key makes every envelope it wrapped unreadable
- **Area:** `security/cmk.py::LocalTestKeyProvider.revoke`
- **Type:** security
- **Priority:** P1
- **Precondition:** three envelopes under one key
- **Steps:** revoke; attempt all three
- **Expected:** `KeyRevoked` on each, with the remedy saying this is usually not
  a fault
- **Why:** "we can take the key away and you cannot read it any more" is the
  product. An operator reading "decryption failed" opens a ticket about a bug
  that does not exist.

### SEC-057 · A revoked key cannot wrap either
- **Area:** `security/cmk.py::LocalTestKeyProvider.wrap`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a revoked provider
- **Steps:** encrypt
- **Expected:** `KeyRevoked` with "provision a new key"
- **Why:** continuing to write envelopes nothing can ever open is worse than
  failing the write.

### SEC-058 · Revocation is irreversible and not selective, and the product says so
- **Area:** `security/cmk.py` module docstring
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** find where a customer is told, before revoking, that every backup
  of that data becomes unreadable including the ones taken for their own
  recovery obligations
- **Expected:** the sentence appears wherever revocation is offered, not only in
  the module docstring
- **Why:** it is the cost of the property being sold, and it is discovered
  rather than stated in most implementations.

### SEC-059 · The key id travels with the envelope so a rotated key can still unwrap
- **Area:** `security/cmk.py::Envelope.key_id`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a provider rotated to a new key id, keeping the old key
  available
- **Steps:** decrypt an envelope written under the old id
- **Expected:** it opens, and the provider is selected by the envelope's
  `key_id`
- **Why:** without it, rotation means re-encrypting everything at once — which
  in practice means never rotating.

### SEC-060 · A null byte in the encryption context is refused
- **Area:** `security/cmk.py::_aad`
- **Type:** security
- **Priority:** P2
- **Precondition:** a tenant id containing `"\x00"`
- **Steps:** encrypt
- **Expected:** `PramaError` with code `CMK.BAD_CONTEXT`
- **Why:** the delimiter is a null byte, so a value containing one could forge a
  second field and make two different contexts produce the same AAD.

### SEC-061 · The AAD is canonical across context orderings
- **Area:** `security/cmk.py::_aad`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two dicts with the same pairs inserted in opposite orders
- **Steps:** compare `_aad` output
- **Expected:** identical bytes
- **Why:** an AAD that depended on dict order would fail to decrypt on a
  different Python version, and the message would say the key was revoked.

### SEC-062 · An envelope with no tenant is refused at encryption
- **Area:** `security/cmk.py::encrypt`
- **Type:** negative
- **Priority:** P1
- **Precondition:** none
- **Steps:** `encrypt(b"x", provider=p, tenant_id="", purpose="samples")`
- **Expected:** `PramaError` code `CMK.NO_TENANT`
- **Why:** without it the AAD binds nothing and a moved envelope decrypts
  cleanly into the wrong estate.

### SEC-063 · Without the `sso` extra, CMK refuses by name rather than falling back
- **Area:** `security/cmk.py::_aesgcm` · `CmkUnavailable`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `cryptography` not importable
- **Steps:** encrypt
- **Expected:** `CmkUnavailable`, code `CMK.UNAVAILABLE`, with the install
  command — and nothing weaker attempted
- **Why:** a deployment that cannot do AES-GCM must not do envelope encryption
  badly.

### SEC-064 · An envelope round-trips through its serialised form
- **Area:** `security/cmk.py::Envelope.to_dict` · `from_dict`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an envelope
- **Steps:** serialise, deserialise, decrypt
- **Expected:** the plaintext, with base64 of every binary field and the context
  preserved exactly
- **Why:** the envelope is stored as JSON in a column, and a base64 padding bug
  presents as a revoked key.

### SEC-065 · No cloud KMS is claimed to have been exercised
- **Area:** `security/cmk.py::KeyProvider`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** check every place CMK is described to a buyer
- **Expected:** "no cloud KMS has been exercised" survives the trip from the
  docstring to the documentation
- **Why:** the module is honest about it; a datasheet that is not would be
  selling something untested.

### SEC-066 · `LocalTestKeyProvider` is named so it cannot be deployed by accident
- **Area:** `security/cmk.py::LocalTestKeyProvider`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** grep configuration and factories for a way to select it
- **Expected:** no configuration path selects it
- **Why:** a customer-managed key held by Prama is not a customer-managed key,
  and a class called `LocalKeyProvider` ends up in somebody's deployment.

## Security — OIDC

### SEC-067 · A well-formed RS256 token verifies and yields its claims
- **Area:** `security/oidc.py::verify_id_token`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an RSA key pair, a token with sub, iss, aud, exp, iat, email
  and groups
- **Steps:** verify
- **Expected:** `IdentityClaims` with every field mapped
- **Why:** the happy path, and the control the refusals are measured against.

### SEC-068 · An ES256 token verifies, with the r||s to DER conversion
- **Area:** `security/oidc.py::_ecdsa_der`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a P-256 key pair
- **Steps:** verify a genuine ES256 token, including one whose r or s has a
  leading zero byte
- **Expected:** verified in both cases
- **Why:** JOSE gives fixed-width r||s and `cryptography` wants DER; a
  half-length split on a short r is a signature that fails for one token in 256.

### SEC-069 · `alg: none` is refused
- **Area:** `security/oidc.py::verify_id_token`
- **Type:** security
- **Priority:** P1
- **Precondition:** a token with header `{"alg":"none"}` and an empty signature
- **Steps:** verify
- **Expected:** `InvalidToken` naming the algorithm, before any claim is read
- **Why:** the canonical JWT attack, and a verifier that dispatches on the
  token's own `alg` will happily verify nothing.

### SEC-070 · HS256 signed with the provider's public key is refused
- **Area:** `security/oidc.py::ACCEPTED_ALGORITHMS`
- **Type:** security
- **Priority:** P1
- **Precondition:** the provider's RSA public key in PEM as the HMAC key
- **Steps:** forge a token, verify
- **Expected:** `InvalidToken`, with the remedy explaining that symmetric
  algorithms are forgeable by anyone holding a public key
- **Why:** algorithm confusion — the attack that makes an asymmetric-only
  accepted set mandatory rather than tidy.

### SEC-071 · The accepted set is fixed by the deployment, not read from the token
- **Area:** `security/oidc.py::verify_id_token`
- **Type:** contract
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the code; then verify with
  `accepted_algorithms=frozenset({"RS256"})` and an ES256 token
- **Expected:** refused; the token's own `alg` is only ever compared, never
  dispatched on
- **Why:** dispatching on the token's `alg` is the vulnerability; comparing it
  to a fixed set is the fix.

### SEC-072 · An unknown `kid` is refused rather than tried against every key
- **Area:** `security/oidc.py::KeySet.signing_key`
- **Type:** security
- **Priority:** P1
- **Precondition:** a key set of three keys, a token naming a fourth
- **Steps:** verify
- **Expected:** `InvalidToken` naming the kid, with the remedy about rotation
- **Why:** trying every key until one works turns a key the provider rotated out
  — and may have published the private half of — into a valid signer forever.

### SEC-073 · A token with no `kid` against several keys is refused
- **Area:** `security/oidc.py::KeySet.signing_key`
- **Type:** security
- **Priority:** P1
- **Precondition:** a key set of two keys, a token with no `kid`
- **Steps:** verify
- **Expected:** `InvalidToken`, "guessing is not verification"
- **Why:** the single-key convenience must not extend to a set where guessing is
  possible.

### SEC-074 · A token with no `kid` against exactly one key is accepted
- **Area:** `security/oidc.py::KeySet.signing_key`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a one-key set
- **Steps:** verify a genuine token with no `kid`
- **Expected:** verified
- **Why:** several small providers do not emit `kid`, and refusing would make
  them unusable for no security gain.

### SEC-075 · An empty key set verifies nothing
- **Area:** `security/oidc.py::KeySet.signing_key`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `KeySet()`
- **Steps:** verify any token
- **Expected:** `InvalidToken`, "the provider's key set is empty"
- **Why:** a JWKS fetch that failed and returned nothing must not become a
  verifier that accepts everything or one that crashes.

### SEC-076 · A key marked for encryption is not a signing key
- **Area:** `security/oidc.py::KeySet.from_jwks`
- **Type:** security
- **Priority:** P2
- **Precondition:** a JWKS with one `use: "enc"` key and one `use: "sig"` key
- **Steps:** build the set
- **Expected:** only the signing key
- **Why:** accepting an encryption key lets a key the provider never signs with
  verify a token.

### SEC-077 · A swapped payload fails the signature
- **Area:** `security/oidc.py::verify_id_token`
- **Type:** security
- **Priority:** P1
- **Precondition:** two genuine tokens from the same provider
- **Steps:** splice token A's header and signature onto token B's payload
- **Expected:** `InvalidToken` on the signature, before any claim is read
- **Why:** the signing input is `header.payload`, and this is the case that
  proves the payload is inside it.

### SEC-078 · Claims are parsed only after the signature verifies
- **Area:** `security/oidc.py::verify_id_token`
- **Type:** security
- **Priority:** P1
- **Precondition:** a token whose payload is not JSON and whose signature is
  wrong
- **Steps:** verify
- **Expected:** the signature failure, not the payload failure
- **Why:** a verifier that parses first has already made decisions — which key,
  which issuer, which tenant — on attacker-controlled data. The error the caller
  sees is the evidence of the ordering.

### SEC-079 · A token from another issuer is refused, however genuine
- **Area:** `security/oidc.py::_check_claims`
- **Type:** security
- **Priority:** P1
- **Precondition:** a correctly signed token with a different `iss`
- **Steps:** verify
- **Expected:** `InvalidToken` naming the expected issuer
- **Why:** a genuinely signed token from another issuer is still not one of
  ours, and this is where a multi-tenant IdP becomes a cross-tenant hole.

### SEC-080 · A token for another client of the same provider is refused
- **Area:** `security/oidc.py::_check_claims`
- **Type:** security
- **Priority:** P1
- **Precondition:** a token whose `aud` is another application
- **Steps:** verify
- **Expected:** `InvalidToken` — genuinely signed, genuinely current, and not
  for us
- **Why:** audience drift is the most common real-world SSO defect, because the
  token verifies against the signature perfectly.

### SEC-081 · An array audience containing ours is accepted
- **Area:** `security/oidc.py::_audiences`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `aud: ["other", "prama"]`
- **Steps:** verify with `audience="prama"`
- **Expected:** accepted
- **Why:** both the string and array forms are legal, and accepting only one
  makes half the providers unusable.

### SEC-082 · An expired token is refused, with one minute of tolerance and no more
- **Area:** `security/oidc.py::MAX_CLOCK_SKEW_SECONDS`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a token with `exp = now - 30` and another with
  `exp = now - 61`
- **Steps:** verify both
- **Expected:** accepted, then refused
- **Why:** zero tolerance rejects valid tokens during the seconds either side of
  expiry; generous tolerance extends every stolen token's life.

### SEC-083 · A token issued in the future is refused
- **Area:** `security/oidc.py::_check_claims`
- **Type:** security
- **Priority:** P2
- **Precondition:** `iat = now + 3600`
- **Steps:** verify
- **Expected:** `InvalidToken` about the clocks
- **Why:** accepting it extends the token's usable life by however far ahead it
  claims to have been issued.

### SEC-084 · A not-yet-valid token is refused
- **Area:** `security/oidc.py::_check_claims`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `nbf = now + 300`
- **Steps:** verify
- **Expected:** `InvalidToken`
- **Why:** `nbf` is optional and honoured when present; ignoring it makes a
  deliberately delayed token immediately usable.

### SEC-085 · A missing required claim is named
- **Area:** `security/oidc.py::_check_claims`
- **Type:** negative
- **Priority:** P2
- **Precondition:** four tokens, each missing one of sub, iss, aud, exp
- **Steps:** verify each
- **Expected:** `InvalidToken` naming the missing claim
- **Why:** "a token without it cannot be checked" is a configuration
  conversation with the IdP team, and the claim name is what starts it.

### SEC-086 · An empty subject is refused
- **Area:** `security/oidc.py::_check_claims`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `sub: ""`
- **Steps:** verify
- **Expected:** `InvalidToken` — an empty subject identifies nobody
- **Why:** an empty string as a principal key collapses every such sign-in onto
  one account.

### SEC-087 · A replayed token without this session's nonce is refused
- **Area:** `security/oidc.py::_check_claims`
- **Type:** security
- **Priority:** P1
- **Precondition:** a token carrying another session's nonce
- **Steps:** verify with the expected nonce
- **Expected:** `InvalidToken` about replay, compared in constant time
- **Why:** the nonce is the only replay protection, and the comparison is the
  one place a timing leak would matter.

### SEC-088 · Nonces are unpredictable
- **Area:** `security/oidc.py::new_nonce`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** read the implementation; generate 1,000 and check for uniqueness
  and length
- **Expected:** `secrets.token_urlsafe(32)`, all distinct
- **Why:** a predictable nonce is no protection against replay, which is the
  only thing a nonce is for.

### SEC-089 · A malformed token is refused before anything else
- **Area:** `security/oidc.py::verify_id_token` · `_b64url`
- **Type:** negative
- **Priority:** P2
- **Precondition:** four inputs: two segments, four segments, a segment that is
  not base64url, an empty string
- **Steps:** verify each
- **Expected:** `InvalidToken` in all four, no traceback
- **Why:** the first thing a fuzzer sends, and the first thing a misconfigured
  client sends.

### SEC-090 · Base64url decoding does not discard rubbish silently
- **Area:** `security/oidc.py::_b64url`
- **Type:** security
- **Priority:** P2
- **Precondition:** a payload segment with `!!` spliced into the middle
- **Steps:** verify
- **Expected:** refused
- **Why:** without strict validation, characters outside the alphabet are
  dropped and the segment decodes to something plausible instead of being
  rejected. The docstring claims `validate=True` matters — the call as written
  passes no `validate` argument, so this case is testing whether the comment
  and the code agree.

### SEC-091 · An unsupported curve or key type is refused by name
- **Area:** `security/oidc.py::JsonWebKey.public_key`
- **Type:** negative
- **Priority:** P3
- **Precondition:** a JWKS with a P-521 EC key and one with `kty: "oct"`
- **Steps:** verify against each
- **Expected:** `InvalidToken` naming the curve or the key type
- **Why:** "unsupported" and "invalid" are different conversations with the IdP
  team.

### SEC-092 · The failure reason reaches the operator and not the browser
- **Area:** `security/oidc.py::InvalidToken`
- **Type:** security
- **Priority:** P1
- **Precondition:** any refusal
- **Steps:** drive a failed sign-in through the console
- **Expected:** a generic failure to the browser; the specific reason in the log
- **Why:** which check failed is useful to an operator and useful to an attacker
  for the same reason, and the module says so.

### SEC-093 · A subject is keyed on issuer and subject together
- **Area:** `security/oidc.py::subject_digest`
- **Type:** security
- **Priority:** P1
- **Precondition:** two providers whose `sub` values collide
- **Steps:** compute both digests
- **Expected:** different
- **Why:** a subject is unique within its issuer and nowhere else; keying on
  subject alone merges two people into one account.

### SEC-094 · An unmapped IdP group grants nothing and is reported
- **Area:** `security/oidc.py::ClaimMapping.roles_for` · `unmapped`
- **Type:** security
- **Priority:** P1
- **Precondition:** a token with groups `["owners", "cafeteria"]` and a mapping
  covering only `owners`
- **Steps:** map
- **Expected:** roles `("owner",)`; unmapped `("cafeteria",)` reported
- **Why:** silently defaulting is how everybody in the directory becomes an
  owner; silently ignoring is how somebody signs in and can see nothing, which
  looks exactly like a permissions bug.

### SEC-095 · Groups arriving as a string, as `roles`, or absent are all handled
- **Area:** `security/oidc.py::verify_id_token`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** three tokens: `groups: "owners"`, `roles: ["owners"]`, and
  neither
- **Steps:** verify each
- **Expected:** `("owners",)`, `("owners",)`, `()`
- **Why:** every provider spells this differently, and a product that assumed
  one spelling needs a fork per customer.

### SEC-096 · Without the `sso` extra, SSO refuses by name
- **Area:** `security/oidc.py::_require_crypto` · `SsoUnavailable`
- **Type:** negative
- **Priority:** P1
- **Precondition:** `cryptography` not importable
- **Steps:** verify any token
- **Expected:** `SsoUnavailable`, code `SSO.UNAVAILABLE`, with the install
  command
- **Why:** a deployment that cannot verify signatures must refuse to do SSO, not
  do it weakly.

### SEC-097 · The verifier fetches nothing
- **Area:** `security/oidc.py`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** scan the module for any network call or HTTP client import
- **Expected:** none; the key set is passed in
- **Why:** fetching JWKS is an egress and a caching problem, and mixing either
  into a verifier makes it untestable offline — which is where these cases run.

## Security — SCIM provisioning

### SEC-098 · A new directory user becomes a create
- **Area:** `security/scim.py::reconcile`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an active SCIM user Prama does not hold
- **Steps:** reconcile against `None`
- **Expected:** `Change.CREATE` with the mapped roles and a stated reason
- **Why:** the base case of provisioning.

### SEC-099 · A leaver Prama has never held creates nothing
- **Area:** `security/scim.py::reconcile`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an inactive SCIM user with no account
- **Steps:** reconcile
- **Expected:** `Change.NONE` with the reason, not a deactivated account
- **Why:** creating a deactivated account puts somebody in the estate who was
  never in it, and they then appear in every principal list forever.

### SEC-100 · A delete deactivates and never deletes
- **Area:** `security/scim.py::reconcile`
- **Type:** security
- **Priority:** P1
- **Precondition:** an active account whose directory user is now inactive
- **Steps:** reconcile
- **Expected:** `Change.DEACTIVATE`, the account retained, the reason naming the
  attestations that refer to them
- **Why:** deleting leaves an attestation signed by a principal that does not
  exist — a hole in the audit trail dressed as a tidy-up.

### SEC-101 · The last active administrator cannot be deprovisioned
- **Area:** `security/scim.py::reconcile`
- **Type:** security
- **Priority:** P1
- **Precondition:** an admin account with `other_active_admins == 0`, directory
  says inactive
- **Steps:** reconcile
- **Expected:** `Change.REFUSED` with the lockout reason
- **Why:** a directory misconfiguration that deactivates every admin locks
  everybody out of the tenant with no way back that does not involve the
  database.

### SEC-102 · A batch deactivating three of four admins refuses on the fourth
- **Area:** `security/scim.py::reconcile_all`
- **Type:** security
- **Priority:** P1
- **Precondition:** four active admins, all four sent inactive
- **Steps:** `reconcile_all`
- **Expected:** three deactivations and one refusal — and the refusal is on the
  one that would leave none, not on the first one reached
- **Why:** the admin pool is recomputed as the batch proceeds; without that, a
  sync either refuses everything or deactivates everybody.

### SEC-103 · Roles are replaced, never unioned
- **Area:** `security/scim.py::reconcile`
- **Type:** security
- **Priority:** P1
- **Precondition:** an account holding `("owner", "steward")`, directory groups
  now mapping to `("steward",)`
- **Steps:** reconcile
- **Expected:** `Change.UPDATE` with roles exactly `("steward",)` and a
  `roles` field change recorded
- **Why:** a union means a role granted once is granted forever, and the group
  somebody was removed from six months ago still confers it.

### SEC-104 · An omitted field in a partial update does not blank the stored one
- **Area:** `security/scim.py::_differences`
- **Type:** negative
- **Priority:** P1
- **Precondition:** an account with an email; a SCIM PATCH omitting `emails`
- **Steps:** reconcile
- **Expected:** no change to the email
- **Why:** SCIM PATCH omits what it is not changing, and treating omission as
  deletion wipes an email address on every sync.

### SEC-105 · A user with no external id is refused
- **Area:** `security/scim.py::reconcile`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a SCIM user with neither `externalId` nor `id`
- **Steps:** reconcile
- **Expected:** `Change.REFUSED` explaining that a create would make a duplicate
  on every sync
- **Why:** without a stable key, every sync creates another account and the
  estate fills with copies of one person.

### SEC-106 · Reactivation is distinguished from creation
- **Area:** `security/scim.py::reconcile`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a deactivated account, directory says active
- **Steps:** reconcile
- **Expected:** `Change.REACTIVATE` with the freshly mapped roles
- **Why:** a returning employee keeps the identity their attestations name.

### SEC-107 · Agreement is reported as agreement
- **Area:** `security/scim.py::reconcile`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an account matching the directory exactly, roles included
- **Steps:** reconcile
- **Expected:** `Change.NONE`, `applies` false
- **Why:** a sync that reports a change every night is a sync nobody reads, and
  a `NONE` that applied something would rewrite the estate nightly.

### SEC-108 · `REFUSED` is distinct from `NONE`
- **Area:** `security/scim.py::Change.alters_anything`
- **Type:** contract
- **Priority:** P2
- **Precondition:** both decisions
- **Steps:** compare
- **Expected:** neither applies, and only one is a finding
- **Why:** "nothing changed" and "something should have changed and was refused"
  need different handling by the caller and different lines in the report.

### SEC-109 · A SCIM resource is parsed in every shape the specification allows
- **Area:** `security/scim.py::ScimUser.from_resource`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** resources with groups as objects with `display`, as objects
  with only `value`, and as bare strings; emails with and without `primary`; a
  name as `name.formatted` and as `displayName`
- **Steps:** parse each
- **Expected:** the documented field in each case; the primary email preferred
- **Why:** every IdP emits a different subset, and a parse that assumed one
  shape drops group membership silently — which reads as a permissions bug.

### SEC-110 · `active` defaults to true when absent, and that is called out
- **Area:** `security/scim.py::ScimUser.from_resource`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a resource with no `active` key
- **Steps:** parse
- **Expected:** active, with the docstring's warning that a PATCH omitting it is
  not a request to activate anybody
- **Why:** the specification's default and the product's risk point in opposite
  directions, and the note is the only thing holding them apart.

### SEC-111 · The decision names the fields it would change
- **Area:** `security/scim.py::Decision.describe`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** an update touching two fields and the role set
- **Steps:** describe
- **Expected:** each field, old value to new
- **Why:** an audit record saying "3 fields changed" answers nothing.

### SEC-112 · There are no SCIM routes, and the product says so
- **Area:** `security/scim.py` module docstring · `docs/19`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** search for an HTTP endpoint speaking SCIM's wire format
- **Expected:** none, and every place SCIM is described says the routes are not
  written
- **Why:** SOC 2 CC6.2 is marked partial specifically because SCIM would close
  it; claiming it closed today would be the overstatement an auditor looks for.

## Security — SIEM export

### SEC-113 · ECS output is one JSON object per line with ECS field names
- **Area:** `security/siem.py::to_ecs`
- **Type:** contract
- **Priority:** P1
- **Precondition:** three audit events
- **Steps:** render
- **Expected:** three lines, each parsing, each carrying `@timestamp`,
  `event.action`, `event.outcome`, `user.id`, `source.ip`, `trace.id`
- **Why:** a field a SIEM has to be taught about is a field nobody filters on.

### SEC-114 · CEF output escapes what would end a field
- **Area:** `security/siem.py::_escape_extension` · `_escape_header`
- **Type:** security
- **Priority:** P1
- **Precondition:** an event whose object id contains `=`, `|`, `\`, a newline
  and a carriage return
- **Steps:** render to CEF
- **Expected:** one line; every special character escaped; the line parses back
  to the original values
- **Why:** an unescaped one silently truncates the record or merges it with the
  next, producing a log line that parses and means something else — which is
  worse than a line that fails to parse.

### SEC-115 · A pipe in a header field is escaped
- **Area:** `security/siem.py::_escape_header`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an action containing `|`
- **Steps:** render
- **Expected:** escaped, and the header still has exactly seven fields
- **Why:** the header and the extension have different escaping rules, and
  applying one to the other is the usual mistake.

### SEC-116 · Severity is derived, not uniform
- **Area:** `security/siem.py::severity_of`
- **Type:** functional
- **Priority:** P1
- **Precondition:** denied, failure and success outcomes
- **Steps:** compute
- **Expected:** 8, 6, 2
- **Why:** a feed where everything is severity 5 gets a suppression rule within
  a week, which is the same as having no feed.

### SEC-117 · An elevated action outranks its own outcome
- **Area:** `security/siem.py::_ELEVATED`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `role.grant` with outcome `success`, and `report.read` with
  outcome `failure`
- **Steps:** compute both
- **Expected:** 7 and 6 — the successful grant outranks the failed read
- **Why:** a successful grant of an admin role is a security event whatever its
  outcome field says, and ranking it below a failed page load buries the line a
  reviewer is looking for.

### SEC-118 · `evidence.erase` is the loudest action in the table
- **Area:** `security/siem.py::_ELEVATED`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare its severity with the others
- **Expected:** 8, equal to a denial and above every other action
- **Why:** erasing evidence is the single most consequential thing this product
  can be told to do.

### SEC-119 · An unknown outcome does not crash and does not rank high
- **Area:** `security/siem.py::severity_of`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** outcome `"partial"`
- **Steps:** compute
- **Expected:** 2, the default
- **Why:** an unrecognised outcome silently becoming a 10 would flood a SIEM;
  becoming an exception would stop the export.

### SEC-120 · Only allow-listed detail keys are exported
- **Area:** `security/siem.py::_detail` · `EXPORTABLE_DETAIL`
- **Type:** security
- **Priority:** P1
- **Precondition:** a detail dict containing `dataset` and `password`
- **Steps:** render in both formats
- **Expected:** `dataset` present, `password` absent, `dropped_detail_keys == 1`
- **Why:** `detail_json` is free-form and written by call sites all over the
  product; shipping it whole to a system with different access controls is how a
  secret reaches a log aggregator.

### SEC-121 · The number of dropped keys is reported, not silently swallowed
- **Area:** `security/siem.py::Exported.describe`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** events with several non-exportable keys
- **Steps:** describe
- **Expected:** the count, and the sentence saying this is not the same as there
  having been none
- **Why:** an empty detail read as "there was none" is how somebody concludes
  the product records nothing useful.

### SEC-122 · A non-dict detail is handled
- **Area:** `security/siem.py::_detail`
- **Type:** negative
- **Priority:** P3
- **Precondition:** `detail_json` holding a string, a list and `None`
- **Steps:** render
- **Expected:** empty detail, zero dropped, no exception
- **Why:** `detail_json` is a text column and anything can be in it.

### SEC-123 · CEF carries at most six custom strings and drops the rest deterministically
- **Area:** `security/siem.py::to_cef`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a detail with eight exportable keys
- **Steps:** render
- **Expected:** `cs1`..`cs6` filled, the extra keys omitted, and the choice made
  in sorted order so two runs agree
- **Why:** CEF defines only six; a seventh silently overwriting `cs1` would
  relabel the tenant field, which is worse than dropping it. The loop reserves
  `cs1`..`cs4` and then starts at index 5, so only two detail keys ever survive
   — the case pins whether that is intended.

### SEC-124 · The export is gated before it is rendered
- **Area:** `security/siem.py::render`
- **Type:** security
- **Priority:** P1
- **Precondition:** an `EU` tenant and a `US` collector
- **Steps:** render with the gate
- **Expected:** `ResidencyRefused`; nothing rendered
- **Why:** this is the last point that knows these are this tenant's audit
  events; a transport handed a finished string has nothing left to decide with.

### SEC-125 · A refused export is refused wholesale
- **Area:** `security/siem.py::render`
- **Type:** security
- **Priority:** P1
- **Precondition:** events spanning two jurisdictions
- **Steps:** render under a rule permitting one
- **Expected:** no output at all
- **Why:** an audit export missing the records that were not allowed to cross is
  an audit export with a hole in it, and nothing in the file says so.

### SEC-126 · An unknown format is refused with the list of known ones
- **Area:** `security/siem.py::render`
- **Type:** negative
- **Priority:** P3
- **Precondition:** `fmt="leef"`
- **Steps:** render
- **Expected:** `ValidationError` naming `cef` and `ecs`
- **Why:** the remedy is the whole message; a bare KeyError is a traceback.

### SEC-127 · An empty event stream renders empty, not a blank line
- **Area:** `security/siem.py::Exported.text`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** no events
- **Steps:** render and take `text()`
- **Expected:** the empty string, not `"\n"`
- **Why:** a blank line in a JSON Lines feed is a parse error at the collector.

### SEC-128 · Timestamps render as ISO-8601 whether they arrive as datetimes or strings
- **Area:** `security/siem.py::to_ecs` · `to_cef`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** events with `occurred_at` as an aware datetime and as a
  string
- **Steps:** render
- **Expected:** the same textual form in both
- **Why:** a SIEM that cannot parse the timestamp indexes every event at
  ingestion time, which destroys the correlation the export exists for.

## Security — SOC 2 readiness

### SEC-129 · Every criterion names a mechanism or is honestly marked a gap
- **Area:** `security/soc2.py::CRITERIA`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** for each criterion, require a mechanism unless the readiness is
  `GAP` or `ORGANISATIONAL`, and require an evidence request in every case
- **Expected:** all ten complete
- **Why:** a gap without an evidence request is a red cell rather than a piece
  of work.

### SEC-130 · The readout leads with the gaps
- **Area:** `security/soc2.py::Readout.describe`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** the shipped criteria
- **Steps:** describe
- **Expected:** the gap count and identities first
- **Why:** a readiness matrix leading with what is covered is one whose gaps are
  read last or not at all.

### SEC-131 · Organisational criteria are not counted as gaps
- **Area:** `security/soc2.py::Readout.gaps`
- **Type:** functional
- **Priority:** P3
- **Precondition:** A1.2 is organisational
- **Steps:** read `gaps`
- **Expected:** A1.2 absent; it appears under `organisational`
- **Why:** they are somebody else's control, and mixing them in makes the
  product look worse and the list less actionable.

### SEC-132 · The caveat that readiness is not compliance survives serialisation
- **Area:** `security/soc2.py::Readout.to_dict`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** none
- **Steps:** serialise; and render `prama pack soc2`
- **Expected:** the Type II caveat present in both
- **Why:** this module's output is the thing most likely to be pasted into a
  buyer's questionnaire, and the caveat is what stops it misleading them.

### SEC-133 · Each criterion's mechanism still exists in the product
- **Area:** `security/soc2.py::CRITERIA`
- **Type:** regression
- **Priority:** P1
- **Precondition:** none
- **Steps:** for every mechanism naming a command, a module or a test, confirm
  it exists — `prama principal create`, `prama bundle seal`, the residency
  policy, the cross-tenant isolation suite, the evidence ledger
- **Expected:** all present
- **Why:** round-1 finding Q-07 was a remedy naming a command that did not
  exist. This is the same failure in the document an auditor reads.

### SEC-134 · CC6.6 is not upgraded while CMK is unexercised
- **Area:** `security/soc2.py::CRITERIA` (CC6.6) · `security/cmk.py`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** compare the criterion's note against the state of `security/cmk.py`
- **Expected:** the note reflects reality — the envelope logic exists and no
  cloud KMS has been exercised
- **Why:** the note currently says customer-managed keys "are not built", and
  the module is built and untested against a real KMS. Both readings are
  defensible and they are not the same sentence; the mismatch is a documentation
  defect either way.

### SEC-135 · CC6.8 stays partial until the container image is signed
- **Area:** `security/soc2.py::CRITERIA` (CC6.8)
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** confirm no image signing exists and the criterion is still partial
- **Expected:** partial, with the note saying provenance stops at the bundle
  boundary
- **Why:** moving it to evidenceable without image signing is precisely the
  overstatement an auditor is looking for.

## Security — the offline bundle

### SEC-136 · A sealed bundle verifies and reports what vouched for it
- **Area:** `security/bundle.py::build_manifest` · `verify`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a staged directory with a wheel, a chart and a schema file
- **Steps:** seal, then verify with the same key
- **Expected:** `is_trustworthy` true; the description names which signature
  held
- **Why:** "sealed by us" and "signed by the publisher" are different claims,
  and a single boolean collapses them.

### SEC-137 · A modified file is named and distinguished from a missing one
- **Area:** `security/bundle.py::verify` · `Verification.describe`
- **Type:** security
- **Priority:** P1
- **Precondition:** a sealed bundle
- **Steps:** append a byte to one wheel; verify
- **Expected:** that file in `modified`, nothing in `missing`, not trustworthy,
  and the description calling it a build or tampering problem
- **Why:** "verification failed" sends an operator to their network team;
  naming the file sends them to whoever built the bundle.

### SEC-138 · A removed file is reported as missing
- **Area:** `security/bundle.py::verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** a sealed bundle
- **Steps:** delete one wheel; verify
- **Expected:** that file in `missing`, not trustworthy, described as a transfer
  problem
- **Why:** the other half of the same distinction, and the reason the two lists
  are separate.

### SEC-139 · Modified is reported before missing
- **Area:** `security/bundle.py::Verification.describe`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** a bundle with one of each
- **Steps:** describe
- **Expected:** the modified clause first
- **Why:** the stated reason — sending an operator to the wrong team costs the
  first hour, and on an air-gapped host there is nobody to ask.

### SEC-140 · A file nobody signed for makes the bundle untrustworthy
- **Area:** `security/bundle.py::Verification.is_trustworthy`
- **Type:** security
- **Priority:** P1
- **Precondition:** a correctly sealed bundle
- **Steps:** add `evil.whl` to the directory; verify; run `prama bundle verify`
- **Expected:** exit 3, `trustworthy: false`, the file named
- **Why:** round-1 finding Q-18 — `bundle verify` exited 0 on exactly this and
  marked it trustworthy. `unexpected` is computed and, as read, is not
  consulted by `is_trustworthy` at all. An unlisted wheel in an offline bundle
  is arbitrary code on a bank's air-gapped host.

### SEC-141 · The manifest and its signatures are not reported as unsigned-for files
- **Area:** `security/bundle.py::verify`
- **Type:** regression
- **Priority:** P2
- **Precondition:** a bundle with `manifest.json`, `manifest.sig` and
  `manifest.ed25519`
- **Steps:** verify
- **Expected:** `unexpected` empty
- **Why:** they cannot appear in the file list they sign, and listing them made
  a correctly signed bundle read as carrying a stray file.

### SEC-142 · A manifest that does not hash to its stated value stops everything
- **Area:** `security/bundle.py::verify` · `Verification.manifest_intact`
- **Type:** security
- **Priority:** P1
- **Precondition:** a bundle whose `manifest.json` has an entry's hash edited
  and its `content_hash` left alone
- **Steps:** verify
- **Expected:** `manifest_intact` false, and the description saying nothing else
  can be trusted including the file list
- **Why:** as read, `verify` computes `stored_hash = manifest.content_hash` and
  compares it with `sha256(manifest.content())` — the same computation twice, so
  `manifest_intact` can never be false. The stated hash must come from the
  *file*, not from the object rebuilt out of it. This is the T6 shape again, in
  the artefact a bank checks before installing.

### SEC-143 · A stripped seal is not a passing seal
- **Area:** `security/bundle.py::verify` · `cli/bundle.py::BundleVerifyCommand`
- **Type:** security
- **Priority:** P1
- **Precondition:** a sealed, unsigned bundle
- **Steps:** delete `manifest.sig`; verify
- **Expected:** `seal_holds` is `None`, `is_trustworthy` false, and the
  description says the bundle proves nothing about where it came from
- **Why:** an unsigned bundle verifies internally and proves nothing about
  origin, and in an air-gapped install there is nothing else to check it
  against.

### SEC-144 · A stripped publisher signature does not downgrade to a pass
- **Area:** `cli/bundle.py::BundleVerifyCommand` · `security/bundle.py::verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** a bundle signed with Ed25519 and sealed with HMAC
- **Steps:** delete `manifest.ed25519`; run `prama bundle verify
  --publisher-key pub.pem`
- **Expected:** non-zero, saying a publisher key was given and no signature was
  found
- **Why:** round-1 finding Q-19 — stripping the signature downgraded
  verification to a pass, because `signature=""` makes `signed` stay `None` and
  the seal alone then satisfies `is_trustworthy`. Asking for provenance and
  being told nothing must not read as provenance established.

### SEC-145 · A signature offered with no key to check it is a no, not an absence
- **Area:** `security/bundle.py::verify`
- **Type:** security
- **Priority:** P1
- **Precondition:** a signed bundle, verified without `--publisher-key`
- **Steps:** verify
- **Expected:** `signature_holds` false or an explicit statement that it could
  not be checked — and the CLI prints the paragraph telling the operator to pass
  a key
- **Why:** an unverifiable signature reported as nothing reads as an unsigned
  bundle, which is a different and lesser problem.

### SEC-146 · A signature verified against the wrong public key fails
- **Area:** `security/bundle.py::Manifest.signature_holds`
- **Type:** security
- **Priority:** P1
- **Precondition:** two Ed25519 key pairs
- **Steps:** sign with one, verify with the other
- **Expected:** false, and `is_trustworthy` false *even when the local seal
  holds*
- **Why:** a signature offered and failing is disqualifying on its own — a
  holding local seal says only that whoever put it on this host had this host's
  key.

### SEC-147 · A malformed signature fails like a wrong one
- **Area:** `security/bundle.py::Manifest.signature_holds`
- **Type:** security
- **Priority:** P2
- **Precondition:** `signature="zz"` and a signature of the wrong length
- **Steps:** verify
- **Expected:** false, no exception, no distinction in the message
- **Why:** distinguishing malformed from wrong tells an attacker which half to
  vary.

### SEC-148 · A failing seal alongside a holding publisher signature is not a finding
- **Area:** `security/bundle.py::Verification.describe`
- **Type:** regression
- **Priority:** P2
- **Precondition:** a bundle signed by the publisher, whose HMAC seal was made
  with a key this host does not have
- **Steps:** verify with the publisher key
- **Expected:** trustworthy, and no sentence about tampering
- **Why:** this is the normal air-gapped case, and reporting it as a failure
  sent an operator looking for tampering that had not happened.

### SEC-149 · Either signature suffices, and neither is silently assumed
- **Area:** `security/bundle.py::Verification.is_trustworthy`
- **Type:** contract
- **Priority:** P1
- **Precondition:** four bundles — seal only, signature only, both, neither
- **Steps:** verify each
- **Expected:** trustworthy for the first three, not for the fourth
- **Why:** requiring both would make the air-gapped case impossible; requiring
  neither is what round 1 found.

### SEC-150 · The seal is pinned to an independent HMAC vector
- **Area:** `security/bundle.py::Manifest.seal`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a fixed manifest and key
- **Steps:** compare with an HMAC written out from RFC 2104 over `hashlib`
  alone, in a test that does not import `hmac`
- **Expected:** equal
- **Why:** finding T6 — replacing this with `sha256(key || message)` produced
  zero new failures across the whole suite.

### SEC-151 · The seal comparison is constant-time and requires a key
- **Area:** `security/bundle.py::verify`
- **Type:** security
- **Priority:** P2
- **Precondition:** a sealed bundle, verified with `key=None`
- **Steps:** verify
- **Expected:** `seal_holds` false, not a crash and not a pass; the comparison
  uses `hmac.compare_digest`
- **Why:** `bool(key) and compare_digest(manifest.seal(key or b""), seal)` is
  written to survive a missing key, and the `b""` fallback is exactly the empty
  key of EVD-072.

### SEC-152 · The manifest's canonical form is stable across machines
- **Area:** `security/bundle.py::Manifest.content`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same bundle catalogued on two hosts, entries discovered
  in different filesystem orders
- **Steps:** compare `content_hash`
- **Expected:** identical
- **Why:** a manifest whose serialisation varied would make a signature depend
  on the JSON library, and a verification failure would then mean nothing.

### SEC-153 · The manifest excludes itself and its signatures
- **Area:** `security/bundle.py::build_manifest`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a directory already containing a manifest and signatures
- **Steps:** re-seal
- **Expected:** neither listed as an entry
- **Why:** a manifest listing its own hash could never be produced, and one
  listing the signature would change the thing the signature covers.

### SEC-154 · `manifest.ed25519` is excluded from the entry list as well
- **Area:** `security/bundle.py::build_manifest`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a directory containing `manifest.ed25519` from a previous
  seal
- **Steps:** re-seal, then verify
- **Expected:** consistent treatment — as read, `build_manifest` skips only
  `manifest.json` and `manifest.sig`, so a pre-existing publisher signature is
  catalogued as an entry and then excluded by `verify`, giving a permanently
  missing file
- **Why:** re-sealing a directory is the ordinary release operation, and this
  makes the second seal produce a bundle that cannot verify.

### SEC-155 · File kinds are classified for a reviewer
- **Area:** `security/bundle.py::_kind_of`
- **Type:** functional
- **Priority:** P3
- **Precondition:** a wheel, a `.sql`, a file under `chart/`, one under
  `image/`, one under `model/`, and an unclassifiable file
- **Steps:** catalogue
- **Expected:** `wheel`, `schema`, `chart`, `image`, `model`, `other`
- **Why:** the kind is what a security team filters on when asked what executes.

### SEC-156 · The SBOM lists what resolved, not what was requested
- **Area:** `security/bundle.py::installed_distributions`
- **Type:** contract
- **Priority:** P1
- **Precondition:** an environment where an installed version exceeds the
  `pyproject.toml` floor
- **Steps:** produce the SBOM
- **Expected:** the installed version
- **Why:** `pyproject.toml` states floors; a bundle whose SBOM listed the
  requirements would describe a different install from the one it carries.

### SEC-157 · `--no-sbom` is possible and discouraged in the same breath
- **Area:** `cli/bundle.py::BundleSealCommand`
- **Type:** documentation
- **Priority:** P3
- **Precondition:** none
- **Steps:** seal with `--no-sbom`; read the help
- **Expected:** an empty SBOM and the help text saying it is rarely right
- **Why:** it is the first thing a bank's security team asks for and cannot be
  produced later from an air-gapped host.

### SEC-158 · Hashing a multi-gigabyte file does not load it into memory
- **Area:** `security/bundle.py::digest`
- **Type:** performance
- **Priority:** P2
- **Precondition:** a 3 GiB sparse image file
- **Steps:** catalogue the directory; watch resident memory
- **Expected:** bounded by the 1 MiB block
- **Why:** the container image is exactly this file, and it is the one an
  offline bundle always carries.

### SEC-159 · Sealing a directory that does not exist is refused with a remedy
- **Area:** `security/bundle.py::build_manifest`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a path that is a file, and a path that does not exist
- **Steps:** seal each
- **Expected:** `ValidationError` in both, naming the path
- **Why:** round-1 finding Q-28 — "directory where a file is expected" produced
  tracebacks across the CLI.

### SEC-160 · Verifying a directory that is not a bundle says so
- **Area:** `cli/bundle.py::_load`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a directory of files with no manifest
- **Steps:** `prama bundle verify`
- **Expected:** a `ValidationError` explaining that a bundle carries a manifest
  because without one there is nothing to check the files against
- **Why:** it is the commonest operator mistake and the message is already
  written.

### SEC-161 · A manifest with a missing key fails cleanly
- **Area:** `cli/bundle.py::_load`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a `manifest.json` with no `entries` key, and one with an
  entry missing `sha256`
- **Steps:** verify
- **Expected:** a typed refusal naming the manifest, not a `KeyError`
- **Why:** `_load` indexes `payload["product"]` and `entry["sha256"]` directly;
  a hand-edited or truncated manifest is exactly what an operator has when they
  run this.

### SEC-162 · `prama bundle verify` exits 3 on a bundle that must not be installed
- **Area:** `cli/bundle.py::BundleVerifyCommand`
- **Type:** contract
- **Priority:** P1
- **Precondition:** each failing bundle from SEC-137 through SEC-146
- **Steps:** run the command, with and without `--json`
- **Expected:** exit 3 in every case, in both output modes, and "Do not install
  this bundle." on the text path
- **Why:** the exit code is the documented distinction between "this bundle is
  wrong" and "I ran the command wrong", and it is what an air-gapped install
  script branches on.

### SEC-163 · `--json` reports the same verdict as the text output
- **Area:** `cli/bundle.py::BundleVerifyCommand`
- **Type:** contract
- **Priority:** P2
- **Precondition:** an untrustworthy bundle
- **Steps:** run with and without `--json`
- **Expected:** the same exit code and the same verdict; the JSON carries
  `missing`, `modified`, `unexpected`, `manifest_intact`, `seal_holds`,
  `trustworthy`
- **Why:** round-1 finding Q-37 was a JSON contract broken on an error path, at
  the exact point a CI gate reads it. Note `to_dict` omits `signature_holds`,
  so a JSON consumer cannot see the publisher verdict at all.

### SEC-164 · Sealing refuses to run with an empty session secret
- **Area:** `cli/bundle.py::_key` · `config.require_secret`
- **Type:** security
- **Priority:** P1
- **Precondition:** the shipped configuration, where
  `security.session_secret` is empty on purpose
- **Steps:** `prama bundle seal ./offline`
- **Expected:** a refusal naming the secret and where to set it
- **Why:** otherwise the bundle is sealed with an empty key, which anybody can
  reproduce, and the word "sealed" means nothing.

### SEC-165 · The private key is read from a file, never from argv
- **Area:** `cli/bundle.py::_private_key`
- **Type:** security
- **Priority:** P2
- **Precondition:** none
- **Steps:** check the flag takes a path; attempt a hex key as an argument
- **Expected:** only `--sign-with KEY.pem`
- **Why:** a private key on an argv is a private key in the shell history and in
  every process listing on the machine while the command runs.

### SEC-166 · An encrypted PEM is refused with a usable message
- **Area:** `cli/bundle.py::_private_key`
- **Type:** negative
- **Priority:** P3
- **Precondition:** a passphrase-protected key
- **Steps:** seal with it
- **Expected:** a message saying the key is encrypted and unsupported
- **Why:** `load_pem_private_key(data, password=None)` raises a library error
  whose text is about types, and the operator has the passphrase in hand.

### SEC-167 · Sealing says how much the seal is worth, on the success path
- **Area:** `cli/bundle.py::BundleSealCommand`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** sealing with and without `--sign-with`
- **Steps:** read the output
- **Expected:** the HMAC paragraph always; the Ed25519 paragraph when signed;
  and when unsigned, the warning that an air-gapped customer can check nothing
- **Why:** this is the moment somebody decides how much the signature is worth,
  and it is the last moment they will think about it.

## Secrets — references, providers, resolution and redaction

### SEC-168 · A reference parses into scheme, location and key
- **Area:** `secrets/reference.py::SecretRef.parse`
- **Type:** functional
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse `env://PRAMA_PG_PASSWORD`,
  `file:///run/secrets/warehouse_password` and
  `hashicorp://secret/data/prod/warehouse#password`
- **Expected:** the documented three-way split in each; the scheme lower-cased;
  `render()` round-trips
- **Why:** the three forms in the module docstring are the product's own
  examples, and a docstring example that does not parse is a defect.

### SEC-169 · An empty reference is refused with an example
- **Area:** `secrets/reference.py::SecretRef.parse`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `""` and `"   "`
- **Expected:** `ValidationError` whose remedy shows `env://PRAMA_DB_PASSWORD`
- **Why:** an empty reference is what a half-filled form produces, and the
  remedy has to show the shape.

### SEC-170 · A pasted password is refused and never echoed
- **Area:** `secrets/reference.py::SecretRef.parse`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** parse a literal password such as `hunter2!`; inspect the
  exception's message and context; check the log
- **Expected:** refused, with the remedy explaining that Prama stores a
  reference; **no context at all**, because the offending text may be the
  password
- **Why:** this error gets logged. The deliberate absence of context is a
  security decision that a later "improvement" would undo.

### SEC-171 · A reference with a scheme and no location is refused
- **Area:** `secrets/reference.py::SecretRef.parse`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** none
- **Steps:** parse `env://`
- **Expected:** refused, naming the scheme, with the scheme safely in the
  context
- **Why:** an empty location would resolve to the environment variable `""` and
  fail with a message about the wrong thing.

### SEC-172 · `try_parse` never raises and never returns a half-parsed reference
- **Area:** `secrets/reference.py::SecretRef.try_parse`
- **Type:** functional
- **Priority:** P3
- **Precondition:** none
- **Steps:** `try_parse(None)`, `try_parse("")`, `try_parse("hunter2")`
- **Expected:** `None` in all three
- **Why:** it is the form used where a field may legitimately hold a literal,
  and a partial parse there becomes a lookup for a secret nobody stored.

### SEC-173 · `_LOOKS_LIKE_A_SECRET` is used or removed
- **Area:** `secrets/reference.py`
- **Type:** regression
- **Priority:** P3
- **Precondition:** none
- **Steps:** grep for the constant
- **Expected:** either a call site, or its removal
- **Why:** it is defined, documented as the way to give a useful error instead
  of trying to resolve a password as a URI, and referenced nowhere. Dead code
  that describes a behaviour the product does not have is how S4 happened.

### SEC-174 · `env://` reads the variable and refuses a missing one
- **Area:** `secrets/providers.py::EnvironmentSecretProvider.resolve`
- **Type:** functional
- **Priority:** P1
- **Precondition:** `PRAMA_TEST_SECRET` set and unset
- **Steps:** resolve both
- **Expected:** the value with `origin` set to the reference; then
  `SecretResolutionError` naming the variable and where to set it
- **Why:** never returning an empty value for a missing secret is the whole
  contract of the SPI — an empty password reaches the driver and comes back as
  an authentication failure.

### SEC-175 · `file://` reads a mounted secret and strips only the trailing newline
- **Area:** `secrets/providers.py::FileSecretProvider.resolve`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** a secret file written by `echo`, one with `\r\n`, and one
  whose value legitimately ends in a space
- **Steps:** resolve each
- **Expected:** the newline stripped in the first two, the space preserved
- **Why:** round-1 finding Q-01 was exactly this class of defect on a different
  input path: a trailing newline silently inside a credential, with both sides
  reporting success.

### SEC-176 · A file reference outside the configured root is refused
- **Area:** `secrets/providers.py::FileSecretProvider._locate`
- **Type:** security
- **Priority:** P1
- **Precondition:** `root=/run/secrets`
- **Steps:** resolve `file:///run/secrets/../../etc/shadow` and a symlink inside
  the root pointing outside it
- **Expected:** refused in both, naming the configured root
- **Why:** a reference is a stored value an authenticated user can edit, so
  without the root it is a way to read any file the process can read. The
  symlink case matters because `resolve()` follows links before the
  `is_relative_to` check.

### SEC-177 · With no root configured, a file reference can read any readable file
- **Area:** `secrets/providers.py::FileSecretProvider._locate`
- **Type:** security
- **Priority:** P1
- **Precondition:** `FileSecretProvider(root=None)` — the default from
  `default_resolver` when `file_root` is unset
- **Steps:** resolve `file:///etc/passwd`
- **Expected:** either a refusal, or a documented deployment requirement that
  `secrets.file.root` is set
- **Why:** the class's own docstring says the root is what stops this, and the
  default constructs without one. An authenticated user who can edit a
  connection record can read arbitrary files.

### SEC-178 · A world-readable secret file is used and reported
- **Area:** `secrets/providers.py::FileSecretProvider._warn_if_readable`
- **Type:** security
- **Priority:** P2
- **Precondition:** a secret file at mode 0644
- **Steps:** resolve
- **Expected:** the value returned and a warning naming the path and the mode
- **Why:** refusing to start is a worse outcome than a warning somebody can act
  on, and passing silently is not an option — the docstring commits to exactly
  this trade.

### SEC-179 · A JSON fragment selects one field
- **Area:** `secrets/providers.py::_field_of`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a secret holding `{"username": "u", "password": "p"}`
- **Steps:** resolve `...#password`
- **Expected:** `p`
- **Why:** most vaults store a document per path, so the fragment is the normal
  case rather than an advanced one.

### SEC-180 · A fragment on a non-JSON secret is refused with the right remedy
- **Area:** `secrets/providers.py::_field_of`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a plain-text secret
- **Steps:** resolve with `#password`
- **Expected:** refused, with the remedy to drop the fragment — and the
  **secret itself never in the message**
- **Why:** the failure text is one careless f-string away from printing the
  credential it could not parse.

### SEC-181 · A missing field names the fields present and not their values
- **Area:** `secrets/providers.py::_field_of` · `secrets/vault.py`
- **Type:** security
- **Priority:** P2
- **Precondition:** a document with `username` and `password`, referenced as
  `#pw`
- **Steps:** resolve
- **Expected:** the field *names* listed; no value anywhere in the message or
  context
- **Why:** the names are safe and are what makes it fixable in one step; the
  values are the secret.

### SEC-182 · A non-string field is serialised rather than coerced silently
- **Area:** `secrets/providers.py::_field_of`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `{"port": 5432}`
- **Steps:** resolve `#port`
- **Expected:** `"5432"` via `json.dumps`, not a `TypeError`
- **Why:** a numeric field in a vault document is common, and a crash here is a
  connection that cannot be made.

### SEC-183 · The memory provider is never a default
- **Area:** `secrets/providers.py::MemorySecretProvider` · `secrets/resolver.py::default_resolver`
- **Type:** security
- **Priority:** P1
- **Precondition:** none
- **Steps:** inspect `default_resolver().schemes`
- **Expected:** `env`, `file`, `vault` — no `memory`
- **Why:** a provider that manufactures secrets from nowhere would make a
  misconfigured deployment look like a working one.

### SEC-184 · Vault is registered but unconfigured, which is not the same as absent
- **Area:** `secrets/resolver.py::default_resolver` · `secrets/vault.py::VaultSecretProvider.available`
- **Type:** functional
- **Priority:** P1
- **Precondition:** no Vault transport or token
- **Steps:** resolve `vault://secret/data/x#password`
- **Expected:** "Vault is referenced but not configured", with what to set — not
  "no provider for scheme 'vault'"
- **Why:** the second message sends somebody looking for a plugin that is
  already installed.

### SEC-185 · The Vault token is itself a reference, never a literal
- **Area:** `secrets/vault.py::VaultSecretProvider.__init__` · `unavailable_remedy`
- **Type:** security
- **Priority:** P1
- **Precondition:** configuration
- **Steps:** check how the token is supplied
- **Expected:** resolved through the ordinary resolver from something like
  `env://VAULT_TOKEN`
- **Why:** otherwise the one secret this module exists to protect is the one
  sitting in a config file.

### SEC-186 · KV v2's nested data is read, not its metadata
- **Area:** `secrets/vault.py::ReadResult.from_body`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a body of `{"data": {"data": {...}, "metadata": {...}}}`
- **Steps:** parse
- **Expected:** the inner document as fields, the version from the metadata
- **Why:** reaching for the outer `data` returns version numbers and timestamps
  — which is not the secret and does not look like an error either.

### SEC-187 · A soft-deleted version is not a value
- **Area:** `secrets/vault.py::ReadResult.is_readable` · `_why_empty`
- **Type:** security
- **Priority:** P1
- **Precondition:** three bodies: soft-deleted with a `deletion_time`,
  `destroyed: true`, and empty data
- **Steps:** resolve each
- **Expected:** a refusal in each, naming which of the three it was and the
  version
- **Why:** Vault returns these with HTTP 200, and a provider that reads the
  empty data hands back an empty string, which reaches the driver as an
  authentication failure and sends somebody to check a password that was never
  read.

### SEC-188 · A reference naming no field is refused rather than guessed
- **Area:** `secrets/vault.py::VaultSecretProvider.resolve`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a two-field document, referenced without a fragment
- **Steps:** resolve
- **Expected:** refused, with "vault://path#password" in the remedy
- **Why:** guessing which field is the credential is how a username gets used as
  a password, and the resulting failure blames the credential.

### SEC-189 · An empty field value is refused
- **Area:** `secrets/vault.py::VaultSecretProvider.resolve`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `{"password": ""}` and `{"password": null}`
- **Steps:** resolve
- **Expected:** refused in both, calling it a half-finished write
- **Why:** the same empty-password failure, one layer further in.

### SEC-190 · A transport failure is reported as a transport failure
- **Area:** `secrets/vault.py::VaultSecretProvider.resolve`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a transport raising a connection error, and one raising a
  403
- **Steps:** resolve
- **Expected:** `SecretResolutionError` naming the path, with the remedy about
  reachability and token expiry, and only the exception *type* in the context
- **Why:** an expired Vault token fails exactly like a wrong path, and the
  remedy is the only thing that separates them. Putting the raw exception text
  in the context would risk carrying a URL with a token in it.

### SEC-191 · The path is passed through as written, including `data/`
- **Area:** `secrets/vault.py::VaultSecretProvider`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a mount not called `secret`
- **Steps:** resolve `vault://kv/data/prama/db#password`
- **Expected:** the transport receives `kv/data/prama/db` unchanged
- **Why:** inserting `data/` silently would be convenient and would break every
  deployment whose mount is named differently.

### SEC-192 · Vault has not been verified against a real server, and that is recorded
- **Area:** `secrets/vault.py` module docstring
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** check every place Vault support is described
- **Expected:** the caveat survives to the documentation
- **Why:** it is recorded here rather than implied by its absence, and that
  choice has to survive the trip to a datasheet.

### SEC-193 · An unknown scheme names what is installed
- **Area:** `secrets/resolver.py::SecretResolver.resolve`
- **Type:** negative
- **Priority:** P1
- **Precondition:** a reference to `aws://`
- **Steps:** resolve
- **Expected:** refused, listing the installed schemes, and the attempt recorded
  as `unknown-scheme`
- **Why:** the remedy is what turns a dead end into a package to install.

### SEC-194 · A provider that says it is unavailable answers in its own terms
- **Area:** `secrets/resolver.py::SecretResolver.resolve` · `SecretProvider.unavailable_remedy`
- **Type:** functional
- **Priority:** P2
- **Precondition:** an unconfigured Vault provider
- **Steps:** resolve
- **Expected:** the provider's own remedy naming the missing transport and token
- **Why:** the resolver knows a provider said no; only the provider knows which
  setting is missing, and a generic "check its configuration" sends somebody
  looking for a plugin that is already installed.

### SEC-195 · An empty resolved secret is refused where the truth is
- **Area:** `secrets/resolver.py::SecretResolver.resolve`
- **Type:** security
- **Priority:** P1
- **Precondition:** an environment variable set to the empty string
- **Steps:** resolve
- **Expected:** refused, recorded as `empty`, with the remedy explaining it
  would reach the source as a blank password
- **Why:** failing at the driver sends somebody to check a credential that was
  never actually read.

### SEC-196 · A resolved secret is cached and expires
- **Area:** `secrets/resolver.py::SecretResolver._cached` · `_store`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a controllable clock, TTL 300s
- **Steps:** resolve twice inside the window and once beyond it, counting
  provider calls
- **Expected:** one call, then a second after expiry
- **Why:** one vault call per batch of a table read will get the vault rate
  limiting a bank's quality platform, and it will be Prama that gets turned off.

### SEC-197 · A TTL of zero disables caching entirely
- **Area:** `secrets/resolver.py::SecretResolver`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `cache_ttl_seconds=0`
- **Steps:** resolve twice
- **Expected:** two provider calls, nothing retained in memory
- **Why:** it is the setting a security team will ask for, and a cache that
  ignored it would hold credentials in memory against an explicit instruction.

### SEC-198 · A rotation is picked up without a restart
- **Area:** `secrets/resolver.py::SecretResolver.invalidate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a cached secret
- **Steps:** rotate the underlying value, `invalidate(reference)`, resolve
- **Expected:** the new value; and `invalidate()` with no argument clears
  everything
- **Why:** a credential rotation that needs a restart is a rotation that does
  not happen.

### SEC-199 · Cache access is thread-safe
- **Area:** `secrets/resolver.py::SecretResolver._lock`
- **Type:** concurrency
- **Priority:** P2
- **Precondition:** eight threads resolving and invalidating the same reference
- **Steps:** hammer for a few seconds
- **Expected:** no `KeyError` from the expiry path, no torn entry, the provider
  called a bounded number of times
- **Why:** resolution happens from request handlers and background
  re-examination at the same time, and the expiry path deletes a key it read
  under the same lock.

### SEC-200 · Every resolution is recorded, and never with the value
- **Area:** `secrets/resolver.py::SecretAccess` · `_record`
- **Type:** security
- **Priority:** P1
- **Precondition:** an audit sink
- **Steps:** resolve successfully, then with a missing secret, then an empty
  one, then an unknown scheme, then an unavailable provider
- **Expected:** five records with outcomes `resolved`, `failed`, `empty`,
  `unknown-scheme`, `provider-unavailable`; the reference, purpose, principal
  and time on each; the fingerprint only on success; no plaintext anywhere
- **Why:** "which system read this credential and when" is a question an auditor
  will ask, and the answer should not require reading application logs.

### SEC-201 · The audit fingerprint makes a rotation visible without holding a secret
- **Area:** `secrets/value.py::SecretValue.fingerprint`
- **Type:** functional
- **Priority:** P2
- **Precondition:** two different values
- **Steps:** fingerprint both; and the same value twice
- **Expected:** stable per value, different across values, 16 hex characters,
  non-reversible
- **Why:** it lets two configurations be compared and a rotation detected
  without anything sensitive being recorded — and 64 bits is enough for
  equality and not for authentication, which is what it is documented as.

### SEC-202 · A failed resolution's detail carries the message and not the secret
- **Area:** `secrets/resolver.py::_record`
- **Type:** security
- **Priority:** P2
- **Precondition:** a provider raising with a message containing the reference
- **Steps:** resolve; inspect the audit record's `detail`
- **Expected:** the message, with no credential in it
- **Why:** `detail=str(exc.args[0])` copies a provider's message into the audit
  trail, so every provider's error text is now a place a secret could leak.

### SEC-203 · A secret never prints itself
- **Area:** `secrets/value.py::SecretValue`
- **Type:** security
- **Priority:** P1
- **Precondition:** `SecretValue("hunter2", origin="env://X")`
- **Steps:** `str()`, `repr()`, `f"{v}"`, `f"{v:>20}"`, `"%s" % v`,
  `json.dumps` via the default encoder, `logging.info("%s", v)`
- **Expected:** `<secret>` everywhere; the origin visible only in the repr
- **Why:** the dangerous moment is the incidental copy — a debug line, an
  exception's repr of its arguments, a config dict serialised into an audit
  record — and each is one line of ordinary well-intentioned code.

### SEC-204 · A secret refuses to be pickled
- **Area:** `secrets/value.py::SecretValue.__reduce__`
- **Type:** security
- **Priority:** P1
- **Precondition:** a secret
- **Steps:** `pickle.dumps`, `copy.deepcopy`, and a multiprocessing hand-off
- **Expected:** `TypeError` with the message about passing the reference instead
- **Why:** pickling is how a secret ends up in a task queue, a cache file or a
  crash dump. Note that `deepcopy` uses the same protocol, so a legitimate copy
  of a configuration dict containing a secret will also fail — the case
  establishes that this is intended.

### SEC-205 · `len()` reveals nothing about the secret
- **Area:** `secrets/value.py::SecretValue.__len__`
- **Type:** security
- **Priority:** P2
- **Precondition:** a 40-character secret
- **Steps:** `len(v)`
- **Expected:** the length of `<secret>`, and no caller in the product uses
  `len()` on a secret to make a decision
- **Why:** the length is a small leak and no legitimate caller needs it — but a
  length check such as "refuse a password under 12 characters" would silently
  pass or fail on the wrong number, so the call sites matter as much as the
  value.

### SEC-206 · Comparison is constant-time, and against another secret too
- **Area:** `secrets/value.py::SecretValue.matches` · `__eq__`
- **Type:** security
- **Priority:** P2
- **Precondition:** two secrets
- **Steps:** read the code; compare equal and unequal pairs, and a secret
  against a plain string
- **Expected:** `hmac.compare_digest` in both paths; `NotImplemented` against a
  bare string via `==`, so an accidental `secret == "literal"` does not silently
  compare wrongly
- **Why:** a credential comparison is the one place in the product where a
  timing leak is exploitable.

### SEC-207 · Hashing a secret does not expose it
- **Area:** `secrets/value.py::SecretValue.__hash__`
- **Type:** security
- **Priority:** P3
- **Precondition:** a secret
- **Steps:** `hash(v)`; place several in a set
- **Expected:** the hash derives from the fingerprint, and equal values collapse
- **Why:** hashing the value would let a dictionary of secrets be probed.

### SEC-208 · Sensitive keys are masked in structured log fields
- **Area:** `core/log.py::redact_mapping`
- **Type:** security
- **Priority:** P1
- **Precondition:** a log call with `prama_fields` containing `password`,
  `api_key`, `authorization` and a nested dict holding `client_secret`
- **Steps:** emit
- **Expected:** `***` for each, at every depth
- **Why:** logs go to a SIEM and are read by people with less access than the
  process that wrote them.

### SEC-209 · A secret passed as a logging argument is not redacted
- **Area:** `core/log.py::RedactionFilter.filter`
- **Type:** security
- **Priority:** P1
- **Precondition:** `_log.warning("password=%s", "hunter2")`
- **Steps:** emit and read the formatted record
- **Expected:** redacted
- **Why:** the filter substitutes over `record.msg` — the *template* — and never
  touches `record.args`, so the classic lazy-formatting call the logging
  documentation recommends writes the credential out in full. The
  pattern-matching redaction only works on messages that were already formatted,
  which is the style the codebase discourages.

### SEC-210 · Redaction does not mask a sensitive key whose value is a list
- **Area:** `core/log.py::redact_mapping`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `{"credentials": ["a", "b"]}` and
  `{"outer": [{"password": "p"}]}`
- **Steps:** redact
- **Expected:** both masked
- **Why:** the recursion descends into dicts and not into lists, so a secret
  inside a list of dicts passes through untouched.

### SEC-211 · `prama config show` redacts every secret it prints
- **Area:** `cli` config rendering · `secrets/value.py`
- **Type:** security
- **Priority:** P1
- **Precondition:** a configuration with a session secret, a database password
  and a Vault token
- **Steps:** `prama config show`, with and without `--json`
- **Expected:** `<secret>` or `***` for each in both forms
- **Why:** it is the command an operator runs while screen-sharing with support.

### SEC-212 · A traceback carrying a secret argument renders it redacted
- **Area:** `secrets/value.py::SecretValue.__repr__` · error rendering
- **Type:** security
- **Priority:** P1
- **Precondition:** a function raising with a `SecretValue` among its arguments,
  under a traceback renderer that shows locals
- **Steps:** trigger it through the CLI and through the API error handler
- **Expected:** `<secret>` in every frame
- **Why:** a rendered traceback on an error page is the incidental copy the
  whole class was designed against, and it is the one path that does not go
  through the logging filter.

### SEC-213 · The SPI stays three methods
- **Area:** `secrets/spi.py::SecretProvider`
- **Type:** contract
- **Priority:** P3
- **Precondition:** none
- **Steps:** enumerate the abstract surface
- **Expected:** `resolve`, `available`, `unavailable_remedy` — no write, rotate
  or delete
- **Why:** the estate already has a secret manager; reimplementing a worse one
  beside it is how credentials end up in two places with different lifetimes.

### SEC-214 · A provider with no scheme cannot be registered
- **Area:** `secrets/resolver.py::SecretResolver.register`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a provider whose `scheme` is `""`
- **Steps:** register
- **Expected:** `SecretResolutionError` naming the class
- **Why:** it would otherwise register under the empty key and answer for
  nothing, silently.

### SEC-215 · Registering two providers for one scheme is resolved or refused
- **Area:** `secrets/resolver.py::SecretResolver.register`
- **Type:** negative
- **Priority:** P2
- **Precondition:** two `env` providers
- **Steps:** register both
- **Expected:** a stated rule — last wins, or a refusal
- **Why:** as written the second silently replaces the first, so a plugin can
  take over the environment scheme and see every secret resolved through it.

### SEC-216 · `resolve_optional` distinguishes "no credential" from "a credential that failed"
- **Area:** `secrets/resolver.py::SecretResolver.resolve_optional`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a connection legitimately using OS authentication
- **Steps:** `resolve_optional(None)` and `resolve_optional("env://MISSING")`
- **Expected:** `None`, then a raised `SecretResolutionError`
- **Why:** collapsing the two would turn a broken vault into a silent switch to
  unauthenticated access.

## Scoring — composites, materiality and coverage

### SCR-001 · Every composite is computed and named
- **Area:** `score/composite.py::score`
- **Type:** functional
- **Priority:** P1
- **Precondition:** measurements across three dimensions
- **Steps:** score
- **Expected:** all three of `MEAN`, `MINIMUM` and `WEIGHTED` present, each
  retrievable by method, with `WEIGHTED` the default of `composite()`
- **Why:** publishing one composite without naming it is how a score becomes
  disputed at exactly the moment somebody needs to rely on it.

### SCR-002 · The mean is the mean of the dimension scores, not of the controls
- **Area:** `score/composite.py::score`
- **Type:** functional
- **Priority:** P2
- **Precondition:** one dimension with four controls and one with a single
  control
- **Steps:** score
- **Expected:** the mean weights the two dimensions equally
- **Why:** a mean over controls is dominated by whatever there is most of, which
  is the first failure the module names.

### SCR-003 · The minimum is the worst dimension
- **Area:** `score/composite.py::score`
- **Type:** functional
- **Priority:** P2
- **Precondition:** dimensions at 0.99, 0.98 and 0.62
- **Steps:** score
- **Expected:** `MINIMUM == 0.62`, and `worst` names that dimension
- **Why:** it answers "is anything badly broken", which is a different question
  from the others and the one an incident manager asks.

### SCR-004 · A broken Tier 1 CDE among fifty clean Tier 4 columns scores badly
- **Area:** `score/composite.py::_weighted_rate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** one Tier 1 control over one million rows failing entirely,
  fifty Tier 4 controls over fifty million rows passing
- **Steps:** score
- **Expected:** the weighted composite is dominated by the Tier 1 failure and is
  materially **below** the plain mean
- **Why:** the obvious implementation multiplies criticality by row count and
  produces a "materiality-weighted" number *higher* than the mean. This is the
  case the module was rewritten for, and it is the one a bank will run first.

### SCR-005 · Rows weight controls within a tier and never across tiers
- **Area:** `score/composite.py::_weighted_rate` · `_rows_weighted`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two Tier 2 controls, one over four rows and one over four
  million
- **Steps:** score
- **Expected:** the large one dominates within the tier; adding rows to a Tier 4
  control does not change the tier's contribution to the composite
- **Why:** rows are evidence and criticality is importance, and multiplying them
  conflates the two.

### SCR-006 · The criticality weights are the shipped ones
- **Area:** `score/composite.py::CRITICALITY_WEIGHT`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** read the table
- **Expected:** 16, 8, 2, 1 — a Tier 1 counting sixteen times a Tier 4
- **Why:** the steepness is deliberate; a gentler weight produces a score that
  still moves mostly with column count, which is the failure being avoided.

### SCR-007 · A control that did not run contributes nothing and is not a pass
- **Area:** `score/composite.py::Measurement.ran` · `score`
- **Type:** security
- **Priority:** P1
- **Precondition:** four controls, two with `ran=False`
- **Steps:** score
- **Expected:** the arithmetic covers two; `not_run == 2`; coverage 0.5
- **Why:** a dataset scoring 100% because half its controls were skipped is the
  most misleading output this module could produce.

### SCR-008 · A control that scanned nothing is excluded and counted separately
- **Area:** `score/composite.py::Measurement.measured` · `Score.scanned_nothing`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a control with `ran=True, scanned=0`
- **Steps:** score
- **Expected:** excluded from every composite; `scanned_nothing == 1`; not
  counted as `not_run`
- **Why:** finding C5 — a dataset that scanned zero rows scored 100%. The two
  need different remedies: one is a scheduling or connectivity problem, the
  other a delivery that did not arrive.

### SCR-009 · An empty scan's rate is zero, not one
- **Area:** `score/composite.py::Measurement.rate`
- **Type:** regression
- **Priority:** P1
- **Precondition:** `Measurement(scanned=0, violations=0)`
- **Steps:** read `rate`
- **Expected:** 0.0
- **Why:** it returned 1.0, which is what made an empty scan a perfect score for
  any caller that reached for the rate without checking `measured`.

### SCR-010 · A score covering nothing says so rather than reporting 100%
- **Area:** `score/composite.py::score` · `Score.describe`
- **Type:** security
- **Priority:** P1
- **Precondition:** every measurement either not run or scanning nothing
- **Steps:** score and describe
- **Expected:** no dimensions, coverage 0.0, and a sentence saying an empty
  result is not a clean one
- **Why:** the degenerate case is the one a broken feed produces every morning,
  and it must not render as green.

### SCR-011 · Coverage is the share of intended controls the score describes
- **Area:** `score/composite.py::Score.coverage`
- **Type:** functional
- **Priority:** P1
- **Precondition:** ten controls, two not run, one scanning nothing
- **Steps:** read `coverage`
- **Expected:** 0.7
- **Why:** a score covering seven tenths of the controls is not a score of the
  dataset, and coverage is the number that says so.

### SCR-012 · Coverage of a dataset with no controls is zero, not one
- **Area:** `score/composite.py::Score.coverage`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** no measurements
- **Steps:** score
- **Expected:** `coverage == 0.0`
- **Why:** an undeclared dataset must not render as fully covered.

### SCR-013 · Disagreement between the composites is surfaced, not resolved
- **Area:** `score/composite.py::Score.methods_disagree`
- **Type:** functional
- **Priority:** P1
- **Precondition:** mean 0.98, minimum 0.62
- **Steps:** describe
- **Expected:** `methods_disagree` true and a sentence naming each composite,
  what it answers, and saying this is the finding rather than a contradiction
- **Why:** most of the dataset being fine while one dimension is not is
  information, and averaging it away is how a score stops being actionable.

### SCR-014 · The disagreement threshold is a boundary, not a vibe
- **Area:** `score/composite.py::Score.methods_disagree`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** composites spanning exactly 0.1, and 0.1000001
- **Steps:** read the flag
- **Expected:** false then true
- **Why:** the constant is inline and unexplained; pinning it stops it drifting
  to whatever makes a demo look calm.

### SCR-015 · One composite alone never reads as disagreement
- **Area:** `score/composite.py::Score.methods_disagree`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a score with a single composite
- **Steps:** read the flag
- **Expected:** false
- **Why:** the guard exists; without it a partially built score would announce a
  disagreement with itself.

### SCR-016 · Dimensions are reported before any composite
- **Area:** `score/composite.py::Score.describe`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a score across three dimensions
- **Steps:** describe
- **Expected:** the per-dimension line first, with counts of violating and
  scanned rows
- **Why:** "quality 91%" is not actionable; "completeness 99%, validity 62%" is.

### SCR-017 · A dimension's rollup sums its rows and violations
- **Area:** `score/composite.py::DimensionScore`
- **Type:** functional
- **Priority:** P2
- **Precondition:** three controls in one dimension
- **Steps:** score
- **Expected:** `scanned` and `violations` are the sums, `controls` the count,
  and `score` the tier-normalised weighted rate rather than the raw ratio
- **Why:** a reader who divides the two printed numbers and gets a different
  percentage from the one beside them will not trust either.

### SCR-018 · Dimensions are ordered deterministically
- **Area:** `score/composite.py::score`
- **Type:** functional
- **Priority:** P3
- **Precondition:** measurements supplied in a shuffled order
- **Steps:** score twice with different orderings
- **Expected:** the same dimension order and the same numbers
- **Why:** a scorecard whose rows move between runs is one nobody can diff.

### SCR-019 · Violations exceeding the rows scanned are refused or reported
- **Area:** `score/composite.py::Measurement.rate`
- **Type:** negative
- **Priority:** P2
- **Precondition:** `scanned=10, violations=15`
- **Steps:** read `rate` and score
- **Expected:** a refusal, or a clamped rate that is visibly flagged — not a
  silent -0.5 propagating into the composite
- **Why:** a two-stage control can produce this through a join, and a negative
  rate drags a composite below zero with no indication why.

### SCR-020 · A perfect dataset scores 1.0 across every method
- **Area:** `score/composite.py::score`
- **Type:** functional
- **Priority:** P2
- **Precondition:** every control passing over real rows
- **Steps:** score
- **Expected:** 1.0 for all three, `methods_disagree` false
- **Why:** the positive control. Without it, a test suite full of failure cases
  can pass against a scorer that always returns zero.

### SCR-021 · The score serialises with everything a scorecard renders
- **Area:** `score/composite.py::Score.to_dict`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a mixed score
- **Steps:** serialise
- **Expected:** dimensions, all composites by name, `methods_disagree`,
  `not_run`, `scanned_nothing`, `controls`, `coverage`, summary
- **Why:** this is the API payload; a missing field turns a qualified score into
  an unqualified one on the screen.

### SCR-022 · Rounding is presentation only
- **Area:** `score/composite.py::Score.to_dict` · `DimensionScore.to_dict`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a score whose composite is 0.9999996
- **Steps:** serialise
- **Expected:** the rounded value is not 1.0, or the rounding is documented as
  lossy
- **Why:** a failing dataset that renders as a clean 100% because of a
  six-decimal round is the smallest possible version of the biggest possible
  problem.

### SCR-023 · Criticality comes from the evidence record, not from today's tier
- **Area:** `score/composite.py::Measurement.criticality` · `evidence/record.py`
- **Type:** security
- **Priority:** P1
- **Precondition:** a dataset re-tiered from 4 to 1 after last year's runs
- **Steps:** score last year's evidence
- **Expected:** last year's tier, as carried on each record
- **Why:** re-tiering a dataset next year must not silently re-weight last
  year's score — which is the reason the field is on the record at all.

### SCR-024 · An SLO budget is the complement of the objective
- **Area:** `score/composite.py::ServiceLevel.budget`
- **Type:** functional
- **Priority:** P2
- **Precondition:** objective 0.995
- **Steps:** read `budget`
- **Expected:** 0.005
- **Why:** a promise without a budget attached is a wish, and this is the
  arithmetic that converts it.

### SCR-025 · Budget consumption is reported against the allowance, not the rows
- **Area:** `score/composite.py::ServiceLevel.consumed`
- **Type:** functional
- **Priority:** P2
- **Precondition:** 1,000,000 rows, 2,500 violations, objective 0.995
- **Steps:** `consumed`
- **Expected:** 0.5 — half the month's allowance
- **Why:** "0.25% failed" means nothing to a business; "half the month's budget
  is gone on the fourth" changes behaviour.

### SCR-026 · An objective of 1.0 leaves no budget and says so
- **Area:** `score/composite.py::ServiceLevel.consumed`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** objective 1.0
- **Steps:** `consumed(1000, 0)` and `consumed(1000, 1)`
- **Expected:** 0.0 then 1.0 — no division by zero
- **Why:** "100% complete" is a promise regulated datasets genuinely make, and
  the arithmetic must not divide by the empty budget.

### SCR-027 · A period with nothing scanned does not consume budget
- **Area:** `score/composite.py::ServiceLevel.consumed`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `scanned=0, violations=0`
- **Steps:** `consumed`
- **Expected:** 0.0, and the describing sentence does not claim the objective
  was met
- **Why:** a month in which nothing ran is not a month in which nothing failed,
  and the SLO line is where that distinction gets lost.

### SCR-028 · The three budget narratives fire at their boundaries
- **Area:** `score/composite.py::ServiceLevel.describe`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** consumption of 0.5, 0.8 and 1.2
- **Steps:** describe each
- **Expected:** comfortable · at this rate the objective is missed · the budget
  is spent and then some
- **Why:** the escalation in the wording is the product's only forward-looking
  statement, and an off-by-one in the thresholds makes it arrive late.

### SCR-029 · The allowance in the message is consistent with the consumption
- **Area:** `score/composite.py::ServiceLevel.describe`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** a fractional allowance — 0.005 of 999 rows
- **Steps:** describe
- **Expected:** `allowed - violations` never renders as a negative "rows of
  allowance left"
- **Why:** `int(self.budget * scanned)` truncates, so the printed allowance can
  be one below the one the arithmetic used.

### SCR-030 · A score is derived from evidence and never stated beside it
- **Area:** `score/composite.py` · the scorecard read path
- **Type:** contract
- **Priority:** P1
- **Precondition:** a stored scorecard, if one exists
- **Steps:** trace where each number on a scorecard comes from
- **Expected:** every number derives from evidence records at read time, or a
  stored score carries the evidence sequence range it was computed over
- **Why:** "derive, never restate" — a score stored beside the evidence drifts
  from it, silently and in the flattering direction.

## Scoring — trust propagation

### SCR-031 · A column with nothing upstream scores its own evidence
- **Area:** `score/trust.py::TrustPropagator.trust`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a source column with local trust 0.8
- **Steps:** `trust`
- **Expected:** score 0.8, empty derivation, and an explanation saying nothing
  upstream is known
- **Why:** the base case, and the one that must not silently become 1.0.

### SCR-032 · A column with no local evidence defaults to full trust
- **Area:** `score/trust.py::TrustPropagator.trust`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a column absent from the local map
- **Steps:** `trust`
- **Expected:** 1.0 — and the explanation distinguishes "no controls" from
  "controls that passed"
- **Why:** `local.get(column, 1.0)` treats an unmeasured column as perfect,
  which is the same mistake as scoring an empty scan 100% and deserves the same
  scrutiny.

### SCR-033 · Trust multiplies along a path under the default semiring
- **Area:** `score/trust.py::Semiring.along`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a two-hop chain with local scores 0.9 and 0.8, no
  attenuation
- **Steps:** propagate
- **Expected:** the arithmetic in the derivation reaches the reported score
- **Why:** the derivation is the whole defence against "arbitrary", and it has
  to be checkable by hand.

### SCR-034 · Complementary inputs take the worst path, not the best
- **Area:** `score/trust.py::Semiring.ALL_INPUTS_MATTER`
- **Type:** security
- **Priority:** P1
- **Precondition:** a derived column fed by a corrupt feed at 0.2 and a healthy
  rate table at 1.0
- **Steps:** propagate under the default
- **Expected:** the score reflects the corrupt feed
- **Why:** taking the best across complementary inputs is the classic error and
  it is seductive because it produces reassuring numbers — a report built from a
  corrupt feed scores as though the feed were fine.

### SCR-035 · Redundancy is asserted, never inferred
- **Area:** `score/trust.py::Semiring.REDUNDANT_SOURCES`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the same graph as SCR-034
- **Steps:** propagate under `REDUNDANT_SOURCES`
- **Expected:** the healthy path governs — and nothing in the product selects
  this semiring automatically from the shape of the lineage
- **Why:** lineage does not record whether inputs are complementary or
  redundant, so inferring it is guessing, and the guess flatters.

### SCR-036 · Every semiring is exercised and explains itself
- **Area:** `score/trust.py::Semiring`
- **Type:** functional
- **Priority:** P2
- **Precondition:** one graph, four semirings
- **Steps:** propagate under each; read `explains`
- **Expected:** four different numbers, each with a sentence naming the
  combination rule
- **Why:** the choice is a configuration with a rationale rather than a constant
  buried in a loop, and the rationale has to reach the reader.

### SCR-037 · `WEAKEST_LINK` takes the minimum in both directions
- **Area:** `score/trust.py::Semiring.WEAKEST_LINK`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a path of 0.9, 0.9, 0.9 and a single hop of 0.8
- **Steps:** propagate
- **Expected:** 0.8 — the chain of three does not multiply down below it
- **Why:** it is what a risk team asks for, and it deliberately ignores how many
  weak links there are.

### SCR-038 · An aggregate is more trustworthy than its input, not less
- **Area:** `score/trust.py::TrustPropagator._attenuate`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a column at 0.5 feeding an aggregating edge
- **Steps:** propagate
- **Expected:** the downstream trust exceeds 0.5
- **Why:** attenuation applies to the *deficit*; applying it to the score would
  make every aggregate less trustworthy than its inputs, which is backwards and
  would rank the wrong things first.

### SCR-039 · Attenuated trust stays within [0, 1]
- **Area:** `score/trust.py::TrustPropagator._attenuate`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an edge with attenuation above 1 and one with a negative
  incoming value
- **Steps:** propagate
- **Expected:** clamped to the unit interval
- **Why:** a trust score outside the range is a number nobody can interpret and
  it propagates everywhere downstream.

### SCR-040 · A cycle in the lineage does not hang
- **Area:** `score/trust.py::TrustPropagator._paths_to`
- **Type:** negative
- **Priority:** P1
- **Precondition:** columns A → B → A
- **Steps:** propagate
- **Expected:** terminates; the `seen` set stops the revisit; the derivation
  names what was skipped
- **Why:** lineage from a real warehouse contains cycles, usually through a
  staging table, and an infinite recursion here takes out the scorecard.

### SCR-041 · Depth is bounded and the bound is visible
- **Area:** `score/trust.py::TrustPropagator._max_depth`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a chain fifteen hops deep, `max_depth=8`
- **Steps:** propagate
- **Expected:** a score derived from eight hops, and the truncation stated in
  the explanation
- **Why:** a silently truncated derivation is a number whose arithmetic does not
  reach its own conclusion, which is exactly the complaint the module exists to
  answer.

### SCR-042 · Path explosion is bounded on a wide graph
- **Area:** `score/trust.py::TrustPropagator._paths_to`
- **Type:** performance
- **Priority:** P1
- **Precondition:** a column with six upstream edges at each of eight levels
- **Steps:** propagate
- **Expected:** it completes within a stated budget
- **Why:** the implementation enumerates *every* path and keeps them all; six to
  the eighth is 1.7 million tuples of hops for one column, and `trust_all` does
  this for every column in the graph.

### SCR-043 · The derivation shown is the path that decided the score
- **Area:** `score/trust.py::TrustPropagator.trust`
- **Type:** regression
- **Priority:** P1
- **Precondition:** four paths under `ALL_INPUTS_MATTER`
- **Steps:** propagate; check the derivation's arithmetic against the reported
  score
- **Expected:** the shown path's outgoing value equals the combined score
- **Why:** showing the strongest path under a semiring that takes the worst
  produces an explanation whose arithmetic does not reach its own conclusion.

### SCR-044 · Paths considered and not taken are counted
- **Area:** `score/trust.py::Trust.alternatives`
- **Type:** functional
- **Priority:** P2
- **Precondition:** four paths
- **Steps:** propagate
- **Expected:** `alternatives == 3`, and the explanation says so
- **Why:** a score that took the best of four paths is a different claim from
  one that had only the path it took.

### SCR-045 · Containment stops propagation, and the hop records why
- **Area:** `score/trust.py::Containment` · `_paths_to`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a downstream column with a passing control that would catch
  the upstream defect
- **Steps:** propagate
- **Expected:** the upstream deficit is not inherited; the hop carries
  `contained_by` and describes it
- **Why:** propagation without containment is why trust scores go to zero
  everywhere after one bad Tuesday and stay there.

### SCR-046 · A control that exists and did not run contains nothing
- **Area:** `score/trust.py::TrustPropagator.__init__`
- **Type:** security
- **Priority:** P1
- **Precondition:** a `Containment` with `passed=False`
- **Steps:** propagate
- **Expected:** the upstream defect propagates as though no containment were
  declared
- **Why:** a containment that counted an unrun control would let anybody stop a
  defect propagating by declaring a control and never running it.

### SCR-047 · A column's trust never exceeds its own evidence
- **Area:** `score/trust.py::TrustPropagator.trust`
- **Type:** functional
- **Priority:** P1
- **Precondition:** local 0.4 with perfect upstream
- **Steps:** propagate
- **Expected:** 0.4 — `min(own, combined)`
- **Why:** clean inputs cannot make a column with failing controls trustworthy,
  and an implementation that averaged them would.

### SCR-048 · Inheritance is flagged only when upstream actually lowered the score
- **Area:** `score/trust.py::Trust.is_inherited`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a score equal to the local value to within floating point
- **Steps:** read the flag
- **Expected:** false — the epsilon guard holds
- **Why:** "upstream brings it down to 0.80" printed beside a local of 0.80 is
  an explanation that contradicts itself.

### SCR-049 · The explanation reconstructs the number
- **Area:** `score/trust.py::Trust.explain`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a three-hop derivation
- **Steps:** read the explanation
- **Expected:** the local score, the semiring's rule, each hop's incoming, local
  and outgoing values, and the final score
- **Why:** a number somebody cannot reconstruct is a number they will not act
  on, and rightly.

### SCR-050 · The remediation queue is least trustworthy first
- **Area:** `score/trust.py::ranked_by_trust`
- **Type:** functional
- **Priority:** P2
- **Precondition:** twenty columns with varied trust, two tied
- **Steps:** rank with `limit=10`
- **Expected:** ascending by score, ties broken by qualified name, exactly ten
- **Why:** a queue whose order changes between runs for tied entries is a queue
  people stop trusting.

### SCR-051 · Trust ranking differs from severity ranking, and the difference is the point
- **Area:** `score/trust.py::ranked_by_trust`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a low-severity defect upstream of a regulatory report and a
  high-severity one on a leaf column
- **Steps:** rank both ways
- **Expected:** different orders, with the upstream defect higher by trust
- **Why:** `RQ8` asks exactly this — severity ranks the finding, trust ranks the
  consequence, and they disagree where the disagreement is worth having.

### SCR-052 · `trust_all` agrees with `trust` column by column
- **Area:** `score/trust.py::TrustPropagator.trust_all`
- **Type:** contract
- **Priority:** P2
- **Precondition:** a graph of thirty columns
- **Steps:** compare the batch result against per-column calls
- **Expected:** identical scores and derivations
- **Why:** two code paths to the same number is one place for them to diverge,
  and the batch one is what the scorecard renders.

## Calibration — conformal p-values

### CAL-001 · The p-value is `(1 + #{s_i >= s}) / (n + 1)`
- **Area:** `calibrate/conformal.py::ConformalCalibrator.p_value`
- **Type:** contract
- **Priority:** P1
- **Precondition:** 99 calibration scores `0..98`, observation 90
- **Steps:** compute
- **Expected:** the value computed by hand from the formula, to the digit
- **Why:** the `1 +` and the `n + 1` **are** the guarantee. Computing
  `#{s_i >= s} / n` makes the smallest p-value zero, so a point more extreme
  than everything seen rejects at any level at all — and it is right about 95%
  of the time on twenty points, which is exactly the kind of wrong that ships.

### CAL-002 · The finite-sample guarantee holds empirically
- **Area:** `calibrate/conformal.py::ConformalCalibrator`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a seeded exchangeable stream, 200 calibration points,
  10,000 test points drawn from the same distribution
- **Steps:** count how many produce `p <= alpha`, for alpha in 0.01, 0.05, 0.1
- **Expected:** at most alpha in each case, within binomial noise
- **Why:** the whole claim of the module, stated as "at most alpha, exactly, in
  finite samples, with no distributional assumption". Asserting the formula is
  not asserting the property.

### CAL-003 · The counterfactual: dropping the `+1` breaks the guarantee
- **Area:** `calibrate/conformal.py::ConformalCalibrator.p_value`
- **Type:** regression
- **Priority:** P1
- **Precondition:** as CAL-002, with a deliberately altered local copy of the
  formula
- **Steps:** rerun the coverage check
- **Expected:** the realised false-alarm rate exceeds alpha
- **Why:** a control that cannot fail is worth nothing, and this one's failure
  mode is subtle enough that only the counterfactual demonstrates it.

### CAL-004 · The smallest expressible p-value is reported as the resolution
- **Area:** `calibrate/conformal.py::ConformalCalibrator.resolution`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 50 unweighted calibration points
- **Steps:** read `resolution`
- **Expected:** `1/51` ≈ 0.0196
- **Why:** a monitor asked for alpha = 0.001 on fifty points cannot honour it,
  and reporting the ceiling is the difference between a system that prints
  `p = 0.0002` from fifty points and one that says what it knows.

### CAL-005 · A budget finer than the resolution is not honoured, and says so
- **Area:** `calibrate/conformal.py::ConformalP.honours`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a p-value from 50 points
- **Steps:** `honours(0.001)` and `honours(0.05)`
- **Expected:** false then true
- **Why:** it is the check that turns a dial into an honest one.

### CAL-006 · A saturated p-value is reported as an upper bound
- **Area:** `calibrate/conformal.py::ConformalP.is_saturated` · `describe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** an observation more extreme than every calibration point
- **Steps:** compute and describe
- **Expected:** `is_saturated` true and a description reading `p ≤ ...`, not
  `p = ...`
- **Why:** a monitor reporting a saturated p-value as a point estimate is
  claiming precision it does not have, and the claim reaches a slide.

### CAL-007 · Below the minimum, no p-value is produced
- **Area:** `calibrate/conformal.py::MINIMUM_CALIBRATION`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 19 and 20 calibration points
- **Steps:** compute at each
- **Expected:** `Uncalibrated` then a `ConformalP`; the refusal names the count,
  the minimum and the coarsest available p-value
- **Why:** a monitor whose finest distinction is "one in eleven" cannot honour
  any useful budget, and returning a number anyway is the failure.

### CAL-008 · `Uncalibrated` is a type, not a `None`
- **Area:** `calibrate/conformal.py::Uncalibrated`
- **Type:** contract
- **Priority:** P1
- **Precondition:** the three reasons — too few points, a non-finite score, a
  zero-weight window
- **Steps:** produce each
- **Expected:** an `Uncalibrated` carrying a distinct reason and the count
- **Why:** "not enough history" and "the calibration set is degenerate" lead to
  different actions, and a monitor that silently returns nothing is a monitor
  that silently stops working.

### CAL-009 · A non-finite observation is refused
- **Area:** `calibrate/conformal.py::ConformalCalibrator.p_value`
- **Type:** negative
- **Priority:** P2
- **Precondition:** a well-calibrated set
- **Steps:** compute for `nan` and for `inf`
- **Expected:** `Uncalibrated` in both
- **Why:** a NaN score would sort unpredictably in `bisect` and produce a
  plausible p-value from nothing.

### CAL-010 · Non-finite calibration points are dropped, and `n` reflects it
- **Area:** `calibrate/conformal.py::ConformalCalibrator.__init__`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** 30 scores of which 5 are `nan`
- **Steps:** construct
- **Expected:** `n == 25`, and the resolution computed from 25
- **Why:** counting the dropped points would overstate the resolution, which is
  the number everything else is qualified by.

### CAL-011 · Calibration scores are held sorted and lookup is a binary search
- **Area:** `calibrate/conformal.py::ConformalCalibrator`
- **Type:** performance
- **Priority:** P2
- **Precondition:** 100,000 calibration points
- **Steps:** compute 10,000 p-values
- **Expected:** completes inside a stated budget; the implementation uses
  `bisect` and the suffix sums rather than a scan
- **Why:** this is called once per monitor per run and a fleet is tens of
  thousands of monitors.

### CAL-012 · Ties are counted as at-least-as-extreme
- **Area:** `calibrate/conformal.py::ConformalCalibrator.p_value`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** calibration scores with ten copies of the value 50, observed
  score exactly 50
- **Steps:** compute
- **Expected:** all ten counted — `bisect_left` puts the index before them
- **Why:** `>=` versus `>` at a tie is the difference between a valid p-value
  and one that is anti-conservative on discrete scores, which row counts are.

### CAL-013 · An observation below everything gives a p-value of one
- **Area:** `calibrate/conformal.py::ConformalCalibrator.p_value`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an observation less extreme than every calibration point
- **Steps:** compute
- **Expected:** `(n + 1)/(n + 1) == 1.0`
- **Why:** the other end of the range, and the one an implementation with an
  off-by-one produces above 1.

### CAL-014 · Recency weighting decays oldest first with the most recent at one
- **Area:** `calibrate/conformal.py::recency_weights`
- **Type:** functional
- **Priority:** P2
- **Precondition:** `count=100, half_life=50`
- **Steps:** compute
- **Expected:** ascending weights, the last exactly 1.0, the fiftieth from the
  end exactly 0.5
- **Why:** the half-life is the parameter an operator sets, and it has to mean
  what its name says.

### CAL-015 · `recency_weights(0)` is empty and a zero half-life does not divide by zero
- **Area:** `calibrate/conformal.py::recency_weights`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `count=0`, and `half_life=0`
- **Steps:** compute both
- **Expected:** `()`, and a finite weight vector via the `1e-9` floor
- **Why:** both are reachable from configuration.

### CAL-016 · Effective sample size, not `n`, bounds the resolution
- **Area:** `calibrate/conformal.py::ConformalCalibrator.effective_n`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 180 points with a 14-day half-life
- **Steps:** read `effective_n` and `resolution`
- **Expected:** an effective n far below 180 and a resolution computed from it
- **Why:** quoting `n` is how a monitor with a six-month window and a two-week
  half-life claims a precision it has about fourteen points' worth of.

### CAL-017 · Effective n equals n when unweighted
- **Area:** `calibrate/conformal.py::ConformalCalibrator.effective_n`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** no weights
- **Steps:** read
- **Expected:** exactly `n`
- **Why:** the formula `(Σw)²/Σw²` must reduce cleanly, or every unweighted
  monitor's resolution is subtly wrong.

### CAL-018 · A weighted p-value is marked inexact and carries a coverage gap
- **Area:** `calibrate/conformal.py::ConformalP.exact` · `_coverage_gap`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a weighted calibrator
- **Steps:** compute; describe
- **Expected:** `exact` false, a non-zero gap, and a description saying validity
  is approximate and by how much
- **Why:** weighting trades exactness for robustness, and the honest reading of
  a weighted conformal p-value is that the approximation is not free.

### CAL-019 · The coverage gap is labelled indicative wherever it surfaces
- **Area:** `calibrate/conformal.py::ConformalCalibrator._coverage_gap`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a weighted p-value rendered into an alert and into the API
- **Steps:** read both
- **Expected:** the number never appears as a proven bound
- **Why:** the exact bound involves unobservable total-variation distances; what
  is reported is how much calibration mass the weighting discards. A number that
  overstates its own rigour is worse than no number, because it is the one that
  ends up in a slide.

### CAL-020 · An unweighted p-value has a coverage gap of exactly zero
- **Area:** `calibrate/conformal.py::ConformalCalibrator._coverage_gap`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** no weights
- **Steps:** read
- **Expected:** 0.0 and `exact` true
- **Why:** a spurious gap on the exact case would make every monitor disclose an
  approximation it does not have.

### CAL-021 · A whole window of zero weight is refused with a remedy
- **Area:** `calibrate/conformal.py::ConformalCalibrator.p_value`
- **Type:** negative
- **Priority:** P2
- **Precondition:** weights that have all decayed to zero
- **Steps:** compute
- **Expected:** `Uncalibrated` telling the operator to widen the window or
  lengthen the half-life
- **Why:** it is what an aggressive half-life over a long window eventually
  produces, and the arithmetic would otherwise divide by zero.

### CAL-022 · Mismatched weights are refused at construction
- **Area:** `calibrate/conformal.py::ConformalCalibrator.__init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** 30 scores and 29 weights
- **Steps:** construct
- **Expected:** `ValueError` naming both counts
- **Why:** silently zipping to the shorter would drop the most recent
  observation, which is the one the weighting exists to emphasise.

### CAL-023 · The quantile is the threshold at which a p-value would equal alpha
- **Area:** `calibrate/conformal.py::ConformalCalibrator.quantile`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a calibrated set
- **Steps:** take `quantile(0.05)`, then compute the p-value at that score
- **Expected:** a p-value at or just below 0.05
- **Why:** it is what a screen renders as "this monitor fires above 41,200
  rows", and a threshold inconsistent with the p-value beside it destroys both.

### CAL-024 · An unachievable alpha returns nothing rather than the largest score
- **Area:** `calibrate/conformal.py::ConformalCalibrator.quantile`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 50 points, alpha 0.001
- **Steps:** `quantile`
- **Expected:** `None`
- **Why:** returning the largest score seen would render a threshold that means
  nothing, and it would look exactly like a working one.

## Calibration — adaptive levels

### CAL-025 · A target outside (0, 1) is refused
- **Area:** `calibrate/conformal.py::AdaptiveCalibrator.__init__`
- **Type:** negative
- **Priority:** P2
- **Precondition:** none
- **Steps:** construct with 0, 1, -0.1 and 5
- **Expected:** `ValueError` explaining that the dial expresses how often a
  normal observation may alert
- **Why:** a target of 5 would be read as "five per cent" by the person typing
  it and as "always alert" by the code.

### CAL-026 · The level tightens when recent alerting exceeds the budget
- **Area:** `calibrate/conformal.py::AdaptiveCalibrator.observe`
- **Type:** functional
- **Priority:** P1
- **Precondition:** target 0.05, twenty consecutive alerts
- **Steps:** observe each
- **Expected:** the current level falls below the target; `is_tightened` true
- **Why:** it is the response to drift that keeps the long-run rate at target
  without a human recalibrating.

### CAL-027 · The level loosens when alerting runs below the budget
- **Area:** `calibrate/conformal.py::AdaptiveCalibrator.observe`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a long run of non-alerts
- **Steps:** observe
- **Expected:** the level rises above the target, bounded by the ceiling
- **Why:** a monitor below budget is wasting sensitivity, and the adaptation is
  what spends it.

### CAL-028 · The level stays inside its floor and ceiling
- **Area:** `calibrate/conformal.py::AdaptiveCalibrator`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 10,000 alerts, then 10,000 non-alerts
- **Steps:** observe
- **Expected:** the level never leaves `[1e-4, 0.5]`
- **Why:** an unbounded level reaches zero and the monitor stops firing
  permanently, or reaches one and everything fires.

### CAL-029 · The long-run rate converges to the target under drift
- **Area:** `calibrate/conformal.py::AdaptiveCalibrator`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a seeded stream whose distribution shifts twice
- **Steps:** run 5,000 observations through the calibrator
- **Expected:** the realised alert rate over the whole run is close to the
  target
- **Why:** this is the Gibbs-Candès guarantee and the only one that survives a
  regime change. It is weaker than exact validity and it is the right one for a
  monitor that has to keep running.

### CAL-030 · The update is on the alert indicator, not on the p-value
- **Area:** `calibrate/conformal.py::AdaptiveCalibrator.observe`
- **Type:** contract
- **Priority:** P1
- **Precondition:** two runs whose alerts coincide but whose p-values differ
  wildly
- **Steps:** compare the resulting levels
- **Expected:** identical
- **Why:** it is what makes the long-run guarantee hold without assuming
  anything about the score distribution, and an "improvement" that weighted by
  how extreme an alert was would quietly remove it.

### CAL-031 · A powerless monitor is reported, not adapted harder
- **Area:** `calibrate/conformal.py::AdaptiveLevel.is_powerless`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 60% of recent p-values saturated
- **Steps:** read the level and describe it
- **Expected:** `is_powerless` true and a description saying there is no
  threshold between alerting on all of them and none, and that the calibration
  set no longer describes the data
- **Why:** the realised rate alone looks like an ordinary overshoot, and
  adapting harder is the one thing that cannot work.

### CAL-032 · The saturation boundary is exactly half
- **Area:** `calibrate/conformal.py::AdaptiveLevel.is_powerless`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** saturation of 0.49 and 0.50
- **Steps:** read the flag
- **Expected:** false then true
- **Why:** the threshold is a bare constant, and the message it gates is a
  strong one.

### CAL-033 · The window bounds what "recent" means
- **Area:** `calibrate/conformal.py::AdaptiveCalibrator.observe`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `window=100`, 150 observations
- **Steps:** observe; read `realised`
- **Expected:** computed over the last 100, and the saturation list stays the
  same length as the alert list
- **Why:** the two lists are popped together; a divergence between them would
  attribute one observation's saturation to another's alert.

### CAL-034 · `judge` carries the saturation signal through
- **Area:** `calibrate/conformal.py::AdaptiveCalibrator.judge`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a saturated p-value
- **Steps:** `judge` it; compare with `test` plus `observe` called separately
  without the flag
- **Expected:** `judge` records the saturation; the separated form loses it
- **Why:** the whole point of the signal is that it appears when nobody is
  watching for it, and the convenience is what makes it hard to lose.

### CAL-035 · `test` compares against the current level, not the target
- **Area:** `calibrate/conformal.py::AdaptiveCalibrator.test`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a tightened calibrator
- **Steps:** test a p-value between the current level and the target
- **Expected:** no alert
- **Why:** "we rejected at 0.003, not the 0.01 you set" is the answer to "why
  did this not alert?", and a test against the declared level would make the
  adaptation decorative.

### CAL-036 · The level describes itself in a sentence an operator can act on
- **Area:** `calibrate/conformal.py::AdaptiveLevel.describe`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** at target, tightened, loosened and powerless
- **Steps:** describe each
- **Expected:** four distinct sentences, each naming the current level, the
  declared one and the reason
- **Why:** an adaptive threshold nobody can explain is indistinguishable from a
  broken one.

## Calibration — validity monitoring

### CAL-037 · A monitor firing at its nominal rate is reported calibrated
- **Area:** `calibrate/validity.py::ValidityMonitor.report`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 500 p-values with 5% below 0.05, nominal 0.05
- **Steps:** report
- **Expected:** `Validity.CALIBRATED`, `promise_holds` true, and a disclosure
  naming both the promise and the realised rate
- **Why:** the positive control, and the sentence every alert carries.

### CAL-038 · A monitor firing far above its promise is reported uncalibrated
- **Area:** `calibrate/validity.py::ValidityMonitor.report`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 500 p-values with 20% below a nominal 0.05
- **Steps:** report
- **Expected:** `Validity.UNCALIBRATED`, with the multiple of the promised rate,
  the interval, and the instruction to treat the level as an intention
- **Why:** a monitor that has quietly stopped being calibrated looks exactly
  like one that has not, and the number on the dial goes on being quoted.

### CAL-039 · The degradation decision allows for sampling noise
- **Area:** `calibrate/validity.py::DEGRADATION_CONFIDENCE`
- **Type:** functional
- **Priority:** P1
- **Precondition:** 100 observations at a realised 0.09 against a nominal 0.05
- **Steps:** report
- **Expected:** not `UNCALIBRATED` — two standard errors is not evidence of much
- **Why:** a validity monitor that flags on any departure flags constantly and
  is switched off, which is a particularly embarrassing death for the component
  whose job is calibration.

### CAL-040 · The confidence is tight because this runs fleet-wide
- **Area:** `calibrate/validity.py::DEGRADATION_CONFIDENCE`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** read the constant and its justification
- **Expected:** 0.999, with the reasoning that 95% would wrongly label one
  monitor in twenty at any moment
- **Why:** the constant is a fleet-scale decision and reads as arbitrary without
  it.

### CAL-041 · Too little history is `UNKNOWN`, not calibrated
- **Area:** `calibrate/validity.py::MINIMUM_OBSERVATIONS`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** 49 and 50 observations
- **Steps:** report at each
- **Expected:** `UNKNOWN` then a verdict; the unknown disclosure says the
  nominal level is an intention rather than a measurement
- **Why:** a new monitor has not earned the promise yet, and letting it claim
  one is how a fleet reports itself as fully calibrated on day one.

### CAL-042 · Firing less often than promised is drifting, not degraded
- **Area:** `calibrate/validity.py::ValidityMonitor.report`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a realised 0.005 against a nominal 0.05, outside the
  interval
- **Steps:** report
- **Expected:** `Validity.DRIFTING` with the reason that the promise holds and
  sensitivity is being wasted
- **Why:** a conservative monitor keeps its promise; treating it as a breach
  conflates waste with dishonesty.

### CAL-043 · Mildly liberal is drifting; badly liberal is uncalibrated
- **Area:** `calibrate/validity.py::ValidityMonitor.report`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** realised rates at 1.9× and 2.1× the nominal, both outside
  the interval
- **Steps:** report
- **Expected:** `DRIFTING` then `UNCALIBRATED` — the severity boundary is at a
  factor of two
- **Why:** the early warning and the degradation are different messages to
  different people, and the boundary between them is a bare comparison.

### CAL-044 · The liberal flag compares the nominal against the interval
- **Area:** `calibrate/validity.py::Point.is_liberal`
- **Type:** regression
- **Priority:** P1
- **Precondition:** a point whose interval lies entirely above its nominal level
- **Steps:** read the flag
- **Expected:** true
- **Why:** the first version compared the empirical rate against its own upper
  bound, and an estimate is always inside its own interval — a check that could
  not fire, on the module whose job is checking that things can.

### CAL-045 · A conservative point is not flagged liberal
- **Area:** `calibrate/validity.py::Point.is_liberal`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** an interval entirely below the nominal level
- **Steps:** read
- **Expected:** false
- **Why:** the counterfactual of CAL-044; a flag that is always true is as
  useless as one that is never true.

### CAL-046 · The curve is evaluated across three orders of magnitude
- **Area:** `calibrate/validity.py::CURVE_LEVELS`
- **Type:** contract
- **Priority:** P2
- **Precondition:** none
- **Steps:** read the levels; build a curve
- **Expected:** seven points from 0.001 to 0.2, each with an interval
- **Why:** a curve that only checks 0.05 says nothing about a monitor asked for
  0.001, and the budget dial genuinely spans that range.

### CAL-047 · Calibration error is the mean absolute deviation across levels
- **Area:** `calibrate/validity.py::CalibrationCurve.calibration_error`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a curve with known deviations
- **Steps:** compute
- **Expected:** the hand-computed mean; `meets_target` against 0.02
- **Why:** it is the wave's headline number and the thing a claim about
  calibration is measured by.

### CAL-048 · An empty curve has zero error and does not claim to meet the target
- **Area:** `calibrate/validity.py::CalibrationCurve`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** no observations
- **Steps:** read `calibration_error` and `meets_target`
- **Expected:** either a guarded `meets_target`, or the curve carrying the same
  "not enough observations" qualification the report does
- **Why:** with no points the error is 0.0 and `meets_target` is therefore
  **true** — a monitor that has seen nothing reports that it meets the wave's
  calibration target. The report's `UNKNOWN` status covers this; the curve,
  serialised on its own, does not.

### CAL-049 · The Wilson interval behaves at the ends of the range
- **Area:** `calibrate/validity.py::wilson_interval`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** `(0, 500)`, `(500, 500)`, `(1, 500)` at 0.999 confidence
- **Steps:** compute
- **Expected:** bounds inside `[0, 1]` in every case, and a non-degenerate
  interval at zero successes
- **Why:** the normal approximation reaches below zero for small rates, and
  small rates are the entire subject here. An interval clamped to zero is a
  number that looks like a bound and is not one.

### CAL-050 · Zero trials gives the widest possible interval
- **Area:** `calibrate/validity.py::wilson_interval`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `(0, 0)`
- **Steps:** compute
- **Expected:** `(0.0, 1.0)`
- **Why:** no observations must mean no information, not a narrow interval
  around zero.

### CAL-051 · The z quantile is right for the confidences actually used
- **Area:** `calibrate/validity.py::_z_for`
- **Type:** contract
- **Priority:** P2
- **Precondition:** 0.95, 0.99, 0.999
- **Steps:** compute
- **Expected:** 1.95996, 2.5758, 3.2905 to five decimals
- **Why:** the bisection is "slow and obviously correct" and nothing pins its
  output; a wrong z makes every interval the wrong width and every verdict
  plausible.

### CAL-052 · The disclosure goes on every alert, not the dashboard
- **Area:** `calibrate/validity.py::ValidityReport.disclosure`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** an uncalibrated monitor raising an alert
- **Steps:** trace the alert to its delivered form — email, webhook, console
- **Expected:** the disclosure on each
- **Why:** a degradation visible only on a status page is a degradation nobody
  sees, because the person reading the alert at three in the morning is not on
  the status page.

### CAL-053 · The window bounds memory and the oldest observations fall out
- **Area:** `calibrate/validity.py::ValidityMonitor.observe`
- **Type:** performance
- **Priority:** P2
- **Precondition:** `window=500`, 10,000 observations
- **Steps:** observe; read `observations`
- **Expected:** 500, holding the most recent
- **Why:** a fleet of tens of thousands of monitors each retaining every p-value
  is a memory leak with a statistical justification.

### CAL-054 · The monitor's own weak point is documented
- **Area:** `calibrate/validity.py::ValidityMonitor`
- **Type:** documentation
- **Priority:** P2
- **Precondition:** none
- **Steps:** read the class docstring against how the product actually feeds it
- **Expected:** the acknowledgement that on live data nobody knows which
  observations were normal, so this reads as "how often does this monitor fire"
- **Why:** it equals the false-alarm rate only when genuine incidents are rare,
  and a reader of the disclosure is entitled to know which of the two they are
  being told.

## Calibration — selection and the budget dial

### CAL-055 · Benjamini-Hochberg takes the largest k, not the first failure
- **Area:** `calibrate/select.py::benjamini_hochberg`
- **Type:** contract
- **Priority:** P1
- **Precondition:** p-values where an early one sits above its line and a later
  one below it
- **Steps:** run
- **Expected:** the count reaches the later index
- **Why:** stopping at the first failure is uniformly less powerful and quietly
  wrong, and it is the mistake almost every hand-rolled implementation makes.

### CAL-056 · BH controls the false discovery rate empirically
- **Area:** `calibrate/select.py::benjamini_hochberg`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a seeded corpus of 1,000 hypotheses, 100 genuinely non-null
- **Steps:** select at alpha 0.05 over many draws
- **Expected:** the realised proportion of false discoveries among rejections is
  at most 0.05 on average
- **Why:** the procedure's whole claim, and asserting the arithmetic is not
  asserting the property.

### CAL-057 · BY costs about `H(m)` in sensitivity and reports it
- **Area:** `calibrate/select.py::Method.BY` · `Selection.dependence_price`
- **Type:** functional
- **Priority:** P1
- **Precondition:** the same corpus under BH and under BY
- **Steps:** select under both
- **Expected:** BY rejects strictly fewer; `dependence_price` is `H(m)`; the
  summary says what assuming nothing about dependence costs
- **Why:** "we assume nothing about dependence" sounds free and is not — on a
  large estate it is a factor of eight, and what it costs is the quiet findings.

### CAL-058 · The harmonic approximation agrees with the exact sum at the crossover
- **Area:** `calibrate/select.py::_harmonic`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** counts of 999, 1000 and 1001
- **Steps:** compare the exact sum with the Euler-Maclaurin form
- **Expected:** agreement to well within the precision that matters
- **Why:** a discontinuity at the crossover would make an estate of 1,000
  monitors behave differently from one of 999, for no reason anybody could
  explain.

### CAL-059 · `_harmonic` of zero and one are safe
- **Area:** `calibrate/select.py::_harmonic`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** 0 and 1
- **Steps:** compute
- **Expected:** 1.0 in both
- **Why:** a zero here would scale alpha to infinity and reject everything.

### CAL-060 · Simes gives a family one p-value
- **Area:** `calibrate/select.py::simes`
- **Type:** contract
- **Priority:** P1
- **Precondition:** a family of five p-values
- **Steps:** compute
- **Expected:** `min_i (m/i) * p_(i)`, hand-computed, capped at 1.0
- **Why:** it is what makes the hierarchy cheaper as well as better shaped, and
  it is valid under the same dependence conditions as BH, which is why the two
  travel together.

### CAL-061 · Simes of an empty family is one
- **Area:** `calibrate/select.py::simes`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `[]`
- **Steps:** compute
- **Expected:** 1.0
- **Why:** a family with no monitors must not be opened.

### CAL-062 · A quiet family is not opened, and the count is reported
- **Area:** `calibrate/select.py::HierarchicalSelector.select`
- **Type:** functional
- **Priority:** P1
- **Precondition:** ten datasets, one with failures and nine quiet
- **Steps:** select
- **Expected:** findings only from the failing dataset;
  `families_unopened == 9`
- **Why:** testing the family first is what stops a quiet dataset's monitors
  spending the estate's error budget — and the count is the efficiency of the
  hierarchy and also its risk.

### CAL-063 · The within-family level is scaled by how many families survived
- **Area:** `calibrate/select.py::HierarchicalSelector.select`
- **Type:** functional
- **Priority:** P1
- **Precondition:** twenty families, four opened, alpha 0.05
- **Steps:** select; read each finding's threshold
- **Expected:** the scaled level of 0.01
- **Why:** the Benjamini-Bogomolov scaling is what keeps the average FDR over
  selected families at alpha rather than inflating it by the number examined.

### CAL-064 · A family that fails wholesale becomes one finding
- **Area:** `calibrate/select.py::HierarchicalSelector._roll_up`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a dataset whose feed did not arrive: 400 controls, all with
  p-values at the floor
- **Steps:** select
- **Expected:** one finding at the dataset level covering all 400,
  `rolled_into_parent == 399`
- **Why:** the reader otherwise gets 400 alerts describing one incident, and the
  one that mattered — a quietly wrong LEI on another dataset — is on page nine.

### CAL-065 · Roll-up is decided before the multiplicity correction
- **Area:** `calibrate/select.py::HierarchicalSelector.select`
- **Type:** regression
- **Priority:** P1
- **Precondition:** the 400-control family, selected under **BY**
- **Steps:** select
- **Expected:** the roll-up still fires
- **Why:** asking afterwards was a real defect — under BY the correction left
  four survivors out of four hundred, no roll-up fired, and the report was four
  arbitrary members of one incident. The conservatism of the procedure had
  silently become a statement about the incident's extent, which it is not.

### CAL-066 · A partial failure is not rolled up
- **Area:** `calibrate/select.py::ROLLUP_FRACTION`
- **Type:** boundary
- **Priority:** P1
- **Precondition:** families with exactly 59% and 61% of monitors failing
- **Steps:** select
- **Expected:** individual findings then a roll-up
- **Why:** rolling up a partial failure hides which parts are broken, and "most
  of the dataset" is a different message from "half of it".

### CAL-067 · A small family is never rolled up
- **Area:** `calibrate/select.py::ROLLUP_MINIMUM`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** a family of four, all failing
- **Steps:** select
- **Expected:** four findings
- **Why:** three monitors failing is three findings; calling it an incident is a
  summary of nothing.

### CAL-068 · A rolled-up finding carries the family's own p-value
- **Area:** `calibrate/select.py::HierarchicalSelector._roll_up`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a family with one catastrophic control and 399 marginal ones
- **Steps:** select; read the finding's p-value
- **Expected:** the Simes value over all members, not the smallest child's
- **Why:** the smallest child's reads as the severity of the incident and is
  not: one control catastrophic and the rest marginal is a different incident
  from uniformly bad.

### CAL-069 · A rolled-up finding is reported one level up
- **Area:** `calibrate/select.py::_parent_level`
- **Type:** functional
- **Priority:** P2
- **Precondition:** a family of `CHECK`-level hypotheses, and one of
  `DOMAIN`-level
- **Steps:** roll up each
- **Expected:** `ATTRIBUTE` for the first; `DOMAIN` again for the second, since
  it cannot go higher
- **Why:** the depth arithmetic is clamped at zero, and a level that wrapped
  would put an estate-wide incident under a check.

### CAL-070 · Findings are ordered by p-value and then by identity
- **Area:** `calibrate/select.py::HierarchicalSelector.select`
- **Type:** functional
- **Priority:** P2
- **Precondition:** findings with tied p-values
- **Steps:** select twice with the hypotheses shuffled
- **Expected:** the same order both times
- **Why:** an alert list that reorders between runs cannot be diffed, and a
  reader cannot tell a new finding from a moved one.

### CAL-071 · Selecting nothing returns an empty selection, not an error
- **Area:** `calibrate/select.py::HierarchicalSelector.select`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** no hypotheses, and hypotheses none of which reject
- **Steps:** select
- **Expected:** an empty `Selection` carrying the method and alpha, and a
  summary saying zero findings from n monitors
- **Why:** a quiet night is the commonest outcome and it must render as a
  sentence rather than as an absence.

### CAL-072 · The selection states its own assumptions
- **Area:** `calibrate/select.py::Selection.describe` · `Method.assumes`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a selection under each method
- **Steps:** describe
- **Expected:** the sentence naming what the procedure assumes about dependence
- **Why:** a procedure whose assumptions nobody can name is a procedure nobody
  should trust.

### CAL-073 · A business budget becomes a per-test level
- **Area:** `calibrate/select.py::Budget.alpha`
- **Type:** functional
- **Priority:** P1
- **Precondition:** two false alarms a month across 10,000 monitor runs
- **Steps:** `alpha`
- **Expected:** 0.0002, and a description stating the arithmetic in the open
- **Why:** every competitor has a sensitivity slider and none can say what
  number it puts on the wall.

### CAL-074 · A budget over zero tests is zero, not a division by zero
- **Area:** `calibrate/select.py::Budget.alpha`
- **Type:** boundary
- **Priority:** P2
- **Precondition:** `tests_per_period=0`
- **Steps:** `alpha`
- **Expected:** 0.0
- **Why:** a newly declared domain has no runs yet, and the dial is rendered
  before the first one.

### CAL-075 · A budget more generous than one alarm per test is capped
- **Area:** `calibrate/select.py::Budget.alpha`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** 100 false alarms across 10 runs
- **Steps:** `alpha`
- **Expected:** 1.0
- **Why:** an alpha above one would make every comparison trivially true and the
  monitor would alert on everything.

### CAL-076 · An unachievable budget is refused with three concrete options
- **Area:** `calibrate/select.py::Budget.shortfall` · `achievable_with`
- **Type:** functional
- **Priority:** P1
- **Precondition:** a budget needing 0.0002 against a resolution of 0.011
- **Steps:** `shortfall`
- **Expected:** the needed level, the achievable one, the implied number of
  false alarms, and the count of observations required
- **Why:** this is the question nobody asks and the one that decides whether the
  dial is honest. Saying so beats printing a threshold that means nothing.

### CAL-077 · An achievable budget has no shortfall text
- **Area:** `calibrate/select.py::Budget.shortfall`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** an achievable budget
- **Steps:** `shortfall`
- **Expected:** the empty string
- **Why:** a warning rendered on the happy path is a warning that gets ignored
  on the unhappy one.

### CAL-078 · Power is labelled an approximation wherever it appears
- **Area:** `calibrate/select.py::power_at`
- **Type:** documentation
- **Priority:** P1
- **Precondition:** a rendered sensitivity dial
- **Steps:** read every surface showing it
- **Expected:** the word "approximate" or equivalent on each
- **Why:** it exists so the dial can answer "what will I miss?" with a number
  rather than a shrug, and a number that forgets it is an approximation becomes
  a commitment.

### CAL-079 · Power is monotone in effect size and in alpha
- **Area:** `calibrate/select.py::power_at`
- **Type:** functional
- **Priority:** P2
- **Precondition:** effects of 0, 1, 2, 3 at alpha 0.01 and 0.05
- **Steps:** compute
- **Expected:** increasing in both; bounded to `[0, 1]`; a zero effect gives
  approximately alpha
- **Why:** a non-monotone power curve on a screen is worse than none, and the
  zero-effect identity is the sanity check that the normal tail is being
  evaluated the right way round.

### CAL-080 · Degenerate power inputs return zero rather than an infinity
- **Area:** `calibrate/select.py::power_at` · `_normal_quantile`
- **Type:** boundary
- **Priority:** P3
- **Precondition:** `n=0` and `alpha=0`
- **Steps:** compute
- **Expected:** 0.0, with no infinity reaching the caller
- **Why:** `_normal_quantile(1.0)` is `inf`, and an infinity rendered on a dial
  is a support call.
