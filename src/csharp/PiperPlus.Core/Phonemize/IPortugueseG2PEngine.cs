using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Abstraction over a Brazilian Portuguese G2P engine
/// (e.g. DotNetG2P.Portuguese.PortugueseG2PEngine).
/// <para>
/// The engine converts raw Brazilian Portuguese text into a flat list of IPA
/// phoneme tokens using rule-based grapheme-to-phoneme conversion. No external
/// G2P dependencies are required.
/// </para>
/// <para>
/// Unlike <see cref="IEnglishG2PEngine"/>, which returns per-word ARPAbet groups,
/// this interface returns a single flat list because Portuguese G2P produces IPA
/// directly. Word boundaries are represented by space <c>" "</c> tokens in the
/// list. Multi-character IPA tokens (e.g. <c>"tʃ"</c> for palatalized t,
/// <c>"dʒ"</c> for palatalized d) are preserved as single elements. Punctuation
/// characters (<c>—</c>, <c>–</c>, <c>…</c>, <c>,</c>, <c>.</c>) appear as
/// standalone tokens.
/// </para>
/// <para>
/// Brazilian Portuguese specific rules applied by the engine:
/// <list type="bullet">
///   <item><description>Coda-l vocalization: syllable-final l becomes [w] (e.g. "Brasil" → [bɾaziw]).</description></item>
///   <item><description>T/d palatalization: ti → [tʃi], di → [dʒi]; unstressed final -te/-de also palatalize.</description></item>
///   <item><description>Unstressed vowel reduction: final e → [i], final o → [u].</description></item>
///   <item><description>Nasal vowels: <c>"ã"</c>, <c>"ẽ"</c>, <c>"ĩ"</c>, <c>"õ"</c>, <c>"ũ"</c> (NFC composed codepoints).</description></item>
/// </list>
/// </para>
/// <para>
/// Stress detection and prosody generation are handled by the
/// <c>PortuguesePhonemizer</c> layer, not by this engine.
/// </para>
/// </summary>
public interface IPortugueseG2PEngine
{
    /// <summary>
    /// Convert <paramref name="text"/> to a flat list of IPA phoneme tokens.
    /// </summary>
    /// <param name="text">Input Brazilian Portuguese text.</param>
    /// <returns>
    /// An ordered list of IPA phoneme strings. Word boundaries are encoded as
    /// space <c>" "</c> tokens. Multi-character phonemes (e.g. <c>"tʃ"</c>,
    /// <c>"dʒ"</c>) appear as single elements. Nasal vowels (<c>"ã"</c>,
    /// <c>"ẽ"</c>, <c>"ĩ"</c>, <c>"õ"</c>, <c>"ũ"</c>) use NFC composed
    /// codepoints. Punctuation characters appear as standalone tokens.
    /// </returns>
    List<string> ToPhonemeList(string text);
}
