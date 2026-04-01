using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;
using PiperPlus.Core.Mapping;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

/// <summary>
/// Pure Hangul-decomposition-based Korean G2P engine that implements
/// <see cref="IKoreanG2PEngine"/>.
/// <para>
/// Ports the Python <c>korean.py</c> logic:
/// <list type="number">
///   <item>NFC-normalize the input text.</item>
///   <item>Split by whitespace into word tokens.</item>
///   <item>For each Hangul syllable (U+AC00..U+D7A3), decompose into
///         (initial, medial, final) jamo indices and map to IPA.</item>
///   <item>Pass punctuation through as-is; skip digits.</item>
///   <item>Map multi-character IPA tokens to PUA codepoints via
///         <see cref="OpenJTalkToPiperMapping.MapSequence"/>.</item>
/// </list>
/// </para>
/// <para>
/// This engine does NOT use g2pk2 (no external NuGet dependency).
/// Phonological rules (liaison, nasalization, aspiration, tensification)
/// are not applied.
/// </para>
/// </summary>
internal sealed class DotNetKoreanG2PEngine : IKoreanG2PEngine
{
    // -----------------------------------------------------------------
    // Hangul syllable block range (U+AC00 .. U+D7A3)
    // -----------------------------------------------------------------
    private const int HangulStart = 0xAC00;
    private const int HangulEnd = 0xD7A3;

    // Decomposition constants
    private const int NMedials = 21;
    private const int NFinals = 28;

    // -----------------------------------------------------------------
    // Initial consonants (chosung) -- 19 entries, index -> IPA tokens
    // -----------------------------------------------------------------
    private static readonly string[][] InitialToIpa =
    [
        ["k"],           // 0: g
        ["k\u0348"],     // 1: gg  (k͈)
        ["n"],           // 2: n
        ["t"],           // 3: d
        ["t\u0348"],     // 4: dd  (t͈)
        ["\u027E"],      // 5: r   (ɾ)
        ["m"],           // 6: m
        ["p"],           // 7: b
        ["p\u0348"],     // 8: bb  (p͈)
        ["s"],           // 9: s
        ["s\u0348"],     // 10: ss (s͈)
        [],              // 11: ieung (silent in initial position)
        ["t\u0255"],     // 12: j  (tc)
        ["t\u0348\u0255"], // 13: jj (t͈c)
        ["t\u0255\u02B0"], // 14: ch (tcʰ)
        ["k\u02B0"],     // 15: k  (kʰ)
        ["t\u02B0"],     // 16: t  (tʰ)
        ["p\u02B0"],     // 17: p  (pʰ)
        ["h"],           // 18: h
    ];

    // -----------------------------------------------------------------
    // Medial vowels (jungsung) -- 21 entries, index -> IPA tokens
    // Diphthongs are decomposed into glide + vowel sequences.
    // -----------------------------------------------------------------
    private static readonly string[][] MedialToIpa =
    [
        ["a"],             // 0: a
        ["\u025B"],        // 1: ae  (ɛ)
        ["j", "a"],        // 2: ya
        ["j", "\u025B"],   // 3: yae (j, ɛ)
        ["\u028C"],        // 4: eo  (ʌ)
        ["e"],             // 5: e
        ["j", "\u028C"],   // 6: yeo (j, ʌ)
        ["j", "e"],        // 7: ye
        ["o"],             // 8: o
        ["w", "a"],        // 9: wa
        ["w", "\u025B"],   // 10: wae (w, ɛ)
        ["w", "e"],        // 11: oe  (modern Seoul: diphthong [we])
        ["j", "o"],        // 12: yo
        ["u"],             // 13: u
        ["w", "\u028C"],   // 14: weo (w, ʌ)
        ["w", "e"],        // 15: we
        ["w", "i"],        // 16: wi
        ["j", "u"],        // 17: yu
        ["\u026F"],        // 18: eu  (ɯ)
        ["\u0270", "i"],   // 19: ui  (ɰ, i)
        ["i"],             // 20: i
    ];

    // -----------------------------------------------------------------
    // Final consonants (jongsung) -- 28 entries, index -> IPA tokens
    // Index 0 = no final consonant.
    // Complex finals are simplified to their representative sound.
    // -----------------------------------------------------------------
    private static readonly string[][] FinalToIpa =
    [
        [],               // 0: (none)
        ["k\u031A"],      // 1: g   (k̚)
        ["k\u031A"],      // 2: gg  (k̚)
        ["k\u031A"],      // 3: gs  (k̚)
        ["n"],            // 4: n
        ["n"],            // 5: nj  (n)
        ["n"],            // 6: nh  (n)
        ["t\u031A"],      // 7: d   (t̚)
        ["l"],            // 8: r/l
        ["k\u031A"],      // 9: lg  (k̚)
        ["m"],            // 10: lm (m)
        ["l"],            // 11: lb (l)
        ["l"],            // 12: ls (l)
        ["l"],            // 13: lt (l)
        ["l"],            // 14: lp (l)
        ["l"],            // 15: lh (l)
        ["m"],            // 16: m
        ["p\u031A"],      // 17: b  (p̚)
        ["p\u031A"],      // 18: bs (p̚)
        ["t\u031A"],      // 19: s  (t̚)
        ["t\u031A"],      // 20: ss (t̚)
        ["\u014B"],       // 21: ng (ŋ)
        ["t\u031A"],      // 22: j  (t̚)
        ["t\u031A"],      // 23: ch (t̚)
        ["k\u031A"],      // 24: k  (k̚)
        ["t\u031A"],      // 25: t  (t̚)
        ["p\u031A"],      // 26: p  (p̚)
        ["t\u031A"],      // 27: h  (t̚)
    ];

