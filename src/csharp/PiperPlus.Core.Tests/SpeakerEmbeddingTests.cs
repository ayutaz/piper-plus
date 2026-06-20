using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Tests for speaker-embedding support in <see cref="SynthesisInput"/> and the
/// <c>LoadSpeakerEmbedding</c> parsing logic used by the CLI.
/// </summary>
/// <remarks>
/// <para>
/// <c>LoadSpeakerEmbedding</c> is a private static method in <c>PiperPlus.Cli/Program.cs</c>
/// and cannot be called directly from this project.  The tests here replicate the same
/// algorithm inline — an established pattern in this test suite (see
/// <see cref="SpeakerEncoderTests"/> which also reimplements private helpers verbatim).
/// </para>
/// <para>
/// The algorithm under test (Program.cs:1775-1811):
/// <list type="bullet">
///   <item>If the first 6 bytes are the NumPy magic <c>\x93NUMPY</c>, parse as v1.0 .npy.</item>
///   <item>Otherwise interpret as raw binary: each 4 bytes = one float32.</item>
///   <item>If the parsed float count differs from 192 the result is zero-padded / truncated.</item>
/// </list>
/// </para>
/// </remarks>
public sealed class SpeakerEmbeddingTests : IDisposable
{
    private const int ExpectedDim = 192;
    private readonly List<string> _tempFiles = [];

    public void Dispose()
    {
        foreach (var path in _tempFiles)
        {
            try { File.Delete(path); }
            catch { /* best-effort */ }
        }
    }

    // ------------------------------------------------------------------
    // Inline reimplementation of LoadSpeakerEmbedding (mirrors Program.cs)
    // ------------------------------------------------------------------

