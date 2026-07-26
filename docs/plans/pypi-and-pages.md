# G2 Plan — PyPI prep + docs site (Class M)

## Work packages

1. **Site (`site/`, designated publish source)** — bright, self-contained,
   wiki-style static pages sharing one stylesheet (`site/assets/style.css`,
   logo bundled at `site/assets/contexel_logo.png`):
   `index.html` (hero + narrative + at-a-glance), `architecture.html`
   (interactive pipeline explorer + budget demo, replaces the old static
   page), `getting-started.html`, `stages.html` (per-stage wiki reference),
   `benchmarks.html`, `contract.html` (context-contract thesis, condensed).
   Root `architecture.html` becomes a redirect into `site/` so the old
   `file://` path keeps working.
2. **PyPI narrative** — `README_PYPI.md` with absolute URLs (PyPI renders no
   repo-relative links); `pyproject.toml` `readme` pointer + richer
   `[project.urls]`. Repo `README.md` gains the narrative intro + site links.
3. **Publish workflow** — `.github/workflows/pages.yml` per
   `skills/web-publishing.md`: push-triggered, path-scoped to `site/**`,
   fail-closed (link/asset check before deploy), publishes `site/` only.
4. **Build validation** — `python -m build` + `twine check dist/*` (tooling:
   `build`/`twine` installed as environment dev tools, not project deps).

## Decisions (recorded)

- **Hand-rolled static HTML instead of a borrowed generator template.**
  Doctrine prefers borrowing (MkDocs/Jekyll/etc.), but a generator adds a
  build dependency and toolchain to a deliberately zero-dependency project;
  the site follows the proven Just-the-Docs *structure* (sidebar wiki
  layout) implemented in ~250 lines of original CSS — self-contained,
  license-clean, no build step, renders from `file://`.
- **Default-light ("brighter") theme with a legible dark variant** via
  `prefers-color-scheme`; brand colors sampled from the logo (blue #2563EB →
  violet #6D5AE6 gradient, navy ink).
- **Interactivity = vanilla JS, inline, no CDN**: stage explorer (click a
  pipeline stage → its exact mechanics) and a budget-slider demo running a
  faithful miniature of select/dedupe/trim in the browser.
- **Action SHAs**: workflow pins actions by full commit SHA fetched from
  GitHub at authoring time; if unfetchable, tags + a TODO note (never
  invented SHAs).

## Gates

- G3 build → G4 review (3-judge panel: content accuracy vs repo, design/
  a11y/self-containment, link+snippet correctness) → G5 QA (link/asset
  checker over `site/`, pytest, `twine check` — real output pasted) →
  version 0.1.11 + CHANGELOG + commit.
- §5 escalations left for the human: `git push`, enabling Pages, PyPI upload.
