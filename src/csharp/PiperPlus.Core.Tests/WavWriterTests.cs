using System.Text;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

public class WavWriterTests
{
    private const int DefaultSampleRate = 22050;
    private const int HeaderSize = 44;

    /// <summary>
    /// Helper: writes samples at the given sample rate and returns the MemoryStream
    /// rewound to position 0 for reading.
    /// </summary>
    private static MemoryStream WriteToMemoryStream(short[] samples, int sampleRate = DefaultSampleRate)
    {
        var ms = new MemoryStream();
        WavWriter.Write(ms, samples.AsSpan(), sampleRate);
        ms.Position = 0;
        return ms;
    }

    // ----------------------------------------------------------------
    // 1. EmptyAudio_WritesValidHeader
    // ----------------------------------------------------------------

    [Fact]
    public void EmptyAudio_WritesValidHeader()
    {
        using var ms = WriteToMemoryStream([]);

        Assert.Equal(HeaderSize, ms.Length);
    }

    // ----------------------------------------------------------------
    // 2. Header_RiffChunk
    // ----------------------------------------------------------------

    [Fact]
    public void Header_RiffChunk()
    {
        short[] samples = [100, -200, 300];
        using var ms = WriteToMemoryStream(samples);
        using var reader = new BinaryReader(ms, Encoding.ASCII, leaveOpen: true);

        // ChunkID = "RIFF"
        var chunkId = Encoding.ASCII.GetString(reader.ReadBytes(4));
        Assert.Equal("RIFF", chunkId);

        // ChunkSize = 36 + NumSamples * 2
        int expectedChunkSize = 36 + samples.Length * 2;
        Assert.Equal(expectedChunkSize, reader.ReadInt32());

        // Format = "WAVE"
        var format = Encoding.ASCII.GetString(reader.ReadBytes(4));
        Assert.Equal("WAVE", format);
    }

    // ----------------------------------------------------------------
    // 3. Header_FmtChunk
    // ----------------------------------------------------------------

    [Fact]
    public void Header_FmtChunk()
    {
        short[] samples = [1, 2, 3];
        using var ms = WriteToMemoryStream(samples);
        using var reader = new BinaryReader(ms, Encoding.ASCII, leaveOpen: true);

        // Skip RIFF header (12 bytes)
        reader.ReadBytes(12);

        // Subchunk1ID = "fmt "
        var subchunk1Id = Encoding.ASCII.GetString(reader.ReadBytes(4));
        Assert.Equal("fmt ", subchunk1Id);

        // Subchunk1Size = 16
        Assert.Equal(16, reader.ReadInt32());

        // AudioFormat = 1 (PCM)
        Assert.Equal((short)1, reader.ReadInt16());

        // NumChannels = 1 (mono)
        Assert.Equal((short)1, reader.ReadInt16());

        // SampleRate = 22050
        Assert.Equal(DefaultSampleRate, reader.ReadInt32());

        // ByteRate = SampleRate * NumChannels * BitsPerSample/8 = 22050 * 1 * 2 = 44100
        Assert.Equal(DefaultSampleRate * 2, reader.ReadInt32());

        // BlockAlign = NumChannels * BitsPerSample/8 = 2
        Assert.Equal((short)2, reader.ReadInt16());

        // BitsPerSample = 16
        Assert.Equal((short)16, reader.ReadInt16());
    }

    // ----------------------------------------------------------------
    // 4. Header_DataChunk
    // ----------------------------------------------------------------

    [Fact]
    public void Header_DataChunk()
    {
        short[] samples = [10, 20, 30, 40, 50];
        using var ms = WriteToMemoryStream(samples);
        using var reader = new BinaryReader(ms, Encoding.ASCII, leaveOpen: true);

        // Skip to data sub-chunk (offset 36)
        reader.ReadBytes(36);

        // Subchunk2ID = "data"
        var subchunk2Id = Encoding.ASCII.GetString(reader.ReadBytes(4));
        Assert.Equal("data", subchunk2Id);

        // Subchunk2Size = NumSamples * 2
        int expectedDataSize = samples.Length * 2;
        Assert.Equal(expectedDataSize, reader.ReadInt32());
    }

    // ----------------------------------------------------------------
    // 5. SampleData_CorrectlyWritten
    // ----------------------------------------------------------------

    [Fact]
    public void SampleData_CorrectlyWritten()
    {
        short[] samples = [short.MinValue, -1, 0, 1, short.MaxValue];
        using var ms = WriteToMemoryStream(samples);
        using var reader = new BinaryReader(ms, Encoding.ASCII, leaveOpen: true);

        // Skip header
        reader.ReadBytes(HeaderSize);

        // Read back each sample and compare
        for (int i = 0; i < samples.Length; i++)
        {
            short actual = reader.ReadInt16();
            Assert.Equal(samples[i], actual);
        }
    }

    // ----------------------------------------------------------------
    // 6. DifferentSampleRate_UpdatesHeader
    // ----------------------------------------------------------------

    [Fact]
    public void DifferentSampleRate_UpdatesHeader()
    {
        const int sampleRate = 44100;
        short[] samples = [100, 200];
        using var ms = WriteToMemoryStream(samples, sampleRate);
        using var reader = new BinaryReader(ms, Encoding.ASCII, leaveOpen: true);

        // Skip to SampleRate field (offset 24)
        reader.ReadBytes(24);

        // SampleRate = 44100
        Assert.Equal(sampleRate, reader.ReadInt32());

        // ByteRate = 44100 * 1 * 2 = 88200
        Assert.Equal(sampleRate * 2, reader.ReadInt32());
    }

    // ----------------------------------------------------------------
    // 7. TotalFileSize
    // ----------------------------------------------------------------

    [Fact]
    public void TotalFileSize()
    {
        short[] samples = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
        using var ms = WriteToMemoryStream(samples);

        long expectedSize = HeaderSize + samples.Length * 2;
        Assert.Equal(expectedSize, ms.Length);
    }

    // ----------------------------------------------------------------
    // 8. WriteToFile_CreatesValidWav
    // ----------------------------------------------------------------

    [Fact]
    public void WriteToFile_CreatesValidWav()
    {
        short[] samples = [1000, -2000, 3000];
        var tempPath = Path.Combine(Path.GetTempPath(), $"piper_test_{Guid.NewGuid():N}.wav");

        try
        {
            WavWriter.Write(tempPath, samples.AsSpan(), DefaultSampleRate);

            Assert.True(File.Exists(tempPath));

            byte[] bytes = File.ReadAllBytes(tempPath);
            long expectedSize = HeaderSize + samples.Length * 2;
            Assert.Equal(expectedSize, bytes.Length);

            // Verify via MemoryStream + BinaryReader
            using var ms = new MemoryStream(bytes);
            using var reader = new BinaryReader(ms, Encoding.ASCII, leaveOpen: true);

            // RIFF header
            Assert.Equal("RIFF", Encoding.ASCII.GetString(reader.ReadBytes(4)));
            Assert.Equal(36 + samples.Length * 2, reader.ReadInt32());
            Assert.Equal("WAVE", Encoding.ASCII.GetString(reader.ReadBytes(4)));

            // Skip to data samples (offset 44): fmt sub-chunk (24) + data header (8) = 32
            reader.ReadBytes(32);
            for (int i = 0; i < samples.Length; i++)
            {
                Assert.Equal(samples[i], reader.ReadInt16());
            }
        }
        finally
        {
            if (File.Exists(tempPath))
            {
                File.Delete(tempPath);
            }
        }
    }
}
