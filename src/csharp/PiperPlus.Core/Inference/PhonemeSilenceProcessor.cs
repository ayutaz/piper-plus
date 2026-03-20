using System;
using System.Collections.Generic;
using System.Globalization;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Splits a phoneme-ID sequence into phrases at positions where a designated
/// "silence phoneme" occurs, and computes the number of zero-valued PCM
/// samples to insert between each phrase.
/// <para>
/// This mirrors the C++ implementation in <c>piper.cpp</c> where
/// <c>phonemeSilenceSeconds</c> causes the phoneme stream to be split into
/// sub-phrases.  Each sub-phrase is synthesised independently and the
/// resulting audio segments are concatenated with silence gaps.
/// </para>
/// </summary>
public static class PhonemeSilenceProcessor
{
    /// <summary>
    /// One contiguous segment of the original phoneme-ID sequence, together
    /// with its matching prosody slice and the number of silence samples to
    /// append <b>after</b> the synthesised audio for this phrase.
    /// </summary>
    /// <param name="PhonemeIds">Phoneme IDs for this phrase.</param>
    /// <param name="ProsodyFlat">
    /// Flat prosody array slice for this phrase (length = <c>PhonemeIds.Count * 3</c>),
    /// or <c>null</c> when no prosody data is available.
    /// </param>
    /// <param name="SilenceSamples">
    /// Number of zero-valued PCM samples to insert after this phrase.
    /// The last phrase (or any phrase not ending on a silence phoneme) has <c>0</c>.
    /// </param>
    public readonly record struct Phrase(
        List<long> PhonemeIds,
        List<long>? ProsodyFlat,
        int SilenceSamples);

    // ------------------------------------------------------------------
    // Parse
    // ------------------------------------------------------------------

