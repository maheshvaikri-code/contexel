using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace Contexel;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>
/// Deterministic context-economy stages — parity port of contexel's Python
/// stages module. Every stage takes and returns records, never mutates its
/// input, and is auto-traced when a trace is active. Behavior matches the
/// Python canon on the shared golden vectors (parity/vectors.json);
/// boundaries are documented in ADR-002.
/// </summary>
public static class Stages
{
    /* ---------------------------- fingerprints --------------------------- */

    /// <summary>Type-qualified fingerprint (1, 1.0, "1", and true all
    /// differ — C# preserves int/float, exceeding the TS port). Containers
    /// are type-tagged so {} and [] never collide (canon fix, 0.1.16).</summary>
    internal static string TypedKey(object? value) => value switch
    {
        null => "NoneType:None",
        bool b => "bool:" + (b ? "True" : "False"),
        long l => "int:" + l.ToString(CultureInfo.InvariantCulture),
        int i => "int:" + i.ToString(CultureInfo.InvariantCulture),
        // -0.0 == 0.0 in Python (equal dict keys): normalize before keying
        double d => "float:" + PyCompat.PyNumber(d == 0 ? 0.0 : d),
        string s => "str:" + Tokens.PythonJson(s),
        System.Collections.IDictionary dict =>
            "dict:{" + string.Join(",", dict.Keys.Cast<object>()
                .Select(k => Tokens.PythonJson((string)k) + ":" + TypedKey(dict[k]))
                .OrderBy(x => x, StringComparer.Ordinal)) + "}",
        System.Collections.IEnumerable seq =>
            "list:[" + string.Join(",", seq.Cast<object?>().Select(TypedKey)) + "]",
        _ => value.GetType().Name + ":" +
             Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture),
    };

    /* ------------------------------- stages ------------------------------ */

    // Order in every record stage (ADR-003): the strict shape check runs
    // FIRST, before Trace.Traced reads records.Count; configuration
    // validation runs inside the stage body.

    public static Records Select(Records records, object fields)
    {
        Strict.CheckRecords(records, "select", mapping: true);
        return Trace.Traced("select", records, () =>
        {
            var keep = Check.Fields(fields, "select");
            return records.Select(r =>
            {
                var output = new Rec();
                foreach (var k in keep)
                    if (r.TryGetValue(k, out var v)) output[k] = v;
                return output;
            }).ToList();
        });
    }

    public static Records Dedupe(Records records, object? key = null)
    {
        // a key indexes the item; without one the whole item is hashed
        Strict.CheckRecords(records, "dedupe", mapping: key is not null);
        return Trace.Traced("dedupe", records, () =>
        {
            List<string>? keys = key is null ? null : Check.Fields(key, "dedupe", "key");
            var seen = new HashSet<string>();
            var output = new Records();
            foreach (var r in records)
            {
                object? basis = keys is null
                    ? r
                    : keys.Select(k => r.TryGetValue(k, out var v) ? v : null).ToList<object?>();
                string fp = TypedKey(basis);
                if (seen.Add(fp)) output.Add(r);
            }
            return output;
        });
    }

    /// <summary>Provenance gate. A bare string for <c>allowed</c> is ONE
    /// value (this overload); see the list overload for the rest.</summary>
    public static Records Allowlist(Records records, string field, string allowed) =>
        AllowlistCore(records, field, allowed is null ? null : [allowed]);

    /// <summary>Provenance gate: keep only records whose <c>field</c> value
    /// is in <c>allowed</c>. A bool never equals a number (<c>true</c> does
    /// not pass <c>allowed=[1]</c>); int and float compare by value. Fail
    /// closed: a record carrying an unhashable value (a dict or list) is
    /// dropped; a missing field reads as null — dropped unless null is
    /// explicitly allowed. An unhashable entry in <c>allowed</c> throws
    /// <see cref="ConfigException"/> (<c>config.invalid_value</c>).</summary>
    public static Records Allowlist(Records records, string field, IEnumerable<object?> allowed) =>
        AllowlistCore(records, field, allowed);

    private static Records AllowlistCore(Records records, string field, IEnumerable<object?>? allowed)
    {
        Strict.CheckRecords(records, "allowlist", mapping: true);
        return Trace.Traced("allowlist", records, () =>
        {
            Check.Str(field, "allowlist", "field");
            if (allowed is null)
                throw Check.InvalidValue("allowlist", "allowed",
                    "allowed must be a string or a list of values, got null");
            // Python builds the set up front: unhashable entries raise
            HashSet<string> allowedKeys;
            try { allowedKeys = new HashSet<string>(allowed.Select(PyCompat.AllowKey)); }
            catch (ArgumentException)
            {
                throw Check.InvalidValue("allowlist", "allowed",
                    "allowed contains an unhashable value");
            }
            return records.Where(r =>
            {
                // r.get(field): missing reads as None, which may be allowed;
                // unhashable record values fail closed
                var v = r.TryGetValue(field, out var x) ? x : null;
                try { return allowedKeys.Contains(PyCompat.AllowKey(v)); }
                catch (ArgumentException) { return false; }
            }).ToList();
        });
    }

    internal static readonly string[] InjectionPatterns =
    [
        @"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|messages|prompts|context)",
        @"disregard\s+(?:all\s+|the\s+)?(?:previous|prior|above|earlier)",
        @"you\s+are\s+now\s+",
        @"new\s+instructions\s*:",
        @"system\s+prompt",
        @"</?\s*(?:system|assistant|instructions?)\s*>",
    ];

    // the built-ins are trusted and compiled together, once; every caller
    // pattern is compiled on its own so it cannot change how they are read
    private static readonly Regex BuiltInMatcher =
        new(string.Join("|", InjectionPatterns),
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    /// <summary>The text a quarantine pattern is matched against for one
    /// field value (mirror of Python's <c>_scan_text</c>). A string is used
    /// as is. A container contributes its dict keys (code-point order) then
    /// values, and list items in order; every leaf as text, joined by ONE
    /// space — so a marker split by a newline or a quote inside a nested
    /// value is still found. Scalars render like Python <c>str()</c> (null is
    /// "None", true is "True"). Iterative, and each container is expanded at
    /// most once (reference identity), so neither a deeply nested nor a
    /// self-referencing value can exhaust the stack or loop.</summary>
    internal static string ScanText(object? value)
    {
        var parts = new List<string>();
        var stack = new Stack<object?>();
        stack.Push(value);
        var seen = new HashSet<object>(ReferenceEqualityComparer.Instance);
        while (stack.Count > 0)
        {
            var v = stack.Pop();
            switch (v)
            {
                case string s:
                    parts.Add(s);
                    break;
                case System.Collections.IDictionary dict:
                {
                    if (!seen.Add(dict)) break;
                    var keys = dict.Keys.Cast<object>()
                        .Select(k => (Text: k as string ?? PyCompat.PyStr(k), Key: k))
                        .ToList();
                    // ascending by code point, popped in that order: each key
                    // text, then its value
                    keys.Sort((a, b) => PyCompat.CompareCodePoints(a.Text, b.Text));
                    for (int i = keys.Count - 1; i >= 0; i--)
                    {
                        stack.Push(dict[keys[i].Key]);
                        stack.Push(keys[i].Text);
                    }
                    break;
                }
                case System.Collections.IEnumerable seq:
                {
                    if (!seen.Add(seq)) break;
                    var items = seq.Cast<object?>().ToList();
                    for (int i = items.Count - 1; i >= 0; i--) stack.Push(items[i]);
                    break;
                }
                default:
                    parts.Add(PyCompat.PyStr(v));
                    break;
            }
        }
        return string.Join(" ", parts);
    }

    /// <summary>Drops or flags records whose scanned text matches a built-in or
    /// custom pattern. <c>normalize: "nfc"</c> widens detection and never
    /// narrows it: the text is scanned as given and also in its Unicode NFC
    /// form, and a record is hit if either matches (so a marker typed with a
    /// precomposed character is also found in its decomposed spelling). It
    /// never touches the patterns; the default (null) scans the text as it is;
    /// any other value raises <see cref="ConfigException"/>. NFC costs time that
    /// grows with the square of a long run of combining marks of two different
    /// kinds: cap the size of text you do not control (README, "Matching:
    /// stems and Unicode forms").</summary>
    public static Records Quarantine(Records records, object? fields = null,
                                     object? patterns = null, string action = "drop",
                                     string into = "quarantined",
                                     bool replacePatterns = false,
                                     string? normalize = null)
    {
        Strict.CheckRecords(records, "quarantine", mapping: true);
        return Trace.Traced("quarantine", records, () =>
        {
            if (action is not ("drop" or "flag"))
                throw new ConfigException("config.invalid_value",
                    $"action must be 'drop' or 'flag', got '{action}'",
                    "quarantine", "action");
            // fields=[] would scan nothing: a configured-looking control that
            // does nothing is exactly what this stage refuses to be
            var fieldNames = Check.Fields(fields ?? new[] { "snippet" }, "quarantine",
                                          allowEmpty: false);
            Check.Str(into, "quarantine", "into");
            bool nfc = Check.Normalize(normalize, "quarantine") is not null;
            // custom patterns EXTEND the built-ins: domain markers must never
            // silently disable "ignore all previous instructions" detection;
            // replacePatterns is the explicit opt-out
            List<Regex> matchers;
            if (patterns is null)
            {
                if (replacePatterns)
                    throw new ConfigException("config.contradictory",
                        "replacePatterns without patterns is contradictory; pass the replacement patterns",
                        "quarantine", "replacePatterns");
                matchers = [BuiltInMatcher];
            }
            else
            {
                var userPatterns = Check.Fields(patterns, "quarantine", "patterns");
                if (userPatterns.Any(string.IsNullOrEmpty))
                    throw new ConfigException("config.empty",
                        "empty pattern fragments match everything; remove them",
                        "quarantine", "patterns");
                var compiled = new List<Regex>();
                foreach (var p in userPatterns)
                {
                    try // each pattern alone: its options and groups stay its own
                    {
                        compiled.Add(new Regex(p,
                            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant));
                    }
                    catch (ArgumentException e)
                    {
                        throw new ConfigException("config.invalid_pattern",
                            $"quarantine: invalid pattern {PyCompat.PyRepr(p)}: {e.Message}",
                            "quarantine", "patterns");
                    }
                }
                matchers = replacePatterns
                    ? compiled
                    : [BuiltInMatcher, .. compiled];
            }
            if (matchers.Count == 0)
                throw new ConfigException("config.empty",
                    "replacePatterns with no patterns would disable the control entirely; pass at least one pattern",
                    "quarantine", "patterns");
            var output = new Records();
            int index = 0;
            foreach (var r in records)
            {
                // fail closed: skipping an item this screen cannot read would
                // KEEP it, so a non-mapping item (only null in C#) always
                // raises, drop or flag mode, strict mode or not
                if (r is null)
                    throw new InputShapeException("input.not_mapping",
                        $"quarantine: item {index} must be a mapping, got null",
                        "quarantine");
                string text = string.Join(" ", fieldNames.Select(f =>
                    r.TryGetValue(f, out var v) ? ScanText(v) : ""));
                bool hit = matchers.Any(m => m.IsMatch(text));
                if (!hit && nfc)
                {
                    // widen only (ADR-006): the raw text was scanned first, so
                    // normalizing can add a detection but never hide one
                    string composed = PyCompat.NormalizeNfc(text);
                    if (!string.Equals(composed, text, StringComparison.Ordinal))
                        hit = matchers.Any(m => m.IsMatch(composed));
                }
                if (action == "flag")
                {
                    // continuing would silently overwrite the caller's data
                    if (r.ContainsKey(into))
                        throw new InputShapeException("input.field_conflict",
                            $"quarantine: record {index} already has a {PyCompat.PyRepr(into)} field; pass a different into",
                            "quarantine", "into");
                    output.Add(new Rec(r) { [into] = hit });
                }
                else if (!hit) output.Add(r);
                index++;
            }
            return output;
        });
    }

    // Python's [^\W_] on ASCII; exotic Unicode word classes are a margin
    private static readonly Regex Word =
        new(@"[\p{L}\p{N}]+", RegexOptions.CultureInvariant);

    /// <summary>Replaces the tool's relevance score with a deterministic lexical
    /// one (BM25 style, computed inside the batch) and writes it to
    /// <paramref name="into"/> on a copy of each record; use before
    /// <see cref="Rank(Records, string, bool)"/>.</summary>
    /// <param name="records">The records to score.</param>
    /// <param name="query">A string or a list of strings.</param>
    /// <param name="fields">The text fields to read (default <c>snippet</c>).</param>
    /// <param name="into">The field that receives the score.</param>
    /// <param name="proximity">Add a bonus for consecutive query terms in order
    /// within an 80-character window.</param>
    /// <param name="match"><c>"word"</c> (default) counts exact words;
    /// <c>"substring"</c> counts raw substrings; <c>"stem"</c> reduces every word
    /// of the query and of the text to its stem with the frozen English stemmer
    /// (see the README). Any other value throws <see cref="ConfigException"/>.</param>
    /// <param name="normalize"><c>null</c> (default) changes nothing; <c>"nfc"</c>
    /// applies Unicode NFC to the query and the text before lower-casing; any
    /// other value throws <see cref="ConfigException"/>. NFC costs time that grows
    /// with the square of a long run of combining marks of two different kinds:
    /// cap the size of text you do not control (README, "Matching: stems and
    /// Unicode forms").</param>
    public static Records Rescore(Records records, object query, object? fields = null,
                                  string into = "score", bool proximity = true,
                                  string match = "word", string? normalize = null)
    {
        Strict.CheckRecords(records, "rescore", mapping: true);
        return RescoreBody(records, query, fields, into, proximity, match, normalize);
    }

    private static Records RescoreBody(Records records, object query, object? fields,
                                       string into, bool proximity, string match,
                                       string? normalize) =>
        Trace.Traced("rescore", records, () =>
        {
            var validQuery = Check.Query(query, "rescore"); // materialized once
            var fieldNames = Check.Fields(fields ?? new[] { "snippet" }, "rescore",
                                          allowEmpty: false);
            Check.Str(into, "rescore", "into");
            Check.Choice(match, "rescore", "match", "word", "substring", "stem");
            bool nfc = Check.Normalize(normalize, "rescore") is not null;
            // NFC first, then lower-case (ADR-006)
            string Prepare(string text) =>
                (nfc ? PyCompat.NormalizeNfc(text) : text).ToLowerInvariant();
            var rawTerms = (validQuery switch
            {
                string q => Word.Matches(Prepare(q)).Select(m => m.Value),
                // Python: str(part) for each element of the list
                System.Collections.IEnumerable qs => qs.Cast<object?>().SelectMany(p =>
                    Word.Matches(Prepare(PyCompat.PyStr(p))).Select(m => m.Value)),
                _ => throw Check.InvalidValue("rescore", "query",
                    "query must be a string or a list of strings"),
            }).ToList();
            var terms = (match == "stem" ? rawTerms.Select(Stem.Of) : rawTerms).Distinct().ToList();
            if (terms.Count == 0 || records.Count == 0)
                return records.Select(r => new Rec(r) { [into] = 0.0 }).ToList();

            var texts = records.Select(r => Prepare(string.Join(" ", fieldNames.Select(f =>
                r.TryGetValue(f, out var v) ? PyCompat.PyStr(v) : "")))).ToList();

            Regex? finder = null;
            if (match == "word")
            {
                string alt = string.Join("|", terms
                    .OrderByDescending(t => t.Length)
                    .Select(Regex.Escape));
                // boundary guards: underscore counts as a boundary
                finder = new Regex($@"(?<![\p{{L}}\p{{N}}])(?:{alt})(?![\p{{L}}\p{{N}}])",
                                   RegexOptions.CultureInvariant);
            }

            int n = records.Count;
            var tfs = new List<Dictionary<string, int>>();
            var firsts = new List<Dictionary<string, int>>();
            var df = terms.ToDictionary(t => t, _ => 0);
            foreach (var text in texts)
            {
                // Python positions are code points; .NET Match.Index is UTF-16
                var toCp = PyCompat.CodePointIndexer(text);
                var row = new Dictionary<string, int>();
                var first = new Dictionary<string, int>();
                if (finder is not null)
                {
                    foreach (Match m in finder.Matches(text))
                    {
                        string t = m.Value;
                        row[t] = row.GetValueOrDefault(t) + 1;
                        if (!first.ContainsKey(t)) first[t] = toCp(m.Index);
                    }
                }
                else if (match == "stem")
                {
                    foreach (Match m in Word.Matches(text))
                    {
                        string t = Stem.Of(m.Value);
                        if (!df.ContainsKey(t)) continue;
                        row[t] = row.GetValueOrDefault(t) + 1;
                        if (!first.ContainsKey(t)) first[t] = toCp(m.Index);
                    }
                }
                else
                {
                    foreach (var t in terms)
                    {
                        int idx = text.IndexOf(t, StringComparison.Ordinal);
                        int cnt = 0, firstIdx = idx;
                        while (idx != -1)
                        {
                            cnt++;
                            // Python str.count is NON-overlapping: advance
                            // past the whole match ("aaaa".count("aa") == 2)
                            idx = text.IndexOf(t, idx + t.Length, StringComparison.Ordinal);
                        }
                        if (cnt > 0) { row[t] = cnt; first[t] = toCp(firstIdx); }
                    }
                }
                foreach (var t in row.Keys) df[t] += 1;
                tfs.Add(row);
                firsts.Add(first);
            }
            var idf = terms.ToDictionary(t => t,
                t => Math.Log((n - df[t] + 0.5) / (df[t] + 0.5) + 1.0));

            const double k1 = 1.5;
            const int window = 80;
            return records.Select((r, i) =>
            {
                var row = tfs[i];
                var first = firsts[i];
                double score = 0;
                foreach (var (t, tf) in row) score += idf[t] * (tf / (tf + k1));
                if (proximity && row.Count > 1)
                {
                    for (int j = 0; j + 1 < terms.Count; j++)
                    {
                        string t1 = terms[j], t2 = terms[j + 1];
                        if (first.TryGetValue(t1, out int p1) && first.TryGetValue(t2, out int p2))
                        {
                            int gap = p2 - p1;
                            if (gap > 0 && gap <= window) score += (idf[t1] + idf[t2]) / 4;
                        }
                    }
                }
                // Python's score starts as int 0 and becomes float only when
                // a term contributes: a no-match record carries int 0, which
                // serializes "0", not "0.0" — C# preserves that distinction
                // explicit boxing: the ternary would otherwise unify long
                // and double to double, silently turning 0 into 0.0
                object scoreValue = row.Count == 0 ? 0L : (object)PyCompat.PyRound(score, 6);
                return new Rec(r) { [into] = scoreValue };
            }).ToList();
        });

    public static Records Rank(Records records, string by, bool desc = true)
    {
        // a field name indexes every item (a key function takes anything)
        Strict.CheckRecords(records, "rank", mapping: true);
        return Trace.Traced("rank", records, () =>
        {
            if (by is null)
                throw Check.InvalidValue("rank", "by",
                    "by must be a field name or a key function, got null");
            var present = records.Where(r => r.ContainsKey(by)).ToList();
            var missing = records.Where(r => !r.ContainsKey(by)).ToList();
            return StableSort(present, r => r[by], desc).Concat(missing).ToList();
        });
    }

    public static Records Rank(Records records, Func<Rec, object?> by, bool desc = true)
    {
        Strict.CheckRecords(records, "rank", mapping: false);
        return Trace.Traced("rank", records, () =>
        {
            if (by is null)
                throw Check.InvalidValue("rank", "by",
                    "by must be a field name or a key function, got null");
            return StableSort(records, by, desc);
        });
    }

    // LINQ OrderBy is stable (List.Sort is NOT); a directional comparator
    // with a stable sort keeps ties in original order like Python
    // sorted(key=..., reverse=...). OrderBy wraps comparer exceptions in
    // InvalidOperationException — unwrap so incomparable values raise
    // ArgumentException like Python's TypeError.
    private static Records StableSort(Records records, Func<Rec, object?> keyOf, bool desc)
    {
        int dir = desc ? -1 : 1;
        var comparer = Comparer<object?>.Create((a, b) => dir * PyCompat.PyCompare(a, b));
        try
        {
            return records.OrderBy(keyOf, comparer).ToList();
        }
        catch (InvalidOperationException e) when (e.InnerException is ArgumentException inner)
        {
            throw new ArgumentException(inner.Message, inner);
        }
    }

    private static string TruncateText(string text, int maxTokens,
                                       Func<string, int>? tokenizer, string suffix)
    {
        if (Tokens.Count(text, tokenizer) <= maxTokens) return text;
        int budget = Math.Max(1, maxTokens - Tokens.Count(suffix, tokenizer));
        if (Tokens.IsHeuristic(tokenizer))
        {
            // ceil(len/4) is invertible: longest fitting prefix = 4*budget
            // code points (Python slices by code points, so must we)
            return PyCompat.PyRstrip(PyCompat.CodePointSlice(text, 4 * budget)) + suffix;
        }
        int lo = 0, hi = PyCompat.CodePointLength(text);
        while (lo < hi)
        {
            int mid = (lo + hi + 1) >> 1;
            if (Tokens.Count(PyCompat.CodePointSlice(text, mid), tokenizer) <= budget) lo = mid;
            else hi = mid - 1;
        }
        return PyCompat.PyRstrip(PyCompat.CodePointSlice(text, lo)) + suffix;
    }

    public static Records TruncateField(Records records, string field, int maxTokens,
                                        Func<string, int>? tokenizer = null,
                                        string suffix = "…")
    {
        Strict.CheckRecords(records, "truncate_field", mapping: true);
        return Trace.Traced("truncate_field", records, () =>
        {
            Check.Str(field, "truncate_field", "field");
            Check.NonNegativeInt(maxTokens, "truncate_field", "maxTokens");
            Check.Str(suffix, "truncate_field", "suffix");
            return records.Select(r =>
            {
                if (!r.TryGetValue(field, out var v) || v is not string s) return r;
                return new Rec(r) { [field] = TruncateText(s, maxTokens, tokenizer, suffix) };
            }).ToList();
        });
    }

    public static Records TrimToBudget(Records records, int maxTokens,
                                       Func<string, int>? tokenizer = null,
                                       int minRecords = 0)
    {
        Strict.CheckRecords(records, "trim_to_budget", mapping: false);
        return TrimBody(records, maxTokens, tokenizer, minRecords);
    }

    private static Records TrimBody(Records records, int maxTokens,
                                    Func<string, int>? tokenizer, int minRecords) =>
        Trace.Traced("trim_to_budget", records, () =>
        {
            Check.NonNegativeInt(maxTokens, "trim_to_budget", "maxTokens");
            Check.NonNegativeInt(minRecords, "trim_to_budget", "minRecords");
            // minRecords guards the silent-failure edge: a too-small budget
            // would return [], indistinguishable from "nothing matched"
            var output = new Records();
            int used = 0;
            foreach (var r in records)
            {
                int cost = Tokens.Count(r, tokenizer) + 2; // list framing
                if (used + cost > maxTokens && output.Count >= minRecords) break;
                output.Add(r);
                used += cost;
            }
            return output;
        });

    /// <summary>Combiner (not auto-traced, matching Python): normalize and
    /// concatenate record lists from different tools; schema maps unified
    /// name -> source name or candidate list (first match wins).</summary>
    public static Records Merge(IEnumerable<Records> sources,
                               Dictionary<string, object>? schema = null,
                               string? dedupeKey = null)
    {
        var combined = new Records();
        foreach (var src in sources)
        {
            foreach (var r in src)
            {
                if (schema is null) { combined.Add(r); continue; }
                var mapped = new Rec();
                foreach (var (unified, candidates) in schema)
                {
                    List<string> names = candidates switch
                    {
                        string one => [one],
                        IEnumerable<string> many => many.ToList(),
                        _ => throw new ArgumentException("schema values must be a string or a sequence of strings"),
                    };
                    foreach (var name in names)
                    {
                        if (r.TryGetValue(name, out var v)) { mapped[unified] = v; break; }
                    }
                }
                combined.Add(mapped);
            }
        }
        return dedupeKey is null ? combined : Dedupe(combined, dedupeKey);
    }
}
