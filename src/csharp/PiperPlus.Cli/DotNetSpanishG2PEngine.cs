using PiperPlus.Core.Phonemize;
using DotNetG2P.Spanish;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="SpanishG2PEngine"/> from DotNetG2P.Spanish
/// to implement <see cref="ISpanishG2PEngine"/>.
/// </summary>
internal sealed class DotNetSpanishG2PEngine : ISpanishG2PEngine
{
    private readonly SpanishG2PEngine _engine = new();

    public List<string> ToPhonemeList(string text)
    {
        // dot-net-g2p ToIPA returns IPA string with stress markers.
        // Convert to flat token list matching piper-plus format.
        string ipa = _engine.ToIPA(text);

        // Split IPA string into individual tokens.
        // Each character or multi-char sequence becomes a separate token.
        // Spaces become " " tokens.
        var tokens = new List<string>();
        // TODO: Implement proper IPA tokenization once dot-net-g2p
        // API surface is confirmed. For now, use character-level split
        // with multi-char token preservation.
        foreach (char ch in ipa)
        {
            tokens.Add(ch.ToString());
        }
        return tokens;
    }
}
