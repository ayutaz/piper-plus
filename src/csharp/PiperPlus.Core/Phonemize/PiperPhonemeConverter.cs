using PiperPlus.Core.Mapping;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Static helper methods for the Piper phoneme pipeline:
/// question-type detection, context-dependent N-phoneme mutation,
/// and PUA token mapping.
/// <para>
/// These three methods correspond to the Python functions
/// <c>_get_question_type</c>, <c>_apply_n_phoneme_rules</c>,
/// and <c>map_sequence</c> in <c>japanese.py</c> / <c>token_mapper.py</c>.
/// </para>
/// </summary>
public static class PiperPhonemeConverter
{
    // -----------------------------------------------------------------
    // Skip tokens: ignored when searching for the next real phoneme
    // after an "N" token.  Mirrors Python _SKIP_TOKENS.
    // -----------------------------------------------------------------
    private static readonly HashSet<string> SkipTokens =
        ["_", "#", "[", "]", "^", "$", "?", "?!", "?.", "?~"];

    // -----------------------------------------------------------------
    // N-variant look-up sets.  Mirrors the Python if/elif chain.
    // -----------------------------------------------------------------
    private static readonly HashSet<string> BilabialPhonemes =
        ["m", "my", "b", "by", "p", "py"];

    private static readonly HashSet<string> AlveolarPhonemes =
        ["n", "ny", "t", "ty", "d", "dy", "ts", "ch"];

    private static readonly HashSet<string> VelarPhonemes =
        ["k", "ky", "kw", "g", "gy", "gw"];

    // -----------------------------------------------------------------
    // GetQuestionType
    // -----------------------------------------------------------------

    /// <summary>
    /// Determine the question-type marker for the given text based on
    /// its trailing punctuation.
    /// </summary>
    /// <param name="text">Input text (may contain trailing whitespace).</param>
    /// <returns>
    /// One of <c>"?!"</c>, <c>"?."</c>, <c>"?~"</c>, <c>"?"</c>, or
    /// <c>"$"</c> (non-question).
    /// </returns>
    public static string GetQuestionType(string text)
    {
        var stripped = text.AsSpan().Trim();

        // Multi-char patterns first (longer before shorter)
        if (EndsWith(stripped, "?!") || EndsWith(stripped, "\uFF01\uFF1F") || EndsWith(stripped, "\uFF1F\uFF01"))
            return "?!";

        if (EndsWith(stripped, "?.") || EndsWith(stripped, "\u3002\uFF1F") || EndsWith(stripped, "\uFF1F\u3002"))
            return "?.";

        if (EndsWith(stripped, "?~") || EndsWith(stripped, "\uFF5E\uFF1F") || EndsWith(stripped, "\uFF1F\uFF5E"))
            return "?~";

        // Single ? fallback
        if (stripped.Length > 0 && (stripped[^1] == '?' || stripped[^1] == '\uFF1F'))
            return "?";

        return "$";
    }

    // -----------------------------------------------------------------
    // ApplyNPhonemeRules
    // -----------------------------------------------------------------

    /// <summary>
    /// Replace every <c>"N"</c> token in <paramref name="tokens"/> with a
    /// context-dependent variant (<c>N_m</c>, <c>N_n</c>, <c>N_ng</c>,
    /// or <c>N_uvular</c>) based on the following phoneme.
    /// </summary>
    /// <param name="tokens">
    /// Mutable list of phoneme tokens (before PUA mapping).
    /// </param>
    /// <returns>A new list with N tokens replaced.</returns>
    public static List<string> ApplyNPhonemeRules(List<string> tokens)
    {
        var result = new List<string>(tokens.Count);

        for (var i = 0; i < tokens.Count; i++)
        {
            if (tokens[i] != "N")
            {
                result.Add(tokens[i]);
                continue;
            }

            // Look ahead past skip tokens to find the next real phoneme.
            string? nextPhoneme = null;
            for (var j = i + 1; j < tokens.Count; j++)
            {
                if (!SkipTokens.Contains(tokens[j]))
                {
                    nextPhoneme = tokens[j];
                    break;
                }
            }

            // Determine N variant based on following phoneme.
            if (nextPhoneme is null)
            {
                result.Add("N_uvular");   // End of phrase
            }
            else if (BilabialPhonemes.Contains(nextPhoneme))
            {
                result.Add("N_m");        // Bilabial
            }
            else if (AlveolarPhonemes.Contains(nextPhoneme))
            {
                result.Add("N_n");        // Alveolar
            }
            else if (VelarPhonemes.Contains(nextPhoneme))
            {
                result.Add("N_ng");       // Velar
            }
            else
            {
                result.Add("N_uvular");   // Vowels, other consonants
            }
        }

        return result;
    }

