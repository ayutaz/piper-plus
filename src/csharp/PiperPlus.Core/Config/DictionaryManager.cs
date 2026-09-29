using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Security.Cryptography;

namespace PiperPlus.Core.Config;

/// <summary>
/// Manages automatic discovery and downloading of the OpenJTalk naist-jdic dictionary.
/// Port of the C++ <c>openjtalk_dictionary_manager.c</c> to idiomatic C#.
/// </summary>
/// <remarks>
/// <para>Search order:</para>
/// <list type="number">
///   <item>Environment variable <c>OPENJTALK_DICTIONARY_PATH</c></item>
///   <item>Environment variables <c>DOTNETG2P_NAIST_JDIC_PATH</c> and <c>NAIST_JDIC_PATH</c></item>
///   <item>Executable-relative: <c>&lt;exe_dir&gt;/../share/open_jtalk/dic</c></item>
///   <item>System paths (OS-specific)</item>
///   <item>Data directory: <c>&lt;data_dir&gt;/open_jtalk_dic_utf_8-1.11</c></item>
/// </list>
/// <para>Control flags:</para>
/// <list type="bullet">
///   <item><c>PIPER_PLUS_OFFLINE_MODE=1</c> disables all network access</item>
///   <item><c>PIPER_PLUS_AUTO_DOWNLOAD_DICT=0</c> disables dictionary auto-download</item>
/// </list>
/// </remarks>
public static class DictionaryManager
{
    // ---------------------------------------------------------------
    // Constants (matching C++ openjtalk_dictionary_manager.c)
    // ---------------------------------------------------------------
    private const string DictionaryUrl =
        "https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz";

    private const string DictionaryDirName = "open_jtalk_dic_utf_8-1.11";

    private const string DictionarySha256 =
        "fe6ba0e43542cef98339abdffd903e062008ea170b04e7e2a35da805902f382a";

    private static readonly string[] RequiredFiles =
    {
        "sys.dic",
        "matrix.bin",
        "char.bin",
        "unk.dic",
    };

    private static readonly HttpClient S_httpClient = CreateHttpClient();

    // Serializes concurrent EnsureDictionaryAsync calls so that parallel callers
    // do not race on the download/extract path (which would corrupt sys.dic and
    // other files due to overlapping FileStream writes). Process-lifetime,
    // intentionally not disposed (Microsoft-recommended pattern for static
    // SemaphoreSlim fields).
    private static readonly SemaphoreSlim S_dictDownloadLock = new SemaphoreSlim(1, 1);

    private static HttpClient CreateHttpClient()
    {
        var client = new HttpClient
        {
            Timeout = TimeSpan.FromMinutes(10),
        };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("PiperPlus/1.0");
        return client;
    }

    // ---------------------------------------------------------------
    // Public API
    // ---------------------------------------------------------------

