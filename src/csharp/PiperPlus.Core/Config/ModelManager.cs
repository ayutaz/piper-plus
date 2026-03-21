using System.Net.Http;
using System.Runtime.InteropServices;

namespace PiperPlus.Core.Config;

/// <summary>
/// Manages voice model discovery, listing, and downloading.
/// Port of the C++ <c>model_manager.cpp</c> to idiomatic C#.
/// </summary>
public static class ModelManager
{
    private static readonly HttpClient s_httpClient = CreateHttpClient();

    private static HttpClient CreateHttpClient()
    {
        var client = new HttpClient
        {
            // HuggingFace redirects to CDN; follow automatically
            Timeout = TimeSpan.FromMinutes(10),
        };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("PiperPlus/1.0");
        return client;
    }

    private const string HuggingFacePrefix = "https://huggingface.co/";

    // ------------------------------------------------------------------
    // GetDefaultModelDir
    // ------------------------------------------------------------------

    /// <summary>
    /// Returns the OS-specific default model directory.
    /// <list type="bullet">
    ///   <item><description>Windows: <c>%APPDATA%\piper\models</c></description></item>
    ///   <item><description>macOS:   <c>~/Library/Application Support/piper/models</c></description></item>
    ///   <item><description>Linux:   <c>$XDG_DATA_HOME/piper/models</c> or <c>~/.local/share/piper/models</c></description></item>
    /// </list>
    /// Override with the <c>PIPER_MODEL_DIR</c> environment variable.
    /// </summary>
    public static string GetDefaultModelDir()
    {
        var envDir = Environment.GetEnvironmentVariable("PIPER_MODEL_DIR");
        if (!string.IsNullOrEmpty(envDir))
        {
            return envDir;
        }

        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            var appData = Environment.GetFolderPath(
                Environment.SpecialFolder.ApplicationData);
            return !string.IsNullOrEmpty(appData)
                ? Path.Combine(appData, "piper", "models")
                : "models";
        }

        if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
        {
            var home = Environment.GetFolderPath(
                Environment.SpecialFolder.UserProfile);
            return !string.IsNullOrEmpty(home)
                ? Path.Combine(home, "Library", "Application Support",
                               "piper", "models")
                : "models";
        }

        // Linux / other Unix
        var xdgData = Environment.GetEnvironmentVariable("XDG_DATA_HOME");
        if (!string.IsNullOrEmpty(xdgData))
        {
            return Path.Combine(xdgData, "piper", "models");
        }

