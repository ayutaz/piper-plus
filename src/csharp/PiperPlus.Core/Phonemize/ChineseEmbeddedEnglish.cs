using System.Collections.Generic;
using PiperPlus.Core.Mapping;
using PiperPlus.Core.Phonemize.Data;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// ZH-EN code-switching: phonemize English text embedded in Chinese context as
/// Mandarin pinyin. Independent of <c>DotNetG2P.Chinese</c> NuGet — uses the
/// in-tree <see cref="PinyinToIpa"/> port. (TICKET-03 §8.2 X7, design §2.3.)
/// </summary>
public static class ChineseEmbeddedEnglish
{
    /// <summary>
    /// Tokenize and convert embedded English text to Mandarin pinyin IPA.
    /// </summary>
    /// <param name="text">English text segment (e.g. <c>"GPS"</c>, <c>"ChatGPT"</c>).</param>
    /// <param name="data">Loanword dictionary (default: <see cref="LoanwordDataLoader.Default"/>).</param>
    /// <returns>
    /// A <see cref="ChineseG2PResult"/> with PUA-mapped tokens and prosody A1/A2/A3
    /// filled with zeros (embedded EN has no Chinese-style tone/word context).
    /// </returns>
    public static ChineseG2PResult Convert(string text, LoanwordData? data = null)
    {
        data ??= LoanwordDataLoader.Default;

        var pinyinSyllables = new List<string>();
        foreach (var token in TokenizeAlnum(text))
        {
            // 1. Case-sensitive loanword
            if (data.Loanwords.TryGetValue(token, out var loanSyl))
            {
                foreach (var s in loanSyl) pinyinSyllables.Add(s);
                continue;
            }
            // 2. Uppercase acronym
            var upper = token.ToUpperInvariant();
            if (data.Acronyms.TryGetValue(upper, out var acroSyl))
            {
                foreach (var s in acroSyl) pinyinSyllables.Add(s);
                continue;
            }
            // 3. Letter-by-letter fallback (digits silently dropped)
            foreach (var ch in upper)
            {
                if (char.IsDigit(ch)) continue;
                if (data.LetterFallback.TryGetValue(ch.ToString(), out var letterSyl))
                {
                    foreach (var s in letterSyl) pinyinSyllables.Add(s);
                }
            }
        }

        if (pinyinSyllables.Count == 0)
            return new ChineseG2PResult(System.Array.Empty<string>(), System.Array.Empty<int>(), System.Array.Empty<int>(), System.Array.Empty<int>());

        var tokens = PhonemizeFromPinyinSyllables(pinyinSyllables);

        // Embedded EN: prosody filled with zeros (matches Python ProsodyInfo
        // contract for the zero-context case; design §8.5).
        var n = tokens.Count;
        var zeros = new int[n];
        return new ChineseG2PResult(tokens, zeros, zeros, zeros);
    }

    /// <summary>
    /// Convert pinyin syllables to PUA-mapped IPA tokens.
    /// Mirrors Python <c>phonemize_from_pinyin_syllables(..., chinese_text="")</c>.
    /// </summary>
    internal static IReadOnlyList<string> PhonemizeFromPinyinSyllables(
        IReadOnlyList<string> syllables)
    {
        if (syllables.Count == 0) return System.Array.Empty<string>();

        // Step 1: extract tone, normalize
        var st = new List<(string Syllable, int Tone)>(syllables.Count);
        foreach (var s in syllables)
        {
            var (baseSyl, tone) = PinyinToIpa.ExtractTone(s);
            st.Add((PinyinToIpa.NormalizePinyin(baseSyl), tone));
        }

        // Step 2: tone sandhi
        PinyinToIpa.ApplyToneSandhi(st);

        // Step 3: pinyin -> IPA tokens
        var tokens = new List<string>(syllables.Count * 3);
        foreach (var (syl, tone) in st)
        {
            var ipa = PinyinToIpa.Convert(syl, tone);
            tokens.AddRange(ipa);
        }

        // Step 4: multi-char IPA -> PUA codepoint mapping
        return OpenJTalkToPiperMapping.MapSequence(tokens);
    }

    /// <summary>
    /// Tokenize text into alphanumeric runs. Mirrors Python
    /// <c>_RE_TOKEN_SPLIT = re.compile(r"[A-Za-z0-9]+")</c>.
    /// </summary>
    internal static List<string> TokenizeAlnum(string text)
    {
        var result = new List<string>();
        var current = new System.Text.StringBuilder();
        foreach (var ch in text)
        {
            bool isAlnum = (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9');
            if (isAlnum)
                current.Append(ch);
            else if (current.Length > 0)
            {
                result.Add(current.ToString());
                current.Clear();
            }
        }
        if (current.Length > 0)
            result.Add(current.ToString());
        return result;
    }
}
