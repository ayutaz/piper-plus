using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Text.RegularExpressions;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Converts ARPAbet tokens to espeak-ng-compatible IPA symbols.
/// <para>
/// This is a 1:1 port of the Python module
/// <c>piper_train/phonemize/english.py</c>. It provides:
/// <list type="bullet">
///   <item>Single-token ARPAbet-to-IPA conversion (<see cref="ConvertToken"/>).</item>
///   <item>Context-dependent word-level conversion (<see cref="ConvertWord"/>).</item>
///   <item>Function-word detection (<see cref="IsFunctionWord"/>).</item>
///   <item>Punctuation detection (<see cref="IsPunctuation"/>).</item>
/// </list>
/// </para>
/// </summary>
public static partial class ArpabetToIPAConverter
{
    // ---------------------------------------------------------------
    // ARPAbet-to-IPA mapping (33 entries + AH-unstressed special case)
    // ---------------------------------------------------------------

    private static readonly Dictionary<string, string> s_arpabetToIpa = new(StringComparer.Ordinal)
    {
        ["AA"] = "\u0251",      // ɑ
        ["AE"] = "\u00e6",      // æ
        ["AH"] = "\u028c",      // ʌ
        ["AO"] = "\u0254\u02d0", // ɔː
        ["AW"] = "a\u028a",    // aʊ
        ["AY"] = "a\u026a",    // aɪ
        ["B"] = "b",
        ["CH"] = "t\u0283",    // tʃ
        ["D"] = "d",
        ["DH"] = "\u00f0",     // ð
        ["EH"] = "\u025b",     // ɛ
        ["ER"] = "\u025a",     // ɚ  (unstressed default; stressed → ɜː in ConvertWord)
        ["EY"] = "e\u026a",    // eɪ
        ["F"] = "f",
        ["G"] = "\u0261",     // ɡ (U+0261, not ASCII g)
        ["HH"] = "h",
        ["IH"] = "\u026a",     // ɪ
        ["IY"] = "i\u02d0",    // iː
        ["JH"] = "d\u0292",    // dʒ
        ["K"] = "k",
        ["L"] = "l",
        ["M"] = "m",
        ["N"] = "n",
        ["NG"] = "\u014b",     // ŋ
        ["OW"] = "o\u028a",    // oʊ
        ["OY"] = "\u0254\u026a", // ɔɪ
        ["P"] = "p",
        ["R"] = "\u0279",     // ɹ
        ["S"] = "s",
        ["SH"] = "\u0283",     // ʃ
        ["T"] = "t",
        ["TH"] = "\u03b8",     // θ
        ["UH"] = "\u028a",     // ʊ
        ["UW"] = "u\u02d0",    // uː
        ["V"] = "v",
        ["W"] = "w",
        ["Y"] = "j",
        ["Z"] = "z",
        ["ZH"] = "\u0292",     // ʒ
    };

    /// <summary>
    /// The complete ARPAbet-to-IPA mapping (read-only).
    /// Keys are uppercase ARPAbet bases without stress digits.
    /// </summary>
    public static IReadOnlyDictionary<string, string> ArpabetToIpa { get; } =
        new ReadOnlyDictionary<string, string>(s_arpabetToIpa);

    // Unstressed AH maps to schwa (ə) instead of ʌ.
    private const string AhUnstressedIpa = "\u0259"; // ə

    // Regex: base letters + optional stress digit (0/1/2).
    [GeneratedRegex(@"^([A-Z]+)(\d)?$")]
    private static partial Regex ArpabetPattern();

    // ---------------------------------------------------------------
    // Punctuation
    // ---------------------------------------------------------------

    private static readonly HashSet<char> s_punctuationChars = new() { ',', '.', ';', ':', '!', '?' };

    /// <summary>
    /// Returns <c>true</c> when <paramref name="token"/> is a single
    /// punctuation character (one of <c>,.;:!?</c>).
    /// </summary>
    public static bool IsPunctuation(string token)
    {
        return token is { Length: 1 } && s_punctuationChars.Contains(token[0]);
    }

    // ---------------------------------------------------------------
    // Function words (~110 entries, case-insensitive)
    // ---------------------------------------------------------------

