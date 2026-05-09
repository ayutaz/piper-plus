using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Convert Mandarin pinyin syllables to IPA tokens. Independent C# port of
/// Python <c>piper_plus_g2p.chinese._pinyin_to_ipa</c>; does not depend on
/// the <c>DotNetG2P.Chinese</c> NuGet package (TICKET-03 §8.2 X7).
/// <para>
/// Output is byte-for-byte identical to the Python reference and the Rust /
/// Go mirrors so that a single ZH-EN model can be served by any runtime.
/// </para>
/// </summary>
internal static class PinyinToIpa
{
    /// <summary>
    /// Pinyin initial -> IPA mapping. Mandarin phonology:
    /// b=[p], p=[pʰ], d=[t], t=[tʰ], g=[k], k=[kʰ] (aspiration distinction).
    /// </summary>
    internal static readonly IReadOnlyDictionary<string, string> InitialToIpa =
        new Dictionary<string, string>
        {
            ["b"] = "p",
            ["p"] = "pʰ",
            ["m"] = "m",
            ["f"] = "f",
            ["d"] = "t",
            ["t"] = "tʰ",
            ["n"] = "n",
            ["l"] = "l",
            ["g"] = "k",
            ["k"] = "kʰ",
            ["h"] = "x",
            ["j"] = "tɕ",
            ["q"] = "tɕʰ",
            ["x"] = "ɕ",
            ["zh"] = "tʂ",
            ["ch"] = "tʂʰ",
            ["sh"] = "ʂ",
            ["r"] = "ɻ",
            ["z"] = "ts",
            ["c"] = "tsʰ",
            ["s"] = "s",
        };

    /// <summary>Pinyin final -> IPA mapping (compound finals as single tokens).</summary>
    internal static readonly IReadOnlyDictionary<string, string> FinalToIpa =
        new Dictionary<string, string>
        {
            ["a"] = "a",
            ["o"] = "o",
            ["e"] = "ɤ", // ɤ
            ["i"] = "i",
            ["u"] = "u",
            ["ü"] = "y_vowel", // ü
            ["v"] = "y_vowel",
            ["ai"] = "aɪ", // aɪ
            ["ei"] = "eɪ", // eɪ
            ["ao"] = "aʊ", // aʊ
            ["ou"] = "oʊ", // oʊ
            ["an"] = "an",
            ["en"] = "ən",         // ən
            ["ang"] = "aŋ",        // aŋ
            ["eng"] = "əŋ",   // əŋ
            ["ong"] = "uŋ",        // uŋ
            ["er"] = "ɚ",          // ɚ
            ["ia"] = "ia",
            ["ie"] = "iɛ",          // iɛ
            ["iao"] = "iaʊ",         // iaʊ
            ["iu"] = "iou",
            ["iou"] = "iou",
            ["ian"] = "iɛn",         // iɛn
            ["in"] = "in",
            ["iang"] = "iaŋ",        // iaŋ
            ["ing"] = "iŋ",          // iŋ
            ["iong"] = "iuŋ",        // iuŋ
            ["ua"] = "ua",
            ["uo"] = "uo",
            ["uai"] = "uaɪ",         // uaɪ
            ["ui"] = "ueɪ",          // ueɪ
            ["uei"] = "ueɪ",         // ueɪ
            ["uan"] = "uan",
            ["un"] = "uən",          // uən
            ["uen"] = "uən",         // uən
            ["uang"] = "uaŋ",        // uaŋ
            ["ueng"] = "uəŋ",   // uəŋ
            ["üe"] = "yɛ",      // yɛ
            ["ve"] = "yɛ",
            ["üan"] = "yɛn",    // yɛn
            ["van"] = "yɛn",
            ["ün"] = "yn",           // yn
            ["vn"] = "yn",
            ["-i_retroflex"] = "ɻ̩", // ɻ̩
            ["-i_alveolar"] = "ɨ",        // ɨ
        };

    private static readonly string[] InitialsOrder =
    {
        "zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h",
        "j", "q", "x", "r", "z", "c", "s",
    };

    private static readonly HashSet<string> RetroflexInitials = new() { "zh", "ch", "sh", "r" };
    private static readonly HashSet<string> AlveolarInitials = new() { "z", "c", "s" };

