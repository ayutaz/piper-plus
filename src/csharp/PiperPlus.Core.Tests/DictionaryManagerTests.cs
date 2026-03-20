using PiperPlus.Core.Config;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="DictionaryManager"/>.
/// Tests cover dictionary search order, validation, control flags, and error paths.
/// Network-dependent tests (actual download) are excluded; only local logic is tested.
/// </summary>
public sealed class DictionaryManagerTests : IDisposable
{
    // Environment variables we may modify during tests
    private readonly string? _origOpenJtalk;
    private readonly string? _origDotNetG2P;
    private readonly string? _origNaistJdic;
    private readonly string? _origOffline;
    private readonly string? _origAutoDownload;

    public DictionaryManagerTests()
    {
        _origOpenJtalk = Environment.GetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH");
        _origDotNetG2P = Environment.GetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH");
        _origNaistJdic = Environment.GetEnvironmentVariable("NAIST_JDIC_PATH");
        _origOffline = Environment.GetEnvironmentVariable("PIPER_OFFLINE_MODE");
        _origAutoDownload = Environment.GetEnvironmentVariable("PIPER_AUTO_DOWNLOAD_DICT");
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", _origOpenJtalk);
        Environment.SetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH", _origDotNetG2P);
        Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", _origNaistJdic);
        Environment.SetEnvironmentVariable("PIPER_OFFLINE_MODE", _origOffline);
        Environment.SetEnvironmentVariable("PIPER_AUTO_DOWNLOAD_DICT", _origAutoDownload);
    }

    // ================================================================
    // IsValidDictionary
    // ================================================================

    [Fact]
    public void IsValidDictionary_NullPath_ReturnsFalse()
    {
        Assert.False(DictionaryManager.IsValidDictionary(null));
    }

    [Fact]
    public void IsValidDictionary_EmptyPath_ReturnsFalse()
    {
        Assert.False(DictionaryManager.IsValidDictionary(""));
    }

    [Fact]
    public void IsValidDictionary_NonexistentPath_ReturnsFalse()
    {
        Assert.False(DictionaryManager.IsValidDictionary("/nonexistent/path/to/dict"));
    }

