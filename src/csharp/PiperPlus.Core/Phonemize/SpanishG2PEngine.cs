using System;
using System.Collections.Generic;
using System.Text;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Rule-based Spanish G2P engine implementing <see cref="ISpanishG2PEngine"/>.
/// <para>
/// A port of <c>src/python/g2p/piper_plus_g2p/spanish.py</c>, the Spanish G2P
/// the models were trained with (Latin American: seseo, yeísmo):
/// <list type="number">
///   <item>Normalization: lowercase, NFC.</item>
///   <item>Tokenization (<c>_RE_TOKEN</c>): runs of Spanish letters are words;
///         <c>,.;:!?¡¿</c> are punctuation; anything else (digits included)
///         is dropped.</item>
///   <item>Grapheme-to-phoneme rules per word (<c>_g2p_word</c>).</item>
///   <item>Syllabification and stress (<c>_find_syllable_boundaries</c>,
///         <c>_get_stressed_syllable</c>, <c>_insert_stress_marker</c>): the
///         stress mark <c>ˈ</c> goes right before the first vowel of the
///         stressed syllable; unstressed function words get no mark.</item>
/// </list>
/// </para>
/// <para>
/// The output follows the <see cref="ISpanishG2PEngine"/> conventions and is
/// Python's <c>phonemize_spanish()</c>: a space token before every word except
/// the first, punctuation as single-character tokens with no space before
/// them, and the trill as the multi-character token <c>"rr"</c>.
/// <see cref="SpanishPhonemizer"/> derives the prosody (A2/A3) from it.
/// </para>
/// </summary>
public sealed class SpanishG2PEngine : ISpanishG2PEngine
{
    // =================================================================
    // Character classes (spanish.py _PUNCTUATION / _VOWELS / _ACCENT_MAP)
    // =================================================================
    private const string Punctuation = ",.;:!?¡¿";
    private const string Vowels = "aeiou";
    private const string StrongVowels = "aeo";
    private const string StressAccents = "áéíóú"; // á é í ó ú

    // Letters of the _RE_TOKEN pattern besides a-z: á é í ó ú ü ñ.
    private const string ExtraLetters = "áéíóúüñ";

    private const string Stress = "ˈ"; // ˈ

    private static readonly char[] StressAccentChars = StressAccents.ToCharArray();

    // Monosyllabic function words that are unstressed in connected speech
    // (_UNSTRESSED_FUNCTION_WORDS): they get no stress mark.
    private static readonly HashSet<string> UnstressedFunctionWords =
    [
        "el", "la", "los", "las", "un", "una", "de", "del", "al", "a", "en",
        "con", "por", "y", "o", "que", "se", "me", "te", "le", "lo", "nos",
        "su", "mi", "tu", "es", "no", "si",
    ];

    // Two-consonant onsets that stay together in the next syllable.
    private static readonly HashSet<string> InseparableOnsets =
    [
        "bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "tr", "tl",
    ];

    // 1-to-1 consonants with no context dependency (_SIMPLE_CONSONANT_MAP).
    private static readonly Dictionary<char, string> SimpleConsonants = new()
    {
        ['f'] = "f",
        ['j'] = "x",
        ['k'] = "k",
        ['l'] = "l",
        ['m'] = "m",
        ['n'] = "n",
        ['ñ'] = "ɲ", // ñ -> ɲ
        ['p'] = "p",
        ['s'] = "s",
        ['t'] = "t",
        ['w'] = "w",
        ['z'] = "s", // seseo
    };

    /// <inheritdoc />
    public List<string> ToPhonemeList(string text)
    {
        var result = new List<string>();
        if (string.IsNullOrEmpty(text))
        {
            return result;
        }

        string normalized = text.ToLowerInvariant().Normalize(NormalizationForm.FormC);

        bool needSpace = false;
        foreach (string token in SplitTokens(normalized))
        {
            // Punctuation never gets a space before it and does not set
            // needSpace: "hola ¿qué?" -> ... a ¿ " " k ˈe ?
            if (Punctuation.Contains(token[0]))
            {
                result.Add(token);
                continue;
            }

            if (needSpace)
            {
                result.Add(" ");
            }

            result.AddRange(ConvertWord(token));
            needSpace = true;
        }

        return result;
    }

    // =================================================================
    // Normalization and tokenization
    // =================================================================
    private static bool IsLetter(char ch) => (ch >= 'a' && ch <= 'z') || ExtraLetters.Contains(ch);

    /// <summary>
    /// Splits like <c>_RE_TOKEN.findall</c>: a run of letters is one word,
    /// each punctuation character is one token (Python matches a run of them
    /// and emits it character by character), anything else is dropped.
    /// </summary>
    private static List<string> SplitTokens(string text)
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