    // -----------------------------------------------------------------
    // MapSequence
    // -----------------------------------------------------------------

    /// <summary>
    /// Convert multi-character phoneme tokens to single PUA codepoints
    /// via <see cref="OpenJTalkToPiperMapping.MapSequence"/>.
    /// </summary>
    /// <param name="tokens">Phoneme tokens to map.</param>
    /// <returns>Mapped token list (each element is a single codepoint string).</returns>
    public static IReadOnlyList<string> MapSequence(List<string> tokens)
    {
        return OpenJTalkToPiperMapping.MapSequence(tokens);
    }

    // -----------------------------------------------------------------
    // EspeakPostProcessIds
    // -----------------------------------------------------------------

    /// <summary>
    /// Shared espeak-ng compatible PostProcessIds used by English, Chinese,
    /// Spanish, French, and Portuguese phonemizers.
    /// Inserts inter-phoneme padding and wraps with BOS/EOS.
    /// <para>
    /// Transformation:
    /// <code>
    /// Input:  [10, 59, 24]
    /// PAD:    [10, 0, 59, 0, 24, 0]
    /// BOS/EOS: [BOS, 0, 10, 0, 59, 0, 24, 0, EOS]
    /// </code>
    /// </para>
    /// </summary>
    /// <param name="phonemeIds">Raw phoneme IDs before padding.</param>
    /// <param name="prosodyFeatures">Prosody info aligned 1:1 with <paramref name="phonemeIds"/>.</param>
    /// <param name="phonemeIdMap">ID map from config.json (must contain <c>"_"</c> for PAD).</param>
    /// <returns>Padded IDs and prosody with BOS/EOS wrapper.</returns>
    public static (List<int> Ids, List<ProsodyInfo?> Prosody) EspeakPostProcessIds(
        List<int> phonemeIds,
        List<ProsodyInfo?> prosodyFeatures,
        Dictionary<string, int[]> phonemeIdMap)
    {
        // Resolve special token IDs from the phoneme-ID map.
        int[] padIds = phonemeIdMap.TryGetValue("_", out int[]? padArr) ? padArr : [0];
        phonemeIdMap.TryGetValue("^", out int[]? bosIds);
        phonemeIdMap.TryGetValue("$", out int[]? eosIds);

        // Calculate capacity upfront for a single allocation.
        int bosLen = bosIds?.Length ?? 0;
        int eosLen = eosIds?.Length ?? 0;
        // BOS ids + PAD(0) + (phoneme + PAD) per phoneme + EOS ids
        int capacity = bosLen + 1 + phonemeIds.Count * (1 + padIds.Length) + eosLen;

        var ids = new List<int>(capacity);
        var prosody = new List<ProsodyInfo?>(capacity);

        // Single-pass PAD check: use simple != for single-element padIds.
        bool singlePad = padIds.Length == 1;
        int singlePadVal = singlePad ? padIds[0] : 0;

        // Add BOS ids + PAD(0).
        if (bosIds is not null)
        {
            ids.AddRange(bosIds);
            ids.Add(padIds[0]);
            for (int i = 0; i < bosIds.Length + 1; i++)
            {
                prosody.Add(null);
            }
        }

        // Add each phoneme + inter-phoneme PAD.
        for (int i = 0; i < phonemeIds.Count; i++)
        {
            int phoneme = phonemeIds[i];
            ids.Add(phoneme);
            prosody.Add(prosodyFeatures[i]);

            // Only insert PAD if current phoneme is not already a pad token (matches Python base.py)
            bool isPad = singlePad ? phoneme == singlePadVal : Array.IndexOf(padIds, phoneme) >= 0;
            if (!isPad)
            {
                ids.AddRange(padIds);
                for (int j = 0; j < padIds.Length; j++)
                {
                    prosody.Add(null);
                }
            }
        }

        // Add EOS ids.
        if (eosIds is not null)
        {
            ids.AddRange(eosIds);
            for (int i = 0; i < eosIds.Length; i++)
            {
                prosody.Add(null);
            }
        }

        return (ids, prosody);
    }

    // -----------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------

    /// <summary>
    /// Check whether <paramref name="span"/> ends with the characters
    /// of <paramref name="suffix"/>.  Ordinal comparison.
    /// </summary>
    private static bool EndsWith(ReadOnlySpan<char> span, string suffix)
    {
        return span.EndsWith(suffix.AsSpan(), StringComparison.Ordinal);
    }
}
