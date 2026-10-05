<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Running Prama in PyCharm and IntelliJ IDEA

This page gets the server and its console running from an IDE, with the debugger and
live reload, in a few minutes. It assumes a clone of the repository. Installing
Python and the dependencies is in [QUICKSTART §1](../../QUICKSTART.md#1-install);
it is linked rather than repeated here, because a second copy of an install
procedure is the one that goes stale.

The repository ships **ready-made run configurations** in `.run/`. Both IDEs load
them automatically when the project opens, so most of this page is about
choosing the interpreter. After that, you pick a configuration and press Run.

![The console after the first run: the estate, as the business describes it](../assets/screenshots/estate.png)

## 1. Which IDE, and which edition

| IDE | What you need |
|---|---|
| **PyCharm** (Professional or Community) | Nothing extra. |
| **IntelliJ IDEA Ultimate** | The **Python** plugin (Settings → Plugins → Marketplace → "Python"). |
| **IntelliJ IDEA Community** | The **Python Community Edition** plugin. |

The run configurations are the same file format in all of them, because the
Python support in IntelliJ IDEA is the PyCharm engine as a plugin.

## 2. The interpreter

Prama needs **Python 3.12 or newer** and is developed on **3.13**, pinned in
`.python-version`. Create the environment once, from a terminal in the project
root, exactly as [QUICKSTART §1](../../QUICKSTART.md#which-python) shows (`uv venv
--python 3.13`, then `uv sync --extra dev --extra serve`); it also says why 3.12 is
the floor.

That leaves a virtual environment in `.venv/`. Point the IDE at it; do not let
the IDE create its own. An IDE-made environment is built from whatever Python the
IDE finds first (often the operating system's, which an upgrade can delete) and
does not read `uv.lock`.

**PyCharm:** *Settings → Project: prama → Python Interpreter → Add Interpreter →
Add Local Interpreter → Select existing → Python*, and choose
`<project>/.venv/bin/python` (`.venv\Scripts\python.exe` on Windows). Recent
PyCharm releases also offer a **uv** interpreter type, which finds the same `.venv`.

**IntelliJ IDEA:** *File → Project Structure → SDKs → + → Add Python SDK →
Virtualenv Environment → Existing environment*, choose `<project>/.venv/bin/python`.
Then, under *Modules*, select the `prama` module and set its SDK to that interpreter.

Check it took: the IDE's terminal (*View → Tool Windows → Terminal*) should print
`.../prama/.venv/bin/python` for `which python`, and `prama version` should answer.

## 3. Source roots

`uv sync` installs the four packages editable, so imports work without any IDE
setup. Marking the roots makes navigation and refactoring understand them as well:

| Folder | Mark as | Why |
|---|---|---|
| `src`, `kernel/src`, `sdk/src`, `agent/src` | **Sources Root** | the server, and the three packages it is built with ([the distributions](../architecture/packages.md)) |
| `tests`, `qa/regression-suite` | **Test Sources Root** | the two suites `pytest` collects |
| `.venv`, `data` | **Excluded** | the environment, and the SQLite database the server writes |

Right-click the folder in the Project view → *Mark Directory as*.

## 4. The run configurations

They appear in the run widget at the top of the window. Each runs in the project
root with the module's interpreter.

| Configuration | What it runs | When |
|---|---|---|
| **Prama - first run** | `run_prama_web.py --init-secret --prepare` | Once, on a fresh clone or after recreating the database |
| **Prama - server** | `run_prama_web.py` | Every day |
| **Prama - server (reload)** | `run_prama_web.py --reload` | While editing: restarts on every save under the four source roots |
| **Prama - prama serve** | `python -m prama serve` | The exact production entry point, for debugging the CLI path |
| **Prama - db init** | `python -m prama db init` | Applying the schema to the configured database |
| **Case study 01 - trading book** | `case-studies/01-trading-book-sqlite/run.py` | Exercising the running server through the SDK |

If one reports that its module is missing (the module is named `prama`, after the
project folder), open it with *Edit Configurations…* and select your interpreter.

### The first run

**Prama - first run** does the three things a fresh clone needs before the server
is any use:

1. It writes a generated `security.session_secret` into
   `config/application.local.yaml`. That file is git-ignored; the tracked
   `config/application.yaml` stays secretless on purpose.
2. It applies the schema to the database, `data/prama.db` by default.
3. It creates the estate `acme-bank`.

Then it serves. The Run window prints the addresses:

```
  Console  http://127.0.0.1:5900/estate
  API      http://127.0.0.1:5900/api/v1
  Docs     http://127.0.0.1:5900/api/v1/docs
```

Open the console and sign in as `admin` / `prama-dev-admin`. The banner asks you
to change that password; do it. [QUICKSTART §2](../../QUICKSTART.md#signing-in)
covers signing in, the estates, and making the estate the default.

From then on use **Prama - server**. Stop it with the red square.

### Live reload

**Prama - server (reload)** watches `src`, `kernel/src`, `sdk/src` and `agent/src`.
Save a file and the server restarts with your change, typically within two
seconds. Refresh the browser to see it.

Templates and static files are read at request time, so a change under
`src/prama/web/templates` or `static/` shows on the next refresh even without
reload.

Two things to know:

- A reloading server is a fresh process each time, so it reads its configuration
  from files and the environment: `config/application.yaml`, its `.local` overlay,
  and `PRAMA_*` variables. `prama serve --reload` refuses `--set` overrides rather
  than silently dropping them.
- Reload is for development. Do not use it on a server anybody else depends on.

### Debugging

Press the **Debug** button (the bug) on **Prama - server** or **Prama - prama
serve**, set a breakpoint in a route (for example
`src/prama/web/routes/estate_routes.py`), and load the page. Debug *without*
reload. The reloader runs the server in a child process, and the debugger only
follows it if *Settings → Build, Execution, Deployment → Python Debugger → Attach
to subprocess automatically while debugging* is on.

## 5. Tests from the IDE

`pytest` is configured in `pyproject.toml` (the two test roots, and
`--import-mode=importlib`), so the IDE needs only to use it:

1. *Settings → Tools → Python Integrated Tools → Testing → Default test runner:*
   **pytest**.
2. Right-click `tests` (or any test file, class or function) → *Run 'pytest in …'*.
   The gutter icons next to each test do the same for one test.
3. For a quick loop, edit the generated configuration and put `-m "not slow"` in
   *Additional Arguments*. That skips the tens-of-seconds performance guards.

The full suite takes about ten minutes. Some tests in `qa/regression-suite` run
the `prama` command itself as a subprocess, so they need `.venv/bin` on `PATH`.
If they fail with `No such file or directory: 'prama'`, either start the IDE from a
shell where the environment is activated, or add `PATH=<project>/.venv/bin:<your
PATH>` to the test configuration's environment variables.

`pytest -m casestudy` runs the case studies end to end against a server the test
starts for itself.

## 6. Driving the running server

With **Prama - server** running, everything else talks to it:

- **The case studies**: **Case study 01 - trading book** (copy it for the
  others) declares an estate, derives controls and runs them. The results appear
  in the console you have open ([the case studies](../../case-studies/README.md)).
- **The SDK**, from the IDE's Python Console: `import prama_sdk as prama;
  client = prama.connect(config="config/application.yaml", username="admin",
  password="…")` ([the SDK](../sdk/README.md)).
- **The CLI**, from the IDE's terminal: `prama control check suite.pql`,
  `prama control explain suite.pql`, and the rest ([the CLI reference](../operations/cli-reference.md)).

## 7. PostgreSQL instead of SQLite

SQLite needs nothing. To develop against PostgreSQL:

1. Start one in Docker:

   ```bash
   docker run -d --name prama-pg -e POSTGRES_PASSWORD=prama -e POSTGRES_USER=prama \
     -e POSTGRES_DB=prama -p 55432:5432 postgres:16-alpine
   ```

2. Set `database.dialect: postgres` and its connection in
   `config/application.local.yaml`, as [QUICKSTART §6](../../QUICKSTART.md#6-configuration)
   shows. Use port 55432 for the container above.
3. `uv pip install -e ".[postgres]"`.
4. Run **Prama - first run** again.

The run configurations do not change.

## 8. When it does not start

| What you see | Why, and what to do |
|---|---|
| `security.session_secret is empty` | Run **Prama - first run** once. It writes the secret to the git-ignored local file. |
| `schema drift against schema/sqlite.sql` at start | The schema files changed since your database was made, and Prama never migrates. Delete the database file (`data/prama.db` by default, which loses its data), then run **Prama - first run**. |
| `cannot listen on 127.0.0.1:5900` | Another server holds the port, often one already running in another Run tab. Stop it, or set `server.port` in the local file. |
| Every console page redirects to sign-in | No estate exists yet. Run **Prama - first run** (it creates `acme-bank`). |
| `ModuleNotFoundError: prama` | The configuration is using another interpreter. Check §2. |
| Imports resolve in the terminal but are red in the editor | The IDE indexed a different interpreter. Re-select `.venv/bin/python` (§2), then *File → Invalidate Caches*. |

Everything else is in [troubleshooting](../operations/troubleshooting.md).

---

<div align="center">
<img src="../assets/prama-mark.svg" width="30" alt=""/><br/>
<sub><b>PRAMA</b> — <i>Declare it. Prove it. Trust it.</i><br/>
Copyright © 2026 <b>Ashutosh Sinha</b> &lt;ajsinha@gmail.com&gt; · All rights reserved.<br/>
Proprietary and confidential. No licence is granted except by separate written agreement.<br/>
See <a href="../../LICENSE">LICENSE</a> and <a href="../../NOTICE">NOTICE</a>. Third-party names and marks are the property of their respective owners.</sub>
</div>
