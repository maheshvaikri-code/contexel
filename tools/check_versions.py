"""Fail when the seven version locations of the three packages disagree.

One release ships a PyPI wheel, an npm tarball and a NuGet package, and each
carries its own copy of the version. A release whose copies differ publishes
mismatched packages, so this check runs on every push to main, on every pull
request and in the release gate (brief AC 33), not only when a tag is cut.

Standard library only, and it runs on every supported Python (3.9 and later),
so the pyproject version is read with a regular expression, not ``tomllib``.

    python tools/check_versions.py            # check the repository
    python tools/check_versions.py --root DIR # check another tree (the tests do)

Exit status: 0 all agree, 1 they disagree (the files are named), 2 a location
could not be read (the file and what was expected are named).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional, Sequence


NL = chr(10)


class Location(NamedTuple):
    label: str      # what the entry is, for the message
    path: str       # relative to the root, with forward slashes
    read: Callable[[str], str]  # file text -> the version string


class Found(NamedTuple):
    label: str
    path: str
    version: str


class Unreadable(Exception):
    """A location whose version could not be read."""


def _project_version(text: str) -> str:
    # the `version = "x"` line of the [project] table, not another table's
    section = re.search(r"^\[project\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    if section:
        line = re.search(r'^version\s*=\s*"([^"]+)"', section.group(1), re.M)
        if line:
            return line.group(1)
    raise Unreadable('no version = "..." line in the [project] table')


def _regex(pattern: str, what: str) -> Callable[[str], str]:
    def read(text: str) -> str:
        found = re.search(pattern, text, re.M)
        if not found:
            raise Unreadable(f"no {what}")
        return found.group(1)

    return read


def _json_version(*keys: str) -> Callable[[str], str]:
    def read(text: str) -> str:
        try:
            value = json.loads(text)
            for key in keys:
                value = value[key]
        except RecursionError as exc:  # json.loads on very deeply nested input
            raise Unreadable("the JSON is nested too deeply to read") from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise Unreadable(f"no {' / '.join(keys)} in the JSON ({exc!r})") from exc
        if not isinstance(value, str) or not value:
            raise Unreadable(f"{' / '.join(keys)} is not a version string")
        return value

    return read


LOCATIONS: Sequence[Location] = (
    Location("Python package (pyproject)", "pyproject.toml", _project_version),
    Location("Python module", "contexel/__init__.py",
             _regex(r'^__version__\s*=\s*"([^"]+)"', '__version__ = "..." line')),
    Location("npm package", "ts/package.json", _json_version("version")),
    Location("npm lockfile (root)", "ts/package-lock.json", _json_version("version")),
    Location("npm lockfile (package entry)", "ts/package-lock.json",
             _json_version("packages", "", "version")),
    Location("TypeScript constant", "ts/src/index.ts",
             _regex(r'^export const VERSION\s*=\s*"([^"]+)"', 'export const VERSION = "..."')),
    Location("NuGet package (csproj)", "csharp/Contexel/Contexel.csproj",
             _regex(r"<Version>([^<]+)</Version>", "<Version> element")),
)


def collect(root: Path) -> List[Found]:
    """Read every location; raise Unreadable (naming the file) on the first failure."""
    found: List[Found] = []
    for loc in LOCATIONS:
        path = root / loc.path
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            why = exc.strerror if isinstance(exc, OSError) and exc.strerror else exc
            raise Unreadable(f"{loc.path} ({loc.label}): cannot read it ({why})") from exc
        try:
            found.append(Found(loc.label, loc.path, loc.read(text)))
        except Unreadable as exc:
            raise Unreadable(f"{loc.path} ({loc.label}): {exc}") from exc
    return found


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split(NL + NL)[0])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                        help="repository root (default: this repository)")
    args = parser.parse_args(argv)
    try:
        found = collect(Path(args.root))
    except Unreadable as exc:
        print(f"check_versions: {exc}", file=sys.stderr)
        return 2
    versions = sorted({f.version for f in found})
    if len(versions) == 1:
        print(f"check_versions: all {len(found)} version locations say {versions[0]}")
        return 0
    print("check_versions: the version locations disagree:", file=sys.stderr)
    for f in found:
        print(f"  {f.version:<12} {f.path}  ({f.label})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
