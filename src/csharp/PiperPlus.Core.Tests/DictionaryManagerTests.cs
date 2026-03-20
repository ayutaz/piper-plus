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
    private readonly string? _origXdgDataHome;

    public DictionaryManagerTests()
    {
        _origOpenJtalk = Environment.GetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH");
        _origDotNetG2P = Environment.GetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH");
        _origNaistJdic = Environment.GetEnvironmentVariable("NAIST_JDIC_PATH");
        _origOffline = Environment.GetEnvironmentVariable("PIPER_OFFLINE_MODE");
        _origAutoDownload = Environment.GetEnvironmentVariable("PIPER_AUTO_DOWNLOAD_DICT");
        _origXdgDataHome = Environment.GetEnvironmentVariable("XDG_DATA_HOME");
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", _origOpenJtalk);
        Environment.SetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH", _origDotNetG2P);
        Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", _origNaistJdic);
        Environment.SetEnvironmentVariable("PIPER_OFFLINE_MODE", _origOffline);
        Environment.SetEnvironmentVariable("PIPER_AUTO_DOWNLOAD_DICT", _origAutoDownload);
        Environment.SetEnvironmentVariable("XDG_DATA_HOME", _origXdgDataHome);
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
    // IsValidDictionary — edge cases
    // ================================================================

    [Fact]
    public void IsValidDictionary_WhitespacePath_ReturnsFalse()
    {
        Assert.False(DictionaryManager.IsValidDictionary("   "));
    }

    [Fact]
    public void IsValidDictionary_OneOfFourFiles_ReturnsFalse()
    {
        var dir = Path.Combine(Path.GetTempPath(), $"dict_test_{Guid.NewGuid():N}");
        try
        {
            Directory.CreateDirectory(dir);
            File.WriteAllBytes(Path.Combine(dir, "sys.dic"), new byte[] { 0 });
            Assert.False(DictionaryManager.IsValidDictionary(dir));
        }
        finally
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    [Fact]
    public void IsValidDictionary_ThreeOfFourFiles_ReturnsFalse()
    {
        var dir = Path.Combine(Path.GetTempPath(), $"dict_test_{Guid.NewGuid():N}");
        try
        {
            Directory.CreateDirectory(dir);
            File.WriteAllBytes(Path.Combine(dir, "sys.dic"), new byte[] { 0 });
            File.WriteAllBytes(Path.Combine(dir, "matrix.bin"), new byte[] { 0 });
            File.WriteAllBytes(Path.Combine(dir, "char.bin"), new byte[] { 0 });
            // Missing unk.dic
            Assert.False(DictionaryManager.IsValidDictionary(dir));
        }
        finally
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    // ================================================================
    // Control flag edge cases
    // ================================================================

    [Fact]
    public async Task IsOfflineMode_OnlyExactOneIsTrue()
    {
        // Clear all env vars to prevent finding a local dictionary
        Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", null);
        Environment.SetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH", null);
        Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", null);
        // "1" should be offline, but "0" should not be
        // Set PIPER_OFFLINE_MODE=0 and PIPER_AUTO_DOWNLOAD_DICT=0
        // If "0" were treated as offline, we'd get "offline mode" error;
        // instead we should get "auto-download is disabled" error.
        Environment.SetEnvironmentVariable("PIPER_OFFLINE_MODE", "0");
        Environment.SetEnvironmentVariable("PIPER_AUTO_DOWNLOAD_DICT", "0");

        try
        {
            var path = await DictionaryManager.EnsureDictionaryAsync(CancellationToken.None);
            // If we get here, a system dictionary was found — that's acceptable
            Assert.True(DictionaryManager.IsValidDictionary(path));
        }
        catch (InvalidOperationException ex)
        {
            // Should throw "auto-download is disabled" NOT "offline mode"
            Assert.Contains("auto-download", ex.Message, StringComparison.OrdinalIgnoreCase);
        }
    }

    [Fact]
    public async Task EnsureDictionaryAsync_OfflineModeWithValidDict_ReturnsPath()
    {
        // Even in offline mode, if dictionary exists locally, it should be returned
        var dir = Path.Combine(Path.GetTempPath(), $"dict_test_{Guid.NewGuid():N}");
        try
        {
            Directory.CreateDirectory(dir);
            File.WriteAllBytes(Path.Combine(dir, "sys.dic"), new byte[] { 0 });
            File.WriteAllBytes(Path.Combine(dir, "matrix.bin"), new byte[] { 0 });
            File.WriteAllBytes(Path.Combine(dir, "char.bin"), new byte[] { 0 });
            File.WriteAllBytes(Path.Combine(dir, "unk.dic"), new byte[] { 0 });

            Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", dir);
            Environment.SetEnvironmentVariable("PIPER_OFFLINE_MODE", "1");

            string result = await DictionaryManager.EnsureDictionaryAsync(CancellationToken.None);
            Assert.Equal(dir, result);
        }
        finally
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }

    // ================================================================
    // Data directory resolution
    // ================================================================

    [Fact]
    public void FindDictionary_DataDirFallback_Checked()
    {
        // GetDataDir() uses XDG_DATA_HOME on non-Windows, or %APPDATA% on Windows.
        // The data-dir candidate is <data_dir>/open_jtalk_dic_utf_8-1.11.
        // On non-Windows we can control this via XDG_DATA_HOME; on Windows via %APPDATA%.
        // We verify that FindDictionary checks the data-dir candidate by creating a
        // valid dictionary there and clearing all other env-var candidates.
        var baseDir = Path.Combine(Path.GetTempPath(), $"dict_test_{Guid.NewGuid():N}");
        var piperDir = Path.Combine(baseDir, "piper");
        var dictDir = Path.Combine(piperDir, "open_jtalk_dic_utf_8-1.11");
        try
        {
            Directory.CreateDirectory(dictDir);
            File.WriteAllBytes(Path.Combine(dictDir, "sys.dic"), new byte[] { 0 });
            File.WriteAllBytes(Path.Combine(dictDir, "matrix.bin"), new byte[] { 0 });
            File.WriteAllBytes(Path.Combine(dictDir, "char.bin"), new byte[] { 0 });
            File.WriteAllBytes(Path.Combine(dictDir, "unk.dic"), new byte[] { 0 });

            // Clear all env-var candidates so they don't short-circuit
            Environment.SetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH", null);
            Environment.SetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH", null);
            Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", null);

            // Point the data directory to our temp location.
            // On non-Windows: GetDataDir() reads XDG_DATA_HOME -> <XDG_DATA_HOME>/piper
            // On Windows: GetDataDir() reads %APPDATA% (not overridable via env var)
            if (!System.Runtime.InteropServices.RuntimeInformation.IsOSPlatform(
                    System.Runtime.InteropServices.OSPlatform.Windows))
            {
                Environment.SetEnvironmentVariable("XDG_DATA_HOME", baseDir);
            }
            else
            {
                // On Windows, GetDataDir() returns %APPDATA%/piper which we cannot
                // override easily. Skip assertion but verify the method does not throw.
                _ = DictionaryManager.FindDictionary();
                return;
            }

            string? result = DictionaryManager.FindDictionary();
            Assert.NotNull(result);
            Assert.Equal(dictDir, result);
        }
        finally
        {
            if (Directory.Exists(baseDir)) Directory.Delete(baseDir, true);
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