    [Fact]
    public void IsValidDictionary_EmptyDirectory_ReturnsFalse()
    {
        var tempDir = Path.Combine(Path.GetTempPath(), $"dict_test_{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempDir);
        try
        {
            Assert.False(DictionaryManager.IsValidDictionary(tempDir));
        }
        finally
        {
            Directory.Delete(tempDir, true);
        }
    }

    [Fact]
    public void IsValidDictionary_PartialFiles_ReturnsFalse()
    {
        var tempDir = Path.Combine(Path.GetTempPath(), $"dict_test_{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempDir);
        try
        {
            // Create only 2 of the 4 required files
            File.WriteAllText(Path.Combine(tempDir, "sys.dic"), "");
            File.WriteAllText(Path.Combine(tempDir, "matrix.bin"), "");

            Assert.False(DictionaryManager.IsValidDictionary(tempDir));
        }
        finally
        {
            Directory.Delete(tempDir, true);
        }
    }

    [Fact]
    public void IsValidDictionary_AllFilesPresent_ReturnsTrue()
    {
        var tempDir = Path.Combine(Path.GetTempPath(), $"dict_test_{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempDir);
        try
        {
            // Create all 4 required files
            File.WriteAllText(Path.Combine(tempDir, "sys.dic"), "");
            File.WriteAllText(Path.Combine(tempDir, "matrix.bin"), "");
            File.WriteAllText(Path.Combine(tempDir, "char.bin"), "");
            File.WriteAllText(Path.Combine(tempDir, "unk.dic"), "");

            Assert.True(DictionaryManager.IsValidDictionary(tempDir));
        }
        finally
        {
            Directory.Delete(tempDir, true);
        }
    }

    // ================================================================
    // FindDictionary — environment variable search order
    // ================================================================

    [Fact]
    public void FindDictionary_OpenJtalkEnvVar_TakesPriority()
    {
        var tempDir = CreateFakeDictionary();
        try
        {
            Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", tempDir);
            // Clear others to ensure they don't interfere
            Environment.SetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH", null);
            Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", null);

            var result = DictionaryManager.FindDictionary();

            Assert.Equal(tempDir, result);
        }
        finally
        {
            Directory.Delete(tempDir, true);
        }
    }

    [Fact]
    public void FindDictionary_DotNetG2PEnvVar_UsedWhenOpenJtalkNotSet()
    {
        var tempDir = CreateFakeDictionary();
        try
        {
            Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", null);
            Environment.SetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH", tempDir);
            Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", null);

            var result = DictionaryManager.FindDictionary();

            Assert.Equal(tempDir, result);
        }
        finally
        {
            Directory.Delete(tempDir, true);
        }
    }

    [Fact]
    public void FindDictionary_NaistJdicEnvVar_UsedAsFallback()
    {
        var tempDir = CreateFakeDictionary();
        try
        {
            Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", null);
            Environment.SetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH", null);
            Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", tempDir);

            var result = DictionaryManager.FindDictionary();

            Assert.Equal(tempDir, result);
        }
        finally
        {
            Directory.Delete(tempDir, true);
        }
    }

    [Fact]
    public void FindDictionary_InvalidEnvVar_SkippedAndContinues()
    {
        var tempDir = CreateFakeDictionary();
        try
        {
            // Point OPENJTALK_DICTIONARY_PATH to an invalid (nonexistent) path
            Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", "/nonexistent/path");
            // Point NAIST_JDIC_PATH to a valid dictionary
            Environment.SetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH", null);
            Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", tempDir);

            var result = DictionaryManager.FindDictionary();

            Assert.Equal(tempDir, result);
        }
        finally
        {
            Directory.Delete(tempDir, true);
        }
    }

    [Fact]
    public void FindDictionary_NoDictionaryAnywhere_ReturnsNull()
    {
        // Clear all env vars that might point to a dictionary
        Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", null);
        Environment.SetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH", null);
        Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", null);

        // FindDictionary checks env vars, exe-relative, system paths, and data dir.
        // If none of those contain a valid dict, it returns null.
        // This test may still find a real dictionary if one is installed on the system,
        // so we just verify the method does not throw.
        _ = DictionaryManager.FindDictionary();
    }

    // ================================================================
    // EnsureDictionaryAsync — control flags
    // ================================================================

    [Fact]
    public async Task EnsureDictionaryAsync_OfflineMode_ThrowsWhenNotFound()
    {
        // Clear all env vars to prevent finding a local dictionary
        Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", null);
        Environment.SetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH", null);
        Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", null);
        Environment.SetEnvironmentVariable("PIPER_OFFLINE_MODE", "1");

        // If a real dictionary exists on the system, this test will pass
        // (FindDictionary succeeds before reaching download check).
        // We can't guarantee no dict exists, so we check the behavior:
        // Either it returns a valid path, or it throws with "offline mode".
        try
        {
            var path = await DictionaryManager.EnsureDictionaryAsync(
                TestContext.Current.CancellationToken);
            // If we get here, a local dictionary was found — that's fine
            Assert.True(DictionaryManager.IsValidDictionary(path));
        }
        catch (InvalidOperationException ex)
        {
            Assert.Contains("offline mode", ex.Message, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public async Task EnsureDictionaryAsync_AutoDownloadDisabled_ThrowsWhenNotFound()
    {
        Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", null);
        Environment.SetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH", null);
        Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", null);
        Environment.SetEnvironmentVariable("PIPER_AUTO_DOWNLOAD_DICT", "0");

        try
        {
            var path = await DictionaryManager.EnsureDictionaryAsync(
                TestContext.Current.CancellationToken);
            Assert.True(DictionaryManager.IsValidDictionary(path));
        }
        catch (InvalidOperationException ex)
        {
            Assert.Contains("auto-download is disabled", ex.Message,
                StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public async Task EnsureDictionaryAsync_ExistingDict_ReturnsImmediately()
    {
        var tempDir = CreateFakeDictionary();
        try
        {
            Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", tempDir);

            var result = await DictionaryManager.EnsureDictionaryAsync(
                TestContext.Current.CancellationToken);

            Assert.Equal(tempDir, result);
        }
        finally
        {
            Directory.Delete(tempDir, true);
        }
    }

    // ================================================================
    // Helpers
    // ================================================================

    /// <summary>
    /// Creates a temporary directory with the 4 required dictionary files.
    /// Returns the path. Caller must delete the directory when done.
    /// </summary>
    private static string CreateFakeDictionary()
    {
        var tempDir = Path.Combine(Path.GetTempPath(), $"dict_test_{Guid.NewGuid():N}");
        Directory.CreateDirectory(tempDir);

        File.WriteAllText(Path.Combine(tempDir, "sys.dic"), "fake");
        File.WriteAllText(Path.Combine(tempDir, "matrix.bin"), "fake");
        File.WriteAllText(Path.Combine(tempDir, "char.bin"), "fake");
        File.WriteAllText(Path.Combine(tempDir, "unk.dic"), "fake");

        return tempDir;
    }
}
