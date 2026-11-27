using System.Text;
using System.Text.Json;
using Xunit;
using static Contexel.Tests.VectorData;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;

/// <summary>
/// Differential fuzz (ADR-007, brief AC 36): replays the seeded corpus that
/// <c>python parity/generate_fuzz.py</c> wrote through the case runner of the shared
/// vectors (<see cref="CaseTests.AssertCase"/>) and compares every outcome with the
/// Python canon. <c>CONTEXEL_FUZZ_CASES</c> is the corpus path (relative to the
/// repository root, or absolute). Unset, the replay returns at once locally; in CI
/// (<c>CI</c> set) an unset variable fails, so the job cannot go green by testing
/// nothing.
/// </summary>
public class FuzzTests
{
    private const int MinCases = 1000, Shown = 20;

    private static string RepoRoot()
    {
        string? dir = AppContext.BaseDirectory;
        while (dir is not null && !File.Exists(Path.Combine(dir, "parity", "vectors.json")))
            dir = Path.GetDirectoryName(dir);
        return dir ?? throw new FileNotFoundException("repository root not found above the test directory");
    }

    /// <summary>The corpus, or null when the variable is unset and this is not CI.</summary>
    private static Rec? Corpus()
    {
        var configured = Environment.GetEnvironmentVariable("CONTEXEL_FUZZ_CASES");
        if (string.IsNullOrEmpty(configured))
        {
            Assert.False(!string.IsNullOrEmpty(Environment.GetEnvironmentVariable("CI")),
                "CONTEXEL_FUZZ_CASES is not set: generate the corpus and point the variable at it " +
                "(python parity/generate_fuzz.py --out parity/fuzz-corpus.json, then set " +
                "CONTEXEL_FUZZ_CASES=parity/fuzz-corpus.json)");
            return null;
        }
        using var doc = JsonDocument.Parse(File.ReadAllText(Path.GetFullPath(configured, RepoRoot())));
        return AsRec(Convert(doc.RootElement));
    }

    private static Rec Corrupted(Rec c)
    {
        var copy = new Rec(c);
        if (c.TryGetValue("expect_error", out var err))
            copy["expect_error"] = new Rec { ["code"] = (string)AsRec(err)["code"]! + ".wrong" };
        else
            copy["expect"] = c["expect"] switch
            {
                List<object?> l => new List<object?>(l) { new Rec { ["canary"] = 1L } },
                string s => s + "!",
                _ => new Rec { ["canary"] = 1L },
            };
        return copy;
    }

    [Fact]
    public void FuzzCorpusIsPresentAndComplete()
    {
        if (Corpus() is not { } corpus) return;
        var meta = AsRec(corpus["_meta"]);
        var cases = AsList(corpus["cases"]).Select(AsRec).ToList();
        Assert.True(cases.Count >= MinCases, $"only {cases.Count} cases (a replay must never pass vacuously)");
        Assert.True((long)meta["case_count"]! == cases.Count,
            $"case_count {meta["case_count"]} disagrees with the {cases.Count} cases in the array");
        var distinctIds = cases.Select(c => (string)c["id"]!).Distinct().Count();
        Assert.True(distinctIds == cases.Count, $"duplicate case ids: {cases.Count - distinctIds} repeated");
        var seen = cases.GroupBy(c => (string)c["stage"]!).ToDictionary(g => g.Key, g => (long)g.Count());
        var generated = AsRec(meta["kind_counts"]).ToDictionary(kv => kv.Key, kv => (long)kv.Value!);
        string Kinds(Dictionary<string, long> d) => string.Join(", ", d.OrderBy(kv => kv.Key).Select(kv => $"{kv.Key}={kv.Value}"));
        Assert.True(Kinds(generated) == Kinds(seen),
            $"the kinds replayed differ from the kinds generated: replayed [{Kinds(seen)}] vs generated [{Kinds(generated)}]");
        Assert.True(cases.Any(c => c.ContainsKey("expect_error")), "no error case in the corpus");
    }

    [Fact]
    public void EveryFuzzCaseMatchesPython()
    {
        if (Corpus() is not { } corpus) return;
        var seed = (long)AsRec(corpus["_meta"])["seed"]!;
        var cases = AsList(corpus["cases"]).Select(AsRec).ToList();
        var failures = new List<string>();
        foreach (var c in cases)
        {
            try { CaseTests.AssertCase(c); }
            catch (Exception e)
            {
                var lines = e.Message.Split('\n').Take(6).Select(l => l.TrimEnd('\r'));
                failures.Add($"{(string)c["id"]!}\n    {string.Join("\n    ", lines)}");
            }
        }
        if (failures.Count == 0) return;
        var index = long.Parse(failures[0].Split('\n')[0].Split('/')[2]);
        var shown = new StringBuilder();
        foreach (var f in failures.Take(Shown)) shown.AppendLine(f);
        throw new Xunit.Sdk.XunitException(
            $"{failures.Count} of {cases.Count} fuzz cases diverge from the canon. First {Math.Min(Shown, failures.Count)}:\n" +
            $"{shown}Reproduce one: python parity/generate_fuzz.py --seed {seed} --show {index}");
    }

    [Fact]
    public void TheReplayCanFailACorruptedExpectationIsRefused()
    {
        if (Corpus() is not { } corpus) return;
        var sample = AsList(corpus["cases"]).Select(AsRec).Take(300).ToList();
        Assert.True(sample.Count > 0, "the corpus has no cases to corrupt (a canary must never pass vacuously)");
        foreach (var c in sample)
            Assert.ThrowsAny<Exception>(() => CaseTests.AssertCase(Corrupted(c)));
    }
}
