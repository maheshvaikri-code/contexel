"""Run every suite and write benchmarks/RESULTS.md and benchmarks/RESULTS.json.

    python -m benchmarks
"""
from __future__ import annotations

import json
from pathlib import Path

from . import suites_report


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main() -> None:
    results = suites_report.collect()
    here = Path(__file__).resolve().parent
    _write(here / "RESULTS.json", json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    _write(here / "RESULTS.md", suites_report.render(results))
    print(f"\nwrote {here / 'RESULTS.json'} and {here / 'RESULTS.md'}")
    print("\ndeterminism:", ", ".join(
        f"{r['check']}: {r['result']}"
        for r in suites_report.determinism_rows(results["determinism"])))


if __name__ == "__main__":
    main()
