"""Third-party validators, and the contract that makes them safe to load.

The second half of the expression layer. Some checks are genuinely code — a
national identifier scheme, a proprietary check digit, a market-specific
convention — and Prama already has the right shape for them:
:class:`SemanticValidator`, with a SQL screen that narrows and a Python
``check`` that decides. ISIN and LEI ride exactly that path.

So this does **not** add a ``PYTHON("…")`` escape hatch to the language. That
would break replay (arbitrary code can read a clock), break versioning (the
code is part of the control's meaning and not part of its hash), remove the
reference interpreter's ability to check the compiler, and become the place
every hard control goes — until the declarative core is decoration around a
pile of Python. The PQL surface stays ``IS VALID 'my_scheme'``, which already
exists, is already two-stage, and already explains itself.

What is enforced, rather than documented:

* **Purity.** No clock, no network, no filesystem, no model. Checked by
  scanning the module's imports at registration, the same way the architecture
  tests scan the source tree — and by running the check twice on the same input
  and requiring the same answer.
* **Identity.** The implementation's source is hashed and folded into the plan
  id, so editing a validator changes the *control's* identity rather than
  silently changing what past evidence meant.
* **No adjudication by a model.** ``CON-007``: a plugin that imports an LLM
  client is refused, because a model output would then determine a pass or fail
  verdict on data.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import ast as python_ast
import dataclasses
import hashlib
import inspect
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from prama.core.errors import ValidationError
from prama.core.log import get_logger

_log = get_logger(__name__)

#: The entry-point group a distribution advertises validators under, alongside
#: the five groups already in ``plugins.entry_point_groups``.
ENTRY_POINT_GROUP = "prama.validators"

#: Modules a validator may not import, and what each would break. The message
#: matters as much as the rule: somebody whose plugin is refused needs to know
#: which guarantee they tripped, not merely that they tripped one.
FORBIDDEN: dict[str, str] = {
    "random": "a random source makes a control unreplayable",
    "secrets": "a random source makes a control unreplayable",
    "socket": "a network call makes a control unreplayable and leaks the data",
    "http": "a network call makes a control unreplayable and leaks the data",
    "urllib": "a network call makes a control unreplayable and leaks the data",
    "requests": "a network call makes a control unreplayable and leaks the data",
    "httpx": "a network call makes a control unreplayable and leaks the data",
    "subprocess": "running a process is arbitrary code execution",
    "os": "the environment and the filesystem make a control unreplayable",
    "pathlib": "reading a file makes a control unreplayable",
    "openai": "a model output would decide a verdict (CON-007)",
    "anthropic": "a model output would decide a verdict (CON-007)",
    # Finding H3. Absent from this list for four releases, while `docs/19` and
    # `docs/08` both recorded "a plugin that imports a clock, a socket or a
    # model is refused at registration" as built. `time` is the clock, and a
    # validator doing `import time; time.gmtime()` was admitted — the call ban
    # below covers `now`/`today`/`utcnow`/`monotonic`/`perf_counter` and not
    # `time()`, `gmtime()` or `localtime()`.
    "time": "reading the clock makes a control unreplayable",
}

#: Prama packages a validator may not reach into. Listed separately because a
#: prefix match against the bare root would have banned every ``prama.*``
#: import — including ``prama.core.errors``, which every validator needs.
FORBIDDEN_PRAMA: dict[str, str] = {
    "prama.llm": "a model output would decide a verdict (CON-007)",
    "prama.agent": "reaching the execution fabric is not a validator's business",
    "prama.db": "a validator that reads the database is not a function of its input",
}

#: Impure *calls*, rather than impure modules. ``datetime`` is not banned: a
#: date-format validator legitimately parses one, and refusing the module would
#: refuse the validator. What is banned is asking it what time it is.
FORBIDDEN_CALLS: dict[str, str] = {
    "now": "reading the clock makes a control unreplayable",
    "today": "reading the clock makes a control unreplayable",
    "utcnow": "reading the clock makes a control unreplayable",
    "monotonic": "reading the clock makes a control unreplayable",
    "perf_counter": "reading the clock makes a control unreplayable",
    "gmtime": "reading the clock makes a control unreplayable",
    "localtime": "reading the clock makes a control unreplayable",
    "time_ns": "reading the clock makes a control unreplayable",
}

#: Ways to import a module without an ``import`` statement, which an AST scan
#: keyed on `ast.Import` cannot see. Banned outright rather than resolved: the
#: argument is an expression, so what it names is not knowable without running
#: it, and a gate that has to run the thing it is gating is not a gate.
#: Called *bare*, as builtins. `re.compile` is an ordinary thing for a format
#: validator to do and `compile` the builtin is not, so the two are told apart
#: by shape: a bare Name here, an Attribute below. Conflating them refused
#: every shipped validator, which is how this distinction was found.
FORBIDDEN_DYNAMIC: dict[str, str] = {
    "__import__": "a dynamic import hides what a validator reaches for",
    "exec": "running generated code is arbitrary code execution",
    "eval": "running generated code is arbitrary code execution",
    "compile": "running generated code is arbitrary code execution",
}

#: Called as a method on something — `importlib.import_module(...)`. No
#: legitimate validator reaches for these under any spelling.
FORBIDDEN_DYNAMIC_ATTRIBUTES: dict[str, str] = {
    "import_module": "a dynamic import hides what a validator reaches for",
    "load_module": "a dynamic import hides what a validator reaches for",
}

#: Inputs every registered validator is run against, twice, at registration.
#: Not a correctness corpus — a determinism and robustness one. A validator
#: that raises on an empty string will raise in production on the first blank.
PROBES: tuple[str, ...] = ("", " ", "0", "ABC123", "GB0002634946", "x" * 256, "é")


@dataclasses.dataclass(frozen=True, slots=True)
class Provenance:
    """Where a validator came from, and what it was when it was loaded."""

    name: str
    module: str
    distribution: str
    #: SHA-256 of the implementation's source. This is what makes editing a
    #: validator change the identity of every control that uses it, instead of
    #: silently changing what last month's evidence meant.
    implementation_hash: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def implementation_hash(validator: Any) -> str:
    """A stable hash of the validator's own source.

    The *class* source, not the module's: a module holding ten validators would
    otherwise give all ten the same hash, and editing one would change the
    identity of controls using the other nine.
    """
    try:
        source = inspect.getsource(type(validator))
    except (OSError, TypeError):
        # A validator with no retrievable source — built dynamically, or from a
        # zipped distribution without source. Refused rather than hashed as
        # empty: an implementation nobody can hash is one whose changes nobody
        # can detect.
        raise ValidationError(
            f"the source of {type(validator).__name__} cannot be read, so it cannot be hashed",
            remedy=(
                "A validator's implementation is part of every control that uses it, "
                "and its hash is part of the plan id. Ship it as source rather than "
                "constructing it at run time."
            ),
            context={"validator": type(validator).__name__},
        ) from None
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:32]


def scan_source(path: str) -> list[tuple[str, str]]:
    """Everything in one file that a validator may not do.

    Takes a *path*, not a loaded object, so a plugin can be vetted **before it
    is imported**. That matters more than it looks: importing a module runs its
    top-level code, so a gate that had to import the thing it was gating would
    already have run it by the time it decided to refuse.

    Entry-point loading cannot avoid importing — that is how Python plugins
    work — so this is the pre-flight an operator runs against a distribution
    before enabling it. It has **no CLI front end yet** — this docstring named
    ``prama validators scan`` for four waves and that command has never
    existed, which is the same overclaim as findings H1 and H7. Call
    :func:`scan_source` directly until there is one.
    """
    try:
        tree = python_ast.parse(Path(path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        # A file that will not parse cannot be scanned, and a scan that
        # silently returns "nothing forbidden" for it would be worse than no
        # scan. The loader refuses it on import instead, loudly.
        return []
    found: list[tuple[str, str]] = []
    for node in python_ast.walk(tree):
        # Dynamic imports first: `__import__("socket")` and
        # `importlib.import_module(name)` are invisible to a scan that only
        # looks at `ast.Import`, and a validator using either was admitted.
        if isinstance(node, python_ast.Call):
            why = None
            called = ""
            if isinstance(node.func, python_ast.Name):
                called = node.func.id
                why = FORBIDDEN_DYNAMIC.get(called)
            elif isinstance(node.func, python_ast.Attribute):
                called = node.func.attr
                why = FORBIDDEN_DYNAMIC_ATTRIBUTES.get(called)
            if why is not None:
                found.append((f"{called}()", why))

        names: list[str] = []
        if isinstance(node, python_ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, python_ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            # Match the whole dotted prefix, not the root. Matching the root
            # made "prama.llm" ban "prama.core.errors" — which every validator
            # imports, so every validator was refused.
            if (reason := FORBIDDEN.get(name.split(".")[0])) is not None:
                found.append((name, reason))
                continue
            for banned, why in FORBIDDEN_PRAMA.items():
                if name == banned or name.startswith(banned + "."):
                    found.append((name, why))

        # Impure calls, wherever they appear. Scanning for the attribute rather
        # than the module is what lets a date validator parse a date without
        # being allowed to ask what today is.
        if isinstance(node, python_ast.Call):
            attribute = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if isinstance(attribute, str) and attribute in FORBIDDEN_CALLS:
                found.append((f"{attribute}()", FORBIDDEN_CALLS[attribute]))
    return found


def forbidden_imports(validator: Any) -> list[tuple[str, str]]:
    """Everything the validator's module — and the modules it pulls in — does
    that it may not.

    Scanned rather than trusted: a declaration of purity from the thing being
    checked is not evidence of purity.

    **Its first-party imports are followed**, one level of the package tree at
    a time, because reading only the validator's own file left the simplest
    evasion open (finding H3): put `import socket, os, random` in a helper
    beside it and import the helper. The helper is where the impurity lives and
    the scan never opened it.

    Only modules inside the validator's own distribution are followed. The
    standard library and third-party packages are not walked — that is an
    unbounded scan, and the ban list already names the ones that matter at the
    point the validator reaches for them.
    """
    module = inspect.getmodule(type(validator))
    path = getattr(module, "__file__", None) if module else None
    if not path:
        return []

    found = list(scan_source(path))
    root = Path(path).parent
    seen = {Path(path).resolve()}
    pending = [Path(path)]
    while pending:
        current = pending.pop()
        for helper in _local_imports(current, root):
            resolved = helper.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            pending.append(helper)
            found.extend(
                (f"{helper.stem}.{name}", f"{why} (reached through {helper.name})")
                for name, why in scan_source(str(helper))
            )
    return found


def _local_imports(path: Path, root: Path) -> list[Path]:
    """Sibling modules this file imports, as paths that exist."""
    try:
        tree = python_ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    names: set[str] = set()
    for node in python_ast.walk(tree):
        if isinstance(node, python_ast.Import):
            names.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, python_ast.ImportFrom):
            if node.level:  # a relative import is by definition local
                names.update(alias.name for alias in node.names)
                if node.module:
                    names.add(node.module.split(".")[-1])
            elif node.module:
                names.add(node.module.split(".")[-1])
    return [candidate for name in sorted(names) if (candidate := root / f"{name}.py").is_file()]


def check_determinism(validator: Any) -> None:
    """Run the check twice on the same inputs and require the same answer.

    Import scanning catches the obvious sources of non-determinism. This
    catches the rest — a cached global, a set iteration order, a validator that
    mutates itself — and it catches a validator that raises on an empty string,
    which will happen on the first blank in production.
    """
    for probe in PROBES:
        try:
            first = validator.judge(probe)
            second = validator.judge(probe)
        except Exception as exc:
            raise ValidationError(
                f"{validator.name} raised on the input {probe!r}",
                remedy=(
                    "A validator must return a judgement for any string, including "
                    "an empty one. Raising means the first blank in production takes "
                    "the control down instead of failing the row."
                ),
                context={"validator": validator.name, "input": probe},
            ) from exc
        if (first.valid, first.reason) != (second.valid, second.reason):
            raise ValidationError(
                f"{validator.name} gave two answers for the same input {probe!r}",
                remedy=(
                    "A control has to replay: the same plan against the same snapshot "
                    "must produce the same verdict. Remove the clock, the random "
                    "source or the mutable state."
                ),
                context={"validator": validator.name, "input": probe},
            )


class PluginRegistry:
    """Validators loaded from outside Prama, and what is known about each."""

    def __init__(self) -> None:
        self._provenance: dict[str, Provenance] = {}

    def admit(self, validator: Any, *, distribution: str = "") -> Provenance:
        """Check a validator and record where it came from.

        Every rule is checked before the validator is usable, and a failure
        names the guarantee it tripped rather than merely refusing.
        """
        if not getattr(validator, "name", ""):
            raise ValidationError(
                f"{type(validator).__name__} has no name",
                remedy="Set the class-level `name`; it is what a control says after IS VALID.",
            )
        banned = forbidden_imports(validator)
        if banned:
            listed = "; ".join(f"{module} — {reason}" for module, reason in sorted(set(banned)))
            raise ValidationError(
                f"{validator.name} imports something a validator may not: {listed}",
                remedy=(
                    "A validator is a pure function of one value. If the check "
                    "genuinely needs outside data, load it as a code list — which is "
                    "versioned, resolved as of a date, and frozen into the plan."
                ),
                context={"validator": validator.name, "imports": sorted({m for m, _ in banned})},
            )
        check_determinism(validator)

        module = inspect.getmodule(type(validator))
        provenance = Provenance(
            name=validator.name,
            module=getattr(module, "__name__", "?"),
            distribution=distribution,
            implementation_hash=implementation_hash(validator),
        )
        self._provenance[validator.name] = provenance
        _log.info(
            "admitted validator %s from %s (%s)",
            provenance.name,
            provenance.distribution or provenance.module,
            provenance.implementation_hash[:12],
        )
        return provenance

    def provenance(self, name: str) -> Provenance | None:
        return self._provenance.get(name)

    def hashes(self) -> dict[str, str]:
        """Implementation hashes by validator name, for folding into a plan."""
        return {name: p.implementation_hash for name, p in sorted(self._provenance.items())}

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._provenance))

    def __len__(self) -> int:
        return len(self._provenance)


#: The registry the platform consults.
PLUGINS = PluginRegistry()


def load_entry_points(
    registry: Any,
    plugins: PluginRegistry | None = None,
    *,
    disabled: Iterable[str] = (),
) -> list[Provenance]:
    """Load every advertised validator, refusing the ones that break a rule.

    A plugin that fails is refused *loudly* and the others still load: one bad
    distribution must not take an estate's validators down with it, and a
    refusal nobody sees is a validator silently missing from every control that
    named it.

    *disabled* names entry points an operator has switched off, from
    `plugins.disabled`. That setting existed in the shipped YAML, in no
    defaults mapping, and was read by nothing (QA finding CFG-036) — because
    this function was called by nothing either.
    """
    from importlib.metadata import entry_points

    plugins = plugins or PLUGINS
    refused = {name.strip().lower() for name in disabled if name.strip()}
    admitted: list[Provenance] = []
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        if entry.name.lower() in refused:
            # Said out loud. A validator that is missing because somebody
            # turned it off must not look the same as one that failed to load.
            _log.info("validator plugin %s is disabled by configuration", entry.name)
            continue
        try:
            validator = entry.load()()
            provenance = plugins.admit(
                validator, distribution=entry.dist.name if entry.dist else ""
            )
            registry.register(validator)
            admitted.append(provenance)
        except Exception as exc:
            _log.error("refused validator plugin %s: %s", entry.name, exc)
    return admitted
