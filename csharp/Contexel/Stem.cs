namespace Contexel;

/// <summary>
/// A small, frozen English suffix stemmer (ADR-006, docs/stemmer-rules.md) —
/// parity port of contexel's Python <c>stem</c> module.
///
/// <c>Rescore(match: "stem")</c> reduces every word to a stem before counting,
/// so <c>parse</c>, <c>parses</c>, <c>parsed</c> and <c>parsing</c> are one term.
/// The rules are a short, ordered list that Python and TypeScript repeat
/// exactly: the result is pinned by the shared vectors, never by "close
/// enough". The stemmer is FROZEN (a future improvement ships under a new
/// <c>match</c> name), English only, not a lemmatizer (<c>configure</c> and
/// <c>config</c> stay apart, <c>speed</c> becomes <c>spe</c>), and expects
/// lower-case input. Lengths are counted in code points, not UTF-16 units, and
/// every comparison is ordinal (a culture-sensitive <c>EndsWith</c> would skip
/// ignorable characters). It never throws and never makes a word longer. It is
/// not part of the public API: <c>Rescore</c> is how it is used.
/// </summary>
internal static class Stem
{
    // a doubled letter from this set loses one copy after "ing"/"ed" is
    // stripped (running -> run, stopped -> stop); "l", "s" and "z" keep both
    private const string Undouble = "bcdfghjkmnpqrtvwx";

    private static bool HasVowel(string text)
    {
        foreach (char c in text)
            if (c is 'a' or 'e' or 'i' or 'o' or 'u' or 'y') return true;
        return false;
    }

    private static bool Ends(string text, string suffix) =>
        text.EndsWith(suffix, StringComparison.Ordinal);

    /// <summary>The stem of an already lower-case <paramref name="word"/>.</summary>
    internal static string Of(string word)
    {
        if (PyCompat.CodePointLength(word) <= 3) return word;
        string w = word;
        // 1. plurals: the first rule that applies wins
        if (Ends(w, "sses"))
            w = w[..^2];
        else if (Ends(w, "ies") && PyCompat.CodePointLength(w) > 4)
            w = w[..^3] + "y";
        else if (Ends(w, "ied") && PyCompat.CodePointLength(w) > 4)
            w = w[..^3] + "y";
        else if (Ends(w, "s") && !(Ends(w, "ss") || Ends(w, "us") || Ends(w, "is")))
            w = w[..^1];
        // 2. "ing" or "ed", never both: the one the word ends with is the only
        //    one considered; it is stripped only if a vowel-bearing base of at
        //    least three code points remains
        string suffix = Ends(w, "ing") ? "ing" : Ends(w, "ed") ? "ed" : "";
        if (suffix.Length > 0)
        {
            string stripped = w[..^suffix.Length];
            if (PyCompat.CodePointLength(stripped) >= 3 && HasVowel(stripped))
            {
                w = stripped;
                char last = w[^1];
                if (last == w[^2] && Undouble.Contains(last)) w = w[..^1];
            }
        }
        // 3. a final "e"
        if (PyCompat.CodePointLength(w) > 3 && Ends(w, "e")) w = w[..^1];
        return w;
    }
}
