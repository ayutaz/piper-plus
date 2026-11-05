namespace PiperPlus.Core;

/// <summary>
/// Shared truthiness contract for boolean <c>PIPER_PLUS_*</c> environment
/// variables (<c>PIPER_PLUS_DISABLE_WARMUP</c>, <c>PIPER_PLUS_DISABLE_CACHE</c>,
/// <c>PIPER_PLUS_DISABLE_MODEL_NOTICE</c>). Mirrors the Python
/// <c>ort_utils.py</c> / <c>download.py</c> rule: <c>"1"</c>, <c>"true"</c> or
/// <c>"yes"</c>, case-insensitive, surrounding whitespace ignored.
/// </summary>
internal static class EnvFlags
{
    /// <summary>
    /// Returns <c>true</c> when <paramref name="value"/> is one of <c>"1"</c>,
    /// <c>"true"</c> or <c>"yes"</c> after trimming (case-insensitive).
    /// </summary>
    internal static bool IsTruthy(string? value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return false;
        }

        var normalized = value.Trim().ToLowerInvariant();
        return normalized is "1" or "true" or "yes";
    }

    /// <summary>
    /// Returns <c>true</c> when the named environment variable is truthy
    /// according to <see cref="IsTruthy(string?)"/>.
    /// </summary>
    internal static bool IsTruthyEnv(string name)
        => IsTruthy(Environment.GetEnvironmentVariable(name));
}
