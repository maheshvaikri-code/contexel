# Code Review — csharp-parity @ worktree on df835f2 (uncommitted)
<!-- G4 artifact. File as docs/reviews/csharp-parity.md -->

**Reviewer role:** Code Reviewer (fresh context) · **Date:** 2026-07-28
**Reviewed against:** docs/adr/002-csharp-parity.md + docs/plans/csharp-parity.md
**Executed:** all commands below were actually run; outputs pasted verbatim (trimmed to the relevant lines).

~~~text
$ dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
Passed!  - Failed: 0, Passed: 36, Skipped: 0, Total: 36, Duration: 61 ms - Contexel.Tests.dll (net8.0)

$ python parity/generate_vectors.py ; git diff --stat parity/vectors.json
wrote D:\contexel\parity\vectors.json (12379 bytes)     # byte-identical: vectors are canon-fresh

$ dotnet pack csharp/Contexel/Contexel.csproj -c Release
Successfully created package Contexel.0.1.16.nupkg
# nuspec verified: MIT license expression, README.md packed, repo URL+commit, zero deps, net8.0
# dotnet build -c Release: 0 Warning(s) 0 Error(s)
~~~

A paired-probe harness (scratch console app referencing Contexel.csproj + a Python
verifier importing the canon) was run ENTIRELY under de-DE culture
(CultureInfo.DefaultThreadCurrentCulture; proven active: default-format 2.5 printed "2,5"):

~~~text
pyfloat:       200,033 paired cases vs repr(float)  -> 0 mismatches
               (incl. -0.0 -> "-0.0", 5e-324, denormals, 1e-4/1e-5, 1e15/1e16/1e21
                boundaries, double.Max/MinValue, 120k random bit patterns)
pyround:       139,020 paired cases vs round(x, nd), nd 0..7 -> 0 value mismatches
               below 1e15 (incl. 16,000 constructed exact ties k/2^(nd+1) and the
               2.675 near-tie class); 496 mismatches ALL at nd=0 AND abs(x) >= 1e15
               (finding 4); 18,993 sign-of-zero-only diffs (finding 6)
pystr/pyrepr:  30 paired values (quote choice, x01/x1f/x7f/xa0/xad escapes, astral,
               nested dict/list) -> 0 mismatches
IsHeuristic(): default=True, method-group=True, fresh delegate instance=True
               (C# delegate == is method+target value equality, so the truncate
               fast path IS exercised), lambda wrapper=False, custom/scoped=False
AsyncLocal:    nested ScopedAsync composes overlays (inner tokenizer 7 survives an
               inner serializer scope), outer restored 2->2; Trace.Begin nesting
               restores t2 -> t1 -> null
fingerprint:   991efabe2a1a8d7b in two separate processes (stable)
serializer:    de-DE output byte-identical to the vectors sample
~~~

## Findings

