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
/// <para>
/// Before creating the <see cref="MeCabTokenizer"/>, this class uses
/// <see cref="DictionaryManager"/> to ensure the naist-jdic dictionary is available.
/// If the dictionary is not found locally, it will be downloaded automatically
/// (unless offline mode or auto-download is disabled).
/// </para>
/// <para>
/// <b>Thread-safety (issue #383 follow-up).</b> <see cref="G2PEngine"/> /
/// <see cref="MeCabTokenizer"/> hold mutable Lattice / ViterbiDecoder state
/// internally and are <em>not</em> safe to call from multiple threads at
/// once — concurrent calls cause <c>NullReferenceException</c> in
/// <c>Lattice.ViterbiDecoder.Decode</c>. We allocate one engine per worker
/// thread via <see cref="ThreadLocal{T}"/> so Phase 1 parallel encoding
/// (<see cref="SentenceParallelEncoder"/>) can dispatch from multiple threads
/// without contention. Each worker pays the engine-construction cost once.
/// </para>
/// </remarks>
internal sealed class DotNetG2PEngine : IJapaneseG2PEngine, IDisposable
{
    // Serialize MeCabTokenizer construction across threads.
    // DotNetG2P.MeCab 1.8.x opens sys.dic with an exclusive FileShare during
    // construction; concurrent ctor calls (e.g. ThreadLocal factory firing
    // on every parallel worker's first Convert call) race on file-lock
    // acquisition and throw IOException. Locking only the ctor keeps the
    // per-thread engine isolation that follows — once each thread has its
    // own tokenizer instance, Convert() runs in parallel without contention.
    private static readonly object S_tokenizerCtorLock = new object();

    private readonly string _dictPath;
    private readonly ThreadLocal<G2PEngine> _threadLocalEngine;

    public DotNetG2PEngine()
    {
        // Ensure dictionary is available (download if necessary).
        // Block on async since the G2PEngine constructor is synchronous.
        _dictPath = DictionaryManager.EnsureDictionaryAsync().GetAwaiter().GetResult();

        // Set NAIST_JDIC_PATH so DotNetG2P.MeCab NaistJdicLocator can find it,
        // and also pass the path directly to the MeCabTokenizer constructor.
        Environment.SetEnvironmentVariable("NAIST_JDIC_PATH", _dictPath);

        _threadLocalEngine = new ThreadLocal<G2PEngine>(
            valueFactory: () =>
            {
                // sys.dic file-lock race workaround for DotNetG2P.MeCab 1.8.x
                lock (S_tokenizerCtorLock)
                {
                    return new G2PEngine(new MeCabTokenizer(_dictPath));
                }
            },
            trackAllValues: true);
    }

    public G2PResult Convert(string text)
    {
        G2PEngine engine = _threadLocalEngine.Value
            ?? throw new InvalidOperationException(
                "ThreadLocal G2PEngine value factory returned null.");
        var features = engine.ToProsodyFeatures(text);

        // ProsodyFeatures uses IReadOnlyList; G2PResult expects arrays.
        var phonemes = new string[features.Phonemes.Count];
        var a1 = new int[features.A1.Count];
        var a2 = new int[features.A2.Count];
        var a3 = new int[features.A3.Count];

        for (int i = 0; i < features.Phonemes.Count; i++)
        {
            phonemes[i] = features.Phonemes[i];
        }

        for (int i = 0; i < features.A1.Count; i++)
        {
            a1[i] = features.A1[i];
        }

        for (int i = 0; i < features.A2.Count; i++)
        {
            a2[i] = features.A2[i];
        }

        for (int i = 0; i < features.A3.Count; i++)
        {
            a3[i] = features.A3[i];
        }

        return new G2PResult(phonemes, a1, a2, a3);
    }

    public void Dispose()
    {
        // G2PEngine / MeCabTokenizer don't expose IDisposable in DotNetG2P 1.8.x,
        // but the ThreadLocal wrapper itself owns ManualResetEvents that need
        // disposing.
        _threadLocalEngine.Dispose();
    }
}
