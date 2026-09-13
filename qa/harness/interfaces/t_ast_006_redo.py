import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from logger import record
import prama.assistant.tools as tools_mod
from prama.assistant.tools import Estate, default_registry
from prama.assistant.agent import Assistant
from prama.llm.spi import ModelProvider, Request, Response, Hosting

class StubProvider(ModelProvider):
    name = "stub"
    hosting = Hosting.SELF_HOSTED
    def __init__(self, texts):
        self._texts = list(texts)
    def complete(self, request):
        text = self._texts.pop(0) if self._texts else "done"
        return Response(text=text, model="stub", provider="stub", request_fingerprint=request.fingerprint)

estate = Estate()
full = default_registry(estate, lambda d, p, b: {})
asst = Assistant(StubProvider(["x"]), full)

before = asst.can_change_anything

# Monkeypatch Capability.mutates at the CLASS level so every enum member (including the real
# Capability.READ / Capability.PROPOSE objects already held by the shipped tools) reports True --
# the only way to genuinely test whether the property is DERIVED (re-read live from
# tool.capability.mutates on every access) vs computed once and cached/hardcoded at construction.
original_property = tools_mod.Capability.mutates
try:
    tools_mod.Capability.mutates = property(lambda self: True)
    after = asst.can_change_anything  # same Assistant object, no reconstruction
finally:
    tools_mod.Capability.mutates = original_property

restored = asst.can_change_anything

ok6 = before is False and after is True and restored is False
record(
    "AST-006",
    "PASS" if ok6 else "FAIL",
    f"before_patch={before} after_forcing_Capability.mutates_to_True_at_the_class_level={after} "
    f"after_restoring={restored} -- patching Capability.mutates directly (rather than swapping a "
    f"tool's .capability instance attribute, which just removes the tool from ToolRegistry.of()'s "
    f"identity-based filter and proves nothing) is what actually exercises whether the property "
    f"re-reads the registry live; SAME Assistant instance used throughout with no reconstruction, "
    f"confirming the value is computed on each access rather than cached at __init__",
)
print("done ast006 redo")
