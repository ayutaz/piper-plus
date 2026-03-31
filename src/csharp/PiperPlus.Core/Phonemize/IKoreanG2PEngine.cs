using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

// -----------------------------------------------------------------
// Korean G2P abstraction layer -- allows Hangul-decomposition-based
// backends to be swapped / mocked independently of the phonemizer.
// -----------------------------------------------------------------

/// <summary>
/// Result returned by a Korean G2P engine: parallel lists of
/// PUA-mapped phoneme tokens and per-token A1/A2/A3 prosody values.
/// <para>
/// Korean prosody dimensions:
/// </para>
/// <list type="table">
///   <listheader>
///     <term>Field</term>
///     <description>Meaning</description>
///   </listheader>
///   <item>
///     <term>A1</term>
///     <description>Fixed at 0 (Korean has no pitch accent like Japanese).</description>
///   </item>
///   <item>
///     <term>A2</term>
///     <description>Fixed at 0 (Korean has no lexical stress like English).</description>
///   </item>
///   <item>
///     <term>A3</term>
///     <description>Number of Hangul syllables in the current word.</description>
///   </item>
/// </list>
/// <para>
/// All three lists must have the same length as <see cref="Phonemes"/>.
/// </para>
/// </summary>
/// <param name="Phonemes">
/// PUA-mapped phoneme tokens produced by the Korean G2P pipeline.
/// Multi-character IPA tokens (e.g. <c>"tɕ"</c>, <c>"kʰ"</c>, <c>"k̚"</c>)
/// are mapped to single PUA codepoints in the range U+E04B-U+E052
/// (with some shared with Chinese at U+E020-U+E024).
/// </param>
/// <param name="A1">Fixed at 0 for each phoneme token.</param>
/// <param name="A2">Fixed at 0 for each phoneme token.</param>
/// <param name="A3">Number of Hangul syllables in the current word for each phoneme token.</param>
public record KoreanG2PResult(
    IReadOnlyList<string> Phonemes,
    IReadOnlyList<int> A1,
    IReadOnlyList<int> A2,
    IReadOnlyList<int> A3);

/// <summary>
/// Abstraction over a Korean G2P engine.
/// <para>
/// Implement this interface to plug in any engine that can convert
/// Korean text to PUA-mapped IPA phoneme sequences with prosody values.
/// The default implementation uses pure Hangul syllable decomposition
/// (no g2pk2 dependency). This keeps the Korean phonemizer testable
/// without a real G2P backend.
/// </para>
/// </summary>
public interface IKoreanG2PEngine
{
    /// <summary>
    /// Convert Korean <paramref name="text"/> to phonemes with prosody.
    /// </summary>
    /// <param name="text">Input Korean text.</param>
    /// <returns>
    /// A <see cref="KoreanG2PResult"/> whose lists are all the same length.
    /// </returns>
    KoreanG2PResult Convert(string text);
}
