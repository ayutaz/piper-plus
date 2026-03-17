using System.Text;
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
        // "abc" should match before "ab" and "a"
        string content = "a\t1\nab\t2\nabc\t3\n";
        string path = CreateTempFile(content);

        var dict = new CustomDictionary();
        dict.LoadDictionary(path);

        // "abc" is replaced first (longest), leaving "d" untouched
        Assert.Equal("3d", dict.ApplyToText("abcd"));
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
}
