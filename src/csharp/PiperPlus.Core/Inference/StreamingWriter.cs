using System;
using System.IO;
using System.Runtime.InteropServices;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Writes raw PCM int16 audio data to a stream in chunked or immediate mode.
/// No WAV header is emitted -- callers receive a bare little-endian int16 byte
/// stream suitable for piping into <c>aplay</c>, <c>ffplay</c>, or any other
/// raw-PCM consumer.
/// </summary>
/// <remarks>
/// <para>
/// This mirrors the C++ streaming output path in <c>main.cpp:rawOutputProc</c>,
/// which writes <c>int16_t</c> data directly to <c>stdout</c> and flushes after
/// each chunk to ensure low-latency delivery to downstream consumers.
/// </para>
/// <para>
/// Both methods flush after every write so that a downstream process (or audio
/// device) receives data as soon as it is available, rather than waiting for the
/// stream's internal buffer to fill up.
/// </para>
/// </remarks>
public static class StreamingWriter
{
    /// <summary>
    /// Default number of samples per chunk (1024 samples = 2048 bytes at 16-bit).
    /// </summary>
    private const int DefaultChunkSamples = 1024;

    /// <summary>
    /// Writes PCM samples to <paramref name="output"/> in fixed-size chunks,
    /// flushing after each chunk for real-time delivery.
    /// </summary>
    /// <param name="output">Destination stream (e.g. <c>Console.OpenStandardOutput()</c>).</param>
    /// <param name="samples">16-bit PCM samples to write.</param>
    /// <param name="chunkSamples">
    /// Number of samples per chunk. The final chunk may be smaller if
    /// <paramref name="samples"/> length is not evenly divisible.
    /// Defaults to 1024.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="output"/> is <c>null</c>.</exception>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="chunkSamples"/> is not positive.</exception>
    public static void WriteChunked(
        Stream output,
        ReadOnlySpan<short> samples,
        int chunkSamples = DefaultChunkSamples)
    {
        if (output is null)
            throw new ArgumentNullException(nameof(output));
        if (chunkSamples <= 0)
            throw new ArgumentOutOfRangeException(nameof(chunkSamples), "Chunk size must be positive.");

        if (samples.IsEmpty)
            return;

        int offset = 0;
        while (offset < samples.Length)
        {
            int remaining = samples.Length - offset;
            int count = Math.Min(chunkSamples, remaining);

            ReadOnlySpan<short> chunk = samples.Slice(offset, count);
            ReadOnlySpan<byte> bytes = MemoryMarshal.AsBytes(chunk);

            output.Write(bytes);
            output.Flush();

            offset += count;
        }
    }

    /// <summary>
    /// Writes all <paramref name="samples"/> to <paramref name="output"/> in a
    /// single operation and flushes immediately. Use this when chunked delivery
    /// is unnecessary (e.g. the buffer is already small enough).
    /// </summary>
    /// <param name="output">Destination stream.</param>
    /// <param name="samples">16-bit PCM samples to write.</param>
    /// <exception cref="ArgumentNullException"><paramref name="output"/> is <c>null</c>.</exception>
    public static void WriteImmediate(Stream output, ReadOnlySpan<short> samples)
    {
        if (output is null)
            throw new ArgumentNullException(nameof(output));

        if (samples.IsEmpty)
            return;

        ReadOnlySpan<byte> bytes = MemoryMarshal.AsBytes(samples);
        output.Write(bytes);
        output.Flush();
    }
}
