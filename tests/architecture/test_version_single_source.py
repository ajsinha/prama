"""The version gate passes on the repository and fails on a planted copy.

"A gate nobody has seen fail is a gate nobody knows works" — Maya's rule,
adopted with the gate itself.

Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _gate():
    spec = importlib.util.spec_from_file_location(
        "check_version_source", REPO / "scripts/check_version_source.py"
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _tree(tmp: Path) -> Path:
    (tmp / "src/prama").mkdir(parents=True)
    shutil.copy(REPO / "src/prama/version.py", tmp / "src/prama/version.py")
    (tmp / "deploy/helm/prama").mkdir(parents=True)
    shutil.copy(REPO / "deploy/helm/prama/Chart.yaml", tmp / "deploy/helm/prama/Chart.yaml")
    return tmp


def test_the_repository_agrees_with_itself() -> None:
    assert _gate().problems(REPO) == []


def test_a_restated_literal_in_source_fails(tmp_path: Path) -> None:
    gate = _gate()
    root = _tree(tmp_path)
    assert gate.problems(root) == []  # the control: a clean tree passes
    version = gate.authority(root)
    (root / "src/prama/banner.py").write_text(f'SHOWN = "{version}"\n')
    assert any("banner.py" in p for p in gate.problems(root))


def test_a_stale_chart_fails(tmp_path: Path) -> None:
    gate = _gate()
    root = _tree(tmp_path)
    chart = root / "deploy/helm/prama/Chart.yaml"
    chart.write_text(chart.read_text().replace(gate.authority(root), "9.9.9"))
    assert any("Chart.yaml" in p and "9.9.9" in p for p in gate.problems(root))
