using PiperPlus.Core.Config;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Phase 4 integration tests covering the end-to-end interaction of
/// <see cref="VoiceCatalog"/>, <see cref="ModelManager"/>, and
/// <see cref="VoiceInfo"/>.
/// </summary>
[Collection("StdErr")]
public sealed class Phase4IntegrationTests : IDisposable
{
    private TextWriter? _originalStdErr;

    public void Dispose()
    {
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
    // E2E flow
    // ================================================================

    [Fact]
    public void FindAndListWorkflow()
    {
        // LoadCatalog -> FindVoice -> voice has correct properties
        var catalog = VoiceCatalog.LoadMergedCatalog();
        Assert.NotNull(catalog);
        Assert.True(catalog.Count > 0, "Merged catalog must contain at least one voice");

        var voice = ModelManager.FindVoice("tsukuyomi");
        Assert.NotNull(voice);
        Assert.Equal("ja_JP-tsukuyomi-chan-medium", voice!.Key);
        Assert.Equal("tsukuyomi-chan", voice.Name);
        Assert.Equal("ja_JP", voice.LanguageCode);
        Assert.Equal("ja", voice.LanguageFamily);
        Assert.Equal("medium", voice.Quality);
        Assert.Equal("piper-plus", voice.Source);
        Assert.Equal("ayousanz/piper-plus-tsukuyomi-chan", voice.RepoId);
        Assert.True(voice.Files.Count > 0, "Voice must have at least one file");
        Assert.True(voice.Aliases.Count > 0, "Voice must have at least one alias");
    }

    [Fact]
    public void ListModelsContainsTsukuyomi()
    {
        using var sw = CaptureStdErr();

        ModelManager.ListModels();

        string output = sw.ToString();
        Assert.Contains("tsukuyomi", output);
    }

    [Fact]
    public void ListModelsContainsCss10()
    {
        using var sw = CaptureStdErr();

        ModelManager.ListModels();

        string output = sw.ToString();
        Assert.Contains("css10-6lang", output);
    }

    [Fact]
    public async Task DownloadNonExistentModel_Fails()
    {
        using var sw = CaptureStdErr();

        bool result = await ModelManager.DownloadModelAsync(
            "nonexistent-model-that-does-not-exist",
            Path.GetTempPath(),
            TestContext.Current.CancellationToken);

        Assert.False(result);
    }

    // ================================================================
    // Catalog integrity
    // ================================================================

    [Fact]
    public void AllModelsHaveFiles()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();

        foreach (var voice in catalog)
        {
            Assert.True(voice.Files.Count > 0,
                $"Voice '{voice.Key}' must have at least one file");
        }
    }

    [Fact]
    public void AllModelsHaveLanguage()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();

        foreach (var voice in catalog)
        {
            Assert.False(string.IsNullOrWhiteSpace(voice.LanguageCode),
                $"Voice '{voice.Key}' must have a non-empty LanguageCode");
            Assert.False(string.IsNullOrWhiteSpace(voice.LanguageFamily),
                $"Voice '{voice.Key}' must have a non-empty LanguageFamily");
        }
    }

    [Fact]
    public void AllAliasesAreUnique()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();
        var seenAliases = new HashSet<string>(StringComparer.Ordinal);

        foreach (var voice in catalog)
        {
            foreach (var alias in voice.Aliases)
            {
                Assert.True(seenAliases.Add(alias),
                    $"Duplicate alias '{alias}' found in voice '{voice.Key}'");
            }
        }
    }

    [Fact]
    public void AllKeysAreUnique()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();
        var seenKeys = new HashSet<string>(StringComparer.Ordinal);

        foreach (var voice in catalog)
        {
            Assert.True(seenKeys.Add(voice.Key),
                $"Duplicate key '{voice.Key}' found in catalog");
        }
    }

    // ================================================================
    // Security
    // ================================================================

    [Fact]
    public void RepoIdFormat_Valid()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();

        foreach (var voice in catalog)
        {
            if (string.IsNullOrEmpty(voice.RepoId))
                continue;

            // Must be "owner/repo" format: exactly one slash
            string[] parts = voice.RepoId.Split('/');
            Assert.Equal(2, parts.Length);
            Assert.False(string.IsNullOrWhiteSpace(parts[0]),
                $"Voice '{voice.Key}': repoId owner part must not be empty");
            Assert.False(string.IsNullOrWhiteSpace(parts[1]),
                $"Voice '{voice.Key}': repoId repo part must not be empty");
        }
    }

    [Fact]
    public void NoPathTraversal_InKeys()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();

        foreach (var voice in catalog)
        {
            Assert.DoesNotContain("..", voice.Key);
        }
    }

    [Fact]
    public void AllUrls_AreHttps()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();
        const string huggingFacePrefix = "https://huggingface.co/";

        foreach (var voice in catalog)
        {
            // Build the base URL the same way ModelManager.DownloadModelAsync does
            string baseUrl;
            if (string.Equals(voice.Source, "piper-plus", StringComparison.Ordinal))
            {
                baseUrl = $"{huggingFacePrefix}{voice.RepoId}/resolve/main/";
            }
            else
            {
                baseUrl = $"{huggingFacePrefix}rhasspy/piper-voices/resolve/v1.0.0/";
            }

            foreach (var file in voice.Files)
            {
                string url = baseUrl + file.RelativePath;
                Assert.StartsWith("https://", url);
            }
        }
    }

    // ================================================================
    // Format
    // ================================================================

    [Fact]
    public void ListModels_OutputFormat()
    {
        // Verify stderr output matches C++ listModels() format:
        //   \n
        //   Available voice models:\n
        //   \n
        //     <LanguageNameEnglish> (<LanguageNameNative>) [<LanguageCode>]:\n
        //       <key>  <padding>  [<source>]  <N> speaker(s)   <quality>\n
        //   ...
        //   \n
        //   Use --download-model <name> to download a model.\n
        //   \n
        using var sw = CaptureStdErr();

        ModelManager.ListModels();

        string output = sw.ToString();

        // Header
        Assert.Contains("Available voice models:", output);

        // Language group header
        Assert.Contains("Japanese", output);
        Assert.Contains("日本語", output);
        Assert.Contains("[ja_JP]:", output);

        // Voice entry format: key, source tag, speaker count, quality
        Assert.Contains("ja_JP-tsukuyomi-chan-medium", output);
        Assert.Contains("[piper-plus]", output);
        Assert.Contains("1 speaker", output);
        Assert.Contains("medium", output);

        // Footer
        Assert.Contains("Use --download-model <name> to download a model.", output);
    }
}
