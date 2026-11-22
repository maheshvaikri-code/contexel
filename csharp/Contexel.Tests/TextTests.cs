using System.Diagnostics;
using System.Text.RegularExpressions;
using Xunit;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>Payload stages (ADR-005): AsRecords / Split / Join carry text
/// through the record stages and back, losslessly, with the same boundaries in
/// every language. Mirrors tests/test_text_stages.py. The property checks are
/// seeded (CONTEXEL_PROP_SEED, CONTEXEL_PROP_CASES) from a small LCG of our own,
/// so the sequence never changes between runtimes, and each has a canary
/// proving the check can fail. Non-ASCII text is built with
/// char.ConvertFromUtf32 so no editor can rewrite it.</summary>
public class TextTests
{
    private static readonly string Astral = char.ConvertFromUtf32(0x1F600);
    private static readonly string EAcute = char.ConvertFromUtf32(0xE9);

    // every character str.splitlines() treats as a line end, other than \n and \r
    private static readonly string WideLineEnds = string.Concat(
        new[] { 0x0B, 0x0C, 0x1C, 0x1D, 0x1E, 0x85, 0x2028, 0x2029 }.Select(char.ConvertFromUtf32));

    private static Rec R(params object?[] keyValues)
    {
        var rec = new Rec();
        for (int i = 0; i < keyValues.Length; i += 2) rec[(string)keyValues[i]!] = keyValues[i + 1];
        return rec;
    }

    private static List<object?> L(params object?[] items) => [.. items];

    private static Records ChunksOf(string text, string by = "lines", int? size = null,
                                    string field = "text") =>
        Text.Split(Text.AsRecords(text, field), field: field, by: by, size: size);

    private static string[] Texts(Records chunks) =>
        chunks.Select(c => (string)c["text"]!).ToArray();

    private static (long Index, long Start, long End) Where(Rec chunk)
    {
        var c = (Rec)chunk["chunk"]!;
        return ((long)c["index"]!, (long)c["start"]!, (long)c["end"]!);
    }

    private static (long, long)[] Spans(Records chunks) =>
        chunks.Select(c => (Where(c).Start, Where(c).End)).ToArray();

    /// <summary>Deep structural equality (canonical JSON; key order is irrelevant).</summary>
    private static void Same(object? expected, object? actual) =>
        Assert.Equal(Tokens.PythonJson(expected), Tokens.PythonJson(actual));

    private static T Code<T>(Action act, string code, string? stage = null, string? param = null)
        where T : ContexelException
    {
        var e = Assert.Throws<T>(act);
        Assert.Equal(code, e.Code);
        if (stage is not null) Assert.Equal(stage, e.Stage);
        if (param is not null) Assert.Equal(param, e.Param);
        return e;
    }

    /// <summary>The code points of a string (a surrogate pair is one).</summary>
    private static int[] CodePoints(string s)
    {
        var cps = new List<int>(s.Length);
        for (int i = 0; i < s.Length; i++)
        {
            if (char.IsSurrogatePair(s, i)) { cps.Add(char.ConvertToUtf32(s, i)); i++; }
            else cps.Add(s[i]);
        }
        return [.. cps];
    }

    private static string FromCodePoints(int[] cps, int start, int end) =>
        string.Concat(cps[start..end].Select(char.ConvertFromUtf32));

    // ---------------------------------------------------------- AsRecords ----

    [Fact]
    public void AsRecordsWrapsAString()
    {
        Same(new Records { R("text", "hello") }, Text.AsRecords("hello"));
        Same(new Records { R("body", "x") }, Text.AsRecords("x", "body"));
        Same(new Records { R("text", "") }, Text.AsRecords(""));
    }

    [Fact]
    public void AsRecordsASingleMappingIsTheSameObject()
    {
        var m = R("a", 1L);
        var output = Text.AsRecords(m);
        Same(new Records { R("a", 1L) }, output);
        Assert.Same(m, output[0]); // the same object, not a copy
    }

    [Fact]
    public void AsRecordsListItemsKeepMappingsAndWrapEverythingElse()
    {
        var keep = R("a", 1L);
        var nested = R("k", R("z", L(1L, 2L)));
        var output = Text.AsRecords(L(keep, "s", 5L, null, L("n", 1L), nested, true));
        Same(new Records
        {
            R("a", 1L), R("text", "s"), R("text", 5L), R("text", null),
            R("text", L("n", 1L)), R("k", R("z", L(1L, 2L))), R("text", true),
        }, output);
        Assert.Same(keep, output[0]);
        Assert.Same(nested, output[5]);
        // an array and a lazy sequence are lists too
        Same(new Records { R("a", 1L), R("text", "t") }, Text.AsRecords(new object?[] { R("a", 1L), "t" }));
        Same(new Records { R("text", "x"), R("text", "y") }, Text.AsRecords(Lazy("x", "y")));
        Same(new Records(), Text.AsRecords(new List<object?>()));
    }

