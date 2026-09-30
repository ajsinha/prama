"""Python DQ delegates: upload for review, decide with four eyes, and try one on rows.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import builtins
from typing import Any

from prama_sdk.base import Resource, endpoint, namespace, seg
from prama_sdk.resources._files import FileLike, upload


@namespace("delegates")
class Delegates(Resource):
    """Python DQ checks: what may run, uploads and their vetting, approval, and try-outs."""

    @endpoint("GET", "/delegates")
    def list(self) -> Any:
        """Configured delegates, those refused (with why), and every upload with its state."""
        return self._get("/delegates")

    @endpoint("POST", "/delegates/submissions")
    def upload(self, delegate: FileLike, *, filename: str = "delegate.py") -> Any:
        """Upload one ``.py`` file (a path, or its source with *filename*). It is vetted in
        the sandbox and proposed; a refusal raises ``ValidationError`` saying why."""
        return self._call(
            "POST",
            "/delegates/submissions",
            files={"delegate": upload(delegate, filename, "text/x-python")},
        )

    @endpoint("GET", "/delegates/submissions/{upload_id}")
    def get(self, upload_id: str) -> Any:
        """One upload: what it declares, what vetting found, who decided, and its source."""
        return self._get(f"/delegates/submissions/{seg(upload_id)}")

    @endpoint("POST", "/delegates/submissions/{upload_id}/decide")
    def decide(self, upload_id: str, action: str, *, note: str = "") -> Any:
        """``approve``, ``reject`` or ``retire``. The uploader cannot approve their own."""
        return self._post(
            f"/delegates/submissions/{seg(upload_id)}/decide", {"action": action, "note": note}
        )

    def approve(self, upload_id: str, *, note: str = "") -> Any:
        return self.decide(upload_id, "approve", note=note)

    def reject(self, upload_id: str, *, note: str = "") -> Any:
        return self.decide(upload_id, "reject", note=note)

    def retire(self, upload_id: str, *, note: str = "") -> Any:
        return self.decide(upload_id, "retire", note=note)

    @endpoint("POST", "/delegates/vet")
    def vet(self, delegate: FileLike, *, filename: str = "delegate.py") -> Any:
        """Run the conformance kit over a file in the sandbox; nothing is stored."""
        return self._call(
            "POST",
            "/delegates/vet",
            files={"delegate": upload(delegate, filename, "text/x-python")},
        )

    @endpoint("POST", "/delegates/try")
    def test(
        self,
        delegate: str,
        rows: builtins.list[dict[str, Any]],
        **params: Any,
    ) -> Any:
        """Run *delegate* over *rows* exactly as a control would, sandboxed.

        Returns the control's PQL, the metrics, and the verdict the
        deterministic engine gives them at the default threshold.
        """
        return self._post("/delegates/try", {"delegate": delegate, "rows": rows, "params": params})

    @endpoint("GET", "/delegates/uploads")
    def uploads(self) -> Any:
        """Approved uploads, with the SHA-256 a remote agent checks them against."""
        return self._get("/delegates/uploads")

    @endpoint("GET", "/delegates/uploads/{upload_id}/source")
    def source(self, upload_id: str) -> Any:
        """An approved upload's source text."""
        return self._get(f"/delegates/uploads/{seg(upload_id)}/source")
