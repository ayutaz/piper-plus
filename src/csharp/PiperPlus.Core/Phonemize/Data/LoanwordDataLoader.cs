using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text.Json;

namespace PiperPlus.Core.Phonemize.Data;

/// <summary>
/// Loads <see cref="LoanwordData"/> from the embedded resource (default) or
/// an arbitrary file path (override). The default load is cached via
/// <c>Lazy&lt;T&gt;</c> with <see cref="LazyThreadSafetyMode.ExecutionAndPublication"/>.
/// </summary>
public static class LoanwordDataLoader
{
    private static readonly Lazy<LoanwordData> s_default =
        new(LoadDefaultInternal, System.Threading.LazyThreadSafetyMode.ExecutionAndPublication);

    /// <summary>Bundled default loanword data (parsed once per process).</summary>
    public static LoanwordData Default => s_default.Value;

    /// <summary>Load from a file path, bypassing the cache (for overrides).</summary>
    public static LoanwordData LoadFromPath(string path)
    {
        if (path is null) throw new ArgumentNullException(nameof(path));
        using var stream = File.OpenRead(path);
        return Parse(path, stream);
    }

    /// <summary>Load from a JSON byte array (for tests / overrides).</summary>
    public static LoanwordData LoadFromBytes(string label, byte[] data)
    {
        if (data is null) throw new ArgumentNullException(nameof(data));
        using var stream = new MemoryStream(data);
        return Parse(label, stream);
    }

    private static LoanwordData LoadDefaultInternal()
    {
        var asm = typeof(LoanwordDataLoader).Assembly;
        const string ResourceName = "PiperPlus.Core.Phonemize.Data.zh_en_loanword.json";
        using var stream = asm.GetManifestResourceStream(ResourceName)
            ?? throw new InvalidOperationException(
                $"Embedded resource not found: {ResourceName}. " +
                $"Available: {string.Join(", ", asm.GetManifestResourceNames())}");
        return Parse("zh_en_loanword.json (bundled)", stream);
    }

    /// <summary>
    /// Parse JSON with Python-equivalent error messages
    /// (<c>"&lt;label&gt;: '&lt;section&gt;.&lt;key&gt;' must be list[str], got &lt;value&gt;"</c>).
    /// </summary>
    internal static LoanwordData Parse(string label, Stream stream)
    {
        // Use System.Text.Json with `JsonElement` so we can inspect the raw
        // structure and produce error messages that match the Python format.
        using var doc = JsonDocument.Parse(stream);
        if (doc.RootElement.ValueKind != JsonValueKind.Object)
            throw new LoanwordSchemaException($"{label}: top-level must be a JSON object");

        var root = doc.RootElement;

        if (!root.TryGetProperty("version", out var versionEl) ||
            versionEl.ValueKind != JsonValueKind.Number ||
            !versionEl.TryGetInt32(out int version))
            throw new LoanwordSchemaException($"{label}: missing or non-int 'version'");

        var acronyms = ParseSection(label, root, "acronyms");
        var loanwords = ParseSection(label, root, "loanwords");
        var letterFallback = ParseSection(label, root, "letter_fallback");

        return new LoanwordData(version, acronyms, loanwords, letterFallback);
    }

    private static IReadOnlyDictionary<string, IReadOnlyList<string>> ParseSection(
        string label, JsonElement root, string section)
    {
        var result = new Dictionary<string, IReadOnlyList<string>>();
        if (!root.TryGetProperty(section, out var sectionEl))
            return result; // missing section ok (forward-compat)
        if (sectionEl.ValueKind != JsonValueKind.Object)
            throw new LoanwordSchemaException(
                $"{label}: section '{section}' must be a mapping, got {sectionEl.ValueKind}");

        foreach (var prop in sectionEl.EnumerateObject())
        {
            if (prop.Value.ValueKind != JsonValueKind.Array)
                throw new LoanwordSchemaException(
                    $"{label}: '{section}.{prop.Name}' must be list[str], got {prop.Value.ValueKind}");
            var list = new List<string>();
            foreach (var item in prop.Value.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.String)
                    throw new LoanwordSchemaException(
                        $"{label}: '{section}.{prop.Name}' must be list[str], got {prop.Value}");
                list.Add(item.GetString()!);
            }
            result[prop.Name] = list;
        }
        return result;
    }
}

/// <summary>Thrown when <c>zh_en_loanword.json</c> fails schema validation.</summary>
public sealed class LoanwordSchemaException : System.Exception
{
    public LoanwordSchemaException(string message) : base(message) { }
}
