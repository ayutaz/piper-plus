using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="SentenceParallelEncoder"/> — Phase 1 of issue #383
/// (parallel per-sentence G2P).
/// </summary>
public class SentenceParallelEncoderTests
{
    /// <summary>
    /// Set PIPER_G2P_PARALLELISM for the duration of the test, restoring on Dispose.
    /// </summary>
    private sealed class EnvScope : IDisposable
    {
        private readonly string? _previous;
        public EnvScope(string? value)
        {
            _previous = Environment.GetEnvironmentVariable(SentenceParallelEncoder.ParallelismEnvVar);
            Environment.SetEnvironmentVariable(SentenceParallelEncoder.ParallelismEnvVar, value);
        }
        public void Dispose() =>
            Environment.SetEnvironmentVariable(SentenceParallelEncoder.ParallelismEnvVar, _previous);
    }

    // ================================================================
    // ResolveParallelism
    // ================================================================

    [Fact]
    public void ResolveParallelism_ZeroOrOneSentence_ReturnsOne()
    {
        using var _ = new EnvScope(null);
        Assert.Equal(1, SentenceParallelEncoder.ResolveParallelism(0));
        Assert.Equal(1, SentenceParallelEncoder.ResolveParallelism(1));
    }

    [Fact]
    public void ResolveParallelism_AutoForMultipleSentences_WithinCap()
    {
        using var _ = new EnvScope(null);
        int n = SentenceParallelEncoder.ResolveParallelism(8);
        Assert.InRange(n, 2, SentenceParallelEncoder.AutoParallelismCap);
        Assert.True(n <= 8);
    }

    [Fact]
    public void ResolveParallelism_AutoCappedByNSentences()
    {
        using var _ = new EnvScope(null);
        Assert.True(SentenceParallelEncoder.ResolveParallelism(2) <= 2);
    }

    [Fact]
    public void ResolveParallelism_ExplicitOne_ForcesSerial()
    {
        using var _ = new EnvScope("1");
        Assert.Equal(1, SentenceParallelEncoder.ResolveParallelism(10));
    }

    [Fact]
    public void ResolveParallelism_ExplicitN_OverridesAutoButCappedByCount()
    {
        using var _ = new EnvScope("8");
        Assert.Equal(3, SentenceParallelEncoder.ResolveParallelism(3));
        Assert.Equal(8, SentenceParallelEncoder.ResolveParallelism(20));
    }

    [Fact]
    public void ResolveParallelism_InvalidEnv_FallsBackToAuto()
    {
        using var _ = new EnvScope("garbage");
        int n = SentenceParallelEncoder.ResolveParallelism(8);
        Assert.True(n >= 2);
    }

    [Fact]
    public void ResolveParallelism_ExplicitZero_TreatedAsSerial()
    {
        using var _ = new EnvScope("0");
        Assert.Equal(1, SentenceParallelEncoder.ResolveParallelism(10));
    }

    // ================================================================
    // EncodeAll
    // ================================================================

    [Fact]
    public void EncodeAll_EmptyInput_ReturnsEmptyArray()
    {
        var result = SentenceParallelEncoder.EncodeAll(
            Array.Empty<string>(), s => s.ToUpperInvariant(), parallelismOverride: 4);
        Assert.Empty(result);
    }

    [Fact]
    public void EncodeAll_SingleSentence_DoesNotSpawnParallel()
    {
        // Capture the thread ID seen by the delegate. With a single input the
        // serial fast path must run on the calling thread.
        int callerTid = Environment.CurrentManagedThreadId;
        int seenTid = -1;
        var result = SentenceParallelEncoder.EncodeAll(
            new[] { "hello" },
            s =>
            {
                seenTid = Environment.CurrentManagedThreadId;
                return s.ToUpperInvariant();
            },
            parallelismOverride: 4);
        Assert.Equal(new[] { "HELLO" }, result);
        Assert.Equal(callerTid, seenTid);
    }

    [Fact]
    public void EncodeAll_PreservesOrder()
    {
        var sentences = new[] { "a", "b", "c", "d", "e", "f", "g", "h" };
        var result = SentenceParallelEncoder.EncodeAll(
            sentences, s => string.Concat(Enumerable.Repeat(s, 3)), parallelismOverride: 4);
        Assert.Equal(new[] { "aaa", "bbb", "ccc", "ddd", "eee", "fff", "ggg", "hhh" }, result);
    }

    [Fact]
    public void EncodeAll_SerialMatchesParallel()
    {
        var sentences = Enumerable.Range(0, 20).Select(i => $"sentence_{i}").ToArray();
        Func<string, (string Text, int Len)> encode = s => (s, s.Length);

        var serial = SentenceParallelEncoder.EncodeAll(sentences, encode, parallelismOverride: 1);
        var parallel = SentenceParallelEncoder.EncodeAll(sentences, encode, parallelismOverride: 4);

        Assert.Equal(serial, parallel);
    }

    [Fact]
    public void EncodeAll_PropagatesExceptions()
    {
        var sentences = new[] { "ok", "fail", "ok2" };
        var ex = Assert.Throws<AggregateException>(() =>
            SentenceParallelEncoder.EncodeAll(
                sentences,
                s =>
                {
                    if (s == "fail")
                    {
                        throw new InvalidOperationException("kaboom");
                    }
                    return s;
                },
                parallelismOverride: 4));
        Assert.Contains(ex.InnerExceptions, e => e.Message == "kaboom");
    }

    [Fact]
    public void EncodeAll_ParallelismOverride_ZeroOrNegative_RunsSerial()
    {
        var sentences = new[] { "a", "b", "c" };
        int callerTid = Environment.CurrentManagedThreadId;
        var seen = new ConcurrentBag<int>();

        var result = SentenceParallelEncoder.EncodeAll(
            sentences,
            s =>
            {
                seen.Add(Environment.CurrentManagedThreadId);
                return s;
            },
            parallelismOverride: 1);

        Assert.Equal(sentences, result);
        // All work observed on the caller thread.
        Assert.All(seen, tid => Assert.Equal(callerTid, tid));
    }

    [Fact]
    public void EncodeAll_RespectsEnvSerialOverride()
    {
        using var _ = new EnvScope("1");
        var sentences = Enumerable.Range(0, 10).Select(i => i.ToString()).ToArray();
        int callerTid = Environment.CurrentManagedThreadId;
        var seen = new ConcurrentBag<int>();

        var result = SentenceParallelEncoder.EncodeAll(
            sentences,
            s =>
            {
                seen.Add(Environment.CurrentManagedThreadId);
                return s;
            });

        Assert.Equal(sentences, result);
        Assert.All(seen, tid => Assert.Equal(callerTid, tid));
    }

    [Fact]
    public void EncodeAll_LargeBatchPreservesOrder()
    {
        // Stress order preservation with 200 items — Parallel.For dispatches
        // chunks out-of-order across workers, so the index-based write path
        // must still land each result at its original position.
        var sentences = Enumerable.Range(0, 200).Select(i => i.ToString()).ToArray();
        var result = SentenceParallelEncoder.EncodeAll(
            sentences,
            s =>
            {
                // Non-trivial work per item to keep workers active.
                int sum = 0;
                for (int i = 0; i < 100; i++) sum += i;
                return $"{s}_{sum}";
            },
            parallelismOverride: 4);

        Assert.Equal(sentences.Length, result.Length);
        for (int i = 0; i < sentences.Length; i++)
        {
            Assert.Equal($"{sentences[i]}_4950", result[i]);
        }
    }
}
