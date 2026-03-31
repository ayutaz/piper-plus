using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Abstraction over a Swedish G2P engine (rule-based + optional NST dictionary).
/// <para>
/// The engine converts Swedish text to a flat list of IPA phoneme tokens
/// using rule-based conversion with Complementary Quantity vowel length,
/// retroflex assimilation, loanword suffix/prefix handling, and stress
/// detection. An optional NST IPA dictionary provides lookup before
/// rule-based fallback.
/// </para>
/// <para>
/// Output conventions (matching the Python <c>phonemize_swedish()</c> in
/// <c>piper_train/phonemize/swedish.py</c>):
/// </para>
/// <list type="bullet">
///   <item>
///     <description>
///     Word boundaries are represented by a space <c>" "</c> token.
///     </description>
///   </item>
///   <item>
///     <description>
///     Multi-character IPA tokens are returned as-is and later mapped to
///     PUA codepoints by the token mapper: long vowels (<c>"i\u02D0"</c>,
///     <c>"y\u02D0"</c>, <c>"e\u02D0"</c>, <c>"\u025B\u02D0"</c>,
///     <c>"\u00F8\u02D0"</c>, <c>"\u0251\u02D0"</c>, <c>"o\u02D0"</c>,
///     <c>"u\u02D0"</c>, <c>"\u0289\u02D0"</c>) map to U+E059-U+E061.
///     </description>
///   </item>
///   <item>
///     <description>
///     Stress markers <c>"\u02C8"</c> (primary) and <c>"\u02CC"</c>
///     (secondary) appear as standalone tokens before the stressed syllable
///     onset.
///     </description>
///   </item>
///   <item>
///     <description>
///     Punctuation characters (<c>.</c>, <c>,</c>, <c>;</c>, <c>:</c>,
///     <c>!</c>, <c>?</c>) appear as standalone tokens.
///     </description>
///   </item>
/// </list>
/// <para>
/// Stress detection and prosody generation (A1/A2/A3) are handled by the
/// <c>SwedishPhonemizer</c> layer, not by this engine.
/// </para>
/// </summary>
public interface ISwedishG2PEngine
{
    /// <summary>
    /// Convert Swedish <paramref name="text"/> to a flat list of IPA phoneme tokens.
    /// </summary>
    /// <param name="text">Input Swedish text.</param>
    /// <returns>
    /// An ordered list of IPA phoneme strings. Each element is either a
    /// single IPA character, a multi-character token (e.g. long vowels
    /// <c>"i\u02D0"</c>, retroflex consonants), a stress marker
    /// (<c>"\u02C8"</c> / <c>"\u02CC"</c>), a space <c>" "</c> for
    /// word boundaries, or a punctuation character.
    /// </returns>
    List<string> ToPhonemeList(string text);
}