    // á é í ó ú ü -> a e i o u; other characters unchanged (_get_base_vowel).
    private static char BaseChar(char ch) => ch switch
    {
        'á' => 'a',
        'é' => 'e',
        'í' => 'i',
        'ó' => 'o',
        'ú' or 'ü' => 'u',
        _ => ch,
    };

    private static string BaseWord(string word)
    {
        var sb = new StringBuilder(word.Length);
        foreach (char ch in word)
        {
            sb.Append(BaseChar(ch));
        }

        return sb.ToString();
    }

    // A vowel, accented or not (_is_vowel_char).
    private static bool IsVowelChar(char ch) => Vowels.Contains(BaseChar(ch));

    // =================================================================
    // Word conversion
    // =================================================================

    /// <summary>
    /// Phonemes of one lowercase word with the stress mark inserted, or
    /// without it for an unstressed function word.
    /// </summary>
    internal static List<string> ConvertWord(string word)
    {
        List<string> phonemes = WordToPhonemes(word);
        if (UnstressedFunctionWords.Contains(word))
        {
            return phonemes;
        }

        List<GraphemeUnit> units = SegmentGraphemes(word);
        List<int> boundaries = FindSyllableBoundaries(units);
        int stressedSyllable = GetStressedSyllable(word, units, boundaries);
        return InsertStressMarker(phonemes, units, boundaries, stressedSyllable);
    }

    /// <summary>Grapheme-to-phoneme rules (<c>_g2p_word</c>).</summary>
    private static List<string> WordToPhonemes(string word)
    {
        var ph = new List<string>();
        string bw = BaseWord(word);
        int n = word.Length;
        int i = 0;

        while (i < n)
        {
            char b = bw[i];
            bool wordInitial = i == 0;
            bool afterNasal = i > 0 && (bw[i - 1] == 'm' || bw[i - 1] == 'n');
            bool afterL = i > 0 && bw[i - 1] == 'l';
            bool beforeFrontVowel = i + 1 < n && (bw[i + 1] == 'e' || bw[i + 1] == 'i');

            if (Vowels.Contains(b))
            {
                ph.Add(b.ToString());
                i++;
                continue;
            }

            // "qu" -> k; the vowel after it is read next.
            if (b == 'q' && i + 1 < n && bw[i + 1] == 'u')
            {
                ph.Add("k");
                i += 2;
                continue;
            }

            if (b == 'c' && i + 1 < n && bw[i + 1] == 'h')
            {
                ph.Add("tʃ"); // tʃ
                i += 2;
                continue;
            }

            if (b == 'l' && i + 1 < n && bw[i + 1] == 'l')
            {
                ph.Add("ʝ"); // ʝ (yeísmo)
                i += 2;
                continue;
            }

            if (b == 'r' && i + 1 < n && bw[i + 1] == 'r')
            {
                ph.Add("rr");
                i += 2;
                continue;
            }

            bool guBeforeFrontVowel = b == 'g' && i + 2 < n && bw[i + 1] == 'u'
                && (bw[i + 2] == 'e' || bw[i + 2] == 'i');

            // "gü" + e/i -> ɡw (the diaeresis makes the u pronounced)
            if (guBeforeFrontVowel && word[i + 1] == 'ü')
            {
                ph.Add("ɡ");
                ph.Add("w");
                i += 2;
                continue;
            }

            // "gu" + e/i -> ɡ / ɣ (the u is silent)
            if (guBeforeFrontVowel)
            {
                bool prevVowel = i > 0 && IsVowelChar(word[i - 1]);
                ph.Add(prevVowel && !afterNasal ? "ɣ" : "ɡ");
                i += 2;
                continue;
            }

            // "sc" + e/i -> s (seseo, no geminate)
            if (b == 's' && i + 2 < n && bw[i + 1] == 'c' && (bw[i + 2] == 'e' || bw[i + 2] == 'i'))
            {
                ph.Add("s");
                i += 2;
                continue;
            }

            // b/v, d: stop at the word start and after a nasal or l,
            // fricative β/ð everywhere else.
            if (b == 'b' || b == 'v')
            {
                ph.Add(wordInitial || afterNasal || afterL ? "b" : "β");
                i++;
                continue;
            }

            if (b == 'c')
            {
                ph.Add(beforeFrontVowel ? "s" : "k");
                i++;
                continue;
            }

            if (b == 'd')
            {
                ph.Add(wordInitial || afterNasal || afterL ? "d" : "ð");
                i++;
                continue;
            }

            if (SimpleConsonants.TryGetValue(b, out string? simple))
            {
                ph.Add(simple);
                i++;
                continue;
            }

            if (b == 'g')
            {
                if (beforeFrontVowel)
                {
                    ph.Add("x");
                }
                else
                {
                    ph.Add(wordInitial || afterNasal || afterL ? "ɡ" : "ɣ");
                }

                i++;
                continue;
            }

            if (b == 'h')
            {
                i++;
                continue;
            }

            // r: trill at the word start and after l/n/s, tap otherwise.
            if (b == 'r')
            {
                bool trill = wordInitial || (i > 0 && (bw[i - 1] == 'l' || bw[i - 1] == 'n' || bw[i - 1] == 's'));
                ph.Add(trill ? "rr" : "ɾ");
                i++;
                continue;
            }

            // x -> ks; in "xc" + e/i the c is silent.
            if (b == 'x')
            {
                ph.Add("k");
                ph.Add("s");
                bool xc = i + 2 < n && bw[i + 1] == 'c' && (bw[i + 2] == 'e' || bw[i + 2] == 'i');
                i += xc ? 2 : 1;
                continue;
            }

            // y: a vowel at the word end, ʝ otherwise.
            if (b == 'y')
            {
                ph.Add(i == n - 1 ? "i" : "ʝ");
                i++;
                continue;
            }

            // Unknown letter (q without u): skipped.
            i++;
        }

        return ph;
    }

