using DotNetG2P.French;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="FrenchG2PEngine"/> from DotNetG2P.French
/// to implement <see cref="IFrenchG2PEngine"/>.
/// </summary>
internal sealed class DotNetFrenchG2PEngine : IFrenchG2PEngine
{
    private readonly FrenchG2PEngine _engine = new();

    public List<string> ToPhonemeList(string text)
    {
        string ipa = _engine.ToIPA(text);
        List<string> tokens = IpaTokenizer.Tokenize(ipa);

        // DotNetG2P.French writes the close front rounded vowel as IPA "y"
        // (its glide is "j"). IFrenchG2PEngine and Python use "y_vowel"
        // (PUA U+E01E); a bare "y" is the Japanese glide in the phoneme_id_map.
        for (int i = 0; i < tokens.Count; i++)
        {
            if (tokens[i] == "y")
            {
                tokens[i] = "y_vowel";
            }
        }

        return tokens;
    }
}
