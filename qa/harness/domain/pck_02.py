import sys, subprocess, json
sys.path.insert(0, "/home/ashutosh/PycharmProjects/prama/src")
from datetime import date

results = []
def R(id_, ok, obs):
    results.append((id_, "PASS" if ok else "FAIL", obs))

def block(id_):
    def deco(fn):
        try:
            fn()
        except AssertionError as e:
            R(id_, False, f"AssertionError: {e}")
        except Exception as e:
            R(id_, False, f"{type(e).__name__}: {e}")
    return deco

PY = "/home/ashutosh/PycharmProjects/prama/.venv/bin/python"
PRAMA = "/home/ashutosh/PycharmProjects/prama/.venv/bin/prama"

@block("PCK-030")
def _():
    out1850 = subprocess.run([PRAMA,"pack","calendar","TARGET2","--year","1850"], capture_output=True, text=True)
    out2200 = subprocess.run([PRAMA,"pack","calendar","TARGET2","--year","2200"], capture_output=True, text=True)
    computed = ("closure(s) in 1850" in out1850.stdout) and ("closure(s) in 2200" in out2200.stdout)
    refused = "outside" in out1850.stdout.lower() or "horizon" in out1850.stdout.lower() or out1850.returncode != 0
    R("PCK-030", refused, f"1850 exit={out1850.returncode} refused_mention={refused}; stdout contains 2015 to 2040 describe: {'2015 to 2040' in out1850.stdout}; computed_anyway={computed}")

@block("PCK-031")
def _():
    # Directly exercise PackCalendarCommand logic with a spec carrying closures via monkeypatch, in-process
    from prama.packs.banking import calendars as cal_mod
    from prama.packs.banking.holidays import observed as obs_fn
    wanted = cal_mod.spec("TARGET2").with_closures([date(2026,9,9)])
    closures = sorted(obs_fn(wanted.rules, [2026]))
    adhoc_shown = date(2026,9,9) in closures
    describe_says = wanted.describe()
    R("PCK-031", adhoc_shown or "ad-hoc" not in describe_says, f"adhoc_in_listing={adhoc_shown}; describe={describe_says!r} (command uses observed(wanted.rules,...) not materialise, so closures attr is never unioned in)")

@block("PCK-032")
def _():
    from prama.packs.banking.calendars import spec
    empty = spec("TARGET2").describe()
    two = spec("TARGET2").with_closures([date(2026,1,1), date(2026,1,2)]).describe()
    ok = "none have been provided" in empty and "2 ad-hoc closure(s) supplied" in two
    R("PCK-032", ok, f"empty={empty!r} two={two!r}")

@block("PCK-033")
def _():
    from prama.packs.banking.calendars import spec
    orig = spec("TARGET2")
    _ = spec("TARGET2").with_closures([date(2026,9,9)])
    after = spec("TARGET2")
    R("PCK-033", len(after.closures)==0, f"len(original spec closures after with_closures call)={len(after.closures)}")

@block("PCK-034")
def _():
    from prama.packs.banking.calendars import install
    from prama.core.calendars import CalendarRegistry
    reg = CalendarRegistry()
    install(reg)
    try:
        install(reg)
        second_ok = False
        msg = "second bare call succeeded silently (duplicate)"
    except Exception as e:
        second_ok = True
        msg = f"{type(e).__name__}: {e}"
    install(reg, replace=True)  # should succeed
    R("PCK-034", second_ok, msg)

@block("PCK-035")
def _():
    from prama.packs.banking.calendars import install
    install()  # bare call, registry dropped
    from prama.schedule import spec as sched_spec
    try:
        sched_spec.parse("06:30 TARGET2")
        R("PCK-035", False, "schedule parsed OK, expected refusal")
    except Exception as e:
        R("PCK-035", True, f"refused as expected: {type(e).__name__}: {e}")

@block("PCK-036")
def _():
    from prama.packs.banking.calendars import spec
    a = spec("target2")
    b = spec("FEDERALRESERVE")
    try:
        spec("Sifma")
        c_raised = None
    except KeyError as e:
        c_raised = "KeyError"
    except Exception as e:
        c_raised = type(e).__name__
    R("PCK-036", a.name=="TARGET2" and b.name=="FederalReserve" and c_raised=="KeyError", f"a={a.name} b={b.name} c_raised={c_raised} (note: spec() itself raises bare KeyError; CLI wraps it)")

@block("PCK-037")
def _():
    out = subprocess.run([PRAMA,"pack","list"], capture_output=True, text=True)
    R("PCK-037", "TARGET2" in out.stdout, f"pack list stdout snippet around calendars: {[l for l in out.stdout.splitlines() if 'calendar' in l.lower() or 'TARGET2' in l]}")

print("=== PCK 030-037 ===")
for id_, res, obs in results:
    print(f"{id_}: {res} :: {obs}")
