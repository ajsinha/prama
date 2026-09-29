<img src="../assets/prama-lockup.svg" alt="Prama — Declare it. Prove it. Trust it." width="330"/>

*Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.*

---

# Knowledge and code: lineage, code, glossary, metadata, comments, delegates, packs, connectors

What an estate knows about itself — where a column comes from, what a term means,
what a field implies, who is waiting on whom — and the code and checks that feed it.
Every operation below is one HTTP endpoint under `/api/v1` and one SDK method; the
console and the CLI call the same services, so the three give the same answer.

```python
import prama.sdk as prama

client = prama.connect()          # reads config/application.yaml; or connect(base_url=..., api_key=...)
```

The examples use the synchronous client. Every method works unchanged on
`AsyncClient`; await it.

| Namespace | What it does | Scope it needs |
|---|---|---|
| `client.lineage` | Scan SQL, import exports and query history, decide edges, impact, gaps | `relationship:read`; `relationship:write` to add, decide or assess a change |
| `client.code` | Receive a ZIP or a git ref and read its lineage; review a change | `relationship:read`; `relationship:write` to receive or review |
| `client.glossary` | Terms, imports from Alation or Collibra, bindings | `declaration:read`; `declaration:write` to import or bind |
| `client.metadata` | Templates, values, business context, implied rules, search | `declaration:read`; `declaration:write`; `control:propose` for a hand-written rule |
| `client.comments` | Comments, threads, resolving, the queue | `declaration:read`; `comment:write` to post or resolve |
| `client.delegates` | Upload a Python check, vet it, decide it with four eyes, try it | `control:read`; `control:propose` to upload or try; `control:approve` to decide |
| `client.packs` | The banking pack: inventory, claims, calendars, message parsing, concepts; SOC 2 | `declaration:read`; `declaration:write` to parse a message |
| `client.connectors` | Installed connectors and their forms; test, browse, profile a connection | `declaration:read`; `declaration:write` to test or profile |

A refusal raises Prama's own error class — `ForbiddenError` for a missing scope,
`ValidationError` for input that cannot be used, `NotFoundError` — with the
server's `remedy`.

## Lineage

**Scan SQL into the store.** Files by path, or SQL as text. sqlglot reads what it can;
a regex fallback reads the rest, and those edges are `inferred` until a person decides
them. Nothing is executed.

```python
run = client.lineage.scan("warehouse", ["etl/01_stage.sql", "etl/02_mart.sql"], dialect="snowflake")
print(run["edges"], run["gaps"], run["understood"])

client.lineage.impact("raw.trades.notional_amt")
# {'reached': [{'column': 'stg.trades.notional', 'impact': 1.0, 'depth': 1}, ...],
#  'upstream': [], 'trust': 1.0, 'trust_explained': '...'}
```

**Decide what waits on a person.** `proposals()` lists inferred edges and the controls
lineage implies (a control resting on an inferred edge is held until the edge is
confirmed). A rejected edge leaves the graph, and impact is recomputed without it.

```python
waiting = client.lineage.proposals()
for edge in waiting["edges"]:
    client.lineage.confirm(edge["id"], note="checked against the job")
```

**What a change puts at risk.** Two versions of a SQL file; `at_risk` is true when a
control or attestation sits downstream — what `prama lineage impact --diff` exits 3 on.

```python
client.lineage.change(before_sql, after_sql)["at_risk"]
```

**Other ways in.** A dbt manifest (`dbt(manifest)`), rows of warehouse query history
(`history("snowflake", rows)`; `history_query("snowflake")` gives the export query),
a Manta or Alation export (`import_export("manta", export)`), and OpenLineage events
(`openlineage(event)`). An import is kept beside Prama's own parse and says what it
dropped; `conflicts()` lists the columns where the two disagree.

```python
result = client.lineage.import_export("manta", "exports/manta.json")
for item in result["dropped"]:
    print(item["source"], item["reason"])
```

## Code

Code is received as a ZIP or fetched from a git location and read by the sandboxed
reader: parsed, never executed. A git location naming a loopback, private or
link-local address, or a host outside `codeintake.git.allowed_hosts`, is refused before
anything is fetched or stored.

```python
run = client.code.add_zip("etl", "build/etl.zip")
run["coverage"]      # {'units': 12, 'read': 12, 'edges': 40, 'gaps': 1, ...}
client.code.add_git("etl", "https://git.example.com/data/etl.git", ref="main",
                    credential_ref="env://GIT_TOKEN")
```

