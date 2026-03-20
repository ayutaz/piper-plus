using System;
using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

// -----------------------------------------------------------------
// FrenchPhonemizer
// -----------------------------------------------------------------

/// <summary>
/// French phonemizer that mirrors the Python
/// <c>phonemize_french_with_prosody()</c> function in
/// <c>piper_train/phonemize/french.py</c>.
/// <para>
/// Processing flow (1:1 with the Python implementation):
/// <list type="number">
///   <item>Call <see cref="IFrenchG2PEngine.ToPhonemeList"/> to get a flat IPA token list.</item>
///   <item>Split tokens by spaces and punctuation into words; for each word compute
///         A3 (phoneme count) and assign A2 stress on the last vowel.</item>
///   <item>Map multi-character tokens to PUA codepoints via
///         <see cref="PiperPhonemeConverter.MapSequence"/>.</item>
///   <item><see cref="PostProcessIds"/>: insert inter-phoneme PAD + BOS/EOS (same as English).</item>
/// </list>
/// </para>
/// </summary>
public sealed class FrenchPhonemizer : IPhonemizer
{
    private readonly IFrenchG2PEngine _engine;

    // French vowels for stress detection (matching Python vowel_phonemes set).
    // Includes oral vowels, nasal vowels (decomposed: base + U+0303), and y_vowel.
    private static readonly HashSet<string> s_vowels = new()
    {
        "a", "e", "\u025b", "i", "o", "\u0254", "u", "y_vowel", "\u0259", "\u00f8", "\u0153",
        "\u025b\u0303", // ɛ̃  (nasal)
        "\u0251\u0303", // ɑ̃  (nasal)
        "\u0254\u0303"  // ɔ̃  (nasal)
    };

    // Punctuation characters that appear as standalone tokens.
    // Matches Python _PUNCTUATION: . , ; : ! ? « » — – …
    private static readonly HashSet<string> s_punctuation = new()
    {
        ".", ",", ";", ":", "!", "?",
        "\u00a1", // ¡
        "\u00bf", // ¿
        "\u00ab", // «
        "\u00bb", // »
        "\u2014", // —
        "\u2013", // –
        "\u2026"  // …
    };

    /// <summary>
    /// Create a new <see cref="FrenchPhonemizer"/> backed by the given G2P engine.
    /// </summary>
    /// <param name="engine">
    /// French G2P engine that produces a flat IPA token list.
    /// </param>
    public FrenchPhonemizer(IFrenchG2PEngine engine)
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
    /// Returns <c>null</c> --- French models use the phoneme-ID map from config.json.
    /// </remarks>
    public Dictionary<string, int[]>? GetPhonemeIdMap() => null;

    /// <inheritdoc />
    /// <remarks>
    /// French requires inter-phoneme padding and BOS/EOS wrapping
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
        return PiperPhonemeConverter.EspeakPostProcessIds(phonemeIds, prosodyFeatures, phonemeIdMap);
    }

    // -----------------------------------------------------------------
    // Core implementation
    // -----------------------------------------------------------------

    /// <summary>
    /// Shared implementation for both <see cref="Phonemize"/> and
    /// <see cref="PhonemizeWithProsody"/>. Follows the exact same
    /// algorithm as Python <c>phonemize_french_with_prosody()</c>.
    /// </summary>
    private (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeCore(string text)
    {
        // Step 1: G2P --- text to flat IPA token list.
        List<string> rawTokens = _engine.ToPhonemeList(text);

        var tokens = new List<string>(rawTokens.Count * 2);
        var prosody = new List<ProsodyInfo?>(rawTokens.Count * 2);
        var currentWord = new List<string>(10);

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

        // Step 3: Map multi-character tokens (nasal vowels, y_vowel, etc.) to PUA codepoints.
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
    /// French has fixed stress on the last syllable --- the last vowel
    /// phoneme in each word receives A2=2; all other phonemes get A2=0.
    /// A3 is the total phoneme count for the word.
    /// No stress marker (<c>"ˈ"</c>) is emitted (matching Python).
    /// </summary>
    private static void FlushWord(
        List<string> wordTokens,
        List<string> outTokens,
        List<ProsodyInfo?> outProsody)
    {
        if (wordTokens.Count == 0)
            return;

        int phonemeCount = wordTokens.Count;

        // French: stress always on last syllable (last vowel phoneme).
        int lastVowelIdx = -1;
        for (int j = wordTokens.Count - 1; j >= 0; j--)
        {
            if (IsVowel(wordTokens[j]))
            {
                lastVowelIdx = j;
                break;
            }
        }

        for (int j = 0; j < wordTokens.Count; j++)
        {
            int a2 = (j == lastVowelIdx) ? 2 : 0;
            outTokens.Add(wordTokens[j]);
            outProsody.Add(new ProsodyInfo(A1: 0, A2: a2, A3: phonemeCount));
        }
    }

    /// <summary>
    /// Check whether <paramref name="token"/> is a French vowel
    /// (oral or nasal, including <c>y_vowel</c>).
    /// </summary>
    private static bool IsVowel(string token)
    {
        return s_vowels.Contains(token);
    }

    /// <summary>
    /// Check whether <paramref name="token"/> is a punctuation character.
    /// </summary>
    private static bool IsPunctuation(string token)
    {
        return s_punctuation.Contains(token);
    }
}
