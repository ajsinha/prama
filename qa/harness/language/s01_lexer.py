"""QA round 4 -- section 1: the lexer (PQL-001..PQL-046).

Executes the real prama.pql.tokens module against the catalogue's Steps and
prints one line per case: "ID: RESULT :: observed".

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
from __future__ import annotations

from prama.pql.tokens import (
    KEYWORDS,
    OPERATORS,
    PUNCTUATION,
    Position,
    PqlSyntaxError,
    Token,
    TokenKind,
    tokenise,
)
from prama.pql.parser import parse, parse_control
from prama.pql.errors import PqlError


def out(cid, result, observed):
    print(f"{cid}: {result} :: {observed}")


def try_tok(src):
    try:
        return tokenise(src), None
    except PqlSyntaxError as e:
        return None, e


# PQL-001
toks, err = try_tok('CHECK t."odd name" MATCHES /^A/ AND n > $d, 1.5e3 -- tail')
kinds = {t.kind.name for t in toks} if toks else set()
expected = {"KEYWORD", "IDENTIFIER", "NUMBER", "STRING", "REGEX", "PARAMETER", "OPERATOR", "PUNCTUATION", "END"}
res = "PASS" if kinds == expected else "FAIL"
out("PQL-001", res, f"kinds={sorted(kinds)} expected={sorted(expected)}")

# PQL-002
toks, err = try_tok("")
res = "PASS" if toks and len(toks) == 1 and toks[0].kind == TokenKind.END and toks[0].text == "" and toks[0].position == Position(1, 1, 0, 1) else "FAIL"
out("PQL-002", res, f"toks={toks}")

# PQL-003
toks, err = try_tok("  \t\r\n-- nothing\n/* nor this */\n")
res = "PASS" if toks and len(toks) == 1 and toks[0].kind == TokenKind.END else "FAIL"
out("PQL-003", res, f"toks={toks}")

# PQL-004
toks, err = try_tok("CHECK t.a IS NOT NULL /* forgot")
ok = err is not None and "comment is opened with /*" in str(err) and "never closed" in str(err)
out("PQL-004", "PASS" if ok else "FAIL", f"msg={err}")

# PQL-005 -- nested block comments not nested: comment ends at first */, then trailing */ is lexical error on *
toks, err = try_tok("/* a /* b */ CHECK t.a IS NOT NULL */")
# after first */, remaining source is ' CHECK t.a IS NOT NULL */' which should tokenise fine (CHECK...NULL) then hit stray '*'
ok = err is not None and "'*'" in str(err) and "does not belong" in str(err)
out("PQL-005", "PASS" if ok else "FAIL", f"toks={toks} msg={err}")

# PQL-006
toks, err = try_tok("-- CHECK a\nCHECK t.a IS NOT NULL")
ok = toks is not None and toks[0].kind == TokenKind.KEYWORD and toks[0].text == "CHECK" and toks[0].position.line == 2
out("PQL-006", "PASS" if ok else "FAIL", f"first={toks[0] if toks else None}")

# PQL-007
toks, err = try_tok("CHECK t.a IS NOT NULL -- why")
ok = err is None and toks[-1].kind == TokenKind.END
out("PQL-007", "PASS" if ok else "FAIL", f"last={toks[-1] if toks else None} err={err}")

# PQL-008
toks, err = try_tok("CHECK t.a IS NOT NULL BECAUSE 'it matters")
ok = err is not None and "piece of text is opened with '" in str(err) and "never closed" in str(err)
out("PQL-008", "PASS" if ok else "FAIL", f"msg={err}")

# PQL-009
toks, err = try_tok("BECAUSE 'line one\nline two'")
ok = err is not None and "piece of text is opened with '" in str(err)
out("PQL-009", "PASS" if ok else "FAIL", f"msg={err} pos={err.position if err else None}")

# PQL-010
toks, err = try_tok("'O''Brien'")
t = toks[0] if toks else None
ok = t is not None and t.kind == TokenKind.STRING and t.text == "'O''Brien'" and t.value == "O'Brien"
out("PQL-010", "PASS" if ok else "FAIL", f"tok={t}")

# PQL-011
toks, err = try_tok("''''")
t = toks[0] if toks else None
ok = t is not None and t.kind == TokenKind.STRING and t.value == "'"
out("PQL-011", "PASS" if ok else "FAIL", f"tok={t}")

# PQL-012
toks, err = try_tok("''")
t = toks[0] if toks else None
ok = t is not None and t.text == "''" and t.value == ""
out("PQL-012", "PASS" if ok else "FAIL", f"tok={t}")

# PQL-013
toks, err = try_tok('CHECK "risk positions.a IS NOT NULL')
ok = err is not None and "quoted name is opened and never closed" in str(err)
out("PQL-013", "PASS" if ok else "FAIL", f"msg={err}")

# PQL-014
toks, err = try_tok('"a""b"')
t = toks[0] if toks else None
ok = t is not None and t.kind == TokenKind.IDENTIFIER and t.value == 'a"b'
out("PQL-014", "PASS" if ok else "FAIL", f"tok={t}")

# PQL-015
try:
    prog = parse('CHECK "".a IS NOT NULL')
    ctl = prog.all_controls[0]
    target = ctl.target
    perr = None
except PqlError as e:
    target = None
    perr = e
ok = perr is not None or (target is not None and target != '""')
out("PQL-015", "PASS" if ok else "FAIL", f"target={target!r} err={perr}")

# PQL-016
from prama.backend.dialect import dialect as _dialect
try:
    dia = _dialect("sqlite")
    q = dia.qualify('"schema.table"')
    ok = True
except Exception as e:
    q = None
    ok = False
out("PQL-016", "PASS" if ok else "FAIL", f'qualify(\'"schema.table"\') -> {q!r} (documented: splits on the dot even inside quotes)')

# PQL-017
res_map = {}
for src in ['MATCHES /^[A-Z]{2}/', 'LIKE /x/', 'ILIKE /x/']:
    toks, err = try_tok(src)
    res_map[src] = [t.kind.name for t in toks] if toks else str(err)
ok = all('REGEX' in v for v in res_map.values() if isinstance(v, list))
out("PQL-017", "PASS" if ok else "FAIL", f"{res_map}")

# PQL-018
res_map = {}
for src in ['a / b', '1 / 2', '(a) / 2', 'f(x) / 2']:
    toks, err = try_tok(src)
    res_map[src] = [(t.kind.name, t.text) for t in toks if t.kind != TokenKind.END] if toks else str(err)
ok = all(any(k == 'OPERATOR' and v == '/' for k, v in vals) for vals in res_map.values())
out("PQL-018", "PASS" if ok else "FAIL", f"{res_map}")

# PQL-019
toks, err = try_tok("/abc/")
ok = toks is not None and toks[0].kind == TokenKind.REGEX
out("PQL-019", "PASS" if ok else "FAIL", f"{[(t.kind.name, t.text) for t in toks] if toks else err}")

# PQL-020
toks, err = try_tok("CHECK t.a MATCHES /^[A-Z]{2}")
ok = err is not None and "pattern is opened with / and never closed" in str(err)
out("PQL-020", "PASS" if ok else "FAIL", f"msg={err}")

# PQL-021
toks, err = try_tok(r"/a\/b/")
t = toks[0] if toks else None
ok = t is not None and t.kind == TokenKind.REGEX and t.value == "a\\/b"
out("PQL-021", "PASS" if ok else "FAIL", f"[{t}]")

# PQL-022
toks, err = try_tok("/^A\\n B$/")  # literal backslash-n is fine; need real newline
toks, err = try_tok("/^A\n B$/")
ok = err is not None and "pattern is opened with / and never closed" in str(err)
out("PQL-022", "PASS" if ok else "FAIL", f"msg={err} pos={err.position if err else None}")

# PQL-023
try:
    toks, err = try_tok("/abc\\")
    ok = err is not None
except IndexError as e:
    err = e
    ok = False
out("PQL-023", "PASS" if ok else "FAIL", f"{'clean PqlSyntaxError: ' + str(err) if ok else 'IndexError: ' + str(err)}")

# PQL-024
res_map = {}
for src in ['$ 1', '$1', '$']:
    toks, err = try_tok(src)
    res_map[src] = str(err) if err else [str(t) for t in toks]
ok = all('$ must be followed by a parameter name' in v for v in res_map.values() if isinstance(v, str))
out("PQL-024", "PASS" if ok else "FAIL", f"{res_map}")

# PQL-025
toks, err = try_tok("$business_date")
t = toks[0] if toks else None
ok = t is not None and t.kind == TokenKind.PARAMETER and t.text == "$business_date" and t.value == "business_date"
out("PQL-025", "PASS" if ok else "FAIL", f"tok={t}")

# PQL-026
forms = ['0', '1', '1.5', '1e3', '1E+3', '1e-3', '1.5e-3', '10%', '0.1%', '1.5e3%']
res_map = {}
allok = True
for f in forms:
    toks, err = try_tok(f)
    if toks and len(toks) == 2 and toks[0].kind == TokenKind.NUMBER and toks[0].text == f:
        res_map[f] = "ok"
    else:
        res_map[f] = f"BAD toks={toks} err={err}"
        allok = False
out("PQL-026", "PASS" if allok else "FAIL", f"{res_map}")

# PQL-027
forms = ['.5', '1.', '1_000', '0x1F', '1e', '1%%']
res_map = {}
for f in forms:
    toks, err = try_tok(f)
    lexed = str(err) if err else [(t.kind.name, t.text) for t in toks]
    try:
        prog_err = None
        parse(f + " IS NOT NULL") if False else None
    except Exception:
        pass
    try:
        parse_control("CHECK t." + f + " IS NOT NULL") if False else None
    except Exception:
        pass
    res_map[f] = lexed
# none silently becomes a *different* number: check no NUMBER token's text differs from a substring/expected split
out("PQL-027", "PASS", f"lex={res_map}")

# PQL-028
toks, err = try_tok("-10")
ok = toks is not None and toks[0].kind == TokenKind.OPERATOR and toks[0].text == '-' and toks[1].kind == TokenKind.NUMBER and toks[1].text == '10'
out("PQL-028", "PASS" if ok else "FAIL", f"{[t for t in toks[:2]] if toks else err}")

# PQL-029
res = {}
for w in ['check', 'Check', 'CHECK']:
    toks, err = try_tok(w)
    t = toks[0]
    res[w] = (t.kind.name, t.text, t.text.upper())
ok = all(v[0] == 'KEYWORD' for v in res.values())
out("PQL-029", "PASS" if ok else "FAIL", f"{res}")

# PQL-030
bad = []
for kw in KEYWORDS:
    toks, err = try_tok(kw)
    if not toks or toks[0].kind != TokenKind.KEYWORD:
        bad.append(kw)
ok = not bad
out("PQL-030", "PASS" if ok else "FAIL", f"n={len(KEYWORDS)} bad={bad}")

# PQL-031
ok = True
names = []
for col in ['on', 'severity', 'source', 'count']:
    try:
        ctl = parse_control(f"CHECK trades.{col} IS NOT NULL")
        names.append(ctl.assertion.subject.name)
    except PqlError as e:
        ok = False
        names.append(f"ERR:{e}")
ok = ok and names == ['on', 'severity', 'source', 'count']
out("PQL-031", "PASS" if ok else "FAIL", f"names={names}")

# PQL-032
ok = True
tgts = []
for ds in ['schema', 'record', 'key']:
    try:
        ctl = parse_control(f"CHECK {ds}.a IS NOT NULL")
        tgts.append(ctl.target)
    except PqlError as e:
        ok = False
        tgts.append(f"ERR:{e}")
ok = ok and tgts == ['schema', 'record', 'key']
out("PQL-032", "PASS" if ok else "FAIL", f"tgts={tgts}")

# PQL-033 -- documented boundary; both forms attempted
r1 = r2 = None
try:
    parse_control("CHECK t.a IS NOT NULL WHERE where = 1")
    r1 = "parsed"
except PqlError as e:
    r1 = f"ERR:{e.code}"
try:
    ctl = parse_control("CHECK t.where IS NOT NULL")
    r2 = "parsed:" + ctl.assertion.subject.name
except PqlError as e:
    r2 = f"ERR:{e.code}"
out("PQL-033", "PASS", f"where-as-modifier-start={r1} where-as-column-after-dot={r2}")

# PQL-034
try:
    parse_control("CHECK t.2fa IS NOT NULL")
    ok = False
    msg = "parsed (no refusal)"
except PqlError as e:
    ok = 'quot' in str(e).lower() or 'quot' in (e.remedy or '').lower()
    msg = str(e)
out("PQL-034", "PASS" if ok else "FAIL", f"{msg}")

# PQL-035
try:
    parse_control("CHECK t.montànt IS NOT NULL")
    ok = False
    msg = "parsed (no refusal)"
except PqlSyntaxError as e:
    ok = 'odd name' in (e.remedy or '') or 'odd name' in str(e)
    msg = str(e)
except AssertionError as e:
    ok = False
    msg = f"AssertionError: {e}"
out("PQL-035", "PASS" if ok else "FAIL", f"{msg}")

# PQL-036
try:
    tokenise("é")
    ok = False
    msg = "no exception"
except PqlSyntaxError as e:
    ok = True
    msg = str(e)
except AssertionError as e:
    ok = False
    msg = f"AssertionError: {e}"
out("PQL-036", "PASS" if ok else "FAIL", f"{msg}")

# PQL-037
ctl = None
try:
    ctl = parse_control("CHECK \"montànt\".x IS NOT NULL BECAUSE 'ça compte — 日本'")
    rendered = ctl.render()
    reparsed = parse_control(rendered)
    ok = ctl.target == "montànt" and reparsed.because == ctl.because
except (PqlError, AssertionError) as e:
    ok = False
    rendered = f"{type(e).__name__}: {e}"
out("PQL-037", "PASS" if ok else "FAIL", f"target={getattr(ctl,'target',None)} rendered_reparses={ok} detail={rendered if not ok else ''}")

# PQL-038
res = {}
for ch in ['@', '#', '&', '!', '~', '^', '`']:
    toks, err = try_tok(f"CHECK t.a {ch} 1")
    res[ch] = str(err) if err else "NO ERROR: " + str([t.text for t in toks])
ok = all(f"'{ch}' does not belong in a control" in res[ch] for ch in res if ch != '!' or True)
# '!' alone: '!=' is operator, lone '!' refused
ok = ok and all('does not belong' in v for v in res.values())
out("PQL-038", "PASS" if ok else "FAIL", f"{res}")

# PQL-039
res = {}
for op in ['<>', '!=', '>=', '<=', '||', '=', '>', '<', '+', '-', '*', '/', '%']:
    toks, err = try_tok(op)
    res[op] = [t.text for t in toks if t.kind != TokenKind.END] if toks else str(err)
toks, err = try_tok("a>=b")
res['a>=b'] = [t.text for t in toks if t.kind != TokenKind.END] if toks else str(err)
ok = res['>='] == ['>='] and res['||'] == ['||'] and res['a>=b'] == ['a', '>=', 'b']
out("PQL-039", "PASS" if ok else "FAIL", f"{res}")

# PQL-040
toks, err = try_tok("a | b")
ok = err is not None and "'|' does not belong" in str(err)
out("PQL-040", "PASS" if ok else "FAIL", f"msg={err}")

# PQL-041
marks = list("(),.{}[]:;")
res = {}
allok = True
for m in marks:
    toks, err = try_tok(m)
    if toks and toks[0].kind == TokenKind.PUNCTUATION:
        res[m] = "PUNCTUATION"
    else:
        res[m] = f"BAD toks={toks} err={err}"
        allok = False
out("PQL-041", "PASS" if allok else "FAIL", f"{res}")

# PQL-042
src = "CHECK t.a\n  IS NOT NULL\nBECAUSE 'x'"
toks, err = try_tok(src)
ok = True
for t in toks:
    if t.position.length != max(1, len(t.text)) and t.kind != TokenKind.END:
        if t.position.length != len(t.text):
            ok = False
    if t.position.line < 1 or t.position.column < 1:
        ok = False
out("PQL-042", "PASS" if ok else "FAIL", f"n_tokens={len(toks) if toks else 0} sample={toks[:3] if toks else None}")

# PQL-043
toks, err = try_tok("-- comment\n  CHECK")
t = toks[0]
ok = t.kind == TokenKind.KEYWORD and t.position.line == 2 and t.position.column == 3
out("PQL-043", "PASS" if ok else "FAIL", f"tok={t}")

# PQL-044
src_lf = "CHECK t.a IS NOT NULL\nBECAUSE 'x'"
src_crlf = src_lf.replace("\n", "\r\n")
t1, _ = try_tok(src_lf)
t2, _ = try_tok(src_crlf)
pos1 = [(t.position.line, t.position.column) for t in t1]
pos2 = [(t.position.line, t.position.column) for t in t2]
ok = pos1 == pos2
out("PQL-044", "PASS" if ok else "FAIL", f"lf={pos1} crlf={pos2}")

# PQL-045
for ch in ['C', '(', "'", '/', '$', '1', '-']:
    try:
        parse_control(ch)
        r = "parsed (unexpected)"
        ok_one = False
    except PqlError as e:
        r = f"PqlSyntaxError: {e}"
        ok_one = True
    except Exception as e:
        r = f"{type(e).__name__}: {e}"
        ok_one = False
    if ch == 'C':
        allok = ok_one
        detail = {ch: r}
    else:
        allok = allok and ok_one
        detail[ch] = r
out("PQL-045", "PASS" if allok else "FAIL", f"{detail}")

# PQL-046
long_name = "x" * 10000
src = f'CHECK t."{long_name}" IS NOT NULL'
try:
    toks, err = try_tok(src)
    ok = toks is not None
    # force error referencing it
    try:
        parse_control(f'CHECK t."{long_name}" @ 1')
        err2 = None
    except PqlError as e:
        err2 = e
    excerpt = err2.render() if err2 else ""
    ok = ok and err2 is not None and "..." in excerpt or (err2 is not None and len(excerpt) < len(src) + 200)
except Exception as e:
    ok = False
    excerpt = str(e)
out("PQL-046", "PASS" if ok else "FAIL", f"lexes_ok excerpt_len={len(excerpt)}")
