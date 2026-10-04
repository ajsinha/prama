"""The developer guides' worked examples run, and do what the guides say they do.

Every complete implementation shown in `docs/developer/` lives as a file under
`docs/developer/examples/` and is exercised here: a connector through the
connector contract, a PQL function against its own reference on real engines,
a validator through admission, a delegate through the conformance kit, a lease
provider through the lease contract, and so on. An example that stops working
fails the build, which is what keeps a guide's code from being decoration.

Each group carries a counterfactual: the property the example demonstrates is
broken on purpose and the check is shown to notice.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "docs" / "developer" / "examples"


def load(stem: str, folder: Path = EXAMPLES) -> ModuleType:
    """Import one example by path, registered under a name of its own.

    Registered in ``sys.modules`` because Prama hashes and parses a plugin's own
    source (`inspect.getsource`), and that needs the module to be findable.
    """
    name = f"prama_developer_example_{stem}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, folder / f"{stem}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_every_example_is_exercised_here() -> None:
    """An example file nobody runs is a guide's code that can rot unseen."""
    source = Path(__file__).read_text(encoding="utf-8")
    examples = sorted(p.stem for p in EXAMPLES.rglob("*.py"))
    assert len(examples) >= 10, "anti-vacuity: the examples were not found"
    missing = [stem for stem in examples if f'"{stem}"' not in source]
    assert not missing, f"examples no test loads: {missing}"


# --------------------------------------------------------------------------- engines


POSTGRES_DSN = os.environ.get("PRAMA_TEST_POSTGRES_DSN", "")
ENGINES = ("duckdb", "sqlite", *(("postgresql",) if POSTGRES_DSN else ()))


def run_sql(engine: str, expression: str) -> Any:
    if engine == "duckdb":
        with duckdb.connect(":memory:") as connection:
            return connection.execute(f"SELECT {expression}").fetchone()[0]  # type: ignore[index]
    if engine == "postgresql":
        import psycopg

        with psycopg.connect(POSTGRES_DSN) as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT {expression}")
            return cursor.fetchone()[0]  # type: ignore[index]
    connection = sqlite3.connect(":memory:")
    try:
        return connection.execute(f"SELECT {expression}").fetchone()[0]
    finally:
        connection.close()


def comparable(value: Any) -> Any:
    from prama.pql.functions import UNSET

    if value is None or value is UNSET:
        return None
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value)).normalize()
    return str(value)


def disagreements(function: Any, cases: list[tuple[str, ...]]) -> list[str]:
    """Each engine's SQL against the function's reference, as the catalogue test does."""
    found = []
    for engine in ENGINES:
        for arguments in cases:
            expected = comparable(function.evaluate(list(arguments)))
            sql = function.render(engine, [f"'{a}'" for a in arguments])
            actual = comparable(run_sql(engine, sql))
            if expected != actual:
                found.append(f"{engine} {arguments}: reference={expected} sql={actual} [{sql}]")
    return found


# --------------------------------------------------------------------------- connectors


LAYOUT = "position_id:1-4,isin:5-16,currency:17-19,notional:20-31"
RECORDS = [
    ("1", "GB0002634946", "GBP", "1000.50"),
    ("2", "US0378331005", "USD", "25000.00"),
    ("3", "DE0007164600", "EUR", "3300.75"),
    ("4", "", "JPY", "120000.0"),
]


@pytest.fixture
def extracts(tmp_path: Path) -> Path:
    root = tmp_path / "landing"
    root.mkdir()
    widths = (4, 12, 3, 12)
    lines = ["".join(f.ljust(w) for f, w in zip(r, widths, strict=True)) for r in RECORDS]
    (root / "positions.txt").write_text("\n".join(lines) + "\n", encoding="ascii")
    (root / "notes.md").write_text("not an extract\n", encoding="ascii")
    return root


