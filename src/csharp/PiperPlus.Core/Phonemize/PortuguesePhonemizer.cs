using System;
using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

// -----------------------------------------------------------------
// PortuguesePhonemizer
// -----------------------------------------------------------------

/// <summary>
/// Brazilian Portuguese phonemizer that mirrors the Python
/// <c>phonemize_portuguese_with_prosody()</c> function in
/// <c>piper_train/phonemize/portuguese.py</c>.
/// <para>
/// Processing flow (1:1 with the Python implementation):
/// <list type="number">
///   <item>Call <see cref="IPortugueseG2PEngine.ToPhonemeList"/> to get a flat IPA token list.</item>
///   <item>Split tokens by spaces and punctuation into words; for each word strip
///         <c>"ˈ"</c> stress markers, compute A3 (phoneme count excluding markers),
///         and assign A2=2 to the phoneme at the stress position.</item>
///   <item>Map multi-character tokens to PUA codepoints via
///         <see cref="PiperPhonemeConverter.MapSequence"/>.</item>
///   <item><see cref="PostProcessIds"/>: insert inter-phoneme PAD + BOS/EOS (same as English).</item>
/// </list>
/// </para>
/// </summary>
public sealed class PortuguesePhonemizer : IPhonemizer
{
    private readonly IPortugueseG2PEngine _engine;

    // Portuguese punctuation characters that appear as standalone tokens.
    // Mirrors Python _PUNCTUATION = set(",.;:!?¡¿—–…")
    private static readonly HashSet<string> Punctuation =
        [".", ",", ";", ":", "!", "?", "\u00a1", "\u00bf", "\u2014", "\u2013", "\u2026"]; // ¡ = U+00A1, ¿ = U+00BF, — = U+2014, – = U+2013, … = U+2026

    /// <summary>
    /// Create a new <see cref="PortuguesePhonemizer"/> backed by the given G2P engine.
    /// </summary>
    /// <param name="engine">
    /// Portuguese G2P engine that produces a flat IPA token list.
    /// </param>
    public PortuguesePhonemizer(IPortugueseG2PEngine engine)
    {
        _engine = engine ?? throw new ArgumentNullException(nameof(engine));
    }

    /// <inheritdoc />
    public List<string> Phonemize(string text)
    {
        var (tokens, _) = PhonemizeCore(text);
        return tokens;
    }

