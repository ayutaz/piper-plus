using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Parallelizes per-sentence G2P encoding so multi-sentence inputs can encode
/// all sentences before sequentially running ONNX inference.
/// </summary>
/// <remarks>
/// <para>
/// This is Phase 1 of issue #383. The Python runtime ships the same design
/// (see <c>src/python_run/piper/voice.py</c>: <c>_resolve_g2p_parallelism</c> /
/// <c>_map_sentences</c>). The G2P pass typically accounts for 19~26% of cold-cache
/// total latency on multi-sentence inputs; parallelising it leaves the ORT
/// inference pipeline unchanged while shaving that fraction.
/// </para>
/// <para>
/// <b>Thread-safety contract.</b> The supplied per-sentence delegate is invoked
/// from worker threads, so callers must ensure the captured phonemizer and
/// dictionary state is safe under concurrent reads. The bundled phonemizers
/// are immutable after construction, satisfying this contract.
/// </para>
/// <para>
/// <b>Auto cap = 4.</b> Mirrors the Python rationale: ORT typically uses
/// ~4 intra-op threads, and most G2P backends wrap native code where 2~4
/// threads already saturate available work. Setting
/// <c>PIPER_G2P_PARALLELISM=1</c> restores the strictly-serial path.
/// </para>
/// </remarks>
public static class SentenceParallelEncoder
{
    /// <summary>Upper bound on the auto-resolved worker count.</summary>
    public const int AutoParallelismCap = 4;

    /// <summary>Environment variable that overrides the auto-resolved worker count.</summary>
    public const string ParallelismEnvVar = "PIPER_G2P_PARALLELISM";

    /// <summary>
    /// Decide how many workers to spend on the G2P pass.
    /// </summary>
    /// <param name="sentenceCount">Number of sentences to encode.</param>
    /// <returns>
    /// <c>1</c> to take the strictly-serial path (zero <see cref="Parallel"/> overhead).
    /// <c>&gt;= 2</c> for parallel encoding.
    /// </returns>
    /// <remarks>
    /// Resolution order:
    /// <list type="bullet">
    ///   <item><c>PIPER_G2P_PARALLELISM=1</c>: force serial.</item>
    ///   <item><c>PIPER_G2P_PARALLELISM=N</c> (N &gt;= 2): force N workers
    ///     (capped at <paramref name="sentenceCount"/>).</item>
    ///   <item>Otherwise (auto): <c>min(sentenceCount, max(2, cores/2),
    ///     <see cref="AutoParallelismCap"/>)</c>. Falls back to 1 when
    ///     <paramref name="sentenceCount"/> &lt;= 1.</item>
    /// </list>
    /// Invalid env values fall through to auto.
    /// </remarks>
    public static int ResolveParallelism(int sentenceCount)
    {
        string? raw = Environment.GetEnvironmentVariable(ParallelismEnvVar)?.Trim();
        if (!string.IsNullOrEmpty(raw))
        {
            if (int.TryParse(raw, out int n))
            {
                if (n <= 1)
                {
                    return 1;
                }

                return Math.Max(1, Math.Min(n, sentenceCount));
            }

            // Invalid: fall through to auto.
        }

        if (sentenceCount <= 1)
        {
            return 1;
        }

        int cores = Environment.ProcessorCount;
        int autoWorkers = Math.Min(Math.Max(2, cores / 2), AutoParallelismCap);
        return Math.Max(1, Math.Min(sentenceCount, autoWorkers));
    }

    /// <summary>
    /// Apply <paramref name="encodeOne"/> to each sentence and return the
    /// results in input order.
    /// </summary>
    /// <typeparam name="TResult">Encoded sentence payload type.</typeparam>
    /// <param name="sentences">Sentences to encode.</param>
    /// <param name="encodeOne">Per-sentence encoder. Must be safe to invoke from
    /// multiple threads concurrently when parallel mode is selected.</param>
    /// <param name="parallelismOverride">Optional explicit worker count.
    /// Pass <c>null</c> to use <see cref="ResolveParallelism"/>.</param>
    /// <returns>Per-sentence encoded results in the same order as <paramref name="sentences"/>.</returns>
    public static TResult[] EncodeAll<TResult>(
        IReadOnlyList<string> sentences,
        Func<string, TResult> encodeOne,
        int? parallelismOverride = null)
    {
        ArgumentNullException.ThrowIfNull(sentences);
        ArgumentNullException.ThrowIfNull(encodeOne);

        int parallelism = parallelismOverride ?? ResolveParallelism(sentences.Count);
        var results = new TResult[sentences.Count];

        if (parallelism <= 1 || sentences.Count <= 1)
        {
            for (int i = 0; i < sentences.Count; i++)
            {
                results[i] = encodeOne(sentences[i]);
            }

            return results;
        }

        // Parallel.For with index-based writes preserves output order even
        // though work units complete out-of-order.
        var options = new ParallelOptions { MaxDegreeOfParallelism = parallelism };
        Parallel.For(0, sentences.Count, options, i =>
        {
            results[i] = encodeOne(sentences[i]);
        });
        return results;
    }
}