class TestConnector:
    @pytest.fixture
    def registry(self) -> Any:
        from prama.connect.registry import ConnectorRegistry

        return load("fixed_width_connector").register(ConnectorRegistry())

    def test_the_form_is_derived_from_the_code(self, registry: Any) -> None:
        schema = registry.schema("fixed_width")
        assert {f.name for f in schema.required_fields} == {"root_path", "layout"}
        assert schema.field("suffix").default == ".txt"
        assert schema.field("layout").display_label == "Record layout"
        assert registry.audit() == []

    def test_an_overlay_the_code_does_not_read_is_reported(self) -> None:
        """The counterfactual for derivation: presentation for a field that does
        not exist is the drift the derived form exists to prevent."""
        from prama.connect.config_schema import ConnectorConfigSchema, FieldPresentation

        example = load("fixed_width_connector")
        overlay = {**example.OVERLAY, "delimiter": FieldPresentation(label="Delimiter")}
        schema = ConnectorConfigSchema.build(example.FixedWidthConnector, overlay=overlay)
        assert schema.audit() == [
            "fixed_width: overlay describes 'delimiter', which the connector never reads"
        ]

    def test_a_missing_required_field_is_refused_before_connecting(
        self, registry: Any, extracts: Path
    ) -> None:
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError, match="layout"):
            registry.create("fixed_width", {"root_path": str(extracts)})

    async def test_the_contract(self, registry: Any, extracts: Path) -> None:
        from prama.connect import HealthState, SamplePlan, SamplingStrategy

        connector = registry.create("fixed_width", {"root_path": str(extracts), "layout": LAYOUT})
        async with connector:
            report = await connector.health()
            assert report.state is HealthState.HEALTHY and report.detail
            assert [o.leaf for o in await connector.discover()] == ["positions.txt"]

            schema = await connector.describe(("positions.txt",))
            assert schema.column_names == ("position_id", "isin", "currency", "notional")
            assert schema.estimated_rows == len(RECORDS)

            first = await connector.snapshot(("positions.txt",))
            second = await connector.snapshot(("positions.txt",))
            assert first.exact and first.identifier == second.identifier

            batches = [b async for b in connector.read(("positions.txt",))]
            rows = [row for batch in batches for row in batch.to_pylist()]
            assert len(rows) == len(RECORDS)
            assert rows[0] == {
                "position_id": "1",
                "isin": "GB0002634946",
                "currency": "GBP",
                "notional": "1000.50",
            }
            assert rows[3]["isin"] is None  # a blank field is missing, not ""

            head = SamplePlan(strategy=SamplingStrategy.HEAD, rows=2)
            sampled = [b async for b in connector.read(("positions.txt",), plan=head)]
            assert sum(b.num_rows for b in sampled) == 2

            assert connector.pushdown_capabilities() == ()
            assert connector.can_run_controls is False

    async def test_it_refuses_what_it_cannot_do_and_says_why(
        self, registry: Any, extracts: Path
    ) -> None:
        from prama.connect import ConnectorError, ReadPolicy, SamplePlan, SamplingStrategy
        from prama.connect.spi import UnauthorisedError

        config = {"root_path": str(extracts), "layout": LAYOUT}
        connector = registry.create("fixed_width", config)
        with pytest.raises(ConnectorError) as missing:
            await connector.describe(("no_such_extract.txt",))
        assert missing.value.remedy and "no_such_extract.txt" in str(missing.value)

        for plan in (
            SamplePlan(predicate="currency = 'GBP'"),
            SamplePlan(strategy=SamplingStrategy.RESERVOIR, rows=2),
        ):
            with pytest.raises(ConnectorError) as refused:
                _ = [b async for b in connector.read(("positions.txt",), plan=plan)]
            assert refused.value.remedy

        narrow = registry.create("fixed_width", config, policy=ReadPolicy(allowed_paths=("x",)))
        assert await narrow.discover() == []
        with pytest.raises(UnauthorisedError) as caught:
            await narrow.describe(("positions.txt",))
        assert "allowed paths" in caught.value.remedy

    async def test_health_names_who_has_to_fix_it(self, registry: Any, extracts: Path) -> None:
        from prama.connect import HealthState

        bad_layout = registry.create("fixed_width", {"root_path": str(extracts), "layout": "x"})
        assert (await bad_layout.health()).state is HealthState.MISCONFIGURED
        no_folder = registry.create(
            "fixed_width", {"root_path": str(extracts / "gone"), "layout": LAYOUT}
        )
        report = await no_folder.health()
        assert report.state is HealthState.UNREACHABLE and not report.needs_access_request


# --------------------------------------------------------------------------- PQL functions


DATE_CASES = [
    ("2026-09-08", "2026-09-11"),
    ("2024-02-29", "2023-12-31"),
    ("2026-01-01", "2026-01-01"),
    ("2024-02-28", "2024-03-01"),
]


