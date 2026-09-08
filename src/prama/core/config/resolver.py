"""``${VAR:default}`` substitution.

Placeholders are resolved after the sources are merged, against the environment
first and the merged configuration second. Resolving against the configuration
itself is what lets one setting be expressed in terms of another
(``evidence.path: ${paths.data}/evidence``) without a templating engine.

Rules, all chosen so that a mistake fails loudly rather than producing a
plausible-looking wrong value:

* ``${VAR}`` with no value and no default is an error, not an empty string.
* Recursion is bounded; a cycle is reported with the chain that formed it.
* ``$${NOT_A_VAR}`` escapes to a literal ``${NOT_A_VAR}``.
* Substitution applies to strings only. A key whose value is an int is left
  alone, so numeric settings cannot be corrupted by a stray ``$``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
import re
from typing import Any, Final

from prama.core.errors import ConfigError

_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(
    r"""
    (?P<escape>\$)?            # a doubled $ escapes: $${X} -> literal ${X}
    \$\{
      (?P<name>[A-Za-z_][A-Za-z0-9_.\-]*)
      (?: : (?P<default>[^}]*) )?
    \}
    """,
    re.VERBOSE,
)

MAX_DEPTH: Final[int] = 16


class PlaceholderResolver:
    """Resolves ``${VAR:default}`` placeholders throughout a configuration tree."""

    def __init__(
        self,
        environ: dict[str, str] | None = None,
        *,
        max_depth: int = MAX_DEPTH,
    ) -> None:
        self._environ = environ if environ is not None else dict(os.environ)
        self._max_depth = max_depth

    def resolve_tree(self, tree: dict[str, Any]) -> dict[str, Any]:
        """Return *tree* with every string value resolved."""
        self._root = tree
        walked = self._walk(tree, path="")
        assert isinstance(walked, dict)
        return walked

    # -- internals ---------------------------------------------------------

    def _walk(self, node: Any, *, path: str) -> Any:
        if isinstance(node, dict):
            return {k: self._walk(v, path=f"{path}.{k}" if path else k) for k, v in node.items()}
        if isinstance(node, list):
            return [self._walk(v, path=f"{path}[{i}]") for i, v in enumerate(node)]
        if isinstance(node, str):
            return self.resolve_value(node, path=path)
        return node

    def resolve_value(self, value: str, *, path: str = "", _seen: tuple[str, ...] = ()) -> str:
        """Resolve a single string, recursively."""
        if len(_seen) > self._max_depth:
            raise ConfigError(
                f"placeholder recursion exceeded {self._max_depth} levels at {path or '<value>'}",
                code="CONFIG.PLACEHOLDER_CYCLE",
                remedy="Break the cycle: a placeholder chain must terminate in a literal.",
                context={"path": path, "chain": " -> ".join(_seen)},
            )

        def replace(match: re.Match[str]) -> str:
            if match.group("escape"):
                return match.group(0)[1:]  # drop one $, keep ${...} literal
            name = match.group("name")
            if name in _seen:
                raise ConfigError(
                    f"placeholder cycle: {' -> '.join((*_seen, name))}",
                    code="CONFIG.PLACEHOLDER_CYCLE",
                    remedy="Remove the self-reference; a placeholder cannot resolve to itself.",
                    context={"path": path, "name": name},
                )
            resolved = self._lookup(name)
            if resolved is None:
                default = match.group("default")
                if default is None:
                    raise ConfigError(
                        f"no value for ${{{name}}}" + (f" (referenced by {path})" if path else ""),
                        code="CONFIG.PLACEHOLDER_UNRESOLVED",
                        remedy=(
                            f"Set the environment variable {name}, define {name} in "
                            f"configuration, or give the placeholder a default: ${{{name}:value}}."
                        ),
                        context={"path": path, "name": name},
                    )
                resolved = default
            return self.resolve_value(resolved, path=path, _seen=(*_seen, name))

        return _PLACEHOLDER.sub(replace, value)

    def _lookup(self, name: str) -> str | None:
        """Environment first, then a dotted path into the merged configuration."""
        if name in self._environ:
            return self._environ[name]
        cursor: Any = getattr(self, "_root", {})
        for part in name.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                return None
            cursor = cursor[part]
        return cursor if isinstance(cursor, str) else (str(cursor) if cursor is not None else None)
