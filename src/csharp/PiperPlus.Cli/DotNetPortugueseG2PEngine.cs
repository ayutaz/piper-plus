using PiperPlus.Core.Phonemize;
using DotNetG2P.Portuguese;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="PortugueseG2PEngine"/> from DotNetG2P.Portuguese
/// to implement <see cref="IPortugueseG2PEngine"/>.
/// Brazilian Portuguese is the default dialect.
/// </summary>
internal sealed class DotNetPortugueseG2PEngine : IPortugueseG2PEngine
{
    private static readonly HashSet<string> PortugueseDigraphs = ["t\u0283", "d\u0292"];

    private readonly PortugueseG2PEngine _engine = new();

    public List<string> ToPhonemeList(string text)
    {
        string ipa = _engine.ToIPA(text);
        return IpaTokenizer.Tokenize(ipa, PortugueseDigraphs);
    }
}
