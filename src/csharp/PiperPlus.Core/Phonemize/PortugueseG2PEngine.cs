using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Rule-based Brazilian Portuguese G2P engine implementing
/// <see cref="IPortugueseG2PEngine"/>.
/// <para>
/// A port of the BR path of <c>src/python/g2p/piper_plus_g2p/portuguese.py</c>,
/// the Portuguese G2P the models were trained with:
/// <list type="number">
///   <item>Normalization: trim, NFC, lowercase, collapse whitespace.</item>
///   <item>Tokenization (<c>_split_words</c>): runs of Portuguese letters are
///         words; <c>,.;:!?¡¿—–…</c> are single punctuation tokens; anything
///         else (digits, hyphens) is dropped.</item>
///   <item>Stress (<c>_find_stress_position</c>): the accented vowel group,
///         otherwise the penultimate for words ending in a/e/o/am/em/en (+s)
///         and the last for other endings.</item>
///   <item>Grapheme-to-phoneme rules per word (<c>_convert_word</c>), then the
///         BR rules: nasal coda removal, coda l → w, t/d palatalization before
///         unstressed final e and unstressed final e/o → i/u.</item>
/// </list>
/// </para>
/// <para>
/// The output follows the <see cref="IPortugueseG2PEngine"/> conventions: a
/// space token before every word after the first token (punctuation
/// included, as in Python), punctuation as single-character tokens, tʃ / dʒ as
/// multi-character tokens and NFC nasal vowels. Python returns the stressed
/// phoneme's index next to the phonemes; this engine marks it with a
/// preceding <c>ˈ</c>, which <see cref="PortuguesePhonemizer"/> strips and
/// turns into A2=2, so the phonemizer's output is Python's
/// <c>phonemize_portuguese()</c>.
/// </para>
/// </summary>
public sealed class PortugueseG2PEngine : IPortugueseG2PEngine
{
    // =================================================================
    // Character classes (portuguese.py)
    // =================================================================
    private const string Punctuation = ",.;:!?¡¿—–…";

    // _VOWELS: a e i o u á à â ã é ê í ó ô õ ú ü
    private const string Vowels = "aeiouáàâãéêíóôõúü";

    // Letters of the _split_words pattern besides a-z: the accented vowels, ç and ñ.
    private const string ExtraLetters = "áàâãéêíóôõúüçñ";

    // e/i, plain or accented: "qu"/"gu" before them have a silent u.
    private const string FrontVowels = "eiéêí";

    private const string StressAccents = "áéíóú"; // acute: stressed open vowel
    private const string Circumflex = "âêô"; // stressed closed vowel
    private const string Tilde = "ãõ"; // nasal, stressed when the only accent

    // _IPA_NASAL_VOWELS / _IPA_VOWELS / _IPA_CONSONANTS (single code points).
    private const string IpaNasalVowels = "ãẽĩõũ";
    private const string IpaVowels = "aeioɛɔu" + IpaNasalVowels;
    private const string IpaConsonants = "bcdfɡhjklmnpɲɾʁsʃtʎvwzʒ";

    private const string Stress = "ˈ"; // ˈ

    private static readonly Regex S_whitespace = new(@"\s+", RegexOptions.Compiled);

    /// <inheritdoc />
    public List<string> ToPhonemeList(string text)
    {
        var result = new List<string>();
        if (string.IsNullOrEmpty(text))
        {
            return result;
        }

        bool needSpace = false;
        foreach (string token in SplitWords(Normalize(text)))
        {
            bool isPunct = Punctuation.Contains(token[0]);

            // Unlike Spanish, punctuation also sets needSpace:
            // "¿como" -> ¿ " " k ˈo m u
            if (!isPunct && needSpace)
            {
                result.Add(" ");
            }

            if (isPunct)
            {
                result.Add(token);
            }
            else
            {
                (List<string> phonemes, int stressIndex) = ConvertWord(token);
                for (int j = 0; j < phonemes.Count; j++)
                {
                    if (j == stressIndex)
                    {
                        result.Add(Stress);
                    }

                    result.Add(phonemes[j]);
                }
            }

            needSpace = true;
        }

        return result;
    }

    // =================================================================
    // Normalization and tokenization
    // =================================================================
    private static string Normalize(string text)
    {
        string s = text.Trim().Normalize(NormalizationForm.FormC).ToLowerInvariant();
        return S_whitespace.Replace(s, " ");
    }

    private static bool IsLetter(char ch) => (ch >= 'a' && ch <= 'z') || ExtraLetters.Contains(ch);

