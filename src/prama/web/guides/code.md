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

SQL files, in about twenty dialects. Every other kind of file (Python, PySpark, Airflow, SSIS,
Informatica, COBOL, JCL, shell) is **inventoried and reported as not yet read**, so a run always
says how much of the application it covered.
