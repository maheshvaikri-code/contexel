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
    /// <summary>A bare string names ONE field, never its characters.</summary>
    private static List<string> FieldList(object fields) => fields switch
    {
        string s => [s],
        IEnumerable<string> seq => seq.ToList(),
        _ => throw new ArgumentException("fields must be a string or a sequence of strings"),
    };

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

    public static Records Select(Records records, object fields) =>
        Trace.Traced("select", records, () =>
        {
            var keep = FieldList(fields);
            return records.Select(r =>
            {
                var output = new Rec();
                foreach (var k in keep)
                    if (r.TryGetValue(k, out var v)) output[k] = v;
                return output;
            }).ToList();
        });

    public static Records Dedupe(Records records, object? key = null) =>
        Trace.Traced("dedupe", records, () =>
        {
            List<string>? keys = key is null ? null : FieldList(key);
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

    public static Records Allowlist(Records records, string field, IEnumerable<object?> allowed) =>
        Trace.Traced("allowlist", records, () =>
        {
            // Python builds set(allowed) up front: unhashable entries raise
            var allowedKeys = new HashSet<string>(allowed.Select(PyCompat.PyEqKey));
            return records.Where(r =>
            {
                // r.get(field): missing reads as None, which may be allowed;
                // unhashable record values fail closed
                var v = r.TryGetValue(field, out var x) ? x : null;
                try { return allowedKeys.Contains(PyCompat.PyEqKey(v)); }
                catch (ArgumentException) { return false; }
            }).ToList();
        });

    internal static readonly string[] InjectionPatterns =
    [
        @"ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|messages|prompts|context)",
        @"disregard\s+(?:all\s+|the\s+)?(?:previous|prior|above|earlier)",
        @"you\s+are\s+now\s+",
        @"new\s+instructions\s*:",
        @"system\s+prompt",
        @"</?\s*(?:system|assistant|instructions?)\s*>",
    ];

    public static Records Quarantine(Records records, object? fields = null,
                                     object? patterns = null, string action = "drop",
                                     string into = "quarantined",
                                     bool replacePatterns = false) =>
        Trace.Traced("quarantine", records, () =>
        {
            if (action is not ("drop" or "flag"))
                throw new ArgumentException($"action must be 'drop' or 'flag', got '{action}'");
            var fieldNames = FieldList(fields ?? new[] { "snippet" });
            // custom patterns EXTEND the built-ins: domain markers must never
            // silently disable "ignore all previous instructions" detection;
            // replacePatterns is the explicit opt-out
            List<string> patternList;
            if (patterns is null)
            {
                if (replacePatterns)
                    throw new ArgumentException(
                        "replacePatterns without patterns is contradictory; pass the replacement patterns");
                patternList = InjectionPatterns.ToList();
            }
            else
            {
                var userPatterns = FieldList(patterns);
                if (userPatterns.Any(string.IsNullOrEmpty))
                    throw new ArgumentException("empty pattern fragments match everything; remove them");
                patternList = replacePatterns
                    ? userPatterns
                    : InjectionPatterns.Concat(userPatterns).ToList();
            }
            if (patternList.Count == 0)
                throw new ArgumentException(
                    "replacePatterns with no patterns would disable the control entirely; pass at least one pattern");
            var matcher = new Regex(string.Join("|", patternList),
                                    RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
            var output = new Records();
            foreach (var r in records)
            {
                // Python str(r.get(f, "")): None -> "None", containers via
                // repr — a payload nested in a dict or list still matches
                string text = string.Join(" ", fieldNames.Select(f =>
                    r.TryGetValue(f, out var v) ? PyCompat.PyStr(v) : ""));
                bool hit = matcher.IsMatch(text);
                if (action == "flag")
                {
                    var flagged = new Rec(r) { [into] = hit };
                    output.Add(flagged);
                }
                else if (!hit) output.Add(r);
            }
            return output;
        });

    // Python's [^\W_] on ASCII; exotic Unicode word classes are a margin
    private static readonly Regex Word =
        new(@"[\p{L}\p{N}]+", RegexOptions.CultureInvariant);

    public static Records Rescore(Records records, object query, object? fields = null,
                                  string into = "score", bool proximity = true,
                                  string match = "word") =>
        Trace.Traced("rescore", records, () =>
        {
            var fieldNames = FieldList(fields ?? new[] { "snippet" });
            var rawTerms = (query switch
            {
                string q => Word.Matches(q.ToLowerInvariant()).Select(m => m.Value),
                IEnumerable<string> qs => qs.SelectMany(p =>
                    Word.Matches(p.ToLowerInvariant()).Select(m => m.Value)),
                _ => throw new ArgumentException("query must be a string or a sequence of strings"),
            }).ToList();
            var terms = rawTerms.Distinct().ToList();
            if (terms.Count == 0 || records.Count == 0)
                return records.Select(r => new Rec(r) { [into] = 0.0 }).ToList();

            var texts = records.Select(r => string.Join(" ", fieldNames.Select(f =>
                r.TryGetValue(f, out var v) ? PyCompat.PyStr(v) : "")).ToLowerInvariant()).ToList();

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

    public static Records Rank(Records records, string by, bool desc = true) =>
        Trace.Traced("rank", records, () =>
        {
            var present = records.Where(r => r.ContainsKey(by)).ToList();
            var missing = records.Where(r => !r.ContainsKey(by)).ToList();
            return StableSort(present, r => r[by], desc).Concat(missing).ToList();
        });

    public static Records Rank(Records records, Func<Rec, object?> by, bool desc = true) =>
        Trace.Traced("rank", records, () => StableSort(records, by, desc));

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
                                        string suffix = "…") =>
        Trace.Traced("truncate_field", records, () =>
            records.Select(r =>
            {
                if (!r.TryGetValue(field, out var v) || v is not string s) return r;
                return new Rec(r) { [field] = TruncateText(s, maxTokens, tokenizer, suffix) };
            }).ToList());

    public static Records TrimToBudget(Records records, int maxTokens,
                                       Func<string, int>? tokenizer = null,
                                       int minRecords = 0) =>
        Trace.Traced("trim_to_budget", records, () =>
        {
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
