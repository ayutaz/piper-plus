using System.Collections.Generic;
using PiperPlus.Core.Phonemize.Data;

namespace PiperPlus.Core.Phonemize;

// -----------------------------------------------------------------
// Chinese G2P abstraction layer — allows pypinyin-based backends
// to be swapped / mocked independently of the phonemizer.
// -----------------------------------------------------------------

/// <summary>
/// Result returned by a Chinese G2P engine: parallel lists of
/// PUA-mapped phoneme tokens and per-token A1/A2/A3 prosody values.
/// <para>
/// Unlike the Japanese <see cref="G2PResult"/> (whose A1/A2/A3 represent
/// accent-nucleus position, mora position, and phrase length), the Chinese
/// prosody dimensions encode tone and word-internal syllable position:
/// </para>
/// <list type="table">
///   <listheader>
///     <term>Field</term>
///     <description>Meaning</description>
///   </listheader>
///   <item>
///     <term>A1</term>
///     <description>Tone value (1-4 = lexical tones, 5 = neutral tone).</description>
///   </item>
///   <item>
///     <term>A2</term>
///     <description>Syllable position within the word (1-based).</description>
///   </item>
///   <item>
///     <term>A3</term>
///     <description>Word length in syllables.</description>
///   </item>
/// </list>
/// <para>
/// All three lists must have the same length as <see cref="Phonemes"/>.
/// </para>
/// </summary>
/// <param name="Phonemes">
/// PUA-mapped phoneme tokens produced by the Chinese G2P pipeline.
/// Multi-character IPA tokens (e.g. <c>"tɕʰ"</c>) are mapped to single
/// PUA codepoints in the range U+E020-U+E04A.
/// </param>
/// <param name="A1">Tone value for each phoneme token (1-5, where 5 = neutral tone).</param>
/// <param name="A2">Syllable position within the word (1-based) for each phoneme token.</param>
/// <param name="A3">Word length in syllables for each phoneme token.</param>
public record ChineseG2PResult(
    IReadOnlyList<string> Phonemes,
    IReadOnlyList<int> A1,
    IReadOnlyList<int> A2,
    IReadOnlyList<int> A3);

/// <summary>
/// Abstraction over a Chinese (Mandarin) G2P engine.
/// <para>
/// Implement this interface to plug in any engine that can convert
/// Mandarin text to PUA-mapped IPA phoneme sequences with tone and
/// word-position prosody values. This keeps the Chinese phonemizer
/// testable without a real pypinyin backend.
/// </para>
/// </summary>
public interface IChineseG2PEngine
{
    /// <summary>
    /// Convert Chinese <paramref name="text"/> to phonemes with prosody.
    /// </summary>
    /// <param name="text">Input Chinese (Mandarin) text.</param>
    /// <returns>
    /// A <see cref="ChineseG2PResult"/> whose lists are all the same length.
    /// </returns>
    ChineseG2PResult Convert(string text);

    /// <summary>
    /// Convert English <paramref name="text"/> embedded in Chinese context to
    /// Mandarin pinyin IPA (ZH-EN code-switching, Issue #384). Default
    /// implementation routes to <see cref="ChineseEmbeddedEnglish.Convert"/>,
    /// which is independent of any specific Chinese G2P backend (NuGet or otherwise).
    /// Engine implementations may override for alternative pipelines.
    /// </summary>
    /// <param name="text">English text segment (e.g. <c>"GPS"</c>, <c>"ChatGPT"</c>).</param>
    /// <param name="loanwordData">
    /// Loanword dictionary; defaults to <see cref="LoanwordDataLoader.Default"/>.
    /// </param>
    /// <returns>
    /// A <see cref="ChineseG2PResult"/> with PUA-mapped tokens. Prosody
    /// (A1/A2/A3) carries per-token tone information matching Python's
    /// <c>phonemize_embedded_english</c> pipeline:
    /// <list type="bullet">
    ///   <item><description><c>A1 = tone</c> (1-4 lexical tones, 5 neutral)</description></item>
    ///   <item><description><c>A2 = 1</c> (syllable position; embedded English has no word context)</description></item>
    ///   <item><description><c>A3 = 1</c> (word length in syllables; same)</description></item>
    /// </list>
    /// Returning zeros would silently drop tone information at the ONNX
    /// prosody tensor (review note R-C1).
    /// </returns>
    ChineseG2PResult ConvertEmbeddedEnglish(string text, LoanwordData? loanwordData = null) =>
        ChineseEmbeddedEnglish.Convert(text, loanwordData);
}
