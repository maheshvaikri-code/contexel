using System.Globalization;
using System.Text;

namespace Contexel;

/// <summary>
/// Token measurement — parity port of contexel's Python tokens module.
/// A record's cost is the token count of its serialized text; the
/// canonical serialization replicates Python's
/// json.dumps(value, ensure_ascii=False, default=str, sort_keys=True),
/// including the ", " / ": " separators, so all languages price identical
/// records identically. Lengths count Unicode code points (Python len).
/// Unlike the TS port, C# preserves int/float: a JSON 1.0 serializes as
/// "1.0" exactly like Python (ADR-002).
/// </summary>
public static class Tokens
{
    public sealed record Scope(Func<string, int>? Tokenizer = null,
                               Func<object?, string>? Serializer = null);

    private static readonly AsyncLocal<Scope?> ScopeLocal = new();
    private static Func<string, int>? _processTokenizer;
    private static Func<object?, string>? _processSerializer;

    public static int Heuristic(string text) =>
        text.Length == 0 ? 0 : Math.Max(1, (PyCompat.CodePointLength(text) + 3) / 4);

    /// <summary>Python-compatible canonical JSON (sort_keys,
    /// ensure_ascii=False, default=str). Hand-rolled: System.Text.Json
    /// escapes far more aggressively than json.dumps.</summary>
    public static string PythonJson(object? value)
    {
        var sb = new StringBuilder();
        WriteJson(sb, value);
        return sb.ToString();
    }

    private static void WriteJson(StringBuilder sb, object? value)
    {
        switch (value)
        {
            case null: sb.Append("null"); break;
            case bool b: sb.Append(b ? "true" : "false"); break;
            case long l: sb.Append(l.ToString(CultureInfo.InvariantCulture)); break;
            case int i: sb.Append(i.ToString(CultureInfo.InvariantCulture)); break;
            case double d:
                if (double.IsNaN(d)) sb.Append("NaN");
                else if (double.IsPositiveInfinity(d)) sb.Append("Infinity");
                else if (double.IsNegativeInfinity(d)) sb.Append("-Infinity");
                else sb.Append(PyCompat.PyFloat(d)); // "1.0", "1e-05" like Python
                break;
            case string s: WriteJsonString(sb, s); break;
            // generic type patterns are invariant (List<Rec> is not
            // List<object?>), so containers match structurally
            case System.Collections.IDictionary dict:
                sb.Append('{');
                bool first = true;
                foreach (var key in dict.Keys.Cast<object>().Select(k => (string)k)
                             .OrderBy(k => k, CodePointComparer.Instance))
                {
                    if (!first) sb.Append(", ");
                    first = false;
                    WriteJsonString(sb, key);
                    sb.Append(": ");
                    WriteJson(sb, dict[key]);
                }
                sb.Append('}');
                break;
            case System.Collections.IEnumerable seq:
                sb.Append('[');
                bool firstItem = true;
                foreach (var item in seq)
                {
                    if (!firstItem) sb.Append(", ");
                    firstItem = false;
                    WriteJson(sb, item);
                }
                sb.Append(']');
                break;
            default: // default=str fallback
                WriteJsonString(sb, Convert.ToString(value, CultureInfo.InvariantCulture) ?? "");
                break;
        }
    }

    private static void WriteJsonString(StringBuilder sb, string s)
    {
        sb.Append('"');
        foreach (char ch in s)
        {
            switch (ch)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                case '\b': sb.Append("\\b"); break;
                case '\f': sb.Append("\\f"); break;
                default:
                    if (ch < 0x20)
                        sb.Append("\\u").Append(((int)ch).ToString("x4", CultureInfo.InvariantCulture));
                    else
                        sb.Append(ch); // ensure_ascii=False: non-ASCII stays raw
                    break;
            }
        }
        sb.Append('"');
    }

    private sealed class CodePointComparer : IComparer<string>
    {
        public static readonly CodePointComparer Instance = new();
        public int Compare(string? x, string? y) => PyCompat.CompareCodePoints(x!, y!);
    }

    /// <summary>Process-wide default tokenizer; null resets to the built-in estimator.</summary>
    public static void SetTokenizer(Func<string, int>? tokenizer) => _processTokenizer = tokenizer;

    /// <summary>Process-wide default serializer; null resets to canonical JSON.</summary>
    public static void SetSerializer(Func<object?, string>? serializer) => _processSerializer = serializer;

    /// <summary>Context-local overrides — safe for concurrent tenants
    /// (AsyncLocal, the .NET analog of contextvars). Nested scopes merge,
    /// so an inner serializer never clobbers an outer tokenizer.</summary>
    public static T Scoped<T>(Scope overrides, Func<T> fn)
    {
        var prev = ScopeLocal.Value;
        ScopeLocal.Value = Merge(prev, overrides);
        try { return fn(); }
        finally { ScopeLocal.Value = prev; }
    }

    public static async Task<T> ScopedAsync<T>(Scope overrides, Func<Task<T>> fn)
    {
        var prev = ScopeLocal.Value;
        ScopeLocal.Value = Merge(prev, overrides);
        try { return await fn().ConfigureAwait(false); }
        finally { ScopeLocal.Value = prev; }
    }

    private static Scope Merge(Scope? outer, Scope overrides) => new(
        overrides.Tokenizer ?? outer?.Tokenizer,
        overrides.Serializer ?? outer?.Serializer);

    private static Func<string, int> ActiveTokenizer() =>
        ScopeLocal.Value?.Tokenizer ?? _processTokenizer ?? Heuristic;

    private static Func<object?, string> ActiveSerializer() =>
        ScopeLocal.Value?.Serializer ?? _processSerializer ?? PythonJson;

    /// <summary>True when the tokenizer in effect is the built-in
    /// estimator (enables the closed-form truncate fast path).</summary>
    public static bool IsHeuristic(Func<string, int>? tokenizer = null) =>
        (tokenizer ?? ActiveTokenizer()) == (Func<string, int>)Heuristic;

    /// <summary>Render a value exactly the way token counting will price it.</summary>
    public static string Serialize(object? value) =>
        value is string s ? s : ActiveSerializer()(value);

    /// <summary>Token cost of any serializable value (strings bypass the serializer).</summary>
    public static int Count(object? value, Func<string, int>? tokenizer = null)
    {
        var tok = tokenizer ?? ActiveTokenizer();
        return tok(value is string s ? s : Serialize(value));
    }
}
