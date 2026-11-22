using System.Collections;
using System.Text;

namespace Contexel;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>
/// Payload stages: carry text through the record stages and back (ADR-005).
/// Every other stage takes a list of mappings. A log, a web page or a plain
/// string is none of that, so three small stages convert at the edges:
/// <code>
/// var chunks = Text.Split(Text.AsRecords(log), by: "lines");   // text -> records
/// // ... Dedupe, Rescore, Rank, TrimToBudget
/// string text = Text.Join(chunks);                              // records -> text
/// </code>
/// <see cref="AsRecords"/> and <see cref="Join"/> are the entry and exit
/// points: call them outside a <see cref="Pipeline"/> (like
/// <see cref="Stages.Merge"/>), because a pipeline hands every stage a list.
/// <see cref="Split"/> is an ordinary traced stage and belongs in a pipeline.
/// <para>Unlike the original stages, these validate the SHAPE of their input in
/// every mode, not only in strict mode: they are new, so there is no lenient
/// behavior to stay compatible with.</para>
/// <para>Boundaries are explicit and identical in Python, TypeScript and C#: a
/// line ends after <c>"\n"</c> only (so <c>"\r\n"</c> is one boundary and a lone
/// <c>"\r"</c> is none), a paragraph ends after a run of two or more newlines
/// (<c>(?:\r?\n){2,}</c>), and sizes and offsets count code points: a surrogate
/// pair is ONE, never two.</para>
/// </summary>
public static class Text
{
    private static string Kind(object? value) => PyCompat.PyTypeName(value) switch
    {
        "NoneType" => "null",
        var other => other,
    };

    private static bool Implements(object value, Type openGeneric) =>
        value.GetType().GetInterfaces().Any(i =>
            i.IsGenericType && i.GetGenericTypeDefinition() == openGeneric);

    /// <summary>Turn a payload into a list of records, the shape every stage
    /// takes. A string becomes <c>[{field: x}]</c>; a
    /// <c>Dictionary&lt;string, object?&gt;</c> becomes <c>[x]</c> (the same
    /// object, not a copy); any other list (a non-string, non-<c>byte[]</c>,
    /// non-dictionary, non-set <see cref="IEnumerable"/>) keeps each mapping item
    /// and wraps every other item, null and nested lists included, as
    /// <c>{field: item}</c>. null, bytes and every other type throw
    /// <see cref="InputShapeException"/> (<c>input.not_list</c>). <c>field</c>
    /// must be a non-empty string (<see cref="ConfigException"/>,
    /// <c>config.invalid_value</c>), checked after the shape. Not traced: it is
    /// an entry point.</summary>
    public static Records AsRecords(object? x, string field = "text")
    {
        bool isList = x is IEnumerable && x is not (string or byte[] or IDictionary)
            && !Implements(x, typeof(ISet<>)) && !Implements(x, typeof(IReadOnlySet<>))
            && !Implements(x, typeof(IDictionary<,>))
            && !Implements(x, typeof(IReadOnlyDictionary<,>));
        if (x is not (string or Rec) && !isList)
            throw new InputShapeException("input.not_list",
                $"as_records: expected a string, a mapping or a list, got {Kind(x)}",
                "as_records");
        Check.Str(field, "as_records", "field");
        if (field.Length == 0)
            throw Check.InvalidValue("as_records", "field", "field must not be empty");
        if (x is string text) return [new Rec { [field] = text }];
        if (x is Rec mapping) return [mapping];
        var output = new Records();
        foreach (var item in (IEnumerable)x!)
            output.Add(item is Rec r ? r : new Rec { [field] = item });
        return output;
    }

    /// <summary>The UTF-16 end offset (exclusive) of every chunk of
    /// <paramref name="text"/>. One linear pass per mode: no substring search
    /// from every position and no backtracking.</summary>
    private static List<int> Ends(string text, string by, int size)
    {
        int n = text.Length;
        var ends = new List<int>();
        if (by == "size")
        {
            for (int i = 0; i < n;)
            {
                int j = i;
                for (int taken = 0; taken < size && j < n; taken++)
                    j += char.IsSurrogatePair(text, j) ? 2 : 1; // one code point
                ends.Add(j);
                i = j;
            }
            return ends;
        }
        int last = 0;
        if (by == "lines")
        {
            for (int pos = text.IndexOf('\n'); pos != -1; pos = text.IndexOf('\n', last))
            {
                last = pos + 1;
                ends.Add(last);
            }
        }
        else
        {
            // (?:\r?\n){2,}, leftmost and greedy. A newline unit is "\n" or "\r\n"
            // and cannot be read two ways, so one left-to-right scan is exact: a
            // run of two or more units ends a chunk, a run of one is skipped.
            for (int i = 0; i < n;)
            {
                int j = i, units = 0;
                while (j < n)
                {
                    if (text[j] == '\n') j++;
                    else if (text[j] == '\r' && j + 1 < n && text[j + 1] == '\n') j += 2;
                    else break;
                    units++;
                }
                if (units >= 2)
                {
                    last = j;
                    ends.Add(last);
                }
                i = units == 0 ? i + 1 : j;
            }
        }
        if (last < n) ends.Add(n); // the remainder after the last boundary is a chunk
        return ends;
    }

