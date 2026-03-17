using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Writes 44-byte PCM WAV headers + int16 sample data.
/// Mono, 16-bit, little-endian only. No external dependencies.
/// </summary>
public static class WavWriter
{
    private const short AudioFormatPcm = 1;
    private const short NumChannels = 1; // mono
    private const short BitsPerSample = 16;
    private const int BytesPerSample = BitsPerSample / 8; // 2
    private const int HeaderSize = 44;

    /// <summary>
    /// Writes a complete WAV file (header + PCM data) to the given stream.
    /// </summary>
    /// <param name="stream">Destination stream (must be writable).</param>
    /// <param name="samples">16-bit PCM samples in little-endian order.</param>
    /// <param name="sampleRate">Sample rate in Hz (e.g. 22050 from config.json).</param>
    public static void Write(Stream stream, ReadOnlySpan<short> samples, int sampleRate)
    {
        if (stream is null)
            throw new ArgumentNullException(nameof(stream));
        if (sampleRate <= 0)
            throw new ArgumentOutOfRangeException(nameof(sampleRate), "Sample rate must be positive.");

        using var writer = new BinaryWriter(stream, Encoding.ASCII, leaveOpen: true);

        long dataSize64 = (long)samples.Length * BytesPerSample;
        if (dataSize64 > int.MaxValue)
            throw new ArgumentException(
                $"Audio data ({samples.Length} samples) exceeds WAV format limit.");
        int dataSize = (int)dataSize64;
        int byteRate = sampleRate * NumChannels * BytesPerSample;
        short blockAlign = (short)(NumChannels * BytesPerSample);

        // --- RIFF header ---
        writer.Write("RIFF"u8);                          // ChunkID        (4)
        writer.Write((int)(HeaderSize - 8 + dataSize));   // ChunkSize      (4): 36 + dataSize
        writer.Write("WAVE"u8);                           // Format         (4)

        // --- fmt sub-chunk ---
        writer.Write("fmt "u8);                           // Subchunk1ID    (4)
        writer.Write(16);                                 // Subchunk1Size  (4)
        writer.Write(AudioFormatPcm);                     // AudioFormat    (2)
        writer.Write(NumChannels);                        // NumChannels    (2)
        writer.Write(sampleRate);                         // SampleRate     (4)
        writer.Write(byteRate);                           // ByteRate       (4)
        writer.Write(blockAlign);                         // BlockAlign     (2)
        writer.Write(BitsPerSample);                      // BitsPerSample  (2)

        // --- data sub-chunk ---
        writer.Write("data"u8);                           // Subchunk2ID    (4)
        writer.Write(dataSize);                           // Subchunk2Size  (4)

        // --- PCM samples (bulk write) ---
        var bytes = MemoryMarshal.AsBytes(samples);
        writer.Write(bytes);
    }

    /// <summary>
    /// Writes a complete WAV file (header + PCM data) to the given file path.
    /// Creates or overwrites the file.
    /// </summary>
    /// <param name="filePath">Destination file path.</param>
    /// <param name="samples">16-bit PCM samples in little-endian order.</param>
    /// <param name="sampleRate">Sample rate in Hz (e.g. 22050 from config.json).</param>
    public static void Write(string filePath, ReadOnlySpan<short> samples, int sampleRate)
    {
        if (string.IsNullOrWhiteSpace(filePath))
            throw new ArgumentException("File path must not be empty.", nameof(filePath));

        using var fs = new FileStream(filePath, FileMode.Create, FileAccess.Write);
        Write(fs, samples, sampleRate);
    }
}
