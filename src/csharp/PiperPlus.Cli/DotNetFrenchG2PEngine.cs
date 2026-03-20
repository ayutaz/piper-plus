using PiperPlus.Core.Phonemize;
using DotNetG2P.French;

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
        return IpaTokenizer.Tokenize(ipa);
    }
}
