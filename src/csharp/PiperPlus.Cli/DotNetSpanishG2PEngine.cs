using PiperPlus.Core.Phonemize;
using DotNetG2P.Spanish;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="SpanishG2PEngine"/> from DotNetG2P.Spanish
/// to implement <see cref="ISpanishG2PEngine"/>.
/// </summary>
internal sealed class DotNetSpanishG2PEngine : ISpanishG2PEngine
{
    private static readonly HashSet<string> SpanishDigraphs = ["rr", "t\u0283", "d\u0292"];

    private readonly SpanishG2PEngine _engine = new();

    public List<string> ToPhonemeList(string text)
    {
        string ipa = _engine.ToIPA(text);
        return IpaTokenizer.Tokenize(ipa, SpanishDigraphs);
    }
}
