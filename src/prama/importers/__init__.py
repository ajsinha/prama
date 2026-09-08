"""Bringing an existing control estate across, and saying what did not come.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.importers.dbt import DbtImporter
from prama.importers.great_expectations import GreatExpectationsImporter
from prama.importers.soda import SodaImporter
from prama.importers.spi import (
    Caveat,
    Collector,
    Importer,
    ImportResult,
    Unmapped,
)

#: Every importer, by the name a person would use for the tool.
IMPORTERS: dict[str, type[Importer]] = {
    "dbt": DbtImporter,
    "soda": SodaImporter,
    "great_expectations": GreatExpectationsImporter,
}


def importer(name: str) -> Importer:
    from prama.core.errors import RegistryError

    key = name.strip().lower().replace("-", "_")
    if key not in IMPORTERS:
        raise RegistryError(
            f"no importer for {name!r}",
            remedy=f"Available: {', '.join(sorted(IMPORTERS))}.",
            context={"requested": name},
        )
    return IMPORTERS[key]()


__all__ = [
    "IMPORTERS",
    "Caveat",
    "Collector",
    "DbtImporter",
    "GreatExpectationsImporter",
    "ImportResult",
    "Importer",
    "SodaImporter",
    "Unmapped",
    "importer",
]