    /// <summary>
    /// Normalize pinyin y/w conventions and v→ü to canonical form.
    /// e.g. yi→i, ya→ia, wu→u, wa→ua, nv→nü.
    /// </summary>
    /// <returns></returns>
    internal static string NormalizePinyin(string py)
    {
        var s = py.Replace("v", "ü");
        if (s.StartsWith("yu"))
        {
            return s.Length > 2 ? "ü" + s.Substring(2) : "ü";
        }

        if (s.StartsWith('y'))
        {
            var rest = s.Substring(1);
            return rest.StartsWith('i') ? rest : "i" + rest;
        }

        if (s.StartsWith('w'))
        {
            var rest = s.Substring(1);
            return rest.StartsWith('u') ? rest : "u" + rest;
        }

        return s;
    }

    /// <summary>Split a normalized pinyin syllable into (initial, final).</summary>
    /// <returns></returns>
    internal static (string Initial, string Final) SplitPinyin(string pinyin)
    {
        foreach (var init in InitialsOrder)
        {
            if (pinyin.StartsWith(init))
            {
                var final = pinyin.Substring(init.Length);
                if (final == "i")
                {
                    if (RetroflexInitials.Contains(init))
                    {
                        return (init, "-i_retroflex");
                    }

                    if (AlveolarInitials.Contains(init))
                    {
                        return (init, "-i_alveolar");
                    }
                }

                if ((init == "j" || init == "q" || init == "x") && final.StartsWith('u'))
                {
                    final = "ü" + final.Substring(1);
                }

                return (init, final);
            }
        }

        return (string.Empty, pinyin);
    }

    /// <summary>Extract trailing tone digit (1-5) from a pinyin syllable.</summary>
    /// <returns></returns>
    internal static (string Base, int Tone) ExtractTone(string syllable)
    {
        if (syllable.Length == 0)
        {
            return (string.Empty, 5);
        }

        var last = syllable[syllable.Length - 1];
        if (last >= '1' && last <= '5')
        {
            return (syllable.Substring(0, syllable.Length - 1), last - '0');
        }

        return (syllable, 5);
    }

    /// <summary>
    /// Convert a single pinyin syllable (without tone digit) to IPA tokens.
    /// Tone marker is appended as <c>"toneN"</c>.
    /// </summary>
    /// <returns></returns>
    internal static List<string> Convert(string syllable, int tone)
    {
        (string? initial, string? final) = SplitPinyin(syllable);
        var tokens = new List<string>();

        if (initial.Length > 0 && InitialToIpa.TryGetValue(initial, out var initIpa))
        {
            tokens.Add(initIpa);
        }

        if (final.Length > 0)
        {
            if (FinalToIpa.TryGetValue(final, out var finalIpa))
            {
                tokens.Add(finalIpa);
            }
            else
            {
                // Fallback: decompose unknown finals char-by-char
                foreach (var ch in final)
                {
                    var key = ch.ToString();
                    if (FinalToIpa.TryGetValue(key, out var chIpa))
                    {
                        tokens.Add(chIpa);
                    }
                    else if (char.IsLetter(ch))
                    {
                        tokens.Add(key);
                    }
                }
            }
        }

        if (tone >= 1 && tone <= 5)
        {
            tokens.Add($"tone{tone}");
        }

        return tokens;
    }

    /// <summary>
    /// Apply Mandarin tone sandhi: T3+T3 → T2+T3, yi/bu rules.
    /// </summary>
    internal static void ApplyToneSandhi(List<(string Syllable, int Tone)> st)
    {
        for (int i = 0; i < st.Count - 1; i++)
        {
            var toneI = st[i].Tone;
            var toneNext = st[i + 1].Tone;

            // Rule 1: T3 + T3 -> T2 + T3
            if (toneI == 3 && toneNext == 3)
            {
                st[i] = (st[i].Syllable, 2);
                continue;
            }

            // Rule 2 & 3: yi tone sandhi
            if (st[i].Syllable == "i" && toneI == 1)
            {
                if (toneNext == 4)
                {
                    st[i] = (st[i].Syllable, 2);
                }
                else if (toneNext >= 1 && toneNext <= 3)
                {
                    st[i] = (st[i].Syllable, 4);
                }

                continue;
            }

            // Rule 4: bu T4 + T4 -> T2 + T4
            if (st[i].Syllable == "bu" && toneI == 4 && toneNext == 4)
            {
                st[i] = (st[i].Syllable, 2);
            }
        }
    }
}