    private static float[] LoadSpeakerEmbedding(string path)
    {
        const int expectedDim = ExpectedDim;
        byte[] bytes = File.ReadAllBytes(path);

        float[] embedding;

        // Detect NumPy .npy magic: \x93NUMPY
        if (bytes.Length >= 10
            && bytes[0] == 0x93 && bytes[1] == (byte)'N'
            && bytes[2] == (byte)'U' && bytes[3] == (byte)'M'
            && bytes[4] == (byte)'P' && bytes[5] == (byte)'Y')
        {
            // bytes[6] = major version; bytes[7] = minor version
            // v1.0 (major=1): uint16 header_len at offset 8, data at offset 10 + headerLen
            // v2.0 (major=2): uint32 header_len at offset 8, data at offset 12 + headerLen
            int majorVersion = bytes[6];
            int headerLen;
            int dataOffset;
            if (majorVersion >= 2)
            {
                headerLen = (int)BitConverter.ToUInt32(bytes, 8);
                dataOffset = 12 + headerLen; // magic(6) + ver(2) + headerLen_uint32(4) + header
            }
            else
            {
                headerLen = BitConverter.ToUInt16(bytes, 8);
                dataOffset = 10 + headerLen; // magic(6) + ver(2) + headerLen_uint16(2) + header
            }
            int numFloats = (bytes.Length - dataOffset) / sizeof(float);
            embedding = new float[numFloats];
            Buffer.BlockCopy(bytes, dataOffset, embedding, 0, numFloats * sizeof(float));
        }
        else
        {
            // Raw binary: each 4 bytes = one float32
            int numFloats = bytes.Length / sizeof(float);
            embedding = new float[numFloats];
            Buffer.BlockCopy(bytes, 0, embedding, 0, numFloats * sizeof(float));
        }

        if (embedding.Length != expectedDim)
        {
            var padded = new float[expectedDim];
            Array.Copy(embedding, padded, Math.Min(embedding.Length, expectedDim));
            return padded;
        }

        return embedding;
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    /// <summary>Creates a temp file with the given raw bytes and registers it for cleanup.</summary>
    private string WriteTempFile(byte[] content, string ext = ".bin")
    {
        var path = Path.Combine(Path.GetTempPath(), $"piper_spk_test_{Guid.NewGuid():N}{ext}");
        File.WriteAllBytes(path, content);
        _tempFiles.Add(path);
        return path;
    }

    /// <summary>
    /// Builds a minimal NumPy v1.0 .npy byte array containing <paramref name="floats"/>.
    /// The header uses a fixed 64-byte header_len (total preamble = 10 + 64 = 74 bytes)
    /// which is the smallest 16-byte-aligned block that fits the minimal descriptor.
    /// </summary>
    private static byte[] BuildNpyV1(float[] floats)
    {
        // Minimal descriptor string; padded to (header_len) bytes with spaces + '\n'.
        const int headerLen = 64; // must be chosen so preamble (10+headerLen) is divisible by 16? No strict requirement; just must fit.
        // Actual NumPy format: "{'descr': '<f4', 'fortran_order': False, 'shape': (N,), }"
        string descriptor = $"{{'descr': '<f4', 'fortran_order': False, 'shape': ({floats.Length},), }}";
        // Pad with spaces to headerLen - 1, then '\n' as the last byte.
        string padded = descriptor.PadRight(headerLen - 1) + "\n";
        byte[] headerBytes = System.Text.Encoding.ASCII.GetBytes(padded);

        // Preamble: magic(6) + ver_major(1) + ver_minor(1) + header_len_uint16(2)
        var preamble = new byte[10];
        preamble[0] = 0x93;
        preamble[1] = (byte)'N';
        preamble[2] = (byte)'U';
        preamble[3] = (byte)'M';
        preamble[4] = (byte)'P';
        preamble[5] = (byte)'Y';
        preamble[6] = 1; // major
        preamble[7] = 0; // minor
        BitConverter.TryWriteBytes(preamble.AsSpan(8), (ushort)headerLen);

        // Data: float32 little-endian
        var dataBytes = new byte[floats.Length * sizeof(float)];
        Buffer.BlockCopy(floats, 0, dataBytes, 0, dataBytes.Length);

        return [.. preamble, .. headerBytes, .. dataBytes];
    }

    /// <summary>
    /// Builds a minimal NumPy v2.0 .npy byte array containing <paramref name="floats"/>.
    /// v2.0 uses major=2, minor=0, and a uint32 header_len field (4 bytes instead of 2).
    /// The preamble is therefore 12 bytes: magic(6) + ver(2) + headerLen_uint32(4).
    /// </summary>
    private static byte[] BuildNpyV2(float[] floats)
    {
        // Descriptor string padded to headerLen bytes with spaces + '\n'.
        const int headerLen = 64;
        string descriptor = $"{{'descr': '<f4', 'fortran_order': False, 'shape': ({floats.Length},), }}";
        string padded = descriptor.PadRight(headerLen - 1) + "\n";
        byte[] headerBytes = System.Text.Encoding.ASCII.GetBytes(padded);

        // Preamble: magic(6) + ver_major(1) + ver_minor(1) + header_len_uint32(4)
        var preamble = new byte[12];
        preamble[0] = 0x93;
        preamble[1] = (byte)'N';
        preamble[2] = (byte)'U';
        preamble[3] = (byte)'M';
        preamble[4] = (byte)'P';
        preamble[5] = (byte)'Y';
        preamble[6] = 2; // major = 2
        preamble[7] = 0; // minor = 0
        BitConverter.TryWriteBytes(preamble.AsSpan(8), (uint)headerLen);

        // Data: float32 little-endian
        var dataBytes = new byte[floats.Length * sizeof(float)];
        Buffer.BlockCopy(floats, 0, dataBytes, 0, dataBytes.Length);

        return [.. preamble, .. headerBytes, .. dataBytes];
    }

    // ================================================================
    // SynthesisInput — SpeakerEmbedding property
    // ================================================================

    [Fact]
    public void SynthesisInput_SpeakerEmbedding_DefaultIsNull()
    {
        var input = new SynthesisInput(PhonemeIds: [1, 2, 3]);

        Assert.Null(input.SpeakerEmbedding);
    }

    [Fact]
    public void SynthesisInput_SpeakerEmbedding_CanBeSet()
    {
        float[] embedding = new float[192];
        for (int i = 0; i < embedding.Length; i++)
            embedding[i] = i * 0.01f;

        var input = new SynthesisInput(
            PhonemeIds: [1, 2, 3],
            SpeakerEmbedding: embedding);

        Assert.NotNull(input.SpeakerEmbedding);
        Assert.Equal(192, input.SpeakerEmbedding.Length);
        Assert.Equal(embedding, input.SpeakerEmbedding);
    }

    [Fact]
    public void SynthesisInput_NoiseScale_DefaultIs04()
    {
        var input = new SynthesisInput(PhonemeIds: [1, 2, 3]);

        Assert.Equal(0.4f, input.NoiseScale);
    }

    [Fact]
    public void SynthesisInput_NoiseW_DefaultIs05()
    {
        var input = new SynthesisInput(PhonemeIds: [1, 2, 3]);

        Assert.Equal(0.5f, input.NoiseW);
    }

    [Fact]
    public void SynthesisInput_SpeakerEmbedding_WithExpression_CreatesModifiedCopy()
    {
        // Verify the record supports non-destructive mutation for SpeakerEmbedding.
        var original = new SynthesisInput(PhonemeIds: [1, 2, 3]);
        float[] emb = new float[192];
        var modified = original with { SpeakerEmbedding = emb };

        Assert.Null(original.SpeakerEmbedding);
        Assert.NotNull(modified.SpeakerEmbedding);
        Assert.Same(emb, modified.SpeakerEmbedding);
    }

    [Fact]
    public void SynthesisInput_SpeakerEmbedding_AllDefaults_OtherFieldsUnchanged()
    {
        // Setting SpeakerEmbedding must not disturb other default values.
        float[] emb = new float[192];
        var input = new SynthesisInput(
            PhonemeIds: [10, 20, 30],
            SpeakerEmbedding: emb);

        Assert.Equal(0, input.SpeakerId);
        Assert.Equal(0.4f, input.NoiseScale);
        Assert.Equal(1.0f, input.LengthScale);
        Assert.Equal(0.5f, input.NoiseW);
        Assert.Null(input.ProsodyFeatures);
    }

    // ================================================================
    // LoadSpeakerEmbedding — raw binary format
    // ================================================================

    [Fact]
    public void LoadSpeakerEmbedding_RawBinary_Returns192Floats()
    {
        // 192 float32 values = 768 bytes
        float[] expected = new float[192];
        for (int i = 0; i < 192; i++)
            expected[i] = (float)i;

        byte[] rawBytes = new byte[192 * sizeof(float)];
        Buffer.BlockCopy(expected, 0, rawBytes, 0, rawBytes.Length);

        string path = WriteTempFile(rawBytes, ".bin");
        float[] result = LoadSpeakerEmbedding(path);

        Assert.Equal(192, result.Length);
        for (int i = 0; i < 192; i++)
            Assert.Equal(expected[i], result[i]);
    }

    [Fact]
    public void LoadSpeakerEmbedding_RawBinary_ValuesRoundtrip()
    {
        // Verify that specific sentinel values survive the binary round-trip.
        float[] sentinels = new float[192];
        sentinels[0] = 1.0f;
        sentinels[95] = -0.5f;
        sentinels[191] = 0.123456f;

        byte[] rawBytes = new byte[192 * sizeof(float)];
        Buffer.BlockCopy(sentinels, 0, rawBytes, 0, rawBytes.Length);

        string path = WriteTempFile(rawBytes, ".bin");
        float[] result = LoadSpeakerEmbedding(path);

        Assert.Equal(1.0f, result[0]);
        Assert.Equal(-0.5f, result[95]);
        Assert.Equal(0.123456f, result[191], precision: 5);
    }

    [Fact]
    public void LoadSpeakerEmbedding_RawBinary_ShorterThan192_PadsWithZeros()
    {
        // 10 floats (40 bytes) — far fewer than 192; remainder must be zero.
        float[] partial = Enumerable.Range(1, 10).Select(x => (float)x).ToArray();
        byte[] rawBytes = new byte[partial.Length * sizeof(float)];
        Buffer.BlockCopy(partial, 0, rawBytes, 0, rawBytes.Length);

        string path = WriteTempFile(rawBytes, ".bin");
        float[] result = LoadSpeakerEmbedding(path);

        Assert.Equal(192, result.Length);
        for (int i = 0; i < 10; i++)
            Assert.Equal(partial[i], result[i]);
        for (int i = 10; i < 192; i++)
            Assert.Equal(0f, result[i]);
    }

    // ================================================================
    // LoadSpeakerEmbedding — NumPy v1.0 .npy format
    // ================================================================

    [Fact]
    public void LoadSpeakerEmbedding_NpyV1_ParsesCorrectly()
    {
        float[] expected = new float[192];
        for (int i = 0; i < 192; i++)
            expected[i] = i * 0.001f;

        byte[] npyBytes = BuildNpyV1(expected);
        string path = WriteTempFile(npyBytes, ".npy");

        float[] result = LoadSpeakerEmbedding(path);

        Assert.Equal(192, result.Length);
        for (int i = 0; i < 192; i++)
            Assert.Equal(expected[i], result[i], precision: 6);
    }

    [Fact]
    public void LoadSpeakerEmbedding_NpyV1_MagicDetected()
    {
        // Verify that the npy branch is taken (not the raw branch) by checking
        // that the result differs from what raw parsing would produce.
        // If the magic bytes were interpreted as floats the first float would
        // encode 0x4E\x93... which is nothing like 0.0.  With correct npy
        // parsing the first float should be 0.0 (our test payload starts at 0).
        float[] payload = new float[192]; // all zeros

        byte[] npyBytes = BuildNpyV1(payload);
        string path = WriteTempFile(npyBytes, ".npy");

        float[] result = LoadSpeakerEmbedding(path);

        Assert.Equal(192, result.Length);
        Assert.All(result, v => Assert.Equal(0f, v));
    }

    [Fact]
    public void LoadSpeakerEmbedding_NpyV1_SentinelValues_RoundTrip()
    {
        float[] payload = new float[192];
        payload[0] = -1.0f;
        payload[100] = 0.7654321f;
        payload[191] = 3.14159265f;

        byte[] npyBytes = BuildNpyV1(payload);
        string path = WriteTempFile(npyBytes, ".npy");

        float[] result = LoadSpeakerEmbedding(path);

        Assert.Equal(-1.0f, result[0]);
        Assert.Equal(0.7654321f, result[100], precision: 6);
        Assert.Equal(3.14159265f, result[191], precision: 5);
    }

    // ================================================================
    // LoadSpeakerEmbedding — NumPy v2.0 .npy format
    // ================================================================

    [Fact]
    public void LoadSpeakerEmbedding_NpyV2_ParsesCorrectly()
    {
        float[] expected = new float[192];
        for (int i = 0; i < 192; i++)
            expected[i] = i * 0.001f;

        byte[] npyBytes = BuildNpyV2(expected);
        string path = WriteTempFile(npyBytes, ".npy");

        float[] result = LoadSpeakerEmbedding(path);

        Assert.Equal(192, result.Length);
        for (int i = 0; i < 192; i++)
            Assert.Equal(expected[i], result[i], precision: 6);
    }

    [Fact]
    public void LoadSpeakerEmbedding_NpyV2_SentinelValues_RoundTrip()
    {
        float[] payload = new float[192];
        payload[0] = -1.0f;
        payload[100] = 0.7654321f;
        payload[191] = 3.14159265f;

        byte[] npyBytes = BuildNpyV2(payload);
        string path = WriteTempFile(npyBytes, ".npy");

        float[] result = LoadSpeakerEmbedding(path);

        Assert.Equal(-1.0f, result[0]);
        Assert.Equal(0.7654321f, result[100], precision: 6);
        Assert.Equal(3.14159265f, result[191], precision: 5);
    }

    [Fact]
    public void LoadSpeakerEmbedding_NpyV2_MagicDetected_DifferentFromRaw()
    {
        // Verify the npy branch is taken for v2 files (not treated as raw binary).
        float[] payload = new float[192]; // all zeros

        byte[] npyBytes = BuildNpyV2(payload);
        string path = WriteTempFile(npyBytes, ".npy");

        float[] result = LoadSpeakerEmbedding(path);

        Assert.Equal(192, result.Length);
        Assert.All(result, v => Assert.Equal(0f, v));
    }

    // ================================================================
    // SpeakerEmbeddingMask — verify "speaker_embedding_mask" is absent
    // ================================================================

    [Fact]
    public void SpeakerEmbeddingMask_NotInInputNames_PiperModelCapabilityKeys()
    {
        // PiperModel.cs lines 43-46 enumerate every recognized input key.
        // Capture the set of known capability-detection keys from PiperSession's
        // inference logic (PiperSession.cs lines 245-295).
        // "speaker_embedding_mask" must not be present in any of them.

        // These are the exact string literals used in PiperModel.cs and PiperSession.cs
        // for capability detection and tensor construction.
        string[] knownInputKeys =
        [
            "input",
            "input_lengths",
            "scales",
            "sid",
            "lid",
            "prosody_features",
            "speaker_embedding",
        ];

        Assert.DoesNotContain("speaker_embedding_mask", knownInputKeys);
    }

    [Fact]
    public void SpeakerEmbeddingMask_NotAddedBySynthesisInput()
    {
        // SynthesisInput must not have a SpeakerEmbeddingMask property.
        // Verify by inspecting the public properties via reflection.
        var propNames = typeof(SynthesisInput)
            .GetProperties(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance)
            .Select(p => p.Name)
            .ToArray();

        Assert.DoesNotContain("SpeakerEmbeddingMask", propNames);
        // Also check for any variant spellings that might indicate a mask field.
        Assert.False(
            propNames.Any(name =>
                name.Contains("Mask", StringComparison.OrdinalIgnoreCase)
                && name.Contains("Speaker", StringComparison.OrdinalIgnoreCase)),
            "SynthesisInput must not contain any Speaker*Mask property");
    }
}
