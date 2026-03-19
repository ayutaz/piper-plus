using System.Globalization;
using PiperPlus.Core.Phonemize;
using DotNetG2P.Portuguese;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="PortugueseG2PEngine"/> from DotNetG2P.Portuguese
/// to implement <see cref="IPortugueseG2PEngine"/>.
/// Brazilian Portuguese is the default dialect.
/// </summary>
internal sealed class DotNetPortugueseG2PEngine : IPortugueseG2PEngine
{
    private readonly PortugueseG2PEngine _engine = new();

    public List<string> ToPhonemeList(string text)
    {
        // dot-net-g2p ToIPA returns IPA string with stress markers.
        // Convert to flat token list matching piper-plus format.
        string ipa = _engine.ToIPA(text);

        return IpaTokenize(ipa);
    }

    /// <summary>
    /// Tokenize an IPA string into individual phoneme tokens, preserving
    /// multi-character sequences as single elements.
    /// <list type="bullet">
    ///   <item>Affricates: "tʃ" (t + U+0283) and "dʒ" (d + U+0292) are kept as single tokens.</item>
    ///   <item>Nasal vowels: NFC precomposed characters (ã, ẽ, ĩ, õ, ũ) remain single tokens.
    ///         NFD decomposed sequences (base + combining mark) are re-joined.</item>
    ///   <item>Stress marker ˈ (U+02C8) is preserved as a standalone token.</item>
    ///   <item>Spaces become " " tokens.</item>
    /// </list>
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

            // Check for known digraphs: "tʃ" (t + U+0283), "dʒ" (d + U+0292)
            if (i + 1 < ipa.Length)
            {
                string pair = ipa.Substring(i, 2);
                if (pair == "t\u0283" || pair == "d\u0292")
                {
                    tokens.Add(pair);
                    i += 2;
                    continue;
                }
            }

            // Base character + any combining characters (handles NFD nasal vowels)
            int start = i;
            i++;
            while (i < ipa.Length && char.GetUnicodeCategory(ipa[i]) == UnicodeCategory.NonSpacingMark)
            {
                i++;
            }
            tokens.Add(ipa.Substring(start, i - start));
        }
        return tokens;
    }
}
