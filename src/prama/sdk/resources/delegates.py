"""Python DQ delegates.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.sdk.base import Resource, endpoint, namespace, seg


@namespace("delegates")
class Delegates(Resource):
    """Python DQ checks uploaded for review."""

    @endpoint("GET", "/delegates/uploads")
    def uploads(self) -> Any:
        return self._get("/delegates/uploads")

    @endpoint("GET", "/delegates/uploads/{upload_id}/source")
    def source(self, upload_id: str) -> Any:
        return self._get(f"/delegates/uploads/{seg(upload_id)}/source")