    /// <summary>
    /// Searches the standard locations for an existing dictionary without downloading.
    /// Returns the path to the dictionary directory, or <c>null</c> if not found.
    /// </summary>
    /// <returns></returns>
    public static string? FindDictionary()
    {
        foreach (var candidate in EnumerateCandidates())
        {
            if (IsValidDictionary(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    /// <summary>
    /// Ensures a dictionary is available: searches standard locations, and downloads
    /// from GitHub if not found (unless offline mode or auto-download is disabled).
    /// </summary>
    /// <param name="ct">Cancellation token for the download operation.</param>
    /// <returns>The path to the validated dictionary directory.</returns>
    /// <exception cref="InvalidOperationException">
    /// When no dictionary is found and downloading is not possible (offline mode,
    /// auto-download disabled, or download failure).
    /// </exception>
    public static async Task<string> EnsureDictionaryAsync(CancellationToken ct = default)
    {
        // 1. Lock-free fast path: if a dictionary is already present, return
        //    immediately without acquiring the download lock. This keeps the
        //    common "dict already exists" path contention-free for parallel
        //    callers (e.g. SentenceParallelEncoder spawning N tasks).
        var existing = FindDictionary();
        if (existing is not null)
        {
            return existing;
        }

        // 2. Serialize the slow path (download + extract). Multiple concurrent
        //    callers must not race on the same archive/file writes — that was
        //    the root cause of sys.dic corruption under 32-way parallel tests.
        await S_dictDownloadLock.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            // 2a. Double-checked lookup inside the lock: another caller may
            //     have completed the download while we were waiting.
            existing = FindDictionary();
            if (existing is not null)
            {
                return existing;
            }

            // 2b. Check control flags
            if (IsOfflineMode())
            {
                throw new InvalidOperationException(
                    "OpenJTalk dictionary not found and offline mode is enabled (PIPER_PLUS_OFFLINE_MODE=1). " +
                    "Please download the dictionary manually or set OPENJTALK_DICTIONARY_PATH.");
            }

            if (IsAutoDownloadDisabled())
            {
                throw new InvalidOperationException(
                    "OpenJTalk dictionary not found and auto-download is disabled (PIPER_PLUS_AUTO_DOWNLOAD_DICT=0). " +
                    "Please download the dictionary manually or set OPENJTALK_DICTIONARY_PATH.");
            }

            // 2c. Download to the data directory
            var dataDir = GetDataDir();
            var dictPath = Path.Join(dataDir, DictionaryDirName);

            await DownloadAndExtractAsync(dataDir, ct).ConfigureAwait(false);

            if (!IsValidDictionary(dictPath))
            {
                throw new InvalidOperationException(
                    $"Dictionary download completed but validation failed. " +
                    $"Expected directory with {string.Join(", ", RequiredFiles)} at: {dictPath}");
            }

            return dictPath;
        }
        finally
        {
            S_dictDownloadLock.Release();
        }
    }

    /// <summary>
    /// Validates that the given directory contains the 4 required dictionary files.
    /// </summary>
    /// <returns></returns>
    public static bool IsValidDictionary(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Directory.Exists(path))
        {
            return false;
        }

        for (int i = 0; i < RequiredFiles.Length; i++)
        {
            if (!File.Exists(Path.Join(path, RequiredFiles[i])))
            {
                return false;
            }
        }

        return true;
    }

    // ---------------------------------------------------------------
    // Candidate enumeration (search order matching C++ implementation)
    // ---------------------------------------------------------------
    private static IEnumerable<string> EnumerateCandidates()
    {
        // 1. OPENJTALK_DICTIONARY_PATH
        var env = Environment.GetEnvironmentVariable("OPENJTALK_DICTIONARY_PATH");
        if (!string.IsNullOrWhiteSpace(env))
        {
            yield return env;
        }

        // 2. DotNetG2P compatibility env vars
        env = Environment.GetEnvironmentVariable("DOTNETG2P_NAIST_JDIC_PATH");
        if (!string.IsNullOrWhiteSpace(env))
        {
            yield return env;
        }

        env = Environment.GetEnvironmentVariable("NAIST_JDIC_PATH");
        if (!string.IsNullOrWhiteSpace(env))
        {
            yield return env;
        }

        // 3. Executable-relative: <exe_dir>/../share/open_jtalk/dic
        var exeRelative = GetExeRelativeDictPath();
        if (exeRelative is not null)
        {
            yield return exeRelative;
        }

        // 4. System paths (OS-specific)
        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            yield return @"C:\Program Files\open_jtalk\dic";
            yield return @"C:\Program Files (x86)\open_jtalk\dic";
        }
        else
        {
            yield return "/usr/share/open_jtalk/dic";
            yield return "/usr/local/share/open_jtalk/dic";
        }

        // 5. Data directory: <data_dir>/open_jtalk_dic_utf_8-1.11
        yield return Path.Join(GetDataDir(), DictionaryDirName);
    }

    private static string? GetExeRelativeDictPath()
    {
        try
        {
            var exePath = Environment.ProcessPath;
            if (string.IsNullOrEmpty(exePath))
            {
                return null;
            }

            var exeDir = Path.GetDirectoryName(exePath);
            if (string.IsNullOrEmpty(exeDir))
            {
                return null;
            }

            var dictPath = Path.GetFullPath(
                Path.Join(exeDir, "..", "share", "open_jtalk", "dic"));
            return Directory.Exists(dictPath) ? dictPath : null;
        }
        catch
        {
            return null;
        }
    }

    // ---------------------------------------------------------------
    // Data directory (matching C++ get_data_dir)
    // ---------------------------------------------------------------
    private static string GetDataDir()
    {
        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            var appData = Environment.GetFolderPath(
                Environment.SpecialFolder.ApplicationData);
            return !string.IsNullOrEmpty(appData)
                ? Path.Join(appData, "piper-plus")
                : Path.Join(Environment.CurrentDirectory, "data");
        }

        // Unix: XDG_DATA_HOME or ~/.local/share/piper-plus
        var xdgData = Environment.GetEnvironmentVariable("XDG_DATA_HOME");
        if (!string.IsNullOrEmpty(xdgData))
        {
            return Path.Join(xdgData, "piper-plus");
        }

        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        return !string.IsNullOrEmpty(home)
            ? Path.Join(home, ".local", "share", "piper-plus")
            : Path.Join(Environment.CurrentDirectory, "data");
    }

