"""``${VAR:default}`` substitution over the typed configuration tree.

Placeholders are resolved after the sources are merged, against the environment
first and the merged configuration second. Resolving against the configuration
itself is what lets one setting be expressed in terms of another
(``evidence.path: ${paths.data}/evidence``) without a templating engine.

The algorithm is DishtaYantra's (`prama.core.config.properties.resolve_value`):
innermost placeholders first, so a nested reference such as
``${db.${env}.host}`` resolves. Rules, all chosen so that a mistake fails loudly
rather than producing a plausible-looking wrong value:

* ``${VAR}`` with no value and no default is an error, not an empty string.
* Recursion is bounded; a cycle is reported with the chain that formed it.
* ``$${NOT_A_VAR}`` escapes to a literal ``${NOT_A_VAR}``.
* Substitution applies to strings only. A key whose value is an int is left
  alone, so numeric settings cannot be corrupted by a stray ``$``.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import os
from typing import Any

from prama.core.config.properties import MAX_DEPTH, resolve_value


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
        self._root: dict[str, Any] = {}

    def resolve_tree(self, tree: dict[str, Any]) -> dict[str, Any]:
        """Return *tree* with every string value resolved."""
        self._root = tree
        walked = self._walk(tree, path="")
        assert isinstance(walked, dict)
        return walked

    def _walk(self, node: Any, *, path: str) -> Any:
        if isinstance(node, dict):
            return {k: self._walk(v, path=f"{path}.{k}" if path else k) for k, v in node.items()}
        if isinstance(node, list):
            return [self._walk(v, path=f"{path}[{i}]") for i, v in enumerate(node)]
        if isinstance(node, str):
            return self.resolve_value(node, path=path)
        return node

    def resolve_value(self, value: str, *, path: str = "") -> str:
        """Resolve a single string, recursively."""
        return resolve_value(value, self._lookup, path=path)

    def _lookup(self, name: str) -> str | None:
        """Environment first, then a dotted path into the merged configuration."""
        if name in self._environ:
            return self._environ[name]
        cursor: Any = self._root
        for part in name.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                return None
            cursor = cursor[part]
        return cursor if isinstance(cursor, str) else (str(cursor) if cursor is not None else None)
