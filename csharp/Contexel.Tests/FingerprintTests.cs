using Xunit;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>Policy fingerprints (ADR-008, brief AC 29-30). Mirrors the policy
/// tests in tests/test_audit_truth.py and the baseline in
/// tests/test_fingerprint_golden.py. Fingerprints are language-local
/// (ADR-002): these values are C#'s own.</summary>
public class FingerprintTests
{
    // A NAMED method: a delegate fingerprints by its method name, and a
    // compiler-generated lambda name would change whenever this file does.
    private static Records Bare(Records records) => records;

    private sealed class Opaque
    {
        public override string ToString() => "Opaque";
    }

    private static Stage Named(string name, Rec? parameters = null) =>
        new(name, Bare, parameters);

    private static List<object?> L(params object?[] items) => [.. items];

    // --- the recorded baseline (written before the audit-truthfulness change)
    // Do not regenerate these values to make a test pass: a change here is a
    // behavior change that needs an ADR.

    public static IEnumerable<object[]> Shapes() =>
    [
        ["contract", "b9c896d3ae7472ab"],
        ["primitives", "313a7dd4b4762dc5"],
        ["list_of_mixed_scalars_and_null", "7c1c9be15a644f14"],
        ["object_with_nesting", "b9ac84206a283de7"],
        ["opaque_object", "704c1b356f69617b"],
        ["named_delegate", "ff5201ec8ea5cd37"],
        ["empty_pipeline", "e3b0c44298fc1c14"],
    ];

    private static Pipeline Build(string shape) => shape switch
    {
        "contract" => new Pipeline(
            Named("allowlist", new Rec { ["field"] = "source", ["allowed"] = L("repo", "docs") }),
            Named("quarantine", new Rec { ["fields"] = L("snippet") }),
            Named("select", new Rec { ["fields"] = L("path", "line", "source", "snippet") }),
            Named("dedupe", new Rec { ["key"] = L("path", "line") }),
            Named("rescore", new Rec
            {
                ["query"] = "exponential backoff jitter", ["fields"] = L("snippet", "path"),
            }),
            Named("truncate_field", new Rec { ["field"] = "snippet", ["max_tokens"] = 12L }),
            Named("rank", new Rec { ["by"] = "score", ["desc"] = true }),
            Named("trim_to_budget", new Rec { ["max_tokens"] = 150L })),
        "primitives" => new Pipeline(
            Named("select", new Rec { ["fields"] = L("a", "b") }),
            Named("dedupe", new Rec { ["key"] = "a" }),
            Named("rank", new Rec { ["by"] = "score", ["desc"] = true }),
            Named("trim_to_budget", new Rec { ["max_tokens"] = 100L })),
        "list_of_mixed_scalars_and_null" => new Pipeline(
            Named("allowlist", new Rec { ["field"] = "s", ["allowed"] = L("x", null, 1L, 2.5, true) }),
            Named("quarantine", new Rec { ["fields"] = L("snippet"), ["action"] = "drop" })),
        "object_with_nesting" => new Pipeline(
            Named("annotate", new Rec
            {
                ["mapping"] = new Rec { ["b"] = L(1L, null, new Rec { ["z"] = 2.5 }), ["k"] = "v" },
                ["empty"] = new Rec(),
                ["label"] = "m",
            })),
        "opaque_object" => new Pipeline(
            Named("annotate", new Rec { ["marker"] = new Opaque(), ["n"] = 3L })),
        "named_delegate" => new Pipeline(
            Named("annotate", new Rec { ["key"] = (Func<Records, Records>)Bare, ["desc"] = false })),
        "empty_pipeline" => new Pipeline(),
        _ => throw new ArgumentException(shape),
    };

    [Theory]
    [MemberData(nameof(Shapes))]
    public void FingerprintMatchesTheRecordedBaseline(string shape, string expected) =>
        Assert.Equal(expected, Build(shape).Fingerprint);

    [Fact]
    public void ParameterOrderDoesNotChangeTheFingerprint()
    {
        var a = new Pipeline(Named("t", new Rec { ["field"] = "s", ["max_tokens"] = 5L }));
        var b = new Pipeline(Named("t", new Rec { ["max_tokens"] = 5L, ["field"] = "s" }));
        Assert.Equal(a.Fingerprint, b.Fingerprint);
    }

    // --- AC 29: what the fingerprint covers ---------------------------------

    private static string Fp(params Stage[] stages) => new Pipeline(stages).Fingerprint;

    private static Stage WithParam(string key, object? value) =>
        Named("annotate", new Rec { [key] = value });

    [Fact]
    public void FingerprintDiffersForSetContents() =>
        Assert.NotEqual(Fp(WithParam("allowed", new HashSet<string> { "a" })),
                        Fp(WithParam("allowed", new HashSet<string> { "b" })));

