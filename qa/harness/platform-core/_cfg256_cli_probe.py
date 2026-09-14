"""Helper for CFG-256: is `plugins.disabled` honoured by the real CLI path?

Invoked as a subprocess (one fresh interpreter per condition) because
`prama.packs.install_shipped` and `prama.classify.plugins.PLUGINS` are
process-global and idempotent-once -- exactly the semantics a real `prama`
invocation has, since each one is its own process. Faking that in-process
would mean resetting globals by hand and proving nothing about the actual
entry point (`prama.cli.main:main` -> `Application.run`).

Usage: python _cfg256_cli_probe.py '<json list of disabled names>' <config.yaml>
Prints one JSON object: {"rc": <exit code>, "admitted": [<names PLUGINS saw>]}
"""
import sys, json
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
import importlib.metadata as im

DISABLED = json.loads(sys.argv[1])
CFG_PATH = sys.argv[2]


class _FakeDist:
    name = "qa-fake-dist"


class _FakeEntry:
    def __init__(self, name):
        self.name = name
        self.dist = _FakeDist()

    def load(self):
        from prama.classify.validators import SemanticValidator, Judgement
        nm = self.name

        class _V(SemanticValidator):
            name = nm

            def check(self, value):
                return Judgement(True, "")

        return _V


from prama.classify.plugins import ENTRY_POINT_GROUP

_real_entry_points = im.entry_points


def _fake_entry_points(*, group=None, **kw):
    if group == ENTRY_POINT_GROUP:
        return [_FakeEntry("qa-plugin-a"), _FakeEntry("qa-plugin-b")]
    return _real_entry_points(group=group, **kw) if group is not None else _real_entry_points(**kw)


im.entry_points = _fake_entry_points

from prama.cli.base import Application, Command, CommandContext
from prama.classify.plugins import PLUGINS

captured = {}


class _FakeCmd(Command):
    name = "qa-fake-cmd"
    help = "qa probe"

    def run(self, ctx: CommandContext) -> int:
        captured["admitted"] = list(PLUGINS.names())
        return 0


app = Application([_FakeCmd()])
rc = app.run(["--config", CFG_PATH, "qa-fake-cmd"])
print(json.dumps({"rc": rc, "admitted": captured.get("admitted")}))
