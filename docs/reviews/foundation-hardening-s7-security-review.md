Filed 2026-11-26 from the Slice 7 execution workspace for branch `feat/hardening-s7-differential-fuzz`. Sanitised: no user name, home or temporary path, e-mail address or agent identifier.

# Security review (G5): Slice 7, differential fuzz

- Role: Security Reviewer (fresh context, holds the ship veto)
- Range: main base 247d11a82521d23f60f1c7d4fa14f323a24f10e3 to head a1877f4db2e7d30a578dfbd31f57c219314e19bf (7 commits, 15 files, +995/-6)
- Mode: read-only. The working tree was clean before and after (`git status --porcelain | wc -l` printed `0`). The only files written were a generator run and two helper scripts in a scratch directory outside the repository, plus this report, which sits in a git-excluded directory (an ignored workspace directory).

## Verdict: APPROVE WITH CONDITIONS (no veto)

Nothing found is CRITICAL, HIGH or MEDIUM. There are 2 LOW findings and 4 INFO findings.

**Condition C1 (applies to F1; due before the next tag push, does not block the merge):** either remove `python -m pip install -e .` from `npm-publish` and `nuget-publish` and run the generator with `PYTHONPATH: ${{ github.workspace }}`, or have the human record in writing that the widening described in F1 is accepted. Under the .Doctrine §5 rule on security tradeoffs, the acceptance has to be the human's.

F2 is recommended hardening and is not a condition.

## Findings

### F1 (LOW): the npm and NuGet publish jobs now run PyPI-resolved build-backend code
Where: `.github/workflows/release.yml:174-179` (npm-publish) and `:224-229` (nuget-publish).

What changes:
- Both jobs hold `id-token: write` at job level (`:163`, `:216`). The runner therefore gives every step the OIDC request variables, including the new steps.
- `python -m pip install -e .` builds the editable install in an isolated environment. pip fetches `hatchling` (`pyproject.toml` `[build-system] requires = ["hatchling"]`) and its dependencies from PyPI at their latest versions, with no lockfile and no hashes, and runs them.
- No repository build hook exists (no `hatch_build.py`, no `setup.py`, no `[tool.hatch...hooks]`). The new third-party code is therefore exactly the hatchling closure.

Ordering:
- In npm-publish, the new steps run before `NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}` (`:201`), and that secret is scoped to the publish step only. The token is never in the environment of the new steps, so there is no direct leak.
- In nuget-publish, the new steps run before `NuGet/login` (`:245`).
- The job-level `CONTEXEL_FUZZ_CASES` is a constant relative path with no `${{ }}` expression, so it carries no secret and allows no injection.

Failure scenario: a compromised hatchling, or a compromised dependency of it on PyPI, runs in npm-publish. It writes `NODE_OPTIONS=--require ...` to `$GITHUB_ENV` or edits a `ts/` script, and so captures `NPM_TOKEN` during the later `npm publish` step. In nuget-publish it mints an OIDC token itself and exchanges it for a NuGet API key.

How much is new compared with the base:
- Before this branch, npm-publish ran `npm ci` (lockfile with integrity hashes, which is stricter), `npm run build`, and repository test code under `prepublishOnly`, with the real token present.
- nuget-publish ran `dotnet test` (repository code plus NuGet test packages).
- The same unpinned-PyPI class already runs with PyPI OIDC in `pypi-publish` (`pip install build twine` unpinned; `python -m build` resolves the same hatchling).
- So the marginal widening is narrow. It makes `NPM_TOKEN` reachable by a hatchling compromise, and it makes the NuGet OIDC exchange reachable from the `nuget` environment if the nuget.org trusted-publishing policy is bound to that environment. That policy setting cannot be checked from the repository.

Fix:
- The install is not needed. `dependencies = []` and the package is pure Python.
- In this review the generator ran from the repository root with only `PYTHONPATH` set, no install, and wrote the full corpus.
- Remove the install step and set `PYTHONPATH` on the generator step (condition C1).

Triggers and fork exposure:
- `release.yml` triggers only on `push: tags: ['v*']` and `workflow_dispatch`. It has no `pull_request` or `pull_request_target` trigger, so forks cannot start these jobs.
- `ci.yml` has `pull_request` (not `pull_request_target`) and `permissions: contents: read`. It references no secrets, so the new CI steps add no privileged capability.

### F2 (LOW, hygiene): the ignore rule covers only the exact path at the repository root
Where: `.gitignore:19` `parity/fuzz-corpus.json`. The pattern contains a slash, so it is anchored to the root.

