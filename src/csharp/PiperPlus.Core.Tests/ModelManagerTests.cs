using PiperPlus.Core.Config;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="ModelManager"/>.
/// Covers <c>GetDefaultModelDir</c>, <c>FindVoice</c>, and <c>ListModels</c>.
/// These tests validate the embedded piper-plus voice catalog behavior
/// that mirrors the C++ model_manager.cpp and Python download.py implementations.
/// </summary>
public sealed class ModelManagerTests : IDisposable
{
    private TextWriter? _originalStdErr;

    public void Dispose()
    {
        // Restore Console.Error if it was redirected during a test
        if (_originalStdErr is not null)
        {
            Console.SetError(_originalStdErr);
            _originalStdErr = null;
        }
    }

    /// <summary>
    /// Redirects <see cref="Console.Error"/> to a <see cref="StringWriter"/>
    /// and returns it. The original stderr is saved for restoration in
    /// <see cref="Dispose"/>.
    /// </summary>
    private StringWriter CaptureStdErr()
    {
        _originalStdErr = Console.Error;
        var sw = new StringWriter();
        Console.SetError(sw);
        return sw;
    }

    // ================================================================
    // GetDefaultModelDir
    // ================================================================

    [Fact]
    public void GetDefaultModelDir_ReturnsNonEmpty()
    {
        string dir = ModelManager.GetDefaultModelDir();

        Assert.False(string.IsNullOrWhiteSpace(dir),
            "GetDefaultModelDir() must return a non-empty string");
    }

    [Fact]
    public void GetDefaultModelDir_ContainsPiperModels()
    {
        string dir = ModelManager.GetDefaultModelDir();
        string lower = dir.ToLowerInvariant();

        Assert.Contains("piper", lower);
        Assert.Contains("models", lower);
    }

    // ================================================================
    // FindVoice — exact key
    // ================================================================

    [Fact]
    public void FindVoice_ByExactKey()
    {
        var voice = ModelManager.FindVoice("ja_JP-tsukuyomi-chan-medium");

        Assert.NotNull(voice);
        Assert.Equal("ja_JP-tsukuyomi-chan-medium", voice!.Key);
        Assert.Equal("tsukuyomi-chan", voice.Name);
        Assert.Equal("ja_JP", voice.LanguageCode);
        Assert.Equal("ja", voice.LanguageFamily);
        Assert.Equal("medium", voice.Quality);
        Assert.Equal("piper-plus", voice.Source);
    }

    // ================================================================
    // FindVoice — alias lookups
    // ================================================================

    [Fact]
    public void FindVoice_ByAlias_Tsukuyomi()
    {
        var voice = ModelManager.FindVoice("tsukuyomi");

        Assert.NotNull(voice);
        Assert.Equal("ja_JP-tsukuyomi-chan-medium", voice!.Key);
        Assert.Equal("tsukuyomi-chan", voice.Name);
    }

    [Fact]
    public void FindVoice_ByAlias_MoeSpeech()
    {
        var voice = ModelManager.FindVoice("moe-speech");

        Assert.NotNull(voice);
        Assert.Equal("ja_JP-moe-speech-20speakers-medium", voice!.Key);
        Assert.Equal("moe-speech-20speakers", voice.Name);
        Assert.Equal(20, voice.NumSpeakers);
    }

    // ================================================================
    // FindVoice — not-found / edge cases
    // ================================================================

    [Fact]
    public void FindVoice_NotFound()
    {
        var voice = ModelManager.FindVoice("nonexistent-model");

        Assert.Null(voice);
    }

    [Fact]
    public void FindVoice_EmptyString()
    {
        var voice = ModelManager.FindVoice("");

        Assert.Null(voice);
    }

    [Fact]
    public void FindVoice_CaseSensitive()
    {
        // Aliases are case-sensitive (exact match only), matching C++ behavior.
        var voice = ModelManager.FindVoice("Tsukuyomi");

        Assert.Null(voice);
    }

    // ================================================================
    // ListModels
    // ================================================================

    [Fact]
    public void ListModels_NoFilter_OutputsAllModels()
    {
        using var sw = CaptureStdErr();

        ModelManager.ListModels(null);

        string output = sw.ToString();

        // The catalog contains both piper-plus voices
        Assert.Contains("ja_JP-tsukuyomi-chan-medium", output);
        Assert.Contains("ja_JP-moe-speech-20speakers-medium", output);
        Assert.Contains("Available voice models:", output);
    }

    [Fact]
    public void ListModels_JapaneseFilter()
    {
        using var sw = CaptureStdErr();

        ModelManager.ListModels("ja");

        string output = sw.ToString();

        // Japanese models should appear
        Assert.Contains("ja_JP-tsukuyomi-chan-medium", output);
        Assert.Contains("ja_JP-moe-speech-20speakers-medium", output);
        Assert.Contains("Japanese", output);
    }

    [Fact]
    public void ListModels_UnknownLanguage()
    {
        using var sw = CaptureStdErr();

        ModelManager.ListModels("xx");

        string output = sw.ToString();

        Assert.Contains("No voice models found for language: xx", output);
    }

    // ================================================================
    // Security validation
    // ================================================================

    [Fact]
    public void FindVoice_PathTraversalKey_Rejected()
    {
        // Keys containing ".." should not match any catalog entry.
        // Even if a malicious catalog entry existed, the key validation
        // in downloadModel would reject it. FindVoice itself simply
        // returns null for unknown keys.
        var voice = ModelManager.FindVoice("../../../etc/passwd");

        Assert.Null(voice);
    }

    [Fact]
    public async Task DownloadModelAsync_InvalidName_ReturnsFalse()
    {
        // Attempting to download a model that does not exist in the catalog
        // should fail gracefully (return false) without making HTTP requests.
        // Capture stderr to suppress the "not found" error message.
        using var sw = CaptureStdErr();

        bool result = await ModelManager.DownloadModelAsync(
            "nonexistent-model-xyz", Path.GetTempPath());

        Assert.False(result);
    }
}
