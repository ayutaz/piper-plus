using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Rule-based French G2P engine implementing <see cref="IFrenchG2PEngine"/>.
/// <para>
/// A port of <c>src/python/g2p/piper_plus_g2p/french.py</c>, the French G2P
/// the models were trained with:
/// <list type="number">
///   <item>Normalization: trim, NFC, lowercase, collapse whitespace.</item>
///   <item>Tokenization (<c>_split_words</c>): letters with inner apostrophes;
///         elision clitics (l' d' j' n' s' c' m' t' qu') merge with the rest
///         of the word; punctuation characters are single tokens.</item>
///   <item>Grapheme-to-phoneme rules per word (<c>_convert_word</c>).</item>
///   <item>Obligatory liaison (<c>_apply_liaison</c>): a trigger word ends
///         with its linking consonant before a vowel-initial word.</item>
/// </list>
/// </para>
/// <para>
/// The output follows the <see cref="IFrenchG2PEngine"/> conventions: a space
/// token before every word except the first, punctuation attached to the
/// preceding word, and nasal vowels / <c>y_vowel</c> as multi-character
/// tokens.
/// </para>
/// </summary>
public sealed class FrenchG2PEngine : IFrenchG2PEngine
{
    // =================================================================
    // Character classes (french.py _PUNCTUATION / _VOWELS / _CONSONANTS)
    // =================================================================
    private const string Punctuation = ",.;:!?\u00a1\u00bf\u2014\u2013\u2026\u00ab\u00bb";
    private const string Vowels = "aeiouy\u00e0\u00e2\u00e6\u00e9\u00e8\u00ea\u00eb\u00ee\u00ef\u00f4\u00f9\u00fb\u00fc\u0153";
    private const string Consonants = "bcdfghjklmnpqrstvwxz";
    private const string SilentFinal = "dghmnpstxz";

    // Letters of the _split_words pattern: a-z, the vowels above, ç and ñ.
    private const string ExtraLetters = "\u00e0\u00e2\u00e6\u00e9\u00e8\u00ea\u00eb\u00ee\u00ef\u00f4\u00f9\u00fb\u00fc\u0153\u00e7\u00f1";

    private const string NasalEin = "\u025b\u0303"; // ɛ̃
    private const string NasalAn = "\u0251\u0303"; // ɑ̃
    private const string NasalOn = "\u0254\u0303"; // ɔ̃
    private const string OpenE = "\u025b"; // ɛ
    private const string OpenO = "\u0254"; // ɔ
    private const string Schwa = "\u0259"; // ə

    private static readonly HashSet<string> IlleAsIl = ["ville", "mille", "tranquille"];

    private static readonly HashSet<string> ErAsEhr =
    [
        "hiver", "enfer", "amer", "cancer", "super", "laser", "hamster",
        "master", "poster", "cluster", "starter", "leader", "transfer", "fer",
    ];

    private static readonly HashSet<string> ElisionClitics = ["l", "d", "j", "n", "s", "c", "m", "t", "qu"];

    private static readonly Dictionary<string, string> LiaisonWords = new()
    {
        ["les"] = "z",
        ["des"] = "z",
        ["ces"] = "z",
        ["mes"] = "z",
        ["tes"] = "z",
        ["ses"] = "z",
        ["nos"] = "z",
        ["vos"] = "z",
        ["aux"] = "z",
        ["petits"] = "z",
        ["grands"] = "z",
        ["gros"] = "z",
        ["deux"] = "z",
        ["trois"] = "z",
        ["six"] = "z",
        ["dix"] = "z",
        ["nous"] = "z",
        ["vous"] = "z",
        ["ils"] = "z",
        ["elles"] = "z",
        ["on"] = "n",
        ["en"] = "n",
        ["dans"] = "z",
        ["sans"] = "z",
        ["chez"] = "z",
        ["un"] = "n",
        ["mon"] = "n",
        ["ton"] = "n",
        ["son"] = "n",
        ["tout"] = "t",
        ["quand"] = "t",
        ["tr\u00e8s"] = "z",
        ["plus"] = "z",
        ["est"] = "t",
        ["ont"] = "t",
        ["sont"] = "t",
        ["font"] = "t",
        ["vont"] = "t",
    };

