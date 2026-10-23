using System;
using System.Collections.Generic;
using System.Linq;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Splits text into sentence-sized chunks suitable for streaming synthesis.
/// <para>
/// Handles both Western (<c>.</c> <c>!</c> <c>?</c>) and CJK
/// (<c>。</c> <c>！</c> <c>？</c>) sentence terminators.  After each
/// terminator, trailing closing punctuation (e.g. <c>」</c> <c>』</c>
/// <c>）</c> <c>"</c> <c>'</c> <c>)</c> <c>]</c>) is consumed as part
/// of the same sentence.
/// </para>
/// <para>
/// SSML envelopes (<c>&lt;speak&gt;...&lt;/speak&gt;</c>) are preserved as
/// single units per the canonical
/// <c>docs/spec/text-splitter-contract.toml</c> spec. If the input begins
/// with <c>&lt;speak</c> (after leading whitespace) and contains a matching
/// <c>&lt;/speak&gt;</c> close tag, the entire envelope is yielded as one
/// unit; only any trailing text after <c>&lt;/speak&gt;</c> is split using
/// the normal sentence-splitting logic. If the <c>&lt;speak&gt;</c> tag is
/// unclosed, the function falls back to normal splitting.
/// </para>
/// <para>
/// A full stop between two digits (<c>3.14</c>) or inside <c>e.g.</c> /
/// <c>i.e.</c> does not end a sentence (Issue #831).
/// </para>
/// <para>
/// This mirrors the Rust implementation in
/// <c>piper-core/src/streaming.rs::split_sentences</c>.
/// </para>
/// </summary>
public static class TextSplitter
{
    /// <summary>
    /// Abbreviations whose full stops do not end a sentence (Issue #831).
    /// g2p_en reads them as part of the text around them (<c>e.g.</c> is
    /// "for example"), and the training data is phonemized without
    /// splitting. See <c>[[non_terminating_abbreviations]]</c> in
    /// <c>docs/spec/text-splitter-contract.toml</c>.
    /// </summary>
    internal static readonly string[] NonTerminatingAbbreviations = ["e.g.", "i.e."];

    /// <summary>
    /// Split text into sentences at natural boundaries.
    /// </summary>
    /// <param name="text">Input text to split.</param>
    /// <returns>
    /// A list of non-empty, trimmed sentences. Empty or whitespace-only
    /// input returns an empty list.
    /// </returns>
    public static List<string> SplitSentences(string text)
    {
        if (string.IsNullOrEmpty(text))
        {
            return new List<string>();
        }

        // SSML envelope detection: if the text starts with `<speak` (after
        // leading whitespace), preserve the entire envelope as a single
        // unit per docs/spec/text-splitter-contract.toml.
        string trimmedStart = text.TrimStart();
        if (trimmedStart.StartsWith("<speak", StringComparison.OrdinalIgnoreCase))
        {
            int closeIdx = FindSpeakClose(trimmedStart);
            if (closeIdx >= 0)
            {
                int envelopeEnd = closeIdx + "</speak>".Length;
                string envelope = trimmedStart.Substring(0, envelopeEnd).Trim();
                var result = new List<string>();
                if (envelope.Length > 0)
                {
                    result.Add(envelope);
                }

                // Any trailing text after </speak> is split normally.
                string tail = trimmedStart.Substring(envelopeEnd).Trim();
                if (tail.Length > 0)
                {
                    result.AddRange(SplitSentencesPlain(tail));
                }

                return result;
            }

            // Unclosed <speak> tag: fall through to normal splitting on the
            // original (untrimmed) text so we don't drop content.
        }

        return SplitSentencesPlain(text);
    }

    /// <summary>
    /// Plain sentence splitter (no SSML awareness). Used internally by
    /// <see cref="SplitSentences"/> after stripping the SSML envelope (or
    /// when no envelope is present).
    /// </summary>
    private static List<string> SplitSentencesPlain(string text)
    {
        if (string.IsNullOrEmpty(text))
        {
            return new List<string>();
        }

        var sentences = new List<string>();
        var current = new System.Text.StringBuilder();

        int i = 0;
        while (i < text.Length)
        {
            char ch = text[i];
            current.Append(ch);
            i++;

            // Check if this character is a sentence terminator
            if (IsSentenceTerminator(ch) && EndsSentence(text, i - 1))
            {
                // Consume any trailing closing punctuation that belongs
                // with this sentence (e.g. 」、）, closing quotes)
                while (i < text.Length && IsClosingPunctuation(text[i]))
                {
                    current.Append(text[i]);
                    i++;
                }

                // Push the completed sentence (trimmed)
                string trimmed = current.ToString().Trim();
                if (trimmed.Length > 0)
                {
                    sentences.Add(trimmed);
                }

                current.Clear();

                // Skip leading whitespace before the next sentence
                while (i < text.Length && char.IsWhiteSpace(text[i]))
                {
                    i++;
                }
            }
        }

        // Handle any remaining text (no trailing terminator)
        string remaining = current.ToString().Trim();
        if (remaining.Length > 0)
        {
            sentences.Add(remaining);
        }

        return sentences;
    }

