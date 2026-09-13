import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(__file__))
import ui_common as u
from logger import record
import cli_common as c


async def main():
    DB = c.WORKDIR / "ui039.db"
    env = u.UiEnv(str(DB))
    await env.start()
    await env.create_principal("alice39", "alicepassword1", ["admin"])
    http, _ = await env.signed_in_client("alice39", "alicepassword1")

    # UI-039: url_for resolves every NAVIGATION endpoint
    from prama.web.rendering import NAVIGATION
    bad39 = {}
    for item in NAVIGATION:
        r = await http.get(item.prefix)
        if r.status_code not in (200, 303, 403):
            bad39[item.label] = r.status_code
    record("UI-039", "PASS" if not bad39 else "FAIL", f"n_nav_items={len(NAVIGATION)} bad={bad39}")

    # UI-042: url_for('static', ...) resolves and files exist -- spot check the vendor assets
    r_home = await http.get("/estate")
    html = r_home.text
    import re
    static_paths = set(re.findall(r'(?:href|src)="(/static/[^"]+)"', html))
    bad42 = {}
    for p in list(static_paths)[:20]:
        rp = await http.get(p)
        if rp.status_code != 200:
            bad42[p] = rp.status_code
    record("UI-042", "PASS" if not bad42 else "FAIL", f"n_checked={len(list(static_paths)[:20])} of {len(static_paths)} found bad={bad42}")

    # UI-043: no template references an external origin
    import subprocess
    grep = subprocess.run(
        ["grep", "-rlEn", r'(src|href)\s*=\s*"https?://|@import\s+["\x27]https?://|url\(https?://',
         str(c.REPO_ROOT / "src/prama/web/templates"), str(c.REPO_ROOT / "src/prama/web/static")],
        capture_output=True, text=True,
    )
    hits = grep.stdout.strip().splitlines()
    record("UI-043", "PASS" if not hits else "FAIL", f"external_refs_found_in={hits[:10]}")

    # UI-044: static mount does not serve outside its directory
    res44 = {}
    for path in ["/static/../../../../etc/passwd", "/static/..%2f..%2f..%2f..%2fetc%2fpasswd", "/static/..\\..\\..\\..\\etc\\passwd"]:
        r = await http.get(path)
        res44[path] = r.status_code
    bad44 = {k: v for k, v in res44.items() if v == 200}
    record("UI-044", "PASS" if not bad44 else "FAIL", f"{res44}")

    # UI-045: security headers present on a page, a redirect, and an error
    r_page = await http.get("/estate")
    r_redirect = await http.get("/")  # redirects to /estate
    r_error = await http.get("/datasets-does-not-exist-anywhere")
    res45 = {}
    for label, resp in [("page", r_page), ("redirect", r_redirect), ("error", r_error)]:
        h = {k.lower(): v for k, v in resp.headers.items()}
        present = {
            "csp": "content-security-policy" in h,
            "xcto": "x-content-type-options" in h,
            "referrer": "referrer-policy" in h,
            "frame": "x-frame-options" in h or "frame-ancestors" in h.get("content-security-policy", ""),
        }
        res45[label] = present
    bad45 = {k: v for k, v in res45.items() if not all(v.values())}
    record("UI-045", "PASS" if not bad45 else "FAIL", f"{res45}")

    # UI-046: a 403/404 in the console renders as HTML, not raw JSON
    auditor_http, _ = await env.signed_in_client("alice39", "alicepassword1")  # reuse; will refine below
    r46_404 = await http.get("/datasets-does-not-exist-page-xyz")
    r46_403 = None
    await env.create_principal("auditor46", "auditorpassword1", ["auditor"])
    http46, _ = await env.signed_in_client("auditor46", "auditorpassword1")
    r46_403 = await http46.post("/controls/save", data={"pql": "x"})
    ct_404 = r46_404.headers.get("content-type", "")
    ct_403 = r46_403.headers.get("content-type", "")
    ok46 = "text/html" in ct_404 and "text/html" in ct_403
    record("UI-046", "PASS" if ok46 else "FAIL", f"404_status={r46_404.status_code} 404_ct={ct_404} 403_status={r46_403.status_code} 403_ct={ct_403}")
    await http46.aclose()

    # UI-047: chosen_theme validates cookie against closed set
    http47 = env.client()
    http47.cookies.set("prama_theme", 'dark" onload="alert(1)')
    r47a = await http47.get("/sign-in")
    bad_theme_reflected = 'onload="alert(1)"' in r47a.text or "dark\" onload" in r47a.text
    http47b = env.client()
    http47b.cookies.set("prama_theme", "x" * 4000)
    r47b = await http47b.get("/sign-in")
    ok47 = r47a.status_code == 200 and not bad_theme_reflected and r47b.status_code == 200
    record("UI-047", "PASS" if ok47 else "FAIL", f"injection_reflected={bad_theme_reflected} large_cookie_status={r47b.status_code}")
    await http47.aclose()
    await http47b.aclose()

    # UI-048: ?theme= previews without changing the preference
    http48 = env.client()
    http48.cookies.set("prama_theme", "dark")
    r48a = await http48.get("/sign-in", params={"theme": "light"})
    match_a = re.search(r'data-theme="([^"]+)"', r48a.text)
    r48b = await http48.get("/sign-in")
    match_b = re.search(r'data-theme="([^"]+)"', r48b.text)
    ok48 = match_a and match_b and match_a.group(1) == "light" and match_b.group(1) == "dark"
    record("UI-048", "PASS" if ok48 else "FAIL", f"with_query={match_a.group(1) if match_a else None} without_query={match_b.group(1) if match_b else None}")
    await http48.aclose()

    # UI-049: prama_density validated the same way
    http49 = env.client()
    http49.cookies.set("prama_density", 'compact" onload="alert(1)')
    r49 = await http49.get("/sign-in")
    ok49 = r49.status_code == 200 and 'onload="alert(1)"' not in r49.text
    record("UI-049", "PASS" if ok49 else "FAIL", f"status={r49.status_code} injection_reflected={'onload=' in r49.text}")
    await http49.aclose()

    await env.stop()
    print("done ui batch 3a")


asyncio.run(main())