    /// <summary>
    /// Parse one or more phoneme-silence specifications into a dictionary.
    /// <para>
    /// Accepted formats (mirrors the C++ CLI <c>--phoneme_silence</c> flag):
    /// <list type="bullet">
    ///   <item><c>"_ 0.5"</c> — single phoneme, space-separated.</item>
    ///   <item><c>"_ 0.5,# 0.3"</c> — multiple phonemes, comma-separated.</item>
    /// </list>
    /// </para>
    /// </summary>
    /// <param name="specification">
    /// A string such as <c>"_ 0.5"</c> or <c>"_ 0.5,# 0.3"</c>.
    /// </param>
    /// <returns>
    /// A dictionary mapping phoneme strings to seconds of silence.
    /// </returns>
    /// <exception cref="ArgumentException">
    /// Thrown when <paramref name="specification"/> is null/empty or contains
    /// an entry that cannot be parsed.
    /// </exception>
    public static Dictionary<string, float> Parse(string specification)
    {
        if (string.IsNullOrWhiteSpace(specification))
        {
            throw new ArgumentException(
                "Phoneme silence specification must not be empty.",
                nameof(specification));
        }

        var result = new Dictionary<string, float>();

        // Split on comma for multi-phoneme specifications.
        string[] entries = specification.Split(',',
            StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        foreach (string entry in entries)
        {
            // Each entry is "<phoneme> <seconds>".
            // Split on whitespace; the phoneme is everything before the last
            // whitespace-delimited token (the seconds value).
            int lastSpace = entry.LastIndexOf(' ');
            if (lastSpace <= 0)
            {
                throw new ArgumentException(
                    $"Cannot parse phoneme silence entry: '{entry}'. " +
                    "Expected format: '<phoneme> <seconds>'.",
                    nameof(specification));
            }

            string phoneme = entry[..lastSpace].Trim();
            string secondsStr = entry[(lastSpace + 1)..].Trim();

            if (string.IsNullOrEmpty(phoneme))
            {
                throw new ArgumentException(
                    $"Empty phoneme in entry: '{entry}'.",
                    nameof(specification));
            }

            if (!float.TryParse(secondsStr, NumberStyles.Float,
                    CultureInfo.InvariantCulture, out float seconds))
            {
                throw new ArgumentException(
                    $"Cannot parse seconds value '{secondsStr}' in entry: '{entry}'.",
                    nameof(specification));
            }

            result[phoneme] = seconds;
        }

        return result;
    }

    // ------------------------------------------------------------------
    // SplitAtPhonemeSilence
    // ------------------------------------------------------------------

    /// <summary>
    /// Split a phoneme-ID sequence into phrases at every position where one
    /// of the designated silence phonemes occurs.
    /// <para>
    /// Processing mirrors the C++ implementation:
    /// <list type="number">
    ///   <item>Build a reverse map from individual phoneme IDs to their
    ///         phoneme strings.</item>
    ///   <item>Walk the phoneme-ID array.  When a silence-phoneme ID is
    ///         encountered the current phrase is closed (the phoneme is
    ///         included in it) and a new phrase is started.</item>
    ///   <item>The silence duration in samples is recorded for the closed
    ///         phrase; the trailing phrase gets 0 silence samples.</item>
    /// </list>
    /// </para>
    /// </summary>
    /// <param name="phonemeIds">
    /// Complete phoneme-ID sequence (may include BOS/EOS/padding).
    /// </param>
    /// <param name="prosodyFlat">
    /// Flat prosody array of length <c>phonemeIds.Length * 3</c>, or
    /// <c>null</c> when prosody is not used.
    /// </param>
    /// <param name="phonemeSilence">
    /// Mapping from phoneme strings to silence duration in seconds, as
    /// returned by <see cref="Parse"/>.
    /// </param>
    /// <param name="phonemeIdMap">
    /// The <c>phoneme_id_map</c> from <c>config.json</c>, mapping phoneme
    /// strings to arrays of integer IDs.
    /// </param>
    /// <param name="sampleRate">Audio sample rate in Hz.</param>
    /// <returns>
    /// An ordered list of <see cref="Phrase"/> segments.  Empty phrases
    /// (those with zero phoneme IDs) are included in the list — the caller
    /// should skip them, matching the C++ behaviour.
    /// </returns>
    public static List<Phrase> SplitAtPhonemeSilence(
        long[] phonemeIds,
        long[]? prosodyFlat,
        Dictionary<string, float> phonemeSilence,
        Dictionary<string, int[]> phonemeIdMap,
        int sampleRate)
    {
        ArgumentNullException.ThrowIfNull(phonemeIds);
        ArgumentNullException.ThrowIfNull(phonemeSilence);
        ArgumentNullException.ThrowIfNull(phonemeIdMap);

        // Build reverse map: phoneme-ID → (phoneme string, silence seconds).
        // A single phoneme string can map to multiple IDs (e.g. "a" → [5, 6]),
        // but each individual ID uniquely identifies at most one silence entry.
        var silenceById = BuildSilenceIdMap(phonemeSilence, phonemeIdMap);

        bool hasProsody = prosodyFlat is not null
                          && prosodyFlat.Length == phonemeIds.Length * 3;

        var phrases = new List<Phrase>(8);
        var currentIds = new List<long>(Math.Max(10, phonemeIds.Length / 4));
        List<long>? currentProsody = hasProsody
            ? new List<long>(Math.Max(10, phonemeIds.Length * 3 / 4))
            : null;

        for (int i = 0; i < phonemeIds.Length; i++)
        {
            long id = phonemeIds[i];
            currentIds.Add(id);

            if (hasProsody)
            {
                int off = i * 3;
                currentProsody!.Add(prosodyFlat![off]);
                currentProsody.Add(prosodyFlat[off + 1]);
                currentProsody.Add(prosodyFlat[off + 2]);
            }

            if (silenceById.TryGetValue(id, out float seconds))
            {
                // Close the current phrase with the computed silence.
                int silenceSamples = (int)(seconds * sampleRate);

                phrases.Add(new Phrase(
                    currentIds,
                    currentProsody,
                    silenceSamples));

                // Start a new phrase.
                currentIds = new List<long>(Math.Max(10, phonemeIds.Length / 4));
                currentProsody = hasProsody
                    ? new List<long>(Math.Max(10, phonemeIds.Length * 3 / 4))
                    : null;
            }
        }

        // Trailing phrase (after the last split point, or all phonemes when
        // no split occurred).  Silence samples = 0.
        phrases.Add(new Phrase(currentIds, currentProsody, SilenceSamples: 0));

        return phrases;
    }

    // ------------------------------------------------------------------
    // Private helpers
    // ------------------------------------------------------------------

    /// <summary>
    /// Build a lookup from individual phoneme IDs to the silence duration
    /// in seconds that should follow them.
    /// </summary>
    private static Dictionary<long, float> BuildSilenceIdMap(
        Dictionary<string, float> phonemeSilence,
        Dictionary<string, int[]> phonemeIdMap)
    {
        var map = new Dictionary<long, float>();

        foreach (var (phoneme, seconds) in phonemeSilence)
        {
            if (!phonemeIdMap.TryGetValue(phoneme, out int[]? ids))
            {
                // The phoneme is not in the model's vocabulary — skip silently.
                // This matches C++ behaviour where unmapped phonemes are ignored.
                continue;
            }

            // Use the last ID of the phoneme's ID array as the split trigger.
            // Multi-ID phonemes (e.g. a phoneme mapped to [5, 6]) should only
            // trigger a split after the entire sequence has been emitted.
            if (ids.Length > 0)
            {
                map[(long)ids[^1]] = seconds;
            }
        }

        return map;
    }
}
