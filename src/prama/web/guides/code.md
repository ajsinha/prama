<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Application code

Send Prama an application's code and it reads the ETL lineage out of it.

```bash
prama code add-zip finrep-etl.zip --source finrep --dialect tsql
prama code add-git https://git.bank.example/risk/etl.git --ref main --source etl \
    --credential-ref env://GIT_TOKEN
prama code runs
```

The **Code** page (linked from Lineage) does the same with an upload form.

## What Prama will not do

- **Run anything.** Nothing received is executed, imported or rendered. dbt Jinja is not rendered
  either; compile the project and use `prama lineage ingest-dbt`.
- **Accept a dangerous archive.** Checked before anything is written:
  - entries that climb out (`..`), absolute paths, and links, which are recorded but never created;
  - archives that expand far beyond their size (bombs);
  - too many or too large files.
- **Fetch from anywhere.** Only `https` and `ssh` are accepted. A host that resolves to a private,
  loopback or metadata address is refused. `codeintake.git.allowed_hosts` narrows it to named
  hosts. Clones run without hooks or submodules.
- **Keep your code.** Files are read in a separate, resource-limited process and deleted after.
  Only hashes and the short expressions that lineage edges cite are kept.

## What it reads today

- **SQL files**, in about twenty dialects, including stored procedures.
- **PySpark and pandas jobs, and Airflow DAGs.** These are read from their syntax tree and never
  run. A join, a merge, templated SQL or a procedure call is reported as a gap, not guessed at.
- **SSIS and Informatica exports.** Their edges are stored as *inferred* until a person confirms
  them.

Every other kind of file (Scala, Java, shell, and mainframe code, which Prama does not analyse) is
**inventoried and reported as not read**, so a run always says how much of the application it
covered. If a model profile for `lineage` exists, the model may propose edges for Scala, Java and
shell, and a person confirms them.

## A new commit

Re-reading a git source reads only the files that changed. If a file is byte-identical to the
last run, and was read by the same reader version and SQL dialect, Prama carries its lineage and
gaps forward unchanged. The run's coverage says how many files were reused. The model pass is
offered only the files that were re-read.

## When a model helps

If the estate has a model profile for the purpose **`lineage`**, files the readers could not
read, or read with gaps, are offered to that model:

```bash
prama llm profile set lineage --route local:qwen2.5-coder:32b
```

Nothing it says is taken on trust. Each edge must quote the exact code it came from, at the lines
it cites, and both column names must appear in the quote. Prama computes the edge's confidence
(never above 0.85) and stores it as **inferred**, so it waits for a person on the Lineage page, as
does any control proposed from it. The code is sent as data, not instructions, so a planted comment
cannot direct the model. Calls go through the gateway, with its budget, residency rules, redaction
and call ledger. A run reports how many edges the model offered and how many survived the checks.

