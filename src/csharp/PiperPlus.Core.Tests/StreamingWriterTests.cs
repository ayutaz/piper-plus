using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Dedicated tests for <see cref="StreamingWriter"/>: chunked and immediate
/// raw PCM int16 output to a stream.
/// </summary>
public sealed class StreamingWriterTests
{
    // ================================================================
    // WriteChunked
    // ================================================================

    [Fact]
    public void WriteChunked_CorrectTotalBytes()
    {
        short[] samples = [100, -200, 300, 400, -500];
        using var ms = new MemoryStream();

        StreamingWriter.WriteChunked(ms, samples.AsSpan());

        Assert.Equal(samples.Length * 2, (int)ms.Length);
    }

    [Fact]
    public void WriteChunked_MultipleChunks_AllDataWritten()
    {
        // 5 samples with chunkSize=2 => 3 chunks (2 + 2 + 1)
        short[] samples = [10, 20, 30, 40, 50];
        using var ms = new MemoryStream();

        StreamingWriter.WriteChunked(ms, samples.AsSpan(), chunkSamples: 2);

        Assert.Equal(samples.Length * 2, (int)ms.Length);

        // Verify every sample was written correctly across chunk boundaries
        ms.Position = 0;
        using var reader = new BinaryReader(ms);
        for (int i = 0; i < samples.Length; i++)
        {
            Assert.Equal(samples[i], reader.ReadInt16());
        }
    }

    [Fact]
    public void WriteChunked_EmptySamples_NoBytesWritten()
    {
        using var ms = new MemoryStream();

        StreamingWriter.WriteChunked(ms, ReadOnlySpan<short>.Empty);

        Assert.Equal(0, (int)ms.Length);
    }

    [Fact]
    public void WriteChunked_NullStream_ThrowsArgumentNullException()
    {
        short[] samples = [1, 2, 3];

        Assert.Throws<ArgumentNullException>(
            () => StreamingWriter.WriteChunked(null!, samples.AsSpan()));
    }

    [Fact]
    public void WriteChunked_InvalidChunkSize_Zero_Throws()
    {
        short[] samples = [1, 2];
        using var ms = new MemoryStream();

        Assert.Throws<ArgumentOutOfRangeException>(
            () => StreamingWriter.WriteChunked(ms, samples.AsSpan(), chunkSamples: 0));
    }

    [Fact]
    public void WriteChunked_InvalidChunkSize_Negative_Throws()
    {
        short[] samples = [1, 2];
        using var ms = new MemoryStream();

        Assert.Throws<ArgumentOutOfRangeException>(
            () => StreamingWriter.WriteChunked(ms, samples.AsSpan(), chunkSamples: -5));
    }

    [Fact]
    public void WriteChunked_DefaultChunkSize_1024()
    {
        // 2048 samples should produce 4096 bytes using the default chunk size (1024).
        // With 2048 samples and default chunkSamples=1024, exactly 2 full chunks.
        short[] samples = new short[2048];
        for (int i = 0; i < samples.Length; i++)
            samples[i] = (short)(i % short.MaxValue);

        using var ms = new MemoryStream();

        StreamingWriter.WriteChunked(ms, samples.AsSpan());

        Assert.Equal(2048 * 2, (int)ms.Length);

        // Verify round-trip of all sample values
        ms.Position = 0;
        using var reader = new BinaryReader(ms);
        for (int i = 0; i < samples.Length; i++)
        {
            Assert.Equal(samples[i], reader.ReadInt16());
        }
    }

    [Fact]
    public void WriteChunked_FinalPartialChunk_Correct()
    {
        // 7 samples with chunkSize=3 => 3 chunks: [3] + [3] + [1 remainder]
        short[] samples = [11, 22, 33, 44, 55, 66, 77];
        using var ms = new MemoryStream();

        StreamingWriter.WriteChunked(ms, samples.AsSpan(), chunkSamples: 3);

        Assert.Equal(7 * 2, (int)ms.Length);

        // Verify the final partial chunk contains the correct value
        ms.Position = 0;
        using var reader = new BinaryReader(ms);
        for (int i = 0; i < samples.Length; i++)
        {
            Assert.Equal(samples[i], reader.ReadInt16());
        }
    }

