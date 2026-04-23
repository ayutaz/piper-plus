using PiperPlus.Core.Inference;
using PiperPlus.Core.IO;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Phase 2 (P2-T05) tests for style_vector handling.
/// </summary>
public class StyleVectorTests
{
    // ---------------------------------------------------------------------
    // SynthesisInput default values
    // ---------------------------------------------------------------------

    [Fact]
    public void SynthesisInput_DefaultStyleVector_IsNull()
    {
        var input = new SynthesisInput(PhonemeIds: [1, 2, 3]);
        Assert.Null(input.StyleVector);
    }

    [Fact]
    public void SynthesisInput_CanSetStyleVector()
    {
        var vec = new float[256];
        var input = new SynthesisInput(
            PhonemeIds: [1, 2, 3],
            StyleVector: vec);
        Assert.NotNull(input.StyleVector);
        Assert.Equal(256, input.StyleVector.Length);
    }

    [Fact]
    public void SynthesisInput_RecordEquality_StyleVectorDifference()
    {
        var a = new SynthesisInput(PhonemeIds: [1, 2], StyleVector: [1.0f, 2.0f]);
        var b = new SynthesisInput(PhonemeIds: [1, 2], StyleVector: [3.0f, 4.0f]);
        Assert.NotEqual(a, b);
    }

    // ---------------------------------------------------------------------
    // NumpyLoader tests
    // ---------------------------------------------------------------------

    [Fact]
    public void NumpyLoader_ReadsFloat32_V1_1D()
    {
        // Construct a minimal .npy v1.0 file in-memory (3 floats).
        string tempPath = Path.GetTempFileName();
        try
        {
            using (var fs = new FileStream(tempPath, FileMode.Create))
            {
                // Magic + version 1.0
                fs.Write([0x93, (byte)'N', (byte)'U', (byte)'M', (byte)'P', (byte)'Y']);
                fs.Write([0x01, 0x00]);
                string header = "{'descr': '<f4', 'fortran_order': False, 'shape': (3,), }";
                // Pad header to align to 16 bytes (typical numpy behavior)
                int totalHdr = 10 + header.Length + 1; // +1 for newline
                int padding = (16 - (totalHdr % 16)) % 16;
                string paddedHeader = header + new string(' ', padding) + "\n";
                byte[] headerBytes = System.Text.Encoding.UTF8.GetBytes(paddedHeader);
                ushort hdrLen = (ushort)headerBytes.Length;
                fs.Write(BitConverter.GetBytes(hdrLen));
                fs.Write(headerBytes);
                // 3 float32 values: 1.0, 2.0, 3.0
                fs.Write(BitConverter.GetBytes(1.0f));
                fs.Write(BitConverter.GetBytes(2.0f));
                fs.Write(BitConverter.GetBytes(3.0f));
            }

            float[] loaded = NumpyLoader.LoadFloat32Array(tempPath);
            Assert.Equal(3, loaded.Length);
            Assert.Equal(1.0f, loaded[0]);
            Assert.Equal(2.0f, loaded[1]);
            Assert.Equal(3.0f, loaded[2]);
        }
        finally
        {
            File.Delete(tempPath);
        }
    }

    [Fact]
    public void NumpyLoader_InvalidMagic_Throws()
    {
        string tempPath = Path.GetTempFileName();
        try
        {
            File.WriteAllBytes(tempPath, [0x00, 0x01, 0x02, 0x03, 0x04, 0x05]);
            Assert.Throws<InvalidDataException>(
                () => NumpyLoader.LoadFloat32Array(tempPath));
        }
        finally
        {
            File.Delete(tempPath);
        }
    }

    [Fact]
    public void NumpyLoader_UnsupportedDtype_Throws()
    {
        string tempPath = Path.GetTempFileName();
        try
        {
            using var fs = new FileStream(tempPath, FileMode.Create);
            fs.Write([0x93, (byte)'N', (byte)'U', (byte)'M', (byte)'P', (byte)'Y']);
            fs.Write([0x01, 0x00]);
            // dtype '<f8' is float64, not supported
            string header = "{'descr': '<f8', 'fortran_order': False, 'shape': (1,), }  \n";
            byte[] headerBytes = System.Text.Encoding.UTF8.GetBytes(header);
            ushort hdrLen = (ushort)headerBytes.Length;
            fs.Write(BitConverter.GetBytes(hdrLen));
            fs.Write(headerBytes);
            fs.Write(BitConverter.GetBytes(1.0));
            fs.Close();

            Assert.Throws<InvalidDataException>(
                () => NumpyLoader.LoadFloat32Array(tempPath));
        }
        finally
        {
            File.Delete(tempPath);
        }
    }
}
