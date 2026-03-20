using DotNetG2P.English;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="EnglishG2PEngine"/> from DotNetG2P.English
/// to implement <see cref="IEnglishG2PEngine"/> for piper-plus English phonemization.
/// </summary>
internal sealed class DotNetEnglishG2PEngine : IEnglishG2PEngine
{
    private readonly EnglishG2PEngine _engine = new();

    public List<List<string>> ConvertToArpabet(string text)
    {
        var result = new List<List<string>>();

        // Split on whitespace and look up each token.
        // LookupWord handles unknown words via LTS fallback.
        foreach (string token in text.Split(' ', StringSplitOptions.RemoveEmptyEntries))
        {
            // Strip leading/trailing punctuation for lookup, keep punct as separate "word"
            string word = token.Trim();
            if (string.IsNullOrEmpty(word))
                continue;

            var phonemes = _engine.LookupWord(word);
            if (phonemes.Count > 0)
            {
                // EnglishPhoneme.ToString() returns ARPAbet like "HH", "AH0", "L"
                var wordPhonemes = new List<string>(phonemes.Count);
                foreach (var p in phonemes)
                    wordPhonemes.Add(p.ToString());
                result.Add(wordPhonemes);
            }
            else
            {
                // Punctuation or unknown: pass through as-is
                result.Add([word]);
            }
        }

        return result;
    }
}
