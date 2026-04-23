using System.Text;

namespace PiperPlus.Core.IO;

/// <summary>
/// Minimal reader for numpy <c>.npy</c> files (Phase 2 P2-T05).
/// </summary>
/// <remarks>
/// Supports the v1.0 / v2.0 file format with dtype <c>&lt;f4</c> (little-endian
/// float32). Accepts 1-D <c>(dim,)</c> or 2-D <c>(1, dim)</c> shapes and
/// returns the underlying float data as a flat array.
/// Any unsupported dtype, Fortran-order, or multi-row shape results in an
/// <see cref="InvalidDataException"/>.
/// </remarks>
public static class NumpyLoader
{
    private static readonly byte[] Magic =
    [
        0x93,
        (byte)'N', (byte)'U', (byte)'M', (byte)'P', (byte)'Y'
    ];

    /// <summary>
    /// Load a 1-D or (1, dim) float32 array from a <c>.npy</c> file.
    /// </summary>
    /// <param name="path">Path to the <c>.npy</c> file.</param>
    /// <returns>The flattened float data.</returns>
    public static float[] LoadFloat32Array(string path)
    {
        ArgumentNullException.ThrowIfNull(path);
        var bytes = File.ReadAllBytes(path);
        if (bytes.Length < 10
            || bytes[0] != Magic[0] || bytes[1] != Magic[1]
            || bytes[2] != Magic[2] || bytes[3] != Magic[3]
            || bytes[4] != Magic[4] || bytes[5] != Magic[5])
        {
            throw new InvalidDataException(
                $".npy magic header invalid: {path}");
        }

        byte major = bytes[6];
        int headerLen;
        int dataOffset;
        switch (major)
        {
            case 1:
                headerLen = bytes[8] | (bytes[9] << 8);
                dataOffset = 10 + headerLen;
                break;
            case 2:
                headerLen = bytes[8]
                    | (bytes[9] << 8)
                    | (bytes[10] << 16)
                    | (bytes[11] << 24);
                dataOffset = 12 + headerLen;
                break;
            default:
                throw new InvalidDataException(
                    $".npy unsupported version: {major}");
        }

        if (bytes.Length < dataOffset)
        {
            throw new InvalidDataException($".npy truncated header: {path}");
        }

        int headerStart = major == 1 ? 10 : 12;
        string header = Encoding.UTF8.GetString(bytes, headerStart, headerLen);
        if (!header.Contains("'descr': '<f4'")
            && !header.Contains("\"descr\": \"<f4\""))
        {
            throw new InvalidDataException(
                $".npy dtype must be '<f4' (little-endian float32); header: {header}");
        }

        int totalBytes = bytes.Length - dataOffset;
        if (totalBytes % 4 != 0)
        {
            throw new InvalidDataException(
                $".npy data size {totalBytes} not a multiple of 4 bytes");
        }

        int count = totalBytes / 4;
        var result = new float[count];
        Buffer.BlockCopy(bytes, dataOffset, result, 0, totalBytes);
        return result;
    }
}
