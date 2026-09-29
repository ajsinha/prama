"""Models through the gateway.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from prama.sdk.base import Resource, body, endpoint, namespace


@namespace("llm")
class Llm(Resource):
    """Models through the gateway: budgeted, ledgered, never a verdict."""

    @endpoint("POST", "/llm/chat")
    def chat(
        self,
        purpose: str,
        prompt: str,
        *,
        system: str | None = None,
        sensitivity: str | None = None,
    ) -> Any:
        return self._post(
            "/llm/chat",
            body(purpose=purpose, prompt=prompt, system=system, sensitivity=sensitivity),
        )

    @endpoint("POST", "/llm/chat/stream")
    def chat_stream(
        self,
        purpose: str,
        prompt: str,
        *,
        system: str | None = None,
        sensitivity: str | None = None,
    ) -> Any:
        """The streamed answer, returned whole as text."""
        return self._post(
            "/llm/chat/stream",
            body(purpose=purpose, prompt=prompt, system=system, sensitivity=sensitivity),
        )
