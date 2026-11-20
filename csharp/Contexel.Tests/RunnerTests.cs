using Xunit;
using static Contexel.Tests.VectorData;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;

/// <summary>The case runner itself must not be able to pass vacuously or
/// ignore a typo: an unknown option name is rejected (top level and inside
/// nested pipeline/shaped/trace_report stage specs), an expect_error case
/// demands the right contexel code, and strict cases run in strict mode.</summary>
public class RunnerTests
{
    private static Rec Case(string stage, Rec args, object? input, params (string, object?)[] extra)
    {
        var c = new Rec { ["id"] = "t/case", ["stage"] = stage, ["args"] = args, ["input"] = input };
        foreach (var (k, v) in extra) c[k] = v;
        return c;
    }

    private static List<object?> Items(params object?[] items) => [.. items];

    private static Rec Spec(string stage, Rec args) => new() { ["stage"] = stage, ["args"] = args };

    private static Rec Err(string code) => new() { ["code"] = code };

    // ------------------------- unknown argument keys -------------------------

    [Fact]
    public void AnUnknownArgKeyAtTheTopLevelIsRejected()
    {
        // "feilds" is a typo of "fields": it must fail loudly, not default
        var c = Case("quarantine", new Rec { ["feilds"] = Items("a") }, Items(), ("expect", Items()));
        var e = Assert.Throws<ArgumentException>(() => CaseTests.AssertCase(c));
        Assert.Contains("feilds", e.Message);
    }

    [Theory]
    [InlineData("select", "field")]
    [InlineData("dedupe", "keys")]
    [InlineData("allowlist", "allow")]
    [InlineData("rescore", "fields_", "x")]
    [InlineData("rank", "order")]
    [InlineData("truncate_field", "maxTokens")]
    [InlineData("trim_to_budget", "max_token")]
    [InlineData("merge", "dedupe")]
    public void AnUnknownArgKeyIsRejectedForEveryStageKind(string kind, string typo, string? query = null)
    {
        var args = new Rec { [typo] = 1L };
        if (query is not null) args["query"] = query;
        var c = Case(kind, args, Items(), ("expect", Items()));
        Assert.Throws<ArgumentException>(() => CaseTests.AssertCase(c));
    }

    [Theory]
    [InlineData("pipeline")]
    [InlineData("shaped")]
    [InlineData("trace_report")]
    public void AnUnknownArgKeyInANestedStageSpecIsRejected(string wrapper)
    {
        var stages = Items(
            Spec("select", new Rec { ["fields"] = Items("a") }),
            Spec("dedupe", new Rec { ["kee"] = Items("a") })); // typo of "key"
        var c = Case(wrapper, new Rec { ["stages"] = stages }, Items(), ("expect", Items()));
        var e = Assert.Throws<ArgumentException>(() => CaseTests.AssertCase(c));
        Assert.Contains("kee", e.Message);
        Assert.Contains("stages[1]", e.Message);
    }

    [Fact]
    public void AnUnknownKeyOrUnknownStageInANestedSpecIsRejected()
    {
        var badKey = Items(new Rec { ["stage"] = "select", ["args"] = new Rec { ["fields"] = Items("a") },
                                     ["note"] = "x" });
        Assert.Throws<ArgumentException>(() => CaseTests.AssertCase(
            Case("pipeline", new Rec { ["stages"] = badKey }, Items(), ("expect", Items()))));
        var badStage = Items(Spec("selekt", new Rec()));
        Assert.Throws<ArgumentException>(() => CaseTests.AssertCase(
            Case("pipeline", new Rec { ["stages"] = badStage }, Items(), ("expect", Items()))));
    }

    [Fact]
    public void AnUnknownTopLevelCaseKeyIsRejected()
    {
        var c = Case("select", new Rec { ["fields"] = Items("a") }, Items(), ("expect", Items()), ("expectt", 1L));
        Assert.ThrowsAny<Xunit.Sdk.XunitException>(() => CaseTests.AssertCase(c));
    }

    [Fact]
    public void ValidArgsOfEveryKindAreAccepted()
    {
        CaseTests.ValidateArgs("quarantine", new Rec
        {
            ["fields"] = Items("a"), ["patterns"] = Items("p"), ["action"] = "flag",
            ["into"] = "q", ["replace_patterns"] = true,
        }, "ok");
        CaseTests.ValidateArgs("rescore", new Rec
        {
            ["query"] = "x", ["fields"] = Items("a"), ["into"] = "s", ["proximity"] = true,
            ["match"] = "word",
        }, "ok");
        CaseTests.ValidateArgs("trace_report", new Rec
        {
            ["id_field"] = "id",
            ["stages"] = Items(Spec("trim_to_budget", new Rec { ["max_tokens"] = 5L, ["min_records"] = 1L })),
        }, "ok");
    }

    // ----------------------------- expect_error -----------------------------

    private static Rec BadRegexCase(object? expectError) =>
        Case("quarantine", new Rec { ["fields"] = Items("a"), ["patterns"] = Items("(unclosed") },
             Items(new Rec { ["a"] = "x" }), ("expect_error", expectError));