    [Fact]
    public void WriteChunked_LittleEndianEncoding()
    {
        // 256 decimal = 0x0100 => little-endian bytes: [0x00, 0x01]
        short[] samples = [256];
        using var ms = new MemoryStream();

        StreamingWriter.WriteChunked(ms, samples.AsSpan());

        byte[] bytes = ms.ToArray();
        Assert.Equal(2, bytes.Length);
        Assert.Equal(0x00, bytes[0]);
        Assert.Equal(0x01, bytes[1]);
    }

    [Fact]
    public void WriteChunked_LargeSampleArray_100K_Handled()
    {
        const int count = 100_000;
        short[] samples = new short[count];
        for (int i = 0; i < count; i++)
            samples[i] = (short)(i % 30000 - 15000);

        using var ms = new MemoryStream();

        StreamingWriter.WriteChunked(ms, samples.AsSpan());

        Assert.Equal(count * 2, (int)ms.Length);

        // Spot-check first, middle, and last sample
        ms.Position = 0;
        using var reader = new BinaryReader(ms);

        Assert.Equal(samples[0], reader.ReadInt16());

        // Seek to middle sample
        ms.Position = (count / 2) * 2;
        Assert.Equal(samples[count / 2], reader.ReadInt16());

        // Seek to last sample
        ms.Position = (count - 1) * 2;
        Assert.Equal(samples[count - 1], reader.ReadInt16());
    }

    // ================================================================
    // WriteImmediate
    // ================================================================

    [Fact]
    public void WriteImmediate_SingleWrite_CorrectBytes()
    {
        short[] samples = [short.MinValue, 0, short.MaxValue, 1234, -5678];
        using var ms = new MemoryStream();

        StreamingWriter.WriteImmediate(ms, samples.AsSpan());

        Assert.Equal(samples.Length * 2, (int)ms.Length);

        ms.Position = 0;
        using var reader = new BinaryReader(ms);
        for (int i = 0; i < samples.Length; i++)
        {
            Assert.Equal(samples[i], reader.ReadInt16());
        }
    }

    [Fact]
    public void WriteImmediate_EmptySamples_NoBytesWritten()
    {
        using var ms = new MemoryStream();

        StreamingWriter.WriteImmediate(ms, ReadOnlySpan<short>.Empty);

        Assert.Equal(0, (int)ms.Length);
    }

    [Fact]
    public void WriteImmediate_NullStream_ThrowsArgumentNullException()
    {
        short[] samples = [42];

        Assert.Throws<ArgumentNullException>(
            () => StreamingWriter.WriteImmediate(null!, samples.AsSpan()));
    }

    [Fact]
    public void WriteImmediate_ByteOrderCorrect()
    {
        // Verify little-endian encoding for several known values:
        //   256  (0x0100) => [0x00, 0x01]
        //   -1   (0xFFFF) => [0xFF, 0xFF]
        //   1    (0x0001) => [0x01, 0x00]
        short[] samples = [256, -1, 1];
        using var ms = new MemoryStream();

        StreamingWriter.WriteImmediate(ms, samples.AsSpan());

        byte[] bytes = ms.ToArray();
        Assert.Equal(6, bytes.Length);

        // 256 => 0x00, 0x01
        Assert.Equal(0x00, bytes[0]);
        Assert.Equal(0x01, bytes[1]);

        // -1 => 0xFF, 0xFF
        Assert.Equal(0xFF, bytes[2]);
        Assert.Equal(0xFF, bytes[3]);

        // 1 => 0x01, 0x00
        Assert.Equal(0x01, bytes[4]);
        Assert.Equal(0x00, bytes[5]);
    }
}
