using System.Collections.Generic;

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
/// This mirrors the Rust implementation in
/// <c>piper-core/src/streaming.rs::split_sentences</c>.
/// </para>
/// </summary>
public static class TextSplitter
{
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
            return new List<string>();

        var sentences = new List<string>();
        var current = new System.Text.StringBuilder();

        int i = 0;
        while (i < text.Length)
        {
            char ch = text[i];
            current.Append(ch);
            i++;

            // Check if this character is a sentence terminator
            if (IsSentenceTerminator(ch))
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