    private static readonly HashSet<string> s_functionWords = new(StringComparer.OrdinalIgnoreCase)
    {
        // articles / determiners
        "a", "an", "the",
        // pronouns
        "i", "me", "my", "mine", "myself",
        "you", "your", "yours", "yourself",
        "he", "him", "his", "himself",
        "she", "her", "hers", "herself",
        "it", "its", "itself",
        "we", "us", "our", "ours", "ourselves",
        "they", "them", "their", "theirs", "themselves",
        // be-verbs
        "am", "is", "are", "was", "were", "be", "been", "being",
        // auxiliaries
        "have", "has", "had", "having",
        "do", "does", "did",
        "will", "would", "shall", "should",
        "can", "could", "may", "might", "must",
        // prepositions
        "at", "by", "for", "from", "in", "of", "on", "to", "with",
        "about", "after", "before", "between", "into", "through", "under",
        // conjunctions
        "and", "but", "or", "nor", "so", "yet", "if",
        "that", "than", "when", "while", "as", "because", "since",
        // others
        "not", "no",
    };

    /// <summary>
    /// Returns <c>true</c> when <paramref name="word"/> is an English
    /// function word (case-insensitive comparison).
    /// </summary>
    public static bool IsFunctionWord(string word)
    {
        return s_functionWords.Contains(word);
    }

    // ---------------------------------------------------------------
    // Single-token conversion
    // ---------------------------------------------------------------

    /// <summary>
    /// Convert a single ARPAbet token (e.g. <c>"AH0"</c>, <c>"K"</c>) to IPA.
    /// </summary>
    /// <param name="arpabetToken">
    /// An ARPAbet token: uppercase base letters with an optional trailing
    /// stress digit (<c>0</c>=unstressed, <c>1</c>=primary, <c>2</c>=secondary).
    /// </param>
    /// <returns>
    /// A tuple of the IPA string and the stress value.
    /// Stress is <c>0</c> (unstressed), <c>1</c> (primary), <c>2</c> (secondary),
    /// or <c>-1</c> for consonants / unknown tokens.
    /// </returns>
    public static (string Ipa, int Stress) ConvertToken(string arpabetToken)
    {
        var m = ArpabetPattern().Match(arpabetToken);
        if (!m.Success)
        {
            // Punctuation or unknown token — return as-is.
            return (arpabetToken, -1);
        }

        string basePart = m.Groups[1].Value;
        int stress = m.Groups[2].Success ? int.Parse(m.Groups[2].Value) : -1;

        // Special case: unstressed AH → schwa (ə).
        if (basePart == "AH" && stress == 0)
        {
            return (AhUnstressedIpa, stress);
        }

        if (s_arpabetToIpa.TryGetValue(basePart, out string? ipa))
        {
            return (ipa, stress);
        }

        // Unknown ARPAbet symbol — return the original token.
        return (arpabetToken, stress);
    }

    // ---------------------------------------------------------------
    // Word-level conversion (context-dependent rules)
    // ---------------------------------------------------------------

    /// <summary>
    /// Convert an ordered list of ARPAbet tokens for a single word to IPA,
    /// applying context-dependent rules:
    /// <list type="bullet">
    ///   <item><c>AA</c> + <c>R</c> merges into <c>ɑːɹ</c>.</item>
    ///   <item><c>ER</c> with primary stress (<c>ER1</c>) becomes <c>ɜː</c>.</item>
    /// </list>
    /// </summary>
    /// <param name="tokens">
    /// ARPAbet tokens for a single word (e.g. <c>["HH","AH0","L","OW1"]</c>).
    /// </param>
    /// <returns>
    /// A list of <c>(Ipa, Stress)</c> tuples after context-dependent merging.
    /// </returns>
    public static List<(string Ipa, int Stress)> ConvertWord(IReadOnlyList<string> tokens)
    {
        var result = new List<(string Ipa, int Stress)>();
        int i = 0;

        while (i < tokens.Count)
        {
            string token = tokens[i];
            var m = ArpabetPattern().Match(token);

            if (m.Success)
            {
                string basePart = m.Groups[1].Value;
                int stress = m.Groups[2].Success ? int.Parse(m.Groups[2].Value) : -1;

                // AA + R → ɑːɹ
                if (basePart == "AA" && i + 1 < tokens.Count && tokens[i + 1] == "R")
                {
                    result.Add(("\u0251\u02d0\u0279", stress)); // ɑːɹ
                    i += 2;
                    continue;
                }

                // Stressed ER (stress == 1) → ɜː
                if (basePart == "ER" && stress == 1)
                {
                    result.Add(("\u025c\u02d0", stress)); // ɜː
                    i += 1;
                    continue;
                }
            }

            var (ipa, s) = ConvertToken(token);
            result.Add((ipa, s));
            i += 1;
        }

        return result;
    }
}
