"""Fail when a published benchmark number differs from the generated results.

The README, the PyPI README and the site show benchmark numbers; the benchmark
writes them to ``benchmarks/COMPARISON.json`` and ``benchmarks/RESULTS.json``
(brief AC 26). The tables in the published files are generated blocks, the few
prose numbers are registered claims, and any other number with a benchmark unit
is an error: see ``benchmarks/publish.py`` for the rules.

Runs with the standard library and contexel only (no benchmark extras, no network,
no dataset), so it runs in CI on every push.

    python tools/check_benchmark_numbers.py            # check the repository
    python tools/check_benchmark_numbers.py --write    # regenerate the marked blocks
    python tools/check_benchmark_numbers.py --root DIR # check another tree (the tests do)

Exit status: 0 everything agrees, 1 something differs (each problem is printed;
a missing, unreadable or oversized file, and results with a missing key, a value
of the wrong type, an empty list or a zero divisor, are reported as problems
rather than a traceback).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    here = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=here)
    parser.add_argument("--write", action="store_true",
                        help="rewrite the generated blocks from the JSON results, then check")
    args = parser.parse_args(argv)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:  # a problem quoting a non-ASCII number must print, not crash
        reconfigure(errors="backslashreplace")

    sys.path.insert(0, str(here))
    from benchmarks import publish  # noqa: E402

    root = args.root.resolve()
    if args.write:
        try:
            for rel in publish.write(root):
                print(f"rewrote the generated blocks of {rel}")
        except (publish.PublishError, OSError, *publish.MALFORMED) as exc:
            print(f"cannot write the generated blocks: {type(exc).__name__}: {exc}")
            return 1
    problems = publish.check(root)
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} problem(s): the published benchmark numbers do not match the results")
        return 1
    print("benchmark numbers: README, PyPI README and site agree with the generated results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
