namespace Contexel;

using Records = List<Dictionary<string, object?>>;

/// <summary>
/// Pin a shaping policy at the tool boundary — parity port of Python's
/// @shaped. The model calls the tool normally and never sees raw output;
/// async tools are awaited, then shaped.
/// <para><c>strict: true</c> (every overload) validates that the tool's
/// result is a list (<see cref="InputShapeException"/> with stage "shaped"
/// otherwise — a tool that returns null would else surface as an obscure
/// error inside the first stage) and runs the pipeline in strict mode,
/// entered inside the wrapper's own run. A pipeline built with
/// <c>strict: true</c> additionally checks each stage's output.</para>
/// </summary>
public static class Shaped
{
    private static Records Apply(Pipeline pipeline, Records? result, bool strict)
    {
        if (!strict) return pipeline.Run(result!);
        if (result is null)
            throw new InputShapeException("input.not_list",
                "shaped: the tool must return a list, got null", "shaped");
        using (Strict.Begin()) return pipeline.Run(result);
    }

    public static Func<Records> Wrap(Pipeline pipeline, Func<Records> tool, bool strict = false) =>
        () => Apply(pipeline, tool(), strict);

    public static Func<T1, Records> Wrap<T1>(Pipeline pipeline, Func<T1, Records> tool,
                                             bool strict = false) =>
        a => Apply(pipeline, tool(a), strict);

    public static Func<T1, T2, Records> Wrap<T1, T2>(Pipeline pipeline, Func<T1, T2, Records> tool,
                                                     bool strict = false) =>
        (a, b) => Apply(pipeline, tool(a, b), strict);

    public static Func<Task<Records>> Wrap(Pipeline pipeline, Func<Task<Records>> tool,
                                           bool strict = false) =>
        async () => Apply(pipeline, await tool().ConfigureAwait(false), strict);

    public static Func<T1, Task<Records>> Wrap<T1>(Pipeline pipeline, Func<T1, Task<Records>> tool,
                                                   bool strict = false) =>
        async a => Apply(pipeline, await tool(a).ConfigureAwait(false), strict);

    public static Func<T1, T2, Task<Records>> Wrap<T1, T2>(Pipeline pipeline,
                                                           Func<T1, T2, Task<Records>> tool,
                                                           bool strict = false) =>
        async (a, b) => Apply(pipeline, await tool(a, b).ConfigureAwait(false), strict);
}
