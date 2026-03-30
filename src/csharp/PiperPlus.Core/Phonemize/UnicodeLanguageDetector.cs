using System;
using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Detects language from Unicode character ranges for multilingual text segmentation.
/// <para>
/// C# port of the Python <c>UnicodeLanguageDetector</c> class and
/// <c>_segment_text_multilingual()</c> function in
/// <c>piper_train/phonemize/multilingual.py</c>.
/// </para>
/// <para>
/// Supports CJK disambiguation (JA vs ZH) by checking for kana presence in context.
/// Latin characters are mapped to a configurable default language.
/// </para>
/// </summary>
public sealed class UnicodeLanguageDetector
{
    // Hiragana: U+3040-309F, Katakana: U+30A0-30FF, Katakana Phonetic: U+31F0-31FF
    private static bool IsKana(char ch) =>
        (ch >= '\u3040' && ch <= '\u309F') ||
        (ch >= '\u30A0' && ch <= '\u30FF') ||
        (ch >= '\u31F0' && ch <= '\u31FF');

    // CJK Unified Ideographs: U+4E00-9FFF, Extension A: U+3400-4DBF
    // CJK Compatibility: U+F900-FAFF
    private static bool IsCjk(char ch) =>
        (ch >= '\u4E00' && ch <= '\u9FFF') ||
        (ch >= '\u3400' && ch <= '\u4DBF') ||
        (ch >= '\uF900' && ch <= '\uFAFF');

    // Japanese-specific: CJK punctuation + fullwidth forms.
    // Excludes fullwidth Latin letters (U+FF21-FF3A, U+FF41-FF5A) which are
    // handled separately as Latin characters.
    private static bool IsJaPunct(char ch) =>
        (ch >= '\u3000' && ch <= '\u303F') ||
        (ch >= '\uFF00' && ch <= '\uFF20') ||
        (ch >= '\uFF3B' && ch <= '\uFF40') ||
        (ch >= '\uFF5B' && ch <= '\uFFEF');

    // Fullwidth Latin letters: U+FF21-FF3A (A-Z), U+FF41-FF5A (a-z)
    private static bool IsFullwidthLatin(char ch) =>
        (ch >= '\uFF21' && ch <= '\uFF3A') ||
        (ch >= '\uFF41' && ch <= '\uFF5A');

    // Hangul Syllables: U+AC00-D7AF, Jamo: U+1100-11FF, Compat Jamo: U+3130-318F
    private static bool IsHangul(char ch) =>
        (ch >= '\uAC00' && ch <= '\uD7AF') ||
        (ch >= '\u1100' && ch <= '\u11FF') ||
        (ch >= '\u3130' && ch <= '\u318F');

    // Basic Latin letters (including extended Latin with diacritics).
    // Excludes multiplication sign (U+00D7) and division sign (U+00F7) which
    // fall within the A-o range.
    private static bool IsLatin(char ch) =>
        (ch >= 'A' && ch <= 'Z') ||
        (ch >= 'a' && ch <= 'z') ||
        (ch >= '\u00C0' && ch <= '\u00D6') ||
        (ch >= '\u00D8' && ch <= '\u00F6') ||
        (ch >= '\u00F8' && ch <= '\u00FF');

    // Swedish-specific characters not used by EN/ES/PT/FR.
    // a-diaeresis (U+00E4), o-diaeresis (U+00F6), a-ring (U+00E5) and uppercase variants.
    private static readonly HashSet<char> SwedishChars = new()
    {
        '\u00E4', '\u00F6', '\u00C4', '\u00D6', '\u00E5', '\u00C5',
    };

    // Swedish function words for word-level disambiguation.
    // These are highly distinctive and do not appear in EN/ES/PT/FR.
    private static readonly HashSet<string> SwedishFunctionWords = new(StringComparer.OrdinalIgnoreCase)
    {
        "och", "att", "jag", "det", "den", "inte", "som", "han", "hon",
        "var", "har", "kan", "ska", "med", "för", "sig", "sin", "min",
        "din", "vill", "från", "när", "här", "där", "också", "alla",
        "denna", "efter", "eller", "under", "utan", "mycket", "mellan",
        "genom", "bara", "sedan", "redan", "aldrig", "alltid", "igen",
        "något", "några", "varje", "vilken", "vilket",
    };

