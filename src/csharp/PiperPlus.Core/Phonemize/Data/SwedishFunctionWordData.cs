using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize.Data;

/// <summary>
/// Deserialized form of <c>sv_function_words.json</c> — the LID-discriminative
/// Swedish word list (Issue #539). Used only by
/// <see cref="UnicodeLanguageDetector"/> for per-word language detection, and
/// is intentionally DISTINCT from the prosody/stress function-word list in the
/// Swedish phonemizer.
/// </summary>
/// <param name="FunctionWords">
/// Highly distinctive Swedish function words (46), lowercased. An exact match
/// is a strong Swedish indicator (e.g. <c>och</c>, <c>jag</c>, <c>för</c>,
/// <c>är</c>).
/// </param>
/// <param name="StrongChars">
/// Characters that are a strong Swedish indicator on their own (a-ring U+00E5
/// and its uppercase U+00C5). The weak chars ä/ö are deliberately excluded —
/// they are shared with German and must NOT trigger Swedish classification.
/// </param>
public sealed record SwedishFunctionWordData(
    IReadOnlySet<string> FunctionWords,
    IReadOnlySet<char> StrongChars);
