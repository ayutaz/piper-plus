using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace PiperPlus.Core.Phonemize;

// -----------------------------------------------------------------
// G2P abstraction layer — allows the G2P engine to be swapped / mocked.
// -----------------------------------------------------------------

/// <summary>
/// Abstraction over an English G2P engine (e.g. g2p-en, DotNetG2P.English).
/// <para>
/// The engine converts raw text into per-word ARPAbet token sequences.
/// Whitespace acts as a word boundary; punctuation characters appear as
/// standalone single-element "words".
/// </para>
/// </summary>
public interface IEnglishG2PEngine
{
    /// <summary>
    /// Convert <paramref name="text"/> to ARPAbet tokens grouped by word.
    /// </summary>
    /// <param name="text">Input English text.</param>
    /// <returns>
    /// A list of words, each word being a list of ARPAbet tokens.
    /// Spaces are consumed as word boundaries. Punctuation-only groups
    /// are kept as separate "words".
    /// </returns>
    List<List<string>> ConvertToArpabet(string text);
}

// -----------------------------------------------------------------
// EnglishPhonemizer
// -----------------------------------------------------------------

/// <summary>
/// English phonemizer that mirrors the Python
/// <c>phonemize_english_with_prosody()</c> / <c>phonemize_english()</c>
/// functions in <c>piper_train/phonemize/english.py</c>.
/// <para>
/// Processing flow (1:1 with the Python implementation):
/// <list type="number">
///   <item>Call <see cref="IEnglishG2PEngine.ConvertToArpabet"/> to get per-word ARPAbet.</item>
///   <item>Extract source words from original text for function-word detection.</item>
///   <item>For each word: apply function-word stress removal, convert to IPA via
///         <see cref="ArpabetToIPAConverter.ConvertWord"/>, insert stress markers,
///         and emit individual phoneme tokens with prosody.</item>
///   <item><see cref="PostProcessIds"/>: insert inter-phoneme PAD + BOS/EOS (English only).</item>
/// </list>
/// </para>
/// </summary>
public sealed partial class EnglishPhonemizer : IPhonemizer
{
    private readonly IEnglishG2PEngine _engine;

    // Regex to extract alphabetic words (including apostrophes) from text.
    // Mirrors Python: re.findall(r"[a-zA-Z']+", text.lower())
    [GeneratedRegex(@"[a-zA-Z']+")]
    private static partial Regex SourceWordRegex();

    // Cache single-char strings for IPA characters (covers ASCII + IPA Extensions)
    private static readonly string[] s_charStrings = InitCharStrings();
    private static string[] InitCharStrings()
    {
        var arr = new string[0x0300];
        for (int i = 0; i < arr.Length; i++)
            arr[i] = ((char)i).ToString();
        return arr;
    }

    /// <summary>
    /// Create a new <see cref="EnglishPhonemizer"/> backed by the given G2P engine.
    /// </summary>
    /// <param name="engine">
    /// English G2P engine that produces per-word ARPAbet token sequences.
    /// </param>
    public EnglishPhonemizer(IEnglishG2PEngine engine)
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
    /// Returns <c>null</c> --- English models use the phoneme-ID map from config.json.
    /// </remarks>
    public Dictionary<string, int[]>? GetPhonemeIdMap() => null;

