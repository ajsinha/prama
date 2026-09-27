"""The provider seam: a model, behind an interface, with nothing assumed.

`FR-CHT-010` asks for Anthropic, Azure OpenAI, Bedrock, Vertex and self-hosted.
The list matters less than the shape: an organisation that will not send its
data to a hosted model must be able to run the same features against something
in its own datacentre, and one that has already bought a model somewhere must
be able to bring it. A platform that can only work with one vendor's endpoint
is a platform half the intended buyers cannot deploy.

Three things this interface insists on that a thin HTTP wrapper would not:

**A request records what it asked.** The prompt, the model, the parameters and
the grammar are all part of the answer's provenance. A proposal a person is
being asked to approve, whose origin is "a model said so", is worth very little
unless the exact question can be reproduced — and reproducing it is also the
only way to tell a model regression from a data change.

**Determinism is requested and never assumed.** Temperature zero and a seed
where the provider has one; but the provider may ignore both, so nothing
downstream may depend on two calls agreeing. Everything a model produces is
re-validated against the data every time, which makes the question moot — and
that is the design, rather than a mitigation for it.

**Nothing leaves without being allowed to.** A prompt carries the sensitivity
of the most sensitive thing in it, and a hosted provider refuses to send one
above its permitted class. That check lives here, at the boundary, rather than
in each caller — a residency rule enforced in six call sites is a residency
rule with a hole in it.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import abc
import dataclasses
import enum
import hashlib
from collections.abc import Iterator
from typing import Any, ClassVar

from prama.core import pjson
from prama.core.errors import ValidationError
from prama.llm.redact import redact
from prama.security.egress import Gate, ResidencyRefused
from prama.semantic.values import Sensitivity


class Hosting(enum.Enum):
    """Where a provider runs, which decides what may be sent to it."""

    #: A vendor's multi-tenant API.
    HOSTED = "hosted"
    #: A vendor's model inside the customer's own cloud tenancy.
    TENANT = "tenant"
    #: A model on the customer's own hardware, reachable without leaving the
    #: network. The only class an air-gapped deployment can use at all.
    SELF_HOSTED = "self_hosted"

    @property
    def permits(self) -> frozenset[Sensitivity]:
        """Sensitivity classes this hosting may receive."""
        if self is Hosting.SELF_HOSTED:
            return frozenset(Sensitivity)
        if self is Hosting.TENANT:
            return frozenset(Sensitivity) - {Sensitivity.RESTRICTED}
        return frozenset({Sensitivity.PUBLIC, Sensitivity.INTERNAL})


@dataclasses.dataclass(frozen=True, slots=True)
class Grammar:
    """A constraint on what the model may emit.

    Supplied to providers that can enforce it during decoding, and used as the
    validator for those that cannot — see :mod:`prama.induce.grammar`. Carried
    here rather than in the prompt because "please only emit valid PQL" is a
    request and this is a constraint, and the difference shows up on the tenth
    generation rather than the first.
    """

    name: str
    #: The grammar itself, in whatever notation the provider takes. Providers
    #: that cannot constrain decoding ignore it and the caller validates.
    definition: str = ""
    #: A regular expression the whole completion must match, for providers
    #: whose only constraint mechanism is a pattern.
    pattern: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "definition": self.definition, "pattern": self.pattern}


@dataclasses.dataclass(frozen=True, slots=True)
class Request:
    """One question put to a model, recorded in full."""

    #: What the model is being asked to be. Separate from the question so the
    #: two can be versioned independently — a change to the instructions is a
    #: change to every proposal the system makes.
    system: str
    prompt: str
    #: The highest sensitivity of anything embedded in the prompt. Checked
    #: against the provider's hosting before anything is sent.
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    grammar: Grammar | None = None
    max_tokens: int = 1024
    #: Zero, always, for anything that becomes a proposal. Exposed rather than
    #: fixed because summarisation and explanation are different jobs with a
    #: different answer.
    temperature: float = 0.0
    seed: int | None = 7
    #: Free-form, recorded with the response: which dataset, which run.
    context: dict[str, str] = dataclasses.field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        """A hash of everything that decides the answer.

        Two requests with the same fingerprint asked the same question. Used to
        cache, and more importantly to tell "the model changed its mind" from
        "we asked something different", which are indistinguishable without it
        and lead to opposite conclusions.
        """
        return hashlib.sha256(
            pjson.canonical(
                {
                    "system": self.system,
                    "prompt": self.prompt,
                    "grammar": self.grammar.to_dict() if self.grammar else None,
                    "temperature": self.temperature,
                    "seed": self.seed,
                    "max_tokens": self.max_tokens,
                }
            )
        ).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "prompt": self.prompt,
            "sensitivity": self.sensitivity.value,
            "grammar": self.grammar.to_dict() if self.grammar else None,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "seed": self.seed,
            "context": dict(self.context),
            "fingerprint": self.fingerprint,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class Response:
    """What came back, and enough to reproduce or dispute it."""

    text: str
    model: str
    provider: str
    request_fingerprint: str
    #: Tokens in and out, for the budget. A feature whose cost cannot be
    #: attributed is a feature that gets switched off wholesale when the bill
    #: arrives, rather than tuned.
    input_tokens: int = 0
    output_tokens: int = 0
    #: True when the provider enforced the grammar during decoding rather than
    #: the caller checking afterwards. Recorded because it changes what a
    #: failure means: a grammar-constrained provider emitting invalid PQL is a
    #: provider bug, and an unconstrained one doing so is Tuesday.
    grammar_enforced: bool = False
    latency_ms: float = 0.0
    #: Set when the provider declined or truncated. Never raised as an
    #: exception by the provider itself: a model refusing to answer is an
    #: ordinary outcome, and the caller has a perfectly good fallback.
    incomplete: str = ""

    @property
    def ok(self) -> bool:
        return not self.incomplete and bool(self.text.strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "request_fingerprint": self.request_fingerprint,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "grammar_enforced": self.grammar_enforced,
            "latency_ms": round(self.latency_ms, 2),
            "incomplete": self.incomplete,
        }


class ModelProvider(abc.ABC):
    """A model Prama can ask a question of."""

    #: The name used in configuration.
    name: ClassVar[str] = ""
    hosting: ClassVar[Hosting] = Hosting.HOSTED
    #: Whether this provider can constrain decoding to a grammar. When it
    #: cannot, the caller validates and retries — which works, and costs more.
    supports_grammar: ClassVar[bool] = False

    @abc.abstractmethod
    def complete(self, request: Request) -> Response:
        """Answer one request. Implementations do not enforce residency."""

    #: The residency gate, installed by whatever built this provider. ``None``
    #: means no residency rule has been declared — which is a refusal for a
    #: provider that leaves the network, not a permission. See
    #: :meth:`permit_residency`.
    residency_gate: Gate | None = None
    #: The **jurisdiction** this provider's endpoint sits in — "EU", "US" —
    #: not a cloud region name. It is compared against the tenant's declared
    #: residency list, so "eu-west-1" would be refused as a destination outside
    #: every rule, which is a confusing way to be right.
    residency_region: str = ""

    def ask(self, request: Request) -> Response:
        """Answer one request, refusing to send what may not be sent.

        The residency check lives here rather than in :meth:`complete`, so a
        provider written by somebody else cannot omit it, and rather than in
        each caller, because a rule enforced in six places is a rule with a
        hole in it.
        """
        self.permit(request)
        self.permit_residency(request)
        return self.complete(self.withhold(request))

    def ask_stream(self, request: Request) -> Iterator[str]:
        """The answer in pieces, after the same checks as :meth:`ask`.

        A provider that cannot stream yields its whole answer once, so every
        provider can be streamed from and a caller need not ask which can.
        """
        self.permit(request)
        self.permit_residency(request)
        yield from self.stream(self.withhold(request))

    def stream(self, request: Request) -> Iterator[str]:
        """Override to stream for real. The default completes, then yields once."""
        response = self.complete(request)
        if response.text:
            yield response.text

    @staticmethod
    def withhold(request: Request) -> Request:
        """The request with secrets and card numbers removed from its text.

        Applied here, on the one path every provider shares, for the reason
        residency is: a rule each caller must remember is a rule with a hole
        in it. Prompts used to reach the provider unredacted; only answers
        were checked (FR-CHT-013). The response then carries the fingerprint
        of what was actually sent.
        """
        system, prompt = redact(request.system), redact(request.prompt)
        if system == request.system and prompt == request.prompt:
            return request
        return dataclasses.replace(request, system=system, prompt=prompt)

    def permit_residency(self, request: Request) -> None:
        """Refuse a prompt whose subject may not travel to this provider.

        Distinct from :meth:`permit`, which asks what *class* of data this is.
        This asks where the data is *from* and where the model *is* — two
        questions with different answers, and the registry in
        :mod:`prama.security.egress` names ``model-inference`` as an egress
        point precisely because the second one had no enforcement at all: the
        sensitivity check was standing in for a residency check it cannot
        perform. A prompt carrying EU column names and samples reached a US
        endpoint so long as nobody had labelled it PII.

        A self-hosted model is exempt because nothing leaves the network. For
        anything else an absent gate is a refusal: undeclared is not
        unrestricted, and treating it as unrestricted is how the one deployment
        nobody got round to configuring is the one that exports.
        """
        if self.hosting is Hosting.SELF_HOSTED:
            return
        if self.residency_gate is None:
            raise ResidencyRefused(
                f"no residency rule is declared, so nothing may be sent to the "
                f"{self.hosting.value} model {self.name!r}",
                remedy=(
                    "Install a residency gate on the provider (Gate.for_tenant with "
                    "the tenant's declared residency), or use a self-hosted provider. "
                    "Prama refuses rather than assuming the movement is allowed."
                ),
                context={"provider": self.name, "hosting": self.hosting.value},
            )
        self.residency_gate.require(
            "model-inference",
            destination=self.residency_region,
            jurisdiction=request.context.get("jurisdiction", ""),
            subject=request.context.get("dataset", "") or "a prompt",
        )

    def permit(self, request: Request) -> None:
        if request.sensitivity not in self.hosting.permits:
            raise ValidationError(
                f"{request.sensitivity.value} content may not be sent to a "
                f"{self.hosting.value} model",
                remedy=(
                    "Use a self-hosted provider for this class of data, mask the "
                    "values before they enter the prompt, or send only the metadata. "
                    "Prama will not make this decision for you."
                ),
                context={
                    "provider": self.name,
                    "hosting": self.hosting.value,
                    "sensitivity": request.sensitivity.value,
                },
            )

    def describe(self) -> str:
        constraint = (
            "constrains decoding to a grammar"
            if self.supports_grammar
            else "cannot constrain decoding; output is validated and retried"
        )
        return f"{self.name} ({self.hosting.value}), {constraint}"


class ProviderRegistry:
    """Every model provider available to this deployment."""

    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        if not provider.name:
            raise ValidationError(
                f"{type(provider).__name__} has no name",
                remedy="Set the class-level `name`; it is how configuration selects it.",
            )
        self._providers[provider.name] = provider

    def get(self, name: str) -> ModelProvider:
        try:
            return self._providers[name]
        except KeyError:
            raise ValidationError(
                f"no model provider named {name!r}",
                remedy=(
                    "Configured providers: "
                    + (", ".join(sorted(self._providers)) or "none")
                    + ". Every model-assisted feature is optional; with none "
                    "configured Prama runs its deterministic half and says so."
                ),
                context={"requested": name},
            ) from None

    def find(self, name: str) -> ModelProvider | None:
        return self._providers.get(name)

    def for_sensitivity(self, sensitivity: Sensitivity) -> tuple[str, ...]:
        """Providers permitted to see this class of data, most local first.

        Ordered that way deliberately: when a self-hosted model can do the job,
        it is the right answer whatever else is configured, because it is the
        one that does not move the data.
        """
        eligible = [
            provider
            for provider in self._providers.values()
            if sensitivity in provider.hosting.permits
        ]
        order = {Hosting.SELF_HOSTED: 0, Hosting.TENANT: 1, Hosting.HOSTED: 2}
        eligible.sort(key=lambda p: (order[p.hosting], p.name))
        return tuple(p.name for p in eligible)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def __len__(self) -> int:
        return len(self._providers)

    def __contains__(self, name: object) -> bool:
        return name in self._providers
