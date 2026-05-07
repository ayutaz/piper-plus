using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize.Data;

/// <summary>
/// Deserialized form of <c>zh_en_loanword.json</c>. Maps English tokens to
/// Mandarin pinyin syllables for ZH-EN code-switching (Issue #384).
/// </summary>
/// <param name="Version">Schema version (currently 1).</param>
/// <param name="Acronyms">
/// Uppercase acronyms (e.g. <c>"GPS" -> ["ji4", "pi4", "ai1", "si4"]</c>).
/// </param>
/// <param name="Loanwords">
/// Case-sensitive loanwords (e.g. <c>"Python" -> ["pai4", "sen1"]</c>).
/// </param>
/// <param name="LetterFallback">
/// Per-letter A-Z mapping for tokens not in <see cref="Acronyms"/> or
/// <see cref="Loanwords"/>.
/// </param>
public sealed record LoanwordData(
    int Version,
    IReadOnlyDictionary<string, IReadOnlyList<string>> Acronyms,
    IReadOnlyDictionary<string, IReadOnlyList<string>> Loanwords,
    IReadOnlyDictionary<string, IReadOnlyList<string>> LetterFallback);
