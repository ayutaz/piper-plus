using PiperPlus.Cli;
using PiperPlus.Core.Inference;
using Xunit;

namespace PiperPlus.Cli.Tests;

public sealed class TimingOutputTests
{
    [Theory]
    [InlineData("json", "\"phoneme\"")]
    [InlineData("tsv", "phoneme")]
    [InlineData("srt", "-->")]
    public void WritesRequestedTimingArtifact(string format, string expected)
    {
        string path = Path.GetTempFileName();
        try
        {
            var entries = new List<TimingWriter.PhonemeTimingEntry>
            {
                new("a", 0, 100, 100),
            };
            Program.WriteTimingOutput(path, format, entries, 22050);
            string content = File.ReadAllText(path);
            Assert.Contains(expected, content, StringComparison.Ordinal);
            Assert.DoesNotContain("\r", content, StringComparison.Ordinal);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public void StdinRecordsHaveDistinctOutputNames()
    {
        Assert.Equal("timing_001.json", Program.TimingPathForUtterance("timing.json", 1));
        Assert.Equal("timing_002.json", Program.TimingPathForUtterance("timing.json", 2));
    }
}
