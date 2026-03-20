using System;
using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

// -----------------------------------------------------------------
// SpanishPhonemizer
// -----------------------------------------------------------------

/// <summary>
/// Spanish phonemizer that mirrors the Python
/// <c>phonemize_spanish_with_prosody()</c> function in
/// <c>piper_train/phonemize/spanish.py</c>.
/// <para>
/// Processing flow (1:1 with the Python implementation):
/// <list type="number">
///   <item>Call <see cref="ISpanishG2PEngine.ToPhonemeList"/> to get a flat IPA token list.</item>
///   <item>Split tokens by spaces and punctuation into words; for each word compute
///         A3 (phoneme count excluding stress markers) and assign A2 stress values.</item>
///   <item>Map multi-character tokens to PUA codepoints via
///         <see cref="PiperPhonemeConverter.MapSequence"/>.</item>
///   <item><see cref="PostProcessIds"/>: insert inter-phoneme PAD + BOS/EOS (same as English).</item>
/// </list>
/// </para>
/// </summary>
public sealed class SpanishPhonemizer : IPhonemizer
{
    private readonly ISpanishG2PEngine _engine;

    // Spanish vowels (monophthongs only, matching Python _VOWELS).
    private static readonly HashSet<string> Vowels = ["a", "e", "i", "o", "u"];

    // Punctuation characters that appear as standalone tokens.
    private static readonly HashSet<string> Punctuation =
        [".", ",", ";", ":", "!", "?", "\u00bf", "\u00a1"]; // ¿ = U+00BF, ¡ = U+00A1

    /// <summary>
    /// Create a new <see cref="SpanishPhonemizer"/> backed by the given G2P engine.
    /// </summary>
    /// <param name="engine">
    /// Spanish G2P engine that produces a flat IPA token list.
    /// </param>
    public SpanishPhonemizer(ISpanishG2PEngine engine)
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
    /// Returns <c>null</c> --- Spanish models use the phoneme-ID map from config.json.
    /// </remarks>
    public Dictionary<string, int[]>? GetPhonemeIdMap() => null;

    /// <inheritdoc />
    /// <remarks>
    /// Spanish requires inter-phoneme padding and BOS/EOS wrapping
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
    /// algorithm as Python <c>phonemize_spanish_with_prosody()</c>.
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

        // Step 3: Map multi-character tokens (rr, tʃ, etc.) to PUA codepoints.
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
    /// A3 is the phoneme count excluding stress markers (<c>"ˈ"</c>).
    /// The stress marker itself and the vowel immediately following it
    /// both receive A2=2.
    /// </summary>
    private static void FlushWord(
        List<string> wordTokens,
        List<string> outTokens,
        List<ProsodyInfo?> outProsody)
    {
        if (wordTokens.Count == 0)
            return;

        // A3 = phoneme count excluding the stress marker "ˈ".
        int phonemeCount = 0;
        for (int i = 0; i < wordTokens.Count; i++)
        {
            if (wordTokens[i] != "\u02c8")
                phonemeCount++;
        }

        for (int i = 0; i < wordTokens.Count; i++)
        {
            string token = wordTokens[i];

            if (token == "\u02c8") // ˈ
            {
                outTokens.Add("\u02c8");
                outProsody.Add(new ProsodyInfo(A1: 0, A2: 2, A3: phonemeCount));
            }
            else
            {
                // Vowel immediately after ˈ also gets A2=2.
                bool isStressedVowel = outTokens.Count > 0
                    && outTokens[^1] == "\u02c8"
                    && IsVowel(token);
                int a2 = isStressedVowel ? 2 : 0;

                outTokens.Add(token);
                outProsody.Add(new ProsodyInfo(A1: 0, A2: a2, A3: phonemeCount));
            }
        }
    }

    /// <summary>
    /// Check whether <paramref name="token"/> is a Spanish vowel (a, e, i, o, u).
    /// </summary>
    private static bool IsVowel(string token)
    {
        return Vowels.Contains(token);
    }

    /// <summary>
    /// Check whether <paramref name="token"/> is a punctuation character.
    /// </summary>
    private static bool IsPunctuation(string token)
    {
        return Punctuation.Contains(token);
    }
}