    // =================================================================
    // Grapheme segmentation, syllabification and stress
    // =================================================================

    /// <summary>A grapheme of <c>_segment_graphemes</c>.</summary>
    private readonly record struct GraphemeUnit(string Grapheme, bool IsVowel, bool IsSilent);

    /// <summary>
    /// Splits a word into graphemes, keeping the digraphs qu, gu/gü + e/i,
    /// ch, ll, rr, sc + e/i and xc + e/i together (<c>_segment_graphemes</c>).
    /// </summary>
    private static List<GraphemeUnit> SegmentGraphemes(string word)
    {
        string bw = BaseWord(word);
        var units = new List<GraphemeUnit>(word.Length);
        int n = word.Length;
        int i = 0;
        while (i < n)
        {
            char b = bw[i];
            char next = i + 1 < n ? bw[i + 1] : '\0';
            bool frontVowelAfterNext = i + 2 < n && (bw[i + 2] == 'e' || bw[i + 2] == 'i');

            if (IsDigraph(b, next, frontVowelAfterNext))
            {
                units.Add(new GraphemeUnit(word.Substring(i, 2), false, false));
                i += 2;
                continue;
            }

            units.Add(new GraphemeUnit(word[i].ToString(), Vowels.Contains(b), b == 'h'));
            i++;
        }

        return units;
    }

    // qu, gu + e/i, ch, ll, rr, sc + e/i, xc + e/i are one unit.
    private static bool IsDigraph(char b, char next, bool frontVowelAfterNext) => b switch
    {
        'q' => next == 'u',
        'g' => next == 'u' && frontVowelAfterNext,
        'c' => next == 'h',
        'l' => next == 'l',
        'r' => next == 'r',
        's' or 'x' => next == 'c' && frontVowelAfterNext,
        _ => false,
    };

    // Two adjacent vowels split when both are strong, or either is an
    // accented i/u ("país" -> pa | ís).
    private static bool IsHiatus(char prevGrapheme, char currGrapheme)
    {
        char prev = BaseChar(prevGrapheme);
        char curr = BaseChar(currGrapheme);
        if (StrongVowels.Contains(prev) && StrongVowels.Contains(curr))
        {
            return true;
        }

        return IsAccentedHighVowel(curr, currGrapheme) || IsAccentedHighVowel(prev, prevGrapheme);
    }

    private static bool IsAccentedHighVowel(char baseChar, char grapheme) =>
        (baseChar == 'i' || baseChar == 'u') && StressAccents.Contains(grapheme);

    // The base letter at the end of a unit (_base_cons): "ch" -> 'h'.
    private static char LastBase(GraphemeUnit unit) => BaseChar(unit.Grapheme[^1]);

