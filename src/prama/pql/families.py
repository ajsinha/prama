"""The type families, in a module with no dependencies.

Five names that both the type checker and the function catalogue need. They
live apart from either because putting them in one made the other import it,
and the catalogue and the checker genuinely depend on each other — the checker
consults the catalogue to type a call, and the catalogue declares its argument
types in the checker's vocabulary.

A shared leaf module is the honest resolution. Hoisting one into the other
would have been a lie about which depends on which.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Final

#: Deliberately coarse. A control cares whether two things are comparable, not
#: whether one is INT and the other BIGINT — and a checker that insisted on the
#: narrow distinction would reject correct controls over every warehouse whose
#: column happened to be declared a different width.
NUMBER: Final = "number"
TEXT: Final = "text"
BOOLEAN: Final = "boolean"
TEMPORAL: Final = "temporal"

#: Not a family: the absence of one. A column Prama has never seen, a
#: parameter the run supplies, a function whose result depends on its
#: arguments. Comparing an unknown with anything is permitted, because
#: refusing would make every control over an unprofiled dataset fail to check.
UNKNOWN: Final = "unknown"

FAMILIES: Final = (NUMBER, TEXT, BOOLEAN, TEMPORAL, UNKNOWN)
