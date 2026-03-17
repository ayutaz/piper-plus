using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Text pre-processing custom dictionary.
/// <para>
/// Loads tab-separated dictionary files where each line maps an original
/// string to its replacement. Entries are applied in longest-match-first
/// order so that longer keys take priority over shorter ones.
/// </para>
/// <para>
/// Mirrors the custom dictionary functionality in the Python
/// (<c>piper_train/phonemize/custom_dict.py</c>) and C++
/// (<c>src/cpp/custom_dictionary.cpp</c>) implementations.
/// </para>
/// </summary>
/// <remarks>
/// <para>Dictionary file format (UTF-8, tab-separated):</para>
/// <code>
/// # Comment lines start with '#'
/// source_text\treplacement_text
/// </code>
/// <list type="bullet">
///   <item>Empty lines are skipped.</item>
///   <item>Lines starting with <c>#</c> are treated as comments.</item>
///   <item>Each entry is <c>original&lt;TAB&gt;replacement</c>.</item>
/// </list>
/// </remarks>
public sealed class CustomDictionary
{
    private static ILogger s_logger = NullLogger.Instance;

    /// <summary>
    /// Replace the default (no-op) logger used for dictionary load warnings.
    /// Call once at application startup; not required for correct operation.
    /// </summary>
    public static void SetLogger(ILogger logger)
    {
        s_logger = logger ?? NullLogger.Instance;
    }

    // Entries stored as (original, replacement) pairs.
    // Kept in a list so we can sort by key length for longest-match-first application.
    private readonly List<KeyValuePair<string, string>> _entries = new();

    // Track whether the sorted cache is stale.
    private bool _dirty;

    // Sorted snapshot used by ApplyToText (rebuilt lazily when _dirty is true).
    private List<KeyValuePair<string, string>>? _sorted;

    /// <summary>
    /// Number of entries currently loaded.
    /// </summary>
    public int Count => _entries.Count;

    /// <summary>
    /// Load a single dictionary file.
    /// </summary>
    /// <param name="filePath">
    /// Path to a UTF-8 text file with tab-separated entries.
    /// </param>
    /// <exception cref="FileNotFoundException">
    /// Thrown when <paramref name="filePath"/> does not exist.
    /// </exception>
    /// <exception cref="ArgumentNullException">
    /// Thrown when <paramref name="filePath"/> is <c>null</c>.
    /// </exception>
    public void LoadDictionary(string filePath)
    {
        ArgumentNullException.ThrowIfNull(filePath);

        if (!File.Exists(filePath))
        {
            throw new FileNotFoundException(
                $"Dictionary file not found: {filePath}", filePath);
        }

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

            _entries.Add(new KeyValuePair<string, string>(key, value));
            _dirty = true;
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
    /// Replacement is case-sensitive.
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
            _sorted = _entries
                .OrderByDescending(kv => kv.Key.Length)
                .ThenBy(kv => kv.Key, StringComparer.Ordinal)
                .ToList();
            _dirty = false;
        }

        foreach (var kv in _sorted)
        {
            if (text.Contains(kv.Key, StringComparison.Ordinal))
            {
                text = text.Replace(kv.Key, kv.Value, StringComparison.Ordinal);
            }
        }

        return text;
    }
}
