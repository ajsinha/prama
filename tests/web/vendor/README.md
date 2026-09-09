# Test-only vendored assets

`axe.min.js` is [axe-core](https://github.com/dequelabs/axe-core) 4.10.2, MPL-2.0,
used by `tests/web/test_axe.py` to audit the console in a real browser.

It lives here rather than under `src/prama/web/static/vendor/` deliberately: it
is an analyser, not part of the product, and shipping an audit tool inside the
application would put half a megabyte of test code on every page load.

Checked in rather than fetched, for the same reason everything else is vendored:
a suite that downloads its own analyser fails on an aeroplane, fails behind a
proxy, and silently audits against a different version each time it succeeds.

To update it, replace the file and note the version here. `test_axe_core_is_vendored`
fails — rather than skipping — if it is missing, because a suite with no analyser
reports green and nobody has looked.