class TestPqlFunction:
    def test_every_engine_agrees_with_the_reference(self) -> None:
        from prama.pql.functions import FunctionRegistry

        example = load("days_between_function")
        function = example.install(FunctionRegistry()).get("days_between")
        assert function is example.DAYS_BETWEEN
        assert not disagreements(function, DATE_CASES)
        assert function.evaluate(["2026-09-08", "2026-09-11"]) == Decimal(3)

    def test_a_date_nobody_can_read_is_unknown_not_zero(self) -> None:
        from prama.pql.functions import UNSET

        example = load("days_between_function")
        assert example.DAYS_BETWEEN.evaluate(["2026-02-30", "2026-03-01"]) is UNSET

    def test_the_agreement_check_catches_a_wrong_lowering(self) -> None:
        """The counterfactual: the SQLite lowering with its arguments swapped
        renders, runs, and is caught disagreeing with the reference."""
        import dataclasses

        example = load("days_between_function")
        swapped = dataclasses.replace(
            example.DAYS_BETWEEN,
            sql_by_engine={
                **example.DAYS_BETWEEN.sql_by_engine,
                "sqlite": "CAST(JULIANDAY({0}) - JULIANDAY({1}) AS INTEGER)",
            },
        )
        assert any(line.startswith("sqlite") for line in disagreements(swapped, DATE_CASES))

    def test_the_pack_function_agrees_too_and_installs_idempotently(self) -> None:
        from prama.pql.functions import FunctionRegistry

        pack = load("insurance_pack")
        registry = pack.install(pack.install(FunctionRegistry()))
        assert registry.names() == ("COVERED_ON",)
        cases = [
            ("2026-01-01", "2026-12-31", "2026-06-30"),
            ("2026-01-01", "2026-12-31", "2027-01-01"),
            ("2026-01-01", "2026-12-31", "2026-12-31"),
        ]
        assert not disagreements(registry.get("COVERED_ON"), cases)
        assert pack.claims()["not_claimed"]


# --------------------------------------------------------------------------- validators


class TestValidator:
    def test_it_decides_with_a_reason(self) -> None:
        validator = load("nhs_number_validator").NhsNumberValidator()
        assert validator.judge("9434765919").valid
        wrong = validator.judge("9434765918")
        assert not wrong.valid and wrong.reason == "check digit is 8, should be 9"
        assert validator.judge("943476591").failed_screen
        assert validator.judge(None).valid  # missing is a completeness question
        assert not validator.screen_is_complete  # the regex alone may not report a pass

    def test_a_body_with_no_possible_check_digit_is_invalid(self) -> None:
        validator = load("nhs_number_validator").NhsNumberValidator()
        body = next(
            f"{n:09d}"
            for n in range(100_000_000, 100_001_000)
            if 11 - sum(int(d) * w for d, w in zip(f"{n:09d}", range(10, 1, -1), strict=True)) % 11
            == 10
        )
        judged = validator.judge(body + "0")
        assert not judged.valid and "no valid check digit" in judged.reason

    def test_it_is_admitted_and_registered(self) -> None:
        from prama_kernel.plugins import PluginRegistry

        from prama.classify.validators import ValidatorRegistry

        validator = load("nhs_number_validator").NhsNumberValidator()
        provenance = PluginRegistry().admit(validator, distribution="acme-validators")
        assert provenance.name == "nhs_number" and len(provenance.implementation_hash) == 32
        registry = ValidatorRegistry()
        registry.register(validator)
        assert registry.find("NHS_NUMBER") is validator

    def test_a_validator_that_reads_the_clock_is_refused(self, tmp_path: Path) -> None:
        """The counterfactual for admission: the same validator with one impure
        import is not usable."""
        from prama_kernel.errors import ValidationError
        from prama_kernel.plugins import PluginRegistry

        source = (EXAMPLES / "nhs_number_validator.py").read_text(encoding="utf-8")
        impure = source.replace(
            "from __future__ import annotations\n",
            "from __future__ import annotations\n\nimport time\n",
        )
        assert impure != source, "anti-vacuity: the import was not inserted"
        (tmp_path / "impure_nhs.py").write_text(impure, encoding="utf-8")
        clocked = load("impure_nhs", tmp_path).NhsNumberValidator()
        with pytest.raises(ValidationError, match="reading the clock"):
            PluginRegistry().admit(clocked)


# --------------------------------------------------------------------------- delegates


