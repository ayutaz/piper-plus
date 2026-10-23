using System.Globalization;
using System.Text;
using DotNetG2P.English;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="EnglishG2PEngine"/> from DotNetG2P.English
/// to implement <see cref="IEnglishG2PEngine"/> for piper-plus English phonemization.
/// </summary>
/// <remarks>
/// Prepares the text the way Python's g2p_en does before its dictionary
/// lookup (src/python/g2p/piper_plus_g2p/english.py): accents are folded,
/// "i.e." / "e.g." are expanded, characters other than letters, digits and
/// <c>' . , ? ! -</c> are removed, and sentence punctuation at the edges of a
/// word becomes its own "word". <see cref="EnglishG2PEngine.LookupWord"/>
/// finds nothing for "Hello," or "café", so without this such words were
/// passed through as raw letters. Number expansion and g2p_en's neural
/// guesser for out-of-dictionary words are not ported (#821).
/// </remarks>
internal sealed class DotNetEnglishG2PEngine : IEnglishG2PEngine
{
    private const string EdgePunctuation = ".,?!";

    private readonly EnglishG2PEngine _engine = new();

    public List<List<string>> ConvertToArpabet(string text)
    {
        var result = new List<List<string>>();

        foreach (string token in Normalize(text).Split(' ', StringSplitOptions.RemoveEmptyEntries))
        {
            int start = 0;
            int end = token.Length;
            while (start < end && EdgePunctuation.Contains(token[start]))
            {
                result.Add([token[start].ToString()]);
                start++;
            }

            while (end > start && EdgePunctuation.Contains(token[end - 1]))
            {
                end--;
            }

            if (end > start)
            {
                AddWord(result, token[start..end]);
            }

            for (int i = end; i < token.Length; i++)
            {
                result.Add([token[i].ToString()]);
            }
        }

        return result;
    }

    private void AddWord(List<List<string>> result, string word)
    {
        // LookupWord handles unknown words via LTS fallback.
        IReadOnlyList<EnglishPhoneme> phonemes = _engine.LookupWord(word);
        if (phonemes.Count > 0)
        {
            // EnglishPhoneme.ToString() returns ARPAbet like "HH", "AH0", "L"
            var wordPhonemes = new List<string>(phonemes.Count);
            foreach (EnglishPhoneme p in phonemes)
            {
                wordPhonemes.Add(p.ToString());
            }

            result.Add(wordPhonemes);
        }
        else
        {
            // Unknown: pass through as-is
            result.Add([word]);
        }
    }

    /// <summary>
    /// g2p_en's text normalization, except number expansion: digits are kept,
    /// so their handling is unchanged until #821.
    /// </summary>
    private static string Normalize(string text)
    {
        var folded = new StringBuilder(text.Length);
        foreach (char ch in text.Normalize(NormalizationForm.FormD))
        {
            if (CharUnicodeInfo.GetUnicodeCategory(ch) != UnicodeCategory.NonSpacingMark)
            {
                folded.Append(ch);
            }
        }

        string s = folded.ToString()
            .Replace("i.e.", "that is", StringComparison.OrdinalIgnoreCase)
            .Replace("e.g.", "for example", StringComparison.OrdinalIgnoreCase);

        var kept = new StringBuilder(s.Length);
        foreach (char ch in s)
        {
            if (char.IsAsciiLetterOrDigit(ch) || ch is '\'' or '.' or ',' or '?' or '!' or '-')
            {
                kept.Append(ch);
            }
            else if (char.IsWhiteSpace(ch))
            {
                kept.Append(' ');
            }
        }

        return kept.ToString();
    }
}
