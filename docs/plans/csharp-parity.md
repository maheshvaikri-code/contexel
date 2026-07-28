# G2 Plan — C# parity (Class L; brief = ADR-002's Decision section)

1. `csharp/Contexel/Contexel.csproj` (PackageId Contexel, net8.0, zero
   deps, README + license packed) + sources mirroring the TS module map:
   `PyCompat.cs` (pyFloat/pyRound/pyStr/pyRepr/pyEqKey/code-point
   helpers/rstrip), `Tokens.cs` (code-point counting, canonical
   Python-json serializer, AsyncLocal scoped overlay), `Trace.cs`
   (Trace/Audit/Traced), `Stages.cs` (8 stages + merge, quarantine
   extend-by-default semantics incl. guards), `Pipeline.cs`
   (stage descriptors + sha256[:16] fingerprint), `Shaped.cs`.
2. `csharp/Contexel.Tests/` (xunit): `VectorData.cs` — loads
   `parity/vectors.json` preserving long-vs-double from raw text;
   `ParityTests.cs` — every stage vector, contract, audit (policies
   excluded), serializer string equality, token counts, all edge
   vectors; `BehaviorTests.cs` — async Shaped, Scoped isolation +
   nesting, quarantine guards, typed dedupe (incl. 1 vs 1.0 — C#
   exceeds TS here), rank TypeError-equivalents.
3. `dotnet test` green locally with real output (G5 evidence).
4. G4: code-reviewer subagent over the csharp/ diff (line-by-line vs
   Python canon; probe divergences by execution).
5. CI: `cs-parity` job (3 OS) — regenerate vectors, diff, dotnet test.
   Release: `nuget-publish` (needs pypi-publish like npm; NUGET_API_KEY
   secret = §5 user setup) + 3-OS `nuget-smoke` quickstart.
6. Docs: csharp/README.md (NuGet-facing), main README "TypeScript
   parity" section generalized to language parity incl. C#, CHANGELOG
   [Unreleased], site getting-started install row.
