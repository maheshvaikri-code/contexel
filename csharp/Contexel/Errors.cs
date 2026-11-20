using System.Collections;

namespace Contexel;

/// <summary>
/// Typed errors (ADR-003). Every error contexel raises on purpose is a
/// <see cref="ContexelException"/> carrying a stable <see cref="Code"/> — the
/// cross-language contract (messages are for humans and may differ between
/// the Python, TypeScript and C# ports; codes may not).
/// <para>The base is <see cref="ArgumentException"/> so every existing
/// <c>catch (ArgumentException)</c> keeps working. <c>paramName</c> is NOT
/// passed to the base: it would append " (Parameter '...')" to
/// <see cref="Exception.Message"/>.</para>
/// </summary>
public class ContexelException : ArgumentException
{
    /// <summary>The complete, stable set of error codes.</summary>
    public static readonly IReadOnlyList<string> Codes =
    [
        "config.invalid_value",
        "config.empty",
        "config.contradictory",
        "config.invalid_pattern",
        "input.not_list",
        "input.not_mapping",
        "input.field_conflict",
    ];

    public string Code { get; }
    public string? Stage { get; }
    public string? Param { get; }

    public ContexelException(string code, string message,
                             string? stage = null, string? param = null)
        : base(message)
    {
        // an unknown code is a developer error, not a contexel outcome
        if (!Codes.Contains(code))
            throw new ArgumentException($"unknown contexel error code '{code}'");
        Code = code;
        Stage = stage;
        Param = param;
    }
}

/// <summary>The stage was configured wrongly (codes <c>config.*</c>). Always thrown.</summary>
public sealed class ConfigException : ContexelException
{
    public ConfigException(string code, string message,
                           string? stage = null, string? param = null)
        : base(code, message, stage, param)
    {
        if (!code.StartsWith("config.", StringComparison.Ordinal))
            throw new ArgumentException($"'{code}' is not a config code");
    }
}

/// <summary>The data does not have the shape the stage needs (codes
/// <c>input.*</c>). Shape errors from the original stages are thrown only in
/// strict mode (<see cref="Strict"/>); a field conflict is always thrown,
/// because continuing would silently destroy data.</summary>
public sealed class InputShapeException : ContexelException
{
    public InputShapeException(string code, string message,
                               string? stage = null, string? param = null)
        : base(code, message, stage, param)
    {
        if (!code.StartsWith("input.", StringComparison.Ordinal))
            throw new ArgumentException($"'{code}' is not an input code");
    }
}

/// <summary>Configuration checks shared by the stages (mirror of Python's
/// <c>errors.py</c> helpers). Every failure carries the stage and the param.</summary>
internal static class Check
{
    private static string Kind(object? value) => PyCompat.PyTypeName(value) switch
    {
        "NoneType" => "null",
        var other => other,
    };

    public static ConfigException InvalidValue(string stage, string param, string message) =>
        new("config.invalid_value", $"{stage}: {message}", stage, param);

    private static bool IsUnordered(object value) =>
        value is IDictionary ||
        value.GetType().GetInterfaces().Any(i =>
            i.IsGenericType && i.GetGenericTypeDefinition() == typeof(ISet<>));

    /// <summary>A bare string means ONE field (never its characters);
    /// otherwise a sequence of strings (the element type is checked at run
    /// time, because the parameter is a boxed <c>object</c>). A dictionary or
    /// a set is refused — unordered, or not a list of names.
    /// <paramref name="allowEmpty"/> false rejects an empty list: a stage
    /// that scans no fields silently does nothing, and for a security control
    /// that is the failure to refuse.</summary>
    public static List<string> Fields(object? value, string stage, string param = "fields",
                                      bool allowEmpty = true)
    {
        List<string> names;
        switch (value)
        {
            case string s:
                names = [s];
                break;
            case IEnumerable seq when !IsUnordered(seq):
                names = [];
                foreach (var item in seq)
                {
                    if (item is not string name)
                        throw InvalidValue(stage, param, $"{param} must contain only strings");
                    names.Add(name);
                }
                break;
            default:
                throw InvalidValue(stage, param,
                    $"{param} must be a string or a list of strings, got {Kind(value)}");
        }
        if (names.Count == 0 && !allowEmpty)
            throw new ConfigException("config.empty",
                $"{stage}: {param} is empty, so the stage would silently do nothing; " +
                "pass at least one field", stage, param);
        return names;
    }

    public static object Query(object? value, string stage, string param = "query")
    {
        if (value is string || (value is IEnumerable && !IsUnordered(value)))
            return value;
        throw InvalidValue(stage, param,
            $"{param} must be a string or a list of strings, got {Kind(value)}");
    }

    public static int NonNegativeInt(int value, string stage, string param)
    {
        if (value < 0)
            throw InvalidValue(stage, param, $"{param} must be an integer >= 0, got {value}");
        return value;
    }

    public static string Str(string? value, string stage, string param)
    {
        if (value is null)
            throw InvalidValue(stage, param, $"{param} must be a string, got null");
        return value;
    }

    public static string Choice(string? value, string stage, string param,
                                params string[] choices)
    {
        if (value is null || !choices.Contains(value))
        {
            string listed = string.Join(", ", choices.Select(PyCompat.PyRepr));
            throw InvalidValue(stage, param,
                $"{param} must be one of {listed}, got {PyCompat.PyRepr(value)}");
        }
        return value;
    }
}