    [Fact]
    public void TheFingerprintOfASetIgnoresInsertionOrderAndSetType()
    {
        var ab = Fp(WithParam("s", new HashSet<string> { "a", "b", "c" }));
        var ba = Fp(WithParam("s", new HashSet<string> { "c", "a", "b" }));
        var sorted = Fp(WithParam("s", new SortedSet<string> { "b", "c", "a" }));
        Assert.Equal(ab, ba);
        Assert.Equal(ab, sorted);
    }

    [Fact]
    public void TheFingerprintOfASetIsNotThatOfAListOrADictionary()
    {
        var forms = new object?[]
        {
            new HashSet<string> { "a" }, L("a"), new Rec { ["a"] = 1L }, new Rec(),
            new HashSet<string>(),
        }.Select(v => Fp(WithParam("v", v))).ToList();
        Assert.Equal(forms.Count, forms.Distinct().Count());
    }

    [Fact]
    public void ASetNestedInAListOrADictionaryIsCoveredToo()
    {
        Assert.NotEqual(
            Fp(WithParam("v", L(1L, new HashSet<long> { 1, 2 }))),
            Fp(WithParam("v", L(1L, new HashSet<long> { 1, 3 }))));
        Assert.NotEqual(
            Fp(WithParam("v", new Rec { ["k"] = new HashSet<string> { "x" } })),
            Fp(WithParam("v", new Rec { ["k"] = new HashSet<string> { "y" } })));
    }

    private static Stage Select(string field) =>
        new("select", r => Stages.Select(r, new[] { field }),
            new Rec { ["fields"] = L(field) });

    private static Stage Outer(Pipeline inner) => new("inner", inner.Run);

    [Fact]
    public void FingerprintDiffersForNestedPipelines()
    {
        var innerA = new Pipeline(Select("a"));
        var innerB = new Pipeline(Select("b"));
        var sameAsA = new Pipeline(Select("a"));
        var dedupe = Named("dedupe", new Rec { ["key"] = "a" });
        Assert.NotEqual(Fp(Outer(innerA), dedupe), Fp(Outer(innerB), dedupe));
        Assert.Equal(Fp(Outer(innerA), dedupe), Fp(Outer(sameAsA), dedupe));
    }

    [Fact]
    public void ANestedPipelineWithItsOwnParametersStillContributesItsFingerprint()
    {
        var parameters = new Rec { ["note"] = "x" };
        Assert.NotEqual(
            Fp(new Stage("inner", new Pipeline(Select("a")).Run, parameters)),
            Fp(new Stage("inner", new Pipeline(Select("b")).Run, parameters)));
    }

    [Fact]
    public void ANestedPipelineStillRunsItsStages()
    {
        var inner = new Pipeline(Select("a"));
        var outer = new Pipeline(Outer(inner),
            new Stage("dedupe", r => Stages.Dedupe(r, "a"), new Rec { ["key"] = "a" }));
        Records input = [new Rec { ["a"] = 1L, ["b"] = 2L }, new Rec { ["a"] = 1L }];
        var result = outer.Run(input);
        Assert.Single(result);
        Assert.Equal(1L, result[0]["a"]);
    }

    [Fact]
    public void ANestedPipelineWrappedInALambdaIsNotDetected()
    {
        // documented limit: only a stage built from `inner.Run` itself is
        // recognised; a lambda that calls it is opaque, like any other lambda
        var innerA = new Pipeline(Select("a"));
        var innerB = new Pipeline(Select("b"));
        Assert.Equal(Fp(new Stage("inner", r => innerA.Run(r))),
                     Fp(new Stage("inner", r => innerB.Run(r))));
    }

    // --- AC 30 (as far as C# can promise it) ---------------------------------

    [Fact]
    public void ParametersChangedAfterConstructionDoNotChangeTheFingerprint()
    {
        var allowed = L("a");
        var pipe = new Pipeline(Named("allowlist", new Rec { ["allowed"] = allowed }));
        var before = pipe.Fingerprint;
        allowed.Add("b");
        Assert.Equal(before, pipe.Fingerprint);
    }

    [Fact]
    public void PipelineCopiesItsListOfStages()
    {
        var stages = new List<Stage> { Select("a") };
        var pipe = new Pipeline(stages);
        var before = pipe.Fingerprint;
        stages.Add(Select("b"));
        stages[0] = Select("b");
        Records input = [new Rec { ["a"] = 1L, ["b"] = 2L }];
        var result = pipe.Run(input);
        Assert.Equal(new[] { "a" }, result[0].Keys.ToArray());
        Assert.Equal(before, pipe.Fingerprint);
    }
}
