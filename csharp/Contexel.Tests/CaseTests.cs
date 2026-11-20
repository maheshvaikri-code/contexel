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
        ["id", "stage", "args", "input", "expect", "expect_error", "strict"];

    // One table of the allowed argument names (snake_case, as in the JSON)
    // per stage kind. A typo'd option must fail loudly — never be silently
    // ignored or defaulted (Slice 1 review, mandatory).
    private static readonly Dictionary<string, HashSet<string>> ArgNames = new()
    {
        ["select"] = ["fields"],
        ["dedupe"] = ["key"],
        ["allowlist"] = ["field", "allowed"],
        ["quarantine"] = ["fields", "patterns", "action", "into", "replace_patterns"],
        ["rescore"] = ["query", "fields", "into", "proximity", "match"],
        ["rank"] = ["by", "desc"],
        ["truncate_field"] = ["field", "max_tokens"],
        ["trim_to_budget"] = ["max_tokens", "min_records"],
        ["merge"] = ["schema", "dedupe_key"],
        ["pipeline"] = ["stages"],
        ["shaped"] = ["stages"],
        ["trace_report"] = ["stages", "id_field"],
    };

    private static readonly HashSet<string> NestingKinds = ["pipeline", "shaped", "trace_report"];
    private static readonly HashSet<string> SpecKeys = ["stage", "args"];

    /// <summary>Reject an unknown option name in a case's args and, for
    /// pipeline/shaped/trace_report, in every nested stage spec.</summary>
    internal static void ValidateArgs(string kind, Rec args, string where)
    {
        if (!ArgNames.TryGetValue(kind, out var allowed))
            throw new ArgumentException($"{where}: unknown stage {kind}");
        foreach (var key in args.Keys)
            if (!allowed.Contains(key))
                throw new ArgumentException(
                    $"{where}: unknown argument '{key}' for stage {kind}");
        if (!NestingKinds.Contains(kind)) return;
        var specs = AsList(args["stages"]);
        for (int i = 0; i < specs.Count; i++)
        {
            var spec = AsRec(specs[i]);
            string at = $"{where}.stages[{i}]";
            foreach (var key in spec.Keys)
                if (!SpecKeys.Contains(key))
                    throw new ArgumentException($"{at}: unknown key '{key}'");
            var inner = (string)spec["stage"]!;
            if (!RecordStages.Contains(inner))
                throw new ArgumentException($"{at}: unknown stage {inner}");
            ValidateArgs(inner, AsRec(spec["args"]), at);
        }
    }

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

    // a JSON null input reaches the stage as null (not-a-list case); a null
    // item stays a null item (not-a-mapping case)
    private static Records Input(Rec c) => c["input"] switch
    {
        "$fixture" => Fixture,
        null => null!,
        var v => AsRecords(v),
    };

    // One adapter per record stage: JSON args -> the port's call shape.
    private static Records RunStage(string kind, Rec a, Records r) => kind switch
    {
        "select" => Stages.Select(r, Strs(a["fields"])),
        "dedupe" => Stages.Dedupe(r, OptStrs(a, "key")),
        "allowlist" => a["allowed"] is string one
            ? Stages.Allowlist(r, (string)a["field"]!, one)
            : Stages.Allowlist(r, (string)a["field"]!, AsList(a["allowed"])),
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

    /// <summary>The call under test: strict cases run inside strict mode.</summary>
    internal static object? Execute(Rec c)
    {
        var kind = (string)c["stage"]!;
        ValidateArgs(kind, AsRec(c["args"]), (string)c["id"]!);
        if (!(c.TryGetValue("strict", out var s) && s is true)) return Run(c);
        using (Strict.Begin()) return Run(c);
    }

    /// <summary>Replay one case: an <c>expect</c> case must equal the canon's
    /// output; an <c>expect_error</c> case must throw the port's contexel
    /// exception with that code — any other exception (or none) fails.</summary>
    internal static void AssertCase(Rec c)
    {
        var id = (string)c["id"]!;
        foreach (var key in c.Keys)
            Assert.True(AllowedKeys.Contains(key), $"case {id} has unsupported key {key}");
        if (c.TryGetValue("strict", out var strictValue))
            Assert.True(strictValue is bool, $"case {id}: strict must be a boolean");
        bool hasExpect = c.ContainsKey("expect"), hasError = c.ContainsKey("expect_error");
        Assert.True(hasExpect != hasError, $"case {id} needs exactly one of expect / expect_error");
        if (hasExpect)
        {
            AssertDeepEqual(c["expect"], Execute(c), id);
            return;
        }
        string code = (string)AsRec(c["expect_error"])["code"]!;
        object? result;
        try { result = Execute(c); }
        catch (ContexelException e)
        {
            Assert.True(e.Code == code,
                $"case {id}: expected error {code}, got {e.Code} ({e.Message})");
            return;
        }
        throw new Xunit.Sdk.XunitException(
            $"case {id}: expected error {code}, but the call returned {Show(result)}");
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
        AssertCase(c);
    }
}
