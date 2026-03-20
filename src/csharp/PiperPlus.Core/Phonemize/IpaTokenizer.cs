using System.Globalization;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Splits an IPA string into properly segmented phoneme tokens.
/// <list type="bullet">
///   <item>Spaces become standalone " " tokens.</item>
///   <item>Known digraphs (e.g. affricates "tʃ", "dʒ") are kept as single tokens.</item>
///   <item>Base characters followed by combining marks (NonSpacingMark) are merged into one token.</item>
/// </list>
/// </summary>
public static class IpaTokenizer
{
    /// <summary>
    /// Tokenize an IPA string into individual phoneme tokens.
    /// </summary>
    /// <param name="ipa">The IPA string to tokenize.</param>
    /// <param name="knownDigraphs">
    /// Optional set of two-character sequences that should be emitted as single tokens.
    /// Pass <c>null</c> when no digraph handling is needed.
    /// </param>
    public static List<string> Tokenize(string ipa, IReadOnlySet<string>? knownDigraphs = null)
    {
        var tokens = new List<string>(Math.Max(4, ipa.Length / 2));
        int i = 0;
        while (i < ipa.Length)
        {
            if (ipa[i] == ' ')
            {
                tokens.Add(" ");
                i++;
                continue;
            }

            // Check for known digraphs (2-char sequences)
            if (knownDigraphs is not null && i + 1 < ipa.Length)
            {
                string pair = ipa.Substring(i, 2);
                if (knownDigraphs.Contains(pair))
                {
                    tokens.Add(pair);
                    i += 2;
                    continue;
                }
            }

            // Base character + any following combining marks
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
