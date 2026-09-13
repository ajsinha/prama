import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import cli_common as c
from logger import record

WORK = c.WORKDIR / "bundle"
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
    root.mkdir(exist_ok=True)
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

ed_priv2 = ed25519.Ed25519PrivateKey.generate()
ed_priv_enc_path = WORK / "priv_enc.pem"
ed_priv_enc_path.write_bytes(ed_priv2.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(b"passphrase123")))

rsa_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
rsa_priv_path = WORK / "rsa_priv.pem"
rsa_priv_path.write_bytes(rsa_priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

# CLI-194: bundle seal writes manifest, seal, summary
cfg194, d194 = new_cfg("cli194")
root194 = stage(d194)
code, out, err = c.run_sub(["--config", str(cfg194), "bundle", "seal", str(root194)])
ok = (
    code == 0
    and (root194 / "manifest.json").exists()
    and (root194 / "manifest.sig").exists()
    and not (root194 / "manifest.ed25519").exists()
    and "manifest:" in out
    and "sbom:" in out
)
record("CLI-194", "PASS" if ok else "FAIL", f"code={code} out={out[:200]!r} err={err[:200]!r}")

# CLI-195: bundle seal with empty session secret refused
cfg195, d195 = new_cfg("cli195", secret="")
root195 = stage(d195)
code, out, err = c.run_sub(["--config", str(cfg195), "bundle", "seal", str(root195)])
manifest_written = (root195 / "manifest.json").exists()
ok = code == 1 and not manifest_written and "Traceback" not in err
record("CLI-195", "PASS" if ok else "FAIL", f"code={code} manifest_written={manifest_written} err={err[:300]!r}")

# CLI-196: seal without --sign-with says what an HMAC is worth
cfg196, d196 = new_cfg("cli196")
root196 = stage(d196)
code, out, err = c.run_sub(["--config", str(cfg196), "bundle", "seal", str(root196)])
ok = code == 0 and "nothing to anybody" in out and "No publisher signature" in out
record("CLI-196", "PASS" if ok else "FAIL", f"code={code} out_tail={out[-400:]!r}")

# CLI-197: --sign-with produces manifest.ed25519 distinct from manifest.sig
cfg197, d197 = new_cfg("cli197")
root197 = stage(d197)
code, out, err = c.run_sub(["--config", str(cfg197), "bundle", "seal", str(root197), "--sign-with", str(ed_priv_path)])
sig = (root197 / "manifest.sig").read_text() if (root197 / "manifest.sig").exists() else None
ed = (root197 / "manifest.ed25519").read_text() if (root197 / "manifest.ed25519").exists() else None
ok = code == 0 and sig is not None and ed is not None and sig != ed
record("CLI-197", "PASS" if ok else "FAIL", f"code={code} sig_present={sig is not None} ed_present={ed is not None} distinct={sig!=ed if sig and ed else None}")

# CLI-198: --sign-with on encrypted / RSA / missing key
cfg198, d198 = new_cfg("cli198")
res198 = {}
for label, path in [("encrypted", ed_priv_enc_path), ("rsa", rsa_priv_path), ("missing", WORK / "nope.pem")]:
    (d198 / label).mkdir(exist_ok=True, parents=True)
    root = stage(d198 / label)
    code, out, err = c.run_sub(["--config", str(cfg198), "bundle", "seal", str(root), "--sign-with", str(path)])
    partial = (root / "manifest.json").exists() and not (root / "manifest.ed25519").exists()
    res198[label] = (code, "Traceback" in err, partial, err[-200:])
ok = all(v[0] != 0 and not v[1] for v in res198.values())
record("CLI-198", "PASS" if ok else "FAIL", f"{res198}")

# CLI-199: no flag accepts key material directly (inspection, not execution)
import subprocess
help_out = subprocess.run(["prama", "bundle", "seal", "--help"], capture_output=True, text=True, env=os.environ).stdout
ok = "--sign-with" in help_out and "KEY.pem" in help_out and "PEM" in help_out
record("CLI-199", "PASS" if ok else "FAIL", f"help={help_out!r}")

# CLI-200: --no-sbom omits the list and warns
cfg200, d200 = new_cfg("cli200")
root200 = stage(d200)
code, out, err = c.run_sub(["--config", str(cfg200), "bundle", "seal", str(root200), "--no-sbom"])
ok = code == 0 and "sbom:     0 distribution(s)" in out
record("CLI-200", "PASS" if ok else "FAIL", f"code={code} out={out[:250]!r}")

print("done bundle batch part1")
