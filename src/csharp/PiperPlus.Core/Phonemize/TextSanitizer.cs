using System;
using System.Text;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Strips control characters from a text before it is read, by the rule every
/// runtime shares (<c>docs/spec/input-sanitize-contract.toml</c>).
/// </summary>
public static class TextSanitizer
{
    /// <summary>
    /// Return <paramref name="text"/> cleaned by the input-sanitize rule:
    /// <c>\n</c>, <c>\t</c> and <c>\r</c> stay (sentence splitting and SSML
    /// use them); VT, FF and NEL (U+000B, U+000C, U+0085) separate words, so
    /// they become a space; every other control character (Unicode category
    /// Cc: U+0000-001F, U+007F, U+0080-009F) is removed.
    /// <para>
    /// Every Cc code point is in the Basic Multilingual Plane, so each one is
    /// a single UTF-16 unit and the check per unit is the check per code
    /// point: surrogate pairs and lone surrogates pass through unchanged, as
    /// do format characters (U+200D, U+FEFF), separators (U+2028) and NBSP.
    /// Idempotent; returns <paramref name="text"/> itself when there is
    /// nothing to change.
    /// </para>
    /// </summary>
    /// <param name="text">The text to clean.</param>
    /// <returns>The cleaned text.</returns>
    public static string StripControlChars(string text)
    {
        ArgumentNullException.ThrowIfNull(text);

        int first = IndexOfStripped(text);
        if (first < 0)
        {
            return text;
        }

        var sb = new StringBuilder(text.Length);
        sb.Append(text, 0, first);
        for (int i = first; i < text.Length; i++)
        {
            char c = text[i];
            if (c is '\u000B' or '\u000C' or '\u0085')
            {
                sb.Append(' ');
            }
            else if (!IsStripped(c))
            {
                sb.Append(c);
            }
        }

        return sb.ToString();
    }

    private static bool IsStripped(char c) => char.IsControl(c) && c is not ('\n' or '\t' or '\r');

    private static int IndexOfStripped(string text)
    {
        for (int i = 0; i < text.Length; i++)
        {
            if (IsStripped(text[i]))
            {
                return i;
            }
        }

        return -1;
    }
}
