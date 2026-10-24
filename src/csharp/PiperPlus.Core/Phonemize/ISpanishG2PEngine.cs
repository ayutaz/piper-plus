using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Abstraction over a Spanish G2P engine (e.g. <see cref="SpanishG2PEngine"/>).
/// <para>
/// The engine converts raw Spanish text into a flat list of IPA phoneme tokens
/// using rule-based Latin American pronunciation (seseo: c/z before e/i → /s/,
/// yeísmo: ll → /ʝ/).
/// </para>
/// <para>
/// Unlike <see cref="IEnglishG2PEngine"/>, which returns per-word ARPAbet groups,
/// this interface returns a single flat list because Spanish G2P produces IPA
/// directly. Word boundaries are represented by space <c>" "</c> tokens in the
/// list. Multi-character IPA tokens (e.g. <c>"tʃ"</c>, <c>"rr"</c>, <c>"dʒ"</c>)
/// are preserved as single elements. Punctuation characters (<c>¿</c>, <c>¡</c>,
/// <c>,</c>, <c>.</c>) appear as standalone tokens.
/// </para>
/// <para>
/// The engine marks stress with a <c>"ˈ"</c> token right before the stressed
/// vowel, as Python's <c>phonemize_spanish()</c> does. Prosody generation
/// (A2 for the mark and that vowel, A3) is handled by the
/// <c>SpanishPhonemizer</c> layer, not by this engine.
/// </para>
/// </summary>
public interface ISpanishG2PEngine
{
    /// <summary>
    /// Convert <paramref name="text"/> to a flat list of IPA phoneme tokens.
    /// </summary>
    /// <param name="text">Input Spanish text.</param>
    /// <returns>
    /// An ordered list of IPA phoneme strings. Word boundaries are encoded as
    /// space <c>" "</c> tokens. Multi-character phonemes (e.g. <c>"tʃ"</c>,
    /// <c>"rr"</c>) appear as single elements. Punctuation characters appear
    /// as standalone tokens.
    /// </returns>
    List<string> ToPhonemeList(string text);
}
