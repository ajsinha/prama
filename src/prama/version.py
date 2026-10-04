"""The single authority for Prama's version.

Every other version string in the repository — banners, API responses, packaging
metadata, documentation — is a copy of this constant and can rot. Read it here.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Final

#: Semantic version of the platform. Wave 1 of the ten-wave plan (docs/corpus/19).
VERSION: Final[str] = "0.1.0"

#: The IR version this build compiles to. Independently versioned from the
#: platform, because third parties may target the IR (FR-EXT-010).
IR_VERSION: Final[str] = "0.1.0"

#: The schema contract this build expects. Bumped whenever schema/*.sql changes
#: in a way that is not backward compatible. There are no migrations: a mismatch
#: is reported loudly by `prama db verify` rather than repaired silently.
SCHEMA_VERSION: Final[str] = "1"

PRODUCT_NAME: Final[str] = "Prama"
PRODUCT_TAGLINE: Final[str] = "Declare it. Prove it. Trust it."
