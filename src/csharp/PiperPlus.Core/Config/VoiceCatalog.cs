using System.Text.Json;

namespace PiperPlus.Core.Config;

/// <summary>
/// Provides access to the piper-plus voice catalog.
/// Mirrors the C++ <c>loadVoiceCatalog()</c> function in <c>model_manager.cpp</c>.
/// </summary>
public static class VoiceCatalog
{
    // -------------------------------------------------------------------
    // Built-in catalog (object initializers — no JSON parsing at runtime)
    // -------------------------------------------------------------------

    private static readonly VoiceInfo[] BuiltInVoices =
    [
        new VoiceInfo(
            Key: "ja_JP-tsukuyomi-chan-medium",
            Name: "tsukuyomi-chan",
            LanguageCode: "ja_JP",
            LanguageFamily: "ja",
            LanguageNameNative: "日本語",
            LanguageNameEnglish: "Japanese",
            Quality: "medium",
            NumSpeakers: 1,
            Source: "piper-plus",
            RepoId: "ayousanz/piper-plus-tsukuyomi-chan",
            Files:
            [
                new VoiceFileInfo("tsukuyomi-chan-6lang-fp16.onnx", 39652717, ""),
                new VoiceFileInfo("config.json", 6279, ""),
            ],
            Aliases: ["tsukuyomi", "tsukuyomi-chan", "ja-tsukuyomi"],
            Description: "Tsukuyomi-chan 6-language TTS model fine-tuned from multilingual base (FP16, MB-iSTFT)"),

        new VoiceInfo(
            Key: "ja_JP-css10-6lang-medium",
            Name: "css10-6lang",
            LanguageCode: "ja_JP",
            LanguageFamily: "ja",
            LanguageNameNative: "日本語",
            LanguageNameEnglish: "Japanese",
            Quality: "medium",
            NumSpeakers: 1,
            Source: "piper-plus",
            RepoId: "ayousanz/piper-plus-css10-ja-6lang",
            Files:
            [
                new VoiceFileInfo("css10-ja-6lang-fp16.onnx", 39652717, ""),
                new VoiceFileInfo("config.json", 5912, ""),
            ],
            Aliases: ["css10", "css10-6lang", "css10-ja", "ja-css10"],
            Description: "CSS10 Japanese 6-language TTS model fine-tuned from multilingual base (FP16, MB-iSTFT, 6841 utterances)"),
    ];

    /// <summary>
    /// Returns the embedded piper-plus catalog (no I/O).
    /// </summary>
    public static IReadOnlyList<VoiceInfo> LoadBuiltInCatalog()
        => BuiltInVoices;

    /// <summary>
    /// Loads a voice catalog from an external <c>voices.json</c> file.
    /// The JSON format matches the C++ upstream catalog: a dictionary keyed by voice key.
    /// </summary>
    /// <exception cref="FileNotFoundException">Thrown when <paramref name="path"/> does not exist.</exception>
    /// <exception cref="InvalidOperationException">Thrown when deserialization fails.</exception>
    public static IReadOnlyList<VoiceInfo> LoadFromFile(string path)
    {
        if (!File.Exists(path))
        {
            throw new FileNotFoundException(
                $"Voices catalog file not found: {path}", path);
        }

        using var stream = File.OpenRead(path);
        var dict = JsonSerializer.Deserialize(
            stream,
            VoiceCatalogJsonContext.Default.DictionaryStringVoiceJsonEntry);

        if (dict is null)
        {
            throw new InvalidOperationException(
                $"Failed to deserialize voice catalog from: {path}");
        }

        var result = new List<VoiceInfo>(dict.Count);
        foreach (var (key, entry) in dict)
        {
            result.Add(VoiceJsonConverter.ToVoiceInfo(key, entry));
        }

        return result;
    }

    private static readonly Lazy<IReadOnlyList<VoiceInfo>> s_cachedCatalog =
        new(() => LoadMergedCatalogInternal(null));

    /// <summary>
    /// Returns the built-in catalog merged with an optional external <c>voices.json</c>.
    /// Built-in entries take precedence when keys collide (same semantics as the C++ implementation).
    /// The result is sorted by language code, then by key.
    /// When <paramref name="externalVoicesJsonPath"/> is <c>null</c>, the result is cached
    /// (thread-safe via <see cref="Lazy{T}"/>).
    /// </summary>
    public static IReadOnlyList<VoiceInfo> LoadMergedCatalog(string? externalVoicesJsonPath = null)
    {
        if (externalVoicesJsonPath is null)
            return s_cachedCatalog.Value;

        // External file specified — bypass cache
        return LoadMergedCatalogInternal(externalVoicesJsonPath);
    }

    private static IReadOnlyList<VoiceInfo> LoadMergedCatalogInternal(string? externalVoicesJsonPath)
    {
        var builtIn = LoadBuiltInCatalog();

        if (string.IsNullOrEmpty(externalVoicesJsonPath) || !File.Exists(externalVoicesJsonPath))
        {
            // Nothing to merge — return built-in sorted
            return SortCatalog(builtIn);
        }

        IReadOnlyList<VoiceInfo> external;
        try
        {
            external = LoadFromFile(externalVoicesJsonPath);
        }
        catch (Exception ex)
        {
            // If external file is unreadable, fall back to built-in only
            System.Diagnostics.Debug.WriteLine(
                $"Failed to load external voices catalog: {ex.Message}");
            return SortCatalog(builtIn);
        }

        // Merge: built-in keys win
        var merged = new Dictionary<string, VoiceInfo>(
            builtIn.Count + external.Count, StringComparer.Ordinal);

        foreach (var voice in builtIn)
        {
            merged[voice.Key] = voice;
        }

        foreach (var voice in external)
        {
            merged.TryAdd(voice.Key, voice);
        }

        return SortCatalog(merged.Values);
    }

    // -------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------

    /// <summary>
    /// Sorts voices by language code, then by key (same order as C++ loadVoiceCatalog).
    /// </summary>
    private static IReadOnlyList<VoiceInfo> SortCatalog(IEnumerable<VoiceInfo> voices)
    {
        var list = voices.ToList();
        list.Sort((a, b) =>
        {
            int cmp = string.Compare(a.LanguageCode, b.LanguageCode, StringComparison.Ordinal);
            return cmp != 0 ? cmp : string.Compare(a.Key, b.Key, StringComparison.Ordinal);
        });
        return list;
    }
}
