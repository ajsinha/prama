import asyncio
import tempfile
import traceback
from pathlib import Path

from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.core.errors import ValidationError
from prama.db import Database
from prama.semantic.gitops import (
    GITOPS_VERSION,
    Drift,
    DriftDetector,
    DriftDirection,
    EstateSerialiser,
    _compact,
    _normalise,
)
from prama.semantic.services import DatasetService, RelationshipService
from prama.semantic.services.graph import ConceptService, ConnectionService, JourneyService
from prama.semantic.relationships import (
    MatchKey,
    RelationshipDeclaration,
    RelationshipKind,
    Tolerance,
)
from prama.semantic.values import Frequency, Grain, Rhythm

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")

results = {}


def record(case_id, ok, observed):
    results[case_id] = (("PASS" if ok else "FAIL"), observed)
    print(f"{case_id}: {'PASS' if ok else 'FAIL'} :: {observed}")


def make_config(tmp_dir: Path):
    return (
        ConfigurationBuilder()
        .with_defaults(DEFAULTS)
        .with_mapping(
            {
                "database": {
                    "dialect": "sqlite",
                    "sqlite": {"path": str(tmp_dir / "prama-test.db")},
                    "schema_dir": str(REPO_ROOT / "schema"),
                    "verify_on_start": True,
                },
                "security": {
                    "session_secret": "test-only-not-a-secret",
                    "cookies_https_only": False,
                },
            },
            name="test",
        )
        .build()
    )


async def new_db():
    tmp_dir = Path(tempfile.mkdtemp())
    config = make_config(tmp_dir)
    database = Database.from_config(config)
    database.initialise(applied_by="qa")
    await database.start()
    return database


async def make_tenant(database, slug="acme"):
    async with database.unit_of_work() as uow:
        tenant = uow.tenants.create(slug=slug, display_name=slug)
        await uow.flush()
        return str(tenant.id)


