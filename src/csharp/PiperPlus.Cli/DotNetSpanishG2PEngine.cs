using System.Globalization;
using PiperPlus.Core.Phonemize;
using DotNetG2P.Spanish;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="SpanishG2PEngine"/> from DotNetG2P.Spanish
/// to implement <see cref="ISpanishG2PEngine"/>.
/// </summary>
internal sealed class DotNetSpanishG2PEngine : ISpanishG2PEngine
{
    private readonly SpanishG2PEngine _engine = new();

    public List<string> ToPhonemeList(string text)
    {
        // dot-net-g2p ToIPA returns IPA string with stress markers.
        // Convert to flat token list matching piper-plus format.
        string ipa = _engine.ToIPA(text);

        return IpaTokenize(ipa);
    }

    /// <summary>
    /// Tokenize an IPA string into individual phoneme tokens, preserving
    /// multi-character IPA sequences that map to PUA codepoints.
    /// <list type="bullet">
    ///   <item>"rr" — alveolar trill (U+E01D)</item>
    ///   <item>"tʃ" (t + U+0283) — voiceless postalveolar affricate (U+E054)</item>
    ///   <item>"dʒ" (d + U+0292) — voiced postalveolar affricate (U+E055)</item>
    /// </list>
    /// Unicode combining characters (U+0300–U+036F) are kept with their
    /// preceding base character as a single token.
    /// </summary>
    private static List<string> IpaTokenize(string ipa)
    {
        var tokens = new List<string>();
        int i = 0;
        while (i < ipa.Length)
        {
            if (ipa[i] == ' ')
            {
                tokens.Add(" ");
                i++;
                continue;
            }

            // Check for known digraphs: "rr", "tʃ" (t+U+0283), "dʒ" (d+U+0292)
            if (i + 1 < ipa.Length)
            {
                string pair = ipa.Substring(i, 2);
                if (pair == "rr" || pair == "t\u0283" || pair == "d\u0292")
                {
                    tokens.Add(pair);
                    i += 2;
                    continue;
                }
            }

            // Base character + any combining characters (U+0300–U+036F range)
            int start = i;
            i++;
            while (i < ipa.Length &&
                   char.GetUnicodeCategory(ipa[i]) == UnicodeCategory.NonSpacingMark)
            {
                i++;
            }
            tokens.Add(ipa.Substring(start, i - start));
        }
        return tokens;
    }
}
