using System.Globalization;
using System.Text.Json;

namespace Contexel.Tests;

using Rec = Dictionary<string, object?>;
using Records = List<Dictionary<string, object?>>;

/// <summary>
/// Loads parity/vectors.json into the library's value model, preserving
/// the int-vs-float distinction from the RAW JSON text ("1" -> long,
/// "1.0" -> double) — the property that gives C# a stricter parity
/// envelope than TS (ADR-002 §3).
/// </summary>
public static class VectorData
{
    public static readonly Rec Vectors = Load();

    private static Rec Load()
    {
        string? dir = AppContext.BaseDirectory;
        while (dir is not null && !File.Exists(Path.Combine(dir, "parity", "vectors.json")))
            dir = Path.GetDirectoryName(dir);
        if (dir is null)
            throw new FileNotFoundException("parity/vectors.json not found above test directory");
        using var doc = JsonDocument.Parse(
            File.ReadAllText(Path.Combine(dir, "parity", "vectors.json")));
        return (Rec)Convert(doc.RootElement)!;
    }

    public static object? Convert(JsonElement e) => e.ValueKind switch
    {
        JsonValueKind.Null => null,
        JsonValueKind.True => true,
        JsonValueKind.False => false,
        JsonValueKind.String => e.GetString(),
        JsonValueKind.Number =>
            e.GetRawText().IndexOfAny(['.', 'e', 'E']) >= 0
                ? e.GetDouble()
                : (object)e.GetInt64(),
        JsonValueKind.Array => e.EnumerateArray().Select(Convert).ToList(),
        JsonValueKind.Object => e.EnumerateObject()
            .ToDictionary(p => p.Name, p => Convert(p.Value)),
        _ => throw new NotSupportedException(e.ValueKind.ToString()),
    };

    public static Rec AsRec(object? v) => (Rec)v!;
    public static List<object?> AsList(object? v) => (List<object?>)v!;
    public static Records AsRecords(object? v) =>
        AsList(v).Select(x => (Rec)x!).ToList();

    public static Rec Edges => AsRec(Vectors["edges"]);
    public static Rec StageVectors => AsRec(Vectors["stages"]);
    public static Records Fixture => AsRecords(Vectors["fixture"]);
    public static string Query => (string)Vectors["query"]!;

    /// <summary>Structural equality via canonical serialization: sorted
    /// keys make key order irrelevant, and int-vs-float is preserved by
    /// construction ("1" never equals "1.0" — Python json distinguishes
    /// them, and so does this port). Serializer correctness itself is
    /// separately pinned by string-equality vectors.</summary>
    public static bool DeepEquals(object? a, object? b) =>
        Tokens.PythonJson(a) == Tokens.PythonJson(b);

    public static string Show(object? v) => Tokens.PythonJson(v);

    public static void AssertDeepEqual(object? expected, object? actual, string context)
    {
        if (!DeepEquals(expected, actual))
            throw new Xunit.Sdk.XunitException(
                $"{context}\nexpected: {Show(expected)}\nactual:   {Show(actual)}");
    }
}
