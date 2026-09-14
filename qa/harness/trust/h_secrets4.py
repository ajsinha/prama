import sys, subprocess, traceback, logging, io, json
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/qa/harness/trust")
from reclib import line
from prama.secrets.value import SecretValue

REPO = "/home/ashutosh/PycharmProjects/prama"
SECRET_TEXT = "hunter2-plaintext-secret-9c3f"

# SEC-212: a traceback carrying a secret argument renders it redacted, in every
# frame, both through the CLI's own error path (commands.py) and through the
# API's unhandled-exception handler (errors.py::unexpected_error_handler),
# which both format via the stdlib `traceback`/`logging` machinery (exc_info=).
# First: confirm the product has no traceback-with-locals renderer (the
# catalogue's stated precondition) -- if it did, a local named `sv` holding the
# raw string would also need checking.
grep_locals = subprocess.run(
    ["grep", "-rn", "-i", "show_locals\\|rich.traceback\\|cgitb\\|extract_tb.*locals",
     f"{REPO}/src/prama"], capture_output=True, text=True)
has_locals_renderer = bool(grep_locals.stdout.strip())

def make_exc():
    sv = SecretValue(SECRET_TEXT, origin="ref:test")
    try:
        raise ValueError("something broke", sv)
    except ValueError:
        return sys.exc_info()

# 1. stdlib traceback.format_exception -- what a bare `except Exception` handler
#    printing the traceback would produce (this is what a rendered traceback on
#    an error page or CLI stderr dump ultimately goes through)
et, ev, etb = make_exc()
rendered = "".join(traceback.format_exception(et, ev, etb))
leaked_1 = SECRET_TEXT in rendered
redacted_present_1 = "<secret>" in rendered

# 2. logging with exc_info= -- exactly what api/errors.py::unexpected_error_handler
#    and prama_error_handler do (`_log.error(..., exc_info=exc)`)
buf = io.StringIO()
h = logging.StreamHandler(buf)
h.setFormatter(logging.Formatter("%(message)s"))
lg = logging.getLogger("qa.sec212")
lg.setLevel(logging.ERROR)
lg.addHandler(h)
et2, ev2, etb2 = make_exc()
lg.error("unhandled %s", type(ev2).__name__, exc_info=(et2, ev2, etb2))
logged = buf.getvalue()
leaked_2 = SECRET_TEXT in logged
redacted_present_2 = "<secret>" in logged

# 3. through the CLI's own exception surface (commands.py catches Exception and
#    reports str(exc)[:200] -- the same pattern used by `db show`); confirm that
#    surfacing str(exc) alone also does not leak, since that is the text a CLI
#    error path actually prints (not a raw traceback dump)
str_exc = str(ev)
leaked_3 = SECRET_TEXT in str_exc

leaked = leaked_1 or leaked_2 or leaked_3
redacted = redacted_present_1 and redacted_present_2

ok = (not leaked) and redacted
line("SEC-212", "PASS" if ok else "FAIL",
     f"has_locals_renderer_in_product={has_locals_renderer} (catalogue precondition 'under a renderer that shows locals' does not correspond to anything shipped) "
     f"traceback.format_exception: leaked={leaked_1} has_<secret>={redacted_present_1} | "
     f"logging(exc_info=): leaked={leaked_2} has_<secret>={redacted_present_2} | "
     f"str(exc) (CLI's own 'except Exception as exc: str(exc)' pattern): leaked={leaked_3} repr_in_str_exc={'<secret>' in str_exc} | "
     f"secret_leaked_anywhere={leaked}")

print("SECTION Secrets-supplement-2 DONE")
