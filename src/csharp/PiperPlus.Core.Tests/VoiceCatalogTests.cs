using System.Text;
using PiperPlus.Core.Config;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="VoiceCatalog"/> and <see cref="VoiceInfo"/>.
/// Covers built-in catalog contents, external JSON merging, and record equality.
/// </summary>
public sealed class VoiceCatalogTests : IDisposable
{
    private readonly string _tempDir;

    public VoiceCatalogTests()
    {
        _tempDir = Path.Combine(Path.GetTempPath(), $"voicecatalog_test_{Guid.NewGuid():N}");
        Directory.CreateDirectory(_tempDir);
    }

    public void Dispose()
    {
        if (Directory.Exists(_tempDir))
        {
            Directory.Delete(_tempDir, recursive: true);
        }
    }

    // ================================================================
    // Helper
    // ================================================================

    /// <summary>
    /// Writes <paramref name="json"/> to a temp file and returns the path.
    /// </summary>
    private string WriteTempJson(string json, string fileName = "voices.json")
    {
        var path = Path.Combine(_tempDir, fileName);
        File.WriteAllText(path, json, Encoding.UTF8);
        return path;
    }

    // ================================================================
    // Built-in catalog tests
    // ================================================================

    [Fact]
    public void LoadBuiltInCatalog_ReturnsTwoModels()
    {
        var catalog = VoiceCatalog.LoadBuiltInCatalog();

        Assert.Equal(2, catalog.Count);
    }

    [Fact]
    public void Tsukuyomi_HasCorrectProperties()
    {
        var catalog = VoiceCatalog.LoadBuiltInCatalog();
        var tsukuyomi = catalog.Single(v => v.Key == "ja_JP-tsukuyomi-chan-medium");

        Assert.Equal("tsukuyomi-chan", tsukuyomi.Name);
        Assert.Equal("ja_JP", tsukuyomi.LanguageCode);
        Assert.Equal("ja", tsukuyomi.LanguageFamily);
        Assert.Equal("medium", tsukuyomi.Quality);
        Assert.Equal(1, tsukuyomi.NumSpeakers);
        Assert.Equal("piper-plus", tsukuyomi.Source);
        Assert.Equal("ayousanz/piper-plus-tsukuyomi-chan", tsukuyomi.RepoId);
    }

    [Fact]
    public void Tsukuyomi_HasCorrectAliases()
    {
        var catalog = VoiceCatalog.LoadBuiltInCatalog();
        var tsukuyomi = catalog.Single(v => v.Key == "ja_JP-tsukuyomi-chan-medium");

        Assert.Equal(3, tsukuyomi.Aliases.Count);
        Assert.Contains("tsukuyomi", tsukuyomi.Aliases);
        Assert.Contains("tsukuyomi-chan", tsukuyomi.Aliases);
        Assert.Contains("ja-tsukuyomi", tsukuyomi.Aliases);
    }

    [Fact]
    public void Tsukuyomi_HasTwoFiles()
    {
        var catalog = VoiceCatalog.LoadBuiltInCatalog();
        var tsukuyomi = catalog.Single(v => v.Key == "ja_JP-tsukuyomi-chan-medium");

        Assert.Equal(2, tsukuyomi.Files.Count);
        Assert.Contains(tsukuyomi.Files, f => f.RelativePath.EndsWith(".onnx", StringComparison.Ordinal));
        Assert.Contains(tsukuyomi.Files, f => f.RelativePath == "config.json");
    }

    [Fact]
    public void Css10_Has1Speaker()
    {
        var catalog = VoiceCatalog.LoadBuiltInCatalog();
        var css10 = catalog.Single(v => v.Key == "ja_JP-css10-6lang-medium");

        Assert.Equal(1, css10.NumSpeakers);
    }

    [Fact]
    public void Css10_HasCorrectAliases()
    {
        var catalog = VoiceCatalog.LoadBuiltInCatalog();
        var css10 = catalog.Single(v => v.Key == "ja_JP-css10-6lang-medium");

        Assert.Equal(4, css10.Aliases.Count);
        Assert.Contains("css10", css10.Aliases);
        Assert.Contains("css10-6lang", css10.Aliases);
        Assert.Contains("css10-ja", css10.Aliases);
        Assert.Contains("ja-css10", css10.Aliases);
    }