    /// <inheritdoc />
    /// <remarks>
    /// English requires inter-phoneme padding and BOS/EOS wrapping
    /// (espeak-ng compatible). This mirrors the Python
    /// <c>EnglishPhonemizer.post_process_ids()</c>.
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
    /// algorithm as Python <c>phonemize_english_with_prosody()</c>.
    /// </summary>
    private (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeCore(string text)
    {
        // Step 1: G2P — text to per-word ARPAbet tokens.
        List<List<string>> words = _engine.ConvertToArpabet(text);

        // Step 2: Extract source words for function-word detection.
        // Mirrors Python: re.findall(r"[a-zA-Z']+", text.lower())
        List<string> sourceWords = GetSourceWords(text);

        var phonemes = new List<string>(sourceWords.Count * 3);
        var prosodyList = new List<ProsodyInfo?>(sourceWords.Count * 3);

        // Step 3: Build function-word flags for each word group.
        // Non-punctuation words are matched to source words in order.
        int srcIdx = 0;
        var wordIsFunction = new bool[words.Count];

        for (int w = 0; w < words.Count; w++)
        {
            if (IsPunctuationWord(words[w]))
            {
                wordIsFunction[w] = false;
            }
            else
            {
                bool isFunc = false;
                if (srcIdx < sourceWords.Count)
                {
                    isFunc = ArpabetToIPAConverter.IsFunctionWord(sourceWords[srcIdx]);
                    srcIdx++;
                }
                wordIsFunction[w] = isFunc;
            }
        }

        // Step 4: Process each word.
        bool needSpace = false;

        for (int wordIdx = 0; wordIdx < words.Count; wordIdx++)
        {
            var wordTokens = words[wordIdx];
            bool isPunct = IsPunctuationWord(wordTokens);
            bool isFunc = wordIsFunction[wordIdx];

            // Punctuation attaches to previous word (no space before).
            // Regular words get a space before them (except the first).
            if (!isPunct && needSpace)
            {
                phonemes.Add(" ");
                prosodyList.Add(new ProsodyInfo(A1: 0, A2: 0, A3: 0));
            }

            // Convert all tokens in the word to IPA (with context-dependent rules).
            List<(string Ipa, int Stress)> wordIpas = ArpabetToIPAConverter.ConvertWord(wordTokens);

            // Function words: remove primary/secondary stress (stress >= 1 → 0).
            if (isFunc)
            {
                for (int i = 0; i < wordIpas.Count; i++)
                {
                    var (ipa, stress) = wordIpas[i];
                    if (stress >= 1)
                    {
                        wordIpas[i] = (ipa, 0);
                    }
                }
            }

            // A3 = total IPA character count for the word (actual phoneme tokens).
            int wordPhonemeCount = 0;
            for (int i = 0; i < wordIpas.Count; i++)
            {
                wordPhonemeCount += wordIpas[i].Ipa.Length;
            }

            // Emit phoneme tokens with prosody.
            for (int i = 0; i < wordIpas.Count; i++)
            {
                var (ipa, stress) = wordIpas[i];

                // stress → A2: primary(1)→2, secondary(2)→1, none(0)→0, consonant(-1)→0
                int a2;
                if (stress == 1)
                    a2 = 2;
                else if (stress == 2)
                    a2 = 1;
                else
                    a2 = 0;

                // Insert stress marker before stressed vowels (espeak-ng compatible).
                if (stress == 1)
                {
                    phonemes.Add("\u02c8"); // ˈ (primary stress)
                    prosodyList.Add(new ProsodyInfo(A1: 0, A2: a2, A3: wordPhonemeCount));
                }
                else if (stress == 2)
                {
                    phonemes.Add("\u02cc"); // ˌ (secondary stress)
                    prosodyList.Add(new ProsodyInfo(A1: 0, A2: a2, A3: wordPhonemeCount));
                }

                // Each IPA character becomes a separate phoneme token.
                foreach (char ch in ipa)
                {
                    phonemes.Add(ch < s_charStrings.Length ? s_charStrings[ch] : ch.ToString());
                    prosodyList.Add(new ProsodyInfo(A1: 0, A2: a2, A3: wordPhonemeCount));
                }
            }

            // After any word (punctuation or regular), next word needs space.
            needSpace = true;
        }

        return (phonemes, prosodyList);
    }

    // -----------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------

    /// <summary>
    /// Check if a word consists entirely of punctuation tokens.
    /// Mirrors Python <c>_is_punctuation_word()</c>.
    /// </summary>
    private static bool IsPunctuationWord(List<string> wordTokens)
    {
        for (int i = 0; i < wordTokens.Count; i++)
        {
            if (!ArpabetToIPAConverter.IsPunctuation(wordTokens[i]))
            {
                return false;
            }
        }
        return true;
    }

    /// <summary>
    /// Extract source words from text for function-word detection.
    /// Returns only alphabetic words (no punctuation), matching the order
    /// of non-punctuation word groups from G2P.
    /// Mirrors Python <c>_get_source_words()</c>.
    /// </summary>
    private static List<string> GetSourceWords(string text)
    {
        var matches = SourceWordRegex().Matches(text.ToLowerInvariant());
        var result = new List<string>(matches.Count);
        foreach (Match m in matches)
        {
            result.Add(m.Value);
        }
        return result;
    }
}