    private static IEnumerable<object?> Lazy(params object?[] items)
    {
        foreach (var item in items) yield return item;
    }

    [Fact]
    public void AsRecordsDoesNotMutateAList()
    {
        var items = L(R("a", 1L), "s");
        var before = Tokens.PythonJson(items);
        Text.AsRecords(items);
        Assert.Equal(before, Tokens.PythonJson(items));
    }

    private sealed class Opaque;

    // a dictionary that implements only the generic IDictionary<K,V>
    private static System.Dynamic.ExpandoObject Expando()
    {
        var expando = new System.Dynamic.ExpandoObject();
        ((IDictionary<string, object?>)expando)["text"] = "a";
        return expando;
    }

    public static IEnumerable<object[]> NotLists() =>
    [
        [null!], [new byte[] { 1, 2 }], [5L], [5], [2.5], [true],
        [new HashSet<long> { 1, 2 }], [new Dictionary<string, string> { ["a"] = "b" }],
        [new Dictionary<int, int> { [1] = 2 }], [new DateTime(2026, 1, 1)], [new Opaque()],
        [Expando()], [System.Text.Json.Nodes.JsonNode.Parse("{\"text\":\"a\",\"b\":1}")!],
    ];

    [Fact]
    public void AsRecordsNonGenericEnumerablesAndGenericListsAreLists()
    {
        var keep = R("a", 1L);
        var output = Text.AsRecords(new System.Collections.ArrayList { keep, "s", null });
        Same(new Records { R("a", 1L), R("text", "s"), R("text", null) }, output);
        Assert.Same(keep, output[0]);
        Same(new Records { R("text", "x"), R("a", 1L) },
             Text.AsRecords(new List<object?> { "x", R("a", 1L) }));
    }

    [Theory]
    [MemberData(nameof(NotLists))]
    public void AsRecordsNullBytesAndOtherTypesRaiseNotList(object? bad)
    {
        var e = Code<InputShapeException>(() => Text.AsRecords(bad), "input.not_list", "as_records");
        Assert.IsAssignableFrom<ContexelException>(e);
        Assert.IsAssignableFrom<ArgumentException>(e);
    }

    [Theory]
    [InlineData("")]
    [InlineData(null)]
    public void AsRecordsFieldMustBeANonEmptyString(string? bad) =>
        Code<ConfigException>(() => Text.AsRecords("x", bad!), "config.invalid_value",
                              "as_records", "field");

    [Fact]
    public void AsRecordsChecksTheShapeBeforeTheFieldName() =>
        Assert.Throws<InputShapeException>(() => Text.AsRecords(null, ""));

    // -------------------------------------------------------------- Split ----

    [Fact]
    public void SplitLinesKeepsSeparators()
    {
        var c = ChunksOf("one\ntwo\nthree", "lines");
        Assert.Equal(["one\n", "two\n", "three"], Texts(c));
        Assert.Equal([(0L, 4L), (4L, 8L), (8L, 13L)], Spans(c));
        Assert.Equal([0L, 1L, 2L], c.Select(x => Where(x).Index).ToArray());
        Assert.Equal(["a\n"], Texts(ChunksOf("a\n"))); // no empty remainder
        Assert.Equal(["\n"], Texts(ChunksOf("\n")));
        Assert.Equal(["\n", "\n"], Texts(ChunksOf("\n\n")));
    }

    [Fact]
    public void SplitCrlfIsOneBoundaryAndALoneCrIsNot()
    {
        Assert.Equal(["a\r\n", "b\rc\n", "d"], Texts(ChunksOf("a\r\nb\rc\nd")));
        Assert.Equal(["a\rb"], Texts(ChunksOf("a\rb")));
        Assert.Equal(["\r"], Texts(ChunksOf("\r")));
        Assert.Equal(["a\r\n"], Texts(ChunksOf("a\r\n")));
    }

    [Fact]
    public void SplitLinesIgnoresTheWiderSplitlinesSeparators()
    {
        string text = "a" + WideLineEnds + "b";
        Assert.Equal([text], Texts(ChunksOf(text, "lines")));
    }

    public static IEnumerable<object[]> ParagraphCases() =>
    [
        ["a\n\nb", new[] { "a\n\n", "b" }],
        ["a\n\n\nb", new[] { "a\n\n\n", "b" }],
        ["a\r\n\r\nb", new[] { "a\r\n\r\n", "b" }],
        ["a\n\r\nb", new[] { "a\n\r\n", "b" }],
        ["a\r\r\n\nb", new[] { "a\r\r\n\n", "b" }],
        ["a\nb", new[] { "a\nb" }],
        ["a\r\nb", new[] { "a\r\nb" }],
        ["a\n \nb", new[] { "a\n \nb" }],
        ["\n\nabc", new[] { "\n\n", "abc" }],
        ["abc\n\n", new[] { "abc\n\n" }],
        ["a\n\nb\n\nc", new[] { "a\n\n", "b\n\n", "c" }],
        ["\n\n\n\n", new[] { "\n\n\n\n" }],
    ];