| # | Sev | Location | Finding | Suggested fix | Resolution |
|---|-----|----------|---------|---------------|------------|
| 1 | [MAJOR] | csharp/Contexel/PyCompat.cs:237-246 (PyEqKey), 226-233 (ToNumber via PyCompare) | CONFIRMED by execution: longs beyond 2^53 collapse through double conversion. Allowlist([{v:9007199254740993}], "v", [9007199254740992]) keeps 1 (Python keeps 0 — probed); Rank desc on ids [9007199254740992, 9007199254740993] returns ...992 first (Python: ...993 first — probed). Also poisons Trace dropped-id attribution (Trace.IdKey routes long through PyEqKey). ADR-002 §7 draws the envelope at long.MaxValue, so 64-bit snowflake-style IDs (~1e18) are in-envelope and realistic. Dedupe/TypedKey are exact (verified) — only the eq/compare layer collapses. | In PyEqKey use the num:double-R key only when (double)l round-trips ((long)(double)l == l); otherwise "int:"+digits — no double can equal a non-representable long, so Python equality is preserved. In PyCompare, compare long-vs-long exactly; long-vs-double with an exactness-aware compare. Alternatively amend ADR-002 §7 to draw the eq/order envelope at 2^53 (human call). | fixed — re-verified by execution 2026-07-28 (see Re-review) |
| 2 | [MAJOR] | csharp/Contexel/Stages.cs:216-224 | CONFIRMED by execution: substring-mode rescore counts OVERLAPPING occurrences (IndexOf(t, idx + 1)); Python str.count is non-overlapping. Rescore([{s:"aaaa"}], "aa", ["s"], match:"substring") scores 0.191788; Python canon 0.16439 (tf 3 vs 2) — different score, different ranking, different shaped context. Note: ts/src/stages.ts:255 has the IDENTICAL divergence, and parity/vectors.json has no substring-mode vector — which is why two prior TS reviews and 36/36 green never saw it. | Advance by the match length: idx = text.IndexOf(t, idx + t.Length, StringComparison.Ordinal). File a follow-up for the TS port and add a substring-mode vector (self-bordered term, e.g. "aa" over "aaaa") so every port is pinned. | fixed — re-verified by execution 2026-07-28 (see Re-review) | TS also fixed + vector added |
| 3 | [MINOR] | csharp/Contexel/Stages.cs:38 (TypedKey), PyCompat.cs:243 (PyEqKey) | CONFIRMED: negative zero diverges. Dedupe([{k:0.0},{k:-0.0}], "k") keeps 2 (Python: 1, since ("float",-0.0) == ("float",0.0)); Allowlist([{v:-0.0}], "v", [0]) keeps 0 (Python: 1). Reachable from JSON: the loader parses "-0.0" to -0.0. | Normalize -0.0 to 0.0 before keying in TypedKey/PyEqKey (d == 0 ? 0.0 : d), matching Python hash/eq. | fixed — re-verified by execution 2026-07-28 (see Re-review) |
| 4 | [MINOR] | csharp/Contexel/PyCompat.cs:147 | CONFIRMED: the abs(x) >= 1e15 early return is not the no-op the comment claims. Doubles in [1e15, 2^52) have spacing down to 0.125; for nd=0 Python rounds the fraction away. Probe: 496/3000 mismatches in the 1e15..4e15 band at nd=0 (e.g. 1000000000000000.125 -> Python 1000000000000000.0, C# returns x unchanged). For nd >= 1 provably identical (rounding moves x by at most 0.05, under half the 0.125 spacing). Unreachable via shipped call sites (nd=0 is only used on percentages <= 100), so latent. | Either raise the guard to 1e16 (F0 handles the band fine) or drop the guard and let the F path run; fix the comment either way. | fixed — re-verified by execution 2026-07-28 (see Re-review) | guard moved to 2^53 |
| 5 | [MINOR] | csharp/Contexel/PyCompat.cs:194-206, 265-282 | CONFIRMED: lone surrogates (outside the JSON envelope, but reachable from any caller-constructed string) are handled worse than both Python and the TS port. (a) Tokens.PythonJson on a dict whose keys differ only at/after a lone surrogate throws InvalidOperationException (CompareCodePoints -> ConvertToUtf32 ArgumentException, wrapped by OrderBy — probed); Python json.dumps succeeds. (b) CodePointLength counts "ab(U+D800)cd" as 4 -> 1 token; Python len is 5 -> 2 tokens (IsHighSurrogate advances 2 without checking that a low surrogate follows; the TS codePointAt approach handles this correctly). | Advance 2 only when i+1 < Length and char.IsLowSurrogate(text[i+1]) (all four helpers); in CompareCodePoints treat an unpaired surrogate as its own code-unit value. | fixed — re-verified by execution 2026-07-28 (see Re-review) |
| 6 | [MINOR] | csharp/Contexel/PyCompat.cs:165,169 + Trace.cs:70 | The documented "-0 normalizes to 0" margin is observable on a vector-pinned surface: Audit()["reduction"] returns +0.0 where Python emits -0.0 whenever a traced pipeline slightly GROWS tokens (rescore adds a score field: reduction = -4e-05 -> Python round(-4e-05, 4) = -0.0, serialized "-0.0"; C# "0.0"). 18,993 sign-of-zero-only diffs in the fuzz. TS pyRound has the identical normalization, so the ports agree with each other and disagree with canon consistently. | Add to ADR-002 §7 as a stated margin (docs-only), addressed — margin added to ADR-002 §7 (docs) |
| 7 | [NIT] | csharp/Contexel/Tokens.cs:58, Stages.cs:42, PyCompat.cs:127 | Hard (string)k casts on IDictionary keys throw InvalidCastException for non-string keys; Python json.dumps coerces int keys to strings. Outside the declared value model, so acceptable — but the failure message is opaque. | Optional: throw ArgumentException accepted as-is — author's call, outside the value model |
| 8 | [NIT] | csharp/Contexel/Pipeline.cs:45 | d.Method.Name ?? "anonymous" — MethodInfo.Name is never null; dead branch. Lambda names are compiler-generated (cross-process stability probed OK, but they can change on recompile; fingerprints are declared language-local, so acceptable). | fixed |
| 9 | [NIT] | csharp/Contexel/Trace.cs:103 | fid is not null tracks an empty-string idField; Python treats "" as falsy (no drop tracking). Degenerate input, no realistic impact. | fixed |
| 10 | [NIT] | csharp/Contexel/Stages.cs:46 | TypedKey fallback for out-of-model types concatenates value with current-culture ToString (everything in-model is handled above, so unreachable for JSON data). | fixed |

Severity meanings: see .Doctrine/roles/code-reviewer.md.

## Verified clean (what was checked and why it is genuinely sound)

- PyFloat digit/exponent parsing from .NET "R" (200k paired cases, 0 diffs, incl.
  every boundary flagged in the review brief: negative exponents, denormals,
  -0.0 -> "-0.0", 1e15/1e16 and 1e-4/1e-5 switchovers, trailing-zero trimming).
- PyRound tie detection + F-format rounding: probed that .NET F formats from the
  EXACT binary value post-.NET Core 3.0 (2.675 -> 2.67), half-to-even on 16k
  constructed true ties, zero in-envelope mismatches.
- Culture invariance end-to-end: the entire probe ran under de-DE with the culture
  proven active; serializer output byte-identical; no "2,5" leaks anywhere.
- IsHeuristic: C# delegate == is value equality (method+target), so method-group
  conversions compare equal and the closed-form truncate fast path IS exercised
  (probed: default/method-group/fresh-instance all True; wrapper lambda False).
- AsyncLocal Scoped/ScopedAsync restore + overlay merge (nested async probe,
  concurrent tenants); Trace.Begin/Dispose nesting restores t2 -> t1 -> null.
- Rec(r) copy: shallow, insertion-order preserving, overwrite-in-place — matches
  Python {**r} semantics.
- LINQ OrderBy: stable (both directions), and its comparer-exception wrapping in
  InvalidOperationException is real (observed in a probe) — the unwrap at
  Stages.cs:287 is needed and correct.
- Vector loader: long-vs-double preserved from raw JSON text; exponent-only "1e5"
  correctly loads as double (matches Python float); Python json.dump always emits
  "." or "e" for floats so the round-trip is type-faithful.
- Test adequacy: every vectors.json key (all 9 stage vectors, contract, audit,
  serializer, token_counts, all 15 edge classes) is consumed by a test; the
  DeepEquals-by-serialization trick is pinned against test theater by the separate
  string-equality serializer vector; the int-0 rescore path is vector-pinned via
  fields_as_string ("0" vs "0.0").
- Packaging: nuspec has MIT license expression, packed README, repository URL +
  commit, zero dependencies, net8.0 only; InternalsVisibleTo proven by the green
  internal-proxy tests; release build has zero warnings.
- README examples use real signatures; ci.yml cs-parity job (regenerate vectors ->
  git diff --exit-code -> dotnet test -> pack, 3 OS) is sound.

## Scope check

The csharp/ package plus ADR/plan match plan slices 1-4. The worktree ALSO carries
uncommitted changes to .github/workflows/ci.yml, .github/workflows/release.yml,
.gitignore, CHANGELOG.md, README.md, README_PYPI.md, and site/* (plan slices 5-6)
that were not in this review's listed file set — ci.yml was skimmed (sound);
release.yml and the site/README edits were NOT reviewed in depth and should be
covered before commit.

## Re-review — 2026-07-28 (same day, post-fix)

All findings were addressed by the builder; every fix was RE-VERIFIED BY
EXECUTION with the same paired C#/Python probe harness (still run entirely
under de-DE culture) plus the new coverage the fixes demanded.

~~~text
$ dotnet test csharp/Contexel.Tests/Contexel.Tests.csproj --nologo
Passed!  - Failed: 0, Passed: 39, Skipped: 0, Total: 39   (was 36; +3 new regression tests)
$ cd ts && npm test
pass 41  fail 0                                            (new substring-mode vector test included)
$ python -m pytest <the 7 git-tracked test files> -q
66 passed
$ sha256sum parity/vectors.json ; python parity/generate_vectors.py ; sha256sum parity/vectors.json
8adcf91b...f87bc0  (identical before/after — regeneration is byte-stable, incl. new rescore_substring vector)
~~~

Note: the full-repo pytest also runs tests/test_doctrine_dashboard.py, an
UNTRACKED local file (git ls-files: absent) that fails on a missing local
artifact (docs/contracts/doctrine-control-room.openapi.json — directory does
not exist and is not tracked). Pre-existing local-environment issue,
unrelated to this task; the 7 tracked test files are all green.

Probe results after the fixes (paired against the Python canon):

~~~text
Finding 1 (large longs):
  allowlist 2^53+1 vs [2^53 long]       C# kept 0 == Python 0   (was 1)
  allowlist 2^53+1 vs [9007199254740992.0] C# kept 0 == Python 0   (was 1)
  allowlist 2^53 long vs [9007199254740992.0] C# kept 1 == Python 1  (collapse preserved)
  allowlist 9007199254740992.0 vs [2^53 long] C# kept 1 == Python 1
  rank desc [.992, .993]                C# first .993 == Python  (was .992)
  PyEqKey(1L) == PyEqKey(1.0) == PyEqKey(true) == "num:1"        (Python 1 == 1.0 == True kept)
  NEW CompareNumbers/CompareLongDouble paired fuzz: 100,154 long-vs-double
  pairs (incl. 2^53/2^63 boundaries, fractions, negatives, long.Max/MinValue,
  full-range random) -> 0 sign mismatches vs Python <,==,>
Finding 2 (substring overlap):
  Rescore("aaaa","aa",substring)        C# 0.16439 == Python 0.16439 (was 0.191788)
  vector edges.rescore_substring row scores [0.268574, 0.313336, 0.611005]
  asserted green in BOTH the C# and TS suites; ts/src/stages.ts:255 fixed too
Finding 3 (-0.0):
  dedupe [0.0, -0.0]                    C# 1 == Python 1  (was 2)
  allowlist -0.0 vs [0]                 C# kept 1 == Python 1  (was 0)
Finding 4 (PyRound guard):
  NEW band sweep: 25,004 cases in [1e15, 2^53) nd 0..3 plus above-2^53
  -> 0 mismatches (was 496 at nd=0); original 139,020-case fuzz now
  0 value mismatches total (18,993 sign-of-zero-only = ADR margin)
Finding 5 (lone surrogates):
  PythonJson({x+D800, x+D801}) len 18 == Python json.dumps len 18 (was InvalidOperationException)
  Tokens.Count("ab(U+D800)cd") = 2 == Python max(1, ceil(5/4)) = 2 (was 1)
Finding 6: margin added to ADR-002 §7 (reduction -0, long envelope, lone surrogates) — read, accurate.
Unchanged-good: pyfloat 200,033 cases 0 diff; pystr/pyrepr 30 values 0 diff;
IsHeuristic matrix unchanged; nested async Scoped + Trace nesting unchanged;
fingerprint 991efabe2a1a8d7b unchanged across processes (fixes did not
disturb the policy hash); all still under de-DE.
~~~

The owed reviews of the remaining worktree slices (release.yml, README,
README_PYPI, site, .gitignore, CHANGELOG) are now done:

- .github/workflows/release.yml: cs-test (3-OS, canon-regenerated vectors +
  git diff --exit-code guard, SHA-pinned actions — consistent with repo
  convention); pypi-publish now gated on cs-test; nuget-publish (environment:
  nuget, minimal permissions, tag/version guard via sed on <Version>,
  dispatch = dry-run, --skip-duplicate, secret via env); nuget-smoke (3-OS,
  installs the PUBLISHED package with a 10x retry for index lag, runs a real
  quickstart with a real assertion). Sound.
- README.md / README_PYPI.md: NuGet badge, install rows, "Language parity"
  section — every claim matches what was verified here (int/float exactness,
  shared vectors, 3-OS gates). Accurate.
- site/getting-started.html: install row + ADR-002 link — accurate.
- .gitignore: bin/, obj/, *.nupkg — correct.
- CHANGELOG.md: C# package entry accurate.

## New findings from the re-review

| # | Sev | Location | Finding | Suggested fix | Resolution |
|---|-----|----------|---------|---------------|------------|
| 11 | [MINOR] | CHANGELOG.md (Unreleased) | The TS substring-mode fix changes published npm behavior (match="substring" scores change for self-bordered terms) but has NO changelog entry — only the C# addition is recorded. Definition of Done: changelog updated where behavior changed. | Add a Fixed entry under Unreleased: substring-mode rescore now counts non-overlapping occurrences like Python str.count (affects ts + csharp). | open |
| 12 | [NIT] | site/index.html:149-154 | The "Supply chain" card still says "Attested dual releases" / "One human-created tag ships both packages" — the neighboring card was updated to three languages; this one was missed. | "triple releases" / "all three packages" + mention NuGet. | open |
| 13 | [NIT] | csharp/Contexel/PyCompat.cs:276 | PLAUSIBLE (not executable here — x64 host): the round-trip check (long)(double)l casts an out-of-range double when (double)l rounds up to 2^63 (only l near long.MaxValue). On net8.0 x64 the cast yields long.MinValue (verified here: PyEqKey(long.MaxValue) = "int:9223372036854775807", correct); on ARM64 (macos-latest CI) net8.0 saturates to long.MaxValue, so PyEqKey(long.MaxValue) would key "num:9.223372036854776E+18" and falsely equal the double 9.2233720368547758E18, which Python distinguishes. One value, one platform, extreme envelope edge. | Bound-check before casting: route l to the exact "int:" path when (double)l >= 9.2233720368547758E18. | open |
| 14 | [NIT] | .github/workflows/release.yml (nuget-smoke) | If all 10 dotnet-add-package retries fail, the install step still exits 0 (loop falls through after sleep); the failure only surfaces one step later as a compile error in dotnet run. Works, but the step name lies about where it failed. | Track success in a flag and exit 1 after the loop. | open |

## Verdict

- [x] Pass (0 BLOCKER, both MAJORs fixed and re-verified by execution)
- [ ] Return to build

**APPROVE-WITH-NITS.** All ten original findings are resolved: the two
MAJORs (large-long collapse, substring overlap) are fixed in C# AND TS,
pinned by a new Python-generated golden vector plus three new regression
tests, and re-verified by 125k fresh paired-fuzz cases with zero
in-envelope mismatches. The parity surface is the strongest of the three
ports: 465k+ total paired probe cases against the CPython canon, all green
under a hostile culture. Remaining items are documentation-grade: finding
11 (CHANGELOG entry for the TS behavior fix) should land before the release
tag that ships these packages; 12-14 are author's-call polish.
