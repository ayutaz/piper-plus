using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Text pre-processing custom dictionary.
/// <para>
/// Loads dictionary files in either TSV or JSON format. Entries are applied
/// in longest-match-first order so that longer keys take priority over
/// shorter ones.
/// </para>
/// <para>
/// Mirrors the custom dictionary functionality in the Python
/// (<c>piper_train/phonemize/custom_dict.py</c>), C++
/// (<c>src/cpp/custom_dictionary.cpp</c>) and Rust
/// (<c>src/rust/piper-core/src/phonemize/custom_dict.rs</c>) implementations.
/// </para>
/// </summary>
/// <remarks>
/// <para><b>TSV format</b> (UTF-8, tab-separated):</para>
/// <code>
/// # Comment lines start with '#'
/// source_text\treplacement_text
/// </code>
/// <para><b>JSON v1.0 format</b>:</para>
/// <code>
/// { "version": "1.0", "entries": { "API": "エーピーアイ" } }
/// </code>
/// <para><b>JSON v2.0 format</b> (with priority):</para>
/// <code>
/// { "version": "2.0", "entries": { "API": { "pronunciation": "エーピーアイ", "priority": 8 } } }
/// </code>
/// <para>Format is auto-detected by file extension: <c>.json</c> files use
/// JSON parsing, all other extensions use TSV parsing.</para>
/// <list type="bullet">
///   <item>Empty lines and comment lines (starting with <c>#</c>) are skipped in TSV.</item>
///   <item>Keys starting with <c>//</c> and metadata keys (<c>version</c>,
///         <c>description</c>, <c>metadata</c>) are skipped in JSON.</item>
///   <item>Higher priority values win when the same key appears in multiple files.</item>
/// </list>
/// </remarks>
public sealed class CustomDictionary
{
    private static ILogger s_logger = NullLogger.Instance;

    private static readonly ConcurrentDictionary<string, Regex> _regexCache = new();

    /// <summary>
    /// Replace the default (no-op) logger used for dictionary load warnings.
    /// Call once at application startup; not required for correct operation.
    /// </summary>
    public static void SetLogger(ILogger logger)
    {
        s_logger = logger ?? NullLogger.Instance;
    }

    private static Regex GetOrCreateRegex(string key, bool caseSensitive)
    {
        string cacheKey = key + (caseSensitive ? "_cs" : "_ci");
        return _regexCache.GetOrAdd(cacheKey, _ =>
        {
            var pattern = @"\b" + Regex.Escape(key) + @"\b";
            var options = RegexOptions.Compiled | RegexOptions.CultureInvariant;
            if (!caseSensitive) options |= RegexOptions.IgnoreCase;
            return new Regex(pattern, options);
        });
    }

    /// <summary>
    /// A single dictionary entry with key, value (replacement text), priority,
    /// and case-sensitivity flag.
    /// Higher priority wins when the same key is loaded from multiple files.
    /// </summary>
    /// <param name="Key">The original dictionary key (before any normalization).</param>
    /// <param name="Value">The replacement text (pronunciation).</param>
    /// <param name="Priority">Priority for conflict resolution (higher wins).</param>
    /// <param name="IsCaseSensitive">
    /// <c>true</c> for mixed-case keys (e.g. "PyTorch") that must match exactly;
    /// <c>false</c> for all-upper or all-lower keys that match case-insensitively.
    /// </param>
    private record DictionaryEntry(string Key, string Value, int Priority = 5, bool IsCaseSensitive = false);

    // Entries stored with priority support.
    // Kept in a list so we can sort by key length for longest-match-first application.
    private readonly List<DictionaryEntry> _entries = new();

    // Track whether the sorted cache is stale.
    private bool _dirty;

    // Sorted snapshot used by ApplyToText (rebuilt lazily when _dirty is true).
    private List<DictionaryEntry>? _sorted;

    private readonly object _sortLock = new();

    /// <summary>
    /// Number of entries currently loaded.
    /// </summary>
    public int Count => _entries.Count;

