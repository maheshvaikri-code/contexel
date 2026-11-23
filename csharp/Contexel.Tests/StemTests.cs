using System.Globalization;
using System.Text.RegularExpressions;
using Xunit;

namespace Contexel.Tests;

/// <summary>The frozen English stemmer (ADR-006, docs/stemmer-rules.md):
/// mirrors tests/test_stem.py. <c>Stem.Of</c> is internal, so these tests reach
/// it through InternalsVisibleTo. Non-ASCII text is built with
/// char.ConvertFromUtf32 so no editor can rewrite it.</summary>
public class StemTests
{
    private static readonly string Astral = char.ConvertFromUtf32(0x1D49C); // one code point, two UTF-16 units
    private static readonly string EAcute = char.ConvertFromUtf32(0xE9);

    public static IEnumerable<object[]> Families() =>
    [
        [new[] { "parse", "parses", "parsed", "parsing" }],
        [new[] { "value", "values", "valued" }],
        [new[] { "query", "queries", "queried", "querying" }],
        [new[] { "try", "tries", "tried", "trying" }],
        [new[] { "file", "files", "filed", "filing" }],
        [new[] { "code", "codes", "coded", "coding" }],
        [new[] { "test", "tests", "tested", "testing" }],
        [new[] { "run", "runs", "running" }],
        [new[] { "stop", "stops", "stopped", "stopping" }],
        [new[] { "return", "returns", "returned", "returning" }],
        [new[] { "class", "classes" }],
        [new[] { "match", "matches", "matched", "matching" }],
        [new[] { "request", "requests", "requested", "requesting" }],
        [new[] { "error", "errors" }],
        [new[] { "index", "indexes", "indexed", "indexing" }],
        [new[] { "cache", "caches", "cached", "caching" }],
    ];

    [Theory]
    [MemberData(nameof(Families))]
    public void StemFamiliesUnify(string[] family) =>
        Assert.Single(family.Select(Stem.Of).Distinct());

    [Fact]
    public void TheParseFamilyStemsToPars() =>
        Assert.Equal(new[] { "pars", "pars", "pars", "pars" },
            new[] { "parse", "parses", "parsed", "parsing" }.Select(Stem.Of));

    // every rule, in the order the rules apply, with the word that exercises it
    [Theory]
    [InlineData("glasses", "glass")]       // sses
    [InlineData("queries", "query")]       // ies
    [InlineData("queried", "query")]       // ied
    [InlineData("tests", "test")]          // plural s
    [InlineData("testing", "test")]        // ing
    [InlineData("tested", "test")]         // ed
    [InlineData("stopped", "stop")]        // undoubling
    [InlineData("value", "valu")]          // final e
    [InlineData("ties", "tie")]            // ies, four letters: the plural s rule
    [InlineData("tied", "tied")]           // ied, four letters: no three-letter base
    [InlineData("class", "class")]         // ss is not a plural
    [InlineData("status", "status")]       // us is not a plural
    [InlineData("analysis", "analysis")]   // is is not a plural
    [InlineData("bus", "bus")]             // three letters or fewer
    [InlineData("need", "need")]           // base must keep three letters
    [InlineData("string", "string")]       // base must keep a vowel
    [InlineData("falling", "fall")]        // l is not undoubled
    [InlineData("passed", "pass")]         // s is not undoubled
    [InlineData("feeding", "feed")]        // only one of ing and ed is stripped
    [InlineData("2020s", "2020")]          // digits are letters to the rules
    public void EachRule(string word, string expected) => Assert.Equal(expected, Stem.Of(word));

    // documented in docs/stemmer-rules.md: the price of a small frozen rule set
    [Theory]
    [InlineData("configure", "configur")]
    [InlineData("config", "config")]
    [InlineData("speed", "spe")]
    [InlineData("news", "new")]
    [InlineData("using", "using")]
    [InlineData("series", "sery")]
    [InlineData("species", "specy")]
    [InlineData("bias", "bia")]
    public void StemDocumentedLimits(string word, string expected) => Assert.Equal(expected, Stem.Of(word));

    [Fact]
    public void StemExpectsLowerCaseInput()
    {
        Assert.Equal("PARSING", Stem.Of("PARSING"));
        Assert.Equal("Pars", Stem.Of("Parsing"));
    }

