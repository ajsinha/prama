"""The banking domain pack.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from prama.packs.banking import (
    cobol,
    fix,
    fpml,
    iso8583,
    iso20022,
    obligations,
    reconciliations,
    regulatory,
    swift,
)
from prama.packs.banking.calendars import SPECS, CalendarSpec, install, spec
from prama.packs.banking.holidays import Observance, Rule, easter_sunday, observed

__all__ = [
    "SPECS",
    "CalendarSpec",
    "Observance",
    "Rule",
    "cobol",
    "easter_sunday",
    "fix",
    "fpml",
    "install",
    "iso8583",
    "iso20022",
    "obligations",
    "observed",
    "reconciliations",
    "regulatory",
    "spec",
    "swift",
]