    private static bool IsVowelChar(char ch) => Vowels.Contains(ch);

    private static bool IsFrontVowel(char ch) => FrontVowels.Contains(ch);

    private static bool IsStressAccented(char ch) =>
        StressAccents.Contains(ch) || Circumflex.Contains(ch) || Tilde.Contains(ch);

    /// <summary>
    /// Splits like <c>_split_words</c>: a run of letters is one word, each
    /// punctuation character is one token, anything else is dropped.
    /// </summary>
    private static List<string> SplitWords(string text)
    {
        var tokens = new List<string>();
        int n = text.Length;
        int i = 0;
        while (i < n)
        {
            char ch = text[i];
            if (IsLetter(ch))
            {
                int start = i;
                while (i < n && IsLetter(text[i]))
                {
                    i++;
                }

                tokens.Add(text[start..i]);
                continue;
            }

            if (Punctuation.Contains(ch))
            {
                tokens.Add(ch.ToString());
            }

            i++;
        }

        return tokens;
    }

    // =================================================================
    // Stress (_count_vowel_groups / _find_stress_position)
    // =================================================================

    /// <summary>
    /// Counts the vowel groups of a word and finds the accented one
    /// (-1 if none). "qu" (always) and "gu" + e/i are consonants, "ou" is one
    /// group. Python only checks the o of "ou" for an accent, which is never
    /// accented there, so an "ou" group is never the accented one.
    /// </summary>
    private static (int Count, int AccentGroup) ScanVowelGroups(string word)
    {
        int count = 0;
        int accentGroup = -1;
        int n = word.Length;
        int i = 0;
        while (i < n)
        {
            char ch = word[i];
            if (ch == 'q' && i + 1 < n && word[i + 1] == 'u')
            {
                i += 2;
                continue;
            }

            if (ch == 'g' && i + 2 < n && word[i + 1] == 'u' && IsFrontVowel(word[i + 2]))
            {
                i += 2;
                continue;
            }

            if (ch == 'o' && i + 1 < n && word[i + 1] == 'u')
            {
                count++;
                i += 2;
                continue;
            }

            if (IsVowelChar(ch))
            {
                if (IsStressAccented(ch))
                {
                    accentGroup = count;
                }

                count++;
            }

            i++;
        }

        return (count, accentGroup);
    }

    /// <summary>
    /// The stressed vowel group counted from the end (<c>_find_stress_position</c>).
    /// </summary>
    private static int FindStressPosition(string word, int groupCount, int accentGroup)
    {
        if (groupCount == 0)
        {
            return 0;
        }

        if (accentGroup >= 0)
        {
            return groupCount - 1 - accentGroup;
        }

        // Paroxytone endings, after stripping every trailing s ("ens" -> "en").
        string stripped = word.TrimEnd('s');
        bool paroxytone = stripped.EndsWith('a') || stripped.EndsWith('e') || stripped.EndsWith('o')
            || stripped.EndsWith("am", StringComparison.Ordinal)
            || stripped.EndsWith("em", StringComparison.Ordinal)
            || stripped.EndsWith("en", StringComparison.Ordinal);
        return paroxytone ? Math.Min(1, groupCount - 1) : 0;
    }

    // =================================================================
    // Grapheme-to-phoneme rules (_convert_word)
    // =================================================================

