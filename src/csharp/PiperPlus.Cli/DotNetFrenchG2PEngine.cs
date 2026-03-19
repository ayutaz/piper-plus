using System.Globalization;
using PiperPlus.Core.Phonemize;
using DotNetG2P.French;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="FrenchG2PEngine"/> from DotNetG2P.French
/// to implement <see cref="IFrenchG2PEngine"/>.
/// </summary>
internal sealed class DotNetFrenchG2PEngine : IFrenchG2PEngine
{
    private readonly FrenchG2PEngine _engine = new();

    public List<string> ToPhonemeList(string text)
    {
        string ipa = _engine.ToIPA(text);
        return IpaTokenize(ipa);
    }

    /// <summary>
    /// Split an IPA string into properly segmented tokens, keeping each base
    /// character together with any following combining marks (e.g. U+0300-U+036F).
    /// This correctly handles French nasal vowels such as "ɛ̃" (U+025B + U+0303),
    /// "ɑ̃" (U+0251 + U+0303), and "ɔ̃" (U+0254 + U+0303).
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

            // Base character + any combining characters (NonSpacingMark)
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
