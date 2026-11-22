namespace Contexel;

/// <summary>
/// Strict mode: opt-in validation of the SHAPE of stage input (ADR-003).
/// The original stages are lenient about data shape; that stays the default,
/// so valid input and today's callers keep byte-identical behavior. Switch
/// strict mode on to get a typed <see cref="InputShapeException"/> that names
/// the stage (and the item index) instead:
/// <code>using (Strict.Begin()) { Stages.Select(records, "a"); }</code>
/// <para>The flag is an <see cref="AsyncLocal{T}"/>: it follows <c>await</c>
/// but is not inherited by a thread started after the block ended.
/// <c>new Pipeline(stages, strict: true)</c> and
/// <c>Shaped.Wrap(..., strict: true)</c> enter strict mode inside their own
/// run. C# is statically typed, so only <c>null</c> can violate the shape
/// (null records, null item). Strict never changes a successful result and
/// is not part of a pipeline's fingerprint.</para>
/// </summary>
public static class Strict
{
    private static readonly AsyncLocal<bool> Flag = new();

    /// <summary>Whether strict mode is active in the current async flow.</summary>
    public static bool IsActive => Flag.Value;

    /// <summary>Turn strict mode on until the returned scope is disposed,
    /// which restores the previous value (nesting works).</summary>
    public static IDisposable Begin()
    {
        var scope = new Scope(Flag.Value);
        Flag.Value = true;
        return scope;
    }

    private sealed class Scope(bool previous) : IDisposable
    {
        private bool _done;

        public void Dispose()
        {
            if (_done) return;
            _done = true;
            Flag.Value = previous;
        }
    }

    /// <summary>In strict mode only: records must be non-null and, when
    /// <paramref name="mapping"/>, every item non-null. Called BEFORE
    /// <c>Trace.Traced</c>, which reads <c>records.Count</c> first.
    /// <paramref name="always"/> validates in every mode, not only in strict
    /// mode: the payload stages (<see cref="Text"/>) are new, so they have no
    /// lenient behavior to stay compatible with.</summary>
    internal static void CheckRecords<T>(List<T>? records, string stage, bool mapping,
                                         bool always = false)
    {
        if (!always && !Flag.Value) return;
        if (records is null)
            throw new InputShapeException("input.not_list",
                $"{stage}: records must be a list, got null", stage);
        if (!mapping) return;
        for (int i = 0; i < records.Count; i++)
            if (records[i] is null)
                throw new InputShapeException("input.not_mapping",
                    $"{stage}: item {i} must be a mapping, got null", stage);
    }

    /// <summary>Strict pipelines: a stage must hand the next one a list.</summary>
    internal static void CheckStageOutput(object? output, string stage, int index)
    {
        if (output is null)
            throw new InputShapeException("input.not_list",
                $"stage {index} ({stage}) returned null, not a list", stage);
    }
}