    private readonly HashSet<string> _languages;
    private readonly bool _hasJa;
    private readonly bool _hasZh;
    private readonly bool _hasKo;
    private readonly bool _hasSv;
    private readonly bool _detectSwedish;
    private readonly string? _defaultLatinResult;

    /// <summary>
    /// Gets the default language code used for Latin-script characters.
    /// </summary>
    public string DefaultLatinLanguage { get; }

    /// <summary>
    /// Create a new <see cref="UnicodeLanguageDetector"/>.
    /// </summary>
    /// <param name="languages">
    /// Language codes supported by this detector (e.g. <c>["ja", "en", "zh"]</c>).
    /// </param>
    /// <param name="defaultLatinLanguage">
    /// Language code for Latin-script characters (default: <c>"en"</c>).
    /// </param>
    public UnicodeLanguageDetector(
        IReadOnlyList<string> languages,
        string defaultLatinLanguage = "en")
    {
        ArgumentNullException.ThrowIfNull(languages);
        ArgumentNullException.ThrowIfNull(defaultLatinLanguage);

        _languages = new HashSet<string>(languages);
        DefaultLatinLanguage = defaultLatinLanguage;

        _hasJa = _languages.Contains("ja");
        _hasZh = _languages.Contains("zh");
        _hasKo = _languages.Contains("ko");
        _hasSv = _languages.Contains("sv");
        _defaultLatinResult = _languages.Contains(defaultLatinLanguage) ? defaultLatinLanguage : null;

        // Latin-script languages available (for Swedish disambiguation).
        int latinLangCount = 0;
        foreach (string lang in languages)
        {
            if (lang is "en" or "es" or "pt" or "fr" or "sv")
                latinLangCount++;
        }

        // Enable Swedish detection when sv is present alongside other Latin langs.
        _detectSwedish = _hasSv && latinLangCount >= 2;
    }

    /// <summary>
    /// Detect language for a single character.
    /// </summary>
    /// <param name="ch">Character to classify.</param>
    /// <param name="contextHasKana">
    /// Whether the surrounding text contains kana (for CJK disambiguation).
    /// When <c>true</c>, CJK ideographs are classified as Japanese; otherwise Chinese.
    /// </param>
    /// <returns>
    /// Language code (e.g. <c>"ja"</c>, <c>"en"</c>, <c>"zh"</c>), or <c>null</c>
    /// for neutral characters (whitespace, digits, basic punctuation).
    /// </returns>
    public string? DetectChar(char ch, bool contextHasKana = false)
    {
        // Kana -> always Japanese
        if (IsKana(ch))
        {
            return _hasJa ? "ja" : null;
        }

        // Hangul -> Korean
        if (IsHangul(ch))
        {
            return _hasKo ? "ko" : null;
        }

        // CJK ideographs -> JA or ZH depending on context
        if (IsCjk(ch))
        {
            if (_hasJa && _hasZh)
            {
                // Disambiguate: if context has kana, it's Japanese
                return contextHasKana ? "ja" : "zh";
            }
            if (_hasJa) return "ja";
            if (_hasZh) return "zh";
            return null;
        }

        // Fullwidth Latin letters (A-Z, a-z) -> treat as Latin, not Japanese
        if (IsFullwidthLatin(ch))
        {
            return _defaultLatinResult;
        }

        // Japanese-specific punctuation (CJK punct + fullwidth forms,
        // excluding fullwidth Latin already handled above)
        if (IsJaPunct(ch))
        {
            return _hasJa ? "ja" : null;
        }

        // Latin characters
        if (IsLatin(ch))
        {
            return _defaultLatinResult;
        }

        // Neutral: whitespace, digits, basic punctuation
        return null;
    }