    [Fact]
    public void AnExpectErrorCaseWithTheRightCodePasses() =>
        CaseTests.AssertCase(BadRegexCase(Err("config.invalid_pattern")));

    [Fact]
    public void AnExpectErrorCaseWhoseCodeIsWrongFails()
    {
        var e = Assert.ThrowsAny<Xunit.Sdk.XunitException>(
            () => CaseTests.AssertCase(BadRegexCase(Err("config.empty"))));
        Assert.Contains("config.invalid_pattern", e.Message);
    }

    [Fact]
    public void AnExpectErrorCaseThatDoesNotThrowFails()
    {
        var c = Case("select", new Rec { ["fields"] = Items("a") }, Items(new Rec { ["a"] = 1L }),
                     ("expect_error", Err("config.empty")));
        var e = Assert.ThrowsAny<Xunit.Sdk.XunitException>(() => CaseTests.AssertCase(c));
        Assert.Contains("returned", e.Message);
    }

    [Fact]
    public void AnExpectErrorCaseThatThrowsANonContexelErrorFails()
    {
        // an incomparable sort is a plain ArgumentException (a bug in the
        // case), never an acceptable outcome for an expect_error case
        var c = Case("rank", new Rec { ["by"] = "s" },
                     Items(new Rec { ["s"] = 1L }, new Rec { ["s"] = "two" }),
                     ("expect_error", Err("config.invalid_value")));
        var e = Assert.Throws<ArgumentException>(() => CaseTests.AssertCase(c));
        Assert.False(e is ContexelException);
    }

    [Fact]
    public void ACaseNeedsExactlyOneOfExpectAndExpectError()
    {
        var neither = Case("select", new Rec { ["fields"] = Items("a") }, Items());
        Assert.ThrowsAny<Xunit.Sdk.XunitException>(() => CaseTests.AssertCase(neither));
        var both = Case("select", new Rec { ["fields"] = Items("a") }, Items(),
                        ("expect", Items()), ("expect_error", Err("config.empty")));
        Assert.ThrowsAny<Xunit.Sdk.XunitException>(() => CaseTests.AssertCase(both));
    }

    [Fact]
    public void AnExpectCaseWhoseOutputDiffersFails()
    {
        var c = Case("select", new Rec { ["fields"] = Items("a") },
                     Items(new Rec { ["a"] = 1L, ["b"] = 2L }),
                     ("expect", Items(new Rec { ["a"] = 1L, ["b"] = 2L })));
        Assert.ThrowsAny<Xunit.Sdk.XunitException>(() => CaseTests.AssertCase(c));
    }

    // ------------------------- strict flag and null input -------------------------

    [Fact]
    public void ANonBooleanStrictIsRejectedNotCoerced()
    {
        foreach (var notABool in new[] { "true", "false" })
        {
            var c = Case("select", new Rec { ["fields"] = Items("a") }, Items(new Rec { ["a"] = 1L }),
                         ("expect", Items(new Rec { ["a"] = 1L })), ("strict", notABool));
            var e = Assert.ThrowsAny<Xunit.Sdk.XunitException>(() => CaseTests.AssertCase(c));
            Assert.Contains("strict must be a boolean", e.Message);
        }
    }

    [Fact]
    public void AStrictCaseRunsInStrictMode()
    {
        var c = Case("select", new Rec { ["fields"] = Items("a") }, null,
                     ("expect_error", Err("input.not_list")), ("strict", true));
        CaseTests.AssertCase(c);
        Assert.False(Strict.IsActive); // and the block is closed again
    }

    [Fact]
    public void WithoutStrictTheSameNullInputIsARawErrorNotTheTypedOne()
    {
        var c = Case("select", new Rec { ["fields"] = Items("a") }, null,
                     ("expect_error", Err("input.not_list")));
        // the stage fails with a non-contexel exception, which the runner must not accept
        var e = Assert.ThrowsAny<Exception>(() => CaseTests.AssertCase(c));
        Assert.False(e is ContexelException);
    }

    [Fact]
    public void ANullItemReachesTheStageAsANullItem()
    {
        var c = Case("select", new Rec { ["fields"] = Items("a") }, Items(new Rec { ["a"] = "x" }, null),
                     ("expect_error", Err("input.not_mapping")), ("strict", true));
        CaseTests.AssertCase(c);
    }

    [Fact]
    public void StrictAppliesToNestedPipelinesToo()
    {
        var c = Case("pipeline",
            new Rec { ["stages"] = Items(Spec("select", new Rec { ["fields"] = Items("a") })) },
            null, ("expect_error", Err("input.not_list")), ("strict", true));
        CaseTests.AssertCase(c);
    }

    [Fact]
    public void TheRealVectorFileCarriesBothNewCaseKeys()
    {
        var cases = AsList(Vectors["cases"]).Select(AsRec).ToList();
        Assert.Contains(cases, c => c.ContainsKey("expect_error"));
        Assert.Contains(cases, c => c.ContainsKey("strict"));
        Assert.Contains(cases, c => c["input"] is null);
    }
}
