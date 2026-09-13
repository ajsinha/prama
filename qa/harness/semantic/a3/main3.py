import asyncio
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")

from prama.core.config import ConfigurationBuilder
from prama.core.config.defaults import DEFAULTS
from prama.core.errors import ConflictError, NotFoundError, ValidationError
from prama.core.clock import utc_now
from prama.db import Database
from prama.db.temporal import Provenance
from prama.semantic.services import DatasetService

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")


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


def record(case_id, outcome):
    print(f"--- {case_id}: {outcome}")


async def main():
    tmp_dir = Path(tempfile.mkdtemp())
    config = make_config(tmp_dir)
    database = Database.from_config(config)
    database.initialise(applied_by="qa")
    await database.start()
    try:
        async with database.unit_of_work() as uow:
            tenant = uow.tenants.create(slug="acme-bank", display_name="Acme Bank")
            await uow.flush()
            tenant_id = str(tenant.id)

        # ============ SEM-177: first declaration opens version 1 ============
        try:
            async with database.unit_of_work() as uow:
                entity, version = await DatasetService(uow).declare(tenant_id=tenant_id, name="V1 DS")
                obs = {
                    "version": version.version, "valid_to": version.valid_to,
                    "superseded_at": version.superseded_at, "is_current": version.is_current,
                }
            record("SEM-177", obs)
        except Exception as e:
            record("SEM-177", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-178: backdated declaration ============
        try:
            year_ago = utc_now() - timedelta(days=365)
            async with database.unit_of_work() as uow:
                entity, version = await DatasetService(uow).declare(
                    tenant_id=tenant_id, name="Backdated DS", valid_from=year_ago
                )
                before_call = utc_now()
                obs = {
                    "valid_from honoured": version.valid_from == year_ago,
                    "valid_from": version.valid_from.isoformat(),
                    "recorded_at close to now": abs((version.recorded_at - before_call).total_seconds()) < 5,
                }
            record("SEM-178", obs)
        except Exception as e:
            record("SEM-178", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-179: amendment closes one period, opens next ============
        try:
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(tenant_id=tenant_id, name="Amend DS")
                ds_id = str(entity.id)
            t_effective = utc_now() + timedelta(seconds=1)
            async with database.unit_of_work() as uow:
                v2 = await uow.datasets.amend(
                    ds_id, tenant_id=tenant_id, effective_from=t_effective,
                    provenance=Provenance(reason="grain change"), description="new grain"
                )
            async with database.unit_of_work() as uow:
                history = await uow.datasets.history(ds_id, tenant_id=tenant_id)
                current_count = 0
                for v in history:
                    if v.is_current:
                        current_count += 1
                v1_row = [v for v in history if v.version == 1][0]
                v2_row = [v for v in history if v.version == 2][0]
            obs = {
                "v1.valid_to == effective": v1_row.valid_to == t_effective,
                "v1.superseded_at is None": v1_row.superseded_at is None,
                "v2.valid_from == effective": v2_row.valid_from == t_effective,
                "v2.valid_to is None": v2_row.valid_to is None,
                "v2.superseded_at is None": v2_row.superseded_at is None,
                "exactly_one_current": current_count,
            }
            record("SEM-179", obs)
        except Exception as e:
            record("SEM-179", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-180: amendment effective before current valid_from refused ============
        try:
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(tenant_id=tenant_id, name="Amend Early DS")
                ds_id = str(entity.id)
                current_valid_from = v1.valid_from
            week_ago = current_valid_from - timedelta(days=7)
            async with database.unit_of_work() as uow:
                try:
                    await uow.datasets.amend(
                        ds_id, tenant_id=tenant_id, effective_from=week_ago,
                        description="backdated change"
                    )
                    outcome = "NO EXCEPTION (unexpected)"
                except ConflictError as e:
                    outcome = f"ConflictError: {e}"
            record("SEM-180", outcome)
        except Exception as e:
            record("SEM-180", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-181: amendment effective exactly at current valid_from accepted ============
        try:
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(tenant_id=tenant_id, name="Amend Exact DS")
                ds_id = str(entity.id)
                current_valid_from = v1.valid_from
            async with database.unit_of_work() as uow:
                try:
                    v2 = await uow.datasets.amend(
                        ds_id, tenant_id=tenant_id, effective_from=current_valid_from,
                        description="same-instant change"
                    )
                    outcome = f"ACCEPTED; v2.valid_from={v2.valid_from.isoformat()}"
                except ConflictError as e:
                    outcome = f"ConflictError (unexpected): {e}"
            async with database.unit_of_work() as uow:
                history = await uow.datasets.history(ds_id, tenant_id=tenant_id)
                v1_row = [v for v in history if v.version == 1][0]
                zero_length = v1_row.valid_from == v1_row.valid_to
            record("SEM-181", f"{outcome}; v1 zero-length validity period (valid_from==valid_to)={zero_length}")
        except Exception as e:
            record("SEM-181", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-182: correction supersedes without touching validity ============
        try:
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(tenant_id=tenant_id, name="Correct DS")
                ds_id = str(entity.id)
                v1_valid_from, v1_valid_to = v1.valid_from, v1.valid_to
            async with database.unit_of_work() as uow:
                v2 = await uow.datasets.correct(
                    ds_id, tenant_id=tenant_id, provenance=Provenance(reason="wrong grain"),
                    description="corrected"
                )
            async with database.unit_of_work() as uow:
                history = await uow.datasets.history(ds_id, tenant_id=tenant_id)
                v1_row = [v for v in history if v.version == 1][0]
                v2_row = [v for v in history if v.version == 2][0]
            obs = {
                "v1.superseded_at set": v1_row.superseded_at is not None,
                "v1.valid_to unchanged": v1_row.valid_to == v1_valid_to,
                "v2.valid_from == v1.valid_from": v2_row.valid_from == v1_valid_from,
                "v2.valid_to == v1.valid_to": v2_row.valid_to == v1_valid_to,
            }
            record("SEM-182", obs)
        except Exception as e:
            record("SEM-182", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-183: correction to dataset with no current version -> NotFoundError ============
        try:
            async with database.unit_of_work() as uow:
                entity, _ = await DatasetService(uow).declare(tenant_id=tenant_id, name="Retired Then Correct DS")
                ds_id = str(entity.id)
            async with database.unit_of_work() as uow:
                retired = await uow.datasets.retire(ds_id, tenant_id=tenant_id)
            async with database.unit_of_work() as uow:
                try:
                    await uow.datasets.correct(
                        ds_id, tenant_id=tenant_id, provenance=Provenance(reason="x"), description="y"
                    )
                    outcome = "NO EXCEPTION (unexpected)"
                except NotFoundError as e:
                    outcome = f"NotFoundError: {e}"
            record("SEM-183", outcome)
        except Exception as e:
            record("SEM-183", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-184: retirement ends validity, destroys nothing ============
        try:
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(tenant_id=tenant_id, name="Retire Twice Versions DS")
                ds_id = str(entity.id)
            t_amend = utc_now() + timedelta(seconds=1)
            async with database.unit_of_work() as uow:
                v2 = await uow.datasets.amend(
                    ds_id, tenant_id=tenant_id, effective_from=t_amend, description="v2 grain"
                )
            past_moment = v1.valid_from + timedelta(milliseconds=1)
            async with database.unit_of_work() as uow:
                retired_version = await uow.datasets.retire(ds_id, tenant_id=tenant_id)
            async with database.unit_of_work() as uow:
                current = await uow.datasets.current(ds_id, tenant_id=tenant_id)
                history = await uow.datasets.history(ds_id, tenant_id=tenant_id)
                past_lookup = await uow.datasets.valid_at(ds_id, past_moment, tenant_id=tenant_id)
            obs = {
                "current is None": current is None,
                "history count": len(history),
                "history versions": [h.version for h in history],
                "valid_at(past) resolves": past_lookup is not None,
                "valid_at(past).version": past_lookup.version if past_lookup else None,
            }
            record("SEM-184", obs)
        except Exception as e:
            record("SEM-184", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-185: retiring twice is not an error, idempotent ============
        try:
            async with database.unit_of_work() as uow:
                entity, _ = await DatasetService(uow).declare(tenant_id=tenant_id, name="Retire Idempotent DS")
                ds_id = str(entity.id)
            async with database.unit_of_work() as uow:
                first_retire = await uow.datasets.retire(ds_id, tenant_id=tenant_id)
                first_valid_to = first_retire.valid_to
            async with database.unit_of_work() as uow:
                second_retire = await uow.datasets.retire(ds_id, tenant_id=tenant_id)
            async with database.unit_of_work() as uow:
                history = await uow.datasets.history(ds_id, tenant_id=tenant_id)
                v1_row = [v for v in history if v.version == 1][0]
            obs = {
                "second_retire returns None": second_retire is None,
                "first valid_to unchanged after second call": v1_row.valid_to == first_valid_to,
            }
            record("SEM-185", obs)
        except Exception as e:
            record("SEM-185", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-186/187/188: valid_at vs as_of after amend + correct ============
        try:
            # dataset amended in "April" and corrected in "June" (using relative markers)
            t0 = utc_now() - timedelta(days=180)   # declared ("March" analog / initial)
            t_april = utc_now() - timedelta(days=150)  # amendment effective
            t_june = utc_now() - timedelta(days=90)    # correction time (recorded_at ~ now of correct call)
            t_march_31 = utc_now() - timedelta(days=160)  # a query date between t0 and t_april... adjust below

            # We want: initial declared at t0 (grain X), amended effective t_april (grain Y),
            # then corrected (the amended version's content is wrong -> corrected to grain Y').
            # Query "31 March" = a date between t0 and t_april --> should resolve to v1 (both pre-correction and post).
            # Actually to test SEM-186/187 properly we need: query date AFTER the amendment (i.e. within v2's validity),
            # then correct v2, and see that valid_at (now, with benefit of correction) returns corrected v2,
            # while as_of(valid_at=that date, known_at=before correction) returns the pre-correction v2.
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(
                    tenant_id=tenant_id, name="Bitemporal Replay DS", valid_from=t0, description="original grain"
                )
                ds_id = str(entity.id)

            async with database.unit_of_work() as uow:
                v2 = await uow.datasets.amend(
                    ds_id, tenant_id=tenant_id, effective_from=t_april,
                    description="April amendment: grain B", provenance=Provenance(reason="grain changed in April")
                )
                v2_recorded_at = v2.recorded_at

            query_valid_at = t_april + timedelta(days=5)  # a date within v2's validity period, after t_april

            # Snapshot "known_at" using real wall-clock time, just after the amendment committed
            # and strictly before the correction is made below (recorded_at/superseded_at are always
            # real wall-clock "now", never backdated -- see VersionedDao.create()/amend()/correct()).
            known_at_before_correction = utc_now()

            async with database.unit_of_work() as uow:
                v3 = await uow.datasets.correct(
                    ds_id, tenant_id=tenant_id, provenance=Provenance(reason="June correction: fixed description"),
                    description="June correction: grain B corrected"
                )
                v3_recorded_at = v3.recorded_at

            known_at_after_correction = utc_now()

            async with database.unit_of_work() as uow:
                valid_at_result = await uow.datasets.valid_at(ds_id, query_valid_at, tenant_id=tenant_id)
                as_of_before = await uow.datasets.as_of(
                    ds_id, query_valid_at, known_at_before_correction, tenant_id=tenant_id
                )
                as_of_after = await uow.datasets.as_of(
                    ds_id, query_valid_at, known_at_after_correction, tenant_id=tenant_id
                )

            record("SEM-186", {
                "valid_at(with benefit of correction).description": valid_at_result.description if valid_at_result else None,
                "valid_at.version": valid_at_result.version if valid_at_result else None,
                "expected: corrected description (v3)": "June correction: grain B corrected",
            })
            record("SEM-187", {
                "as_of(valid_at=query, known_at=before correction).description": as_of_before.description if as_of_before else None,
                "as_of_before.version": as_of_before.version if as_of_before else None,
                "expected: pre-correction description (v2)": "April amendment: grain B",
            })
            record("SEM-188", {
                "as_of_before == valid_at_result content": (as_of_before.description == valid_at_result.description) if (as_of_before and valid_at_result) else None,
                "as_of_after == valid_at_result content": (as_of_after.description == valid_at_result.description) if (as_of_after and valid_at_result) else None,
            })

            # Now the "no correction ever made" dataset, to show the two reads AGREE
            async with database.unit_of_work() as uow:
                entity_nc, v1_nc = await DatasetService(uow).declare(
                    tenant_id=tenant_id, name="Never Corrected DS", valid_from=t0, description="only version"
                )
                ds_nc_id = str(entity_nc.id)
                v1_nc_recorded_at = v1_nc.recorded_at
            query_date_nc = t0 + timedelta(days=1)
            async with database.unit_of_work() as uow:
                valid_at_nc = await uow.datasets.valid_at(ds_nc_id, query_date_nc, tenant_id=tenant_id)
                as_of_nc = await uow.datasets.as_of(
                    ds_nc_id, query_date_nc, v1_nc_recorded_at + timedelta(seconds=1), tenant_id=tenant_id
                )
            agree = (valid_at_nc.description == as_of_nc.description) if (valid_at_nc and as_of_nc) else None
            print(f"    (SEM-188 continued) uncorrected dataset: valid_at vs as_of agree = {agree}")

        except Exception as e:
            record("SEM-186/187/188", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-189: known_at alone (no valid_at) is not silently discarded ============
        try:
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(tenant_id=tenant_id, name="Known At Only DS")
                ds_id = str(entity.id)
            async with database.unit_of_work() as uow:
                v2 = await uow.datasets.correct(
                    ds_id, tenant_id=tenant_id, provenance=Provenance(reason="fix"), description="corrected"
                )
            async with database.unit_of_work() as uow:
                current_version_number = (await uow.datasets.current(ds_id, tenant_id=tenant_id)).version
            year_2000 = datetime(2000, 1, 1, tzinfo=timezone.utc)
            # There is no API surface that accepts known_at without valid_at other than calling the
            # DAO method directly and omitting the positional valid_at argument.
            async with database.unit_of_work() as uow:
                try:
                    result = await uow.datasets.as_of(ds_id, known_at=year_2000, tenant_id=tenant_id)  # type: ignore[call-arg]
                    outcome = f"NO EXCEPTION; returned {result!r} (version={getattr(result, 'version', None)})"
                except TypeError as e:
                    outcome = f"TypeError (refused to even call): {e}"
            record("SEM-189", f"{outcome}; current version is v{current_version_number} -- did result silently equal current? that would be the regression")
        except Exception as e:
            record("SEM-189", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-190: as_of before first recorded_at returns None ============
        try:
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(tenant_id=tenant_id, name="Before Recorded DS")
                ds_id = str(entity.id)
                today = v1.valid_from
            yesterday = today - timedelta(days=1)
            async with database.unit_of_work() as uow:
                result = await uow.datasets.as_of(ds_id, today, yesterday, tenant_id=tenant_id)
            record("SEM-190", f"as_of(valid_at=today, known_at=yesterday) -> {result!r}")
        except Exception as e:
            record("SEM-190", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-191: history ordered oldest first, by record time then version ============
        try:
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(tenant_id=tenant_id, name="History Order DS")
                ds_id = str(entity.id)
            t_amend2 = utc_now() + timedelta(seconds=1)
            async with database.unit_of_work() as uow:
                v2 = await uow.datasets.amend(ds_id, tenant_id=tenant_id, effective_from=t_amend2, description="amended")
            async with database.unit_of_work() as uow:
                v3 = await uow.datasets.correct(ds_id, tenant_id=tenant_id, provenance=Provenance(reason="fix"), description="corrected")
            async with database.unit_of_work() as uow:
                history = await uow.datasets.history(ds_id, tenant_id=tenant_id)
            obs = {
                "count": len(history),
                "versions_in_order": [h.version for h in history],
                "superseded_row_present": any(h.superseded_at is not None for h in history),
            }
            record("SEM-191", obs)
        except Exception as e:
            record("SEM-191", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-192: version numbers increase on both paths (amend, correct, amend) ============
        try:
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(tenant_id=tenant_id, name="Version Sequence DS")
                ds_id = str(entity.id)
            t1 = utc_now() + timedelta(seconds=1)
            async with database.unit_of_work() as uow:
                v2 = await uow.datasets.amend(ds_id, tenant_id=tenant_id, effective_from=t1, description="v2")
            async with database.unit_of_work() as uow:
                v3 = await uow.datasets.correct(ds_id, tenant_id=tenant_id, provenance=Provenance(reason="fix"), description="v3")
            t2 = t1 + timedelta(seconds=1)
            async with database.unit_of_work() as uow:
                v4 = await uow.datasets.amend(ds_id, tenant_id=tenant_id, effective_from=t2, description="v4")
            record("SEM-192", f"versions={[v2.version, v3.version, v4.version]}")
        except Exception as e:
            record("SEM-192", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-193: exactly one current version at every moment (concurrency) ============
        try:
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(tenant_id=tenant_id, name="Concurrent Amend DS")
                ds_id = str(entity.id)

            async def try_amend(label):
                try:
                    async with database.unit_of_work() as uow2:
                        v = await uow2.datasets.amend(
                            ds_id, tenant_id=tenant_id, effective_from=utc_now(), description=f"amend-{label}"
                        )
                    return (label, "OK", v.version)
                except Exception as e:
                    return (label, f"{type(e).__name__}: {e}", None)

            results = await asyncio.gather(try_amend("A"), try_amend("B"))
            async with database.unit_of_work() as uow:
                history = await uow.datasets.history(ds_id, tenant_id=tenant_id)
                current_rows = [h for h in history if h.is_current]
            record("SEM-193", f"results={results}; current_row_count={len(current_rows)}; total_versions={len(history)}")
        except Exception as e:
            record("SEM-193", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-194: provenance recorded on every version ============
        try:
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(
                    tenant_id=tenant_id, name="Provenance DS", authored_by="alice"
                )
                ds_id = str(entity.id)
            t_a = utc_now() + timedelta(seconds=1)
            async with database.unit_of_work() as uow:
                v2 = await uow.datasets.amend(
                    ds_id, tenant_id=tenant_id, effective_from=t_a, description="amended",
                    provenance=Provenance(authored_by="alice", approved_by="bob", reason="amendment reason"),
                )
            async with database.unit_of_work() as uow:
                v3 = await uow.datasets.correct(
                    ds_id, tenant_id=tenant_id, provenance=Provenance(authored_by="alice", reason="correction reason"),
                    description="corrected",
                )
            async with database.unit_of_work() as uow:
                history = await uow.datasets.history(ds_id, tenant_id=tenant_id)
            obs = []
            for v in history:
                obs.append({
                    "version": v.version, "authored_by": v.authored_by, "approved_by": v.approved_by,
                    "approved_at": v.approved_at, "change_reason": v.change_reason,
                })
            record("SEM-194", obs)
        except Exception as e:
            record("SEM-194", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        # ============ SEM-195: control's evidence resolves against the declaration it ran under ============
        try:
            t0 = utc_now() - timedelta(days=10)
            async with database.unit_of_work() as uow:
                entity, v1 = await DatasetService(uow).declare(
                    tenant_id=tenant_id, name="Evidence Replay DS", valid_from=t0, description="grain A"
                )
                ds_id = str(entity.id)
            # "computed_at" for a control that ran before the correction below -- must be real
            # wall-clock time, since recorded_at/superseded_at are never backdated.
            control_ran_at = utc_now()
            async with database.unit_of_work() as uow:
                v2 = await uow.datasets.correct(
                    ds_id, tenant_id=tenant_id, provenance=Provenance(reason="grain was wrong"),
                    description="grain B (corrected)",
                )
            async with database.unit_of_work() as uow:
                resolved = await uow.datasets.as_of(ds_id, control_ran_at, control_ran_at, tenant_id=tenant_id)
            record("SEM-195", f"resolved.description={resolved.description if resolved else None} (expected pre-correction 'grain A')")
        except Exception as e:
            record("SEM-195", f"EXC {type(e).__name__}: {e}")
            traceback.print_exc()

        print("=== DONE bitemporality section ===")
    finally:
        await database.stop()
        database.sync_engine().dispose()


asyncio.run(main())