        var linuxHome = Environment.GetFolderPath(
            Environment.SpecialFolder.UserProfile);
        return !string.IsNullOrEmpty(linuxHome)
            ? Path.Combine(linuxHome, ".local", "share", "piper", "models")
            : "models";
    }

    // ------------------------------------------------------------------
    // FindVoice
    // ------------------------------------------------------------------

    private static Dictionary<string, VoiceInfo>? s_voiceLookup;

    private static Dictionary<string, VoiceInfo> GetVoiceLookup(IReadOnlyList<VoiceInfo> catalog)
    {
        if (s_voiceLookup is not null) return s_voiceLookup;

        var lookup = new Dictionary<string, VoiceInfo>(catalog.Count * 4, StringComparer.Ordinal);
        foreach (var voice in catalog)
        {
            lookup.TryAdd(voice.Key, voice);
            foreach (var alias in voice.Aliases)
            {
                lookup.TryAdd(alias, voice);
            }
        }
        s_voiceLookup = lookup;
        return lookup;
    }

    /// <summary>
    /// Searches the merged catalog for a voice by exact key or alias.
    /// Uses a cached dictionary for O(1) lookup.
    /// Returns <c>null</c> when no match is found.
    /// </summary>
    public static VoiceInfo? FindVoice(string nameOrAlias)
    {
        if (nameOrAlias is null) return null;
        var catalog = VoiceCatalog.LoadMergedCatalog();
        var lookup = GetVoiceLookup(catalog);
        return lookup.TryGetValue(nameOrAlias, out var voice) ? voice : null;
    }

    // ------------------------------------------------------------------
    // ListModels
    // ------------------------------------------------------------------

    /// <summary>
    /// Writes a human-readable list of available voice models to <c>stderr</c>.
    /// Output format matches the C++ implementation for consistency.
    /// </summary>
    /// <param name="languageFilter">
    /// Optional language code (e.g. "ja" or "ja_JP") to filter by.
    /// </param>
    public static void ListModels(string? languageFilter = null)
    {
        var catalog = VoiceCatalog.LoadMergedCatalog();

        if (catalog.Count == 0)
        {
            Console.Error.WriteLine("No voice models found.");
            return;
        }

        // Filter by language if specified
        IReadOnlyList<VoiceInfo> filtered;
        if (string.IsNullOrEmpty(languageFilter))
        {
            filtered = catalog;
        }
        else
        {
            var list = new List<VoiceInfo>();
            foreach (var voice in catalog)
            {
                if (string.Equals(voice.LanguageFamily, languageFilter,
                                   StringComparison.Ordinal) ||
                    string.Equals(voice.LanguageCode, languageFilter,
                                   StringComparison.Ordinal))
                {
                    list.Add(voice);
                }
            }

            filtered = list;
        }

        if (filtered.Count == 0)
        {
            Console.Error.WriteLine(
                $"No voice models found for language: {languageFilter}");
            return;
        }

        Console.Error.WriteLine();
        Console.Error.WriteLine("Available voice models:");

        // Group by language code (catalog is already sorted by language, then key)
        string currentLang = "";
        foreach (var voice in filtered)
        {
            if (!string.Equals(voice.LanguageCode, currentLang,
                                StringComparison.Ordinal))
            {
                currentLang = voice.LanguageCode;
                Console.Error.WriteLine();

                var header = $"  {voice.LanguageNameEnglish}";
                if (!string.IsNullOrEmpty(voice.LanguageNameNative) &&
                    voice.LanguageNameNative != voice.LanguageNameEnglish)
                {
                    header += $" ({voice.LanguageNameNative})";
                }

                header += $" [{voice.LanguageCode}]:";
                Console.Error.WriteLine(header);
            }

            // Format: key  [source]  N speaker(s)  quality
            var keyPart = $"    {voice.Key}";
            int padLen = 44 - keyPart.Length; // 4 indent + 40 key width
            var padding = padLen > 0 ? new string(' ', padLen) : "  ";

            var speakers = voice.NumSpeakers == 1 ? "1 speaker" :
                $"{voice.NumSpeakers} speakers";

            Console.Error.WriteLine(
                $"{keyPart}{padding}[{voice.Source}]  {speakers}   {voice.Quality}");
        }

        Console.Error.WriteLine();
        Console.Error.WriteLine("Use --download-model <name> to download a model.");
        Console.Error.WriteLine();
    }

    // ------------------------------------------------------------------
    // DownloadModelAsync
    // ------------------------------------------------------------------

    /// <summary>
    /// Downloads a voice model (all files) to <paramref name="modelDir"/>.
    /// Uses <see cref="HttpClient"/> for downloading (HTTPS enforced).
    /// Existing files with matching size are skipped.
    /// </summary>
    /// <returns><c>true</c> if all files downloaded (or skipped) successfully.</returns>
    public static async Task<bool> DownloadModelAsync(
        string modelName, string modelDir, CancellationToken ct = default)
    {
        var voice = FindVoice(modelName);
        if (voice is null)
        {
            Console.Error.WriteLine(
                $"Error: Model '{modelName}' not found. " +
                "Use --list-models to see available models.");
            return false;
        }

        Console.Error.WriteLine(
            $"Downloading model: {voice.Key} ({voice.Source})");

        // Security: validate voice key (no path traversal)
        if (!IsSafeVoiceKey(voice.Key))
        {
            Console.Error.WriteLine(
                $"Error: Voice key '{voice.Key}' contains unsafe path characters.");
            return false;
        }

        // Security: validate repo ID format
        if (!string.IsNullOrEmpty(voice.RepoId) && !IsSafeRepoId(voice.RepoId))
        {
            Console.Error.WriteLine(
                $"Error: Repo ID '{voice.RepoId}' has invalid format.");
            return false;
        }

        // Ensure target directory exists
        Directory.CreateDirectory(modelDir);

        // Build base URL depending on source
        string baseUrl;
        if (string.Equals(voice.Source, "piper-plus", StringComparison.Ordinal))
        {
            baseUrl = $"{HuggingFacePrefix}{voice.RepoId}/resolve/main/";
        }
        else
        {
            // Upstream piper
            baseUrl = $"{HuggingFacePrefix}rhasspy/piper-voices/resolve/v1.0.0/";
        }

        bool allOk = true;

        foreach (var file in voice.Files)
        {
            // Security: validate file path safety (no path traversal)
            var localName = Path.GetFileName(file.RelativePath);
            if (string.IsNullOrEmpty(localName) || file.RelativePath.Contains(".."))
            {
                Console.Error.WriteLine(
                    $"  Skipping file with unsafe path: {file.RelativePath}");
                allOk = false;
                continue;
            }

            var url = baseUrl + file.RelativePath;

            // Security: enforce HTTPS HuggingFace prefix
            if (!url.StartsWith(HuggingFacePrefix, StringComparison.Ordinal))
            {
                Console.Error.WriteLine(
                    $"Error: Rejecting URL with unexpected scheme/domain: {url}");
                allOk = false;
                continue;
            }

            // Use just the filename as the local name (flat directory layout)
            var localPath = Path.Combine(modelDir, localName);

            // Skip if file already exists with correct size
            if (File.Exists(localPath) && file.SizeBytes > 0)
            {
                var existingSize = new FileInfo(localPath).Length;
                if (existingSize == file.SizeBytes)
                {
                    Console.Error.WriteLine($"  {localName} already exists, skipping");
                    continue;
                }
            }

            Console.Error.WriteLine($"  Downloading {url} ...");
            if (!await DownloadFileAsync(url, localPath, ct).ConfigureAwait(false))
            {
                Console.Error.WriteLine($"  Failed to download {file.RelativePath}");
                allOk = false;
            }
            else
            {
                Console.Error.WriteLine($"  Downloaded {localName}");

                // Verify MD5 digest if available
                if (!string.IsNullOrEmpty(file.Md5Digest))
                {
                    using var md5 = System.Security.Cryptography.MD5.Create();
                    using var fileStream = File.OpenRead(localPath);
                    var hashBytes = md5.ComputeHash(fileStream);
                    var actualHash = BitConverter.ToString(hashBytes)
                        .Replace("-", "").ToLowerInvariant();
                    if (actualHash != file.Md5Digest.ToLowerInvariant())
                    {
                        Console.Error.WriteLine(
                            $"  MD5 mismatch for {localName}: " +
                            $"expected {file.Md5Digest}, got {actualHash}");
                    }
                }
            }
        }

        if (allOk)
        {
            // Find the .onnx file to show the --model path
            string? onnxFile = null;
            foreach (var file in voice.Files)
            {
                var fn = Path.GetFileName(file.RelativePath);
                if (fn.EndsWith(".onnx", StringComparison.OrdinalIgnoreCase))
                {
                    onnxFile = Path.Combine(modelDir, fn);
                    break;
                }
            }

            Console.Error.WriteLine();
            Console.Error.WriteLine("Model downloaded successfully!");
            if (onnxFile is not null)
            {
                Console.Error.WriteLine($"Use with:  --model {onnxFile}");
            }

            Console.Error.WriteLine();
        }

        return allOk;
    }

    // ------------------------------------------------------------------
    // ResolveModelPathAsync
    // ------------------------------------------------------------------

    /// <summary>
    /// Resolves a model path from a file path, model name, or alias.
    /// <list type="number">
    ///   <item><description>If <paramref name="modelStr"/> exists as a file, returns it directly.</description></item>
    ///   <item><description>If it matches a model name/alias, checks for a locally cached ONNX file.</description></item>
    ///   <item><description>If not cached, auto-downloads the model and returns the ONNX path.</description></item>
    /// </list>
    /// </summary>
    /// <param name="modelStr">File path, model name, or alias.</param>
    /// <param name="modelDir">
    /// Directory for cached models. Falls back to <see cref="GetDefaultModelDir"/>.
    /// </param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Absolute path to the resolved <c>.onnx</c> model file.</returns>
    /// <exception cref="FileNotFoundException">
    /// Thrown when <paramref name="modelStr"/> is not a file and not a known model name,
    /// or when the downloaded model does not contain an ONNX file.
    /// </exception>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the download fails.
    /// </exception>
    public static async Task<string> ResolveModelPathAsync(
        string modelStr, string? modelDir = null, CancellationToken ct = default)
    {
        // 1. Direct file path
        if (File.Exists(modelStr))
            return Path.GetFullPath(modelStr);

        // 2. Try as model name/alias
        var voice = FindVoice(modelStr);
        if (voice is null)
        {
            throw new FileNotFoundException(
                $"Model '{modelStr}' not found as file or model name. " +
                "Use --list-models to see available models.");
        }

        var dir = modelDir ?? GetDefaultModelDir();

        // Find the .onnx file entry in the voice catalog
        var onnxFile = voice.Files
            .FirstOrDefault(f => f.RelativePath.EndsWith(".onnx", StringComparison.OrdinalIgnoreCase));

        // Check if already cached locally
        if (onnxFile is not null)
        {
            var cachedPath = Path.Combine(dir, Path.GetFileName(onnxFile.RelativePath));
            if (File.Exists(cachedPath))
                return cachedPath;
        }

        // 3. Auto-download
        Console.Error.WriteLine($"Model '{voice.Key}' not found locally. Downloading...");
        bool success = await DownloadModelAsync(voice.Key, dir, ct).ConfigureAwait(false);
        if (!success)
        {
            throw new InvalidOperationException(
                $"Failed to download model '{voice.Key}'.");
        }

        if (onnxFile is not null)
        {
            var downloadedPath = Path.Combine(dir, Path.GetFileName(onnxFile.RelativePath));
            if (File.Exists(downloadedPath))
                return downloadedPath;
        }

        throw new FileNotFoundException(
            $"Model '{voice.Key}' downloaded but ONNX file not found in {dir}.");
    }

    // ------------------------------------------------------------------
    // Private: file download via HttpClient
    // ------------------------------------------------------------------

    private static async Task<bool> DownloadFileAsync(
        string url, string outputPath, CancellationToken ct)
    {
        var tempPath = outputPath + ".tmp";
        try
        {
            using var response = await s_httpClient
                .GetAsync(url, HttpCompletionOption.ResponseHeadersRead, ct)
                .ConfigureAwait(false);
            response.EnsureSuccessStatusCode();

            // Ensure parent directory exists (defensive)
            var dir = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrEmpty(dir))
            {
                Directory.CreateDirectory(dir);
            }

            await using var contentStream = await response.Content
                .ReadAsStreamAsync(ct)
                .ConfigureAwait(false);
            await using var fileStream = new FileStream(
                tempPath, FileMode.Create, FileAccess.Write,
                FileShare.None, bufferSize: 81920, useAsync: true);

            await contentStream
                .CopyToAsync(fileStream, ct)
                .ConfigureAwait(false);

            // Atomically replace the target file
            File.Move(tempPath, outputPath, true);

            return true;
        }
        catch (Exception ex) when (
            ex is HttpRequestException or TaskCanceledException or IOException)
        {
            Console.Error.WriteLine($"  Download error: {ex.Message}");

            // Clean up partial temp file
            try { File.Delete(tempPath); } catch { /* best-effort */ }

            return false;
        }
    }

    // ------------------------------------------------------------------
    // Private: security validation helpers
    // ------------------------------------------------------------------

    /// <summary>
    /// Validates that a voice key contains no path traversal characters.
    /// Rejects "..", "/", and "\" to prevent directory escape.
    /// </summary>
    private static bool IsSafeVoiceKey(string key)
    {
        if (string.IsNullOrEmpty(key)) return false;
        if (key.Contains("..")) return false;
        if (key.Contains('/')) return false;
        if (key.Contains('\\')) return false;
        return true;
    }

    /// <summary>
    /// Validates that a repoId matches the <c>owner/repo</c> format with only
    /// safe characters (alphanumerics, hyphens, underscores, dots, one slash).
    /// </summary>
    private static bool IsSafeRepoId(string repoId)
    {
        if (string.IsNullOrEmpty(repoId)) return false;

        int slashCount = 0;
        foreach (char c in repoId)
        {
            if (c == '/')
            {
                slashCount++;
                if (slashCount > 1) return false;
            }
            else if (!char.IsAsciiLetterOrDigit(c) &&
                     c != '-' && c != '_' && c != '.')
            {
                return false;
            }
        }

        // Must have exactly one slash (owner/repo format)
        return slashCount == 1;
    }
}