    [Fact]
    public void StemLeavesWordsOfThreeCodePointsOrFewerUnchanged()
    {
        var alphabet = "abcdefghijklmnopqrstuvwxyz0123456789".Select(c => c.ToString())
            .Concat([EAcute, Astral]).ToArray();
        Assert.Equal("", Stem.Of(""));
        foreach (var a in alphabet)
        {
            Assert.Equal(a, Stem.Of(a));
            foreach (var b in alphabet)
            {
                Assert.Equal(a + b, Stem.Of(a + b));
                foreach (var c in alphabet) Assert.Equal(a + b + c, Stem.Of(a + b + c));
            }
        }
    }

    [Fact]
    public void StemCountsCodePointsNotUtf16Units()
    {
        // an astral letter is ONE code point: these words are three to six
        // code points long, so the length rules treat them as the short words
        // they are
        Assert.Equal(Astral + "as", Stem.Of(Astral + "as"));
        Assert.Equal(Astral + "aing", Stem.Of(Astral + "aing"));
        Assert.Equal(Astral + "ie", Stem.Of(Astral + "ies"));
        Assert.Equal(Astral + Astral + "y", Stem.Of(Astral + Astral + "ies"));
        Assert.Equal(Astral + "aa", Stem.Of(Astral + "aaing"));
    }

    [Fact]
    public void StemComparesOrdinallySoIgnorableCharactersDoNotCount()
    {
        // a soft hyphen (U+00AD) is ignorable to a culture-sensitive EndsWith:
        // "tests" + soft hyphen would then look like it ends with "s"
        string softHyphen = char.ConvertFromUtf32(0xAD);
        Assert.Equal("tests" + softHyphen, Stem.Of("tests" + softHyphen));
        Assert.Equal("testing" + softHyphen, Stem.Of("testing" + softHyphen));
    }

    [Fact]
    public void StemIsTheSameUnderAnotherCulture()
    {
        CultureInfo turkish;
        try { turkish = new CultureInfo("tr-TR"); }
        catch (CultureNotFoundException) { return; } // invariant-globalization runtime: nothing to compare
        var saved = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = turkish;
            Assert.Equal("pars", Stem.Of("parsing"));
            Assert.Equal("test", Stem.Of("tests"));
            Assert.Equal("query", Stem.Of("queries"));
        }
        finally
        {
            CultureInfo.CurrentCulture = saved;
        }
    }

    [Fact]
    public void StemNeverThrowsAndNeverGrowsAWord()
    {
        // a small seeded generator of our own: the sequence is the same on every runtime
        uint state = 20261123;
        int Next(int n)
        {
            state = unchecked(state * 1103515245u + 12345u);
            return (int)((state >> 8) % (uint)n);
        }
        var alphabet = ("abcdefghijklmnopqrstuvwxyz" + "abcdefghijklmnopqrstuvwxyz" + "0123456789 _-" + "ABCSEING")
            .Select(c => c.ToString())
            .Concat([EAcute, char.ConvertFromUtf32(0x4E2D), char.ConvertFromUtf32(0x1F600), Astral, ((char)0xD800).ToString()])
            .ToArray();
        for (int i = 0; i < 50000; i++)
        {
            int n = Next(13);
            var word = string.Concat(Enumerable.Range(0, n).Select(_ => alphabet[Next(alphabet.Length)]));
            string stem = Stem.Of(word);
            Assert.True(stem.Length <= word.Length, word);
            Assert.Equal(word.Length == 0, stem.Length == 0);
        }
    }

    private static string FindUp(string relative)
    {
        string? dir = AppContext.BaseDirectory;
        while (dir is not null && !File.Exists(Path.Combine(dir, relative)))
            dir = Path.GetDirectoryName(dir);
        return dir is null
            ? throw new FileNotFoundException(relative + " not found above the test directory")
            : Path.Combine(dir, relative);
    }

    [Fact]
    public void StemIsNotPartOfThePublicApi()
    {
        // ruling S5-1: reached through Rescore(match: "stem"); no public type is called Stem
        Assert.DoesNotContain(typeof(Stages).Assembly.GetExportedTypes(), t => t.Name == "Stem");
    }

    [Fact]
    public void TheRuleTableExamplesAreWhatTheStemmerReturns()
    {
        string doc = File.ReadAllText(FindUp(Path.Combine("docs", "stemmer-rules.md"))).Replace("\r\n", "\n");
        var rows = Regex.Matches(doc, "^\\| `([^`]*)` \\| `([^`]*)` \\|$", RegexOptions.Multiline);
        Assert.True(rows.Count >= 40, "the rule document lost its worked examples");
        foreach (Match row in rows)
            Assert.Equal(row.Groups[2].Value, Stem.Of(row.Groups[1].Value));
    }
}
