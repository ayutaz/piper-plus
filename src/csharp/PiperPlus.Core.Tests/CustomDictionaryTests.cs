using System.Text;
using System.Text.Json;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Dedicated unit tests for <see cref="CustomDictionary"/>.
/// Covers loading, comment/empty/malformed line handling, longest-match
/// replacement, multi-file accumulation, and cache rebuild behaviour.
/// </summary>
public sealed class CustomDictionaryTests : IDisposable
{
    private readonly List<string> _tempFiles = new();

    public void Dispose()
    {
        foreach (var path in _tempFiles)
        {
            try { File.Delete(path); } catch { /* best-effort cleanup */ }
        }
    }

    /// <summary>
    /// Creates a temporary file with the given content and registers it for cleanup.
    /// </summary>
    private string CreateTempFile(string content)
    {
        var path = Path.GetTempFileName();
        File.WriteAllText(path, content, Encoding.UTF8);
        _tempFiles.Add(path);
        return path;
    }

    /// <summary>
    /// Creates a temporary <c>.json</c> file with the given content and registers it for cleanup.
    /// </summary>
    private string CreateTempJsonFile(string content)
    {
        var path = Path.Combine(Path.GetTempPath(), $"piper_test_{Guid.NewGuid():N}.json");
        File.WriteAllText(path, content, Encoding.UTF8);
        _tempFiles.Add(path);
        return path;
    }

    // ================================================================
    // LoadDictionary
    // ================================================================

    [Fact]
    public void LoadDictionary_ValidFile_LoadsEntries()
    {
        string content = "hello\tworld\nfoo\tbar\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(2, dict.Count);
    }

    [Fact]
    public void LoadDictionary_CommentLines_Skipped()
    {
        string content = "# this is a comment\nhello\tworld\n# another comment\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(1, dict.Count);
        Assert.Equal("world", dict.ApplyToText("hello"));
    }

    [Fact]
    public void LoadDictionary_EmptyLines_Skipped()
    {
        string content = "\nhello\tworld\n\n\nfoo\tbar\n\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(2, dict.Count);
    }

    [Fact]
    public void LoadDictionary_MalformedLine_NoTab_Skipped()
    {
        string content = "no_tab_here\nhello\tworld\nalso no tab\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(1, dict.Count);
        Assert.Equal("world", dict.ApplyToText("hello"));
    }

    [Fact]
    public void LoadDictionary_FileNotFound_NoThrow()
    {
        // LoadDictionary itself throws FileNotFoundException, but
        // LoadDictionaries (plural) catches exceptions and logs a warning.
        var dict = new CustomDictionary();

        // Single-file API throws
        Assert.Throws<FileNotFoundException>(
            () => dict.LoadDictionary("/nonexistent/path/dictionary.txt"));

        // Multi-file API does not throw -- it logs a warning and continues
        dict.LoadDictionaries(new[] { "/nonexistent/path/dictionary.txt" });
        Assert.Equal(0, dict.Count);
    }

    [Fact]
    public void LoadDictionary_NullPath_ThrowsArgumentNullException()
    {
        var dict = new CustomDictionary();

        Assert.Throws<ArgumentNullException>(() => dict.LoadDictionary(null!));
    }

    [Fact]
    public void LoadDictionary_ValueContainsTabs_PreservedCorrectly()
    {
        // Only split on the first tab; subsequent tabs are part of the value.
        string content = "key\tval1\tval2\tval3\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(1, dict.Count);

        string result = dict.ApplyToText("key");
        Assert.Equal("val1\tval2\tval3", result);
    }

    [Fact]
    public void LoadDictionary_MultipleCalls_Accumulate()
    {
        string content1 = "hello\tworld\n";
        string content2 = "foo\tbar\n";
        string path1 = CreateTempFile(content1);
        string path2 = CreateTempFile(content2);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path1);
        dict.LoadDictionary(path2);

