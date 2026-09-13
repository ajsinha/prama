"""Third-party validators, and the contract that makes them safe to load.

This is the "inject external Python" half of the expression layer, and the
tests are the contract: purity enforced rather than declared, and the
implementation's hash folded into the plan so editing a validator changes the
identity of every control that uses it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from prama.classify.plugins import (
    FORBIDDEN,
    FORBIDDEN_CALLS,
    FORBIDDEN_PRAMA,
    PROBES,
    PluginRegistry,
    forbidden_imports,
    implementation_hash,
    scan_source,
)
from prama.classify.validators import default_registry
from prama.core.errors import ValidationError


def _write(tmp_path: Path, body: str, name: str = "plug") -> Path:
    """A validator module on disk, never imported.

    For the checks that must work on a plugin whose dependencies are not
    installed — which is the situation an operator reviewing one is in.
    """
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _load(tmp_path: Path, body: str, name: str = "plug") -> Any:
    """Write a validator module, import it, and return an instance.

    Written to disk because the checks scan the module's *source*: a validator
    built in memory has nothing to scan, which is itself refused.
    """
    import importlib.util
    import sys

    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered in sys.modules before exec: `inspect.getmodule` and
    # `inspect.getsource` both resolve through it, and without it a plugin
    # loaded this way has no readable source — which the registry then refuses,
    # for the right reason and in the wrong test.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.Plugin()


PURE = """
    from prama.classify.validators import Judgement, SemanticValidator

    class Plugin(SemanticValidator):
        name = "acme_account"
        label = "Acme account number"
        screen_pattern = r"^AC[0-9]{8}$"

        def check(self, value: str) -> Judgement:
            digits = value[2:]
            total = sum(int(d) * (i + 1) for i, d in enumerate(digits))
            if total % 11 == 0:
                return Judgement(valid=True)
            return Judgement(valid=False, reason="the weighted sum is not divisible by 11")
"""


class TestAPureValidatorIsAdmitted:
    def test_it_loads(self, tmp_path: Path) -> None:
        registry = PluginRegistry()
        provenance = registry.admit(_load(tmp_path, PURE), distribution="acme-pack")
        assert provenance.name == "acme_account"
        assert provenance.distribution == "acme-pack"
        assert len(provenance.implementation_hash) == 32

    def test_the_shipped_validators_would_pass_their_own_gate(self) -> None:
        """The rules are not stricter than the code they were written for. A
        gate the product's own validators fail is a gate somebody widens."""
        registry = PluginRegistry()
        shipped = default_registry()
        for name in shipped.names():
            registry.admit(shipped.get(name), distribution="prama")
        assert len(registry) == len(shipped)


class TestPurityIsEnforcedNotDeclared:
    @pytest.mark.parametrize("module", ["random", "socket", "requests", "subprocess", "os"])
    def test_an_impure_import_is_caught(self, tmp_path: Path, module: str) -> None:
        """Scanned from the file, without importing it.

        That is the point of ``scan_source``: importing a module runs its
        top-level code, so a gate that had to import the thing it was gating
        would already have run it by the time it decided to refuse. It also
        lets a plugin be vetted when its dependencies are not even installed —
        which is the situation an operator is actually in when reviewing one.
        """
        path = _write(
            tmp_path,
            f"""
            import {module}
            from prama.classify.validators import Judgement, SemanticValidator

            class Plugin(SemanticValidator):
                name = "impure"
                screen_pattern = r"^.*$"

                def check(self, value: str) -> Judgement:
                    return Judgement(valid=True)
            """,
            name=f"impure_{module}",
        )
        found = scan_source(str(path))
        assert found, f"{module} should have been caught"

    def test_a_loaded_impure_validator_is_refused(self, tmp_path: Path) -> None:
        """The same rule, applied where a plugin actually arrives."""
        validator = _load(
            tmp_path,
            """
            import random
            from prama.classify.validators import Judgement, SemanticValidator

            class Plugin(SemanticValidator):
                name = "impure"
                screen_pattern = r"^.*$"

                def check(self, value: str) -> Judgement:
                    return Judgement(valid=True)
            """,
            name="impure_loaded",
        )
        with pytest.raises(ValidationError, match="may not"):
            PluginRegistry().admit(validator)

    def test_the_refusal_names_the_guarantee_that_was_tripped(self, tmp_path: Path) -> None:
        """Somebody whose plugin is refused needs to know *which* guarantee,
        not merely that they tripped one."""
        path = _write(
            tmp_path,
            """
            import requests
            from prama.classify.validators import Judgement, SemanticValidator

            class Plugin(SemanticValidator):
                name = "networked"
                screen_pattern = r"^.*$"

                def check(self, value: str) -> Judgement:
                    return Judgement(valid=True)
            """,
            name="networked",
        )
        reasons = " ".join(reason for _module, reason in scan_source(str(path)))
        assert "unreplayable" in reasons
        assert "leaks the data" in reasons

    def test_a_model_client_is_refused_because_ai_never_adjudicates(self, tmp_path: Path) -> None:
        """CON-007. A model output would decide a pass or fail verdict on
        data, which no code path may allow."""
        path = _write(
            tmp_path,
            """
            from prama.llm import provider
            from prama.classify.validators import Judgement, SemanticValidator

            class Plugin(SemanticValidator):
                name = "asks_a_model"
                screen_pattern = r"^.*$"

                def check(self, value: str) -> Judgement:
                    return Judgement(valid=True)
            """,
            name="asks_a_model",
        )
        reasons = " ".join(reason for _module, reason in scan_source(str(path)))
        assert "CON-007" in reasons

    def test_reading_the_clock_is_refused_but_parsing_a_date_is_not(self, tmp_path: Path) -> None:
        """``datetime`` is not banned: a date-format validator legitimately
        parses one. What is banned is asking it what time it is — otherwise the
        rule would refuse the validator it was written to protect."""
        parses = _load(
            tmp_path,
            """
            from datetime import date
            from prama.classify.validators import Judgement, SemanticValidator

            class Plugin(SemanticValidator):
                name = "parses_dates"
                screen_pattern = r"^\\d{4}-\\d{2}-\\d{2}$"

                def check(self, value: str) -> Judgement:
                    try:
                        date.fromisoformat(value)
                    except ValueError:
                        return Judgement(valid=False, reason="not a real date")
                    return Judgement(valid=True)
            """,
            name="parses_dates",
        )
        PluginRegistry().admit(parses)

        asks = _load(
            tmp_path,
            """
            from datetime import date
            from prama.classify.validators import Judgement, SemanticValidator

            class Plugin(SemanticValidator):
                name = "asks_the_clock"
                screen_pattern = r"^.*$"

                def check(self, value: str) -> Judgement:
                    return Judgement(valid=value <= date.today().isoformat())
            """,
            name="asks_the_clock",
        )
        with pytest.raises(ValidationError, match="unreplayable"):
            PluginRegistry().admit(asks)

    def test_the_call_ban_covers_every_spelling_of_now(self) -> None:
        for spelling in ("now", "today", "utcnow", "monotonic"):
            assert spelling in FORBIDDEN_CALLS

    def test_prama_internals_are_matched_by_prefix_not_by_root(self) -> None:
        """Matching the root made "prama.llm" ban "prama.core.errors", which
        every validator imports — so every validator was refused."""
        assert "prama" not in FORBIDDEN
        assert all(key.startswith("prama.") for key in FORBIDDEN_PRAMA)


