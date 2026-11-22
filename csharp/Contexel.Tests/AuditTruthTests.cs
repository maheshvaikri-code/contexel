using Xunit;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>Audit truthfulness (ADR-008, brief AC 28-30): the trail must not
/// under-report. Mirrors tests/test_audit_truth.py.</summary>
public class AuditTruthTests
{
    private static Rec R(params (string Key, object? Value)[] fields)
    {
        var r = new Rec();
        foreach (var (key, value) in fields) r[key] = value;
        return r;
    }

    /// <summary>Run one stage under a trace; return its recorded dropped ids.</summary>
    private static List<object?> Drops(Func<Records> stage)
    {
        using var t = Trace.Begin("id");
        stage();
        var stages = (List<object?>)t.Audit()["stages"]!;
        return (List<object?>)((Rec)stages[0]!)["dropped_ids"]!;
    }

    [Fact]
    public void TraceReportsADropWhenAnotherSurvivorNeverHadTheId()
    {
        Records records = [R(("id", "a"), ("t", "x")), R(("t", "y")), R(("id", "b"), ("t", "z"))];
        var dropped = Drops(() => Stages.Allowlist(records, "t", new List<object?> { "y", "z" }));
        Assert.Equal(new object?[] { "a" }, dropped);
    }

    [Fact]
    public void TraceSelectStrippingIdsIsNotADrop()
    {
        Records records = [R(("id", "u0"), ("title", "t0")), R(("id", "u1"), ("title", "t1")),
                           R(("id", "u2"), ("title", "t2"))];
        Assert.Empty(Drops(() => Stages.Select(records, new[] { "title" })));
    }

    [Fact]
    public void TraceMixedInputWithSelectStrippingIdsIsNotADrop()
    {
        Records records = [R(("id", "a"), ("title", "x")), R(("title", "y")),
                           R(("id", "b"), ("title", "z"))];
        Assert.Empty(Drops(() => Stages.Select(records, new[] { "title" })));
    }

    [Fact]
    public void TraceAmbiguityIsBoundedByTheLostCount()
    {
        // The stage keeps "a" with its id, keeps one record WITHOUT an id and
        // discards two. Only ONE id can be explained by a stripped survivor.
        Records records = [R(("id", "a"), ("title", "1")), R(("id", "b"), ("title", "2")),
                           R(("id", "c"), ("title", "3"))];
        var dropped = Drops(() => Trace.Traced("keep_a_and_one_stripped", records,
            () => [records[0], R(("title", "stripped"))]));
        Assert.Equal(new object?[] { "c" }, dropped);
    }

    [Fact]
    public void TraceAStageThatAddsIdlessRecordsNeverHidesMoreThanItAdded()
    {
        Records records = [R(("id", "a")), R(("id", "b"))];
        var dropped = Drops(() => Trace.Traced("add_two_drop_b", records,
            () => [records[0], R(("n", 1L)), R(("n", 2L))]));
        Assert.Empty(dropped);
    }

    [Fact]
    public void TraceDroppedIdsAreReportedInInputOrder()
    {
        Records records = [R(("id", 1L), ("k", "drop")), R(("k", "keep")),
                           R(("id", 3L), ("k", "drop")), R(("id", 4L), ("k", "keep"))];
        var dropped = Drops(() => Stages.Allowlist(records, "k", new List<object?> { "keep" }));
        Assert.Equal(new object?[] { 1L, 3L }, dropped);
    }

    [Fact]
    public void TraceCountsANullItemAsIdlessInsteadOfFailing()
    {
        // a null item (the one non-mapping item C# can hold) has no id: it is
        // unidentified on both sides, so the drop of "a" is still reported
        Records records = [R(("id", "a")), null!, R(("id", "b"))];
        var dropped = Drops(() => Trace.Traced("keep_b_and_null", records,
            () => [records[1], records[2]]));
        Assert.Equal(new object?[] { "a" }, dropped);
    }
}
