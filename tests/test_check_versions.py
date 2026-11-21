"""tools/check_versions.py (brief AC 33): the seven version locations of the three
packages must agree, and the check must say which file is wrong when they do not."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NL = chr(10)
sys.path.insert(0, str(ROOT / "tools"))
import check_versions  # noqa: E402

PYPROJECT = """[build-system]
requires = ["hatchling"]

[project]
name = "contexel"
version = "{v}"
description = "x"

[project.urls]
Homepage = "https://example.invalid"

[tool.example]
version = "9.9.9"
"""
INIT = """__version__ = "{v}"
__all__ = []
"""
INDEX_TS = """export const VERSION = "{v}";
"""
CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <Version>{v}</Version>
  </PropertyGroup>
</Project>
"""

# the seven locations: the keyword that sets each one, and the file it lives in
KEYS = {
    "pyproject": "pyproject.toml",
    "init": "contexel/__init__.py",
    "package": "ts/package.json",
    "lock_root": "ts/package-lock.json",
    "lock_entry": "ts/package-lock.json",
    "index_ts": "ts/src/index.ts",
    "csproj": "csharp/Contexel/Contexel.csproj",
}


def make_tree(root: Path, version: str = "1.2.3", **versions: str) -> Path:
    """Write a minimal repository whose seven locations say ``version``, except
    the ones named in ``versions`` (keyword = key of KEYS)."""
    v = {key: versions.get(key, version) for key in KEYS}
    lock = {"name": "contexel", "version": v["lock_root"], "lockfileVersion": 3,
            "packages": {"": {"name": "contexel", "version": v["lock_entry"]},
                         "node_modules/x": {"version": "9.9.9"}}}
    files = {
        "pyproject.toml": PYPROJECT.format(v=v["pyproject"]),
        "contexel/__init__.py": INIT.format(v=v["init"]),
        "ts/package.json": json.dumps({"name": "contexel", "version": v["package"]}),
        "ts/package-lock.json": json.dumps(lock),
        "ts/src/index.ts": INDEX_TS.format(v=v["index_ts"]),
        "csharp/Contexel/Contexel.csproj": CSPROJ.format(v=v["csproj"]),
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def run(root, capsys):
    status = check_versions.main(["--root", str(root)])
    out = capsys.readouterr()
    return status, out.out, out.err


def test_agreeing_versions_pass(tmp_path, capsys):
    status, out, err = run(make_tree(tmp_path), capsys)
    assert status == 0, err
    assert out == "check_versions: all 7 version locations say 1.2.3" + NL


@pytest.mark.parametrize("key", sorted(KEYS))
def test_disagreeing_versions_fail_naming_the_file(tmp_path, capsys, key):
    root = make_tree(tmp_path, **{key: "1.2.4"})
    status, _out, err = run(root, capsys)
    assert status == 1
    assert KEYS[key] in err
    assert "1.2.3" in err and "1.2.4" in err


def test_the_pyproject_version_is_the_project_tables_not_another_tables(tmp_path, capsys):
    root = make_tree(tmp_path)
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    other, rest = text.split("[tool.example]")
    # a [tool.*] table with a different version BEFORE [project] must not win
    (root / "pyproject.toml").write_text(
        "[tool.example]" + rest + NL + other, encoding="utf-8")
    status, _out, err = run(root, capsys)
    assert status == 0, err


def test_crlf_files_are_read(tmp_path, capsys):
    root = make_tree(tmp_path)
    for rel in ("pyproject.toml", "contexel/__init__.py", "ts/src/index.ts",
                "csharp/Contexel/Contexel.csproj"):
        path = root / rel
        path.write_bytes(path.read_bytes().replace(NL.encode(), (chr(13) + NL).encode()))
    status, _out, err = run(root, capsys)
    assert status == 0, err


def test_a_missing_file_fails_loudly_naming_it(tmp_path, capsys):
    root = make_tree(tmp_path)
    (root / "csharp/Contexel/Contexel.csproj").unlink()
    status, _out, err = run(root, capsys)
    assert status == 2
    assert "csharp/Contexel/Contexel.csproj" in err


@pytest.mark.parametrize("rel, broken", [
    ("pyproject.toml", "[project]" + NL + "name = 'x'" + NL),
    ("contexel/__init__.py", "__all__ = []" + NL),
    ("ts/package.json", "{}"),
    ("ts/package.json", "not json"),
    ("ts/package-lock.json", json.dumps({"version": "1.2.3", "packages": {}})),
    ("ts/src/index.ts", "export const NAME = 'x';" + NL),
    ("csharp/Contexel/Contexel.csproj", "<Project></Project>"),
])
def test_a_file_without_a_readable_version_fails_loudly(tmp_path, capsys, rel, broken):
    root = make_tree(tmp_path)
    (root / rel).write_text(broken, encoding="utf-8")
    status, _out, err = run(root, capsys)
    assert status == 2
    assert rel in err


def test_the_repository_itself_agrees(capsys):
    status, out, err = run(ROOT, capsys)
    assert status == 0, err
    assert "version locations say" in out


def test_it_runs_as_the_script_ci_runs(tmp_path):
    root = make_tree(tmp_path, csproj="9.0.0")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_versions.py"), "--root", str(root)],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1
    assert "csharp/Contexel/Contexel.csproj" in proc.stderr


NOT_UTF8 = bytes([0xFF, 0xFE, 0x00]) + b" not utf-8 " + bytes([0x80])


@pytest.mark.parametrize("rel", ["contexel/__init__.py", "ts/package.json"])
def test_a_file_that_is_not_utf8_fails_loudly_naming_it(tmp_path, capsys, rel):
    root = make_tree(tmp_path)
    (root / rel).write_bytes(NOT_UTF8)
    status, _out, err = run(root, capsys)
    assert status == 2
    assert rel in err
    assert "Traceback" not in err
