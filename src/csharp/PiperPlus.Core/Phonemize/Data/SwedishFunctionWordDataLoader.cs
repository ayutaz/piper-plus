using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text.Json;

namespace PiperPlus.Core.Phonemize.Data;

/// <summary>
/// Loads <see cref="SwedishFunctionWordData"/> from the embedded
/// <c>sv_function_words.json</c> resource (Issue #539). Mirrors
/// <see cref="LoanwordDataLoader"/>: the default load is cached via
/// <c>Lazy&lt;T&gt;</c> with
/// <see cref="System.Threading.LazyThreadSafetyMode.ExecutionAndPublication"/>.
/// <para>
/// The loader matches the graceful-degradation contract of the Python / Rust /
/// Go / C++ runtimes: there is NO hardcoded fallback. If the resource is
/// missing or malformed, BOTH the function-word set and the strong-char set are
/// EMPTY, so the per-word Swedish post-pass becomes a complete no-op. Unknown
/// top-level JSON properties (e.g. <c>schema_version</c> bumps or future
/// sections) are silently ignored for forward-compatibility.
/// </para>
/// </summary>
public static class SwedishFunctionWordDataLoader
{
    private static readonly Lazy<SwedishFunctionWordData> S_default =
        new(LoadDefaultInternal, System.Threading.LazyThreadSafetyMode.ExecutionAndPublication);

    /// <summary>Bundled default Swedish LID data (parsed once per process).</summary>
    public static SwedishFunctionWordData Default => S_default.Value;

    /// <summary>Load from a JSON byte array (for tests / overrides).</summary>
    /// <returns>The parsed data, or empty sets on parse failure.</returns>
    public static SwedishFunctionWordData LoadFromBytes(byte[] data)
    {
        if (data is null)
        {
            throw new ArgumentNullException(nameof(data));
        }

        using var stream = new MemoryStream(data);
        return Parse(stream);
    }

    private static SwedishFunctionWordData LoadDefaultInternal()
    {
        // Never throw at type-init / first access: a missing or corrupt
        // resource must degrade to empty sets (full no-op post-pass), exactly
        // like Python's module-import loader. Throwing here would brick every
        // caller of UnicodeLanguageDetector.
        try
        {
            Assembly asm = typeof(SwedishFunctionWordDataLoader).Assembly;
            const string ResourceName = "PiperPlus.Core.Phonemize.Data.sv_function_words.json";
            using Stream? stream = asm.GetManifestResourceStream(ResourceName);
            if (stream is null)
            {
                return Empty();
            }

            return Parse(stream);
        }
        catch (Exception ex) when (ex is IOException or
                                   InvalidOperationException or
                                   System.Security.SecurityException or
                                   UnauthorizedAccessException or
                                   NotSupportedException or
                                   JsonException or
                                   BadImageFormatException)
        {
            return Empty();
        }
    }

    private static SwedishFunctionWordData Empty() =>
        new(new HashSet<string>(), new HashSet<char>());

    /// <summary>
    /// Parse the JSON, reading the <c>function_words</c> (lowercased) and
    /// <c>strong_chars</c> arrays. Mirrors the Python loader: malformed or
    /// missing data yields empty sets rather than throwing, and unknown
    /// properties are ignored.
    /// </summary>
    /// <returns>The parsed data, or empty sets on any failure.</returns>
    internal static SwedishFunctionWordData Parse(Stream stream)
    {
        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(stream);
        }
        catch (JsonException)
        {
            return Empty();
        }

        using (doc)
        {
            if (doc.RootElement.ValueKind != JsonValueKind.Object)
            {
                return Empty();
            }

            JsonElement root = doc.RootElement;

            // function_words: list[str], lowercased, non-empty entries only.
            var functionWords = new HashSet<string>();
            if (root.TryGetProperty("function_words", out JsonElement wordsEl) &&
                wordsEl.ValueKind == JsonValueKind.Array)
            {
                foreach (JsonElement item in wordsEl.EnumerateArray()
                    .Where(e => e.ValueKind == JsonValueKind.String))
                {
                    string? w = item.GetString();
                    if (!string.IsNullOrEmpty(w))
                    {
                        functionWords.Add(w.ToLowerInvariant());
                    }
                }
            }

            // strong_chars: list[str]; each non-empty string contributes its
            // characters (a-ring / Å are single BMP code points). Iterating per
            // char mirrors Go's per-rune expansion for cross-runtime parity.
            var strongChars = new HashSet<char>();
            if (root.TryGetProperty("strong_chars", out JsonElement charsEl) &&
                charsEl.ValueKind == JsonValueKind.Array)
            {
                foreach (JsonElement item in charsEl.EnumerateArray()
                    .Where(e => e.ValueKind == JsonValueKind.String))
                {
                    string? s = item.GetString();
                    if (!string.IsNullOrEmpty(s))
                    {
                        foreach (char c in s)
                        {
                            strongChars.Add(c);
                        }
                    }
                }
            }

            return new SwedishFunctionWordData(functionWords, strongChars);
        }
    }
}
