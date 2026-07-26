# G4 Review — PyPI prep + docs site (0.1.11)

Three-judge fresh-context panel (facts vs repo · design/a11y/self-containment
· links/snippets/workflow). 15 findings: 4 BLOCKER, 5 MAJOR, 6 MINOR — all
resolved; none waived.

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| 1 | BLOCKER | benchmarks.html quoted stale trace numbers (≈1% / 3.3×) vs RESULTS.md (46.3 vs 176.7 ms, 3.81×) | Quotes RESULTS.md figures verbatim |
| 2 | BLOCKER | benchmarks.html invented tokenizer figures (−2% prose) and hid the +17.5% dense-prose overestimate | Restated: −0.4%..+4% typical, ~+18% dense prose, −29% JSON |
| 3 | BLOCKER | index.html "Six stages" vs seven exports | Unified framing: "six pipeline stages plus a merge combiner" (index + README_PYPI) |
| 4 | BLOCKER | contract.html flagship snippet raised TypeError (`stage(rescore, query_from_task, ...)` positional; undefined name) | Rewritten as a valid per-task factory `code_search(task_query)` |
| 5 | MAJOR | same snippet, semantic impossibility of pinning a per-task query in a static pipeline | Covered by the factory rewrite |
| 6 | MAJOR | stages.html "(measured: ~1%)" unsupported | Replaced with the real 46.3-vs-43.6 ms measurement |
| 7 | MAJOR | dark mode: --good/--warn/--blue/--violet below WCAG AA on dark surfaces (2.7–3.6:1) | Lightened dark-mode variants (#3DD68C/#F0A464/#7CA7FF/#A99CFF) |
| 8 | MAJOR | index.html had no h1 | Visually-hidden h1 + .visually-hidden utility |
| 9 | MAJOR | architecture.html misused ARIA tabs (role=tab without selected/controls/keyboard) | Roles dropped; plain buttons with aria-pressed; aria-live kept |
| 10 | MINOR | index table intro conflated the two experiments | Intro now separates outcome columns from the shared-glue ms @28k |
| 11 | MINOR | duplicate of #3 (plumbing lens) | Same fix |
| 12 | MINOR | demo JS prices ~1–2 tokens under the library's canonical JSON (separator spaces) | Claim softened to "≈4 chars/token + 2 framing" |
| 13 | MINOR | stages.html lead said every stage auto-traced; merge is not | Exception stated in the merge entry |
| 14 | MINOR | site_check.py didn't scan CSS for @import/url() CDNs nor iframe/video/audio/source | Both added; checker re-run clean |
| 15 | MINOR | 197 KB logo on every page | Optimized to 9.5 KB (720 px, 256-color dithered); visually verified |

Panel also independently re-verified the pinned action SHAs (git ls-remote)
and all local links/anchors — clean.