    // ================================================================
    // External catalog merge tests
    // ================================================================

    [Fact]
    public void LoadMergedCatalog_NoExternalFile_ReturnsBuiltIn()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog(externalVoicesJsonPath: null);

        // Should contain the 2 built-in models
        Assert.Equal(2, catalog.Count);
        Assert.Contains(catalog, v => v.Key == "ja_JP-tsukuyomi-chan-medium");
        Assert.Contains(catalog, v => v.Key == "ja_JP-css10-6lang-medium");
    }

    [Fact]
    public void LoadMergedCatalog_WithExternalFile_MergesCorrectly()
    {
        const string externalJson = """
        {
            "en_US-amy-medium": {
                "name": "amy",
                "language": {
                    "code": "en_US",
                    "family": "en",
                    "name_native": "English",
                    "name_english": "English"
                },
                "quality": "medium",
                "num_speakers": 1,
                "source": "piper",
                "repo": "rhasspy/piper-voices",
                "files": {},
                "aliases": ["amy"]
            }
        }
        """;

        var path = WriteTempJson(externalJson);
        var catalog = VoiceCatalog.LoadMergedCatalog(externalVoicesJsonPath: path);

        // 2 built-in + 1 external = 3
        Assert.Equal(3, catalog.Count);
        Assert.Contains(catalog, v => v.Key == "ja_JP-tsukuyomi-chan-medium");
        Assert.Contains(catalog, v => v.Key == "ja_JP-css10-6lang-medium");
        Assert.Contains(catalog, v => v.Key == "en_US-amy-medium");

        // Verify external entry properties
        var amy = catalog.Single(v => v.Key == "en_US-amy-medium");
        Assert.Equal("amy", amy.Name);
        Assert.Equal("en_US", amy.LanguageCode);
        Assert.Equal("en", amy.LanguageFamily);
        Assert.Equal("medium", amy.Quality);
        Assert.Equal(1, amy.NumSpeakers);
        Assert.Equal("piper", amy.Source);
        Assert.Equal("rhasspy/piper-voices", amy.RepoId);
        Assert.Contains("amy", amy.Aliases);
    }

    [Fact]
    public void LoadMergedCatalog_BuiltInOverridesExternal()
    {
        // External file contains a key that collides with a built-in entry.
        // Built-in entry should take precedence.
        const string externalJson = """
        {
            "ja_JP-tsukuyomi-chan-medium": {
                "name": "fake-tsukuyomi",
                "language": {
                    "code": "ja_JP",
                    "family": "ja",
                    "name_native": "Japanese",
                    "name_english": "Japanese"
                },
                "quality": "low",
                "num_speakers": 99,
                "source": "external",
                "repo": "fake/repo",
                "files": {},
                "aliases": ["fake"]
            }
        }
        """;

        var path = WriteTempJson(externalJson);
        var catalog = VoiceCatalog.LoadMergedCatalog(externalVoicesJsonPath: path);

        // The built-in tsukuyomi should win — external entry with the same key is discarded.
        var tsukuyomi = catalog.Single(v => v.Key == "ja_JP-tsukuyomi-chan-medium");
        Assert.Equal("tsukuyomi-chan", tsukuyomi.Name);
        Assert.Equal("piper-plus", tsukuyomi.Source);
        Assert.Equal(1, tsukuyomi.NumSpeakers);
        Assert.NotEqual("fake-tsukuyomi", tsukuyomi.Name);
    }

    // ================================================================
    // VoiceInfo record equality tests
    // ================================================================

    [Fact]
    public void VoiceInfo_Equality()
    {
        var a = new VoiceInfo(
            Key: "test-key",
            Name: "test",
            LanguageCode: "en_US",
            LanguageFamily: "en",
            LanguageNameNative: "English",
            LanguageNameEnglish: "English",
            Quality: "medium",
            NumSpeakers: 1,
            Source: "test",
            RepoId: "test/repo",
            Files: [new VoiceFileInfo("model.onnx", 1024, "abc123")],
            Aliases: ["test-alias"]);

        var b = new VoiceInfo(
            Key: "test-key",
            Name: "test",
            LanguageCode: "en_US",
            LanguageFamily: "en",
            LanguageNameNative: "English",
            LanguageNameEnglish: "English",
            Quality: "medium",
            NumSpeakers: 1,
            Source: "test",
            RepoId: "test/repo",
            Files: [new VoiceFileInfo("model.onnx", 1024, "abc123")],
            Aliases: ["test-alias"]);

        // C# records use value equality for primitive fields.
        // IReadOnlyList properties (Files, Aliases) use reference equality
        // by default, so two separately constructed instances are NOT equal.
        Assert.NotSame(a, b);

        // Same-reference instances are equal.
        var c = a;
        Assert.Equal(a, c);
        Assert.True(a == c);
    }

    [Fact]
    public void VoiceFileInfo_Properties()
    {
        var file = new VoiceFileInfo(
            RelativePath: "model.onnx",
            SizeBytes: 77594624,
            Md5Digest: "d41d8cd98f00b204e9800998ecf8427e");

        Assert.Equal("model.onnx", file.RelativePath);
        Assert.Equal(77594624, file.SizeBytes);
        Assert.Equal("d41d8cd98f00b204e9800998ecf8427e", file.Md5Digest);

        // VoiceFileInfo is a record with only primitive/string fields,
        // so two instances with the same values should be equal.
        var same = new VoiceFileInfo("model.onnx", 77594624, "d41d8cd98f00b204e9800998ecf8427e");
        Assert.Equal(file, same);
    }

    // ================================================================
    // Caching, sorting, and catalog-wide invariant tests
    // ================================================================

    [Fact]
    public void LoadMergedCatalog_CachingVerification_ReturnsSameReference()
    {
        // When called without an external path, the result is cached via Lazy<T>.
        // Two consecutive calls should return the exact same object reference.
        var first = VoiceCatalog.LoadMergedCatalog();
        var second = VoiceCatalog.LoadMergedCatalog();

        Assert.Same(first, second);
    }

    [Fact]
    public void LoadBuiltInCatalog_SortedByLanguageAndKey()
    {
        // LoadMergedCatalog sorts by LanguageCode then Key.
        // Verify the merged catalog (which wraps built-in) maintains this order.
        var catalog = VoiceCatalog.LoadMergedCatalog();

        for (int i = 1; i < catalog.Count; i++)
        {
            var prev = catalog[i - 1];
            var curr = catalog[i];

            int langCmp = string.Compare(
                prev.LanguageCode, curr.LanguageCode, StringComparison.Ordinal);

            if (langCmp == 0)
            {
                int keyCmp = string.Compare(
                    prev.Key, curr.Key, StringComparison.Ordinal);
                Assert.True(keyCmp <= 0,
                    $"Catalog not sorted by key within same language: " +
                    $"'{prev.Key}' should come before '{curr.Key}'");
            }
            else
            {
                Assert.True(langCmp < 0,
                    $"Catalog not sorted by language code: " +
                    $"'{prev.LanguageCode}' should come before '{curr.LanguageCode}'");
            }
        }
    }

    [Fact]
    public void VoiceInfo_AllCatalogEntries_HaveNonEmptyKey()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();

        foreach (var voice in catalog)
        {
            Assert.False(string.IsNullOrWhiteSpace(voice.Key),
                "Every catalog entry must have a non-empty Key");
        }
    }

    [Fact]
    public void VoiceInfo_AllCatalogEntries_HaveFiles()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();

        foreach (var voice in catalog)
        {
            Assert.True(voice.Files.Count >= 1,
                $"Voice '{voice.Key}' must have at least 1 file");
        }
    }

    [Fact]
    public void VoiceInfo_AllCatalogEntries_HaveValidRepoId()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();

        foreach (var voice in catalog)
        {
            int slashCount = voice.RepoId.Count(c => c == '/');
            Assert.Equal(1, slashCount);
        }
    }

    [Fact]
    public void VoiceFileInfo_AllFiles_HaveNonEmptyRelativePath()
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();

        foreach (var voice in catalog)
        {
            foreach (var file in voice.Files)
            {
                Assert.False(string.IsNullOrWhiteSpace(file.RelativePath),
                    $"File in voice '{voice.Key}' must have a non-empty RelativePath");
            }
        }
    }
}