    [Theory]
    [MemberData(nameof(ParagraphCases))]
    public void SplitParagraphsBoundaries(string text, string[] expected) =>
        Assert.Equal(expected, Texts(ChunksOf(text, "paragraphs")));

    [Fact]
    public void SplitSizeCountsCodePoints()
    {
        string text = "ab" + Astral + Astral + Astral + "c"; // 6 code points, 9 UTF-16 units
        var c = ChunksOf(text, "size", 2);
        Assert.Equal(["ab", Astral + Astral, Astral + "c"], Texts(c));
        Assert.Equal([(0L, 2L), (2L, 4L), (4L, 6L)], Spans(c));
        Assert.Equal(["abc", "def"], Texts(ChunksOf("abcdef", "size", 3)));
        Assert.Equal(["abc"], Texts(ChunksOf("abc", "size", 10)));
        Assert.Equal(["a", "b"], Texts(ChunksOf("ab", "size", 1)));
    }

    [Fact]
    public void SplitSizeNeverCutsASurrogatePairInHalf()
    {
        string text = Astral + Astral + Astral;
        foreach (var chunk in ChunksOf(text, "size", 1))
            Assert.Equal(Astral, chunk["text"]);
        Assert.Equal([(0L, 1L), (1L, 2L), (2L, 3L)], Spans(ChunksOf(text, "size", 1)));
    }

    public static IEnumerable<object?[]> EveryMode() =>
    [
        ["lines", null], ["paragraphs", null], ["size", 3],
    ];

    [Theory]
    [MemberData(nameof(EveryMode))]
    public void SplitEmptyTextYieldsNothingAndASeparatorFreeTextIsOneChunk(string by, int? size)
    {
        Same(new Records(), Text.Split([R("text", "", "id", 1L)], by: by, size: size));
        var output = Text.Split(
            [R("id", 0L, "text", "xyz"), R("id", 1L, "text", ""), R("id", 2L, "text", "q")],
            by: by, size: size);
        Assert.Equal(new object?[] { 0L, 2L }, output.Select(c => c["id"]).ToArray());
        Assert.Equal(["xyz", "q"], Texts(output));
        var only = ChunksOf("abc", by, size);
        Assert.Equal(["abc"], Texts(only));
        Assert.Equal([(0L, 3L)], Spans(only));
    }

    [Fact]
    public void SplitOffsetsIndexBackIntoTheText()
    {
        string text = "caf" + EAcute + "\r\nna\nve" + Astral + "\n\nz";
        var cps = CodePoints(text);
        foreach (var (by, size) in new (string, int?)[] { ("lines", null), ("paragraphs", null), ("size", 3) })
            foreach (var c in ChunksOf(text, by, size))
            {
                var (_, start, end) = Where(c);
                Assert.Equal(FromCodePoints(cps, (int)start, (int)end), c["text"]);
            }
    }

    [Fact]
    public void SplitChunksCarryTheParentFields()
    {
        var parent = R("id", 7L, "text", "a\nb", "meta", R("k", 1L), "tags", L("t"));
        var before = Tokens.PythonJson(parent);
        var output = Text.Split([parent]);
        Same(new Records
        {
            R("id", 7L, "text", "a\n", "meta", R("k", 1L), "tags", L("t"),
              "chunk", R("index", 0L, "start", 0L, "end", 2L)),
            R("id", 7L, "text", "b", "meta", R("k", 1L), "tags", L("t"),
              "chunk", R("index", 1L, "start", 2L, "end", 3L)),
        }, output);
        Assert.Equal(before, Tokens.PythonJson(parent)); // the input is never mutated
        Assert.Equal("a\nb", parent["text"]);
    }

    [Fact]
    public void SplitChunksKeepTheParentKeyComparer()
    {
        // a case-insensitive record: the chunk replaces the text under its own
        // key, it does not add a second "text" next to the parent's "TEXT"
        var parent = new Rec(StringComparer.OrdinalIgnoreCase) { ["TEXT"] = "a\nb" };
        var output = Text.Split([parent]);
        Assert.Equal(["a\n", "b"], output.Select(c => (string)c["TEXT"]!).ToArray());
        foreach (var chunk in output)
        {
            Assert.Equal(parent.Count + 1, chunk.Count); // the text entry and the chunk
            Assert.Equal(chunk["TEXT"], chunk["text"]);
        }
        Assert.Equal("a\nb", parent["TEXT"]);
    }

    [Fact]
    public void SplitIndexRestartsForEachParentAndParentsKeepTheirOrder()
    {
        var output = Text.Split([R("id", "a", "text", "1\n2\n"), R("id", "x", "text", "x\ny\nz")]);
        Assert.Equal(
            [("a", 0L), ("a", 1L), ("x", 0L), ("x", 1L), ("x", 2L)],
            output.Select(c => ((string)c["id"]!, Where(c).Index)).ToArray());
    }

