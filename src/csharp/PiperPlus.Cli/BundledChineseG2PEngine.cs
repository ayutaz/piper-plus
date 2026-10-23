using System;
using System.IO;
using System.Reflection;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

/// <summary>
/// Chinese G2P for the CLI: <see cref="PinyinDictionaryChineseG2PEngine"/>
/// over the shared numeric-tone pinyin dictionaries embedded in this assembly
/// (linked from <c>src/rust/piper-plus-g2p/data</c>, the canonical copy).
/// <para>
/// This replaced the DotNetG2P.Chinese adapter, whose output disagreed with
/// the Python reference in 43 of 47 golden cases: tone markers were added a
/// second time on top of the ones <c>ToPuaPhonemes</c> already returns,
/// multi-character IPA such as <c>ts</c> was left unmapped and dropped by the
/// encoder, and its phoneme inventory and dictionary differ from what the
/// models were trained on (issue #790).
/// </para>
/// </summary>
internal sealed class BundledChineseG2PEngine : IChineseG2PEngine
{
    // ~2.7 MB of JSON; parse once per process.
    private static readonly Lazy<PinyinDictionaryChineseG2PEngine> Shared = new(Load);

    public ChineseG2PResult Convert(string text) => Shared.Value.Convert(text);

    private static PinyinDictionaryChineseG2PEngine Load()
    {
        Assembly assembly = typeof(BundledChineseG2PEngine).Assembly;
        using Stream single = Open(assembly, "PiperPlus.Cli.pinyin_single.json");
        using Stream phrases = Open(assembly, "PiperPlus.Cli.pinyin_phrases.json");
        return PinyinDictionaryChineseG2PEngine.FromJson(single, phrases);
    }

    private static Stream Open(Assembly assembly, string name) =>
        assembly.GetManifestResourceStream(name)
        ?? throw new InvalidOperationException($"Embedded pinyin dictionary '{name}' is missing from {assembly.GetName().Name}.");
}
