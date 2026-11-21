"""What the published wheel contains (brief AC 32): ``py.typed`` marks the package
as typed, so a type checker uses its annotations instead of treating it as untyped."""
import os
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_py_typed_is_in_the_source_tree():
    marker = ROOT / "contexel" / "py.typed"
    assert marker.is_file()
    assert marker.stat().st_size == 0  # PEP 561: a marker file, content ignored


def test_the_wheel_ships_py_typed(tmp_path):
    # hatchling is the build backend; CI's test legs do not have it installed
    # (pip builds in an isolated environment), so CI's "hygiene" job checks the
    # real wheel too.
    build = pytest.importorskip("hatchling.build")
    previous = os.getcwd()
    os.chdir(ROOT)
    try:
        wheel = build.build_wheel(str(tmp_path))
    finally:
        os.chdir(previous)
    with zipfile.ZipFile(tmp_path / wheel) as archive:
        names = archive.namelist()
    assert "contexel/py.typed" in names
    assert "contexel/__init__.py" in names