**Review a change** — the same four questions `prama code review` answers, as a
structured result: what lineage changed, what it reaches, which controls lose their
basis, what the change implies. `fails` is true when a live control loses its basis;
`markdown` is the pull-request comment.

```python
review = client.code.review("before.zip", "after.zip")
if review["fails"]:
    print(review["broken"])          # {identity: control name}
review = client.code.review_git("https://git.example.com/data/etl.git", "main", "feature/fx")
```

## Glossary

```python
result = client.glossary.import_export("alation", "exports/alation-terms.json")
print(result["terms_created"], result["bound_to_concepts"], result["dropped"])

client.glossary.bind("Account", "attribute", "trades.account_id")
client.glossary.bind("Account", "concept", "Account")      # a concept by name
client.glossary.search("settlement")
```

## Metadata

Setting a field whose template carries a rule does not create a control; it creates a
proposal, which becomes a control only when a person accepts it on the proposals queue.

```python
client.metadata.install_starter("data-quality-attribute")
result = client.metadata.set("trades.account_id", mandatory="yes")
result["proposals"][0]["pql"]    # 'CHECK trades.account_id IS NOT NULL DIMENSION completeness'

client.metadata.set_context("trades", "Every booked trade, by trade date.")
client.metadata.author_rule("trades", "CHECK trades.trade_id IS NOT NULL")   # proposed
client.metadata.describe("trades")        # context, metadata, attributes, rules, implied rules
client.metadata.search("settlement currency")
client.metadata.ask("trade amounts in USD")   # ranked by a discover model when one is configured
client.metadata.correlation()
```

`save_template(document)` or `save_template(yaml=...)` saves your own template;
`templates()` lists them with each field's rules.

## Comments and the queue

```python
thread = client.comments.post("@bo is ccy upper case?", object_kind="dataset", object_ref="trades")
client.comments.reply(thread["id"], "Yes, ISO 4217.")
client.comments.threads("dataset", "trades")
client.comments.resolve(thread["id"])

client.comments.queue()                              # yours
client.comments.queue(section="approvals")           # one list
client.comments.queue(person="bo", approver=True)    # somebody else's: needs admin
```

## Delegates

A delegate goes from a file to a control that runs it in four steps: uploaded, vetted in
the sandbox (the server never imports uploaded code), proposed with what vetting found,
and approved by somebody holding `control:approve` who is **not** the uploader.

```python
upload = client.delegates.upload("checks/over_limit.py")
upload["findings"]                          # every conformance check and its outcome
client.delegates.approve(upload["id"])      # ForbiddenError: the uploader cannot approve
other.delegates.approve(upload["id"])       # a second person can

tried = client.delegates.test("acme.over_limit@2", rows, limit=100)
tried["metrics"], tried["verdict"]          # measured in the sandbox, judged by the engine
```

`vet(file)` runs the conformance kit and stores nothing; `list()` shows the server's
configured delegates, those it refused and why, and every upload with its state.

## Domain packs

```python
client.packs.claims()                        # what the banking pack does NOT discharge
client.packs.calendar("TARGET2", year=2030)["closures"]
parsed = client.packs.parse(open("order.fix").read())
parsed["format"], parsed["defects"]          # e.g. ['tag 10: states 162 and the bytes give 173']
client.packs.concept("Exposure")["boundary"]
client.packs.recognise(["counterparty_id", "as_of_date", "exposure_amount"])
client.packs.soc2()                          # Prama's own readiness, gaps first
```

`parse` reads FIX, ISO 8583, FpML, SWIFT MT and ISO 20022 (pacs.008, camt.053), infers
the format when it is not given, and declines rather than guesses. No defects means no
structural defect, not "valid".

## Connectors

The configuration form of each connector is derived from its code. A connection is
configured with `client.connections.create(...)` and used here.

```python
sqlite = next(c for c in client.connectors.list() if c["key"] == "sqlite")
[f["name"] for g in sqlite["form"]["groups"] for f in g["fields"] if f["required"]]
# ['database_path']

conn = client.connections.create("desk", "sqlite", config={"database_path": "/data/desk.db"})
client.connectors.test(conn["id"])           # usable, and needs_access_request if it is permissions
client.connectors.browse(conn["id"])         # objects, largest first
client.connectors.profile(conn["id"], "main.trades")
client.connectors.cost(conn["id"], "main.trades")   # without reading it
```

## What is not here

`prama delegate check` (the conformance kit over a local directory, for CI) and
`prama delegate pull` (copying approved uploads into an agent's directory) work on the
caller's own files; `vet` and `uploads()`/`source()` are their API counterparts.
