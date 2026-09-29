"""Delegates uploaded through the console: vetted in a sandbox, approved by a second person.

The path from a file somebody chose in a browser to a control that runs it:

1. **Received.** A `.py` file, at most 256 KB, UTF-8. Nothing else.
2. **Vetted in a sandbox** (`prama.delegates.vet`, a resource-limited
   subprocess). It runs the full conformance kit: the pre-import scan,
   admission's determinism and robustness probes, the one-pass check, and a
   streaming run. The file must hold exactly one delegate. The server process
   never imports uploaded code, not even to vet it.
3. **Proposed**, with what vetting found. A refusal is not stored; the
   uploader is shown why.
4. **Approved** by somebody holding `control:approve` who is *not* the
   uploader, or **rejected**. A version is immutable, so a rejected
   `name@version` stays rejected; fix it and raise the version.
5. **Adopted** by a host when it runs controls: the approved source is written
   to `delegates.upload_dir`, content-addressed by its SHA-256, and registered
   from its stored description *without being imported*. It runs only in the
   sandbox, which re-hashes the file before importing it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from prama.core.errors import ForbiddenError, NotFoundError, ValidationError

#: The largest delegate file accepted. A check is a page or two of Python.
MAX_BYTES = 256 * 1024


def vet(filename: str, body: bytes, *, timeout_s: int = 120) -> dict[str, Any]:
    """Run the conformance kit over one file, in the delegate sandbox."""
    from prama.delegates.sandbox import run_isolated

    with tempfile.TemporaryDirectory(prefix="prama-vet-") as scratch:
        (Path(scratch) / filename).write_bytes(body)
        Path(scratch).chmod(0o755)  # readable inside the worker's own namespace
        try:
            finished = run_isolated(["-m", "prama.delegates.vet", scratch], timeout_s=timeout_s)
        except TimeoutError:
            return {"ok": False, "checks": [], "described": [], "error": "vetting timed out"}
    try:
        return dict(json.loads(finished.output.decode("utf-8") or "{}"))
    except json.JSONDecodeError:
        return {
            "ok": False,
            "checks": [],
            "described": [],
            "error": finished.errors[-300:] or "vetting failed",
        }


async def submit(uow: Any, tenant_id: str, filename: str, body: bytes, *, by: str) -> Any:
    """Vet an uploaded file and, if it conforms, propose it for approval."""
    if not by:
        raise ValidationError(
            "an upload needs a signed-in person", remedy="Sign in: the uploader is on record."
        )
    name = Path(filename or "").name
    if not name.endswith(".py") or name.startswith(("_", ".")):
        raise ValidationError(
            f"{name or 'the file'} is not a delegate file",
            remedy="Upload one .py file whose name does not start with _ or a dot.",
        )
    if len(body) > MAX_BYTES:
        raise ValidationError(
            f"{name} is larger than {MAX_BYTES // 1024} KB",
            remedy="A delegate is a page or two of Python; move reference data into parameters.",
        )
    try:
        source = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{name} is not UTF-8 text", remedy="Save it as UTF-8.") from exc
    result = vet(name, body)
    described = result.get("described") or []
    failed = [c for c in result.get("checks") or [] if not c.get("passed")]
    if result.get("error") or failed or len(described) != 1:
        why = result.get("error") or "; ".join(
            f"{c['name']}: {c.get('detail') or 'failed'}" for c in failed
        )
        if not why:
            why = f"the file holds {len(described)} delegates; upload exactly one per file"
        raise ValidationError(f"{name} was refused: {why}", remedy="Fix it and upload it again.")
    (entry,) = described
    return await uow.delegate_uploads.submit(
        tenant_id,
        name=str(entry["name"]),
        version=str(entry["version"]),
        filename=name,
        source=source,
        source_hash=hashlib.sha256(body).hexdigest(),
        state="proposed",
        described=json.dumps(entry, sort_keys=True),
        findings=json.dumps(result.get("checks") or []),
        by=by,
    )


async def decide(
    uow: Any, tenant_id: str, upload_id: str, *, action: str, by: str, note: str = ""
) -> Any:
    """`approve`, `reject` (a proposal) or `retire` (an approved delegate)."""
    row = await uow.delegate_uploads.one(tenant_id, upload_id)
    if row is None:
        raise NotFoundError("no such upload", remedy="Uploads are listed on the Delegates page.")
    allowed = {"approve": "proposed", "reject": "proposed", "retire": "approved"}
    if action not in allowed or row.state != allowed[action]:
        raise ValidationError(
            f"{row.name}@{row.version} is {row.state}; it cannot be {action}d",
            remedy="Approve or reject a proposal; retire an approved delegate.",
        )
    if action == "approve" and by == row.submitted_by:
        # Four eyes: code that will run against the estate's data is approved
        # by somebody other than the person who wrote it.
        raise ForbiddenError(
            "the uploader cannot approve their own delegate",
            remedy="Ask another person holding control:approve to review and approve it.",
        )
    state = {"approve": "approved", "reject": "rejected", "retire": "retired"}[action]
    return await uow.delegate_uploads.decide(row, state=state, by=by, note=note)


async def adopt(uow: Any, tenant_id: str, host: Any) -> int:
    """Register this tenant's approved uploads with *host*, without importing them."""
    adopted = 0
    # Re-adopted from scratch on every pass: an upload retired since the last
    # one must not keep running in a long-lived host (the scheduler's).
    host.registry.drop_uploads()
    root = Path(host.upload_dir) / tenant_id
    for row in await uow.delegate_uploads.approved(tenant_id):
        target = root / row.source_hash / row.filename
        body = row.source.encode("utf-8")
        if hashlib.sha256(body).hexdigest() != row.source_hash:
            host.registry.refused[row.name] = "the stored source no longer matches its hash"
            continue
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        if host.registry.adopt_described(
            json.loads(row.described), origin=f"upload:{target}", source_hash=row.source_hash
        ):
            adopted += 1
    return adopted