    /// <inheritdoc />
    public (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeWithProsody(string text)
    {
        return PhonemizeCore(text);
    }

    /// <inheritdoc />
    /// <remarks>
    /// Returns <c>null</c> --- Portuguese models use the phoneme-ID map from config.json.
    /// </remarks>
    public Dictionary<string, int[]>? GetPhonemeIdMap() => null;

    /// <inheritdoc />
    /// <remarks>
    /// Portuguese requires inter-phoneme padding and BOS/EOS wrapping
    /// (same pattern as English / espeak-ng compatible).
    /// <para>
    /// Transformation:
    /// <code>
    /// Input:  [10, 59, 24]
    /// PAD:    [10, 0, 59, 0, 24, 0]
    /// BOS/EOS: [BOS, 0, 10, 0, 59, 0, 24, 0, EOS]
    /// </code>
    /// </para>
    /// </remarks>
    public (List<int> Ids, List<ProsodyInfo?> Prosody) PostProcessIds(
        List<int> phonemeIds,
        List<ProsodyInfo?> prosodyFeatures,
        Dictionary<string, int[]> phonemeIdMap)
    {
        // Resolve special token IDs from the phoneme-ID map.
        int[] padIds = phonemeIdMap.TryGetValue("_", out int[]? padArr) ? padArr : [0];
        phonemeIdMap.TryGetValue("^", out int[]? bosIds);
        phonemeIdMap.TryGetValue("$", out int[]? eosIds);

        // Step 1: Insert PAD after every phoneme ID.
        var paddedIds = new List<int>(phonemeIds.Count * 2);
        var paddedProsody = new List<ProsodyInfo?>(phonemeIds.Count * 2);

        for (int i = 0; i < phonemeIds.Count; i++)
        {
            paddedIds.Add(phonemeIds[i]);
            paddedProsody.Add(prosodyFeatures[i]);

            // Only insert PAD if current phoneme is not already a pad token (matches Python base.py)
            if (Array.IndexOf(padIds, phonemeIds[i]) < 0)
            {
                paddedIds.AddRange(padIds);
                for (int j = 0; j < padIds.Length; j++)
                {
                    paddedProsody.Add(null);
                }
            }
        }

        // Step 2: Wrap with BOS + PAD ... EOS.
        if (bosIds is not null)
        {
            var withBos = new List<int>(bosIds.Length + 1 + paddedIds.Count);
            withBos.AddRange(bosIds);
            withBos.Add(padIds[0]);
            withBos.AddRange(paddedIds);

            var withBosProsody = new List<ProsodyInfo?>(bosIds.Length + 1 + paddedProsody.Count);
            for (int i = 0; i < bosIds.Length + 1; i++)
            {
                withBosProsody.Add(null);
            }
            withBosProsody.AddRange(paddedProsody);

            paddedIds = withBos;
            paddedProsody = withBosProsody;
        }

        if (eosIds is not null)
        {
            paddedIds.AddRange(eosIds);
            for (int i = 0; i < eosIds.Length; i++)
            {
                paddedProsody.Add(null);
            }
        }

        return (paddedIds, paddedProsody);
    }

    // -----------------------------------------------------------------
    // Core implementation
    // -----------------------------------------------------------------

    /// <summary>
    /// Shared implementation for both <see cref="Phonemize"/> and
    /// <see cref="PhonemizeWithProsody"/>. Follows the exact same
    /// algorithm as Python <c>phonemize_portuguese_with_prosody()</c>.
    /// </summary>
    private (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeCore(string text)
    {
        // Step 1: G2P --- text to flat IPA token list.
        List<string> rawTokens = _engine.ToPhonemeList(text);

        var tokens = new List<string>();
        var prosody = new List<ProsodyInfo?>();
        var currentWord = new List<string>();

        // Step 2: Split into words by space / punctuation, process each word.
        for (int i = 0; i < rawTokens.Count; i++)
        {
            string token = rawTokens[i];

            if (token == " ")
            {
                FlushWord(currentWord, tokens, prosody);
                tokens.Add(" ");
                prosody.Add(new ProsodyInfo(A1: 0, A2: 0, A3: 0));
                currentWord.Clear();
            }
            else if (IsPunctuation(token))
            {
                FlushWord(currentWord, tokens, prosody);
                tokens.Add(token);
                prosody.Add(new ProsodyInfo(A1: 0, A2: 0, A3: 0));
                currentWord.Clear();
            }
            else
            {
                currentWord.Add(token);
            }
        }

        // Flush any remaining word tokens.
        FlushWord(currentWord, tokens, prosody);

        // Step 3: Map multi-character tokens (tʃ, dʒ, etc.) to PUA codepoints.
        var mapped = PiperPhonemeConverter.MapSequence(tokens);

        var result = new List<string>(mapped.Count);
        for (int i = 0; i < mapped.Count; i++)
        {
            result.Add(mapped[i]);
        }

        return (result, prosody);
    }

    // -----------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------

    /// <summary>
    /// Flush accumulated word tokens into the output lists with prosody.
    /// The <c>"ˈ"</c> stress marker from the G2P engine is stripped from
    /// output (matching Python behavior where <c>_convert_word()</c>
    /// returns phonemes without markers). A3 is the phoneme count
    /// excluding stress markers. The phoneme at the stress position
    /// receives A2=2.
    /// </summary>
    private static void FlushWord(
        List<string> wordTokens,
        List<string> outTokens,
        List<ProsodyInfo?> outProsody)
    {
        if (wordTokens.Count == 0)
            return;

        // Find stress position from ˈ marker and build clean token list.
        int stressIdx = -1;
        var cleanTokens = new List<string>(wordTokens.Count);

        for (int j = 0; j < wordTokens.Count; j++)
        {
            if (wordTokens[j] == "\u02c8") // ˈ
            {
                // The next phoneme token is the stressed one.
                stressIdx = cleanTokens.Count;
            }
            else
            {
                cleanTokens.Add(wordTokens[j]);
            }
        }

        int phonemeCount = cleanTokens.Count;

        // Output without ˈ (matching Python behavior).
        for (int j = 0; j < cleanTokens.Count; j++)
        {
            int a2 = (j == stressIdx) ? 2 : 0;
            outTokens.Add(cleanTokens[j]);
            outProsody.Add(new ProsodyInfo(A1: 0, A2: a2, A3: phonemeCount));
        }
    }

    /// <summary>
    /// Check whether <paramref name="token"/> is a punctuation character.
    /// </summary>
    private static bool IsPunctuation(string token)
    {
        return Punctuation.Contains(token);
    }
}
