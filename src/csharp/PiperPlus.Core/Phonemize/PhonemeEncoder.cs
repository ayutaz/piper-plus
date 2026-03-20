using System;
using System.Collections.Generic;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Converts text to phoneme IDs and prosody features suitable for ONNX inference.
/// <para>
/// Mirrors the Python <c>text_to_phoneme_ids_and_prosody()</c> function in
/// <c>piper_train/infer_onnx.py</c>:
/// <list type="number">
///   <item>Phonemize text via <see cref="IPhonemizer.PhonemizeWithProsody"/>.</item>
///   <item>Map each phoneme token to integer IDs using the phoneme-ID map.</item>
///   <item>Apply language-specific post-processing via <see cref="IPhonemizer.PostProcessIds"/>.</item>
/// </list>
/// </para>
/// </summary>
public static class PhonemeEncoder
{
    private static ILogger s_logger = NullLogger.Instance;

    /// <summary>
    /// Replace the default (no-op) logger used for unknown-phoneme warnings.
    /// Call once at application startup; not required for correct operation.
    /// </summary>
    public static void SetLogger(ILogger logger)
    {
        s_logger = logger ?? NullLogger.Instance;
    }

    /// <summary>
    /// Convert <paramref name="text"/> to a list of phoneme IDs and per-ID prosody
    /// features using the given <paramref name="phonemizer"/> and
    /// <paramref name="phonemeIdMap"/>.
    /// </summary>
    /// <param name="phonemizer">Language-specific phonemizer implementation.</param>
    /// <param name="text">Input text to phonemize.</param>
    /// <param name="phonemeIdMap">
    /// Mapping from phoneme token strings to integer ID arrays
    /// (typically sourced from <c>config.json</c>).
    /// </param>
    /// <returns>
    /// A tuple of phoneme IDs and corresponding prosody features.
    /// Each entry in <c>ProsodyFeatures</c> may be <c>null</c> when prosody
    /// information is unavailable for that position.
    /// </returns>
    public static (List<int> PhonemeIds, List<ProsodyInfo?> ProsodyFeatures) Encode(
        IPhonemizer phonemizer,
        string text,
        Dictionary<string, int[]> phonemeIdMap)
    {
        ArgumentNullException.ThrowIfNull(phonemizer);
        ArgumentNullException.ThrowIfNull(text);
        ArgumentNullException.ThrowIfNull(phonemeIdMap);

        // Step 1: Phonemize text into tokens + prosody.
        var (tokens, prosodyList) = phonemizer.PhonemizeWithProsody(text);

        // Step 2: Map tokens to IDs, duplicating prosody for multi-ID tokens.
        var phonemeIds = new List<int>(tokens.Count * 2);
        var prosodyFeatures = new List<ProsodyInfo?>(tokens.Count * 2);

        for (int i = 0; i < tokens.Count; i++)
        {
            string token = tokens[i];
            ProsodyInfo? prosody = prosodyList[i];

            if (phonemeIdMap.TryGetValue(token, out int[]? ids))
            {
                phonemeIds.AddRange(ids);
                for (int j = 0; j < ids.Length; j++)
                {
                    prosodyFeatures.Add(prosody);
                }
            }
            else
            {
                s_logger.LogWarning("Unknown phoneme: {Phoneme}", token);
            }
        }

        // Step 3: Language-specific post-processing (BOS/EOS/padding).
        return phonemizer.PostProcessIds(phonemeIds, prosodyFeatures, phonemeIdMap);
    }

    /// <summary>
    /// Convert <paramref name="text"/> to ONNX-ready tensors: a <c>long[]</c> of
    /// phoneme IDs and an optional flat <c>long[]</c> of prosody features.
    /// <para>
    /// This is a convenience wrapper around <see cref="Encode"/> that produces
    /// arrays directly consumable by <see cref="Inference.SynthesisInput"/>:
    /// <list type="bullet">
    ///   <item><c>PhonemeIds</c>: each <c>int</c> widened to <c>long</c>.</item>
    ///   <item>
    ///     <c>ProsodyFlat</c>: interleaved <c>[a1_0, a2_0, a3_0, a1_1, a2_1, a3_1, ...]</c>.
    ///     Positions where prosody is <c>null</c> are filled with <c>[0, 0, 0]</c>.
    ///     Returns <c>null</c> when <b>all</b> prosody entries are <c>null</c>.
    ///   </item>
    /// </list>
    /// </para>
    /// </summary>
    /// <param name="phonemizer">Language-specific phonemizer implementation.</param>
    /// <param name="text">Input text to phonemize.</param>
    /// <param name="phonemeIdMap">
    /// Mapping from phoneme token strings to integer ID arrays
    /// (typically sourced from <c>config.json</c>).
    /// </param>
    /// <returns>
    /// A tuple of <c>long[]</c> phoneme IDs and an optional flat <c>long[]</c>
    /// prosody array (layout: <c>[a1_0, a2_0, a3_0, a1_1, ...]</c>).
    /// </returns>
    public static (long[] PhonemeIds, long[]? ProsodyFlat) EncodeDirect(
        IPhonemizer phonemizer,
        string text,
        Dictionary<string, int[]> phonemeIdMap)
    {
        var (ids, prosody) = Encode(phonemizer, text, phonemeIdMap);

        // Convert int IDs to long for ONNX tensor compatibility.
        var phonemeIdsLong = new long[ids.Count];
        for (int i = 0; i < ids.Count; i++)
        {
            phonemeIdsLong[i] = ids[i];
        }

        // Build flat prosody array: [a1_0, a2_0, a3_0, a1_1, a2_1, a3_1, ...].
        // Return null if every entry is null (no prosody data at all).
        bool hasAnyProsody = false;
        for (int i = 0; i < prosody.Count; i++)
        {
            if (prosody[i] is not null)
            {
                hasAnyProsody = true;
                break;
            }
        }

        if (!hasAnyProsody)
        {
            return (phonemeIdsLong, null);
        }

        var flat = new long[prosody.Count * 3];
        for (int i = 0; i < prosody.Count; i++)
        {
            int offset = i * 3;
            if (prosody[i] is { } p)
            {
                flat[offset] = p.A1;
                flat[offset + 1] = p.A2;
                flat[offset + 2] = p.A3;
            }
            // null entries remain [0, 0, 0] (default long[] initialization).
        }

        return (phonemeIdsLong, flat);
    }
}
