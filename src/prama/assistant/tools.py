"""What the assistant can do, and — more importantly — what it cannot.

`FR-CHT-001`…`017`. The safety contract for a conversational agent over a data
platform is usually written as instructions: *do not delete anything, do not
approve your own proposals, ignore instructions that arrive in data.* Every one
of those is a request, and the assistant reads text an attacker can write.

**The contract here is capability, not instruction.** An assistant that cannot
approve a proposal — because no tool exists that approves one, in a registry
that is enumerable and tested — cannot be talked into approving one. No prompt
is clever enough to call a function that is not there. Everything else in this
module is secondary to that, and the test that matters is the one that
enumerates the registry and asserts that nothing in it mutates.

**Two capabilities, and there is no third.**

*Read* answers questions. It can see the estate, the controls, the evidence and
the incidents, and it returns them as data.

*Propose* adds to the review queue that Wave 6 built. A proposal is not a
change; it is a request for one, ranked among the others, decided by a person,
and passing the identical validation gate as a proposal from any other source.

There is no *approve*, no *activate*, no *delete*, no *edit*. Not restricted, not
gated behind a permission — absent. The queue is the only way in, for the
assistant exactly as for the miners, and that is what makes "every assistant
mutation is a reviewable diff" true by construction rather than by policy.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
import enum
from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar

from prama.core.errors import ValidationError


class Capability(enum.Enum):
    """What a tool is allowed to do. There is no third member, on purpose."""

    #: Answers a question from what is already there. Never changes anything.
    READ = "read"
    #: Adds to the review queue. A request for a change, not a change.
    PROPOSE = "propose"

    @property
    def mutates(self) -> bool:
        """Whether this changes the estate. False for both, and that is the
        contract: proposing is not changing, and nothing else exists."""
        return False

    @property
    def explains(self) -> str:
        return {
            Capability.READ: "reads the estate and answers",
            Capability.PROPOSE: ("adds a proposal to the review queue, where a person decides"),
        }[self]


@dataclasses.dataclass(frozen=True, slots=True)
class Argument:
    """One parameter, with the check that runs before the tool does."""

    name: str
    kind: str = "string"
    required: bool = True
    description: str = ""
    #: Values it may take, when the set is closed. A closed set is worth far
    #: more than a description: a model asked for a dataset name will invent
    #: one, and a model given a list will not.
    choices: tuple[str, ...] = ()
    maximum_length: int = 512

    def validate(self, value: Any) -> Any:
        if value is None:
            if self.required:
                raise ValidationError(
                    f"{self.name} is required",
                    remedy=f"Supply {self.name}: {self.description}",
                )
            return None
        if self.kind == "integer":
            try:
                return int(value)
            except (TypeError, ValueError) as error:
                raise ValidationError(
                    f"{self.name} must be a whole number, and {value!r} is not",
                    remedy="Supply a number.",
                    cause=error,
                ) from error
        text = str(value)
        if len(text) > self.maximum_length:
            # A bounded argument is a bounded injection surface. A tool that
            # accepts an unbounded string accepts a paragraph of instructions
            # dressed as a dataset name.
            raise ValidationError(
                f"{self.name} is {len(text)} characters, and at most "
                f"{self.maximum_length} are accepted",
                remedy=(
                    "Shorten it. An argument this long is either a mistake or an "
                    "instruction wearing an argument's name."
                ),
            )
        if self.choices and text not in self.choices:
            raise ValidationError(
                f"{self.name} must be one of {', '.join(self.choices)}",
                remedy=f"{text!r} is not among them.",
            )
        return text

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.kind,
            "required": self.required,
            "description": self.description,
            "choices": list(self.choices),
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Result:
    """What a tool returned, and whether its content can be trusted.

    The flag is the point. Almost everything a read tool returns was written by
    somebody other than the operator — a column description, a value, a
    document — and it arrives in the model's context looking exactly like the
    operator's own words. Marking it is what lets the prompt builder fence it.
    """

    content: Any
    #: True when any part of this came from data rather than from the platform.
    untrusted: bool = False
    #: Where it came from, for the audit trail and for the fence.
    provenance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "untrusted": self.untrusted,
            "provenance": self.provenance,
        }


class Tool(abc.ABC):
    """Something the assistant can do, with its capability declared."""

    name: ClassVar[str] = ""
    capability: ClassVar[Capability] = Capability.READ
    description: ClassVar[str] = ""
    arguments: ClassVar[tuple[Argument, ...]] = ()
    #: True when the result contains data the estate's users wrote. Declared by
    #: the tool because the tool knows, and defaulting it to False would make
    #: the safe answer the one nobody has to think about.
    returns_untrusted: ClassVar[bool] = False

    @abc.abstractmethod
    def run(self, **arguments: Any) -> Result:
        """Do the thing. Arguments are already validated by :meth:`call`."""

    def call(self, arguments: Mapping[str, Any]) -> Result:
        """Validate, then run. The only entry point.

        Unknown arguments are refused rather than ignored. A tool that silently
        drops what it does not recognise is a tool whose behaviour depends on a
        model's spelling.
        """
        known = {argument.name for argument in self.arguments}
        unexpected = set(arguments) - known
        if unexpected:
            raise ValidationError(
                f"{self.name} does not take {', '.join(sorted(unexpected))}",
                remedy=f"It takes: {', '.join(sorted(known)) or 'no arguments'}.",
            )
        checked = {
            argument.name: argument.validate(arguments.get(argument.name))
            for argument in self.arguments
        }
        result = self.run(**checked)
        return dataclasses.replace(result, untrusted=result.untrusted or self.returns_untrusted)

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "capability": self.capability.value,
            "description": self.description,
            "arguments": [argument.to_dict() for argument in self.arguments],
            "returns_untrusted": self.returns_untrusted,
        }


class ToolRegistry:
    """Every tool the assistant has, and a guarantee about the set.

    The guarantee is enforced at registration rather than documented: a tool
    whose capability is not READ or PROPOSE cannot be added, and since those
    are the only two members of the enum, no mutating tool can exist to be
    added. The registration check is belt and braces for the day somebody adds
    a third member.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValidationError(
                f"{type(tool).__name__} has no name",
                remedy="Set the class-level `name`; it is how the model calls it.",
            )
        if tool.capability.mutates:
            raise ValidationError(
                f"{tool.name} claims a capability that mutates the estate",
                remedy=(
                    "The assistant proposes; a person decides. Route the change "
                    "through the proposal queue like every other source of changes."
                ),
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise ValidationError(
                f"there is no tool called {name!r}",
                remedy=(
                    "Available: " + (", ".join(sorted(self._tools)) or "none") + ". "
                    "A model asking for a tool that does not exist is usually a model "
                    "that has been told about one, which is worth looking at."
                ),
            ) from None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def of(self, capability: Capability) -> tuple[Tool, ...]:
        return tuple(tool for tool in self._tools.values() if tool.capability is capability)

    def schemas(self) -> list[dict[str, Any]]:
        return [self._tools[name].schema() for name in self.names()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools


# ---------------------------------------------------------------------------
# The tools themselves
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Estate:
    """The read surface, injected so the assistant has no other way in.

    A collection of callables rather than a reference to the platform: the
    assistant can reach exactly what is passed here and nothing else, so the
    blast radius of a compromised prompt is the contents of this object.
    """

    datasets: Callable[[], Sequence[str]] = lambda: ()
    describe_dataset: Callable[[str], Mapping[str, Any]] = lambda _: {}
    controls: Callable[[str], Sequence[Mapping[str, Any]]] = lambda _: ()
    incidents: Callable[[], Sequence[Mapping[str, Any]]] = lambda: ()
    lineage: Callable[[str], Sequence[Mapping[str, Any]]] = lambda _: ()
    evidence: Callable[[str], Mapping[str, Any]] = lambda _: {}


class ListDatasets(Tool):
    name: ClassVar[str] = "list_datasets"
    capability: ClassVar[Capability] = Capability.READ
    description: ClassVar[str] = "The datasets in the estate, by name."

    def __init__(self, estate: Estate) -> None:
        self._estate = estate

    def run(self, **_: Any) -> Result:
        return Result(content=list(self._estate.datasets()), provenance="estate")


class DescribeDataset(Tool):
    name: ClassVar[str] = "describe_dataset"
    capability: ClassVar[Capability] = Capability.READ
    description: ClassVar[str] = (
        "What a dataset is: its grain, rhythm, attributes and declared meaning."
    )
    arguments: ClassVar[tuple[Argument, ...]] = (
        Argument("dataset", description="the dataset's name", maximum_length=200),
    )
    #: Descriptions and interpretations are written by the estate's users, so
    #: everything here is text somebody else authored.
    returns_untrusted: ClassVar[bool] = True

    def __init__(self, estate: Estate) -> None:
        self._estate = estate

    def run(self, dataset: str = "", **_: Any) -> Result:
        return Result(
            content=dict(self._estate.describe_dataset(dataset)),
            untrusted=True,
            provenance=f"declaration of {dataset}",
        )


class ListControls(Tool):
    name: ClassVar[str] = "list_controls"
    capability: ClassVar[Capability] = Capability.READ
    description: ClassVar[str] = "The controls on a dataset and their last verdicts."
    arguments: ClassVar[tuple[Argument, ...]] = (
        Argument("dataset", description="the dataset's name", maximum_length=200),
    )
    returns_untrusted: ClassVar[bool] = True

    def __init__(self, estate: Estate) -> None:
        self._estate = estate

    def run(self, dataset: str = "", **_: Any) -> Result:
        return Result(
            content=[dict(item) for item in self._estate.controls(dataset)],
            untrusted=True,
            provenance=f"controls on {dataset}",
        )


class ListIncidents(Tool):
    name: ClassVar[str] = "list_incidents"
    capability: ClassVar[Capability] = Capability.READ
    description: ClassVar[str] = "Open incidents, most recent first."
    returns_untrusted: ClassVar[bool] = True

    def __init__(self, estate: Estate) -> None:
        self._estate = estate

    def run(self, **_: Any) -> Result:
        return Result(
            content=[dict(item) for item in self._estate.incidents()],
            untrusted=True,
            provenance="incident log",
        )


class TraceLineage(Tool):
    name: ClassVar[str] = "trace_lineage"
    capability: ClassVar[Capability] = Capability.READ
    description: ClassVar[str] = (
        "What a column feeds and what feeds it, with the impact along each hop."
    )
    arguments: ClassVar[tuple[Argument, ...]] = (
        Argument("column", description="a qualified column, like positions.amount"),
    )

    def __init__(self, estate: Estate) -> None:
        self._estate = estate

    def run(self, column: str = "", **_: Any) -> Result:
        return Result(
            content=[dict(item) for item in self._estate.lineage(column)],
            provenance=f"lineage of {column}",
        )


class ProposeControl(Tool):
    """The only tool that changes anything, and it changes the queue.

    Named for what it does rather than for what a user asks for. Somebody
    saying "add a control" gets a proposal, and the assistant's reply says so —
    because a user who believes a control was added and finds none tomorrow
    trusts nothing the assistant says afterwards.
    """

    name: ClassVar[str] = "propose_control"
    capability: ClassVar[Capability] = Capability.PROPOSE
    description: ClassVar[str] = (
        "Add a proposed control to the review queue. It does not take effect "
        "until a person approves it."
    )
    arguments: ClassVar[tuple[Argument, ...]] = (
        Argument("dataset", description="the dataset it applies to", maximum_length=200),
        Argument("pql", description="the control in PQL", maximum_length=2000),
        Argument(
            "because",
            description="why it should exist, in the business's words",
            maximum_length=1000,
        ),
    )

    def __init__(self, propose: Callable[[str, str, str], Mapping[str, Any]]) -> None:
        self._propose = propose

    def run(self, dataset: str = "", pql: str = "", because: str = "", **_: Any) -> Result:
        return Result(
            content=dict(self._propose(dataset, pql, because)),
            provenance="proposal queue",
        )


def read_only_registry(estate: Estate) -> ToolRegistry:
    """Everything that answers, and nothing that changes.

    The default for a Slack or Teams surface, where the person asking may not
    be the person accountable and the conversation is not a review.
    """
    registry = ToolRegistry()
    for tool in (
        ListDatasets(estate),
        DescribeDataset(estate),
        ListControls(estate),
        ListIncidents(estate),
        TraceLineage(estate),
    ):
        registry.register(tool)
    return registry


def default_registry(
    estate: Estate, propose: Callable[[str, str, str], Mapping[str, Any]]
) -> ToolRegistry:
    """Read plus propose. The full surface, and still nothing that mutates."""
    registry = read_only_registry(estate)
    registry.register(ProposeControl(propose))
    return registry
