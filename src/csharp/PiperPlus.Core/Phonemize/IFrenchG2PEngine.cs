using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

// -----------------------------------------------------------------
// French G2P abstraction layer — allows the rule-based G2P engine
// to be swapped / mocked independently of the phonemizer.
// -----------------------------------------------------------------

/// <summary>
/// Abstraction over a French G2P engine (e.g. DotNetG2P.French.FrenchG2PEngine).
/// <para>
/// The engine converts French text to a flat list of IPA phoneme tokens
/// using rule-based longest-match left-to-right scanning.  No external
/// G2P library is required — French grapheme-to-phoneme conversion is
/// fully rule-based.
/// </para>
/// <para>
/// Output conventions (matching the Python <c>phonemize_french()</c> in
/// <c>piper_train/phonemize/french.py</c>):
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
///     PUA codepoints by the token mapper:
///     nasal vowels <c>"ɛ̃"</c> (U+E056), <c>"ɑ̃"</c> (U+E057),
///     <c>"ɔ̃"</c> (U+E058), and <c>"y_vowel"</c> (U+E01E).
///     </description>
///   </item>
///   <item>
///     <description>
///     Punctuation characters (including <c>«</c>, <c>»</c>, <c>—</c>,
///     <c>–</c>, <c>…</c>) appear as standalone single-character tokens.
///     </description>
///   </item>
///   <item>
///     <description>
///     Notable G2P rules: <c>-er</c> → /e/ (verb infinitives),
///     <c>-ille</c> → /ij/ (default) or /il/ (ville, mille, tranquille),
///     <c>-tion</c> → /sjɔ̃/.
///     </description>
///   </item>
/// </list>
/// <para>
/// Stress detection and prosody generation (A1/A2/A3) are handled by the
/// <c>FrenchPhonemizer</c> layer, not by this engine.
/// </para>
/// </summary>
public interface IFrenchG2PEngine
{
    /// <summary>
    /// Convert French <paramref name="text"/> to a flat list of IPA phoneme tokens.
    /// </summary>
    /// <param name="text">Input French text.</param>
    /// <returns>
    /// An ordered list of IPA phoneme strings.  Each element is either a
    /// single IPA character, a multi-character token (e.g. <c>"ɛ̃"</c>,
    /// <c>"y_vowel"</c>), a space <c>" "</c> for word boundaries, or a
    /// punctuation character.
    /// </returns>
    List<string> ToPhonemeList(string text);
}