    /// <summary>
    /// Indices of the units that start a syllable
    /// (<c>_find_syllable_boundaries</c>). Silent h is skipped; strong + strong
    /// vowels and an accented i/u are a hiatus; one consonant before a vowel
    /// starts the next syllable, and of two or more the last two do if they
    /// are an inseparable onset, otherwise the last one. Python also counts a
    /// word-initial consonant cluster this way ("gracias" -> g | ra | cias),
    /// and so does this port.
    /// </summary>
    private static List<int> FindSyllableBoundaries(List<GraphemeUnit> units)
    {
        var nonSilent = new List<int>(units.Count);
        for (int u = 0; u < units.Count; u++)
        {
            if (!units[u].IsSilent)
            {
                nonSilent.Add(u);
            }
        }

        int count = nonSilent.Count;
        if (count == 0)
        {
            return [0];
        }

        bool IsVowelAt(int k) => units[nonSilent[k]].IsVowel;
        char BaseAt(int k) => LastBase(units[nonSilent[k]]);

        var boundaries = new List<int> { 0 };
        int i = 1;
        while (i < count)
        {
            if (IsVowelAt(i))
            {
                if (IsVowelAt(i - 1))
                {
                    char prevGrapheme = units[nonSilent[i - 1]].Grapheme[^1];
                    char currGrapheme = units[nonSilent[i]].Grapheme[^1];
                    if (IsHiatus(prevGrapheme, currGrapheme))
                    {
                        boundaries.Add(i);
                    }
                }

                i++;
                continue;
            }

            int consStart = i;
            while (i < count && !IsVowelAt(i))
            {
                i++;
            }

            if (i >= count)
            {
                continue;
            }

            int consCount = i - consStart;
            if (consCount == 1)
            {
                boundaries.Add(consStart);
            }
            else if (consCount == 2)
            {
                string pair = string.Concat(BaseAt(consStart), BaseAt(consStart + 1));
                boundaries.Add(InseparableOnsets.Contains(pair) ? consStart : consStart + 1);
            }
            else
            {
                string last2 = string.Concat(BaseAt(i - 2), BaseAt(i - 1));
                boundaries.Add(InseparableOnsets.Contains(last2) ? i - 2 : i - 1);
            }
        }

        var result = new List<int>(boundaries.Count);
        foreach (int b in boundaries)
        {
            result.Add(nonSilent[b]);
        }

        return result;
    }

    /// <summary>
    /// The 0-based stressed syllable (<c>_get_stressed_syllable</c>): the one
    /// with the accent mark; otherwise the penultimate for words ending in a
    /// vowel, n or s, and the last for other endings.
    /// </summary>
    private static int GetStressedSyllable(string word, List<GraphemeUnit> units, List<int> boundaries)
    {
        int syllables = boundaries.Count;
        if (syllables == 0)
        {
            return 0;
        }

        int accentIndex = word.IndexOfAny(StressAccentChars);
        if (accentIndex >= 0)
        {
            int accentUnit = 0;
            int offset = 0;
            for (int u = 0; u < units.Count; u++)
            {
                int length = units[u].Grapheme.Length;
                if (offset <= accentIndex && accentIndex < offset + length)
                {
                    accentUnit = u;
                    break;
                }

                offset += length;
            }

            for (int s = syllables - 1; s >= 0; s--)
            {
                if (boundaries[s] <= accentUnit)
                {
                    return s;
                }
            }

            return 0;
        }

        if (syllables == 1)
        {
            return 0;
        }

        char last = BaseChar(word[^1]);
        return Vowels.Contains(last) || last == 'n' || last == 's'
            ? Math.Max(0, syllables - 2)
            : syllables - 1;
    }

    /// <summary>
    /// Phonemes a unit produces, for mapping the stressed unit to a phoneme
    /// index (<c>_phoneme_count_for_unit</c>): silent h 0, gü 2, x 2, other
    /// units 1. Python counts "xc" as 1 although it produces k s; the port
    /// keeps that, so the mark lands where Python puts it.
    /// </summary>
    private static int PhonemeCountForUnit(string grapheme)
    {
        string b = BaseWord(grapheme);
        if (b == "h")
        {
            return 0;
        }

        if (b.Length == 2 && b[0] == 'g' && grapheme[1] == 'ü')
        {
            return 2;
        }

        return b == "x" ? 2 : 1;
    }

    /// <summary>
    /// Inserts <c>ˈ</c> before the phoneme of the stressed syllable's first
    /// vowel (<c>_insert_stress_marker</c>); past the end it is appended, as
    /// Python's list slicing does.
    /// </summary>
    private static List<string> InsertStressMarker(
        List<string> phonemes, List<GraphemeUnit> units, List<int> boundaries, int stressedSyllable)
    {
        if (phonemes.Count == 0 || boundaries.Count == 0 || stressedSyllable >= boundaries.Count)
        {
            return phonemes;
        }

        int start = boundaries[stressedSyllable];
        int end = stressedSyllable + 1 < boundaries.Count ? boundaries[stressedSyllable + 1] : units.Count;

        int stressedUnit = -1;
        for (int u = start; u < end && u < units.Count; u++)
        {
            if (units[u].IsVowel)
            {
                stressedUnit = u;
                break;
            }
        }

        if (stressedUnit < 0)
        {
            return phonemes;
        }

        int phonemeIndex = 0;
        for (int u = 0; u < stressedUnit; u++)
        {
            phonemeIndex += PhonemeCountForUnit(units[u].Grapheme);
        }

        var result = new List<string>(phonemes);
        result.Insert(Math.Min(phonemeIndex, result.Count), Stress);
        return result;
    }
}