    [Fact]
    public void SplitPassesThroughARecordWithoutAStringField()
    {
        Records records =
        [
            R("id", 1L), R("id", 2L, "text", null), R("id", 3L, "text", 5L),
            R("id", 4L, "text", L("a\nb")), R("id", 5L, "text", "k\nl"),
        ];
        var output = Text.Split(records);
        for (int i = 0; i < 4; i++) Assert.Same(records[i], output[i]);
        Assert.Equal(["k\n", "l"], Texts(output.Skip(4).ToList()));
    }

    [Fact]
    public void SplitAPassthroughRecordMayAlreadyHaveTheIntoKey()
    {
        var record = R("text", 5L, "chunk", "x");
        var output = Text.Split([record]);
        Assert.Single(output);
        Assert.Same(record, output[0]);
    }

    [Fact]
    public void SplitExistingIntoKeyRaisesFieldConflict()
    {
        var e = Code<InputShapeException>(
            () => Text.Split([R("text", "ok\nok"), R("text", "a\nb", "chunk", 1L)]),
            "input.field_conflict", "split", "into");
        Assert.Contains("record 1", e.Message);
        // a different into name is the way out
        var output = Text.Split([R("text", "a\nb", "chunk", 1L)], into: "part");
        Assert.Equal(new object?[] { 1L, 1L }, output.Select(c => c["chunk"]).ToArray());
        Assert.Equal(0L, ((Rec)output[0]["part"]!)["index"]);
        // an empty text yields no chunks, but the clash is still refused
        Assert.Throws<InputShapeException>(() => Text.Split([R("text", "", "chunk", 1L)]));
        // into equal to field clashes with the very text being split
        Assert.Throws<InputShapeException>(() => Text.Split([R("text", "a")], into: "text"));
    }

    [Theory]
    [InlineData(null)]
    [InlineData(0)]
    [InlineData(-1)]
    public void SplitBySizeRequiresAPositiveIntegerSize(int? size) =>
        Code<ConfigException>(() => Text.Split([R("text", "abc")], by: "size", size: size),
                              "config.invalid_value", "split", "size");

    [Fact]
    public void SplitSizeTypesCSharpCannotSpellAreRefusedByTheUntypedEntry()
    {
        // the typed Split takes int?, so a bool, a fraction or a string cannot be
        // passed to it; the vector runner reaches them through SplitCore
        foreach (object? bad in new object?[] { null, 0L, -1L, true, 2.5, "3", 2.0 })
            Code<ConfigException>(
                () => Text.SplitCore([R("text", "abc")], "text", "size", bad, "chunk"),
                "config.invalid_value", "split", "size");
        // a long size beyond int is a valid size: it just holds the whole text
        Assert.Equal(["abc"], Texts(Text.SplitCore([R("text", "abc")], "text", "size",
                                                   long.MaxValue, "chunk")));
        Assert.Equal(["ab", "c"], Texts(Text.SplitCore([R("text", "abc")], "text", "size",
                                                       2L, "chunk")));
    }

    [Theory]
    [InlineData("lines", 3)]
    [InlineData("paragraphs", 3)]
    [InlineData("lines", 0)]
    public void SplitSizeWithAnotherModeIsContradictory(string by, int size) =>
        Code<ConfigException>(() => Text.Split([R("text", "abc")], by: by, size: size),
                              "config.contradictory", "split", "size");

    [Fact]
    public void SplitSizeWithAnotherModeIsContradictoryForAnyUntypedValue() =>
        Code<ConfigException>(
            () => Text.SplitCore([R("text", "abc")], "text", "lines", 2.5, "chunk"),
            "config.contradictory", "split", "size");

    [Theory]
    [InlineData("words")]
    [InlineData("")]
    [InlineData(null)]
    public void SplitUnknownByRaises(string? by) =>
        Code<ConfigException>(() => Text.Split([R("text", "abc")], by: by!),
                              "config.invalid_value", "split", "by");

    [Fact]
    public void SplitFieldAndIntoMustBeStrings()
    {
        Code<ConfigException>(() => Text.Split([R("text", "abc")], field: null!),
                              "config.invalid_value", "split", "field");
        Code<ConfigException>(() => Text.Split([R("text", "abc")], into: null!),
                              "config.invalid_value", "split", "into");
    }

    [Fact]
    public void SplitValidatesFieldThenByThenIntoThenSize()
    {
        // each pair is broken in two ways; the earlier one in the order is reported
        Code<ConfigException>(() => Text.Split([R("text", "a")], field: null!, by: "bogus"),
                              "config.invalid_value", "split", "field");
        Code<ConfigException>(() => Text.Split([R("text", "a")], by: "bogus", into: null!),
                              "config.invalid_value", "split", "by");
        Code<ConfigException>(() => Text.Split([R("text", "a")], by: "size", into: null!, size: 0),
                              "config.invalid_value", "split", "into");
    }