Evidence:
```
$ git check-ignore -v parity/fuzz-corpus.json
.gitignore:19:parity/fuzz-corpus.json	parity/fuzz-corpus.json
$ git check-ignore -v --no-index ts/parity/fuzz-corpus.json fuzz-corpus.json csharp/parity/fuzz-corpus.json parity/corpus.json
(no output) exit=1
```

The corpus is not tracked: `git ls-files parity/ | grep -i fuzz` lists only `parity/generate_fuzz.py`.

CI is covered. Every workflow writes `parity/fuzz-corpus.json` from the root, and both replays resolve a relative value against the repository root, not the working directory (`ts/test/fuzz.test.ts:52`, `FuzzTests.cs:41`). Running from `ts/` with the documented `--out` fails with no such directory, so that case fails safe.

Failure scenario: a developer runs `--out fuzz-corpus.json` or `--out parity/corpus-2.json` locally, then runs `git add -A`. A 37 MB file is committed. The content is synthetic with no secrets, so this is repository bloat, not confidentiality.

Suggestion: a non-anchored glob such as `fuzz-corpus*.json` plus `parity/*corpus*.json`, or a size guard in a pre-commit hook.

### F3 (INFO): the replays read any path named by `CONTEXEL_FUZZ_CASES`
Where: `ts/test/fuzz.test.ts:52` (`path.resolve(ROOT, configured)`, absolute values allowed) and `csharp/Contexel.Tests/FuzzTests.cs:41` (`Path.GetFullPath(configured, RepoRoot())`).

This crosses no privilege boundary: whoever sets the variable already runs the test code. In CI the value is a constant.

One leak path exists if the variable is misconfigured. Node's JSON.parse error echoes about 10 characters of the file into the log:
```
$ node -e '<JSON.parse of "TOKEN=abcdef0123456789secretvalue\nmore", print e.message>'
v24.18.0 Unexpected token 'T', "TOKEN=abcd"... is not valid JSON
```
C#'s JsonException reports line and byte position only. With CI's constant path this cannot happen.

Deserialization is JSON only:
- TypeScript uses `JSON.parse` cast to a type.
- C# uses `JsonDocument.Parse` and then `VectorData.Convert` (`VectorData.cs:31`), a plain `ValueKind` switch to null, bool, string, number, List and Dictionary. There is no type-name or polymorphic binding and no `BinaryFormatter`.
- `JsonDocument` keeps its default depth limit of 64. Node has no explicit bound.

Who controls the file in CI: the generator, in the same job, from repository code. Measured corpus: 36,739,827 bytes, maximum nesting depth 9, ASCII only on disk.

The runners the replays call open no other file. A grep for file and process APIs in `runner.ts`, `CaseTests.cs` and `VectorData.cs` found only `VectorData.cs:22/27`, which reads `parity/vectors.json`. Case fields such as `"path": "src/a.py"` are record data and are never opened.

### F4 (INFO): generator `--out` and `--cases`
Where: `parity/generate_fuzz.py:414-424`.

- `open(args.out, "wb")` truncates whatever path the invoker names and follows symlinks. That is the invoker's own authority. The CI path does not exist in a fresh checkout (ignored, untracked). A tracked symlink could only arrive in a commit, and such a commit already controls the code that runs.
- The write is not atomic. A partial file makes both replays fail to parse, so the failure mode is closed.
- `--cases` has no upper bound and costs grow linearly. Measured default run (20,000 cases): `exit 0 seconds 9.3 peak_rss_MB 217`, file 36,739,827 bytes, `wrote 20000 cases (seed 20261126) ...; 2209 error cases, 3115 strict, 24 redrawn`.
- `--cases 0` or a negative value gives an empty corpus. Both replays then fail their minimum of 1000 cases, which is fail-closed.
- `--show` takes an argparse int, used only as a random seed component and never as an index.

Dangerous constructs: the grep of the four new files for eval, exec, pickle, marshal, subprocess, os.system, shell=True, socket, urllib, requests, http, yaml, new Function, child_process, Process.Start, TypeNameHandling and BinaryFormatter matched only `tests/test_fuzz_generator.py:9` and `:45`.

The test harness call (`tests/test_fuzz_generator.py:44-45`) is safe:
- It uses a list argv `[sys.executable, <repo>/parity/generate_fuzz.py, *args]`, with no shell, `check=True` and `cwd=ROOT`.
- The arguments are integer constants rendered with `str()` and a pytest `tmp_path`, so there is nothing to inject.
- The environment is `os.environ` plus `PYTHONHASHSEED` and `PYTHONPATH`.

