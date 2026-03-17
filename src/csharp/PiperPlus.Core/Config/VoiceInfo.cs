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
    string Description = "");