    // Punctuation characters passed through as-is
    private static readonly HashSet<char> Punctuation =
        [',', '.', ';', ':', '!', '?', '\u3002', '\uFF0C', '\uFF01', '\uFF1F', '\u3001'];

    // Regex to split text into word tokens and whitespace
    private static readonly Regex WordSplitRegex = new(@"(\s+)", RegexOptions.Compiled);

    public KoreanG2PResult Convert(string text)
    {
        // NFC normalize to handle NFD-decomposed Hangul jamo
        text = text.Normalize(NormalizationForm.FormC);

        var phonemes = new List<string>();
        var a1 = new List<int>();
        var a2 = new List<int>();
        var a3 = new List<int>();

        // Split by whitespace while preserving structure
        string[] parts = WordSplitRegex.Split(text);

        bool needSpace = false;
        foreach (string part in parts)
        {
            // Skip empty strings from split
            if (part.Length == 0)
                continue;

            // Whitespace between words -> mark that next word needs a space
            if (IsWhitespace(part))
            {
                needSpace = true;
                continue;
            }

            // Insert word-boundary space token
            if (needSpace && phonemes.Count > 0)
            {
                phonemes.Add(" ");
                a1.Add(0);
                a2.Add(0);
                a3.Add(0);
            }

            int syllableCount = CountHangulSyllables(part);
            int wordA3 = Math.Max(syllableCount, 1);

            foreach (char ch in part)
            {
                if (IsHangulSyllable(ch))
                {
                    string[] ipaTokens = SyllableToIpa(ch);
                    foreach (string token in ipaTokens)
                    {
                        phonemes.Add(token);
                        a1.Add(0);
                        a2.Add(0);
                        a3.Add(wordA3);
                    }
                }
                else if (Punctuation.Contains(ch))
                {
                    phonemes.Add(ch.ToString());
                    a1.Add(0);
                    a2.Add(0);
                    a3.Add(0);
                }
                else if (char.IsLetter(ch))
                {
                    // Non-Hangul alphabetic characters (e.g., Latin) -- pass through
                    phonemes.Add(ch.ToString());
                    a1.Add(0);
                    a2.Add(0);
                    a3.Add(wordA3);
                }
                // Digits and other characters are skipped
            }

            needSpace = true;
        }

        // Map multi-character tokens to PUA codepoints
        IReadOnlyList<string> mapped = OpenJTalkToPiperMapping.MapSequence(phonemes);
        var mappedList = new List<string>(mapped.Count);
        for (int i = 0; i < mapped.Count; i++)
            mappedList.Add(mapped[i]);

        return new KoreanG2PResult(
            Phonemes: mappedList,
            A1: a1,
            A2: a2,
            A3: a3);
    }

    // -----------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------

    /// <summary>
    /// Check if character is a composed Hangul syllable (U+AC00..U+D7A3).
    /// </summary>
    private static bool IsHangulSyllable(char ch)
    {
        int code = ch;
        return code >= HangulStart && code <= HangulEnd;
    }

    /// <summary>
    /// Decompose a Hangul syllable into (initial, medial, final) indices.
    /// </summary>
    private static (int Initial, int Medial, int Final) DecomposeSyllable(char ch)
    {
        int code = ch - HangulStart;
        int initial = code / (NMedials * NFinals);
        int medial = (code % (NMedials * NFinals)) / NFinals;
        int final_ = code % NFinals;
        return (initial, medial, final_);
    }

    /// <summary>
    /// Convert a single Hangul syllable to a list of IPA tokens.
    /// </summary>
    private static string[] SyllableToIpa(char ch)
    {
        var (initial, medial, final_) = DecomposeSyllable(ch);

        // Collect all tokens
        var result = new List<string>(6);
        result.AddRange(InitialToIpa[initial]);
        result.AddRange(MedialToIpa[medial]);
        result.AddRange(FinalToIpa[final_]);
        return result.ToArray();
    }

    /// <summary>
    /// Count the number of Hangul syllables in a word.
    /// </summary>
    private static int CountHangulSyllables(string word)
    {
        int count = 0;
        foreach (char ch in word)
        {
            if (IsHangulSyllable(ch))
                count++;
        }
        return count;
    }

    /// <summary>
    /// Check if a string is entirely whitespace.
    /// </summary>
    private static bool IsWhitespace(string s)
    {
        foreach (char ch in s)
        {
            if (!char.IsWhiteSpace(ch))
                return false;
        }
        return true;
    }
}