LEDGER = [
    {"account_id": "A", "as_of": "2026-09-01", "opening": 100.0, "closing": 110.0},
    {"account_id": "A", "as_of": "2026-09-03", "opening": 95.0, "closing": 95.0},
    {"account_id": "A", "as_of": "2026-09-02", "opening": 110.0, "closing": 90.0},
    {"account_id": "B", "as_of": "2026-09-01", "opening": 5.0, "closing": 5.0},
    {"account_id": "B", "as_of": "not a date", "opening": 5.0, "closing": 5.0},
]


class TestDelegate:
    PATH = EXAMPLES / "delegates" / "balance_continuity.py"

    def test_the_conformance_kit_passes_it_with_its_cases(self) -> None:
        from prama.delegates.testkit import Case, check_delegate

        report = check_delegate(
            self.PATH,
            cases=[
                Case("one break and one undated row", rows=LEDGER, scanned=5, violating=2),
                Case("one row establishes nothing", rows=LEDGER[:1], established=False),
            ],
            large_rows=20_000,
        )
        assert report.ok, report.render()

    def test_a_wrong_expectation_is_caught(self) -> None:
        """The counterfactual: the kit is not a rubber stamp."""
        from prama.delegates.testkit import Case, check_delegate

        report = check_delegate(
            self.PATH, cases=[Case("wrong", rows=LEDGER, violating=0)], large_rows=100
        )
        assert not report.ok

    def test_the_tolerance_parameter_is_honoured(self) -> None:
        delegate = load("balance_continuity", EXAMPLES / "delegates").BalanceContinuity()
        loose = delegate.measure(iter(LEDGER), delegate.resolve({"tolerance": 10}))
        strict = delegate.measure(iter(LEDGER), delegate.resolve({}))
        assert (strict.violating, loose.violating) == (2, 1)


# --------------------------------------------------------------------------- monitors


def steady(count: int = 200, seed: int = 3) -> list[float]:
    rng = random.Random(seed)
    return [1000 + rng.gauss(0, 20) for _ in range(count)]


class TestDetector:
    def test_the_detector_contract(self) -> None:
        detector = load("trimmed_deviation_detector").TrimmedDeviation()
        history = steady()
        assert detector.score(4000.0, history).value > detector.score(1005.0, history).value
        assert detector.score(1.0, [1.0, 2.0]) is None
        assert detector.good_at and detector.blind_to

        with_outlier = [*steady(60), 9999.0]
        scores = detector.scores(with_outlier)
        assert len(scores) == len(with_outlier) and scores[-1] == max(scores)

    def test_noise_costs_sensitivity_never_validity(self) -> None:
        from prama.calibrate.conformal import ConformalCalibrator, ConformalP

        detector = load("trimmed_deviation_detector").TrimmedDeviation()
        rng = random.Random(11)
        fired = 0
        for _ in range(300):
            history = [rng.gauss(0, 1) for _ in range(120)]
            score = detector.score(rng.gauss(0, 1), history)
            p = ConformalCalibrator(detector.scores(history)).p_value(score.value)
            fired += isinstance(p, ConformalP) and p.value <= 0.10
        assert fired / 300 <= 0.16

    def test_it_joins_an_ensemble_and_a_monitor(self) -> None:
        from prama.monitor.detect import Ensemble, default_ensemble
        from prama.monitor.fleet import Monitor

        detector = load("trimmed_deviation_detector").TrimmedDeviation()
        ensemble = Ensemble(detectors=(*default_ensemble().detectors, detector))
        assert "trimmed_deviation" in ensemble.score_all(4000.0, steady())
        assert Monitor("trades", "rows", detector=detector).detector is detector


# --------------------------------------------------------------------------- importers


SHEET = """dataset,column,rule,value
trades,trade_id,not null,
trades,trade_id,unique,
trades,ccy,one of,USD|EUR|GBP
trades,notional,minimum,0
trades,book,looks right,
trades,price,minimum,cheap
"""


class TestImporter:
    def test_what_came_across_and_what_did_not(self) -> None:
        result = load("rules_sheet_importer").RulesSheetImporter().read_text(SHEET)
        assert result.imported == 4
        assert len(result.caveats) == 3
        assert [u.source for u in result.unmapped] == [
            "rules sheet row 6 (trades.book: looks right)",
            "rules sheet row 7 (trades.price: minimum)",
        ]
        assert all("Imported from rules sheet row" in c.render() for c in result.controls)
        assert "2 did not come across" in result.render()

    def test_it_is_found_by_name_once_registered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from prama.importers import IMPORTERS, importer

        example = load("rules_sheet_importer")
        monkeypatch.setitem(IMPORTERS, "rules_sheet", example.RulesSheetImporter)
        assert isinstance(importer("rules-sheet"), example.RulesSheetImporter)


