using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using PiperPlus.Core.Mapping;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Parses raw phoneme strings (from <c>--raw-phonemes</c> mode) into phoneme IDs
/// using the model's <c>phoneme_id_map</c>.
/// <para>
/// Input format: space-separated phoneme tokens, e.g. <c>"^ k o N_m p o $"</c>.
/// Supports both single-character tokens (looked up directly in the map) and
/// multi-character tokens such as PUA names (<c>a:</c>, <c>N_m</c>, etc.) which
/// are resolved via <see cref="OpenJTalkToPiperMapping"/>.
/// </para>
/// <para>
/// Mirrors the C++ <c>parsePhonemeString()</c> in <c>phoneme_parser.cpp</c>
/// combined with <c>phonemes_to_ids()</c> in <c>phoneme_ids.cpp</c>.
/// </para>
/// </summary>
public static class RawPhonemeParser
{
    private static ILogger s_logger = NullLogger.Instance;

    /// <summary>
    /// Replace the default (no-op) logger used for unknown-token warnings.
    /// Call once at application startup; not required for correct operation.
    /// </summary>
    public static void SetLogger(ILogger logger)
    {
        s_logger = logger ?? NullLogger.Instance;
    }

    /// <summary>
    /// Convert a space-separated phoneme string to an array of phoneme IDs.
    /// <para>
    /// Resolution order for each token:
    /// <list type="number">
    ///   <item>Direct lookup in <paramref name="phonemeIdMap"/> (handles single-char
    ///         tokens and pre-mapped PUA characters).</item>
    ///   <item>PUA mapping via <see cref="OpenJTalkToPiperMapping.TokenToChar"/>
    ///         (handles multi-character names such as <c>"a:"</c> or <c>"N_ng"</c>).</item>
    ///   <item>If neither resolves, the token is skipped with a warning log.</item>
    /// </list>
    /// </para>
    /// </summary>
    /// <param name="phonemeString">
    /// Space-separated phoneme tokens.
    /// May be empty or <c>null</c>, in which case an empty array is returned.
    /// </param>
    /// <param name="phonemeIdMap">
    /// Mapping from phoneme token strings to integer ID arrays, typically from
    /// <c>config.json</c>.
    /// </param>
    /// <returns>Flat array of phoneme IDs suitable for ONNX inference input.</returns>
    public static long[] Parse(string? phonemeString, Dictionary<string, int[]> phonemeIdMap)
    {
        ArgumentNullException.ThrowIfNull(phonemeIdMap);

        if (string.IsNullOrWhiteSpace(phonemeString))
        {
            return [];
        }

        var tokens = phonemeString.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        // Estimate: each space-separated token maps to ~1-2 IDs
        var result = new List<long>(tokens.Length * 2);

        foreach (var token in tokens)
        {
            // 1. Direct lookup -- covers single-char phonemes ("a", "k", "^", "$", etc.)
            //    and pre-encoded PUA characters ("\uE000" etc.) passed directly.
            if (phonemeIdMap.TryGetValue(token, out var ids))
            {
                foreach (var id in ids)
                {
                    result.Add(id);
                }
                continue;
            }

            // 2. Multi-char token -> PUA mapping (e.g. "a:" -> '\uE000', "N_m" -> '\uE019')
            //    MapToken returns a cached string (no allocation) when the token is known.
            var mapped = OpenJTalkToPiperMapping.MapToken(token);
            if (!ReferenceEquals(mapped, token) && phonemeIdMap.TryGetValue(mapped, out var puaIds))
            {
                foreach (var id in puaIds)
                {
                    result.Add(id);
                }
                continue;
            }

            // 3. Unknown token -- warn and skip.
            s_logger.LogWarning("Raw phoneme parser: unknown token '{Token}' (skipped)", token);
        }

        return result.ToArray();
    }
}
