namespace Contexel;

using Records = List<Dictionary<string, object?>>;

/// <summary>
/// Pin a shaping policy at the tool boundary — parity port of Python's
/// @shaped. The model calls the tool normally and never sees raw output;
/// async tools are awaited, then shaped.
/// </summary>
public static class Shaped
{
    public static Func<Records> Wrap(Pipeline pipeline, Func<Records> tool) =>
        () => pipeline.Run(tool());

    public static Func<T1, Records> Wrap<T1>(Pipeline pipeline, Func<T1, Records> tool) =>
        a => pipeline.Run(tool(a));

    public static Func<T1, T2, Records> Wrap<T1, T2>(Pipeline pipeline, Func<T1, T2, Records> tool) =>
        (a, b) => pipeline.Run(tool(a, b));

    public static Func<Task<Records>> Wrap(Pipeline pipeline, Func<Task<Records>> tool) =>
        async () => pipeline.Run(await tool().ConfigureAwait(false));

    public static Func<T1, Task<Records>> Wrap<T1>(Pipeline pipeline, Func<T1, Task<Records>> tool) =>
        async a => pipeline.Run(await tool(a).ConfigureAwait(false));

    public static Func<T1, T2, Task<Records>> Wrap<T1, T2>(Pipeline pipeline, Func<T1, T2, Task<Records>> tool) =>
        async (a, b) => pipeline.Run(await tool(a, b).ConfigureAwait(false));
}
