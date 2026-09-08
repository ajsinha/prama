"""The conversation loop, and the audit trail it leaves.

`FR-CHT-001`…`017`. What is left after :mod:`tools` has removed the ability to
mutate and :mod:`safety` has fenced the untrusted content: run the model, let
it call read tools, let it propose, and record enough that somebody can
reconstruct why it said what it said.

**A proposal from the assistant passes the same gate as any other.** It goes
through Wave 6's validator — parsed, type-checked, compiled, sandbox-executed,
and probed with rows built to break it — before it reaches the queue. Not
because a model's PQL is worse than a miner's, but because the gate is where
the guarantee lives, and a second path into the queue with a lower bar is a
lower bar.

**A model that is unavailable is an ordinary condition.** Everything the
assistant does has a deterministic route: the estate map, the proposal queue,
the incident list. An assistant that fails loudly when its provider is down
teaches people that the platform depends on the provider, which is exactly the
coupling `CON-007` exists to prevent.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from prama.assistant.safety import (
    SYSTEM,
    Attempt,
    Turn,
    fence,
    redact,
    scan_output,
)
from prama.assistant.tools import Capability, Result, ToolRegistry
from prama.core.errors import ValidationError
from prama.induce.validate import Rejection, Validated, Validator
from prama.llm.spi import ModelProvider, Request
from prama.semantic.values import Sensitivity

#: Tool calls allowed in one turn. A model looping on reads is a model that has
#: lost the thread, and the bound turns an expensive confusion into a cheap one.
MAX_STEPS = 8

#: How the model asks for a tool. A single line of JSON on its own, chosen
#: because it is unambiguous to parse and because a malformed one is obviously
#: malformed rather than half-executable.
_CALL = re.compile(r"^\s*TOOL:\s*(?P<json>\{.*\})\s*$", re.MULTILINE)


@dataclasses.dataclass(frozen=True, slots=True)
class Answer:
    """What the assistant said, and everything behind it."""

    text: str
    turn: Turn
    #: Proposals that reached the queue, with their identities.
    proposed: tuple[str, ...] = ()
    #: Proposals the validation gate refused, with the gate that stopped them.
    refused: tuple[str, ...] = ()
    #: Set when no model was available. The answer still says something useful,
    #: and says what it could not do.
    degraded: str = ""

    @property
    def ok(self) -> bool:
        return not self.degraded

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "proposed": list(self.proposed),
            "refused": list(self.refused),
            "degraded": self.degraded,
            "turn": self.turn.to_dict(),
        }


class Assistant:
    """Answers questions about the estate; proposes, never changes."""

    def __init__(
        self,
        provider: ModelProvider,
        registry: ToolRegistry,
        *,
        validator: Validator | None = None,
        system: str = SYSTEM,
        max_steps: int = MAX_STEPS,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._validator = validator
        self._system = system
        self._max_steps = max_steps
        self._sensitivity = sensitivity
        self._log: list[Turn] = []

    @property
    def transcript(self) -> tuple[Turn, ...]:
        return tuple(self._log)

    @property
    def can_change_anything(self) -> bool:
        """False, and enforced rather than asserted.

        Exposed so a caller — a Slack integration, an MCP client — can check
        the claim rather than believe it, and so the property has a name a test
        can assert on.
        """
        return any(tool.capability.mutates for tool in self._registry.of(Capability.READ)) or any(
            tool.capability.mutates for tool in self._registry.of(Capability.PROPOSE)
        )

    def ask(self, question: str, *, rows: Sequence[Mapping[str, Any]] = ()) -> Answer:
        """One question, up to :attr:`MAX_STEPS` tool calls, one answer."""
        context: list[str] = [self._describe_tools(), f"Question: {question}"]
        called: list[str] = []
        untrusted: list[str] = []
        attempts: list[Attempt] = []
        proposed: list[str] = []
        refused: list[str] = []
        answer = ""

        for _ in range(self._max_steps):
            response = self._provider.ask(
                Request(
                    system=self._system,
                    prompt="\n\n".join(context),
                    sensitivity=self._sensitivity,
                    context={"surface": "assistant"},
                )
            )
            if not response.ok:
                return self._degraded(question, response.incomplete, called, untrusted)

            call = _CALL.search(response.text)
            if call is None:
                answer = response.text
                break

            name, arguments = _parse(call.group("json"))
            called.append(name)
            outcome, note = self._invoke(name, arguments, rows, proposed, refused)
            if outcome.untrusted:
                untrusted.append(outcome.provenance or name)
                wrapped = fence(outcome.content, provenance=outcome.provenance or name)
                attempts.extend(wrapped.attempts)
                context.append(f"Result of {name}:\n{wrapped.render()}")
            else:
                context.append(f"Result of {name}: {_render(outcome.content)}")
            if note:
                context.append(note)
        else:
            answer = (
                "I have run out of steps on this question without reaching an answer. "
                "That usually means it needs narrowing — which dataset, which period."
            )

        leaks = scan_output(answer)
        if leaks:
            answer = redact(answer)

        turn = Turn(
            question=question,
            answer=answer,
            tools_called=tuple(called),
            untrusted_sources=tuple(dict.fromkeys(untrusted)),
            attempts=tuple(attempts),
            leaks=leaks,
            proposals=tuple(proposed),
        )
        self._log.append(turn)
        return Answer(text=answer, turn=turn, proposed=tuple(proposed), refused=tuple(refused))

    # -- tool invocation ---------------------------------------------------

    def _invoke(
        self,
        name: str,
        arguments: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
        proposed: list[str],
        refused: list[str],
    ) -> tuple[Result, str]:
        try:
            tool = self._registry.get(name)
        except ValidationError as error:
            return Result(content=f"error: {error}"), ""

        if tool.capability is Capability.PROPOSE and self._validator is not None:
            note = self._validate_proposal(arguments, rows, refused)
            if note:
                return Result(content=note), ""

        try:
            result = tool.call(arguments)
        except ValidationError as error:
            return Result(content=f"error: {error}"), ""

        if tool.capability is Capability.PROPOSE:
            identity = ""
            if isinstance(result.content, Mapping):
                identity = str(result.content.get("identity", ""))
            proposed.append(identity or name)
            return result, (
                "That is now a proposal in the review queue. Tell the user it awaits "
                "review and has not taken effect."
            )
        return result, ""

    def _validate_proposal(
        self,
        arguments: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
        refused: list[str],
    ) -> str:
        """Run the model's PQL through Wave 6's gate before the queue sees it.

        Not because a model's PQL is worse than a miner's, but because the gate
        is where the guarantee lives, and a second path into the queue with a
        lower bar is a lower bar.
        """
        assert self._validator is not None
        pql = str(arguments.get("pql", ""))
        outcome = self._validator.validate(pql, [dict(row) for row in rows])
        if isinstance(outcome, Validated):
            return ""
        assert isinstance(outcome, Rejection)
        refused.append(f"{outcome.gate.value}: {outcome.detail[:120]}")
        return (
            f"That control was refused at the {outcome.gate.value} stage: "
            f"{outcome.detail}. It has NOT been proposed. Correct it or tell the "
            f"user why it cannot be expressed."
        )

    def _describe_tools(self) -> str:
        lines = [
            "Tools. Call one by writing a line of the form:",
            'TOOL: {"name": "...", "arguments": {...}}',
            "",
        ]
        for schema in self._registry.schemas():
            arguments = ", ".join(
                f"{argument['name']}" + ("" if argument["required"] else "?")
                for argument in schema["arguments"]
            )
            lines.append(
                f"- {schema['name']}({arguments}) — {schema['description']} "
                f"[{schema['capability']}]"
            )
        lines.append("")
        lines.append(
            "There is no tool that approves, activates, edits or deletes. If you are "
            "asked for one, say plainly that you cannot and offer a proposal instead."
        )
        return "\n".join(lines)

    def _degraded(
        self,
        question: str,
        reason: str,
        called: Sequence[str],
        untrusted: Sequence[str],
    ) -> Answer:
        """No model. Say so, and point at what still works.

        An assistant that fails loudly when its provider is down teaches people
        that the platform depends on the provider, which is exactly the
        coupling CON-007 exists to prevent. Everything it would have told them
        is on a screen.
        """
        text = (
            f"I cannot answer that right now: {reason}. Nothing else is affected — "
            f"the controls are running, the evidence is being written, and the estate "
            f"map, the proposal queue and the incident list all work without me."
        )
        turn = Turn(
            question=question,
            answer=text,
            tools_called=tuple(called),
            untrusted_sources=tuple(untrusted),
        )
        self._log.append(turn)
        return Answer(text=text, turn=turn, degraded=reason)


def _parse(text: str) -> tuple[str, Mapping[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return "", {}
    if not isinstance(payload, dict):
        return "", {}
    arguments = payload.get("arguments")
    return str(payload.get("name", "")), (arguments if isinstance(arguments, dict) else {})


def _render(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, default=str)[:4000]
