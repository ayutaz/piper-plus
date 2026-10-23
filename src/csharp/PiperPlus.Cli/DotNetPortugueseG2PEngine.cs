using System.Text;
using DotNetG2P.Portuguese;
using PiperPlus.Core.Phonemize;

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
        // DotNetG2P.Portuguese ties affricates with U+0361 (t͡ʃ, d͡ʒ). The tie
        // bar is a combining mark, so the tokenizer would emit "d͡" + "ʒ"
        // instead of the "dʒ" digraph that IPortugueseG2PEngine promises.
        // It also writes nasal vowels decomposed ("i" + U+0303); the
        // interface, Python and the phoneme_id_map use the NFC form ("ĩ").
        string ipa = _engine.ToIPA(text).Normalize(NormalizationForm.FormC).Replace("\u0361", string.Empty, StringComparison.Ordinal);
        return IpaTokenizer.Tokenize(ipa, PortugueseDigraphs);
    }
}