    /// <summary>
    /// Check if <paramref name="text"/> contains any Hiragana or Katakana characters.
    /// </summary>
    /// <param name="text">Text to scan.</param>
    /// <returns><c>true</c> if at least one kana character is found.</returns>
    public bool HasKana(string text)
    {
        ArgumentNullException.ThrowIfNull(text);

        for (int i = 0; i < text.Length; i++)
        {
            if (IsKana(text[i]))
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// Split <paramref name="text"/> into <c>(language, segment)</c> pairs
    /// using Unicode-based language detection.
    /// <para>
    /// Mirrors the Python <c>_segment_text_multilingual()</c> function:
    /// <list type="number">
    ///   <item>Pre-scan entire text for kana (for CJK disambiguation).</item>
    ///   <item>Iterate char by char, detecting language.</item>
    ///   <item>Neutral chars (<c>null</c>) are absorbed into the current segment.</item>
    ///   <item>When language changes, flush the current segment.</item>
    ///   <item>If no language-specific chars found, fall back to <see cref="DefaultLatinLanguage"/>.</item>
    /// </list>
    /// </para>
    /// </summary>
    /// <param name="text">Input text to segment.</param>
    /// <returns>
    /// A list of <c>(Lang, Text)</c> tuples. May be empty if the input is
    /// whitespace-only.
    /// </returns>
    public List<(string Lang, string Text)> SegmentText(string text)
    {
        ArgumentNullException.ThrowIfNull(text);

        if (string.IsNullOrWhiteSpace(text))
        {
            return new List<(string, string)>();
        }

        // Pre-scan for kana to help CJK disambiguation.
        bool contextHasKana = HasKana(text);

        var segments = new List<(string Lang, string Text)>();
        string? currentLang = null;
        int segmentStart = 0;

        for (int i = 0; i < text.Length; i++)
        {
            char ch = text[i];
            string? lang = DetectChar(ch, contextHasKana);

            if (lang is not null && lang != currentLang && currentLang is not null)
            {
                segments.Add((currentLang, text[segmentStart..i]));
                segmentStart = i;
            }

            if (lang is not null)
            {
                currentLang = lang;
            }
        }

        if (segmentStart < text.Length && currentLang is not null)
        {
            segments.Add((currentLang, text[segmentStart..]));
        }

        // If no language-specific characters were detected (e.g., text is only
        // numbers, URLs, or punctuation), fall back to the default language so
        // the text is processed rather than silently dropped.
        if (segments.Count == 0 && !string.IsNullOrWhiteSpace(text))
        {
            segments.Add((DefaultLatinLanguage, text));
        }

        // Post-pass: word-level Swedish detection within Latin segments.
        // When sv is in the language set alongside other Latin languages,
        // re-examine default-Latin segments for Swedish function words.
        if (_detectSwedish)
        {
            segments = RefineLatinSegmentsForSwedish(segments);
        }

        return segments;
    }

    /// <summary>
    /// Re-classify Latin segments as Swedish based on indicator count.
    /// <para>
    /// For each segment assigned to the default Latin language, count Swedish
    /// indicators (characters in <see cref="SwedishChars"/> + function words
    /// in <see cref="SwedishFunctionWords"/>). If at least one indicator is
    /// found, the entire segment is re-classified as <c>"sv"</c>.
    /// </para>
    /// </summary>
    private List<(string Lang, string Text)> RefineLatinSegmentsForSwedish(
        List<(string Lang, string Text)> segments)
    {
        string defaultLang = DefaultLatinLanguage;

        // If the default Latin language is already Swedish, nothing to refine.
        if (defaultLang == "sv")
            return segments;

        var result = new List<(string Lang, string Text)>(segments.Count);

        foreach (var (lang, segText) in segments)
        {
            if (lang != defaultLang)
            {
                result.Add((lang, segText));
                continue;
            }

            // Count Swedish indicators in this segment.
            int svScore = 0;
            foreach (string rawWord in segText.Split(' ', StringSplitOptions.RemoveEmptyEntries))
            {
                string word = rawWord.Trim('.', ',', ';', ':', '!', '?').ToLowerInvariant();
                if (word.Length == 0)
                    continue;

                // Swedish-specific characters
                bool hasSwedishChar = false;
                foreach (char c in word)
                {
                    if (SwedishChars.Contains(c))
                    {
                        hasSwedishChar = true;
                        break;
                    }
                }

                if (hasSwedishChar)
                {
                    svScore++;
                }
                else if (SwedishFunctionWords.Contains(word))
                {
                    svScore++;
                }
            }

            result.Add(svScore >= 1 ? ("sv", segText) : (defaultLang, segText));
        }

        return result;
    }
}
