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

<!--TABLE-->

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