    /// <summary>
    /// Find the index of the closing <c>&lt;/speak&gt;</c> tag
    /// (case-insensitive on the tag name, matching Python's
    /// <c>re.IGNORECASE</c>). Returns <c>-1</c> if no closing tag is found.
    /// </summary>
    private static int FindSpeakClose(string text)
    {
        return text.IndexOf("</speak>", StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Whether the terminator at <paramref name="index"/> ends a sentence.
    /// A full stop does not when it sits between two digits or is one of the
    /// full stops of a <see cref="NonTerminatingAbbreviations"/> entry that
    /// starts the text or follows a non-ASCII-alphanumeric character
    /// (Issue #831, docs/spec/text-splitter-contract.toml).
    /// </summary>
    private static bool EndsSentence(string text, int index)
    {
        if (!IsFullStop(text[index]))
        {
            return true;
        }

        if (index > 0 && index < text.Length - 1
            && IsDigit(text[index - 1]) && IsDigit(text[index + 1]))
        {
            return false;
        }

        return !NonTerminatingAbbreviations.Any(abbr =>
            Enumerable.Range(0, abbr.Length)
                .Any(j => abbr[j] == '.' && IsAbbreviationAt(text, index - j, abbr)));
    }

    /// <summary>
    /// Whether <paramref name="abbr"/> occurs at <paramref name="start"/>
    /// (ASCII case-insensitive) and starts the text or follows a character
    /// that is not an ASCII letter or digit.
    /// </summary>
    private static bool IsAbbreviationAt(string text, int start, string abbr)
    {
        if (start < 0 || start + abbr.Length > text.Length)
        {
            return false;
        }

        if (string.Compare(text, start, abbr, 0, abbr.Length, StringComparison.OrdinalIgnoreCase) != 0)
        {
            return false;
        }

        return start == 0 || !char.IsAsciiLetterOrDigit(text[start - 1]);
    }

    /// <summary>
    /// Full stops covered by Issue #831: <c>.</c> and the fullwidth
    /// <c>．</c> (U+FF0E). C# does not treat U+FF0E as a terminator yet (see
    /// <see cref="IsSentenceTerminator"/>), so only <c>.</c> reaches this
    /// check today; U+FF0E is listed so the rule holds once it does.
    /// </summary>
    private static bool IsFullStop(char ch) => ch is '.' or '\uFF0E';

    /// <summary>
    /// ASCII <c>0</c>-<c>9</c> or fullwidth <c>０</c>-<c>９</c> (U+FF10-FF19).
    /// </summary>
    private static bool IsDigit(char ch) => ch is (>= '0' and <= '9') or (>= '\uFF10' and <= '\uFF19');

    /// <summary>
    /// Check whether a character is a sentence-ending terminator.
    /// </summary>
    private static bool IsSentenceTerminator(char ch)
    {
        return ch switch
        {
            '.' or '!' or '?' => true,
            '\u3002' => true,   // 。
            '\uFF01' => true,   // ！
            '\uFF1F' => true,   // ？
            _ => false,
        };
    }

    /// <summary>
    /// Check whether a character is closing punctuation that follows a
    /// sentence terminator (e.g. closing brackets, quotation marks).
    /// </summary>
    private static bool IsClosingPunctuation(char ch)
    {
        return ch switch
        {
            ')' or ']' or '}' or '"' or '\'' => true,
            '\u300D' => true,   // 」
            '\u300F' => true,   // 』
            '\uFF09' => true,   // ）
            '\uFF3D' => true,   // ］
            '\u3011' => true,   // 】
            '\uFF63' => true,   // ｣ (half-width)
            '\u201D' => true,   // " (right double quotation mark)
            '\u2019' => true,   // ' (right single quotation mark)
            '\u00BB' => true,   // » (right-pointing double angle quotation mark)
            _ => false,
        };
    }
}