# --------------------------------------------------------------------------- LLM providers


class Recorder:
    def __init__(self, reply: dict[str, Any] | Exception) -> None:
        self.reply = reply
        self.sent: list[dict[str, Any]] = []

    def __call__(self, url: str, body: bytes, timeout: float) -> bytes:
        self.sent.append({"url": url, **json.loads(body)})
        if isinstance(self.reply, Exception):
            raise self.reply
        return json.dumps(self.reply).encode()


class TestModelProvider:
    def test_ask_redacts_before_complete_sees_the_prompt(self) -> None:
        from prama.llm.spi import Grammar, Request

        example = load("generate_provider")
        opener = Recorder(
            {"generated_text": "CHECK t.a IS NOT NULL", "details": {"generated_tokens": 7}}
        )
        provider = example.GenerateProvider("http://127.0.0.1:8080", opener=opener)
        response = provider.ask(
            Request(
                system="Draft PQL.",
                prompt="Card 4111 1111 1111 1111 failed; draft a check.",
                grammar=Grammar(name="pql", pattern="CHECK .*"),
            )
        )
        assert response.ok and response.text == "CHECK t.a IS NOT NULL"
        assert response.output_tokens == 7 and response.grammar_enforced
        (sent,) = opener.sent
        assert sent["url"] == "http://127.0.0.1:8080/generate"
        assert "4111 1111 1111 1111" not in sent["inputs"]
        assert sent["parameters"]["grammar"] == {"type": "regex", "value": "CHECK .*"}

    def test_a_failed_call_is_incomplete_not_raised(self) -> None:
        from prama.llm.spi import Request

        example = load("generate_provider")
        provider = example.GenerateProvider("http://x", opener=Recorder(OSError("refused")))
        response = provider.ask(Request(system="", prompt="hello"))
        assert not response.ok and "refused" in response.incomplete

    def test_a_hosted_provider_with_no_residency_rule_sends_nothing(self) -> None:
        """The counterfactual for the boundary: change only the hosting, and
        `ask` refuses before `complete` is reached."""
        from prama.llm.spi import Hosting, Request
        from prama.security.egress import ResidencyRefused

        example = load("generate_provider")

        class Hosted(example.GenerateProvider):  # type: ignore[name-defined,misc]
            hosting = Hosting.HOSTED

        opener = Recorder({"generated_text": "x"})
        with pytest.raises(ResidencyRefused):
            Hosted("https://models.example.com", opener=opener).ask(Request(system="", prompt="q"))
        assert opener.sent == []


# --------------------------------------------------------------------------- code readers


MAPPING = """source,target,transform,job
raw.trades.acct,stg.trades.account_id,rename,load_trades
stg.trades.notional,mart.positions.exposure,aggregated,build_positions
notional,mart.positions.exposure_usd,derived,build_positions
stg.trades.ccy,mart.positions.ccy,translated,build_positions
"""


class TestCodeReader:
    def test_edges_gaps_and_coverage(self) -> None:
        from prama.lineage.graph import LineageGraph, Transform

        result = load("mapping_sheet_scanner").MappingSheetScanner().scan(MAPPING, source="s2t.csv")
        edges = result.extraction.edges
        assert [e.transform for e in edges] == [Transform.RENAME, Transform.AGGREGATED]
        assert edges[0].produced_by == "load_trades"
        assert sorted(g.kind for g in result.extraction.gaps) == ["unknown_transform", "unparsed"]
        assert result.coverage == 0.5 and "2 of 4 units" in result.describe()
        assert len(list(result.extraction.into(LineageGraph()).edges())) == 2

    def test_a_sheet_of_the_wrong_shape_is_misconfigured_not_empty(self) -> None:
        result = load("mapping_sheet_scanner").MappingSheetScanner().scan("from,to\na.b,c.d\n")
        assert "no source or target column" in result.misconfigured
        assert result.misconfigured in result.describe()


# --------------------------------------------------------------------------- agent executors


SLOW = (
    "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 3000000) "
    "SELECT count(*) AS n FROM c"
)