async def main():
    # ---------- SEM-232 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            dataset, version = await dsvc.declare(
                tenant_id=tenant,
                name="Positions EOD",
                description="Daily end-of-day positions.",
                purpose="risk reporting",
                domain_id=None,
                owner_id="alice",
                criticality=2,
                shape="feed",
                grain=Grain(("account_id", "instrument_id", "as_of_date"), "one per acct/instr/day"),
                rhythm=Rhythm(
                    Frequency.DAILY, arrival_by="06:30", calendar="TARGET2",
                    volume_drivers=("trading_days", "month_end"),
                ),
                temporality="snapshot",
                authoritativeness="authoritative",
                sensitivity="confidential",
                tags=["risk", "frtb"],
                authored_by="alice",
                approved_by="bob",
            )
            dataset_id = str(dataset.id)
            for i in range(3):
                await dsvc.declare_attribute(
                    tenant_id=tenant,
                    dataset_id=dataset_id,
                    name=f"attr_{i}",
                    definition=f"def {i}",
                )
            attributes = await uow.attributes.for_dataset(dataset_id, tenant_id=tenant)
        serialiser = EstateSerialiser()
        document = serialiser.dataset_document(version, attributes)
        text = serialiser.dump(document)
        restored = serialiser.load(text)
        names_in_order = [a["name"] for a in restored["attributes"]]
        ok = (
            restored == document
            and restored["spec"]["grain"]["attributes"] == list(("account_id", "instrument_id", "as_of_date"))
            and restored["spec"]["rhythm"]["volume_drivers"] == ["trading_days", "month_end"]
            and names_in_order == ["attr_0", "attr_1", "attr_2"]
        )
        record(
            "SEM-232",
            ok,
            f"round-trip equal={restored == document}; grain={restored['spec'].get('grain')}; "
            f"rhythm.volume_drivers={restored['spec'].get('rhythm', {}).get('volume_drivers')}; "
            f"attributes order={names_in_order}",
        )
    except Exception:
        record("SEM-232", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-233 ----------
    try:
        DATASET_FIELDS = set(EstateSerialiser.DATASET_FIELDS)
        # Build a document with every field non-empty to see rendered keys.
        # Use a fake object exposing the attributes dataset_document reads.
        class FakeVersion:
            slug = "x"
            name = "X"
            description = "d"
            purpose = "p"
            owner_id = "o"
            steward_id = "s"
            criticality = 1
            shape = "table"
            domain_id = "dom"
            grain_json = {"attributes": ["a"], "statement": "s"}
            rhythm_json = {"frequency": "daily"}
            temporality = "snapshot"
            authoritativeness = "authoritative"
            sensitivity = "confidential"
            jurisdiction = "UK"
            retention_days = 30
            lifecycle_state = "active"
            tags_json = ["t1"]

        document = EstateSerialiser().dataset_document(FakeVersion(), [])
        rendered_spec_keys = set(document["spec"].keys())
        rendered_metadata_keys = set(document["metadata"].keys())
        rendered_all = rendered_spec_keys | rendered_metadata_keys
        custodian_absent = "custodian_id" not in rendered_all and "custodian_id" in DATASET_FIELDS
        source_of_truth_absent = (
            "source_of_truth_id" not in rendered_all and "source_of_truth_id" in DATASET_FIELDS
        )
        slug_in_tuple_but_metadata_only = "slug" in DATASET_FIELDS and "slug" in rendered_metadata_keys
        owner_renamed = "owner_id" in DATASET_FIELDS and "owner_id" not in rendered_all and "owner" in rendered_spec_keys
        steward_renamed = (
            "steward_id" in DATASET_FIELDS and "steward_id" not in rendered_all and "steward" in rendered_spec_keys
        )
        ok = (
            custodian_absent
            and source_of_truth_absent
            and owner_renamed
            and steward_renamed
        )
        record(
            "SEM-233",
            ok,
            f"DATASET_FIELDS={sorted(DATASET_FIELDS)}; rendered keys={sorted(rendered_all)}; "
            f"custodian_id in tuple but absent from rendering={custodian_absent}; "
            f"source_of_truth_id in tuple but absent from rendering={source_of_truth_absent}; "
            f"owner_id->owner rename={owner_renamed}; steward_id->steward rename={steward_renamed}",
        )
    except Exception:
        record("SEM-233", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-234 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            dataset, _ = await dsvc.declare(tenant_id=tenant, name="DS For Attr")
            dataset_id = str(dataset.id)
            csvc = ConceptService(uow)
            concept, _ = await csvc.declare_concept(tenant_id=tenant, name="ConceptZ")
            prop, _ = await csvc.declare_property(
                tenant_id=tenant, concept_id=str(concept.id), name="PropZ"
            )
            entity, version = await dsvc.declare_attribute(
                tenant_id=tenant,
                dataset_id=dataset_id,
                name="full_attr",
                definition="the definition",
                interpretation="the interpretation",
                semantic_type="monetary_amount",
                is_cde=True,
                obligations=["FRTB"],
                unit="USD",
                currency_attribute="ccy",
                numeric_precision=18,
                numeric_scale=2,
                value_domain_json={"kind": "range", "min": 0, "max": 100},
                optionality="conditional",
                optionality_condition="required when ccy is set",
                sensitivity="pii",
                concept_property_id=str(prop.id),
                glossary_term="Notional",
            )
        document = EstateSerialiser().attribute_document(version)
        expected_fields = {
            "definition",
            "interpretation",
            "semantic_type",
            "unit",
            "currency_attribute",
            "precision",
            "scale",
            "value_domain",
            "optionality",
            "optionality_condition",
            "cde",
            "obligations",
            "sensitivity",
            "concept_property",
            "glossary_term",
        }
        missing = expected_fields - set(document.keys())
        ok = not missing and document["cde"] is True and "intercompany" not in document.get("interpretation", "")
        record(
            "SEM-234",
            ok and set(document.keys()) >= expected_fields,
            f"document keys={sorted(document.keys())}; missing expected fields={missing}",
        )
    except Exception:
        record("SEM-234", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-235 ----------
    try:
        from prama.semantic.gitops import EstateSerialiser as ES

        class FakeRelVersion:
            kind = "reconciles_with"
            from_dataset_id = "d1"
            to_dataset_id = "d2"
            name = "n"
            description = ""
            match_keys_json = [{"left": "id", "right": None}]
            compare_json = ["amount"]
            cardinality = "many_to_many"
            tolerance_json = {"absolute": 1.0, "relative": None, "currency": "EUR", "rounding_scale": None}
            offset_json = None
            filter_expression = None
            owner_id = None
            criticality = 4
            status = "confirmed"

        doc = ES().relationship_document(FakeRelVersion())
        tolerance = doc["spec"].get("tolerance", {})
        match_keys = doc["spec"].get("match_keys", [])
        ok = (
            "relative" not in tolerance
            and all("right" not in mk for mk in match_keys)
            and tolerance.get("absolute") == 1.0
        )
        record(
            "SEM-235",
            ok,
            f"tolerance={tolerance}; match_keys={match_keys}",
        )
    except Exception:
        record("SEM-235", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-236 ----------
    try:
        payload = {
            "absolute": 0.0,
            "retention_days": 0,
            "case_sensitive": False,
            "lateness_tolerance_seconds": 0.0,
            "nested": {"a": 0, "b": 0.0, "c": False},
        }
        compacted = _compact(payload)
        checks = {
            "absolute": "absolute" in compacted and compacted["absolute"] == 0.0,
            "retention_days": "retention_days" in compacted and compacted["retention_days"] == 0,
            "case_sensitive": "case_sensitive" in compacted and compacted["case_sensitive"] is False,
            "lateness_tolerance_seconds": (
                "lateness_tolerance_seconds" in compacted
                and compacted["lateness_tolerance_seconds"] == 0.0
            ),
            "nested.a": "nested" in compacted and compacted.get("nested", {}).get("a") == 0,
            "nested.b": "nested" in compacted and compacted.get("nested", {}).get("b") == 0.0,
            "nested.c": "nested" in compacted and compacted.get("nested", {}).get("c") is False,
        }
        ok = all(checks.values())
        record(
            "SEM-236",
            ok,
            f"compacted={compacted}; per-field survival={checks}",
        )
    except Exception:
        record("SEM-236", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-237 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            dataset, version = await dsvc.declare(
                tenant_id=tenant,
                name="Grain DS",
                grain=Grain(("account_id", "as_of_date"), "one row per account per day"),
            )
        document = EstateSerialiser().dataset_document(version, [])
        grain = document["spec"]["grain"]
        ok = isinstance(grain, dict) and grain.get("attributes") == ["account_id", "as_of_date"] and "statement" in grain
        # Confirm Grain.from_dict can rebuild it
        rebuilt = Grain.from_dict(grain) if hasattr(Grain, "from_dict") else None
        record(
            "SEM-237",
            ok,
            f"grain={grain}; Grain.from_dict works={rebuilt is not None}",
        )
    except Exception:
        record("SEM-237", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-238, SEM-239 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            dsvc = DatasetService(uow)
            sub, sub_v = await dsvc.declare(tenant_id=tenant, name="Sub-ledger")
            gl, gl_v = await dsvc.declare(tenant_id=tenant, name="General Ledger")
            _, rel_version = await RelationshipService(uow).declare(
                tenant_id=tenant,
                declaration=RelationshipDeclaration(
                    kind=RelationshipKind.RECONCILES_WITH,
                    from_dataset_id=str(sub.id),
                    to_dataset_id=str(gl.id),
                    match_keys=(MatchKey("account_code"),),
                    compare=("amount",),
                    tolerance=Tolerance(absolute=1.0, currency="EUR"),
                ),
            )
            jsvc = JourneyService(uow)
            _, journey_version = await jsvc.declare(
                tenant_id=tenant,
                name="J Test",
                steps=[{"kind": "dataset", "dataset_id": str(sub.id)}],
            )
        slugs = {str(sub.id): sub_v.slug, str(gl.id): gl_v.slug}
        rel_doc = EstateSerialiser().relationship_document(rel_version, slug_of=slugs)
        ok238 = (
            rel_doc["spec"]["from"] == sub_v.slug
            and rel_doc["spec"]["to"] == gl_v.slug
            and rel_doc["spec"]["from"] != str(sub.id)
        )
        journey_doc = EstateSerialiser().journey_document(journey_version, slug_of=slugs)
        ok238 = ok238 and journey_doc["spec"]["steps"][0].get("dataset") == sub_v.slug and "dataset_id" not in journey_doc["spec"]["steps"][0]
        record(
            "SEM-238",
            ok238,
            f"relationship from/to={rel_doc['spec']['from']!r}/{rel_doc['spec']['to']!r}; "
            f"journey step={journey_doc['spec']['steps'][0]}",
        )

        # SEM-239: missing slug falls back to identifier
        rel_doc_missing_slug = EstateSerialiser().relationship_document(rel_version, slug_of={})
        ok239 = (
            rel_doc_missing_slug["spec"]["from"] == str(sub.id)
            and rel_doc_missing_slug["spec"]["to"] == str(gl.id)
        )
        record(
            "SEM-239",
            ok239,
            f"with empty slug_of: from={rel_doc_missing_slug['spec']['from']!r} "
            f"(expect raw id {sub.id!r}); to={rel_doc_missing_slug['spec']['to']!r}",
        )
    except Exception:
        record("SEM-238", False, "EXC:" + traceback.format_exc())
        record("SEM-239", False, "blocked")
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-240 ----------
    try:
        class FakeRelVersion2:
            kind = "reconciles_with"
            from_dataset_id = "d1"
            to_dataset_id = "d2"
            name = "n"
            description = "some description"
            match_keys_json = []
            compare_json = []
            cardinality = "many_to_many"
            tolerance_json = None
            offset_json = None
            filter_expression = None
            owner_id = None
            criticality = 4
            status = "confirmed"

        long_left = "a" * 80
        long_right = "b" * 80
        slugs = {"d1": long_left, "d2": long_right}
        doc1 = EstateSerialiser().relationship_document(FakeRelVersion2(), slug_of=slugs)
        name1 = doc1["metadata"]["name"]
        ok_truncated = len(name1) <= 120

        # Two relationships between the same long-named datasets collide after truncation
        class FakeRelVersion3(FakeRelVersion2):
            kind = "reconciles_with"

        doc2 = EstateSerialiser().relationship_document(FakeRelVersion3(), slug_of=slugs)
        name2 = doc2["metadata"]["name"]
        collide = name1 == name2
        record(
            "SEM-240",
            ok_truncated and collide,
            f"name len={len(name1)} (<=120: {ok_truncated}); name1==name2 (collision)={collide}; "
            f"name={name1!r}",
        )
    except Exception:
        record("SEM-240", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-241 ----------
    database = await new_db()
    try:
        tenant = await make_tenant(database)
        async with database.unit_of_work() as uow:
            entity, version = await uow.connections.create(
                tenant_id=tenant,
                name="Risk WH",
                slug="risk_wh",
                source_type="snowflake",
                credential_ref="vault://prama/risk-wh",
                config_json={"account": "acme", "auth": {"password": "hunter2-secret"}},
            )
        document = EstateSerialiser().connection_document(version)
        text = EstateSerialiser().dump(document)
        cred_present = "vault://prama/risk-wh" in text
        nested_secret_present = "hunter2-secret" in text
        record(
            "SEM-241",
            cred_present and nested_secret_present,
            f"credential_ref present={cred_present}; nested config['auth']['password'] "
            f"emitted verbatim in the exported YAML={nested_secret_present} (config_json is "
            f"copied wholesale into the document)",
        )
    except Exception:
        record("SEM-241", False, "EXC:" + traceback.format_exc())
    finally:
        await database.stop()
        database.sync_engine().dispose()

    # ---------- SEM-242 ----------
    try:
        document = {
            "apiVersion": f"prama/v{GITOPS_VERSION}",
            "kind": "Dataset",
            "metadata": {"name": "Z", "slug": "z"},
            "spec": {"description": "d", "owner": "alice", "criticality": 4, "тест": "unicode тест"},
        }
        dump1 = EstateSerialiser.dump(document)
        dump2 = EstateSerialiser.dump(document)
        ok = dump1 == dump2
        # key order preserved: name/owner near top
        lines = dump1.splitlines()
        keys_order = [l.split(":")[0].strip() for l in lines if ":" in l]
        no_escaped_unicode = "\\u" not in dump1
        no_sort = list(document["spec"].keys()) == ["description", "owner", "criticality", "тест"]
        wrapped_at_100 = all(len(l) <= 100 for l in lines)
        record(
            "SEM-242",
            ok and no_escaped_unicode and wrapped_at_100,
            f"identical dumps={ok}; unicode not escaped={no_escaped_unicode}; "
            f"all lines <=100 chars={wrapped_at_100}; sample={dump1[:200]!r}",
        )
    except Exception:
        record("SEM-242", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-243 ----------
    try:
        outcomes = []
        for bad in ["\t- not: [valid", "just a string", "[1,2,3]"]:
            try:
                EstateSerialiser().load(bad)
                outcomes.append(f"{bad!r}: NO EXCEPTION (FAIL)")
            except ValidationError as e:
                outcomes.append(f"{bad!r}: ValidationError {e.message!r}")
            except Exception as e:
                outcomes.append(f"{bad!r}: {type(e).__name__} (FAIL, expected ValidationError)")
        ok = all("ValidationError" in o and "FAIL" not in o for o in outcomes)
        record("SEM-243", ok, "; ".join(outcomes))
    except Exception:
        record("SEM-243", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-244 ----------
    try:
        base = {"apiVersion": f"prama/v{GITOPS_VERSION}", "kind": "Dataset", "metadata": {"slug": "x"}}
        outcomes = []
        for missing_key in ("apiVersion", "kind", "metadata"):
            doc = {k: v for k, v in base.items() if k != missing_key}
            import yaml as _yaml

            text = _yaml.safe_dump(doc)
            try:
                EstateSerialiser().load(text)
                outcomes.append(f"{missing_key}: NO EXCEPTION (FAIL)")
            except ValidationError as e:
                name_ok = missing_key in e.message
                remedy_ok = "export an existing object" in e.remedy.lower()
                outcomes.append(f"{missing_key}: named={name_ok} remedy_ok={remedy_ok}")
        # spec not required
        text_no_spec = _yaml.safe_dump(base)
        try:
            loaded = EstateSerialiser().load(text_no_spec)
            spec_not_required = True
        except ValidationError:
            spec_not_required = False
        ok = all("FAIL" not in o and "named=True" in o and "remedy_ok=True" in o for o in outcomes) and spec_not_required
        record(
            "SEM-244",
            ok,
            f"{'; '.join(outcomes)}; document with no 'spec' key loads OK={spec_not_required}",
        )
    except Exception:
        record("SEM-244", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-245 ----------
    try:
        outcomes = []
        try:
            EstateSerialiser().load("apiVersion: prama/v2\nkind: Dataset\nmetadata: {slug: x}\n")
            outcomes.append("prama/v2: NO EXCEPTION (FAIL)")
        except ValidationError as e:
            has_both = "1" in e.message and "2" in e.message
            outcomes.append(f"prama/v2: ValidationError has_both_versions={has_both}")
        for variant in ("v1", "1"):
            try:
                doc = EstateSerialiser().load(
                    f"apiVersion: {variant}\nkind: Dataset\nmetadata: {{slug: x}}\n"
                )
                outcomes.append(f"{variant!r}: accepted")
            except ValidationError as e:
                outcomes.append(f"{variant!r}: refused ({e.message})")
        ok = (
            "has_both_versions=True" in outcomes[0]
            and outcomes[1] == "'v1': accepted"
            and outcomes[2] == "'1': accepted"
        )
        record("SEM-245", ok, "; ".join(outcomes))
    except Exception:
        record("SEM-245", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-246 ----------
    try:
        text = EstateSerialiser().manifest(
            tenant="acme-bank", counts={"datasets": 42, "relationships": 17, "connections": 3}
        )
        restored = EstateSerialiser().load(text)
        from prama.version import SCHEMA_VERSION

        ok = (
            restored["metadata"]["tenant"] == "acme-bank"
            and restored["metadata"]["schema_version"] == SCHEMA_VERSION
            and restored["contents"] == dict(sorted({"datasets": 42, "relationships": 17, "connections": 3}.items()))
            and list(restored["contents"].keys()) == sorted(restored["contents"].keys())
        )
        record(
            "SEM-246",
            ok,
            f"manifest metadata={restored['metadata']}; contents={restored['contents']}",
        )
    except Exception:
        record("SEM-246", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-247 ----------
    try:
        store = {"only_store": {"name": "A"}, "shared": {"name": "same", "criticality": 1}}
        repository = {
            "only_git": {"name": "B"},
            "shared": {"name": "same", "criticality": 3},
        }
        drifts = DriftDetector().compare(store, repository, kind="Dataset")
        by_id = {d.identifier: d for d in drifts}
        ok = (
            by_id["only_store"].direction is DriftDirection.ONLY_IN_STORE
            and by_id["only_git"].direction is DriftDirection.ONLY_IN_GIT
            and by_id["shared"].direction is DriftDirection.DIFFERENT
            and by_id["shared"].fields == ("criticality",)
        )
        record(
            "SEM-247",
            ok,
            f"directions={[(k, v.direction.value, v.fields) for k, v in by_id.items()]}",
        )
    except Exception:
        record("SEM-247", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-248 ----------
    try:
        store = {
            "x": {
                "name": "X",
                "version": 7,
                "recorded_at": "2026-01-01",
                "authored_by": "alice",
                "change_reason": "reason",
            }
        }
        repository = {"x": {"name": "X"}}
        drifts = DriftDetector().compare(store, repository, kind="Dataset")
        ok = drifts == []
        record("SEM-248", ok, f"drifts={drifts}")
    except Exception:
        record("SEM-248", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-249 ----------
    try:
        outcomes = []
        pairs = [
            ({"tags": []}, {}),
            ({}, {"tags": None}),
            ({"tags": []}, {"tags": None}),
        ]
        for left, right in pairs:
            d = DriftDetector().compare({"x": left}, {"x": right}, kind="Dataset")
            outcomes.append((left, right, d))
        ok = all(d == [] for _, _, d in outcomes)
        record(
            "SEM-249",
            ok,
            f"pairs and results: {[(l, r, len(d)) for l, r, d in outcomes]}",
        )
    except Exception:
        record("SEM-249", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-250 ----------
    try:
        drifts1 = DriftDetector().compare(
            {"x": {"tolerance": {"absolute": 1.0, "relative": None}}},
            {"x": {"tolerance": {"relative": None, "absolute": 1.0}}},
            kind="Relationship",
        )
        drifts2 = DriftDetector().compare(
            {"x": {"tolerance": {"absolute": 1.0}}},
            {"x": {"tolerance": {"absolute": 2.0}}},
            kind="Relationship",
        )
        ok = drifts1 == [] and len(drifts2) == 1 and drifts2[0].fields == ("tolerance",)
        record(
            "SEM-250",
            ok,
            f"reordered nested mapping drifts={drifts1}; changed value drifts={[d.render() for d in drifts2]}",
        )
    except Exception:
        record("SEM-250", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-251 ----------
    try:
        drifts = DriftDetector().compare(
            {"x": {"grain": {"attributes": ["account_id", "business_date"]}}},
            {"x": {"grain": {"attributes": ["business_date", "account_id"]}}},
            kind="Dataset",
        )
        ok = len(drifts) == 1 and drifts[0].fields == ("grain",)
        record("SEM-251", ok, f"drifts={[d.render() for d in drifts]}")
    except Exception:
        record("SEM-251", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-252 ----------
    try:
        exported = {"x": {"owner": "alice", "criticality": 4}}
        edited = {"x": {"owner": "bob", "criticality": 1}}
        drifts = DriftDetector().compare(exported, edited, kind="Dataset")
        ok = len(drifts) == 1 and drifts[0].fields == tuple(sorted(["owner", "criticality"]))
        record(
            "SEM-252",
            ok,
            f"drifts={[d.render() for d in drifts]}; fields={drifts[0].fields if drifts else None}",
        )
    except Exception:
        record("SEM-252", False, "EXC:" + traceback.format_exc())

    # ---------- SEM-253 ----------
    try:
        no_drift_summary = DriftDetector.summarise([])
        three_drifts = [
            Drift(DriftDirection.ONLY_IN_STORE, "Dataset", "a"),
            Drift(DriftDirection.ONLY_IN_GIT, "Dataset", "b"),
            Drift(DriftDirection.DIFFERENT, "Dataset", "c", ("owner",)),
        ]
        three_summary = DriftDetector.summarise(three_drifts)
        ok = (
            no_drift_summary == "in sync: no drift between Prama and the repository"
            and "3 difference(s):" in three_summary
            and all(d.identifier in three_summary for d in three_drifts)
        )
        record(
            "SEM-253",
            ok,
            f"no_drift_summary={no_drift_summary!r}; three_summary={three_summary!r}",
        )
    except Exception:
        record("SEM-253", False, "EXC:" + traceback.format_exc())

    print("\n\n==== SUMMARY PART 1 ====")
    for k, (r, o) in results.items():
        print(f"{k}\t{r}\t{o}")


asyncio.run(main())
