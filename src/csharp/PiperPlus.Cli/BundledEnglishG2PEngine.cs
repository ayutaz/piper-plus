using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

/// <summary>
/// English G2P for the CLI: <see cref="EnglishG2PEngine"/> over the shared
/// CMU dictionary embedded in this assembly (linked from
/// <c>src/rust/piper-plus-g2p/data</c>, the canonical copy).
/// <para>
/// This replaced the DotNetG2P.English adapter, whose dictionary and
/// letter-to-sound rules differ from Python's g2p_en (Issue #832), and which
/// did not expand numbers: digits were passed through as raw characters that
/// are not in the model's <c>phoneme_id_map</c> (Issue #821).
/// </para>
/// </summary>
internal sealed class BundledEnglishG2PEngine : IEnglishG2PEngine
{
    // ~3.7 MB of JSON; parse once per process.
    private static readonly Lazy<EnglishG2PEngine> Shared = new(Load);

    public List<List<string>> ConvertToArpabet(string text) => Shared.Value.ConvertToArpabet(text);

    private static EnglishG2PEngine Load()
    {
        Assembly assembly = typeof(BundledEnglishG2PEngine).Assembly;
        const string name = "PiperPlus.Cli.cmudict_data.json";
        using Stream stream = assembly.GetManifestResourceStream(name)
            ?? throw new InvalidOperationException($"Embedded CMU dictionary '{name}' is missing from {assembly.GetName().Name}.");
        return EnglishG2PEngine.FromJson(stream);
    }
}
