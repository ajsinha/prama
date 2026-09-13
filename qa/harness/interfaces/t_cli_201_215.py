import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "bundle2"
WORK.mkdir(exist_ok=True, parents=True)


def new_cfg(name, secret="test-secret-value-1234"):
    d = c.WORKDIR / name
    d.mkdir(exist_ok=True, parents=True)
    cfgf = d / "application.yaml"
    cfgf.write_text(
        "database:\n  dialect: sqlite\n"
        f"  sqlite:\n    path: {d/'x.db'}\n"
        f"  schema_dir: {c.REPO_ROOT/'schema'}\n"
        f"security:\n  session_secret: {secret}\n"
    )
    return cfgf, d


def stage(d, n=3):
    root = d / "offline"
    root.mkdir(exist_ok=True, parents=True)
    for i in range(n):
        (root / f"file{i}.whl").write_text(f"content {i}" * 10)
    return root


from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.hazmat.primitives import serialization

ed_priv = ed25519.Ed25519PrivateKey.generate()
ed_pub = ed_priv.public_key()
ed_priv_path = WORK / "priv.pem"
ed_priv_path.write_bytes(ed_priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
ed_pub_path = WORK / "pub.pem"
ed_pub_path.write_bytes(ed_pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
rsa_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
rsa_pub_path = WORK / "rsa_pub.pem"
rsa_pub_path.write_bytes(rsa_priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def seal(cfg, root, sign_with=None):
    argv = ["--config", str(cfg), "bundle", "seal", str(root)]
    if sign_with:
        argv += ["--sign-with", str(sign_with)]
    return c.run_sub(argv)


# CLI-201: untouched bundle verifies exit 0
cfg201, d201 = new_cfg("cli201")
root201 = stage(d201)
seal(cfg201, root201)
code, out, err = c.run_sub(["--config", str(cfg201), "bundle", "verify", str(root201)])
ok = code == 0
record("CLI-201", "PASS" if ok else "FAIL", f"code={code} out={out[:200]!r} err={err[:200]!r}")

# CLI-202: modified file exit 3
target = next(root201.glob("*.whl"))
original = target.read_text()
target.write_text(original + "X")
code, out, err = c.run_sub(["--config", str(cfg201), "bundle", "verify", str(root201)])
target.write_text(original)
ok = code == 3 and "Do not install this bundle" in out
record("CLI-202", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-203: an added file exit 3, trustworthy false
extra = root201 / "extra_not_in_manifest.whl"
extra.write_text("sneaky content")
code, out, err = c.run_sub(["--json", "--config", str(cfg201), "bundle", "verify", str(root201)])
extra.unlink()
doc = json.loads(out)
ok = code == 3 and doc.get("trustworthy") is False
record("CLI-203", "PASS" if ok else "FAIL", f"code={code} doc={doc}")

# CLI-204: removed file exit 3
removed = root201 / "file0.whl"
removed_text = removed.read_text()
removed.unlink()
code, out, err = c.run_sub(["--config", str(cfg201), "bundle", "verify", str(root201)])
removed.write_text(removed_text)
ok = code == 3 and "file0.whl" in out
record("CLI-204", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-205: stripping manifest.ed25519 with --publisher-key given -> exit 3
cfg205, d205 = new_cfg("cli205")
root205 = stage(d205)
seal(cfg205, root205, sign_with=ed_priv_path)
(root205 / "manifest.ed25519").unlink()
code, out, err = c.run_sub(["--config", str(cfg205), "bundle", "verify", str(root205), "--publisher-key", str(ed_pub_path)])
ok = code == 3
record("CLI-205", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-206: stripping manifest.sig -> exit 3
cfg206, d206 = new_cfg("cli206")
root206 = stage(d206)
seal(cfg206, root206)
(root206 / "manifest.sig").unlink()
code, out, err = c.run_sub(["--config", str(cfg206), "bundle", "verify", str(root206)])
ok = code == 3
record("CLI-206", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-207: no manifest at all
cfg207, d207 = new_cfg("cli207")
root207 = stage(d207)
code, out, err = c.run_sub(["--config", str(cfg207), "bundle", "verify", str(root207)])
ok = code == 1 and "not a bundle" in err
record("CLI-207", "PASS" if ok else "FAIL", f"code={code} err={err[:300]!r}")

# CLI-208: manifest with a missing required field
cfg208, d208 = new_cfg("cli208")
root208 = stage(d208)
seal(cfg208, root208)
m = json.loads((root208 / "manifest.json").read_text())
del m["entries"]
(root208 / "manifest.json").write_text(json.dumps(m))
code, out, err = c.run_sub(["--config", str(cfg208), "bundle", "verify", str(root208)])
ok = code == 1 and "Traceback" not in err and "KeyError" not in err
record("CLI-208", "PASS" if ok else "FAIL", f"code={code} err={err[:300]!r}")

# CLI-209: manifest not JSON at all
cfg209, d209 = new_cfg("cli209")
root209 = stage(d209)
seal(cfg209, root209)
(root209 / "manifest.json").write_text("<html>not json</html>")
code, out, err = c.run_sub(["--config", str(cfg209), "bundle", "verify", str(root209)])
ok = code == 1 and "Traceback" not in err
record("CLI-209", "PASS" if ok else "FAIL", f"code={code} err={err[:300]!r}")

# CLI-210: verify with wrong session secret
cfg210a, d210a = new_cfg("cli210a", secret="key-alpha-1234")
cfg210b, d210b = new_cfg("cli210b", secret="key-beta-5678")
root210 = stage(d210a)
seal(cfg210a, root210)
code, out, err = c.run_sub(["--config", str(cfg210b), "bundle", "verify", str(root210)])
ok = code == 3 and ("seal" in out.lower() or "seal" in err.lower())
record("CLI-210", "PASS" if ok else "FAIL", f"code={code} out={out[:300]!r}")

# CLI-211: signed bundle, verify with no key -> says so
cfg211, d211 = new_cfg("cli211")
root211 = stage(d211)
seal(cfg211, root211, sign_with=ed_priv_path)
code, out, err = c.run_sub(["--config", str(cfg211), "bundle", "verify", str(root211)])
ok = code == 0 and "hashes alone" in out and "no key was given" in out.lower()
record("CLI-211", "PASS" if ok else "FAIL", f"code={code} out={out[:400]!r}")

# CLI-212: --publisher-key pointing at a private key or rubbish
cfg212, d212 = new_cfg("cli212")
root212 = stage(d212)
seal(cfg212, root212, sign_with=ed_priv_path)
rubbish = WORK / "rubbish.pem"
rubbish.write_text("not a pem key")
res212 = {}
for label, path in [("private-key-as-public", ed_priv_path), ("rubbish", rubbish)]:
    code, out, err = c.run_sub(["--config", str(cfg212), "bundle", "verify", str(root212), "--publisher-key", str(path)])
    res212[label] = (code, "Traceback" in err, err[-200:])
ok = all(v[0] != 0 for v in res212.values())
record("CLI-212", "PASS" if ok else "FAIL", f"{res212}")

# CLI-213: verify --json exit equals text path
cfg213, d213 = new_cfg("cli213")
root213 = stage(d213)
seal(cfg213, root213)
target213 = next(root213.glob("*.whl"))
target213.write_text(target213.read_text() + "TAMPER")
code_t, out_t, _ = c.run_sub(["--config", str(cfg213), "bundle", "verify", str(root213)])
code_j, out_j, _ = c.run_sub(["--json", "--config", str(cfg213), "bundle", "verify", str(root213)])
doc = json.loads(out_j)
ok = code_t == 3 and code_j == 3 and doc.get("trustworthy") is False
record("CLI-213", "PASS" if ok else "FAIL", f"text_code={code_t} json_code={code_j} trustworthy={doc.get('trustworthy')}")

# CLI-214: bundle sbom reports resolved versions
code, out, err = c.run(["bundle", "sbom"])
lines = [l for l in out.splitlines() if "==" in l]
ok214 = code == 0 and len(lines) > 0 and "as resolved rather than as requested" in out
import importlib.metadata as im
sample_ok = False
if lines:
    name, ver = lines[0].strip().split("==")
    try:
        real_ver = im.version(name)
        sample_ok = real_ver == ver
    except Exception:
        sample_ok = None
ok = ok214 and (sample_ok is not False)
record("CLI-214", "PASS" if ok else "FAIL", f"code={code} n_dists={len(lines)} sample_check={sample_ok} sample_line={lines[0] if lines else None}")

# CLI-215: bundle sbom needs no configuration and no database
code, out, err = c.run(["bundle", "sbom"])
ok = code == 0
record("CLI-215", "PASS" if ok else "FAIL", f"code={code} (no --config given at all)")

print("done bundle batch part2")
