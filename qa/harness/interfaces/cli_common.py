import io
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path("/home/ashutosh/PycharmProjects/prama")
sys.path.insert(0, str(REPO_ROOT / "src"))

from prama.cli.base import Application, EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_DRIFT  # noqa
from prama.cli.commands import all_commands  # noqa

WORKDIR = Path(tempfile.mkdtemp(prefix="prama-qa-cli-"))

CALL_LOG = []  # list of (argv, code, traceback_seen: bool)
import json as _json

CALL_LOG_PATH = Path(__file__).parent / "cli_call_log.jsonl"


def run(argv, out=None):
    """Run the CLI in-process. Returns (code, stdout_text, stderr_text).

    Catches SystemExit (argparse usage errors) as well as normal returns.
    Also unexpected exceptions (non-PramaError, non-SystemExit) are caught here
    and reported as a traceback string in stderr-equivalent, exactly like what a
    real terminal user would see if Application.run let it propagate.
    """
    import contextlib
    import traceback as tb_mod

    out = out or io.StringIO()
    err = io.StringIO()
    real_stdout = io.StringIO()
    code = None
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(real_stdout):
        try:
            code = Application(all_commands()).run(argv, out=out)
        except SystemExit as e:
            code = e.code
        except BaseException:
            err.write(tb_mod.format_exc())
            code = "UNCAUGHT_EXCEPTION"
    stderr_text = err.getvalue()
    stdout_text = out.getvalue() + real_stdout.getvalue()
    has_tb = "Traceback (most recent call last)" in stderr_text or code == "UNCAUGHT_EXCEPTION"
    with open(CALL_LOG_PATH, "a") as f:
        f.write(_json.dumps({"argv": argv, "code": code, "traceback": has_tb}) + "\n")
    return code, stdout_text, stderr_text


def fresh_config(name="cli"):
    """Write a throwaway sqlite config file and return its path."""
    d = WORKDIR / name
    d.mkdir(parents=True, exist_ok=True)
    path = d / "application.yaml"
    path.write_text(
        "database:\n"
        "  dialect: sqlite\n"
        f"  sqlite:\n    path: {d / 'cli.db'}\n"
        f"  schema_dir: {REPO_ROOT / 'schema'}\n"
        "security:\n"
        "  session_secret: test-only-not-a-secret\n"
    )
    return path


def run_argparse_error(argv):
    """argparse SystemExit capture for usage errors (argparse writes to real stderr and calls sys.exit)."""
    import contextlib

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    code = None
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        try:
            Application(all_commands()).run(argv, out=buf_out)
        except SystemExit as e:
            code = e.code
    return code, buf_out.getvalue(), buf_err.getvalue()


def run_sub(argv, stdin_input=None, cwd=None, env=None):
    """Run the real `prama` executable as a subprocess (for stdin/tty-sensitive cases)."""
    import subprocess

    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    proc = subprocess.run(
        ["prama"] + argv,
        input=stdin_input,
        capture_output=True,
        text=True,
        cwd=cwd or str(WORKDIR),
        env=full_env,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr
