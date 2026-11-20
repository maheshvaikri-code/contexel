using Xunit;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>Configuration validation (ADR-003): a misconfigured call always
/// throws a typed ConfigException — strict mode is not needed — and never
/// silently does something else. C# parameters are statically typed, so this
/// covers what the type system leaves open: negatives, empty lists, an
/// unknown match string, element types inside a boxed object (fields, key,
/// query, patterns) and null. Mirrors tests/test_config_validation.py.</summary>
public class ConfigTests
{
    private static Records Recs() =>
    [
        new Rec { ["a"] = "x y", ["n"] = 1L },
        new Rec { ["a"] = "y z", ["n"] = 2L },
    ];

    private static ConfigException Raised(Action call) =>
        Assert.Throws<ConfigException>(call);

    private static readonly string[] A = ["a"];

    [Theory]
    [InlineData("fuzzy")]
    [InlineData("WORD")]
    [InlineData("")]
    [InlineData(null)]
    public void RescoreUnknownMatchThrows(string? bad)
    {
        var e = Raised(() => Stages.Rescore(Recs(), "x", A, match: bad!));
        Assert.Equal(("config.invalid_value", "rescore", "match"), (e.Code, e.Stage, e.Param));
        Assert.NotEmpty(Stages.Rescore(Recs(), "x", A, match: "word"));
        Assert.NotEmpty(Stages.Rescore(Recs(), "x", A, match: "substring"));
    }

    [Fact]
    public void RescoreMatchStemIsReservedUntilTheStemmerShips()
    {
        var e = Raised(() => Stages.Rescore(Recs(), "x", A, match: "stem"));
        Assert.Equal("config.invalid_value", e.Code);
        Assert.Contains("not available yet", e.Message);
    }

    [Fact]
    public void RescoreEmptyFieldsThrows()
    {
        foreach (object empty in new object[] { Array.Empty<string>(), new List<string>() })
        {
            var e = Raised(() => Stages.Rescore(Recs(), "x", empty));
            Assert.Equal(("config.empty", "fields"), (e.Code, e.Param));
        }
    }

    public static IEnumerable<object?[]> WrongTypedRescore() =>
    [
        [null, A, "score", "query"],
        [5, A, "score", "query"],
        ["x", 5, "score", "fields"],
        ["x", new object?[] { 1L }, "score", "fields"],
        ["x", null, null, "into"],
    ];

    [Theory]
    [MemberData(nameof(WrongTypedRescore))]
    public void RescoreWrongTypedParametersThrow(object? query, object? fields, string? into, string param)
    {
        // fields == null means "the default" in C#, so the null-into row passes a valid field list
        var f = fields ?? A;
        var e = Raised(() => Stages.Rescore(Recs(), query!, f, into!));
        Assert.Equal(("config.invalid_value", param), (e.Code, e.Param));
    }

    [Fact]
    public void RescoreQueryElementsMustBeStrings()
    {
        // a sequence query is accepted only when EVERY element is a non-null
        // string: str() of a stray element used to be scored silently
        object?[][] bad =
        [
            [1L], [null], ["x", 2L], ["x", null], [new Rec()], [new List<object?> { "x" }],
        ];
        foreach (var query in bad)
        {
            var e = Raised(() => Stages.Rescore(Recs(), query, A));
            Assert.Equal(("config.invalid_value", "query"), (e.Code, e.Param));
            Assert.Contains("query must contain only strings", e.Message);
        }
        Assert.NotEmpty(Stages.Rescore(Recs(), new[] { "x", "y" }, A));
        Assert.NotEmpty(Stages.Rescore(Recs(), new List<object?> { "x", "y" }, A));
        Assert.NotEmpty(Stages.Rescore(Recs(), "x y", A));
        // an empty sequence stays valid: it scores everything 0.0
        Assert.All(Stages.Rescore(Recs(), Array.Empty<string>(), A), r => Assert.Equal(0.0, r["score"]));
    }

    /// <summary>A sequence that can be enumerated only once: a second
    /// enumeration yields nothing (a database cursor, a stream).</summary>
    private sealed class OneShot(string[] items) : IEnumerable<string>
    {
        public int Enumerations { get; private set; }

        public IEnumerator<string> GetEnumerator()
        {
            Enumerations++;
            return (Enumerations == 1 ? items : []).AsEnumerable().GetEnumerator();
        }

        System.Collections.IEnumerator System.Collections.IEnumerable.GetEnumerator() =>
            GetEnumerator();
    }

