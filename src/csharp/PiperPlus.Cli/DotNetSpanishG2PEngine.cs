using DotNetG2P.Spanish;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="SpanishG2PEngine"/> from DotNetG2P.Spanish
/// to implement <see cref="ISpanishG2PEngine"/>.
/// </summary>
internal sealed class DotNetSpanishG2PEngine : ISpanishG2PEngine
{
    private const string Stress = "\u02C8";

    private static readonly HashSet<string> SpanishDigraphs = ["rr", "t\u0283", "d\u0292"];

    private static readonly HashSet<string> Vowels = ["a", "e", "i", "o", "u"];

    private readonly SpanishG2PEngine _engine = new();

    public List<string> ToPhonemeList(string text)
    {
        string ipa = _engine.ToIPA(text);
        return MoveStressToVowel(IpaTokenizer.Tokenize(ipa, SpanishDigraphs));
    }

    /// <summary>
    /// DotNetG2P.Spanish marks stress at the start of the syllable ("ˈkasa").
    /// Python's spanish.py, and SpanishPhonemizer's A2 rule (the vowel right
    /// after the mark is stressed), put the mark right before the stressed
    /// vowel ("kˈasa"). A mark with no vowel before the next word boundary
    /// stays where it is.
    /// </summary>
    private static List<string> MoveStressToVowel(List<string> tokens)
    {
        var result = new List<string>(tokens.Count);
        int pending = -1;
        foreach (string token in tokens)
        {
            if (token == Stress)
            {
                pending = result.Count;
                result.Add(token);
                continue;
            }

            if (pending >= 0 && (token == " " || Vowels.Contains(token)))
            {
                if (token != " ")
                {
                    result.RemoveAt(pending);
                    result.Add(Stress);
                }

                pending = -1;
            }

            result.Add(token);
        }

        return result;
    }
}
