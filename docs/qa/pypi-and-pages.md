# G5 QA — PyPI prep + docs site (0.1.11)

All output below is pasted from real runs on 2026-07-26 (Windows, Python
3.12.7).

## Site verification (fail-closed gate, post-fixes)

```
$ python tools/site_check.py
checked 6 pages under site/ -> OK
exit=0
```

Covers: local link/asset existence, no external embedded resources in HTML
or CSS (CDN check incl. @import/url()), secret scan. Same script gates the
Pages workflow before deploy.

## Tests

Doctrine framework self-tests are excluded from routine runs per the
human's instruction (`--ignore-glob=tests/test_doctrine_*`); one of them
(`test_doctrine_dashboard.py::test_openapi_lists_only_the_bounded_v1_surface`)
fails independently of this work and is out of scope here — not hidden,
noted.

```
$ python -m pytest tests reference_agent -q --ignore-glob="tests/test_doctrine_*"   (x5)
46 passed in 0.24s
46 passed in 0.23s
46 passed in 0.26s
46 passed in 0.24s
46 passed in 0.22s
```

Anomaly, recorded honestly: one earlier invocation of the same command
reported `1 failed, 45 passed in 0.42s`; the failing test id was not
captured, and five consecutive clean-state reruns pass. That invocation ran
while G4 review agents were concurrently executing Python in this working
tree (a plausible interference source — hypothesis, not established cause).
Watch item: if it recurs, capture with `-x -lf` immediately.

## Package build

```
$ python -m build && python -m twine check dist/*
Successfully built contexel-0.1.11.tar.gz and contexel-0.1.11-py3-none-any.whl
Checking dist/contexel-0.1.11-py3-none-any.whl: PASSED
Checking dist/contexel-0.1.11.tar.gz: PASSED
```

(0.1.10 artifacts also built PASSED before the bump; rebuilt at 0.1.11 —
output above is from the post-bump run.)

## Security / publish governance

- Site output contains no secrets (scanner + review); publishes `site/`
  only; docs/ paperwork never published.
- Workflow pins actions by full SHA; fail-closed verify precedes deploy.
- §5 escalations reserved for the human: `git push`, enabling Pages
  (Settings → Pages → Source: GitHub Actions), `twine upload`.
