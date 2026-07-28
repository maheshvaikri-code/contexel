using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Contexel;

using Records = List<Dictionary<string, object?>>;

/// <summary>A named, parameter-bound step in a pipeline. The parameters
/// exist for the policy fingerprint; the function is the behavior.</summary>
public sealed record Stage(string Name, Func<Records, Records> Fn,
                           Dictionary<string, object?>? Parameters = null);

/// <summary>
/// Composition with a stable policy fingerprint — parity port of Python's
/// pipeline(). The fingerprint hashes stage names + bound parameters
/// (sha256, first 16 hex chars) and is recorded into any active trace, so
/// an audit shows WHICH policy shaped the context. Fingerprints are
/// language-local in v1 (ADR-002).
/// </summary>
public sealed class Pipeline
{
    private readonly List<Stage> _stages;
    public string Fingerprint { get; }

    public Pipeline(params Stage[] stages)
    {
        _stages = stages.ToList();
        var repr = new StringBuilder();
        foreach (var s in _stages)
        {
            repr.Append(s.Name).Append('(');
            if (s.Parameters is not null)
                repr.Append(string.Join(",", s.Parameters
                    .OrderBy(kv => kv.Key, StringComparer.Ordinal)
                    .Select(kv => kv.Key + "=" + StableRepr(kv.Value))));
            repr.Append(");");
        }
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes(repr.ToString()));
        Fingerprint = Convert.ToHexString(hash)[..16].ToLowerInvariant();
    }

    private static string StableRepr(object? value) => value switch
    {
        Delegate d => "<fn:" + d.Method.Name + ">",
        _ => Tokens.PythonJson(value),
    };

    public Records Run(Records records)
    {
        var tr = Trace.Current;
        if (tr is not null && !tr.Policies.Contains(Fingerprint))
            tr.Policies.Add(Fingerprint);
        var current = records;
        foreach (var s in _stages) current = s.Fn(current);
        return current;
    }
}