class TestDeterminismIsTestedNotTrusted:
    def test_a_validator_that_changes_its_mind_is_refused(self, tmp_path: Path) -> None:
        """Import scanning catches the obvious sources. This catches a cached
        global, a mutable set, a counter — the ones a scan cannot see."""
        validator = _load(
            tmp_path,
            """
            from prama.classify.validators import Judgement, SemanticValidator

            class Plugin(SemanticValidator):
                name = "flip_flop"
                screen_pattern = r"^.*$"
                _calls = 0

                def check(self, value: str) -> Judgement:
                    type(self)._calls += 1
                    return Judgement(valid=type(self)._calls % 2 == 0)
            """,
            name="flip_flop",
        )
        with pytest.raises(ValidationError, match="two answers"):
            PluginRegistry().admit(validator)

    def test_a_validator_that_raises_on_a_blank_is_refused(self, tmp_path: Path) -> None:
        """It will raise on the first blank in production, and take the control
        down instead of failing the row."""
        validator = _load(
            tmp_path,
            """
            from prama.classify.validators import Judgement, SemanticValidator

            class Plugin(SemanticValidator):
                name = "fragile"
                screen_pattern = None

                def check(self, value: str) -> Judgement:
                    return Judgement(valid=value[5] == "X")
            """,
            name="fragile",
        )
        with pytest.raises(ValidationError, match="raised on the input"):
            PluginRegistry().admit(validator)

    def test_the_probes_include_the_inputs_that_break_things(self) -> None:
        assert "" in PROBES
        assert any(len(p) > 100 for p in PROBES)


class TestIdentity:
    def test_the_hash_is_of_the_class_not_the_module(self, tmp_path: Path) -> None:
        """A module holding ten validators would otherwise give all ten the
        same hash, and editing one would change the identity of controls using
        the other nine."""
        first = _load(tmp_path, PURE, name="one")
        second = _load(tmp_path, PURE.replace("acme_account", "other_account"), name="two")
        assert implementation_hash(first) != implementation_hash(second)

    def test_editing_the_implementation_changes_the_hash(self, tmp_path: Path) -> None:
        original = _load(tmp_path, PURE, name="orig")
        edited = _load(tmp_path, PURE.replace("% 11 == 0", "% 13 == 0"), name="edited")
        assert implementation_hash(original) != implementation_hash(edited)

    def test_a_validator_whose_source_cannot_be_read_is_refused(self) -> None:
        """An implementation nobody can hash is one whose changes nobody can
        detect."""
        from prama.classify.validators import Judgement, SemanticValidator

        built = type(
            "Dynamic",
            (SemanticValidator,),
            {
                "name": "dynamic",
                "screen_pattern": r"^.*$",
                "check": lambda *_: Judgement(valid=True),
            },
        )()
        with pytest.raises(ValidationError, match="cannot be read"):
            implementation_hash(built)


