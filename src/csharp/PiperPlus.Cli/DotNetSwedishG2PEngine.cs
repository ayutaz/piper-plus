using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter implementing <see cref="ISwedishG2PEngine"/> by delegating to
/// the rule-based <see cref="SwedishG2PEngine"/> in PiperPlus.Core.
/// </summary>
internal sealed class DotNetSwedishG2PEngine : ISwedishG2PEngine
{
    private readonly SwedishG2PEngine _engine = new();

    public List<string> ToPhonemeList(string text)
    {
        return _engine.ToPhonemeList(text);
    }
}
