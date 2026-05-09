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
    private static readonly Lazy<LoanwordData> S_default =
        new(LoadDefaultInternal, System.Threading.LazyThreadSafetyMode.ExecutionAndPublication);

    /// <summary>Bundled default loanword data (parsed once per process).</summary>
    public static LoanwordData Default => S_default.Value;

    /// <summary>Load from a file path, bypassing the cache (for overrides).</summary>
    /// <returns></returns>
    public static LoanwordData LoadFromPath(string path)
    {
        if (path is null)
        {
            throw new ArgumentNullException(nameof(path));
        }

        using FileStream stream = File.OpenRead(path);
        return Parse(path, stream);
    }

    /// <summary>Load from a JSON byte array (for tests / overrides).</summary>
    /// <returns></returns>
    public static LoanwordData LoadFromBytes(string label, byte[] data)
    {
        if (data is null)
        {
            throw new ArgumentNullException(nameof(data));
        }

        using var stream = new MemoryStream(data);
        return Parse(label, stream);
    }

    private static LoanwordData LoadDefaultInternal()
    {
        Assembly asm = typeof(LoanwordDataLoader).Assembly;
        const string ResourceName = "PiperPlus.Core.Phonemize.Data.zh_en_loanword.json";
        using Stream stream = asm.GetManifestResourceStream(ResourceName)
            ?? throw new InvalidOperationException(
                $"Embedded resource not found: {ResourceName}. " +
                $"Available: {string.Join(", ", asm.GetManifestResourceNames())}");
        return Parse("zh_en_loanword.json (bundled)", stream);
    }

    /// <summary>
    /// Parse JSON with shape-compatible Python-style error messages
    /// (<c>"&lt;label&gt;: '&lt;section&gt;.&lt;key&gt;' must be list[str], got &lt;value&gt;"</c>).
    /// Mirrors the Python loader's behavior: <c>version</c> is optional and
    /// any unknown top-level fields are silently ignored (forward-compat).
    /// Wraps <see cref="JsonException"/> as <see cref="LoanwordSchemaException"/>
    /// so callers only have to catch one exception type.
    /// </summary>
    /// <returns></returns>
    internal static LoanwordData Parse(string label, Stream stream)
    {
        // Use System.Text.Json with `JsonElement` so we can inspect the raw
        // structure and produce error messages that share the Python format.
        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(stream);
        }
        catch (JsonException e)
        {
            throw new LoanwordSchemaException($"{label}: invalid JSON: {e.Message}", e);
        }

        using (doc)
        {
            if (doc.RootElement.ValueKind != JsonValueKind.Object)
            {
                throw new LoanwordSchemaException($"{label}: top-level must be a JSON object");
            }

            JsonElement root = doc.RootElement;

            // Python's `_load_loanword_data` does not validate `version`. Be
            // lenient: also accept `schema_version` as a forward-compat alias
            // and fall back to 1 so a future payload that drops the field
            // outright still loads (review note R-C4).
            int version = 1;
            if (root.TryGetProperty("version", out JsonElement v1) &&
                v1.ValueKind == JsonValueKind.Number &&
                v1.TryGetInt32(out int parsedV1))
            {
                version = parsedV1;
            }
            else if (root.TryGetProperty("schema_version", out JsonElement v2) &&
                     v2.ValueKind == JsonValueKind.Number &&
                     v2.TryGetInt32(out int parsedV2))
            {
                version = parsedV2;
            }

            IReadOnlyDictionary<string, IReadOnlyList<string>> acronyms = ParseSection(label, root, "acronyms");
            IReadOnlyDictionary<string, IReadOnlyList<string>> loanwords = ParseSection(label, root, "loanwords");
            IReadOnlyDictionary<string, IReadOnlyList<string>> letterFallback = ParseSection(label, root, "letter_fallback");

            return new LoanwordData(version, acronyms, loanwords, letterFallback);
        }
    }

    private static IReadOnlyDictionary<string, IReadOnlyList<string>> ParseSection(
        string label, JsonElement root, string section)
    {
        var result = new Dictionary<string, IReadOnlyList<string>>();
        if (!root.TryGetProperty(section, out JsonElement sectionEl))
        {
            return result; // missing section ok (forward-compat)
        }

        if (sectionEl.ValueKind != JsonValueKind.Object)
        {
            throw new LoanwordSchemaException(
                $"{label}: section '{section}' must be a mapping, got {sectionEl.ValueKind}");
        }

        foreach (JsonProperty prop in sectionEl.EnumerateObject())
        {
            if (prop.Value.ValueKind != JsonValueKind.Array)
            {
                throw new LoanwordSchemaException(
                    $"{label}: '{section}.{prop.Name}' must be list[str], got {prop.Value.ValueKind}");
            }

            var list = new List<string>();
            foreach (JsonElement item in prop.Value.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.String)
                {
                    throw new LoanwordSchemaException(
                        $"{label}: '{section}.{prop.Name}' must be list[str], got {prop.Value}");
                }

                list.Add(item.GetString()!);
            }

            result[prop.Name] = list;
        }

        return result;
    }
}

/// <summary>
/// Thrown when <c>zh_en_loanword.json</c> fails schema validation.
/// Provides the full set of CA1032 ctors so callers can wrap a
/// <see cref="System.Text.Json.JsonException"/> via the
/// <c>(message, innerException)</c> overload.
/// </summary>
public sealed class LoanwordSchemaException : System.Exception
{
    public LoanwordSchemaException()
    {
    }

    public LoanwordSchemaException(string message)
        : base(message)
    {
    }

    public LoanwordSchemaException(string message, System.Exception innerException)
        : base(message, innerException)
    {
    }
}
