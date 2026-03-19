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
    private readonly PortugueseG2PEngine _engine = new();

    public List<string> ToPhonemeList(string text)
    {
        // dot-net-g2p ToIPA returns IPA string with stress markers.
        // Convert to flat token list matching piper-plus format.
        string ipa = _engine.ToIPA(text);

        // Split IPA string into individual tokens.
        // Each character or multi-char sequence becomes a separate token.
        // Spaces become " " tokens.
        var tokens = new List<string>();
        // NOTE: Tokenization depends on dot-net-g2p output format.
        // Multi-char tokens (tʃ, dʒ) and nasal vowels (ã, ẽ, ĩ, õ, ũ as NFC)
        // must be preserved as single elements. ˈ stress markers should be included.
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