    /// <summary>Code points in <c>text[start..end]</c>: UTF-16 units minus the
    /// pairs that count once.</summary>
    private static int CodePoints(string text, int start, int end)
    {
        int count = end - start;
        for (int i = start; i < end - 1; i++)
            if (char.IsSurrogatePair(text, i)) { count--; i++; }
        return count;
    }

    /// <summary>Cut the text in <c>field</c> into chunk records.
    /// <c>by: "lines"</c> ends a chunk after each <c>"\n"</c>;
    /// <c>by: "paragraphs"</c> after each run of two or more newlines;
    /// <c>by: "size"</c> every <c>size</c> code points (<c>size</c> must then be
    /// a positive integer). Every chunk keeps its trailing separator, so joining
    /// the chunks with <c>""</c> reproduces the text exactly.
    /// <para>Each chunk is <c>{...parent, [field]: chunk, [into]: {index, start,
    /// end}}</c>: <c>index</c> counts from 0 within its parent and <c>[start,
    /// end)</c> are code-point offsets into the original text. A record whose
    /// <c>field</c> is not a string passes through untouched (the same object);
    /// a string that is empty yields no chunks (that record disappears). A
    /// string-valued record that already has the <c>into</c> key throws
    /// <see cref="InputShapeException"/> (<c>input.field_conflict</c>).</para>
    /// <para><c>by</c> must be lines, paragraphs or size and <c>size</c> must be
    /// omitted for the first two (<see cref="ConfigException"/>:
    /// <c>config.invalid_value</c> and <c>config.contradictory</c>). Items must be
    /// mappings: this stage checks its input in every mode.</para>
    /// <para>Rank reorders chunks by score; to restore reading order before
    /// <see cref="Join"/>, rank again by <c>chunk.start</c> ascending.</para></summary>
    public static Records Split(Records records, string field = "text", string by = "lines",
                                int? size = null, string into = "chunk") =>
        SplitCore(records, field, by, size, into);

    /// <summary>The body of <see cref="Split"/> with <c>size</c> as a boxed value,
    /// so a value C# cannot spell as <c>int?</c> (a bool, a fraction, a string:
    /// the shared vectors carry them) reaches the same validation as in the
    /// other languages. Any whole number that is not a bool is a size; a
    /// <c>long</c> beyond <c>int.MaxValue</c> simply holds the whole text.</summary>
    internal static Records SplitCore(Records records, string field, string by, object? size,
                                      string into)
    {
        // shape first (always, strict mode or not), then the configuration
        Strict.CheckRecords(records, "split", mapping: true, always: true);
        return Trace.Traced("split", records, () =>
        {
            Check.Str(field, "split", "field");
            Check.Choice(by, "split", "by", "lines", "paragraphs", "size");
            Check.Str(into, "split", "into");
            int cut = 0;
            if (by == "size")
            {
                if (size is bool || size is not (long or int) || Convert.ToInt64(size) < 1)
                    throw Check.InvalidValue("split", "size",
                        $"size must be a positive integer when by='size', got {PyCompat.PyRepr(size)}");
                cut = (int)Math.Min(Convert.ToInt64(size), int.MaxValue);
            }
            else if (size is not null)
                throw new ConfigException("config.contradictory",
                    $"split: size={PyCompat.PyRepr(size)} only applies to by='size', " +
                    $"got by={PyCompat.PyRepr(by)}", "split", "size");
            var output = new Records();
            for (int i = 0; i < records.Count; i++)
            {
                var r = records[i];
                // only the record's own field counts, and only a string is cut
                if (!r.TryGetValue(field, out var value) || value is not string text)
                {
                    output.Add(r);
                    continue;
                }
                if (r.ContainsKey(into))
                    throw new InputShapeException("input.field_conflict",
                        $"split: record {i} already has a {PyCompat.PyRepr(into)} field; " +
                        "pass a different into", "split", "into");
                int start = 0;
                long position = 0; // code-point offset of `start`
                int index = 0;
                foreach (int end in Ends(text, by, cut))
                {
                    long length = CodePoints(text, start, end);
                    // keep the parent's key comparer: the chunk text replaces the
                    // field in place instead of landing next to it
                    output.Add(new Rec(r, r.Comparer)
                    {
                        [field] = text[start..end],
                        [into] = new Rec
                        {
                            ["index"] = (long)index,
                            ["start"] = position,
                            ["end"] = position + length,
                        },
                    });
                    position += length;
                    start = end;
                    index++;
                }
            }
            return output;
        }, keepsIds: true);
    }

    /// <summary>Join the <c>field</c> of every record into one string. A record
    /// without <c>field</c> is skipped; a string value is used as it is; any
    /// other value (null included) is rendered with
    /// <see cref="Tokens.Serialize"/>, the text the token budget priced. The
    /// parts are joined with <c>sep</c>. Items must be mappings (checked in every
    /// mode). Not traced: it is an exit point.</summary>
    public static string Join(Records records, string field = "text", string sep = "")
    {
        Strict.CheckRecords(records, "join", mapping: true, always: true);
        Check.Str(field, "join", "field");
        Check.Str(sep, "join", "sep");
        var output = new StringBuilder();
        bool first = true;
        foreach (var r in records)
        {
            if (!r.TryGetValue(field, out var value)) continue;
            if (!first) output.Append(sep);
            first = false;
            output.Append(value is string s ? s : Tokens.Serialize(value));
        }
        return output.ToString();
    }
}
