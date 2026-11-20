using Xunit;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>Strict mode (ADR-003): opt-in shape validation that names the
/// stage and the item index, never changes a successful result, and holds
/// when a pipeline or shaper turns it on itself. C# is statically typed, so
/// only null can violate the shape. Mirrors tests/test_strict.py.</summary>
public class StrictTests
{
    // every stage with arguments that are valid on a list of {"a": ...} records
    private static readonly Dictionary<string, Func<Records, Records>> Calls = new()
    {
        ["select"] = r => Stages.Select(r, new[] { "a" }),
        ["dedupe"] = r => Stages.Dedupe(r, new[] { "a" }),
        ["rank"] = r => Stages.Rank(r, "a"),
        ["allowlist"] = r => Stages.Allowlist(r, "a", ["x"]),
        ["quarantine"] = r => Stages.Quarantine(r, new[] { "a" }),
        ["rescore"] = r => Stages.Rescore(r, "x", new[] { "a" }),
        ["truncate_field"] = r => Stages.TruncateField(r, "a", 5),
        ["trim_to_budget"] = r => Stages.TrimToBudget(r, 10),
    };

    public static IEnumerable<object[]> All() => Calls.Keys.Select(k => new object[] { k });
    public static IEnumerable<object[]> NeedMapping() =>
        Calls.Keys.Where(k => k != "trim_to_budget").Select(k => new object[] { k });

    private static Rec A(string v) => new() { ["a"] = v };

    [Fact]
    public void StrictOffKeepsTodaysLenientBehavior()
    {
        Assert.False(Strict.IsActive);
        Records withNulls = [A("x"), null!, A("x"), null!];
        Assert.Equal(2, Stages.Dedupe(withNulls).Count);          // items need not be mappings
        Records nums = [new Rec { ["n"] = 3L }, new Rec { ["n"] = 1L }, new Rec { ["n"] = 2L }];
        Assert.Equal(new object?[] { 3L, 2L, 1L },
            Stages.Rank(nums, r => r["n"]).Select(r => r["n"]).ToArray());
        // still a raw error, as before — not a contexel one
        var e = Assert.ThrowsAny<Exception>(() => Stages.Select(null!, new[] { "a" }));
        Assert.False(e is ContexelException);
    }

    [Theory]
    [MemberData(nameof(All))]
    public void StrictRejectsANullListAndNamesTheStage(string name)
    {
        using var _ = Strict.Begin();
        var e = Assert.Throws<InputShapeException>(() => Calls[name](null!));
        Assert.Equal("input.not_list", e.Code);
        Assert.Equal(name, e.Stage);
        Assert.Contains(name, e.Message);
    }

    [Theory]
    [MemberData(nameof(NeedMapping))]
    public void StrictRejectsANullItemAndNamesTheIndex(string name)
    {
        Records records = [A("x"), A("y"), null!, A("z")];
        using var _ = Strict.Begin();
        var e = Assert.Throws<InputShapeException>(() => Calls[name](records));
        Assert.Equal("input.not_mapping", e.Code);
        Assert.Equal(name, e.Stage);
        Assert.Contains("item 2", e.Message);
    }

    [Fact]
    public void StrictDoesNotRequireAMappingWhereTheStageDoesNotIndexOne()
    {
        Records withNulls = [null!, null!, A("x")];
        using var _ = Strict.Begin();
        Assert.Equal(3, Stages.TrimToBudget(withNulls, 100).Count);
        Assert.Equal(2, Stages.Dedupe(withNulls).Count);                 // key=null hashes the item
        Assert.Equal(3, Stages.Rank(withNulls, r => 0L).Count);          // a key function takes anything
        Assert.Throws<InputShapeException>(() => Stages.Dedupe(withNulls, "a")); // a key indexes the item
        Assert.Throws<InputShapeException>(() => Stages.Rank(withNulls, "a"));   // so does a field name
    }

    [Fact]
    public void TheFlagIsScopedToTheBlockAndNests()
    {
        Assert.False(Strict.IsActive);
        using (Strict.Begin())
        {
            Assert.True(Strict.IsActive);
            using (Strict.Begin()) Assert.True(Strict.IsActive);
            Assert.True(Strict.IsActive);              // the inner dispose restored "on"
        }
        Assert.False(Strict.IsActive);
        Assert.Throws<InvalidOperationException>((Action)(() =>
        {
            using var _ = Strict.Begin();
            throw new InvalidOperationException("boom");
        }));
        Assert.False(Strict.IsActive);
    }

    [Fact]
    public void DisposingAScopeTwiceDoesNotClobberAnOuterScope()
    {
        var outer = Strict.Begin();
        var inner = Strict.Begin();
        inner.Dispose();
        inner.Dispose();
        Assert.True(Strict.IsActive);
        outer.Dispose();
        Assert.False(Strict.IsActive);
    }