    /// <summary>
    /// Phonemes of one lowercase word and the index of its stressed vowel
    /// (-1 if it has none), after the BR post-processing.
    /// </summary>
    internal static (List<string> Phonemes, int StressIndex) ConvertWord(string word)
    {
        var ph = new List<string>();
        int stressIndex = -1;
        int n = word.Length;
        int i = 0;

        (int groupCount, int accentGroup) = ScanVowelGroups(word);
        int stressTarget = groupCount - 1 - FindStressPosition(word, groupCount, accentGroup);
        int currentGroup = 0;

        while (i < n)
        {
            char ch = word[i];
            char next = i + 1 < n ? word[i + 1] : '\0';

            if (ch == 'n' && next == 'h')
            {
                ph.Add("ɲ"); // ɲ
                i += 2;
                continue;
            }

            if (ch == 'l' && next == 'h')
            {
                ph.Add("ʎ"); // ʎ
                i += 2;
                continue;
            }

            if (ch == 'c' && next == 'h')
            {
                ph.Add("ʃ"); // ʃ
                i += 2;
                continue;
            }

            if (ch == 'r' && next == 'r')
            {
                ph.Add("ʁ"); // ʁ
                i += 2;
                continue;
            }

            if (ch == 's' && next == 's')
            {
                ph.Add("s");
                i += 2;
                continue;
            }

            // "sc" + e/i -> s (no geminate)
            if (ch == 's' && next == 'c' && i + 2 < n && IsFrontVowel(word[i + 2]))
            {
                ph.Add("s");
                i += 2;
                continue;
            }

            // "qu" + e/i -> k (silent u); "qu" + anything else -> kw
            if (ch == 'q' && next == 'u')
            {
                ph.Add("k");
                if (!(i + 2 < n && IsFrontVowel(word[i + 2])))
                {
                    ph.Add("w");
                }

                i += 2;
                continue;
            }

            // "gu" + e/i -> ɡ (silent u)
            if (ch == 'g' && next == 'u' && i + 2 < n && IsFrontVowel(word[i + 2]))
            {
                ph.Add("ɡ");
                i += 2;
                continue;
            }

            // "ou" -> o, one vowel group
            if (ch == 'o' && next == 'u')
            {
                if (currentGroup == stressTarget)
                {
                    stressIndex = ph.Count;
                }

                ph.Add("o");
                currentGroup++;
                i += 2;
                continue;
            }

            switch (ch)
            {
                case 'r':
                    // Tap between vowels, ʁ everywhere else (word edges, coda,
                    // after a consonant).
                    bool intervocalic = i > 0 && i < n - 1 && IsVowelChar(word[i - 1]) && IsVowelChar(word[i + 1]);
                    ph.Add(intervocalic ? "ɾ" : "ʁ");
                    i++;
                    continue;

                case 's':
                    ph.Add(i > 0 && i + 1 < n && IsVowelChar(word[i - 1]) && IsVowelChar(word[i + 1]) ? "z" : "s");
                    i++;
                    continue;

                case 'x':
                    // Simplified: z between vowels, ʃ elsewhere.
                    ph.Add(i > 0 && i + 1 < n && IsVowelChar(word[i - 1]) && IsVowelChar(word[i + 1]) ? "z" : "ʃ");
                    i++;
                    continue;

                case 'c':
                    ph.Add(i + 1 < n && IsFrontVowel(word[i + 1]) ? "s" : "k");
                    i++;
                    continue;

                case 'ç': // ç
                    ph.Add("s");
                    i++;
                    continue;

                case 'g':
                    ph.Add(i + 1 < n && IsFrontVowel(word[i + 1]) ? "ʒ" : "ɡ");
                    i++;
                    continue;

                case 'j':
                    ph.Add("ʒ"); // ʒ
                    i++;
                    continue;

                case 't':
                    // BR: t before i -> tʃ (before unstressed final e: post-processing)
                    ph.Add(next == 'i' || next == 'í' ? "tʃ" : "t");
                    i++;
                    continue;

                case 'd':
                    ph.Add(next == 'i' || next == 'í' ? "dʒ" : "d");
                    i++;
                    continue;

                case 'h':
                    i++;
                    continue;

                case 'b' or 'f' or 'k' or 'l' or 'm' or 'n' or 'p' or 'v' or 'w' or 'z':
                    ph.Add(ch.ToString());
                    i++;
                    continue;
            }

            if (IsVowelChar(ch))
            {
                bool absorbsNasal = false;
                bool isNasal = Tilde.Contains(ch);
                if (!isNasal && (next == 'n' || next == 'm'))
                {
                    // Nasal before n/m at the word end or before a consonant;
                    // the n/m is absorbed. Not before the "nh" digraph.
                    bool beforeNh = next == 'n' && i + 2 < n && word[i + 2] == 'h';
                    if (!beforeNh && (i + 2 >= n || !IsVowelChar(word[i + 2])))
                    {
                        isNasal = true;
                        absorbsNasal = true;
                    }
                }

                char vowel = BaseVowel(ch);
                string phoneme;
                if (isNasal)
                {
                    phoneme = NasalVowel(vowel);
                }
                else if (StressAccents.Contains(ch))
                {
                    // Acute accent: open é -> ɛ, ó -> ɔ.
                    phoneme = vowel switch
                    {
                        'e' => "ɛ",
                        'o' => "ɔ",
                        _ => vowel.ToString(),
                    };
                }
                else
                {
                    phoneme = vowel.ToString();
                }

                if (currentGroup == stressTarget)
                {
                    stressIndex = ph.Count;
                }

                ph.Add(phoneme);
                currentGroup++;
                i += absorbsNasal ? 2 : 1;
                continue;
            }

            // y, ñ and other letters: skipped.
            i++;
        }

        RemoveDuplicateNasalCoda(ph);
        ApplyCodaLVocalization(ph);
        ApplyBrPostprocessing(ph, stressIndex);
        return (ph, stressIndex);
    }