    [Fact]
    public void SplitChecksItsInputInEveryMode()
    {
        Assert.False(Strict.IsActive);
        Code<InputShapeException>(() => Text.Split(null!), "input.not_list", "split");
        var e = Code<InputShapeException>(() => Text.Split([R("text", "a"), null!]),
                                          "input.not_mapping", "split");
        Assert.Contains("item 1", e.Message);
    }

    [Fact]
    public void SplitChecksTheShapeBeforeTheConfiguration() =>
        Assert.Throws<InputShapeException>(() => Text.Split(null!, by: "bogus"));

    [Fact]
    public void SplitUnderATraceReportsANonListWithTheTypedError()
    {
        using var t = Trace.Begin();
        Assert.Throws<InputShapeException>(() => Text.Split(null!));
        Assert.Empty(t.Entries); // nothing was run, so nothing is recorded
    }

    [Fact]
    public void SplitDoesNotMutateItsInputForAnyMode()
    {
        Records records = [R("text", "a\n\nb\nc", "meta", R("k", L(1L)))];
        var before = Tokens.PythonJson(records);
        Text.Split(records);
        Text.Split(records, by: "paragraphs");
        Text.Split(records, by: "size", size: 2);
        Assert.Equal(before, Tokens.PythonJson(records));
    }

    [Fact]
    public void SplitIsTracedAndAnExpansionIsNotADrop()
    {
        Records records =
        [
            R("id", "a", "text", "1\n2\n3"), R("id", "b", "text", ""),
            R("id", "c", "text", "z"), R("text", "no id\nhere"),
        ];
        using var t = Trace.Begin("id");
        var output = Text.Split(records);
        var entry = t.Entries[0];
        Assert.Equal(("split", 4, output.Count), (entry.Stage, entry.InCount, entry.OutCount));
        Assert.Equal(3 + 1 + 2, output.Count); // a: 3 chunks, b: none, c: 1, no-id: 2
        // b vanished (documented) and is reported; a and c were expanded or kept
        Assert.Equal(new List<object?> { "b" }, entry.DroppedIds);
    }

    [Fact]
    public void TracedKeepsIdsMakesAttributionExactAndTheDefaultIsUnchanged()
    {
        // a stage that expands an id-less record into two and drops the record "b"
        Records ExpandAndDrop() => [R("t", "x"), R("t", "y"), R("id", "a")];
        Records records = [R("id", "a"), R("id", "b"), R("t", "one")];
        using var t = Trace.Begin("id");
        Trace.Traced("exact", records, ExpandAndDrop, keepsIds: true);
        Trace.Traced("default", records, ExpandAndDrop);
        // exact: "b" has no survivor, so it is reported; the default rule explains
        // it away as an id lost by one of the id-less records the stage added
        Assert.Equal(new List<object?> { "b" }, t.Entries[0].DroppedIds);
        Assert.Empty(t.Entries[1].DroppedIds);
    }

    [Fact]
    public void SplitStagePoliciesArePartOfTheFingerprint()
    {
        static string Fp(string by, int? size) => new Pipeline(
            new Stage("split", r => Text.Split(r, by: by, size: size),
                      new Rec { ["by"] = by, ["size"] = size.HasValue ? (long)size.Value : null }))
            .Fingerprint;

        Assert.Equal(Fp("size", 3), Fp("size", 3));
        Assert.NotEqual(Fp("size", 3), Fp("size", 4));
        Assert.NotEqual(Fp("lines", null), Fp("paragraphs", null));
    }

    [Fact]
    public void SplitRunsInAStrictPipelineAndStrictChangesNothing()
    {
        const string text = "a\nb\n\nc";
        Stage[] stages =
        [
            new Stage("split", r => Text.Split(r, by: "paragraphs")),
            new Stage("dedupe", r => Stages.Dedupe(r, "text")),
        ];
        Same(new Pipeline(stages, strict: true).Run(Text.AsRecords(text)),
             new Pipeline(stages).Run(Text.AsRecords(text)));
    }

    [Fact]
    public void AnOffRampInsideAStrictPipelineNamesTheStage()
    {
        // Join returns a string, so it belongs OUTSIDE the pipeline (docs); a stage
        // that hands the next one anything but a list is named by strict mode
        var pipe = new Pipeline(
            [
                new Stage("split", r => Text.Split(r)),
                new Stage("join", r => { Text.Join(r); return null!; }),
            ], strict: true);
        Code<InputShapeException>(() => pipe.Run(Text.AsRecords("a\nb")), "input.not_list", "join");
    }

