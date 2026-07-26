"""Fail-closed checks for the docs site (used locally and by pages.yml).

Verifies, over every HTML file in site/:
1. every local href/src target exists (no 404 links or missing assets);
2. the site is self-contained — no external stylesheet/script/font loads
   (external <a> links are fine; embedded resources are not);
3. no secret-shaped strings in the published output.

Exit code 0 = publishable; 1 = do not publish.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

ATTR = re.compile(r"""(?:href|src)=["']([^"']+)["']""", re.IGNORECASE)
EMBED = re.compile(
    r"""<(?:link[^>]+href|(?:script|img|iframe|video|audio|source)[^>]+src)"""
    r"""=["'](https?:)?//""",
    re.IGNORECASE,
)
CSS_EMBED = re.compile(r"""(?:@import|url\()\s*["']?\s*(?:https?:)?//""",
                       re.IGNORECASE)
SECRET = re.compile(
    r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN[ A-Z]*PRIVATE KEY)"
)


def main() -> int:
    problems: list[str] = []
    pages = sorted(SITE.glob("*.html"))
    if not pages:
        print(f"no pages found under {SITE}")
        return 1
    for page in pages:
        text = page.read_text(encoding="utf-8")
        if EMBED.search(text):
            problems.append(f"{page.name}: external embedded resource (CDN) found")
        if SECRET.search(text):
            problems.append(f"{page.name}: secret-shaped string found")
        for target in ATTR.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            local = (page.parent / target.split("#")[0]).resolve()
            if not local.exists():
                problems.append(f"{page.name}: broken local link -> {target}")
    for sheet in SITE.glob("assets/*.css"):
        text = sheet.read_text(encoding="utf-8")
        if CSS_EMBED.search(text):
            problems.append(f"assets/{sheet.name}: external @import/url() found")
        if SECRET.search(text):
            problems.append(f"assets/{sheet.name}: secret-shaped string found")
    for line in problems:
        print("FAIL:", line)
    print(f"checked {len(pages)} pages under site/ -> "
          f"{'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
