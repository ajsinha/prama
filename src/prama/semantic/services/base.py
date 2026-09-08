"""Service base: a unit of work, an approval policy, and an audit obligation.

Every mutation writes an audit event. That is not diligence, it is the
requirement: a declaration nobody can attribute is a declaration an auditor will
not accept.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from prama.core.errors import ValidationError
from prama.db.session import UnitOfWork
from prama.semantic.policy import ApprovalPolicy

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """A stable, readable identifier derived from a business name.

    Used for URLs, GitOps filenames and cross-references. Derived rather than
    typed, because asking a business user to invent a slug is asking them to do
    a computer's job.
    """
    normalised = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = _SLUG_STRIP.sub("_", normalised.lower()).strip("_")
    if not slug:
        raise ValidationError(
            f"{value!r} contains no characters usable in an identifier",
            remedy="Give the object a name containing letters or digits.",
            context={"name": value},
        )
    return slug[:128]


class SemanticService:
    """Base: a unit of work, an approval policy, and an audit obligation."""

    def __init__(self, uow: UnitOfWork, *, policy: ApprovalPolicy | None = None) -> None:
        self._uow = uow
        self._policy = policy or ApprovalPolicy()

    def _audit(
        self,
        *,
        tenant_id: str,
        action: str,
        object_kind: str,
        object_id: str,
        actor_id: str | None,
        actor_kind: str = "human",
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Record who did what.

        ``actor_kind`` distinguishes a person from the platform acting on its
        own behalf — a health check or a drift detection has no human author,
        and recording one would be a small lie in a permanent record.
        """
        self._uow.audit.record(
            tenant_id=tenant_id,
            action=action,
            object_kind=object_kind,
            object_id=object_id,
            actor_id=actor_id,
            actor_kind=actor_kind,
            detail=detail or {},
        )