    private static readonly Dictionary<char, string> SimpleConsonants = new()
    {
        ['b'] = "b",
        ['d'] = "d",
        ['f'] = "f",
        ['k'] = "k",
        ['l'] = "l",
        ['m'] = "m",
        ['n'] = "n",
        ['p'] = "p",
        ['s'] = "s",
        ['t'] = "t",
        ['v'] = "v",
        ['w'] = "w",
        ['z'] = "z",
    };

    private static readonly Regex S_whitespace = new(@"\s+", RegexOptions.Compiled);

    /// <inheritdoc />
    public List<string> ToPhonemeList(string text)
    {
        var result = new List<string>();
        if (string.IsNullOrEmpty(text))
        {
            return result;
        }

        string normalized = Normalize(text);
        List<string> words = SplitWords(normalized);

        bool needSpace = false;
        for (int t = 0; t < words.Count; t++)
        {
            string word = words[t];
            bool isPunct = IsPunctuationToken(word);
            if (!isPunct && needSpace)
            {
                result.Add(" ");
            }

            if (isPunct)
            {
                result.Add(word);
            }
            else
            {
                result.AddRange(ConvertWord(word));

                // Liaison (_apply_liaison): the linking consonant ends this word
                // when the next token is a word starting with a vowel sound.
                // Punctuation in between blocks it.
                if (LiaisonWords.TryGetValue(word, out string? linking)
                    && t + 1 < words.Count
                    && !IsPunctuationToken(words[t + 1])
                    && StartsWithVowelSound(words[t + 1]))
                {
                    result.Add(linking);
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

    private static bool IsVowel(char ch) => Vowels.Contains(ch);

    private static bool IsConsonant(char ch) => Consonants.Contains(ch);

    private static bool IsSilentFinal(char ch) => SilentFinal.Contains(ch);

    private static bool IsLetter(char ch) => (ch >= 'a' && ch <= 'z') || ExtraLetters.Contains(ch);

    private static bool IsPunctuationToken(string token) => token.Length == 1 && Punctuation.Contains(token[0]);

    /// <summary>
    /// Splits like <c>_split_words</c>: a word is a run of letters that may
    /// contain apostrophes between letters (typographic apostrophes count as
    /// apostrophes); punctuation characters are single tokens; anything else
    /// is dropped. In a word with apostrophes, an elision clitic starts a
    /// merge: it and every later part become one word (<c>qu'il</c> →
    /// <c>quil</c>); other parts are words of their own (<c>aujourd'hui</c> →
    /// <c>aujourd</c> + <c>hui</c>).
    /// </summary>
    private static List<string> SplitWords(string text)
    {
        string s = text.Replace('\u2019', '\'').Replace('\u2018', '\'');
        var tokens = new List<string>();
        int n = s.Length;
        int i = 0;
        while (i < n)
        {
            char ch = s[i];
            if (Punctuation.Contains(ch))
            {
                tokens.Add(ch.ToString());
                i++;
                continue;
            }

            if (!IsLetter(ch))
            {
                i++;
                continue;
            }

            // Split the word at its inner apostrophes.
            var parts = new List<string>();
            var part = new StringBuilder();
            while (i < n)
            {
                if (IsLetter(s[i]))
                {
                    part.Append(s[i]);
                    i++;
                }
                else if (s[i] == '\'' && i + 1 < n && IsLetter(s[i + 1]))
                {
                    parts.Add(part.ToString());
                    part.Clear();
                    i++;
                }
                else
                {
                    break;
                }
            }

            parts.Add(part.ToString());

            var merged = new StringBuilder();
            for (int k = 0; k < parts.Count; k++)
            {
                if (merged.Length > 0)
                {
                    merged.Append(parts[k]);
                }
                else if (k < parts.Count - 1 && ElisionClitics.Contains(parts[k]))
                {
                    merged.Append(parts[k]);
                }
                else
                {
                    tokens.Add(parts[k]);
                }
            }

            if (merged.Length > 0)
            {
                tokens.Add(merged.ToString());
            }
        }

        return tokens;
    }

    /// <summary>
    /// A vowel letter, or <c>h</c> and a vowel (<c>_starts_with_vowel_sound</c>;
    /// h aspiré is not distinguished).
    /// </summary>
    private static bool StartsWithVowelSound(string word)
    {
        if (word.Length == 0)
        {
            return false;
        }

        if (IsVowel(word[0]))
        {
            return true;
        }

        return word[0] == 'h' && word.Length > 1 && IsVowel(word[1]);
    }

    // =================================================================
    // Grapheme-to-phoneme rules (_convert_word)
    // =================================================================
    // word[start:start+s.Length] == s (a slice past the end never matches).
    private static bool At(string word, int start, string s) =>
        start >= 0 && start + s.Length <= word.Length && string.CompareOrdinal(word, start, s, 0, s.Length) == 0;

    private static bool AllConsonants(string s)
    {
        foreach (char c in s)
        {
            if (!IsConsonant(c))
            {
                return false;
            }
        }

        return true;
    }

    private static bool AnyPronounced(string s)
    {
        foreach (char c in s)
        {
            if (!IsSilentFinal(c))
            {
                return true;
            }
        }

        return false;
    }

    // "an"/"in"/"on"/"un"/"yn" (+ m): nasal at the end, or before a consonant
    // other than a doubled n/m.
    private static bool IsNasalContext(string word, int i)
    {
        int n = word.Length;
        if (i + 1 >= n || (word[i + 1] != 'n' && word[i + 1] != 'm'))
        {
            return false;
        }

        return i + 2 >= n || (!IsVowel(word[i + 2]) && word[i + 2] != word[i + 1]);
    }

    private static bool EndsOrBeforeConsonant(string word, int p) => p >= word.Length || !IsVowel(word[p]);

    internal static List<string> ConvertWord(string word)
    {
        var ph = new List<string>();
        int n = word.Length;
        int i = 0;

        while (i < n)
        {
            char ch = word[i];

            // -er word-final in polysyllabic words (parler) -> /e/; "mer",
            // "fer" and the ErAsEhr words keep /ɛʁ/.
            if (ch == 'e' && i + 1 == n - 1 && word[i + 1] == 'r')
            {
                int vowelCount = 0;
                foreach (char c in word)
                {
                    if (IsVowel(c))
                    {
                        vowelCount++;
                    }
                }

                if (vowelCount >= 2 && !ErAsEhr.Contains(word))
                {
                    ph.Add("e");
                    i += 2;
                    continue;
                }
            }

            if (ch == 'e' && i + 2 < n && At(word, i + 1, "au"))
            {
                ph.Add("o");
                i += 3;
                continue;
            }

            if (ch == 'o' && At(word, i + 1, "uille") && EndsOrBeforeConsonant(word, i + 6))
            {
                ph.Add("u");
                ph.Add("j");
                i += 6;
                continue;
            }

            if (ch == 'a' && At(word, i + 1, "ille") && EndsOrBeforeConsonant(word, i + 5))
            {
                ph.Add("a");
                ph.Add("j");
                i += 5;
                continue;
            }

            if (ch == 'e' && At(word, i + 1, "uille") && i + 6 >= n)
            {
                ph.Add("\u0153");
                ph.Add("j");
                i += 6;
                continue;
            }

            if (ch == 'e' && i + 2 < n && At(word, i + 1, "il") && i + 3 >= n)
            {
                ph.Add(OpenE);
                ph.Add("j");
                i += 3;
                continue;
            }

            if (ch == 'e' && At(word, i + 1, "ille") && EndsOrBeforeConsonant(word, i + 5))
            {
                ph.Add(OpenE);
                ph.Add("j");
                i += 5;
                continue;
            }

            // "ain"/"aim", "ein"/"eim" -> ɛ̃
            if ((ch == 'a' || ch == 'e') && i + 2 < n && word[i + 1] == 'i'
                && (word[i + 2] == 'n' || word[i + 2] == 'm') && EndsOrBeforeConsonant(word, i + 3))
            {
                ph.Add(NasalEin);
                i += 3;
                continue;
            }

            if (ch == 'o' && i + 2 < n && At(word, i + 1, "in") && EndsOrBeforeConsonant(word, i + 3))
            {
                ph.Add("w");
                ph.Add(NasalEin);
                i += 3;
                continue;
            }

            if (ch == 'i' && i + 2 < n && At(word, i + 1, "en") && EndsOrBeforeConsonant(word, i + 3))
            {
                ph.Add("j");
                ph.Add(NasalEin);
                i += 3;
                continue;
            }

            // "tion" -> /sjɔ̃/; "stion" -> /stjɔ̃/
            if (ch == 't' && i + 3 < n && At(word, i + 1, "ion") && EndsOrBeforeConsonant(word, i + 4))
            {
                ph.Add(i > 0 && word[i - 1] == 's' ? "t" : "s");
                ph.Add("j");
                ph.Add(NasalOn);
                i += 4;
                continue;
            }

            if (ch == 'i' && i + 3 < n && At(word, i + 1, "lle") && EndsOrBeforeConsonant(word, i + 4))
            {
                ph.Add("i");
                ph.Add(IlleAsIl.Contains(word) ? "l" : "j");
                i += 4;
                continue;
            }

            if (ch == 'g' && i + 1 < n && word[i + 1] == 'n')
            {
                ph.Add("\u0272"); // ɲ
                i += 2;
                continue;
            }

            if (ch == 'p' && i + 1 < n && word[i + 1] == 'h')
            {
                ph.Add("f");
                i += 2;
                continue;
            }

            if (ch == 't' && i + 1 < n && word[i + 1] == 'h')
            {
                ph.Add("t");
                i += 2;
                continue;
            }

            if (ch == 'c' && i + 1 < n && word[i + 1] == 'h')
            {
                ph.Add("\u0283"); // ʃ
                i += 2;
                continue;
            }

            if (ch == 'q' && i + 1 < n && word[i + 1] == 'u')
            {
                ph.Add("k");
                i += 2;
                continue;
            }

            if (ch == 'g' && i + 2 < n && word[i + 1] == 'u'
                && "ei\u00e9\u00e8\u00ea\u00eb\u00ee\u00ef".Contains(word[i + 2]))
            {
                ph.Add("\u0261"); // ɡ
                i += 2;
                continue;
            }

            // Nasal vowels
            if ((ch == 'a' || ch == 'e') && IsNasalContext(word, i))
            {
                ph.Add(NasalAn);
                i += 2;
                continue;
            }

            if ((ch == 'i' || ch == 'u' || ch == 'y') && IsNasalContext(word, i))
            {
                ph.Add(NasalEin);
                i += 2;
                continue;
            }

            if (ch == 'o' && IsNasalContext(word, i))
            {
                ph.Add(NasalOn);
                i += 2;
                continue;
            }

            // Vowel digraphs
            if (ch == 'o' && i + 1 < n && word[i + 1] == 'u')
            {
                ph.Add("u");
                i += 2;
                continue;
            }

            if (ch == 'a' && i + 1 < n && word[i + 1] == 'u')
            {
                ph.Add("o");
                i += 2;
                continue;
            }

            if (ch == 'o' && i + 1 < n && word[i + 1] == 'i')
            {
                ph.Add("w");
                ph.Add("a");
                i += 2;
                continue;
            }

            if ((ch == 'a' || ch == 'e') && i + 1 < n && word[i + 1] == 'i')
            {
                ph.Add(OpenE);
                i += 2;
                continue;
            }

            // "eu" / "\u0153u": open before a pronounced consonant, closed otherwise.
            if ((ch == 'e' || ch == '\u0153') && i + 1 < n && word[i + 1] == 'u')
            {
                bool open = i + 2 < n && IsConsonant(word[i + 2]) && !IsSilentFinal(word[i + 2]);
                ph.Add(open ? "\u0153" : "\u00f8");
                i += 2;
                continue;
            }

            // Single vowels
            switch (ch)
            {
                case '\u00e9': // é
                    ph.Add("e");
                    i++;
                    continue;
                case '\u00e8': // è
                case '\u00ea': // ê
                case '\u00eb': // ë
                    ph.Add(OpenE);
                    i++;
                    continue;
                case '\u00e0': // à
                case '\u00e2': // â
                case 'a':
                    ph.Add("a");
                    i++;
                    continue;
                case '\u00ee': // î
                case '\u00ef': // ï
                    ph.Add("i");
                    i++;
                    continue;
                case 'i':
                    // Glide before a vowel, except before a word-final silent e (vie).
                    if (i + 1 < n && IsVowel(word[i + 1]) && !(i + 1 == n - 1 && word[i + 1] == 'e'))
                    {
                        ph.Add("j");
                    }
                    else
                    {
                        ph.Add("i");
                    }

                    i++;
                    continue;
                case '\u00f4': // ô
                    ph.Add("o");
                    i++;
                    continue;
                case 'o':
                    {
                        // Open /ɔ/ before pronounced final consonant(s), ignoring a
                        // trailing silent e/es (porte, homme).
                        string effective = word.Substring(i + 1);
                        if (effective.EndsWith("es", StringComparison.Ordinal))
                        {
                            effective = effective.Substring(0, effective.Length - 2);
                        }
                        else if (effective.EndsWith('e'))
                        {
                            effective = effective.Substring(0, effective.Length - 1);
                        }

                        ph.Add(effective.Length > 0 && AllConsonants(effective) && AnyPronounced(effective) ? OpenO : "o");
                        i++;
                        continue;
                    }

                case '\u00f9': // ù
                case '\u00fb': // û
                case '\u00fc': // ü
                    ph.Add("y_vowel");
                    i++;
                    continue;
                case 'u':
                    if (i + 1 < n && word[i + 1] == 'i')
                    {
                        ph.Add("\u0265"); // ɥ
                        ph.Add("i");
                        i += 2;
                        continue;
                    }

                    ph.Add("y_vowel");
                    i++;
                    continue;
                case 'y':
                    ph.Add(i + 1 < n && IsVowel(word[i + 1]) ? "j" : "i");
                    i++;
                    continue;
                case '\u0153': // œ
                    ph.Add("\u0153");
                    i++;
                    continue;
                case '\u00e6': // æ
                    ph.Add("e");
                    i++;
                    continue;
                case 'e':
                    {
                        // Word-final e is silent.
                        if (i == n - 1)
                        {
                            i++;
                            continue;
                        }

                        // ɛ in a closed syllable: before 2+ consonants, or before only
                        // consonants of which at least one is pronounced.
                        string remaining = word.Substring(i + 1);
                        int consonantCount = 0;
                        foreach (char c in remaining)
                        {
                            if (!IsConsonant(c))
                            {
                                break;
                            }

                            consonantCount++;
                        }

                        bool closed = consonantCount >= 2 || (AllConsonants(remaining) && AnyPronounced(remaining));
                        ph.Add(closed ? OpenE : Schwa);
                        i++;
                        continue;
                    }
            }

            // Consonants
            switch (ch)
            {
                case 'c':
                    ph.Add(i + 1 < n && "eiy\u00e9\u00e8\u00ea\u00eb".Contains(word[i + 1]) ? "s" : "k");
                    i++;
                    continue;
                case '\u00e7': // ç
                    ph.Add("s");
                    i++;
                    continue;
                case 'g':
                    ph.Add(i + 1 < n && "eiy\u00e9\u00e8\u00ea\u00eb".Contains(word[i + 1]) ? "\u0292" : "\u0261");
                    i++;
                    continue;
                case 'j':
                    ph.Add("\u0292"); // ʒ
                    i++;
                    continue;
                case 'r':
                    ph.Add("\u0281"); // ʁ
                    i += i + 1 < n && word[i + 1] == 'r' ? 2 : 1;
                    continue;
                case 'x':
                    {
                        // Silent at the end and before a final silent e/es.
                        string after = word.Substring(i + 1);
                        if (i == n - 1 || after == "e" || after == "es")
                        {
                            i++;
                            continue;
                        }

                        // "ex" + vowel -> /ɡz/
                        if (i > 0 && word[i - 1] == 'e' && i + 1 < n && IsVowel(word[i + 1]))
                        {
                            ph.Add("\u0261");
                            ph.Add("z");
                            i++;
                            continue;
                        }

                        ph.Add("k");
                        ph.Add("s");
                        i++;
                        continue;
                    }

                case 'h':
                    i++;
                    continue;
            }

            if (SimpleConsonants.TryGetValue(ch, out string? simple))
            {
                // A word-final consonant, or one before a final s (temps), is
                // silent when it is a silent-final letter.
                bool isFinal = i == n - 1 || (i == n - 2 && word[n - 1] == 's');
                if (isFinal && IsSilentFinal(ch))
                {
                    i++;
                    continue;
                }

                // Intervocalic single s -> /z/
                if (ch == 's' && i > 0 && IsVowel(word[i - 1]) && i + 1 < n && IsVowel(word[i + 1]))
                {
                    ph.Add("z");
                    i++;
                    continue;
                }

                ph.Add(simple);
                i += i + 1 < n && word[i + 1] == ch ? 2 : 1;
                continue;
            }

            if (Punctuation.Contains(ch))
            {
                ph.Add(ch.ToString());
            }

            i++;
        }

        return ph;
    }
}
