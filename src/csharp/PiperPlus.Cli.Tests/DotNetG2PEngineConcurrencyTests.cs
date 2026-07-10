using System;
using System.Collections.Concurrent;
using System.Linq;
using System.Threading.Tasks;
using PiperPlus.Cli;
using PiperPlus.Core.Phonemize;
using Xunit;

namespace PiperPlus.Cli.Tests;

/// <summary>
/// xUnit fixture that holds shared <see cref="DotNetG2PEngine"/> and
/// <see cref="DotNetEnglishG2PEngine"/> instances for the concurrency tests.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="DotNetG2P.MeCab.MeCabTokenizer"/> holds sys.dic open via
/// memory-mapped IO and does not implement IDisposable in v1.8.x. When
/// each test creates its own <see cref="DotNetG2PEngine"/> via
/// <c>using var engine = new DotNetG2PEngine()</c>, the previous engine's
/// sys.dic handle is not deterministically released before the next
/// engine's constructor tries to open it. On macOS this results in
/// "The process cannot access the file ... because it is being used by
/// another process." (Ubuntu/Windows have more permissive file share
/// semantics and tolerate the brief overlap.)
/// </para>
/// <para>
/// Sharing a single engine across tests via <see cref="IClassFixture{T}"/>
/// keeps sys.dic open exactly once for the lifetime of the test class,
/// eliminating the ctor-vs-teardown race.
/// </para>
/// </remarks>
public sealed class DotNetG2PEngineFixture : IDisposable
{
    // DotNetG2PEngine と DotNetEnglishG2PEngine は PiperPlus.Cli で
    // internal sealed。 xUnit の IClassFixture DI (Activator.CreateInstance)
    // は fixture class を public にする必要があるが、 property 型が internal
    // だと CS0053 で fail する。 property を internal にして accessibility を
    // 揃える (assembly-internal なので tests 側からは問題なくアクセス可能)。
    internal DotNetG2PEngine JaEngine { get; }
    internal DotNetEnglishG2PEngine EnEngine { get; }
    internal MultilingualPhonemizer Multilingual { get; }
    internal JapanesePhonemizer JaPhonemizer { get; }

    public DotNetG2PEngineFixture()
    {
        JaEngine = new DotNetG2PEngine();
        EnEngine = new DotNetEnglishG2PEngine();
        JaPhonemizer = new JapanesePhonemizer(JaEngine);
        var phonemizers = new System.Collections.Generic.Dictionary<string, IPhonemizer>
        {
            ["ja"] = JaPhonemizer,
            ["en"] = new EnglishPhonemizer(EnEngine),
        };
        Multilingual = new MultilingualPhonemizer(phonemizers, "en");
    }

    public void Dispose()
    {
        JaEngine.Dispose();
        // DotNetEnglishG2PEngine is not IDisposable in v1.8.x.
    }
}

/// <summary>
/// Concurrency / regression tests for the CLI-side G2P engine adapters
/// (Issue #383 follow-up).
/// </summary>
/// <remarks>
/// <para>
/// The original Phase 1 PR (<c>af308fd4</c>) added <see cref="SentenceParallelEncoder"/>
/// tests in <c>PiperPlus.Core.Tests</c>, but those tests only exercise the
/// scheduler with a synthetic delegate — they never run real Japanese G2P
/// concurrently. As a result, a thread-safety bug in
/// <c>DotNetG2P.MeCab.MeCabTokenizer</c> (Lattice / ViterbiDecoder mutable
/// state) slipped through and caused <see cref="NullReferenceException"/>
/// crashes on parallel JA input. The fix in <c>c567f5be</c> wraps each
/// worker thread in <see cref="ThreadLocal{T}"/>; these tests guard against
/// any future regression of that contract.
/// </para>
/// <para>
/// <see cref="DotNetG2PEngine"/> is <c>internal sealed</c> in
/// <c>PiperPlus.Cli</c>, so this test project source-links the file
/// (<c>&lt;Compile Link&gt;</c> in the csproj) and exercises it in-process.
/// This mirrors the approach used by <c>PiperPlus.Bench</c>.
/// </para>
/// <para>
/// Uses <see cref="IClassFixture{T}"/> to share a single engine across all
/// tests — see <see cref="DotNetG2PEngineFixture"/> for the macOS sys.dic
/// file-lock rationale.
/// </para>
/// </remarks>
public class DotNetG2PEngineConcurrencyTests : IClassFixture<DotNetG2PEngineFixture>
{
    private const string Ja1 = "こんにちは。";
    private const string Ja2 = "東京駅から新幹線で大阪まで約2時間。";
    private const string Ja3 = "桜の花が満開になりました。";
    private const string Ja4 = "明日の午後3時に渋谷で会いましょう。";

    private readonly DotNetG2PEngineFixture _fx;

    public DotNetG2PEngineConcurrencyTests(DotNetG2PEngineFixture fx)
    {
        _fx = fx;
    }

