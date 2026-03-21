using DotNetG2P;
using DotNetG2P.MeCab;
using PiperPlus.Core.Config;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="G2PEngine"/> (DotNetG2P.Core + DotNetG2P.MeCab)
/// to implement <see cref="IJapaneseG2PEngine"/> for piper-plus Japanese phonemization.
/// </summary>
/// <remarks>
/// Before creating the <see cref="MeCabTokenizer"/>, this class uses
/// <see cref="DictionaryManager"/> to ensure the naist-jdic dictionary is available.
/// If the dictionary is not found locally, it will be downloaded automatically
/// (unless offline mode or auto-download is disabled).
/// </remarks>
internal sealed class DotNetG2PEngine : IJapaneseG2PEngine
{
    private readonly G2PEngine _engine;

    public DotNetG2PEngine()
    {
        // Ensure dictionary is available (download if necessary).
        // Block on async since the G2PEngine constructor is synchronous.
        var dictPath = DictionaryManager.EnsureDictionaryAsync().GetAwaiter().GetResult();

        // Set NAIST_JDIC_PATH so DotNetG2P.MeCab NaistJdicLocator can find it,
        // and also pass the path directly to the MeCabTokenizer constructor.
        Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", dictPath);

        var tokenizer = new MeCabTokenizer(dictPath);
        _engine = new G2PEngine(tokenizer);
    }

    public G2PResult Convert(string text)
    {
        var features = _engine.ToProsodyFeatures(text);

        // ProsodyFeatures uses IReadOnlyList; G2PResult expects arrays.
        var phonemes = new string[features.Phonemes.Count];
        var a1 = new int[features.A1.Count];
        var a2 = new int[features.A2.Count];
        var a3 = new int[features.A3.Count];

        for (int i = 0; i < features.Phonemes.Count; i++)
            phonemes[i] = features.Phonemes[i];
        for (int i = 0; i < features.A1.Count; i++)
            a1[i] = features.A1[i];
        for (int i = 0; i < features.A2.Count; i++)
            a2[i] = features.A2[i];
        for (int i = 0; i < features.A3.Count; i++)
            a3[i] = features.A3[i];

        return new G2PResult(phonemes, a1, a2, a3);
    }
}
