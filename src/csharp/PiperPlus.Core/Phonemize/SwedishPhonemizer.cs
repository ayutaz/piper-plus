using System;
using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

// -----------------------------------------------------------------
// SwedishPhonemizer
// -----------------------------------------------------------------

/// <summary>
/// Swedish phonemizer that mirrors the Python
/// <c>phonemize_swedish_with_prosody()</c> function in
/// <c>piper_train/phonemize/swedish.py</c>.
/// <para>
/// Processing flow (1:1 with the Python implementation):
/// <list type="number">
///   <item>Call <see cref="ISwedishG2PEngine.ToPhonemeList"/> to get a flat IPA token list.</item>
///   <item>Split tokens by spaces and punctuation into words; for each word compute
///         A3 (phoneme count excluding stress markers) and assign A2 stress values
///         (2=primary, 1=secondary, 0=none). A1 is always 0.</item>
///   <item>Map multi-character tokens (long vowels etc.) to PUA codepoints via
///         <see cref="PiperPhonemeConverter.MapSequence"/>.</item>
///   <item><see cref="PostProcessIds"/>: insert inter-phoneme PAD + BOS/EOS (same as English).</item>
/// </list>
/// </para>
/// </summary>
public sealed class SwedishPhonemizer : IPhonemizer
{
    private readonly ISwedishG2PEngine _engine;

    // Punctuation characters that appear as standalone tokens.
    // Matches Python PUNCTUATION = set(",.;:!?")
    private static readonly HashSet<string> Punctuation =
        [".", ",", ";", ":", "!", "?"];

    /// <summary>
    /// Create a new <see cref="SwedishPhonemizer"/> backed by the given G2P engine.
    /// </summary>
    /// <param name="engine">
    /// Swedish G2P engine that produces a flat IPA token list.
    /// </param>
    public SwedishPhonemizer(ISwedishG2PEngine engine)
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
    /// Returns <c>null</c> --- Swedish models use the phoneme-ID map from config.json.
    /// </remarks>
    public Dictionary<string, int[]>? GetPhonemeIdMap() => null;

    /// <inheritdoc />
    /// <remarks>
    /// Swedish requires inter-phoneme padding and BOS/EOS wrapping
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
    /// algorithm as Python <c>phonemize_swedish_with_prosody()</c>.
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

        // Step 3: Map multi-character tokens (long vowels, etc.) to PUA codepoints.
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
    /// <para>
    /// Mirrors Python <c>phonemize_swedish_with_prosody()</c> logic:
    /// <list type="bullet">
    ///   <item>A1 = 0 (always)</item>
    ///   <item>A2 = 2 for primary stress marker <c>"\u02C8"</c>,
    ///         1 for secondary stress marker <c>"\u02CC"</c>,
    ///         0 otherwise</item>
    ///   <item>A3 = word phoneme count (excluding stress markers)</item>
    /// </list>
    /// </para>
    /// </summary>
    private static void FlushWord(
        List<string> wordTokens,
        List<string> outTokens,
        List<ProsodyInfo?> outProsody)
    {
        if (wordTokens.Count == 0)
            return;

        // A3 = phoneme count excluding stress markers "ˈ" (U+02C8) and "ˌ" (U+02CC).
        int phonemeCount = 0;
        for (int i = 0; i < wordTokens.Count; i++)
        {
            if (wordTokens[i] != "\u02C8" && wordTokens[i] != "\u02CC")
                phonemeCount++;
        }

        for (int i = 0; i < wordTokens.Count; i++)
        {
            string token = wordTokens[i];

            if (token == "\u02C8") // ˈ primary stress
            {
                outTokens.Add("\u02C8");
                outProsody.Add(new ProsodyInfo(A1: 0, A2: 2, A3: phonemeCount));
            }
            else if (token == "\u02CC") // ˌ secondary stress
            {
                outTokens.Add("\u02CC");
                outProsody.Add(new ProsodyInfo(A1: 0, A2: 1, A3: phonemeCount));
            }
            else
            {
                outTokens.Add(token);
                outProsody.Add(new ProsodyInfo(A1: 0, A2: 0, A3: phonemeCount));
            }
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
