using PiperPlus.Core.Inference;

namespace PiperPlus.Cli;

internal static partial class Program
{
    internal static string? TimingPathForUtterance(string? path, int index)
    {
        if (string.IsNullOrEmpty(path) || path == "-")
        {
            return path;
        }

        string extension = Path.GetExtension(path);
        return path[..^extension.Length] + $"_{index:D3}" + extension;
    }

    internal static void WriteTimingOutput(string? path, string format, List<TimingWriter.PhonemeTimingEntry> entries, int sampleRate)
    {
        if (string.IsNullOrEmpty(path))
        {
            return;
        }

        using Stream output = path == "-" ? Console.OpenStandardOutput() : File.Create(path);
        switch (format.ToLowerInvariant())
        {
            case "json": TimingWriter.WriteJson(output, entries, sampleRate); break;
            case "tsv": TimingWriter.WriteTsv(output, entries); break;
            case "srt": TimingWriter.WriteSrt(output, entries); break;
            default: throw new ArgumentException($"Unknown timing format: {format}");
        }
    }
}
