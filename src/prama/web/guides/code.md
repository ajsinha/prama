<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Application code

Send Prama an application's code, as a ZIP or a git location, and it reads the ETL lineage out of it
without ever running it. The page is **Controls → Code intake** (`/code`); what it finds appears on
**Lineage**.

## To send code

1. On **Code intake**, name the source, and give the SQL dialect if it is not the default.
2. Either choose a ZIP and press **Receive and read**, or give a git URL (`https` or `ssh`), a ref
   and a credential **reference** such as `env://GIT_TOKEN` (never the token itself), and press
   **Fetch and read**.
3. Read the run that appears: files read, edges found, gaps, and what was **not read**.

From the command line:

```bash
prama code add-zip finrep-etl.zip --source finrep --dialect tsql
prama code add-git https://git.bank.example/risk/etl.git --ref main --source etl \
    --credential-ref env://GIT_TOKEN
prama code runs
```

## What it reads

| Kind of file | How |
|---|---|
| SQL, including stored procedures | about twenty dialects |
| PySpark, pandas, Airflow DAGs | from the syntax tree; a join, merge, templated SQL or procedure call is a gap, not a guess |
| Power BI (`.pbit`, `model.bim`) | through Power Query and DAX, so impact reaches the dashboard |
| SSIS and Informatica exports | stored as *inferred* until a person confirms them |

Everything else (Scala, Java, shell, and mainframe code, which Prama does not analyse) is
**inventoried and reported as not read**, so a run always says how much it covered. dbt Jinja is
not rendered: compile the project and use `prama lineage ingest-dbt`.

## To re-read after a commit

Fetch the git source again (or let a steward goal do it). Only changed files are re-read; a file
byte-identical to the last run, read by the same reader version and dialect, carries its lineage
forward, and the run says how many were reused.

## To let a model help

Give the estate a model profile for the purpose `lineage`
(`prama llm profile set lineage --route local:qwen2.5-coder:32b`). Files the readers could not read,
or read with gaps, are then offered to it. Every edge it proposes must quote the code it came from,
is capped at 0.85 confidence and stored as **inferred**, and waits for a person on **Lineage**.

## What it refuses

- **Running anything.** Nothing received is executed, imported or rendered.
- **A dangerous archive**: entries that climb out (`..`), absolute paths, links, bombs, and too many
  or too large files, all checked before anything is written.
- **Fetching from anywhere.** Only `https` and `ssh`; private, loopback and metadata addresses are
  refused, and `codeintake.git.allowed_hosts` narrows it to named hosts.
- **Keeping your code.** Files are read in a resource-limited process and deleted after; only hashes
  and the short expressions edges cite are kept.

## Go deeper

- [Lineage and code](../../../../docs/architecture/lineage-and-code.md#code-intake): the sandbox, the readers, and reviewing a pull request (`prama code review`).
- [Writing a code reader](../../../../docs/developer/code-readers.md): teaching Prama another language or tool.