    [Theory]
    [MemberData(nameof(All))]
    public void StrictCheckRunsBeforeTrace(string name)
    {
        using var _ = Strict.Begin();
        using var t = Trace.Begin();
        // not a raw NullReferenceException from Trace.Traced reading records.Count
        var e = Assert.Throws<InputShapeException>(() => Calls[name](null!));
        Assert.Equal(("input.not_list", name), (e.Code, e.Stage));
    }

    [Fact]
    public void PipelineStrictDoesNotLeakIntoTheCaller()
    {
        var pipe = new Pipeline(
            [new Stage("select", r => Stages.Select(r, new[] { "a" }))], strict: true);
        Assert.False(Strict.IsActive);
        pipe.Run([A("x")]);
        Assert.False(Strict.IsActive);   // after a successful strict run
        Assert.Throws<InputShapeException>(() => pipe.Run(null!));
        Assert.False(Strict.IsActive);   // after a throwing strict run
        Assert.Throws<InputShapeException>(() => pipe.Run([A("x"), null!]));
        Assert.False(Strict.IsActive);
    }

    [Fact]
    public void ShapedStrictDoesNotLeakIntoTheCaller()
    {
        var pipe = new Pipeline(new Stage("select", r => Stages.Select(r, new[] { "a" })));
        var ok = Shaped.Wrap(pipe, () => new Records { A("x") }, strict: true);
        var bad = Shaped.Wrap(pipe, () => (Records)null!, strict: true);
        Assert.False(Strict.IsActive);
        ok();
        Assert.False(Strict.IsActive);
        Assert.Throws<InputShapeException>(() => bad());
        Assert.False(Strict.IsActive);
        // thrown from INSIDE the strict block (a null item), not before it
        var badItem = Shaped.Wrap(pipe, () => new Records { A("x"), null! }, strict: true);
        Assert.Throws<InputShapeException>(() => badItem());
        Assert.False(Strict.IsActive);
    }

    [Fact]
    public void AStaleSecondDisposeDoesNotSwitchStrictOffInsideALaterScope()
    {
        var s1 = Strict.Begin();
        s1.Dispose();
        var s2 = Strict.Begin();
        s1.Dispose();                     // stale: must be a no-op
        Assert.True(Strict.IsActive);
        s2.Dispose();
        Assert.False(Strict.IsActive);
    }

    [Fact]
    public async Task PipelineStrictHoldsOnAWorkerThread()
    {
        var pipe = new Pipeline(
            [new Stage("select", r => Stages.Select(r, new[] { "a" }))], strict: true);
        var e = await Assert.ThrowsAsync<InputShapeException>(
            () => Task.Run(() => pipe.Run(null!)));
        Assert.Equal("input.not_list", e.Code);
    }

    [Fact]
    public async Task AStrictBlockFlowsIntoTasksStartedInsideItButNotAfterIt()
    {
        // .NET difference from Python's ContextVar caveat: AsyncLocal flows
        // into child tasks and threads started while the block is active
        Task<bool> probe;
        using (Strict.Begin()) probe = Task.Run(() => Strict.IsActive);
        Assert.True(await probe);
        Assert.False(await Task.Run(() => Strict.IsActive));
    }

    [Fact]
    public void PipelineStrictNamesTheStageThatReturnedANull()
    {
        var pipe = new Pipeline(
            [
                new Stage("select", r => Stages.Select(r, new[] { "a" })),
                new Stage("returns_none", _ => null!),
                new Stage("select", r => Stages.Select(r, new[] { "a" })),
            ], strict: true);
        var e = Assert.Throws<InputShapeException>(() => pipe.Run([new Rec { ["a"] = 1L }]));
        Assert.Equal("input.not_list", e.Code);
        Assert.Equal("returns_none", e.Stage);
        Assert.Contains("stage 1", e.Message);
    }

    [Fact]
    public void PipelineWithoutStrictLetsTheNextStageFailObscurely()
    {
        var pipe = new Pipeline(
            new Stage("returns_none", _ => null!),
            new Stage("select", r => Stages.Select(r, new[] { "a" })));
        var e = Assert.ThrowsAny<Exception>(() => pipe.Run([new Rec { ["a"] = 1L }]));
        Assert.False(e is ContexelException);
    }

    [Fact]
    public void PipelineStrictChecksStageOutputsNotThePipelineInput()
    {
        // the pipeline itself checks only what each stage RETURNS: a null
        // input to an empty pipeline passes straight through...
        Assert.Null(new Pipeline(Array.Empty<Stage>(), strict: true).Run(null!));
        // ...and a pass-through stage hands the null on, so ITS output fails
        var pipe = new Pipeline([new Stage("pass_through", r => r)], strict: true);
        var e = Assert.Throws<InputShapeException>(() => pipe.Run(null!));
        Assert.Equal("pass_through", e.Stage);
        Assert.Contains("stage 0", e.Message);
    }

    [Fact]
    public void ThePipelineParamsConstructorStillWorks()
    {
        var pipe = new Pipeline(new Stage("select", r => Stages.Select(r, new[] { "a" })));
        Assert.False(pipe.IsStrict);
        Assert.Single(pipe.Run([new Rec { ["a"] = 1L, ["b"] = 2L }]));
    }

