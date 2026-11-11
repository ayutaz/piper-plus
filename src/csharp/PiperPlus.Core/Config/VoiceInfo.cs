namespace PiperPlus.Core.Config;

/// <summary>
/// Describes a single downloadable file belonging to a voice model.
/// Mirrors the C++ <c>VoiceFileInfo</c> struct in <c>model_manager.hpp</c>.
/// </summary>
public record VoiceFileInfo(
    string RelativePath,
    long SizeBytes,
    string Md5Digest);

/// <summary>
/// Describes a voice model entry in the catalog.
/// Mirrors the C++ <c>VoiceInfo</c> struct in <c>model_manager.hpp</c>.
/// </summary>
public record VoiceInfo(
    string Key,
    string Name,
    string LanguageCode,
    string LanguageFamily,
    string LanguageNameNative,
    string LanguageNameEnglish,
    string Quality,
    int NumSpeakers,
    string Source,
    string RepoId,
    IReadOnlyList<VoiceFileInfo> Files,
    IReadOnlyList<string> Aliases,
    string Description = "")
{
    /// <summary>HuggingFace revision for pinned model downloads.</summary>
    public string Revision { get; init; } = "main";

    /// <summary>
    /// Usage notice (terms, required credit) to show when this model is used.
    /// Empty for models without usage conditions. Executables print it to
    /// stderr; the library never prints it (docs/reference/model-resolution.md §9).
    /// </summary>
    public IReadOnlyList<string> Notice { get; init; } = [];

    /// <summary>
    /// Model file names that identify this model when given as a path, used to
    /// decide whether <see cref="Notice"/> applies to a local file.
    /// </summary>
    public IReadOnlyList<string> NoticeFiles { get; init; } = [];
}