    /// <summary>
    /// Load a single dictionary file.
    /// <para>
    /// Format is auto-detected by file extension: <c>.json</c> files are
    /// parsed as JSON (v1.0 / v2.0), all other extensions are parsed as TSV.
    /// </para>
    /// </summary>
    /// <param name="filePath">
    /// Path to a UTF-8 dictionary file (TSV or JSON).
    /// </param>
    /// <exception cref="FileNotFoundException">
    /// Thrown when <paramref name="filePath"/> does not exist.
    /// </exception>
    /// <exception cref="ArgumentNullException">
    /// Thrown when <paramref name="filePath"/> is <c>null</c>.
    /// </exception>
    /// <exception cref="JsonException">
    /// Thrown when a <c>.json</c> file contains malformed JSON.
    /// </exception>
    public void LoadDictionary(string filePath)
    {
        ArgumentNullException.ThrowIfNull(filePath);

        if (!File.Exists(filePath))
        {
            throw new FileNotFoundException(
                $"Dictionary file not found: {filePath}", filePath);
        }

        if (filePath.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
            LoadJsonDictionary(filePath);
        else
            LoadTsvDictionary(filePath);
    }

    // ----------------------------------------------------------------
    // TSV loading (original format)
    // ----------------------------------------------------------------

    private void LoadTsvDictionary(string filePath)
    {
        using var reader = new StreamReader(filePath, Encoding.UTF8);
        string? line;

        while ((line = reader.ReadLine()) is not null)
        {
            // Skip empty lines.
            if (string.IsNullOrWhiteSpace(line))
                continue;

            // Skip comment lines.
            if (line.StartsWith('#'))
                continue;

            // Split on the first tab.
            int tabIndex = line.IndexOf('\t');
            if (tabIndex < 0)
                continue; // Malformed line — no tab found; skip silently.

            string key = line[..tabIndex];
            string value = line[(tabIndex + 1)..];

            if (key.Length == 0)
                continue; // Empty key — skip.

            AddEntry(key, value, 5);
        }
    }

    // ----------------------------------------------------------------
    // JSON loading (v1.0 / v2.0 — matches C++/Rust format)
    // ----------------------------------------------------------------

    private void LoadJsonDictionary(string filePath)
    {
        string json = File.ReadAllText(filePath, Encoding.UTF8);
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        // Get entries — either from "entries" key or root level.
        JsonElement entries;
        if (root.TryGetProperty("entries", out var entriesObj)
            && entriesObj.ValueKind == JsonValueKind.Object)
        {
            entries = entriesObj;
        }
        else
        {
            entries = root;
        }

        foreach (var prop in entries.EnumerateObject())
        {
            string word = prop.Name;

            // Skip metadata keys.
            if (word is "version" or "description" or "metadata")
                continue;

            // Skip comment keys (v2.0 convention).
            if (word.StartsWith("//"))
                continue;

            if (prop.Value.ValueKind == JsonValueKind.Object)
            {
                // V2.0: { "pronunciation": "...", "priority": N }
                if (prop.Value.TryGetProperty("pronunciation", out var pronEl))
                {
                    string pronunciation = pronEl.GetString() ?? "";
                    int priority = 5;
                    if (prop.Value.TryGetProperty("priority", out var priEl)
                        && priEl.ValueKind == JsonValueKind.Number)
                    {
                        priority = priEl.GetInt32();
                    }

                    AddEntry(word, pronunciation, priority);
                }
            }
            else if (prop.Value.ValueKind == JsonValueKind.String)
            {
                // V1.0: "word": "pronunciation"
                AddEntry(word, prop.Value.GetString() ?? "", 5);
            }
        }
    }

    // ----------------------------------------------------------------
    // Priority-aware entry insertion
    // ----------------------------------------------------------------

    private void AddEntry(string key, string value, int priority)
    {
        bool caseSensitive = IsMixedCase(key);

        // For case-insensitive entries, match by lowered key to deduplicate
        // (e.g. "API" and "api" should be treated as the same entry).
        var existing = _entries.FindIndex(e =>
            caseSensitive
                ? (e.IsCaseSensitive && e.Key == key)
                : (!e.IsCaseSensitive && string.Equals(e.Key, key, StringComparison.OrdinalIgnoreCase)));

        if (existing >= 0)
        {
            if (priority <= _entries[existing].Priority)
                return; // Existing has higher or equal priority — keep it.

            _entries[existing] = new DictionaryEntry(key, value, priority, caseSensitive);
        }
        else
        {
            _entries.Add(new DictionaryEntry(key, value, priority, caseSensitive));
        }

        _dirty = true;
    }

    /// <summary>
    /// Load default dictionaries from standard locations.
    /// <para>
    /// Searches for a <c>data/dictionaries/</c> directory relative to the
    /// application base directory, its parent directories, and the current
    /// working directory.  All <c>*.json</c> files in the first directory
    /// found are loaded in ordinal-sorted order (matching C++ behaviour).
    /// Files that fail to parse are silently skipped with a log warning.
    /// </para>
    /// </summary>
    public void LoadDefaults()
    {
        var searchPaths = new List<string>();

        // Exe-relative paths (matches C++ findDictDir candidates)
        var exeDir = AppContext.BaseDirectory.TrimEnd(
            Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        searchPaths.Add(Path.Combine(exeDir, "data", "dictionaries"));
        searchPaths.Add(Path.Combine(exeDir, "..", "data", "dictionaries"));
        searchPaths.Add(Path.Combine(exeDir, "..", "..", "data", "dictionaries"));

        // Working directory
        searchPaths.Add(Path.Combine(
            Directory.GetCurrentDirectory(), "data", "dictionaries"));

        foreach (var searchPath in searchPaths)
        {
            if (!Directory.Exists(searchPath))
                continue;

            // Load in sorted order (matching C++ behaviour)
            var files = Directory.GetFiles(searchPath, "*.json")
                .OrderBy(f => f, StringComparer.Ordinal)
                .ToArray();

            foreach (var file in files)
            {
                try
                {
                    LoadDictionary(file);
                }
                catch (Exception ex)
                {
                    s_logger.LogWarning(
                        "Failed to load default dictionary {File}: {Message}",
                        file, ex.Message);
                }
            }

            // Only load from first found directory
            return;
        }
    }

    /// <summary>
    /// Load multiple dictionary files. If loading one file fails, a warning
    /// is logged via <see cref="SetLogger"/> and the remaining files are still processed.
    /// </summary>
    /// <param name="filePaths">Paths to dictionary files.</param>
    /// <exception cref="ArgumentNullException">
    /// Thrown when <paramref name="filePaths"/> is <c>null</c>.
    /// </exception>
    public void LoadDictionaries(IEnumerable<string> filePaths)
    {
        ArgumentNullException.ThrowIfNull(filePaths);

        foreach (var filePath in filePaths)
        {
            try
            {
                LoadDictionary(filePath);
            }
            catch (Exception ex)
            {
                s_logger.LogWarning(
                    "Failed to load dictionary {FilePath}: {Message}",
                    filePath, ex.Message);
            }
        }
    }

    /// <summary>
    /// Apply all dictionary entries to <paramref name="text"/>.
    /// <para>
    /// Entries are applied in longest-key-first order (longest match wins).
    /// Mixed-case keys (e.g. "PyTorch") match case-sensitively; all-upper
    /// or all-lower keys (e.g. "AI", "python") match case-insensitively.
    /// ASCII-only keys use word-boundary matching (<c>\b</c>) to prevent
    /// partial matches (e.g. "AI" does not match inside "AIDS").
    /// Non-ASCII keys (Japanese, Chinese, etc.) use simple substring replacement.
    /// </para>
    /// </summary>
    /// <param name="text">Input text.</param>
    /// <returns>Text with all matching entries replaced.</returns>
    public string ApplyToText(string text)
    {
        if (string.IsNullOrEmpty(text) || _entries.Count == 0)
            return text;

        // Rebuild sorted snapshot when entries have changed.
        if (_dirty || _sorted is null)
        {
            lock (_sortLock)
            {
                if (_dirty || _sorted is null)
                {
                    _sorted = _entries
                        .OrderByDescending(e => e.Key.Length)
                        .ThenBy(e => e.Key, StringComparer.Ordinal)
                        .ToList();
                    _dirty = false;
                }
            }
        }

        foreach (var entry in _sorted)
        {
            if (StartsWithAscii(entry.Key))
            {
                // Fast pre-check: skip regex if the key doesn't appear at all.
                if (text.IndexOf(entry.Key, entry.IsCaseSensitive ? StringComparison.Ordinal : StringComparison.OrdinalIgnoreCase) < 0)
                    continue;

                // ASCII words: use \b word boundary to prevent partial matches.
                var regex = GetOrCreateRegex(entry.Key, entry.IsCaseSensitive);
                text = regex.Replace(text, entry.Value);
            }
            else
            {
                // Non-ASCII (Japanese, Chinese, etc.): simple substring replacement.
                var comparison = entry.IsCaseSensitive
                    ? StringComparison.Ordinal
                    : StringComparison.OrdinalIgnoreCase;
                text = text.Replace(entry.Key, entry.Value, comparison);
            }
        }

        return text;
    }

    // ----------------------------------------------------------------
    // Helper methods for case sensitivity and word boundary detection
    // ----------------------------------------------------------------

    /// <summary>
    /// Returns <c>true</c> when <paramref name="word"/> contains both
    /// upper-case and lower-case characters (e.g. "PyTorch", "iPhone").
    /// Such words are stored in the case-sensitive bucket and require
    /// exact-case matching.
    /// </summary>
    private static bool IsMixedCase(string word)
    {
        bool hasUpper = false, hasLower = false;
        foreach (char c in word)
        {
            if (char.IsUpper(c)) hasUpper = true;
            if (char.IsLower(c)) hasLower = true;
            if (hasUpper && hasLower) return true;
        }
        return false;
    }

    /// <summary>
    /// Returns <c>true</c> when the first character of <paramref name="word"/>
    /// is in the ASCII range (0-127), matching the C++ implementation.
    /// Words starting with non-ASCII characters (Japanese, Chinese, etc.)
    /// skip <c>\b</c> word-boundary matching because regex word boundaries
    /// do not work reliably with multi-byte characters.
    /// </summary>
    private static bool StartsWithAscii(string word)
    {
        return word.Length > 0 && word[0] <= 127;
    }
}
