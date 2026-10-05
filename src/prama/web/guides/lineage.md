<!-- Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE. -->

# Lineage

Column-level lineage: which column feeds which, how (copied, cast, computed, aggregated, used as a
filter), and how that is known. The page is **Estate → Lineage** (`/lineage`). Lineage arrives from
SQL, application code ([Application code](/help/code)), dbt, OpenLineage events, warehouse query
history, and other catalogues ([glossary and imports](/help/glossary)).

## To bring lineage in

```bash
prama lineage scan etl/ --source warehouse                 # every .sql file under etl/
prama lineage scan procs/ --source finrep --dialect tsql
prama lineage ingest-dbt target/manifest.json --source jaffle_shop   # after `dbt compile`
prama lineage history snowflake rows.json                  # --query prints the export to run
```

Orchestrators that emit **OpenLineage** (Airflow, Spark, Marquez) can post events to
`POST /api/v1/lineage/openlineage` with a key holding `relationship:write`. Re-scanning or replaying
refreshes edges rather than duplicating them.

## To check an edge

Each edge says how it is known:

| Status | Meaning |
|---|---|
| **parsed** | Read by the SQL parser from code it fully understood. |
| **inferred** | From the fallback pattern reader, or proposed by a model. Needs a person. |
| **confirmed** | A person agreed. |
| **rejected** | A person disagreed. It stays rejected however often a scan finds it again. |

Confirm or reject inferred edges on the page. An edge a source stops producing is closed, not
deleted: "fed by that column until Tuesday" is lineage too.

## To see what a defect reaches

Name a column on the page, or:

```bash
prama lineage impact raw.trades.notional
```

Everything downstream is listed, ranked by how much of the defect survives each hop (an aggregate
carries least), with the controls and attestations on it.

## To ask whether a change breaks anything

```bash
prama lineage impact --diff old/load_stg.sql new/load_stg.sql
```

It exits 3 when a control or attestation is at risk, so CI can stop the change. For a whole pull
request, `prama code review --base origin/main` does the same across every file.

## To see what was not read

```bash
prama lineage gaps
```

Every statement a scan could not fully read is listed with the reason. A partial graph with visible
gaps is worth more than a complete-looking one whose gaps are hidden.

## Go deeper

- [Lineage and code](../../../../docs/architecture/lineage-and-code.md): the lineage store, how an edge is known, and impact.
- [Writing a code reader](../../../../docs/developer/code-readers.md): adding a source of lineage.