    // á à â ã -> a, é ê -> e, í -> i, ó ô õ -> o, ú ü -> u (_ACCENTED).
    private static char BaseVowel(char ch) => ch switch
    {
        'á' or 'à' or 'â' or 'ã' => 'a',
        'é' or 'ê' => 'e',
        'í' => 'i',
        'ó' or 'ô' or 'õ' => 'o',
        'ú' or 'ü' => 'u',
        _ => ch,
    };

    private static string NasalVowel(char vowel) => vowel switch
    {
        'a' => "ã",
        'e' => "ẽ",
        'i' => "ĩ",
        'o' => "õ",
        'u' => "ũ",
        _ => vowel.ToString(),
    };

    // =================================================================
    // BR post-processing
    // =================================================================
    private static bool IsPunctuationToken(string token) => token.Length == 1 && Punctuation.Contains(token[0]);

    private static bool IsIpaVowel(string token) => token.Length == 1 && IpaVowels.Contains(token[0]);

    // A consonant phoneme, or a multi-character one starting with a consonant (tʃ).
    private static bool StartsWithIpaConsonant(string token) =>
        token.Length > 0 && IpaConsonants.Contains(token[0]) && !IsIpaVowel(token);

    /// <summary>
    /// Drops an n/m after a nasal vowel at the end of the word
    /// (<c>_remove_duplicate_nasal_coda</c>).
    /// </summary>
    private static void RemoveDuplicateNasalCoda(List<string> ph)
    {
        for (int i = ph.Count - 1; i >= 1; i--)
        {
            if ((ph[i] == "n" || ph[i] == "m")
                && ph[i - 1].Length == 1 && IpaNasalVowels.Contains(ph[i - 1][0])
                && (i == ph.Count - 1 || ph[i + 1] == " " || IsPunctuationToken(ph[i + 1])))
            {
                ph.RemoveAt(i);
            }
        }
    }

    /// <summary>
    /// l at the word end or before a consonant becomes w
    /// (<c>_apply_coda_l_vocalization</c>).
    /// </summary>
    private static void ApplyCodaLVocalization(List<string> ph)
    {
        for (int i = 0; i < ph.Count; i++)
        {
            if (ph[i] != "l")
            {
                continue;
            }

            if (i == ph.Count - 1)
            {
                ph[i] = "w";
                continue;
            }

            string next = ph[i + 1];
            if (next == " " || IsPunctuationToken(next) || StartsWithIpaConsonant(next))
            {
                ph[i] = "w";
            }
        }
    }

    /// <summary>
    /// Unstressed final e: te -> tʃi, de -> dʒi, otherwise e -> i; unstressed
    /// final o -> u (<c>_apply_br_postprocessing</c>). Trailing punctuation is
    /// skipped; a word of one phoneme is left alone.
    /// </summary>
    private static void ApplyBrPostprocessing(List<string> ph, int stressIndex)
    {
        foreach ((int start, int end) in FindWordRanges(ph))
        {
            if (end - start < 2)
            {
                continue;
            }

            int last = end - 1;
            while (last >= start && IsPunctuationToken(ph[last]))
            {
                last--;
            }

            if (last < start || last == stressIndex)
            {
                continue;
            }

            if (ph[last] == "e")
            {
                if (last >= start + 1 && ph[last - 1] == "t")
                {
                    ph[last - 1] = "tʃ";
                }
                else if (last >= start + 1 && ph[last - 1] == "d")
                {
                    ph[last - 1] = "dʒ";
                }

                ph[last] = "i";
            }
            else if (ph[last] == "o")
            {
                ph[last] = "u";
            }
        }
    }

    // (start, end) of each space-separated run (_find_word_ranges).
    private static List<(int Start, int End)> FindWordRanges(List<string> ph)
    {
        var ranges = new List<(int Start, int End)>();
        int start = 0;
        for (int i = 0; i < ph.Count; i++)
        {
            if (ph[i] == " ")
            {
                if (i > start)
                {
                    ranges.Add((start, i));
                }

                start = i + 1;
            }
        }

        if (start < ph.Count)
        {
            ranges.Add((start, ph.Count));
        }

        return ranges;
    }
}
