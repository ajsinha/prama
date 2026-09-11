#!/usr/bin/env bash
# The full gate, with the exit status of every step actually respected.
#
# Written because piping pytest into `tail` returns tail's status, so a
# collection error sails through an `&&` chain and a commit lands on a red
# suite. That happened twice. `set -o pipefail` is the fix, and having one
# script means it is the fix everywhere rather than in the command somebody
# remembered to write correctly.
set -euo pipefail
cd "$(dirname "$0")/.."
ruff check src tests scripts
ruff format --check -q src tests scripts
mypy src | tail -1
python scripts/check_file_length.py
# Documentation that is generated from the code must still match the code. A
# reference edited by hand is a second source of truth, and it drifts in the
# flattering direction.
python3 scripts/generate_docs.py --check
pytest tests -q | tail -3
echo "gate: green"