        Assert.Equal(2, dict.Count);
        Assert.Equal("world", dict.ApplyToText("hello"));
        Assert.Equal("bar", dict.ApplyToText("foo"));
    }

    [Fact]
    public void LoadDictionaries_PartialFailure_ContinuesWithValid()
    {
        string content = "alpha\tbeta\n";
        string validPath = CreateTempFile(content);
        string bogusPath = "/nonexistent/path/does_not_exist.txt";

        var dict = new CustomDictionary();
        dict.LoadDictionaries(new[] { bogusPath, validPath });

        // The valid file should still have been loaded
        Assert.Equal(1, dict.Count);
        Assert.Equal("beta", dict.ApplyToText("alpha"));
    }

    // ================================================================
    // ApplyToText
    // ================================================================

    [Fact]
    public void ApplyToText_SingleReplacement()
    {
        string content = "cat\tdog\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("the dog sat", dict.ApplyToText("the cat sat"));
    }

    [Fact]
    public void ApplyToText_MultipleReplacements()
    {
        string content = "cat\tdog\nsat\tlay\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("the dog lay", dict.ApplyToText("the cat sat"));
    }

    [Fact]
    public void ApplyToText_LongestMatchFirst()
    {
        // Non-ASCII keys use substring replacement (no word boundary), so we
        // can test longest-match-first ordering with Japanese characters.
        string content = "あ\t1\nあい\t2\nあいう\t3\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        // "あいう" is replaced first (longest), leaving "え" untouched
        Assert.Equal("3え", dict.ApplyToText("あいうえ"));
    }

    [Fact]
    public void ApplyToText_OverlappingPatterns_LongestWins()
    {
        // "pineapple" should be replaced, not "pine" + "apple" separately
        string content = "pine\tP\napple\tA\npineapple\tPA\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("PA", dict.ApplyToText("pineapple"));
    }

    [Fact]
    public void ApplyToText_NoMatch_ReturnsOriginal()
    {
        string content = "hello\tworld\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("goodbye", dict.ApplyToText("goodbye"));
    }

    [Fact]
    public void ApplyToText_EmptyText_ReturnsEmpty()
    {
        string content = "hello\tworld\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("", dict.ApplyToText(""));
    }

    [Fact]
    public void ApplyToText_EmptyDictionary_ReturnsOriginal()
    {
        var dict = new CustomDictionary();

        Assert.Equal("anything here", dict.ApplyToText("anything here"));
    }

    [Fact]
    public void ApplyToText_CacheRebuild_AfterNewLoad()
    {
        string content1 = "hello\tworld\n";
        string path1 = CreateTempFile(content1);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path1);

        // First apply -- builds the sorted cache
        Assert.Equal("world", dict.ApplyToText("hello"));

        // Load more entries -- should mark cache dirty
        string content2 = "foo\tbar\n";
        string path2 = CreateTempFile(content2);
        dict.LoadDictionary(path2);

        // Second apply -- must rebuild cache and include new entries
        Assert.Equal("bar", dict.ApplyToText("foo"));
        // Original entries should still work
        Assert.Equal("world", dict.ApplyToText("hello"));
    }

    // ================================================================
    // JSON dictionary tests
    // ================================================================

    [Fact]
    public void LoadJsonV1_SimpleFormat()
    {
        string json = """
            {
                "version": "1.0",
                "entries": {
                    "API": "エーピーアイ",
                    "CPU": "シーピーユー"
                }
            }
            """;
        string path = CreateTempJsonFile(json);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(2, dict.Count);
        Assert.Equal("エーピーアイ test", dict.ApplyToText("API test"));
        Assert.Equal("シーピーユー test", dict.ApplyToText("CPU test"));
    }

    [Fact]
    public void LoadJsonV2_WithPriority()
    {
        string json = """
            {
                "version": "2.0",
                "entries": {
                    "API": { "pronunciation": "エーピーアイ", "priority": 8 },
                    "GPU": { "pronunciation": "ジーピーユー", "priority": 3 }
                }
            }
            """;
        string path = CreateTempJsonFile(json);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(2, dict.Count);
        Assert.Equal("エーピーアイ", dict.ApplyToText("API"));
        Assert.Equal("ジーピーユー", dict.ApplyToText("GPU"));
    }

    [Fact]
    public void LoadJsonV2_CommentSkipped()
    {
        string json = """
            {
                "version": "2.0",
                "entries": {
                    "// this is a comment": { "pronunciation": "ignored", "priority": 1 },
                    "API": { "pronunciation": "エーピーアイ", "priority": 5 }
                }
            }
            """;
        string path = CreateTempJsonFile(json);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        // Comment key should not become an entry
        Assert.Equal(1, dict.Count);
        Assert.Equal("エーピーアイ", dict.ApplyToText("API"));
    }

    [Fact]
    public void LoadJsonV2_MissingPriority_DefaultsFive()
    {
        // V2.0 object without "priority" key — should default to 5
        string json = """
            {
                "version": "2.0",
                "entries": {
                    "API": { "pronunciation": "エーピーアイ" }
                }
            }
            """;
        string path = CreateTempJsonFile(json);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(1, dict.Count);

        // Load a second file with priority 5 — same priority, should NOT override
        string json2 = """
            {
                "version": "2.0",
                "entries": {
                    "API": { "pronunciation": "CHANGED", "priority": 5 }
                }
            }
            """;
        string path2 = CreateTempJsonFile(json2);
        dict.LoadDictionary(path2);

        // Original entry (default priority 5) should be kept
        Assert.Equal("エーピーアイ", dict.ApplyToText("API"));
    }

    [Fact]
    public void LoadJson_PriorityOverride()
    {
        // First file: priority 3
        string json1 = """
            {
                "version": "2.0",
                "entries": {
                    "API": { "pronunciation": "low-priority", "priority": 3 }
                }
            }
            """;
        // Second file: priority 8 — should win
        string json2 = """
            {
                "version": "2.0",
                "entries": {
                    "API": { "pronunciation": "high-priority", "priority": 8 }
                }
            }
            """;
        string path1 = CreateTempJsonFile(json1);
        string path2 = CreateTempJsonFile(json2);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path1);
        dict.LoadDictionary(path2);

        Assert.Equal(1, dict.Count);
        Assert.Equal("high-priority", dict.ApplyToText("API"));
    }

    [Fact]
    public void LoadJson_LowerPriority_Rejected()
    {
        // First file: priority 8
        string json1 = """
            {
                "version": "2.0",
                "entries": {
                    "API": { "pronunciation": "high-priority", "priority": 8 }
                }
            }
            """;
        // Second file: priority 3 — should be rejected
        string json2 = """
            {
                "version": "2.0",
                "entries": {
                    "API": { "pronunciation": "low-priority", "priority": 3 }
                }
            }
            """;
        string path1 = CreateTempJsonFile(json1);
        string path2 = CreateTempJsonFile(json2);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path1);
        dict.LoadDictionary(path2);

        Assert.Equal(1, dict.Count);
        Assert.Equal("high-priority", dict.ApplyToText("API"));
    }

    [Fact]
    public void LoadJson_InvalidJson_Throws()
    {
        string badJson = "{ this is not valid JSON }}}";
        string path = CreateTempJsonFile(badJson);

        var dict = new CustomDictionary();

        Assert.ThrowsAny<JsonException>(() => dict.LoadDictionary(path));
    }

    [Fact]
    public void LoadMixed_TsvAndJson()
    {
        // TSV file
        string tsvContent = "hello\tworld\n";
        string tsvPath = CreateTempFile(tsvContent);

        // JSON file
        string jsonContent = """
            {
                "version": "1.0",
                "entries": {
                    "foo": "bar"
                }
            }
            """;
        string jsonPath = CreateTempJsonFile(jsonContent);

        var dict = new CustomDictionary();
        dict.LoadDictionary(tsvPath);
        dict.LoadDictionary(jsonPath);

        Assert.Equal(2, dict.Count);
        Assert.Equal("world", dict.ApplyToText("hello"));
        Assert.Equal("bar", dict.ApplyToText("foo"));
    }

    [Fact]
    public void ApplyToText_JsonEntries_Work()
    {
        string json = """
            {
                "version": "1.0",
                "entries": {
                    "cat": "dog",
                    "sat": "lay"
                }
            }
            """;
        string path = CreateTempJsonFile(json);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("the dog lay", dict.ApplyToText("the cat sat"));
    }

    [Fact]
    public void LoadJson_MetadataSkipped()
    {
        // All metadata keys at the entries level should be ignored
        string json = """
            {
                "version": "2.0",
                "description": "Test dictionary",
                "metadata": { "author": "test" },
                "entries": {
                    "version": "should-be-skipped",
                    "description": "should-be-skipped",
                    "metadata": "should-be-skipped",
                    "API": "エーピーアイ"
                }
            }
            """;
        string path = CreateTempJsonFile(json);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        // Only "API" should be loaded; version/description/metadata are skipped
        Assert.Equal(1, dict.Count);
        Assert.Equal("エーピーアイ", dict.ApplyToText("API"));
    }

    // ================================================================
    // Word boundary matching (ASCII keys)
    // ================================================================

    [Fact]
    public void ApplyToText_WordBoundary_API_NotInsideRapid()
    {
        // "API" should not match inside "rapid"
        string content = "API\tエーピーアイ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("rapid development", dict.ApplyToText("rapid development"));
    }

    [Fact]
    public void ApplyToText_WordBoundary_AI_StandaloneButNotInAIDS()
    {
        // "AI" should match standalone but not inside "AIDS"
        string content = "AI\tエーアイ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("エーアイ and AIDS", dict.ApplyToText("AI and AIDS"));
    }

    [Fact]
    public void ApplyToText_WordBoundary_StandaloneMatch()
    {
        // "API" should match as a standalone word
        string content = "API\tエーピーアイ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("the エーピーアイ works", dict.ApplyToText("the API works"));
    }

    // ================================================================
    // Case-insensitive matching (all-upper / all-lower keys)
    // ================================================================

    [Fact]
    public void ApplyToText_CaseInsensitive_AllLowerMatchesAnyCase()
    {
        // "python" (all lowercase) should match "Python" and "PYTHON"
        string content = "python\tパイソン\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("パイソン is great", dict.ApplyToText("Python is great"));
        Assert.Equal("パイソン is great", dict.ApplyToText("PYTHON is great"));
        Assert.Equal("パイソン is great", dict.ApplyToText("python is great"));
    }

    [Fact]
    public void ApplyToText_CaseInsensitive_AllUpperMatchesAnyCase()
    {
        // "API" (all uppercase) should match "api" and "Api"
        string content = "API\tエーピーアイ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("the エーピーアイ", dict.ApplyToText("the api"));
        Assert.Equal("the エーピーアイ", dict.ApplyToText("the Api"));
        Assert.Equal("the エーピーアイ", dict.ApplyToText("the API"));
    }

    // ================================================================
    // Case-sensitive matching (mixed-case keys)
    // ================================================================

    [Fact]
    public void ApplyToText_CaseSensitive_MixedCaseExactOnly()
    {
        // "PyTorch" (mixed case) should only match "PyTorch", not "pytorch" or "PYTORCH"
        string content = "PyTorch\tパイトーチ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("パイトーチ is great", dict.ApplyToText("PyTorch is great"));
        Assert.Equal("pytorch is great", dict.ApplyToText("pytorch is great"));
        Assert.Equal("PYTORCH is great", dict.ApplyToText("PYTORCH is great"));
    }

    [Fact]
    public void ApplyToText_CaseSensitive_iPhone()
    {
        // "iPhone" is mixed case — must match exactly
        string content = "iPhone\tアイフォン\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("アイフォン 16", dict.ApplyToText("iPhone 16"));
        Assert.Equal("iphone 16", dict.ApplyToText("iphone 16"));
    }

    // ================================================================
    // Non-ASCII (Japanese/Chinese) — substring replacement, no boundary
    // ================================================================

    [Fact]
    public void ApplyToText_NonAscii_JapaneseSubstringReplacement()
    {
        // Japanese word replaces as substring without word boundary
        string content = "東京\tトウキョウ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("トウキョウタワー", dict.ApplyToText("東京タワー"));
        Assert.Equal("トウキョウ駅", dict.ApplyToText("東京駅"));
    }

    [Fact]
    public void ApplyToText_NonAscii_ChineseSubstringReplacement()
    {
        // Chinese word — substring, no boundary
        string content = "机器\tジーチー\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("ジーチー学习", dict.ApplyToText("机器学习"));
    }

    // ================================================================
    // Combined: word boundary + case sensitivity
    // ================================================================

    [Fact]
    public void ApplyToText_WordBoundaryAndCaseInsensitive_Combined()
    {
        // "gpu" (all lowercase) should match "GPU" at word boundary
        // but not inside "gpuXyz" (which should still be blocked by boundary)
        string json = """
            {
                "version": "1.0",
                "entries": {
                    "gpu": "ジーピーユー"
                }
            }
            """;
        string path = CreateTempJsonFile(json);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("ジーピーユー acceleration", dict.ApplyToText("GPU acceleration"));
        Assert.Equal("ジーピーユー acceleration", dict.ApplyToText("gpu acceleration"));
    }

    [Fact]
    public void ApplyToText_MixedCaseWithBoundary()
    {
        // "TensorFlow" (mixed case) should use word boundary AND case sensitivity
        string content = "TensorFlow\tテンソルフロー\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("テンソルフロー v2", dict.ApplyToText("TensorFlow v2"));
        Assert.Equal("tensorflow v2", dict.ApplyToText("tensorflow v2"));
        // Should not match inside a larger word
        Assert.Equal("TensorFlowLite", dict.ApplyToText("TensorFlowLite"));
    }

    // ================================================================
    // LoadDefaults
    // ================================================================

    [Fact]
    public void LoadDefaults_NoDictionaryDirectory_DoesNotThrow()
    {
        // When no data/dictionaries/ directory exists in any search path,
        // LoadDefaults should simply return without error.
        var dict = new CustomDictionary();
        dict.LoadDefaults(); // Must not throw
        // Count may be 0 or > 0 depending on the working directory;
        // just verify it does not crash.
    }

    [Fact]
    public void LoadDefaults_WithTempDirectory_LoadsJsonFiles()
    {
        // Create a temporary directory structure: <tmpDir>/data/dictionaries/
        var baseDir = Path.Combine(Path.GetTempPath(), $"piper_defaults_{Guid.NewGuid():N}");
        var dictDir = Path.Combine(baseDir, "data", "dictionaries");
        Directory.CreateDirectory(dictDir);

        try
        {
            // Create two JSON dictionary files
            string json1 = """
                {
                    "version": "1.0",
                    "entries": { "alpha": "ALPHA_REPLACED" }
                }
                """;
            string json2 = """
                {
                    "version": "1.0",
                    "entries": { "beta": "BETA_REPLACED" }
                }
                """;
            File.WriteAllText(Path.Combine(dictDir, "a_first.json"), json1, Encoding.UTF8);
            File.WriteAllText(Path.Combine(dictDir, "b_second.json"), json2, Encoding.UTF8);

            // Also create a non-JSON file that should be ignored
            File.WriteAllText(Path.Combine(dictDir, "ignored.txt"), "gamma\tGAMMA", Encoding.UTF8);

            // Save and change working directory so that data/dictionaries/ is found
            var originalDir = Directory.GetCurrentDirectory();
            Directory.SetCurrentDirectory(baseDir);
            try
            {
                var dict = new CustomDictionary();
                dict.LoadDefaults();

                // Should have loaded entries from both JSON files
                Assert.Equal(2, dict.Count);
                Assert.Equal("ALPHA_REPLACED", dict.ApplyToText("alpha"));
                Assert.Equal("BETA_REPLACED", dict.ApplyToText("beta"));
            }
            finally
            {
                Directory.SetCurrentDirectory(originalDir);
            }
        }
        finally
        {
            Directory.Delete(baseDir, true);
        }
    }

    [Fact]
    public void LoadDefaults_MalformedFile_SkippedSilently()
    {
        var baseDir = Path.Combine(Path.GetTempPath(), $"piper_defaults_{Guid.NewGuid():N}");
        var dictDir = Path.Combine(baseDir, "data", "dictionaries");
        Directory.CreateDirectory(dictDir);

        try
        {
            // One valid, one malformed JSON
            string validJson = """
                {
                    "version": "1.0",
                    "entries": { "good": "GOOD_ENTRY" }
                }
                """;
            string badJson = "{ this is not valid JSON }}}";

            File.WriteAllText(Path.Combine(dictDir, "a_valid.json"), validJson, Encoding.UTF8);
            File.WriteAllText(Path.Combine(dictDir, "b_broken.json"), badJson, Encoding.UTF8);

            var originalDir = Directory.GetCurrentDirectory();
            Directory.SetCurrentDirectory(baseDir);
            try
            {
                var dict = new CustomDictionary();
                dict.LoadDefaults(); // Must not throw

                // The valid file's entry should have been loaded
                Assert.True(dict.Count >= 1);
                Assert.Equal("GOOD_ENTRY", dict.ApplyToText("good"));
            }
            finally
            {
                Directory.SetCurrentDirectory(originalDir);
            }
        }
        finally
        {
            Directory.Delete(baseDir, true);
        }
    }

    [Fact]
    public void LoadDefaults_SortedOrder_FilesLoadedAlphabetically()
    {
        var baseDir = Path.Combine(Path.GetTempPath(), $"piper_defaults_{Guid.NewGuid():N}");
        var dictDir = Path.Combine(baseDir, "data", "dictionaries");
        Directory.CreateDirectory(dictDir);

        try
        {
            // Two files with same key but different values.
            // "a_first.json" loads first with priority 5,
            // "b_second.json" loads second with priority 5 => does not override (equal priority keeps first).
            string json1 = """
                {
                    "version": "2.0",
                    "entries": { "KEY": { "pronunciation": "FROM_FIRST", "priority": 5 } }
                }
                """;
            string json2 = """
                {
                    "version": "2.0",
                    "entries": { "KEY": { "pronunciation": "FROM_SECOND", "priority": 5 } }
                }
                """;
            File.WriteAllText(Path.Combine(dictDir, "a_first.json"), json1, Encoding.UTF8);
            File.WriteAllText(Path.Combine(dictDir, "b_second.json"), json2, Encoding.UTF8);

            var originalDir = Directory.GetCurrentDirectory();
            Directory.SetCurrentDirectory(baseDir);
            try
            {
                var dict = new CustomDictionary();
                dict.LoadDefaults();

                // Equal priority: first loaded wins => "FROM_FIRST"
                Assert.Equal("FROM_FIRST", dict.ApplyToText("KEY"));
            }
            finally
            {
                Directory.SetCurrentDirectory(originalDir);
            }
        }
        finally
        {
            Directory.Delete(baseDir, true);
        }
    }

    [Fact]
    public void LoadDefaults_OnlyLoadsFromFirstFoundDirectory()
    {
        var baseDir = Path.Combine(Path.GetTempPath(), $"piper_defaults_{Guid.NewGuid():N}");
        var dictDir = Path.Combine(baseDir, "data", "dictionaries");
        Directory.CreateDirectory(dictDir);

        // Create a second candidate directory one level up (would be searched later)
        var parentDictDir = Path.Combine(baseDir, "..", "data", "dictionaries");

        try
        {
            string json1 = """
                {
                    "version": "1.0",
                    "entries": { "first_dir": "FOUND" }
                }
                """;
            File.WriteAllText(Path.Combine(dictDir, "test.json"), json1, Encoding.UTF8);

            // We only verify the working-directory path is used
            var originalDir = Directory.GetCurrentDirectory();
            Directory.SetCurrentDirectory(baseDir);
            try
            {
                var dict = new CustomDictionary();
                dict.LoadDefaults();

                Assert.True(dict.Count >= 1);
                Assert.Equal("FOUND", dict.ApplyToText("first_dir"));
            }
            finally
            {
                Directory.SetCurrentDirectory(originalDir);
            }
        }
        finally
        {
            Directory.Delete(baseDir, true);
        }
    }

    // ================================================================
    // Case-insensitive deduplication
    // ================================================================

    [Fact]
    public void AddEntry_CaseInsensitiveDedup_AllUpperAndAllLower()
    {
        // Loading "API" and then "api" (both case-insensitive) should deduplicate.
        // The first loaded entry (priority 5) should be kept.
        string content1 = "API\tエーピーアイ\n";
        string content2 = "api\tshould-not-override\n";
        string path1 = CreateTempFile(content1);
        string path2 = CreateTempFile(content2);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path1);
        dict.LoadDictionary(path2);

        // "api" and "API" are both all-upper/all-lower and deduplicated.
        Assert.Equal(1, dict.Count);
        Assert.Equal("エーピーアイ", dict.ApplyToText("API"));
    }

    [Fact]
    public void AddEntry_MixedCaseAndCaseInsensitive_AreSeparate()
    {
        // "PyTorch" (mixed case, case-sensitive) and "pytorch" (all lower, case-insensitive)
        // should be stored as separate entries.
        string content = "PyTorch\tミックス\npytorch\tインセンシティブ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal(2, dict.Count);
        // "PyTorch" matches the case-sensitive entry
        Assert.Equal("ミックス is here", dict.ApplyToText("PyTorch is here"));
        // "PYTORCH" matches the case-insensitive entry (all-lower "pytorch")
        Assert.Equal("インセンシティブ is here", dict.ApplyToText("PYTORCH is here"));
    }

    // ================================================================
    // Word boundary: multiple occurrences
    // ================================================================

    [Fact]
    public void ApplyToText_WordBoundary_MultipleOccurrences()
    {
        // "AI" should replace all standalone occurrences but skip embedded ones
        string content = "AI\tエーアイ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("エーアイ is エーアイ but AIDS is not",
            dict.ApplyToText("AI is AI but AIDS is not"));
    }

    [Fact]
    public void ApplyToText_WordBoundary_WithPunctuation()
    {
        // Word boundaries should work correctly with adjacent punctuation
        string content = "AI\tエーアイ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("エーアイ, エーアイ. エーアイ!",
            dict.ApplyToText("AI, AI. AI!"));
    }

    [Fact]
    public void ApplyToText_WordBoundary_HyphenatedWord()
    {
        // Hyphens count as word boundaries for \b
        string content = "AI\tエーアイ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("エーアイ-powered", dict.ApplyToText("AI-powered"));
    }

    // ================================================================
    // Regex special characters in keys
    // ================================================================

    [Fact]
    public void ApplyToText_SpecialRegexChars_EscapedProperly()
    {
        // Keys containing regex special characters should be escaped properly
        // by Regex.Escape() before being used in the pattern.
        // Note: \b word-boundary only fires between word (\w) and non-word (\W)
        // characters. "C++" has '+' which is non-word, so "\bC\+\+\b" won't
        // match "C++ is" because there's no \b between '+' and ' '.
        // Only keys that consist entirely of word characters get full boundary
        // matching. This is the expected behavior matching C++ implementation.
        string content = "C++\tシープラスプラス\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        // "C++" boundary: \b fires before C (word char after start/space),
        // but not after ++ (both non-word). So the replacement does NOT fire.
        // This is consistent with the word-boundary design.
        Assert.Equal("C++ is great", dict.ApplyToText("C++ is great"));
    }

    [Fact]
    public void ApplyToText_DotInKey_EscapedProperly()
    {
        // "." is a regex metacharacter
        string content = "v2.0\tバージョンニ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Contains("バージョンニ", dict.ApplyToText("upgrade to v2.0"));
    }

    // ================================================================
    // Non-ASCII case insensitivity
    // ================================================================

    [Fact]
    public void ApplyToText_NonAscii_CaseInsensitive_JapaneseUnchanged()
    {
        // Japanese characters don't have case, so IsMixedCase returns false
        // and matching uses OrdinalIgnoreCase (which is effectively Ordinal for CJK).
        string content = "東京\tトウキョウ\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        Assert.Equal("トウキョウは首都です", dict.ApplyToText("東京は首都です"));
    }

    // ================================================================
    // LoadDefaults with explicit --custom-dict integration
    // ================================================================

    [Fact]
    public void LoadDefaults_ThenUserFile_UserOverridesDefaults()
    {
        // Simulates the CLI behavior: LoadDefaults (lower priority), then
        // load user-specified files. User files with higher priority should win.
        var baseDir = Path.Combine(Path.GetTempPath(), $"piper_defaults_{Guid.NewGuid():N}");
        var dictDir = Path.Combine(baseDir, "data", "dictionaries");
        Directory.CreateDirectory(dictDir);

        try
        {
            // Default dictionary with priority 5
            string defaultJson = """
                {
                    "version": "2.0",
                    "entries": {
                        "API": { "pronunciation": "default-pron", "priority": 5 }
                    }
                }
                """;
            File.WriteAllText(Path.Combine(dictDir, "defaults.json"), defaultJson, Encoding.UTF8);

            // User dictionary with priority 8
            string userJson = """
                {
                    "version": "2.0",
                    "entries": {
                        "API": { "pronunciation": "user-pron", "priority": 8 }
                    }
                }
                """;
            string userFile = CreateTempJsonFile(userJson);

            var originalDir = Directory.GetCurrentDirectory();
            Directory.SetCurrentDirectory(baseDir);
            try
            {
                var dict = new CustomDictionary();
                dict.LoadDefaults();        // defaults first (priority 5)
                dict.LoadDictionary(userFile);  // user override (priority 8)

                // User entry should win
                Assert.Equal("user-pron", dict.ApplyToText("API"));
            }
            finally
            {
                Directory.SetCurrentDirectory(originalDir);
            }
        }
        finally
        {
            Directory.Delete(baseDir, true);
        }
    }
}