    [Fact]
    public void RescoreEnumeratesALazyQueryExactlyOnce()
    {
        var oneShot = new OneShot(["x", "y"]);
        var scored = Stages.Rescore(Recs(), oneShot, A);
        Assert.Equal(1, oneShot.Enumerations);
        VectorData.AssertDeepEqual(
            Stages.Rescore(Recs(), new List<string> { "x", "y" }, A)
                .Select(r => (object?)r).ToList(),
            scored, "one-shot query");
        Assert.Contains(scored, r => (double)r["score"]! > 0.0);
    }

    [Fact]
    public void RescoreRejectsBoolQueryElements()
    {
        object?[][] bad = [[true], ["x", false]];
        foreach (var query in bad)
        {
            var e = Raised(() => Stages.Rescore(Recs(), query, A));
            Assert.Equal(("config.invalid_value", "query"), (e.Code, e.Param));
            Assert.Contains("query must contain only strings", e.Message);
        }
    }

    [Fact]
    public void ConfigurationErrorsThrowEvenWithNoRecordsAndNoStrictMode()
    {
        Assert.Equal("config.invalid_value",
            Raised(() => Stages.Rescore([], "x", match: "fuzzy")).Code);
        Assert.Equal("config.invalid_value", Raised(() => Stages.TrimToBudget([], -1)).Code);
        Assert.Equal("config.empty",
            Raised(() => Stages.Quarantine([], fields: Array.Empty<string>())).Code);
        // an empty query is not a configuration error: it scores everything 0.0
        var scored = Stages.Rescore(Recs(), "", A);
        VectorData.AssertDeepEqual(
            Recs().Select(r => (object?)new Rec(r) { ["score"] = 0.0 }).ToList(), scored, "empty query");
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(-100)]
    [InlineData(int.MinValue)]
    public void MaxTokensMustBeANonNegativeInteger(int bad)
    {
        foreach (Action call in new Action[]
        {
            () => Stages.TrimToBudget(Recs(), bad),
            () => Stages.TruncateField(Recs(), "a", bad),
        })
        {
            var e = Raised(call);
            Assert.Equal(("config.invalid_value", "maxTokens"), (e.Code, e.Param));
            Assert.IsAssignableFrom<ArgumentException>(e);
        }
    }

    [Fact]
    public void MaxTokensZeroReturnsEmptyAndStaysValid()
    {
        Assert.Empty(Stages.TrimToBudget(Recs(), 0));
        Assert.NotEmpty(Stages.TruncateField(Recs(), "a", 0)); // clips to the minimum, never throws
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(int.MinValue)]
    public void MinRecordsMustBeANonNegativeInteger(int bad)
    {
        var e = Raised(() => Stages.TrimToBudget(Recs(), 10, minRecords: bad));
        Assert.Equal("minRecords", e.Param);
        Assert.Single(Stages.TrimToBudget(Recs(), 0, minRecords: 1));
    }

    [Fact]
    public void TruncateFieldFieldAndSuffixMustBeStrings()
    {
        Assert.Equal("field", Raised(() => Stages.TruncateField(Recs(), null!, 10)).Param);
        Assert.Equal("suffix", Raised(() => Stages.TruncateField(Recs(), "a", 10, suffix: null!)).Param);
    }

    public static IEnumerable<object?[]> BadFields() =>
    [
        [null],
        [5],
        [1.5],
        [new object?[] { "a", 1L }],
        [new Rec { ["a"] = 1L }],
        [new HashSet<string> { "a" }],
        [new List<int> { 1 }],
    ];

    [Theory]
    [MemberData(nameof(BadFields))]
    public void FieldsMustBeAStringOrAListOfStrings(object? bad)
    {
        var calls = new List<Action> { () => Stages.Select(Recs(), bad!) };
        // quarantine and rescore treat a null "fields" as the default, so a
        // null only applies to select
        if (bad is not null)
        {
            calls.Add(() => Stages.Quarantine(Recs(), fields: bad));
            calls.Add(() => Stages.Rescore(Recs(), "x", fields: bad));
        }
        foreach (var call in calls)
        {
            var e = Raised(call);
            Assert.Equal(("config.invalid_value", "fields"), (e.Code, e.Param));
        }
    }

    [Fact]
    public void AStringAnArrayAListAndABoxedListAreValidFieldsAndABareStringIsOneField()
    {
        var expected = Recs().Select(r => (object?)new Rec { ["a"] = r["a"] }).ToList();
        VectorData.AssertDeepEqual(expected, Stages.Select(Recs(), "a"), "string");
        VectorData.AssertDeepEqual(expected, Stages.Select(Recs(), new[] { "a" }), "array");
        VectorData.AssertDeepEqual(expected, Stages.Select(Recs(), new List<string> { "a" }), "list");
        VectorData.AssertDeepEqual(expected, Stages.Select(Recs(), new List<object?> { "a" }), "boxed list");
        // select keeps an empty list valid; it just keeps nothing
        Assert.All(Stages.Select(Recs(), Array.Empty<string>()), r => Assert.Empty(r));
    }

