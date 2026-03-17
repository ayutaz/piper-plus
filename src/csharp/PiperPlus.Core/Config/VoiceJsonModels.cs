using System.Text.Json;
using System.Text.Json.Serialization;

namespace PiperPlus.Core.Config;

// -----------------------------------------------------------------------
// JSON-serializable DTOs for external voices.json deserialization.
// Used by VoiceCatalog.LoadFromFile() to parse the upstream piper
// voices.json format.
// -----------------------------------------------------------------------

/// <summary>
/// Represents a single voice entry inside the top-level voices JSON dictionary.
/// Maps the JSON structure used by C++ <c>parseVoiceEntry</c> in <c>model_manager.cpp</c>.
/// </summary>
internal sealed class VoiceJsonEntry
{
    [JsonPropertyName("name")]
    public string Name { get; set; } = "";

    [JsonPropertyName("language")]
    public VoiceLanguageJson? Language { get; set; }

    [JsonPropertyName("quality")]
    public string Quality { get; set; } = "";

    [JsonPropertyName("num_speakers")]
    public int NumSpeakers { get; set; } = 1;

    [JsonPropertyName("source")]
    public string Source { get; set; } = "";

    [JsonPropertyName("repo")]
    public string Repo { get; set; } = "";

    [JsonPropertyName("files")]
    public Dictionary<string, VoiceFileJson>? Files { get; set; }

    [JsonPropertyName("aliases")]
    public List<string>? Aliases { get; set; }

    [JsonPropertyName("description")]
    public string Description { get; set; } = "";

    [JsonPropertyName("speaker_id_map")]
    public Dictionary<string, int>? SpeakerIdMap { get; set; }
}

/// <summary>
/// Represents the "language" block inside a voice entry JSON object.
/// </summary>
internal sealed class VoiceLanguageJson
{
    [JsonPropertyName("code")]
    public string Code { get; set; } = "";

    [JsonPropertyName("family")]
    public string Family { get; set; } = "";

    [JsonPropertyName("name_native")]
    public string NameNative { get; set; } = "";

    [JsonPropertyName("name_english")]
    public string NameEnglish { get; set; } = "";
}

/// <summary>
/// Represents a single file entry inside the "files" dictionary of a voice JSON object.
/// </summary>
internal sealed class VoiceFileJson
{
    [JsonPropertyName("size_bytes")]
    public long SizeBytes { get; set; }

    [JsonPropertyName("md5_digest")]
    public string Md5Digest { get; set; } = "";
}

/// <summary>
/// Converts <see cref="VoiceJsonEntry"/> DTOs into <see cref="VoiceInfo"/> records.
/// </summary>
internal static class VoiceJsonConverter
{
    /// <summary>
    /// Converts a single <see cref="VoiceJsonEntry"/> to a <see cref="VoiceInfo"/> record.
    /// </summary>
    /// <param name="key">The dictionary key from the voices.json root object.</param>
    /// <param name="entry">The deserialized JSON entry.</param>
    /// <param name="defaultSource">
    /// Fallback value for <see cref="VoiceInfo.Source"/> when the entry has no
    /// explicit "source" field. Matches the C++ <c>parseVoiceEntry</c> semantics.
    /// </param>
    public static VoiceInfo ToVoiceInfo(
        string key,
        VoiceJsonEntry entry,
        string defaultSource = "piper")
    {
        // Convert files dictionary to VoiceFileInfo list
        var files = new List<VoiceFileInfo>();
        if (entry.Files is not null)
        {
            foreach (var (relativePath, fileJson) in entry.Files)
            {
                files.Add(new VoiceFileInfo(relativePath, fileJson.SizeBytes, fileJson.Md5Digest));
            }
        }

        var lang = entry.Language;

        return new VoiceInfo(
            Key: key,
            Name: entry.Name,
            LanguageCode: lang?.Code ?? "",
            LanguageFamily: lang?.Family ?? "",
            LanguageNameNative: lang?.NameNative ?? "",
            LanguageNameEnglish: lang?.NameEnglish ?? "",
            Quality: entry.Quality,
            NumSpeakers: entry.NumSpeakers,
            Source: string.IsNullOrEmpty(entry.Source) ? defaultSource : entry.Source,
            RepoId: entry.Repo,
            Files: files,
            Aliases: entry.Aliases ?? [],
            Description: entry.Description);
    }
}

/// <summary>
/// Source-generated JSON serializer context for trim-safe / AOT-safe deserialization
/// of external voices.json files.
/// </summary>
[JsonSerializable(typeof(Dictionary<string, VoiceJsonEntry>))]
[JsonSourceGenerationOptions(
    PropertyNameCaseInsensitive = false,
    ReadCommentHandling = JsonCommentHandling.Skip,
    AllowTrailingCommas = true)]
internal partial class VoiceCatalogJsonContext : JsonSerializerContext;
