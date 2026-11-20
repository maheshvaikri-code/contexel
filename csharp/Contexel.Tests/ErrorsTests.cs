using Xunit;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>The typed error model (ADR-003): a stable Code is the
/// cross-language contract, the two subclasses keep every existing
/// catch (ArgumentException) working, and the original quarantine messages
/// are untouched. Mirrors tests/test_errors.py.</summary>
public class ErrorsTests
{
    private static readonly string[] DocumentedCodes =
    [
        "config.invalid_value", "config.empty", "config.contradictory",
        "config.invalid_pattern", "input.not_list", "input.not_mapping",
        "input.field_conflict",
    ];

    [Fact]
    public void ConfigExceptionIsAnArgumentExceptionAndAContexelException()
    {
        var e = new ConfigException("config.empty", "nothing to do", "quarantine", "fields");
        Assert.IsAssignableFrom<ContexelException>(e);
        Assert.IsAssignableFrom<ArgumentException>(e);
        Assert.False((object)e is InputShapeException);
        Assert.Equal(("config.empty", "quarantine", "fields", "nothing to do"),
                     (e.Code, e.Stage, e.Param, e.Message));
    }

    [Fact]
    public void InputShapeExceptionIsAnArgumentExceptionAndAContexelException()
    {
        var e = new InputShapeException("input.not_list", "not a list", "select");
        Assert.IsAssignableFrom<ContexelException>(e);
        Assert.IsAssignableFrom<ArgumentException>(e);
        Assert.False((object)e is ConfigException);
        Assert.Equal(("input.not_list", "select", null), (e.Code, e.Stage, e.Param));
    }

    [Fact]
    public void TheMessageIsNeverDecoratedWithAParameterName()
    {
        // ArgumentException(message, paramName) would append " (Parameter ...)"
        var e = new ConfigException("config.invalid_value", "bad", "rescore", "match");
        Assert.Equal("bad", e.Message);
        Assert.Null(e.ParamName);
    }

    [Fact]
    public void ErrorCodesAreTheDocumentedSet() =>
        Assert.Equal(DocumentedCodes, ContexelException.Codes);

    [Fact]
    public void AnUnknownCodeIsRefused()
    {
        // a developer error: a plain ArgumentException, not a contexel error
        var e = Assert.Throws<ArgumentException>(() => new ConfigException("config.made_up", "x"));
        Assert.Contains("unknown contexel error code", e.Message);
        Assert.Throws<ArgumentException>(() => new ContexelException("made.up", "x"));
    }

    [Fact]
    public void EachSubclassRefusesTheOtherFamiliesCodes()
    {
        Assert.Throws<ArgumentException>(() => new ConfigException("input.not_list", "x"));
        Assert.Throws<ArgumentException>(() => new InputShapeException("config.empty", "x"));
    }

    [Fact]
    public void TheErrorTypesAreExportedFromThePackage()
    {
        foreach (var t in new[]
        {
            typeof(ContexelException), typeof(ConfigException),
            typeof(InputShapeException), typeof(Strict),
        })
            Assert.True(t.IsPublic, $"{t.Name} must be public");
    }

    public static IEnumerable<object[]> QuarantineMessages() =>
    [
        ["action", "allow", "action must be 'drop' or 'flag', got 'allow'", "config.invalid_value"],
        ["patterns", "", "empty pattern fragments match everything; remove them", "config.empty"],
        ["emptyreplace", "", "replacePatterns with no patterns would disable the control " +
            "entirely; pass at least one pattern", "config.empty"],
        ["replace", "", "replacePatterns without patterns is contradictory; pass the " +
            "replacement patterns", "config.contradictory"],
    ];

    [Theory]
    [MemberData(nameof(QuarantineMessages))]
    public void ExistingQuarantineMessagesAreUnchanged(string which, string arg,
                                                       string message, string code)
    {
        Records one = [new Rec { ["snippet"] = "x" }];
        Action call = which switch
        {
            "action" => () => Stages.Quarantine(one, action: arg),
            "patterns" => () => Stages.Quarantine(one, patterns: new[] { arg }),
            "emptyreplace" => () => Stages.Quarantine(one, patterns: Array.Empty<string>(),
                                                      replacePatterns: true),
            _ => () => Stages.Quarantine(one, replacePatterns: true),
        };
        var info = Assert.ThrowsAny<ArgumentException>(call); // the pre-existing handler still works
        Assert.Equal(message, info.Message);
        var typed = Assert.IsType<ConfigException>(info);
        Assert.Equal(code, typed.Code);
    }
}
