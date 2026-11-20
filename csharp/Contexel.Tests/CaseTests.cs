using Xunit;
using static Contexel.Tests.VectorData;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>
/// Data-driven parity cases (ADR-007): replay every case in vectors.json
/// "cases" through one adapter per stage and compare with the Python canon.
/// Adding a case never touches this file.
/// </summary>
public class CaseTests
{
    private static readonly HashSet<string> AllowedKeys =
        ["id", "stage", "args", "input", "expect"];

    public static IEnumerable<object[]> CaseIds() =>
        AsList(Vectors["cases"]).Select(c => new object[] { (string)AsRec(c)["id"]! });

    private static string[] Strs(object? v) => v switch
    {
        string s => [s],
        List<object?> l => l.Select(x => (string)x!).ToArray(),
        _ => throw new ArgumentException("expected a string or a list of strings"),
    };

    private static object? OptStrs(Rec a, string key) =>
        a.TryGetValue(key, out var v) && v is not null ? Strs(v) : null;

    private static bool Flag(Rec a, string key, bool dflt) =>
        a.TryGetValue(key, out var v) ? (bool)v! : dflt;

    private static string Str(Rec a, string key, string dflt) =>
        a.TryGetValue(key, out var v) ? (string)v! : dflt;

    private static Records Input(Rec c) =>
        c["input"] is "$fixture" ? Fixture : AsRecords(c["input"]);

    // One adapter per record stage: JSON args -> the port's call shape.
    private static Records RunStage(string kind, Rec a, Records r) => kind switch
    {
        "select" => Stages.Select(r, Strs(a["fields"])),
        "dedupe" => Stages.Dedupe(r, OptStrs(a, "key")),
        "allowlist" => Stages.Allowlist(r, (string)a["field"]!, AsList(a["allowed"])),
        "quarantine" => Stages.Quarantine(r, OptStrs(a, "fields"), OptStrs(a, "patterns"),
            Str(a, "action", "drop"), Str(a, "into", "quarantined"),
            Flag(a, "replace_patterns", false)),
        "rescore" => Stages.Rescore(r, a["query"] is string q ? q : Strs(a["query"]),
            OptStrs(a, "fields"), Str(a, "into", "score"), Flag(a, "proximity", true),
            Str(a, "match", "word")),
        "rank" => Stages.Rank(r, (string)a["by"]!, Flag(a, "desc", true)),
        "truncate_field" => Stages.TruncateField(r, (string)a["field"]!, (int)(long)a["max_tokens"]!),
        "trim_to_budget" => Stages.TrimToBudget(r, (int)(long)a["max_tokens"]!,
            minRecords: a.TryGetValue("min_records", out var m) ? (int)(long)m! : 0),
        _ => throw new ArgumentException($"unknown stage {kind}"),
    };

    private static readonly HashSet<string> RecordStages =
        ["select", "dedupe", "allowlist", "quarantine", "rescore", "rank",
         "truncate_field", "trim_to_budget"];

    private static Stage Bind(Rec spec)
    {
        var kind = (string)spec["stage"]!;
        var args = AsRec(spec["args"]);
        return new Stage(kind, r => RunStage(kind, args, r), args);
    }

    private static Pipeline Build(Rec args) =>
        new(AsList(args["stages"]).Select(s => Bind(AsRec(s))).ToArray());

    private static object? Run(Rec c)
    {
        var kind = (string)c["stage"]!;
        var args = AsRec(c["args"]);
        if (RecordStages.Contains(kind)) return RunStage(kind, args, Input(c));
        switch (kind)
        {
            case "merge":
                return Stages.Merge(AsList(c["input"]).Select(AsRecords),
                    args.TryGetValue("schema", out var sc) && sc is not null
                        ? AsRec(sc).ToDictionary(kv => kv.Key,
                            kv => (object)(kv.Value is string s ? s : Strs(kv.Value)))
                        : null,
                    args.TryGetValue("dedupe_key", out var dk) ? (string?)dk : null);
            case "pipeline":
                return Build(args).Run(Input(c));
            case "shaped":
            {
                var records = Input(c);
                return Shaped.Wrap(Build(args), () => records)();
            }
            case "trace_report":
            {
                using var t = Trace.Begin(args.TryGetValue("id_field", out var f) ? (string?)f : null);
                Build(args).Run(Input(c));
                return t.Report();
            }
            default:
                throw new ArgumentException($"unknown case kind {kind}");
        }
    }

    [Fact]
    public void CasesSectionIsPresentAndComplete()
    {
        var cases = AsList(Vectors["cases"]);
        Assert.NotEmpty(cases); // a runner must never pass vacuously
        Assert.Equal((long)AsRec(Vectors["_meta"])["case_count"]!, (long)cases.Count);
        var ids = cases.Select(c => (string)AsRec(c)["id"]!).ToList();
        Assert.Equal(ids.Count, ids.Distinct().Count());
    }

    [Theory]
    [MemberData(nameof(CaseIds))]
    public void CaseMatchesPython(string id)
    {
        var c = AsList(Vectors["cases"]).Select(AsRec).Single(x => (string)x["id"]! == id);
        foreach (var key in c.Keys)
            Assert.True(AllowedKeys.Contains(key), $"case {id} has unsupported key {key}");
        AssertDeepEqual(c["expect"], Run(c), id);
    }
}