    [Fact]
    public void ShapedStrictRejectsANullReturn()
    {
        var pipe = new Pipeline(new Stage("select", r => Stages.Select(r, new[] { "a" })));
        var tool = Shaped.Wrap(pipe, () => (Records)null!, strict: true);
        var e = Assert.Throws<InputShapeException>(() => tool());
        Assert.Equal(("input.not_list", "shaped"), (e.Code, e.Stage));
    }

    [Fact]
    public void ShapedStrictHoldsForEveryOverload()
    {
        var pipe = new Pipeline(new Stage("select", r => Stages.Select(r, new[] { "a" })));
        Assert.Throws<InputShapeException>(() =>
            Shaped.Wrap(pipe, (int _) => (Records)null!, strict: true)(1));
        Assert.Throws<InputShapeException>(() =>
            Shaped.Wrap(pipe, (int _, int _) => (Records)null!, strict: true)(1, 2));
        Assert.Throws<InputShapeException>(() =>
            Shaped.Wrap(pipe, async () => { await Task.Yield(); return (Records)null!; },
                        strict: true)().GetAwaiter().GetResult());
        Assert.Throws<InputShapeException>(() =>
            Shaped.Wrap(pipe, async (int _) => { await Task.Yield(); return (Records)null!; },
                        strict: true)(1).GetAwaiter().GetResult());
        Assert.Throws<InputShapeException>(() =>
            Shaped.Wrap(pipe, async (int _, int _) => { await Task.Yield(); return (Records)null!; },
                        strict: true)(1, 2).GetAwaiter().GetResult());
    }

    [Fact]
    public async Task ShapedStrictHoldsForAsyncToolsAndOnAWorkerThread()
    {
        var pipe = new Pipeline(new Stage("select", r => Stages.Select(r, new[] { "a" })));
        var tool = Shaped.Wrap(pipe, async () =>
        {
            await Task.Delay(1);
            return (Records)null!;
        }, strict: true);
        await Assert.ThrowsAsync<InputShapeException>(() => Task.Run(() => tool()));
    }

    [Fact]
    public void ShapedWithAPrebuiltPipelineRunsItInStrictMode()
    {
        var pipe = new Pipeline(new Stage("select", r => Stages.Select(r, new[] { "a" })));
        var tool = Shaped.Wrap(pipe, () => new Records { new Rec { ["a"] = 1L }, null! }, strict: true);
        var e = Assert.Throws<InputShapeException>(() => tool());
        Assert.Equal("input.not_mapping", e.Code);
    }

    [Fact]
    public void ShapedWithoutStrictIsUnchanged()
    {
        var pipe = new Pipeline(new Stage("select", r => Stages.Select(r, new[] { "a" })));
        var tool = Shaped.Wrap(pipe, () => new Records { new Rec { ["a"] = 1L, ["b"] = 2L } });
        VectorData.AssertDeepEqual(new List<object?> { new Rec { ["a"] = 1L } }, tool(), "shaped");
        Assert.False(Strict.IsActive);
    }

    [Fact]
    public void StrictDoesNotChangeTheFingerprint()
    {
        Stage[] stages =
        [
            new("select", r => Stages.Select(r, new[] { "a" }),
                new Rec { ["fields"] = new List<object?> { "a" } }),
            new("dedupe", r => Stages.Dedupe(r, new[] { "a" }),
                new Rec { ["key"] = new List<object?> { "a" } }),
        ];
        Assert.Equal(new Pipeline(stages, strict: true).Fingerprint, new Pipeline(stages).Fingerprint);
    }

    [Fact]
    public void StrictNeverChangesASuccessfulResult()
    {
        Stage[] stages =
        [
            new("allowlist", r => Stages.Allowlist(r, "source", ["repo", "docs"])),
            new("quarantine", r => Stages.Quarantine(r, new[] { "snippet" })),
            new("select", r => Stages.Select(r, new[] { "path", "line", "source", "snippet" })),
            new("dedupe", r => Stages.Dedupe(r, new[] { "path", "line" })),
            new("rescore", r => Stages.Rescore(r, "exponential backoff jitter",
                new[] { "snippet", "path" })),
            new("truncate_field", r => Stages.TruncateField(r, "snippet", 12)),
            new("rank", r => Stages.Rank(r, "score", desc: true)),
            new("trim_to_budget", r => Stages.TrimToBudget(r, 150)),
        ];
        var lenient = new Pipeline(stages).Run(VectorData.Fixture);
        Assert.NotEmpty(lenient);
        VectorData.AssertDeepEqual(lenient, new Pipeline(stages, strict: true).Run(VectorData.Fixture), "strict pipeline");
        using (Strict.Begin())
            VectorData.AssertDeepEqual(lenient, new Pipeline(stages).Run(VectorData.Fixture), "ambient strict");
    }
}