    // ---------------------------------------------------------------
    // Control flags
    // ---------------------------------------------------------------
    private static bool IsOfflineMode()
    {
        var value = Environment.GetEnvironmentVariable("PIPER_PLUS_OFFLINE_MODE");
        return string.Equals(value, "1", StringComparison.Ordinal);
    }

    private static bool IsAutoDownloadDisabled()
    {
        var value = Environment.GetEnvironmentVariable("PIPER_PLUS_AUTO_DOWNLOAD_DICT");
        return string.Equals(value, "0", StringComparison.Ordinal);
    }

    // ---------------------------------------------------------------
    // Download, verify, and extract
    // ---------------------------------------------------------------
    private static async Task DownloadAndExtractAsync(
        string dataDir, CancellationToken ct)
    {
        Directory.CreateDirectory(dataDir);

        // Everything happens in a PER-PROCESS staging directory, and the
        // finished dictionary is moved into place in one step.
        //
        // S_dictDownloadLock is a SemaphoreSlim, so it serialises callers
        // within one process only. Three things here were shared across
        // processes and raced:
        //
        //   1. the archive's ".tmp" (opened FileMode.Create + FileShare.None,
        //      so the second process simply failed),
        //   2. the archive itself (one process could File.Move onto it while
        //      another was computing its SHA256),
        //   3. the extraction target -- ExtractTarGzAsync wrote straight into
        //      dataDir, so FindDictionary() in another process could see the
        //      dictionary directory HALF POPULATED and hand it to
        //      MeCabTokenizer.
        //
        // Measured (PR #728 CI, `build-and-test (ubuntu-24.04)`):
        //   System.IO.IOException: The process cannot access the file
        //   '.../open_jtalk_dic_utf_8-1.11/sys.dic' because it is being used
        //   by another process.
        //     at DotNetG2P.MeCab.Dictionary.SystemDictionary.Load
        //     at PiperPlus.Cli.DotNetG2PEngine..ctor
        // `dotnet test <sln>` runs PiperPlus.Cli.Tests and
        // PiperPlus.Core.Tests in parallel, and the latter's
        // CliIntegrationTests spawns `dotnet PiperPlus.Cli.dll` -- two OS
        // processes sharing ~/.local/share/piper-plus. Issue #735 is the same
        // race landing on the other side of it (FileNotFoundException for a
        // file the winner had not extracted yet).
        //
        // A named Mutex is not used: its cross-process semantics on Unix
        // differ from Windows, and the atomic move makes correctness
        // independent of it. Two processes may both download -- wasteful but
        // correct, and the loser's staging directory is discarded.
        var stagingDir = BuildStagingDirPath(dataDir);
        Directory.CreateDirectory(stagingDir);

        var finalDictPath = Path.Join(dataDir, DictionaryDirName);
        var archivePath = Path.Join(stagingDir, "open_jtalk_dic_utf_8-1.11.tar.gz");
        var tempPath = archivePath + ".tmp";

        try
        {
            // Download
            Console.Error.WriteLine(
                $"Downloading OpenJTalk dictionary from {DictionaryUrl} ...");

            using (HttpResponseMessage response = await S_httpClient
                .GetAsync(DictionaryUrl, HttpCompletionOption.ResponseHeadersRead, ct)
                .ConfigureAwait(false))
            {
                response.EnsureSuccessStatusCode();

                var totalBytes = response.Content.Headers.ContentLength;

                await using Stream contentStream = await response.Content
                    .ReadAsStreamAsync(ct)
                    .ConfigureAwait(false);
                await using var fileStream = new FileStream(
                    tempPath, FileMode.Create, FileAccess.Write,
                    FileShare.None, bufferSize: 81920, useAsync: true);

                await CopyWithProgressAsync(
                    contentStream, fileStream, totalBytes, ct).ConfigureAwait(false);
            }

            // Rename .tmp -> final
            File.Move(tempPath, archivePath, overwrite: true);

            Console.Error.WriteLine("Download complete.");

            // Verify SHA256
            Console.Error.WriteLine("Verifying checksum ...");
            var actualHash = await ComputeSha256Async(archivePath, ct).ConfigureAwait(false);

            if (!string.Equals(actualHash, DictionarySha256, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException(
                    $"SHA256 mismatch: expected {DictionarySha256}, got {actualHash}. " +
                    "The downloaded archive may be corrupted.");
            }

            Console.Error.WriteLine("Checksum verified.");

            // Extract tar.gz into the staging directory, never into dataDir.
            Console.Error.WriteLine("Extracting dictionary ...");
            await ExtractTarGzAsync(archivePath, stagingDir, ct).ConfigureAwait(false);

            // Publish in one step. Directory.Move within a filesystem is a
            // rename, so another process sees either no dictionary or a
            // complete one -- never a partially extracted directory.
            var stagedDictPath = Path.Join(stagingDir, DictionaryDirName);
            if (!IsValidDictionary(stagedDictPath))
            {
                throw new InvalidOperationException(
                    $"Extraction completed but the staged dictionary is incomplete. " +
                    $"Expected {string.Join(", ", RequiredFiles)} at: {stagedDictPath}");
            }

            try
            {
                Directory.Move(stagedDictPath, finalDictPath);
                Console.Error.WriteLine("OpenJTalk dictionary installed successfully.");
            }
            catch (IOException) when (IsValidDictionary(finalDictPath))
            {
                // Another process published first. Its copy is equally valid
                // (same URL, same verified SHA256), so keep it and drop ours
                // rather than replacing a directory someone may have open.
                Console.Error.WriteLine(
                    "OpenJTalk dictionary was installed concurrently by another process; "
                    + "using the existing copy.");
            }
        }
        finally
        {
            // The staging directory holds the archive, its .tmp and anything
            // left over from a failed extract. None of it is shared with
            // another process, so removing it unconditionally is safe.
            TryDeleteDirectory(stagingDir);
        }
    }

    /// <summary>
    /// Monotonic sequence for staging directory names.
    /// </summary>
    /// <remarks>
    /// <see cref="Environment.ProcessId"/> separates processes; this counter
    /// separates callers within one process, so a retry after a failed
    /// download cannot collide with its own leftovers.
    /// </remarks>
    private static long stagingSeq;

    /// <summary>
    /// Returns the next staging directory sequence number.
    /// </summary>
    /// <remarks>
    /// <c>internal</c> so DictionaryManagerTests can assert that two callers
    /// never receive the same staging name -- a constant or timestamp-derived
    /// name would move the cross-process race inside the process, which is
    /// what happened in the Rust port of the ORT cache fix (#686).
    /// </remarks>
    internal static long NextStagingSeq() => Interlocked.Increment(ref stagingSeq);

    /// <summary>
    /// Builds the per-process staging directory path used while downloading
    /// and extracting. Exposed for tests; see <see cref="NextStagingSeq"/>.
    /// </summary>
    internal static string BuildStagingDirPath(string dataDir) =>
        Path.Join(dataDir, $".staging.{Environment.ProcessId}.{NextStagingSeq():x8}");

    /// <summary>
    /// Best-effort recursive delete. Used only for per-process staging
    /// directories, never for a published dictionary.
    /// </summary>
    private static void TryDeleteDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path))
            {
                Directory.Delete(path, recursive: true);
            }
        }
        catch (IOException)
        {
            // best effort
        }
        catch (UnauthorizedAccessException)
        {
            // best effort
        }
    }

    /// <summary>
    /// Copies stream content with periodic progress reporting to stderr.
    /// </summary>
    private static async Task CopyWithProgressAsync(
        Stream source, Stream destination, long? totalBytes, CancellationToken ct)
    {
        var buffer = new byte[81920];
        long totalRead = 0;
        long lastReportedMb = -1;
        int bytesRead;

        while ((bytesRead = await source.ReadAsync(buffer, ct).ConfigureAwait(false)) > 0)
        {
            await destination.WriteAsync(buffer.AsMemory(0, bytesRead), ct).ConfigureAwait(false);
            totalRead += bytesRead;

            // Report progress every 1 MB
            long currentMb = totalRead / (1024 * 1024);
            if (currentMb > lastReportedMb)
            {
                lastReportedMb = currentMb;
                if (totalBytes.HasValue && totalBytes.Value > 0)
                {
                    var pct = (double)totalRead / totalBytes.Value * 100;
                    Console.Error.Write(
                        $"\r  Downloaded {currentMb} MB / {totalBytes.Value / (1024 * 1024)} MB ({pct:F0}%)");
                }
                else
                {
                    Console.Error.Write($"\r  Downloaded {currentMb} MB");
                }
            }
        }

        Console.Error.WriteLine(); // newline after progress
    }

    private static async Task<string> ComputeSha256Async(
        string filePath, CancellationToken ct)
    {
        using var sha256 = SHA256.Create();
        await using var fileStream = new FileStream(
            filePath, FileMode.Open, FileAccess.Read,
            FileShare.Read, bufferSize: 81920, useAsync: true);

        var hashBytes = await sha256.ComputeHashAsync(fileStream, ct).ConfigureAwait(false);
        return Convert.ToHexString(hashBytes).ToLowerInvariant();
    }

    /// <summary>
    /// Extracts a .tar.gz archive using GZipStream + manual tar parsing.
    /// Handles the standard POSIX tar format used by the OpenJTalk dictionary archive.
    /// </summary>
    private static async Task ExtractTarGzAsync(
        string archivePath, string outputDir, CancellationToken ct)
    {
        await using var fileStream = new FileStream(
            archivePath, FileMode.Open, FileAccess.Read,
            FileShare.Read, bufferSize: 81920, useAsync: true);
        await using var gzipStream = new GZipStream(fileStream, CompressionMode.Decompress);

        // Buffer to hold each 512-byte tar header block
        var headerBuf = new byte[512];

        while (true)
        {
            ct.ThrowIfCancellationRequested();

            // Read the 512-byte tar header
            int totalRead = 0;
            while (totalRead < 512)
            {
                int read = await gzipStream.ReadAsync(
                    headerBuf.AsMemory(totalRead, 512 - totalRead), ct).ConfigureAwait(false);
                if (read == 0)
                {
                    return; // end of stream
                }

                totalRead += read;
            }

            // Two consecutive zero blocks = end of archive
            if (IsZeroBlock(headerBuf))
            {
                return;
            }

            // Parse header fields
            var name = ReadTarString(headerBuf, 0, 100);
            var sizeOctal = ReadTarString(headerBuf, 124, 12);
            var typeFlag = (char)headerBuf[156];
            var prefix = ReadTarString(headerBuf, 345, 155);

            // Combine prefix + name (UStar format)
            var fullName = string.IsNullOrEmpty(prefix)
                ? name
                : prefix + "/" + name;

            if (string.IsNullOrEmpty(fullName))
            {
                return;
            }

            // Parse size (octal)
            long fileSize = 0;
            if (!string.IsNullOrWhiteSpace(sizeOctal))
            {
                try
                {
                    fileSize = Convert.ToInt64(sizeOctal.Trim(), 8);
                }
                catch (FormatException)
                {
                    fileSize = 0;
                }
            }

            // Sanitize path: reject absolute paths and path traversal
            fullName = fullName.Replace('\\', '/');
            if (fullName.StartsWith('/') || fullName.Contains(".."))
            {
                // Skip unsafe entries, but still consume data blocks
                await SkipTarDataAsync(gzipStream, fileSize, ct).ConfigureAwait(false);
                continue;
            }

            var outputPath = Path.Join(outputDir, fullName.Replace('/', Path.DirectorySeparatorChar));

            switch (typeFlag)
            {
                case '5': // directory
                case 'D': // GNU directory
                    Directory.CreateDirectory(outputPath);
                    await SkipTarDataAsync(gzipStream, fileSize, ct).ConfigureAwait(false);
                    break;

                case '0': // regular file
                case '\0': // regular file (old-style)
                    // Ensure parent directory exists
                    var parentDir = Path.GetDirectoryName(outputPath);
                    if (!string.IsNullOrEmpty(parentDir))
                    {
                        Directory.CreateDirectory(parentDir);
                    }

                    await ExtractFileAsync(gzipStream, outputPath, fileSize, ct).ConfigureAwait(false);
                    break;

                default:
                    // Skip symlinks, hard links, etc.
                    await SkipTarDataAsync(gzipStream, fileSize, ct).ConfigureAwait(false);
                    break;
            }
        }
    }

    private static async Task ExtractFileAsync(
        Stream tarStream, string outputPath, long fileSize, CancellationToken ct)
    {
        await using var outFile = new FileStream(
            outputPath, FileMode.Create, FileAccess.Write,
            FileShare.None, bufferSize: 81920, useAsync: true);

        var buffer = new byte[81920];
        long remaining = fileSize;

        while (remaining > 0)
        {
            int toRead = (int)Math.Min(remaining, buffer.Length);
            int read = await tarStream.ReadAsync(buffer.AsMemory(0, toRead), ct).ConfigureAwait(false);
            if (read == 0)
            {
                throw new InvalidOperationException(
                    $"Unexpected end of tar stream while extracting {outputPath}");
            }

            await outFile.WriteAsync(buffer.AsMemory(0, read), ct).ConfigureAwait(false);
            remaining -= read;
        }

        // Tar entries are padded to 512-byte boundaries
        long padding = (512 - (fileSize % 512)) % 512;
        if (padding > 0)
        {
            await SkipBytesAsync(tarStream, padding, ct).ConfigureAwait(false);
        }
    }

    private static async Task SkipTarDataAsync(
        Stream tarStream, long fileSize, CancellationToken ct)
    {
        // Total bytes to skip: file data + padding to 512-byte boundary
        long totalSkip = fileSize + ((512 - (fileSize % 512)) % 512);
        await SkipBytesAsync(tarStream, totalSkip, ct).ConfigureAwait(false);
    }

    private static async Task SkipBytesAsync(
        Stream stream, long count, CancellationToken ct)
    {
        var buffer = new byte[Math.Min(count, 81920)];
        long remaining = count;
        while (remaining > 0)
        {
            int toRead = (int)Math.Min(remaining, buffer.Length);
            int read = await stream.ReadAsync(buffer.AsMemory(0, toRead), ct).ConfigureAwait(false);
            if (read == 0)
            {
                return; // end of stream
            }

            remaining -= read;
        }
    }

    private static bool IsZeroBlock(byte[] block)
    {
        for (int i = 0; i < block.Length; i++)
        {
            if (block[i] != 0)
            {
                return false;
            }
        }

        return true;
    }

    private static string ReadTarString(byte[] buffer, int offset, int length)
    {
        int end = offset;
        int limit = offset + length;
        while (end < limit && buffer[end] != 0)
        {
            end++;
        }

        return System.Text.Encoding.ASCII.GetString(buffer, offset, end - offset);
    }
}