class TestAgentExecutor:
    @pytest.fixture
    def book(self, tmp_path: Path) -> Path:
        path = tmp_path / "book.db"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE trades (trade_id INTEGER, amount REAL)")
        connection.executemany("INSERT INTO trades VALUES (?, ?)", [(1, 5.0), (2, 7.5), (3, None)])
        connection.commit()
        connection.close()
        return path

    def test_it_is_chosen_for_an_assignment_and_answers(self, book: Path) -> None:
        from prama_agent.config import Source
        from prama_agent.executors import Executors
        from prama_kernel.agent.protocol import Assignment

        example = load("time_limited_executor")
        executor = example.TimeLimitedSqliteExecutor(Source("book", "sqlite", path=str(book)))
        assignment = Assignment(
            plan_id="p1",
            dataset="trades",
            binding="book",
            engine="sqlite",
            metric_query="SELECT count(*) AS rows_checked, count(amount) AS present FROM trades",
        )
        chosen = Executors.of({"book": executor})(assignment)
        assert chosen is executor
        assert chosen(assignment.metric_query) == [{"rows_checked": 3, "present": 2}]
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            chosen("DELETE FROM trades")

    def test_a_statement_past_its_limit_is_interrupted(self, book: Path) -> None:
        from prama_agent.config import Source

        example = load("time_limited_executor")
        source = Source("book", "sqlite", path=str(book))
        with pytest.raises(TimeoutError, match="ran past"):
            example.TimeLimitedSqliteExecutor(source, seconds=0.01)(SLOW)
        # The counterfactual: the same statement with room to finish finishes,
        # so it was the limit that stopped it, not the statement that was wrong.
        assert example.TimeLimitedSqliteExecutor(source, seconds=60)(SLOW) == [{"n": 3_000_000}]


# --------------------------------------------------------------------------- secrets and leases


class TestSecretProvider:
    def test_a_reference_resolves_and_the_value_does_not_print(self, tmp_path: Path) -> None:
        from prama.secrets.resolver import SecretResolver

        env = tmp_path / ".env"
        env.write_text('# local only\nexport WAREHOUSE_PASSWORD="s3cret"\nEMPTY=\n')
        provider = load("dotenv_secret_provider").DotenvSecretProvider(env)
        value = SecretResolver([provider]).resolve("dotenv://WAREHOUSE_PASSWORD")
        assert value.reveal() == "s3cret" and "s3cret" not in repr(value)
        assert value.origin == "dotenv://WAREHOUSE_PASSWORD"

    def test_every_refusal_carries_a_remedy(self, tmp_path: Path) -> None:
        from prama.secrets.resolver import SecretResolver
        from prama.secrets.spi import SecretResolutionError

        env = tmp_path / ".env"
        env.write_text("EMPTY=\n")
        provider = load("dotenv_secret_provider").DotenvSecretProvider(env)
        resolver = SecretResolver([provider])
        for reference in ("dotenv://MISSING", "dotenv://EMPTY", "dotenv://EMPTY#field"):
            with pytest.raises(SecretResolutionError) as caught:
                resolver.resolve(reference)
            assert caught.value.remedy
        gone = SecretResolver(
            [load("dotenv_secret_provider").DotenvSecretProvider(env.parent / "x")]
        )
        with pytest.raises(SecretResolutionError, match="not usable"):
            gone.resolve("dotenv://ANY")


class TestLeaseContract:
    async def test_the_in_process_provider_conforms(self) -> None:
        from prama.core.concurrency.leases import MemoryLeaseProvider

        assert await load("lease_contract").check(MemoryLeaseProvider()) == []

    async def test_the_database_provider_conforms(self, started_database: Any) -> None:
        assert await load("lease_contract").check(started_database.lease_provider()) == []

    async def test_a_provider_that_grants_everything_is_caught(self) -> None:
        """The counterfactual: a provider that ignores the current holder breaks
        the first sentence of the contract, and the check names it."""
        from prama.core.concurrency.leases import Lease, MemoryLeaseProvider

        class Careless(MemoryLeaseProvider):
            async def acquire(self, resource: str, holder: str, ttl: float) -> Lease | None:
                self._leases.pop(resource, None)
                return await super().acquire(resource, holder, ttl)

        broken = await load("lease_contract").check(Careless())
        assert "a second holder acquired a resource that was already held" in broken
