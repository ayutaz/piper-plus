using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

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
    private static readonly Regex s_kanaRegex = new(
        @"[\u3040-\u309F\u30A0-\u30FF\u31F0-\u31FF]",
        RegexOptions.Compiled);

    // CJK Unified Ideographs: U+4E00-9FFF, Extension A: U+3400-4DBF
    // CJK Compatibility: U+F900-FAFF
    private static readonly Regex s_cjkRegex = new(
        @"[\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF]",
        RegexOptions.Compiled);

    // Japanese-specific: CJK punctuation + fullwidth forms.
    // Excludes fullwidth Latin letters (U+FF21-FF3A, U+FF41-FF5A) which are
    // handled separately as Latin characters.
    private static readonly Regex s_jaPunctRegex = new(
        @"[\u3000-\u303F\uFF00-\uFF20\uFF3B-\uFF40\uFF5B-\uFFEF]",
        RegexOptions.Compiled);

    // Fullwidth Latin letters: U+FF21-FF3A (A-Z), U+FF41-FF5A (a-z)
    private static readonly Regex s_fullwidthLatinRegex = new(
        @"[\uFF21-\uFF3A\uFF41-\uFF5A]",
        RegexOptions.Compiled);

    // Hangul Syllables: U+AC00-D7AF, Jamo: U+1100-11FF, Compat Jamo: U+3130-318F
    private static readonly Regex s_hangulRegex = new(
        @"[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]",
        RegexOptions.Compiled);

    // Basic Latin letters (including extended Latin with diacritics).
    // Excludes multiplication sign (U+00D7) and division sign (U+00F7) which
    // fall within the A-o range.
    private static readonly Regex s_latinRegex = new(
        @"[A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u00FF]",
        RegexOptions.Compiled);

    private readonly HashSet<string> _languages;
    private readonly bool _hasJa;
    private readonly bool _hasZh;
    private readonly bool _hasKo;

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
        string s = ch.ToString();

        // Kana -> always Japanese
        if (s_kanaRegex.IsMatch(s))
        {
            return _hasJa ? "ja" : null;
        }

        // Hangul -> Korean
        if (s_hangulRegex.IsMatch(s))
        {
            return _hasKo ? "ko" : null;
        }

        // CJK ideographs -> JA or ZH depending on context
        if (s_cjkRegex.IsMatch(s))
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
        if (s_fullwidthLatinRegex.IsMatch(s))
        {
            return _languages.Contains(DefaultLatinLanguage)
                ? DefaultLatinLanguage
                : null;
        }

        // Japanese-specific punctuation (CJK punct + fullwidth forms,
        // excluding fullwidth Latin already handled above)
        if (s_jaPunctRegex.IsMatch(s))
        {
            return _hasJa ? "ja" : null;
        }

        // Latin characters
        if (s_latinRegex.IsMatch(s))
        {
            return _languages.Contains(DefaultLatinLanguage)
                ? DefaultLatinLanguage
                : null;
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
        return s_kanaRegex.IsMatch(text);
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
        var currentChars = new List<char>();

        for (int i = 0; i < text.Length; i++)
        {
            char ch = text[i];
            string? lang = DetectChar(ch, contextHasKana);

            if (lang is not null && lang != currentLang && currentLang is not null)
            {
                segments.Add((currentLang, new string(currentChars.ToArray())));
                currentChars.Clear();
            }

            if (lang is not null)
            {
                currentLang = lang;
            }

            currentChars.Add(ch);
        }

        if (currentChars.Count > 0 && currentLang is not null)
        {
            segments.Add((currentLang, new string(currentChars.ToArray())));
        }

        // If no language-specific characters were detected (e.g., text is only
        // numbers, URLs, or punctuation), fall back to the default language so
        // the text is processed rather than silently dropped.
        if (segments.Count == 0 && !string.IsNullOrWhiteSpace(text))
        {
            segments.Add((DefaultLatinLanguage, text));
        }

        return segments;
    }
}