    [Fact]
    public void CheckedAlwaysValidatesWithoutStrictMode()
    {
        Assert.False(Strict.IsActive);
        Code<InputShapeException>(
            () => Strict.CheckRecords<Rec>(null, "always", mapping: true, always: true),
            "input.not_list", "always");
        var e = Code<InputShapeException>(
            () => Strict.CheckRecords([R("a", 1L), null!], "always", mapping: true, always: true),
            "input.not_mapping", "always");
        Assert.Contains("item 1", e.Message);
        // a stage that never indexes an item does not need one
        Strict.CheckRecords([R("a", 1L), null!], "always", mapping: false, always: true);
        // without always and without strict mode nothing is checked
        Strict.CheckRecords<Rec>(null, "lenient", mapping: true);
        Strict.CheckRecords(new Records { null! }, "lenient", mapping: true);
        Strict.CheckRecords([R("a", 1L)], "always", mapping: true, always: true);
    }

    // --------------------------------------------------------------- Join ----

    [Fact]
    public void JoinSkipsMissingKeepsStringsAndSerializesTheRest()
    {
        Records records =
        [
            R("text", "a"), R("other", 1L), R("text", R("k", 1L)), R("text", L(1L, "x")),
            R("text", null), R("text", true), R("text", 2.5),
        ];
        Assert.Equal("a|{\"k\": 1}|[1, \"x\"]|null|true|2.5", Text.Join(records, sep: "|"));
        Assert.Equal("a{\"k\": 1}[1, \"x\"]nulltrue2.5", Text.Join(records));
    }

    [Fact]
    public void JoinFieldSepAndEmpty()
    {
        Assert.Equal("x\ny", Text.Join([R("body", "x"), R("text", "no"), R("body", "y")], "body", "\n"));
        Assert.Equal("", Text.Join([]));
        Assert.Equal("", Text.Join([R("other", 1L)]));
        Assert.Equal("-", Text.Join([R("text", ""), R("text", "")], sep: "-"));
    }

    [Fact]
    public void JoinRendersNonStringsWithTheActiveSerializer()
    {
        var output = Tokens.Scoped(
            new Tokens.Scope(Serializer: v => v is Rec ? "<dict>" : "<other>"),
            () => Text.Join([R("text", R("k", 1L)), R("text", "s"), R("text", 7L)], sep: " "));
        Assert.Equal("<dict> s <other>", output);
    }

    [Fact]
    public void JoinChecksItsInputInEveryMode()
    {
        Assert.False(Strict.IsActive);
        Code<InputShapeException>(() => Text.Join(null!), "input.not_list", "join");
        Code<InputShapeException>(() => Text.Join([R("text", "a"), null!]), "input.not_mapping", "join");
        Assert.Equal("ab", Text.Join([R("text", "a"), R("text", "b")]));
    }

    [Fact]
    public void JoinChecksTheShapeBeforeTheConfiguration() =>
        Assert.Throws<InputShapeException>(() => Text.Join(null!, field: null!));

    [Fact]
    public void JoinFieldAndSepMustBeStrings()
    {
        Code<ConfigException>(() => Text.Join([R("text", "a")], field: null!),
                              "config.invalid_value", "join", "field");
        Code<ConfigException>(() => Text.Join([R("text", "a")], sep: null!),
                              "config.invalid_value", "join", "sep");
    }

    [Fact]
    public void JoinRoundTripsSplitForEveryMode()
    {
        string text = "line one\r\nline two\n\n\npara " + Astral + "\rlone cr\n" + EAcute;
        foreach (var (by, size) in new (string, int?)[] { ("lines", null), ("paragraphs", null), ("size", 5) })
            Assert.Equal(text, Text.Join(ChunksOf(text, by, size)));
    }

    // ------------------------------------------ properties (AC 11, 12) ----

    /// <summary>A tiny linear congruential generator (Knuth's MMIX constants).
    /// Deterministic on every runtime: System.Random's sequence is not part of
    /// its contract, ours never changes.</summary>
    private sealed class Lcg(ulong seed)
    {
        private ulong _state = seed;

        private uint Next()
        {
            _state = unchecked(_state * 6364136223846793005UL + 1442695040888963407UL);
            return (uint)(_state >> 33);
        }

        /// <summary>An integer in [lo, hi].</summary>
        public int Between(int lo, int hi) => lo + (int)(Next() % (uint)(hi - lo + 1));
    }

    private const long DefaultSeed = 20261119;
    private const int DefaultCases = 200;

    private static long BaseSeed() =>
        long.TryParse(Environment.GetEnvironmentVariable("CONTEXEL_PROP_SEED"), out var s) ? s : DefaultSeed;

    private static int CaseCount() =>
        int.TryParse(Environment.GetEnvironmentVariable("CONTEXEL_PROP_CASES"), out var n) ? n : DefaultCases;

    private static IEnumerable<long> Seeds()
    {
        long b = BaseSeed();
        for (int i = 0; i < CaseCount(); i++) yield return b + i;
    }

    /// <summary>The run's seeds, then the default ones: whether a check CAN fail
    /// must not depend on how small a reproduction run is.</summary>
    private static IEnumerable<long> CanarySeeds()
    {
        foreach (var s in Seeds()) yield return s;
        for (int i = 0; i < DefaultCases; i++) yield return DefaultSeed + i;
    }