    [Fact]
    public void DedupeKeyMustBeNullAStringOrAListOfStrings()
    {
        Assert.Equal("key", Raised(() => Stages.Dedupe(Recs(), 5)).Param);
        Assert.Equal("key", Raised(() => Stages.Dedupe(Recs(), new object?[] { "a", 1L })).Param);
        Assert.Equal(2, Stages.Dedupe(Recs(), null).Count);
        Assert.Equal(2, Stages.Dedupe(Recs(), "a").Count);
        Assert.Equal(2, Stages.Dedupe(Recs(), new[] { "a" }).Count);
    }

    [Fact]
    public void RankByIsValidated()
    {
        Assert.Equal("by", Raised(() => Stages.Rank(Recs(), (string)null!)).Param);
        Assert.Equal("by", Raised(() => Stages.Rank(Recs(), (Func<Rec, object?>)null!)).Param);
    }

    [Fact]
    public void RankAcceptsAFieldNameAndAKeyFunction()
    {
        Assert.Equal(new object?[] { 2L, 1L }, Stages.Rank(Recs(), "n").Select(r => r["n"]).ToArray());
        Assert.Equal(new object?[] { 1L, 2L },
            Stages.Rank(Recs(), r => r["n"], desc: false).Select(r => r["n"]).ToArray());
    }

    public static IEnumerable<object?[]> WrongTypedPatterns() =>
    [
        [5],
        [new object?[] { "ok", 5L }],
        [new Rec { ["a"] = 1L }],
    ];

    [Theory]
    [MemberData(nameof(WrongTypedPatterns))]
    public void QuarantineWrongTypedPatternsThrow(object patterns)
    {
        var e = Raised(() => Stages.Quarantine(Recs(), A, patterns));
        Assert.Equal(("config.invalid_value", "patterns"), (e.Code, e.Param));
    }

    [Fact]
    public void QuarantineANullIntoThrows()
    {
        var e = Raised(() => Stages.Quarantine(Recs(), A, into: null!));
        Assert.Equal(("config.invalid_value", "into"), (e.Code, e.Param));
    }

    [Fact]
    public void QuarantineActionIsValidated()
    {
        var e = Raised(() => Stages.Quarantine(Recs(), A, action: "allow"));
        Assert.Equal(("config.invalid_value", "action"), (e.Code, e.Param));
        Assert.Equal("config.invalid_value",
            Raised(() => Stages.Quarantine(Recs(), A, action: null!)).Code);
    }

    [Fact]
    public void EveryConfigurationErrorCarriesItsStageName()
    {
        var cases = new Dictionary<string, Action>
        {
            ["select"] = () => Stages.Select(Recs(), 5),
            ["dedupe"] = () => Stages.Dedupe(Recs(), 5),
            ["rank"] = () => Stages.Rank(Recs(), (string)null!),
            ["allowlist"] = () => Stages.Allowlist(Recs(), "a", (IEnumerable<object?>)null!),
            ["quarantine"] = () => Stages.Quarantine(Recs(), 5),
            ["rescore"] = () => Stages.Rescore(Recs(), null!),
            ["truncate_field"] = () => Stages.TruncateField(Recs(), "a", -1),
            ["trim_to_budget"] = () => Stages.TrimToBudget(Recs(), -1),
        };
        foreach (var (stage, call) in cases)
        {
            var e = Raised(call);
            Assert.Equal(stage, e.Stage);
            Assert.False(string.IsNullOrEmpty(e.Param));
            Assert.StartsWith(stage + ":", e.Message);
        }
    }

    [Fact]
    public void ConfigurationIsValidatedAfterTheStrictShapeCheck()
    {
        // both wrong: strict reports the shape (it runs first); lenient reports the config
        using (Strict.Begin())
            Assert.Throws<InputShapeException>(() => Stages.Select(null!, 5));
        Assert.Throws<ConfigException>(() => Stages.Select(Recs(), 5));
    }

    [Fact]
    public void ConfigurationErrorsAreRaisedInsideAnActiveTraceToo()
    {
        using var t = Trace.Begin(idField: "n");
        Assert.Throws<ConfigException>(() => Stages.TrimToBudget(Recs(), -1));
        Assert.Empty(t.Entries); // a failed stage records nothing
    }
}
