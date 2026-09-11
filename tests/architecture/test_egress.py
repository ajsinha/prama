"""Every registered egress point actually consults the gate.

A policy engine nothing calls permits everything, and it fails silently, which
is the worst way for a control to fail. The registry in
:mod:`prama.security.egress` is only worth having if something checks that its
entries are true — an assertion in a review document does not survive a year of
changes, and a hand-audit is a hand-audit.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import ClassVar

import pytest

from prama.security.egress import EGRESS_POINTS, EgressPoint, Gate, ResidencyRefused

SRC = Path(__file__).resolve().parents[2] / "src"


def module_path(dotted: str) -> Path:
    return SRC / Path(*dotted.split(".")).with_suffix(".py")


def reaches_the_gate(path: Path) -> bool:
    """Whether this module consults residency at all.

    Deliberately coarse: it asks whether the module names the gate, not whether
    every branch reaches it. A tighter check would need to know which functions
    perform the movement, and a guard that claims more precision than it has is
    worse than one that states its limit.
    """
    source = path.read_text(encoding="utf-8")
    return "Gate" in source or "residency" in source or "ResidencyRefused" in source


class TestTheRegistryIsTrue:
    @pytest.mark.parametrize("egress", EGRESS_POINTS, ids=lambda e: e.name)
    def test_the_module_exists(self, egress: EgressPoint) -> None:
        assert module_path(egress.module).is_file(), egress.module

    @pytest.mark.parametrize("egress", EGRESS_POINTS, ids=lambda e: e.name)
    def test_the_module_consults_residency(self, egress: EgressPoint) -> None:
        """A registered point that does not is a build failure, not a note."""
        assert reaches_the_gate(module_path(egress.module)), (
            f"{egress.module} is registered as an egress point and never "
            "consults residency. Either wire the gate into it or remove the "
            "entry — a registry that lists a point nobody checks is worse than "
            "no registry, because it reads as coverage."
        )

    @pytest.mark.parametrize("egress", EGRESS_POINTS, ids=lambda e: e.name)
    def test_it_says_where_the_jurisdiction_comes_from(self, egress: EgressPoint) -> None:
        """The common defect is an egress that knows its destination and not
        its subject's home, which answers the wrong question confidently."""
        assert egress.jurisdiction_from
        assert egress.destination_from
        assert egress.what

    def test_names_are_unique(self) -> None:
        names = [e.name for e in EGRESS_POINTS]
        assert len(set(names)) == len(names)

    def test_modules_are_unique(self) -> None:
        """Two entries for one module means one of them is not the whole
        story, and a reviewer reading either would be misled."""
        modules = [e.module for e in EGRESS_POINTS]
        assert len(set(modules)) == len(modules)


class TestNothingSendsWithoutBeingRegistered:
    #: Modules permitted to reach the network without being an egress point,
    #: and why. Short on purpose: each line is something a security reviewer
    #: has to accept.
    NOT_EGRESS: ClassVar[dict[str, str]] = {
        "prama/db/schema/bootstrap.py": (
            "imports socket for gethostname, to record who applied a schema. "
            "Nothing of the tenant's leaves"
        ),
    }

    #: Matched as whole dotted prefixes, not by first component. `urllib.parse`
    #: is string handling and reaches nothing; treating it as network traffic
    #: because it starts with `urllib` put a template renderer on this list,
    #: and a guard that cries wolf teaches the next reader to ignore it.
    NETWORK: ClassVar[tuple[str, ...]] = (
        "httpx",
        "requests",
        "urllib.request",
        "urllib.error",
        "http.client",
        "smtplib",
        "socket",
        "aiohttp",
        "websockets",
        "ftplib",
    )

    def _is_network(self, imported: str) -> bool:
        return any(imported == name or imported.startswith(name + ".") for name in self.NETWORK)

    def network_modules(self) -> list[str]:
        found = []
        for path in sorted(SRC.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names.add(node.module)
            if any(self._is_network(name) for name in names):
                found.append(str(path.relative_to(SRC)))
        return found

    def test_the_matcher_does_not_confuse_urllib_parse_with_urllib_request(self) -> None:
        """The false positive that forced the narrowing."""
        assert self._is_network("urllib.request")
        assert not self._is_network("urllib.parse")
        assert self._is_network("socket")
        assert not self._is_network("socketserver")

    def test_every_module_that_can_reach_the_network_is_accounted_for(self) -> None:
        """Derived from the imports rather than from a list somebody keeps up
        to date. The list is the thing that rots; the imports are the thing
        that is true."""
        registered = {e.module.replace(".", "/") + ".py" for e in EGRESS_POINTS}
        unaccounted = [
            name
            for name in self.network_modules()
            if name not in registered and name not in self.NOT_EGRESS
        ]
        assert not unaccounted, (
            f"these modules can reach the network and are neither a registered "
            f"egress point nor an accepted exception: {unaccounted}"
        )

    def test_the_exceptions_are_still_real(self) -> None:
        """An exception list whose entries no longer apply is how a real
        violation eventually inherits somebody else's waiver."""
        for name in self.NOT_EGRESS:
            assert (SRC / name).is_file(), f"{name} no longer exists; drop its exception"
            assert name in self.network_modules(), (
                f"{name} no longer touches the network; drop its exception rather "
                "than leaving a waiver lying around for the next module"
            )


class TestTheGateRefusesRatherThanReports:
    def test_require_raises_on_a_refusal(self) -> None:
        """A returned decision can be ignored, and the call site where somebody
        forgets is the one that matters."""
        gate = Gate.for_tenant("EU", tenant_id="t1")
        with pytest.raises(ResidencyRefused):
            gate.require("siem-export", destination="US", jurisdiction="EU")

    def test_undeclared_is_refused_and_says_to_declare(self) -> None:
        gate = Gate.for_tenant("EU")
        with pytest.raises(ResidencyRefused) as caught:
            gate.require("siem-export", destination="EU")
        assert "Undeclared is not" in caught.value.remedy

    def test_an_unstated_destination_is_refused(self) -> None:
        gate = Gate.for_tenant("EU")
        with pytest.raises(ResidencyRefused) as caught:
            gate.require("siem-export", destination="", jurisdiction="EU")
        assert "State the destination" in caught.value.remedy

    def test_a_tenant_with_no_rule_is_not_deny_everything(self) -> None:
        """Most deployments are in one region with no obligation at all, and a
        product that refused every movement until a rule was written is a
        product nobody finishes installing."""
        gate = Gate.for_tenant(None)
        assert gate.require("siem-export", destination="US").may_proceed

    def test_a_typo_in_the_egress_name_is_refused(self) -> None:
        """Accepting a free string would make a typo an egress point that
        quietly checks nothing."""
        from prama.core.errors import ValidationError

        with pytest.raises(ValidationError, match="no such egress point"):
            Gate.for_tenant("EU").require("siem_export", destination="EU")

    def test_the_refusal_has_its_own_error_type(self) -> None:
        """An operator triaging a failed export needs to tell "may not go
        there" from "the request was malformed"."""
        assert ResidencyRefused.code == "RESIDENCY.REFUSED"
