using System.Text.RegularExpressions;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Segment of text that is either normal text or inline phonemes.
/// When <see cref="IsPhonemes"/> is <c>true</c>, <see cref="Text"/> contains
/// space-separated phoneme tokens (same format as <c>--raw-phonemes</c>).
/// </summary>
/// <param name="IsPhonemes">
/// <c>true</c> when this segment was enclosed in <c>[[ ... ]]</c> notation.
/// </param>
/// <param name="Text">The segment content (plain text or phoneme string).</param>
public record TextOrPhonemes(bool IsPhonemes, string Text);

/// <summary>
/// Parses <c>[[ phoneme ]]</c> inline notation in text, splitting input into
/// alternating text and phoneme segments.
/// <para>
/// Mirrors the C++ <c>parsePhonemeString()</c> inline-notation support in
/// <c>phoneme_parser.hpp</c>. The notation allows users to mix normal text
/// (processed by the phonemizer) with pre-specified phoneme sequences:
/// <code>
///   "Hello [[ h ə l oʊ ]] world"
///   → [TextOrPhonemes(false, "Hello "), TextOrPhonemes(true, "h ə l oʊ"), TextOrPhonemes(false, " world")]
/// </code>
/// </para>
/// </summary>
public static partial class InlinePhonemeParser
{
    // Match [[ ... ]] with optional internal whitespace.
    // Group 1 captures the content between the brackets.
    [GeneratedRegex(@"\[\[\s*([^\]]*?)\s*\]\]")]
    private static partial Regex PhonemeNotationRegex();

    /// <summary>
    /// Parse text containing <c>[[ phoneme ]]</c> notation into segments.
    /// Normal text is returned as-is; phoneme segments are marked with
    /// <see cref="TextOrPhonemes.IsPhonemes"/> set to <c>true</c>.
    /// </summary>
    /// <param name="input">Input text, possibly containing <c>[[ ... ]]</c> notation.</param>
    /// <returns>
    /// Ordered list of segments. Returns an empty list for <c>null</c> or empty input.
    /// </returns>
    public static List<TextOrPhonemes> Parse(string? input)
    {
        if (string.IsNullOrEmpty(input))
            return [];

        var result = new List<TextOrPhonemes>();
        int lastPos = 0;

        foreach (Match match in PhonemeNotationRegex().Matches(input))
        {
            // Add preceding text segment
            if (match.Index > lastPos)
            {
                var text = input[lastPos..match.Index];
                result.Add(new TextOrPhonemes(false, text));
            }

            // Add phoneme segment (even if empty — matches C++ behavior)
            var phonemes = match.Groups[1].Value.Trim();
            result.Add(new TextOrPhonemes(true, phonemes));

            lastPos = match.Index + match.Length;
        }

        // Add trailing text segment
        if (lastPos < input.Length)
        {
            var text = input[lastPos..];
            result.Add(new TextOrPhonemes(false, text));
        }

        return result;
    }
}