    private static readonly string[] Alphabet =
        ["a", "b", " ", "\n", "\n", "\r", "\r\n", "\r\n", "\n\n", Astral, EAcute, "x"];

    private static string RandomText(Lcg rng)
    {
        int pieces = rng.Between(0, 40);
        return string.Concat(Enumerable.Range(0, pieces).Select(_ => Alphabet[rng.Between(0, Alphabet.Length - 1)]));
    }

    /// <summary>A promise of Split that did not hold (the check itself failing,
    /// as opposed to the test harness).</summary>
    private sealed class CheckFailed(string message) : Exception(message);

    private static void Need(bool ok, string message)
    {
        if (!ok) throw new CheckFailed(message);
    }

    private static int Count(string s, char ch) => s.Count(x => x == ch);

    private static readonly Regex ParagraphRun = new(@"(?:\r?\n){2,}", RegexOptions.CultureInvariant);

    /// <summary>Every promise of Split about one text; throws CheckFailed.</summary>
    private static void CheckSplit(string text, string by, int? size, Records chunks)
    {
        var all = CodePoints(text);
        Need(string.Concat(chunks.Select(c => (string)c["text"]!)) == text, "chunks do not rebuild the text");
        Need(chunks.Select(c => Where(c).Index).SequenceEqual(Enumerable.Range(0, chunks.Count).Select(i => (long)i)),
             "bad index");
        long position = 0;
        foreach (var c in chunks)
        {
            var (_, start, end) = Where(c);
            Need(start == position && end > start, "offsets are not contiguous");
            Need(end <= all.Length && FromCodePoints(all, (int)start, (int)end) == (string)c["text"]!,
                 "offsets do not index the text");
            position = end;
        }
        Need(position == all.Length, "offsets do not cover the text");
        var body = chunks.Take(Math.Max(0, chunks.Count - 1)).ToList();
        if (by == "lines")
        {
            foreach (var c in body)
            {
                var t = (string)c["text"]!;
                Need(t.EndsWith('\n') && Count(t, '\n') == 1, "line boundary");
            }
            if (chunks.Count > 0) Need(Count((string)chunks[^1]["text"]!, '\n') <= 1, "line boundary");
        }
        else if (by == "paragraphs")
        {
            foreach (var c in chunks)
            {
                var m = ParagraphRun.Match((string)c["text"]!);
                Need(!m.Success || m.Index + m.Length == ((string)c["text"]!).Length, "paragraph boundary");
            }
            foreach (var c in body) Need(ParagraphRun.IsMatch((string)c["text"]!), "paragraph boundary");
        }
        else
        {
            foreach (var c in body) Need(CodePoints((string)c["text"]!).Length == size, "size boundary");
            if (chunks.Count > 0)
            {
                int last = CodePoints((string)chunks[^1]["text"]!).Length;
                Need(last >= 1 && last <= size, "size boundary");
            }
        }
    }

    [Fact]
    public void SplitIsLosslessAndItsOffsetsIndexBackForRandomTexts()
    {
        foreach (long seed in Seeds())
        {
            var rng = new Lcg((ulong)seed);
            string text = RandomText(rng);
            int size = rng.Between(1, 6);
            foreach (var (by, sz) in new (string, int?)[] { ("lines", null), ("paragraphs", null), ("size", size) })
            {
                try { CheckSplit(text, by, sz, ChunksOf(text, by, sz)); }
                catch (CheckFailed e) // name the seed, whatever failed
                {
                    throw new Xunit.Sdk.XunitException(
                        $"seed {seed} by={by} text={PyCompat.PyRepr(text)}: {e.Message}");
                }
            }
        }
    }

    private static Rec WithChunk(Rec c, long start, long end)
    {
        var chunk = new Rec((Rec)c["chunk"]!) { ["start"] = start, ["end"] = end };
        return new Rec(c) { ["chunk"] = chunk };
    }

    private static string WithoutLastCodePoint(string s) =>
        s.Length >= 2 && char.IsSurrogatePair(s, s.Length - 2) ? s[..^2] : s[..^1];

    private static readonly Dictionary<string, Func<Records, Records>> Corruptions = new()
    {
        ["drop_last_char"] = chunks => chunks.Select((c, i) => i == chunks.Count - 1
            ? new Rec(c) { ["text"] = WithoutLastCodePoint((string)c["text"]!) } : c).ToList(),
        ["shift_offsets"] = chunks => chunks.Select(c =>
            WithChunk(c, Where(c).Start + 1, Where(c).End + 1)).ToList(),
        ["reverse"] = chunks => Enumerable.Reverse(chunks).ToList(),
        ["cut_one_too_soon"] = chunks => chunks.Count == 0 ? chunks
            : chunks.Select((c, i) => i == 0
                ? new Rec(WithChunk(c, Where(c).Start, Where(c).End - 1))
                    { ["text"] = WithoutLastCodePoint((string)c["text"]!) }
                : c).ToList(),
    };