class TestThePlanCarriesIt:
    def test_a_control_using_a_validator_changes_when_the_code_does(self) -> None:
        """The non-negotiable part. Without it the code is part of a control's
        *meaning* and not part of its *identity*: somebody edits the check
        digit routine and last month's evidence silently starts meaning
        something else while claiming to be the same control.
        """
        from prama.classify.plugins import PLUGINS
        from prama.ir.resolve import resolved
        from prama.pql import parse_control

        source = "CHECK t.isin IS VALID 'isin' SEVERITY major DIMENSION validity BECAUSE 'x'"
        control = parse_control(source)

        before = PLUGINS.provenance("isin")
        try:
            PLUGINS._provenance.pop("isin", None)
            unknown = resolved(control).plan_id
            PLUGINS.admit(default_registry().get("isin"), distribution="prama")
            known = resolved(control).plan_id
            assert unknown != known
        finally:
            if before is not None:
                PLUGINS._provenance["isin"] = before
            else:
                PLUGINS._provenance.pop("isin", None)


class TestTheThreeEvasionsThatWorked:
    """Finding H3. `docs/19` and `docs/08` both record "a plugin that imports a
    clock, a socket or a model is refused at registration" as built.

    Three independent holes, none covered: `time` was not on the ban list, a
    dynamic import was invisible to a scan keyed on `ast.Import`, and the scan
    read only the validator's *own* file — so a helper module beside it could
    import anything at all. A validator doing `import time`,
    `__import__("socket")` and `time.gmtime()` was admitted.
    """

    def scan(self, tmp_path: Path, source: str, name: str = "impure.py") -> list[tuple[str, str]]:
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        return scan_source(str(path))

    def test_the_clock_is_refused(self, tmp_path: Path) -> None:
        found = self.scan(tmp_path, "import time\n\ndef judge(v):\n    return time.time()\n")
        assert found, "`import time` is a clock, and a clock makes a control unreplayable"
        assert any("time" in name for name, _ in found)

    def test_reading_the_clock_by_another_name_is_refused(self, tmp_path: Path) -> None:
        """The call ban covered now/today/utcnow/monotonic/perf_counter and not
        gmtime, localtime or time_ns."""
        for call in ("gmtime", "localtime", "time_ns"):
            found = self.scan(tmp_path, f"import calendar\n\ndef judge(v):\n    return {call}()\n")
            assert found, f"{call}() reads the clock and was admitted"

    def test_a_dynamic_import_is_refused(self, tmp_path: Path) -> None:
        found = self.scan(tmp_path, 'def judge(v):\n    return __import__("socket")\n')
        assert found, "__import__ hides what the validator reaches for"

    def test_importlib_is_refused(self, tmp_path: Path) -> None:
        found = self.scan(
            tmp_path,
            'import importlib\n\ndef judge(v):\n    return importlib.import_module("socket")\n',
        )
        assert found

    def test_generated_code_is_refused(self, tmp_path: Path) -> None:
        for spelling in ('eval("1")', 'exec("x=1")', 'compile("1", "<s>", "eval")'):
            found = self.scan(tmp_path, f"def judge(v):\n    return {spelling}\n")
            assert found, f"{spelling} is arbitrary code execution"

    def test_an_ordinary_regex_is_not_refused(self, tmp_path: Path) -> None:
        """The counterfactual, and not a hypothetical: banning `compile` by name
        alone refused every shipped validator, because `re.compile` is the
        ordinary thing a format check does. A gate that refuses the honest case
        is not a stricter gate, it is a broken one."""
        found = self.scan(
            tmp_path,
            'import re\n\nPATTERN = re.compile("^[0-9]+$")\n\ndef judge(v):\n'
            "    return bool(PATTERN.match(v))\n",
        )
        assert not found, found

    def test_a_helper_module_cannot_launder_an_import(self, tmp_path: Path) -> None:
        """The simplest evasion of all: put it in the file next door.

        `forbidden_imports` read `inspect.getmodule(type(validator)).__file__`
        and nothing else, so the helper — where the impurity actually lives —
        was never opened.
        """
        (tmp_path / "helper.py").write_text(
            "import socket\n\ndef reach():\n    return socket.gethostname()\n", encoding="utf-8"
        )
        (tmp_path / "validator.py").write_text(
            "import helper\n\n\nclass Sneaky:\n    name = 'sneaky'\n\n"
            "    def judge(self, value):\n        return helper.reach()\n",
            encoding="utf-8",
        )
        sys.path.insert(0, str(tmp_path))
        try:
            import importlib

            module = importlib.import_module("validator")
            found = forbidden_imports(module.Sneaky())
        finally:
            sys.path.remove(str(tmp_path))
            sys.modules.pop("validator", None)
            sys.modules.pop("helper", None)

        assert found, "the socket lived one file away and the scan never opened it"
        assert any("helper" in reason for _, reason in found), found