    /// <summary>
    /// 16 worker threads × 64 conversions each across a small pool of JA
    /// sentences must never throw. Pre-fix this consistently triggered
    /// <c>NullReferenceException</c> in <c>Lattice.ViterbiDecoder.Decode</c>.
    /// </summary>
    [Fact]
    public void DotNetG2PEngine_ConcurrentJa_NoCrash()
    {
        var engine = _fx.JaEngine;
        var sentences = new[] { Ja1, Ja2, Ja3, Ja4 };

        const int workers = 16;
        const int iterationsPerWorker = 64;
        var exceptions = new ConcurrentBag<Exception>();

        Parallel.For(0, workers, new ParallelOptions { MaxDegreeOfParallelism = workers }, w =>
        {
            try
            {
                for (int i = 0; i < iterationsPerWorker; i++)
                {
                    var text = sentences[(w + i) % sentences.Length];
                    G2PResult result = engine.Convert(text);
                    Assert.NotNull(result.Phonemes);
                    Assert.True(
                        result.Phonemes.Length > 0,
                        $"empty phonemes for '{text}' on worker {w} iter {i}");
                }
            }
            catch (Exception ex)
            {
                exceptions.Add(ex);
            }
        });

        Assert.Empty(exceptions);
    }

    /// <summary>
    /// Same sentence convert from many threads must produce the same arrays
    /// (deterministic, no torn writes). Not a strict thread-safety check —
    /// the underlying engine could theoretically be racey *and* still give
    /// the same answer — but combined with the no-crash test above, this
    /// catches any silent state corruption regression.
    /// </summary>
    [Fact]
    public void DotNetG2PEngine_ConcurrentJa_DeterministicResult()
    {
        var engine = _fx.JaEngine;
        G2PResult baseline = engine.Convert(Ja2);

        const int workers = 12;
        const int iterations = 32;
        var observed = new ConcurrentBag<G2PResult>();

        Parallel.For(0, workers, new ParallelOptions { MaxDegreeOfParallelism = workers }, _ =>
        {
            for (int i = 0; i < iterations; i++)
            {
                observed.Add(engine.Convert(Ja2));
            }
        });

        Assert.Equal(workers * iterations, observed.Count);
        foreach (G2PResult r in observed)
        {
            Assert.Equal(baseline.Phonemes, r.Phonemes);
            Assert.Equal(baseline.A1, r.A1);
            Assert.Equal(baseline.A2, r.A2);
            Assert.Equal(baseline.A3, r.A3);
        }
    }

    /// <summary>
    /// End-to-end Phase 1 contract: feed a multi-sentence JA input through
    /// <see cref="JapanesePhonemizer"/> (which holds a single
    /// <see cref="DotNetG2PEngine"/>) under both serial
    /// (<c>PIPER_PLUS_G2P_PARALLELISM=1</c>) and auto modes — outputs must match
    /// sentence-by-sentence. This is the regression scenario the original
    /// Phase 1 tests missed (synthetic delegate didn't touch MeCab).
    /// </summary>
    [Fact]
    public void SentenceParallelEncoder_JaInput_MatchesSerial()
    {
        var phonemizer = _fx.JaPhonemizer;

        var sentences = new[] { Ja1, Ja2, Ja3, Ja4, Ja1, Ja2, Ja3, Ja4 };

        var prev = Environment.GetEnvironmentVariable(
            SentenceParallelEncoder.ParallelismEnvVar);
        try
        {
            Environment.SetEnvironmentVariable(
                SentenceParallelEncoder.ParallelismEnvVar, "1");
            List<string>[] serial = SentenceParallelEncoder.EncodeAll(
                sentences, phonemizer.Phonemize);

            Environment.SetEnvironmentVariable(
                SentenceParallelEncoder.ParallelismEnvVar, null);
            List<string>[] parallel = SentenceParallelEncoder.EncodeAll(
                sentences, phonemizer.Phonemize);

            Assert.Equal(sentences.Length, serial.Length);
            Assert.Equal(serial.Length, parallel.Length);
            for (int i = 0; i < sentences.Length; i++)
            {
                Assert.Equal(serial[i], parallel[i]);
            }
        }
        finally
        {
            Environment.SetEnvironmentVariable(
                SentenceParallelEncoder.ParallelismEnvVar, prev);
        }
    }

    /// <summary>
    /// Mixed-language input through <see cref="MultilingualPhonemizer"/>
    /// (JA + EN) must not crash under parallel encoding. This guards
    /// against the multilingual dispatch routing JA segments to a shared
    /// MeCab instance from multiple worker threads.
    /// </summary>
    [Fact]
    public void SentenceParallelEncoder_MixedLang_NoCrash()
    {
        var multilingual = _fx.Multilingual;

        var sentences = new[]
        {
            "こんにちは、Hello world.",
            "東京駅で waiting です。",
            "Tomorrow at 3pm 渋谷で会いましょう。",
            "Pure English sentence here.",
            "純粋な日本語の文章です。",
            Ja2,
            Ja3,
            Ja4,
        };

        var exceptions = new ConcurrentBag<Exception>();
        Parallel.For(0, 8, new ParallelOptions { MaxDegreeOfParallelism = 8 }, _ =>
        {
            try
            {
                List<string>[] results = SentenceParallelEncoder.EncodeAll(
                    sentences, multilingual.Phonemize, parallelismOverride: 4);
                Assert.Equal(sentences.Length, results.Length);
                Assert.All(results, tokens =>
                {
                    Assert.NotNull(tokens);
                    Assert.NotEmpty(tokens);
                });
            }
            catch (Exception ex)
            {
                exceptions.Add(ex);
            }
        });

        Assert.Empty(exceptions);
    }
}