    [Theory]
    [InlineData("drop_last_char")]
    [InlineData("shift_offsets")]
    [InlineData("reverse")]
    [InlineData("cut_one_too_soon")]
    public void TheSplitCheckRejectsABrokenSplit(string corruption)
    {
        int caught = 0;
        foreach (long seed in CanarySeeds())
        {
            string text = RandomText(new Lcg((ulong)seed));
            if (CodePoints(text).Length < 4) continue;
            foreach (var (by, size) in new (string, int?)[] { ("lines", null), ("paragraphs", null), ("size", 2) })
            {
                var chunks = ChunksOf(text, by, size);
                CheckSplit(text, by, size, chunks); // the real split passes
                var broken = Corruptions[corruption](chunks);
                if (Tokens.PythonJson(broken) == Tokens.PythonJson(chunks))
                    continue; // nothing to corrupt on this text
                Assert.Throws<CheckFailed>(() => CheckSplit(text, by, size, broken));
                caught++;
            }
            if (caught > 0) return;
        }
        throw new Xunit.Sdk.XunitException("no seed produced a text the corruption could change");
    }

    [Fact]
    public void TheGeneratorIsDeterministic()
    {
        // pinned: a change of the sequence would silently change every property case
        var rng = new Lcg(20261119);
        Assert.Equal(new[] { 2, 6, 4, 6, 9, 8, 4, 6 }, Enumerable.Range(0, 8).Select(_ => rng.Between(0, 9)).ToArray());
        Assert.Equal(RandomText(new Lcg(1)), RandomText(new Lcg(1)));
    }

    // ------------------------------------------------- scale and adversarial ----

    // A generous guard against quadratic behavior, not a benchmark: a linear cut
    // of a million characters takes well under a second, a quadratic one far
    // longer than twenty, and a slow CI runner keeps a wide margin.
    private static readonly TimeSpan LinearGuard = TimeSpan.FromSeconds(20);

    private static void Within(TimeSpan limit, Action work, string what)
    {
        var watch = Stopwatch.StartNew();
        work();
        Assert.True(watch.Elapsed < limit, $"{what} took {watch.Elapsed.TotalMilliseconds:F0} ms");
    }

    [Fact]
    public void SplitCompletesOnAMillionCharactersAndRoundTrips()
    {
        string lines = string.Concat(Enumerable.Repeat("abcdefghi\n", 100_000)); // exactly 1,000,000
        Assert.Equal(1_000_000, lines.Length);
        Records c = [];
        Within(LinearGuard, () => c = ChunksOf(lines, "lines"), "lines");
        Assert.Equal(100_000, c.Count);
        Assert.Equal((999_990L, 1_000_000L), Spans(c)[^1]);
        Assert.Equal(lines, Text.Join(c));

        string paragraphs = string.Concat(Enumerable.Repeat("para\n\n", 166_666)) + "tail";
        Records p = [];
        Within(LinearGuard, () => p = ChunksOf(paragraphs, "paragraphs"), "paragraphs");
        Assert.Equal(166_667, p.Count);
        Assert.Equal(paragraphs, Text.Join(p));

        Records sized = [];
        Within(LinearGuard, () => sized = ChunksOf(lines, "size", 1000), "size");
        Assert.Equal(1000, sized.Count);
        Assert.Equal(lines, Text.Join(sized));
        Assert.Equal((999_000L, 1_000_000L), Spans(sized)[^1]);
    }

    [Fact]
    public void SplitCountsCodePointsOnAMillionAstralCharacters()
    {
        // 500,000 astral code points = 1,000,000 UTF-16 units: offsets must be
        // code points, and the cut must stay linear
        string text = string.Concat(Enumerable.Repeat(Astral, 500_000));
        Records c = [];
        Within(LinearGuard, () => c = ChunksOf(text, "size", 1000), "astral size");
        Assert.Equal(500, c.Count);
        Assert.Equal((499_000L, 500_000L), Spans(c)[^1]);
        Assert.Equal(text, Text.Join(c));
    }

    [Theory]
    [InlineData("\r")]
    [InlineData("\r\n")]
    [InlineData("\n\r")]
    [InlineData("\n")]
    [InlineData("a")]
    public void SplitStaysLinearOnAdversarialSeparators(string unit)
    {
        // a million characters of separators that almost match: must just complete
        string text = string.Concat(Enumerable.Repeat(unit, 1_000_000 / unit.Length));
        foreach (var by in new[] { "lines", "paragraphs", "size" })
        {
            Records chunks = [];
            Within(LinearGuard,
                   () => chunks = by == "size" ? ChunksOf(text, by, 7) : ChunksOf(text, by),
                   $"{PyCompat.PyRepr(unit)} by {by}");
            Assert.Equal(text, Text.Join(chunks));
        }
    }
}
