#!/usr/bin/env bash
# Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved. Proprietary; see LICENSE.
# The full gate, with the exit status of every step actually respected.
#
# Written because piping pytest into `tail` returns tail's status, so a
# collection error sails through an `&&` chain and a commit lands on a red
# suite. That happened twice. `set -o pipefail` is the fix, and having one
# script means it is the fix everywhere rather than in the command somebody
# remembered to write correctly.
set -euo pipefail
cd "$(dirname "$0")/.."
ruff check src sdk kernel agent tests scripts qa/regression-suite case-studies
ruff format --check -q src sdk kernel agent tests scripts qa/regression-suite
mypy src | tail -1
mypy sdk/src | tail -1
mypy kernel/src | tail -1
mypy agent/src | tail -1
python scripts/check_file_length.py
python3 scripts/check_version_source.py
# Documentation that is generated from the code must still match the code. A
# reference edited by hand is a second source of truth, and it drifts in the
# flattering direction.
python3 scripts/generate_docs.py --check
# The lock file must describe this pyproject. A lock that has drifted is worse
# than none: it looks like a reproducible build and is not one. Skipped rather
# than failed where uv is absent, because a contributor without it can still run
# everything else.
if command -v uv >/dev/null 2>&1; then
  uv lock --check
  # requirements.txt and requirements-dev.txt are derived from the lock, for
  # pip users; a copy that has drifted from it pins the wrong versions.
  python3 scripts/export_requirements.py --check
else
  echo "uv not installed; skipping the lock-file check"
fi
# Both suites pyproject's testpaths names: tests/ and qa/regression-suite/.
pytest -q | tail -3
echo "gate: green"
