using System.Globalization;
using System.Text;

namespace Contexel;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>
/// Per-stage observability — parity port of contexel's Python trace.
/// <c>using var t = Trace.Begin(idField: "path")</c> activates a trace
/// (AsyncLocal, the .NET analog of contextvars); stages auto-record their
/// effect, including which records each stage dropped. <c>Audit()</c> is
/// the governance record (snake_case keys, matching the golden vectors).
/// </summary>
public sealed class Trace : IDisposable
{
    public sealed record Entry(string Stage, int InCount, int OutCount,
                               int TokensBefore, int TokensAfter,
                               List<object?> DroppedIds);

    public List<Entry> Entries { get; } = [];
    public List<string> Policies { get; } = [];
    public string? IdField { get; }

    private static readonly AsyncLocal<Trace?> CurrentLocal = new();
    private readonly Trace? _previous;

    private Trace(string? idField)
    {
        IdField = idField;
        _previous = CurrentLocal.Value;
        CurrentLocal.Value = this;
    }

    public static Trace Begin(string? idField = null) => new(idField);
    public static Trace? Current => CurrentLocal.Value;

    public void Dispose() => CurrentLocal.Value = _previous;

    public int TokensBefore => Entries.Count > 0 ? Entries[0].TokensBefore : 0;
    public int TokensAfter => Entries.Count > 0 ? Entries[^1].TokensAfter : 0;
    public double Reduction =>
        TokensBefore == 0 ? 0 : 1 - (double)TokensAfter / TokensBefore;

    public string Report()
    {
        if (Entries.Count == 0) return "(no stages traced)";
        var lines = Entries.Select(e =>
            $"{e.Stage,-16} {e.InCount,5} -> {e.OutCount,-5} " +
            $"{e.TokensBefore.ToString("N0", CultureInfo.InvariantCulture),7} -> " +
            $"{e.TokensAfter.ToString("N0", CultureInfo.InvariantCulture),-7} tokens").ToList();
        lines.Add(new string('-', 56));
        lines.Add(
            $"{"total",-16} {"",5}    {"",-5} " +
            $"{TokensBefore.ToString("N0", CultureInfo.InvariantCulture),7} -> " +
            $"{TokensAfter.ToString("N0", CultureInfo.InvariantCulture),-7} tokens  " +
            $"({PyCompat.PyRound(Reduction * 100, 0).ToString(CultureInfo.InvariantCulture)}% reduction)");
        return string.Join("\n", lines);
    }

    /// <summary>JSON-able governance record: policy fingerprints,
    /// per-stage dropped ids (stage = removal reason), token movement.</summary>
    public Rec Audit() => new()
    {
        ["policies"] = new List<object?>(Policies),
        ["id_field"] = IdField,
        ["tokens_before"] = (long)TokensBefore,
        ["tokens_after"] = (long)TokensAfter,
        ["reduction"] = PyCompat.PyRound(Reduction, 4),
        ["stages"] = Entries.Select(e => (object?)new Rec
        {
            ["stage"] = e.Stage,
            ["records_in"] = (long)e.InCount,
            ["records_out"] = (long)e.OutCount,
            ["tokens_before"] = (long)e.TokensBefore,
            ["tokens_after"] = (long)e.TokensAfter,
            ["dropped_ids"] = new List<object?>(e.DroppedIds),
        }).ToList(),
    };

    /// <summary>Python-dict-faithful id key: 1, 1.0, and True share a key
    /// (Python dict equality), containers key by canonical JSON.</summary>
    private static string IdKey(object? value) => value switch
    {
        null => "None",
        bool or long or int or double => PyCompat.PyEqKey(value),
        string s => "str:" + s,
        _ => "json:" + Tokens.PythonJson(value),
    };

    /// <summary>Wrap a stage body so an active trace records its effect
    /// (including dropped ids, with the unidentified-survivor wildcard).</summary>
    internal static Records Traced(string name, Records records, Func<Records> fn)
    {
        var tr = Current;
        if (tr is null) return fn();
        int beforeN = records.Count;
        int beforeTok = Tokens.Count(records);
        var output = fn();
        var dropped = new List<object?>();
        string? fid = tr.IdField;
        if (!string.IsNullOrEmpty(fid)) // Python: `if self.id_field:` — "" is falsy
        {
            var remaining = new Dictionary<string, int>();
            int unidentified = 0; // survivors without the id field absorb drops
            foreach (var r in output)
            {
                if (r.TryGetValue(fid, out var v))
                {
                    string k = IdKey(v);
                    remaining[k] = remaining.GetValueOrDefault(k) + 1;
                }
                else unidentified++;
            }
            foreach (var r in records)
            {
                if (r.TryGetValue(fid, out var original))
                {
                    string k = IdKey(original);
                    int left = remaining.GetValueOrDefault(k);
                    if (left > 0) remaining[k] = left - 1;
                    else if (unidentified > 0) unidentified--;
                    else dropped.Add(original);
                }
            }
        }
        tr.Entries.Add(new Entry(name, beforeN, output.Count, beforeTok,
                                 Tokens.Count(output), dropped));
        return output;
    }
}
