using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

/// <summary>
/// Stub adapter implementing <see cref="ISwedishG2PEngine"/>.
/// <para>
/// TODO: Replace with a proper DotNetG2P.Swedish NuGet package when available.
/// Currently performs a basic character-level fallback: lowercases the input,
/// splits into words, and returns each character as a separate IPA token with
/// spaces between words. This produces usable (though imprecise) phoneme
/// sequences for Swedish models until a real rule-based or dictionary-backed
/// G2P engine is implemented.
/// </para>
/// </summary>
internal sealed class DotNetSwedishG2PEngine : ISwedishG2PEngine
{
    public List<string> ToPhonemeList(string text)
    {
        string lower = text.ToLowerInvariant().Trim();
        if (string.IsNullOrEmpty(lower))
            return [];

        var tokens = new List<string>(lower.Length * 2);

        for (int i = 0; i < lower.Length; i++)
        {
            char c = lower[i];

            if (c == ' ')
            {
                // Collapse consecutive spaces; avoid leading/trailing space tokens.
                if (tokens.Count > 0 && tokens[^1] != " ")
                    tokens.Add(" ");
            }
            else if (IsPunctuation(c))
            {
                tokens.Add(c.ToString());
            }
            else if (char.IsLetter(c))
            {
                tokens.Add(c.ToString());
            }
            // Skip digits and other non-letter characters.
        }

        // Remove trailing space if present.
        if (tokens.Count > 0 && tokens[^1] == " ")
            tokens.RemoveAt(tokens.Count - 1);

        return tokens;
    }

    private static bool IsPunctuation(char c) =>
        c is '.' or ',' or ';' or ':' or '!' or '?';
}