JSON dumps followed by loads serves only as a deep copy. The quarantine patterns are fixed and simple; none can backtrack catastrophically.

### F5 (INFO): failure output carries raw control characters from the corpus
The corpus deliberately contains ESC, NUL, BEL and similar characters: 43,902 strings contain ESC. They appear in failure messages only when a divergence occurs. The worst outcome is cosmetic ANSI rendering in the log.

They cannot form a GitHub workflow command. Of 2,409,259 corpus strings and keys, 0 have a line that starts with `::` once leading whitespace is removed, and only 2 contain a colon at all. The alphabets in `generate_fuzz.py` have no colon-bearing word.

### F6 (INFO): fail-closed posture checked by reading, not by execution
- `ts/test/fuzz.test.ts:43-50`: if the variable is unset and `CI` is set, a failing test is registered.
- `FuzzTests.cs:37`: all three Facts fail.
- A variable that is set but names a missing file throws (TS at module load, C# with FileNotFoundException), and the run fails.
- `npm-publish` sets the variable at job level, so `npm publish` -> `prepublishOnly` -> `npm test` sees it.

I did not run the TS or C# suites, because they write `dist-test/`, `bin/` and `obj/` into the tree. One side note: `FuzzTests.cs:92` `long.Parse` on a malformed id would throw inside the failure path. That still fails, but it loses the diagnostic. It is not a security issue.

## The six-point sweep

1. **Secrets and private data:** clean. Over the added lines of `git diff 247d11a..a1877f4`:
   - E-mail-shaped regex: 2 hits, both `@pytest.fixture` (false positives).
   - User, home and temp path regex (drive paths, Users, AppData, Temp, /tmp/, home/): 0 hits. The only `/tmp/nupkg` is a pre-existing context line in `ci.yml`, not an added one.
   - Token and credential regex (api key, secret, token, password, bearer, GitHub/npm/AWS/NuGet key shapes, private-key header): every hit is `max_tokens`, `tokenizes`, or the synthetic corpus words "secret" and "ignore all previous instructions".
   - Agent-identifier regex: 0 hits in the diff and 0 in the commit messages (no co-author or sign-off trailers).
   - All 7 commits have a single author.
   - Error messages print case ids and corpus values only (F3, F5).
2. **Input boundaries:** the environment-variable path (F3), the generator CLI (F4) and the subprocess argv (F4) were all reviewed. No SQL or template surface. No shell interpolation: the new workflow lines contain no `${{ }}` expression.
3. **Dependencies:**
   - `git diff --stat 247d11a..a1877f4 -- pyproject.toml ts/package-lock.json ts/package.json 'csharp/**/*.csproj' requirements*.txt .github/actions` shows only `ts/package.json | 2 +-`, the test-script line that adds `dist-test/test/fuzz.test.js`.
   - No `PackageReference` was added (grep exit 1).
   - The added `uses:` lines are `actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97` twice. That SHA already occurs 5 times in the base `release.yml`, so no new Action and no new pin.
   - `npm audit --package-lock-only` in `ts/` printed `found 0 vulnerabilities`. This made one registry query; it wrote no file.
   - The Python runtime dependency list is `dependencies = []`, unchanged. No pip-audit was needed for a zero-dependency set.
   - Plan constraint met: "zero new dependencies".
4. **Dangerous constructs:** none beyond the safe list-argv `subprocess.run` in the test (F4). No eval, exec, pickle, yaml or shell use.
5. **AuthN/AuthZ:** no auth surface in the code. The CI credential surface is analysed in F1. Publishing stays gated on `github.event_name == 'push' && github.ref_type == 'tag'`, unchanged.
6. **Failure posture:** fail-closed under CI (F6). Resources are bounded in CI: 9.3 s, 217 MB, a 37 MB corpus, depth 9 (F3, F4). The publish jobs keep `timeout-minutes: 15`.

## Executed evidence
- `PYTHONPATH=<repo> PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider tests/test_fuzz_generator.py` printed `8 passed in 3.45s`, and the tree stayed clean.
- With `PYTHONPATH` at the repo root, `contexel.__file__` resolved to the repository package (Python 3.12.7), not the stale site-packages copy.
- The generator was run with `--out` pointing outside the repository; the output and the inspection results are quoted in F3 to F5.

## Hands off to
The Release Manager, for C1 before the next tag push. Nothing goes back to the builder for the merge.
