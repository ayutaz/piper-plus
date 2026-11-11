using System.IO;
using System.Linq;
using System.Text.Json;

namespace PiperPlus.Core.Tests;

/// <summary>
/// The CLI strips control characters before it reads a text, in every way it
/// takes one: <c>--text</c> with <c>--test-mode</c>, <c>--text</c> with a
/// model, and the <c>text</c> of JSONL on standard input.
/// <para>
/// Contract: <c>docs/spec/input-sanitize-contract.toml</c> (runtime
/// <c>csharp</c>). Cases: <c>tests/fixtures/g2p/input_sanitize_cases.json</c>
/// (the Spanish word cases and the pipeline cases). A command-line argument
/// cannot hold a NUL, so the <c>--text</c> tests put DEL (removed by the same
/// rule) where a case has a NUL; JSONL carries the NUL itself.
/// </para>
/// <para>
/// Regression focus: the CLI applied the custom dictionary, the short-text
/// check, the <c>[[ ]]</c> notation and sentence splitting to the raw text.
/// </para>
/// </summary>
public sealed class CliInputSanitizeTests
{
    public sealed record TextCase(string Name, string Clean, string Dirty)
    {
        public override string ToString() => Name;
    }

    private static string RepoFile(params string[] parts) =>
        Path.Join([TextSanitizerContractTests.RepoRoot(), .. parts]);

    private static string ModelPath => RepoFile("test", "models", "multilingual-test-medium.onnx");

    private static List<TextCase> LoadCases()
    {
        string path = RepoFile("tests", "fixtures", "g2p", "input_sanitize_cases.json");
        using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(path));
        var cases = new List<TextCase>();
        foreach (JsonElement e in doc.RootElement.GetProperty("word_cases").EnumerateArray())
        {
            if (e.GetProperty("language").GetString() == "es")
            {
                cases.Add(new TextCase(
                    "es " + e.GetProperty("control").GetString(),
                    e.GetProperty("clean").GetString()!,
                    e.GetProperty("dirty").GetString()!));
            }
        }

        foreach (JsonElement e in doc.RootElement.GetProperty("pipeline_cases").EnumerateArray())
        {
            cases.Add(new TextCase(
                e.GetProperty("name").GetString()!,
                e.GetProperty("clean").GetString()!,
                e.GetProperty("dirty").GetString()!));
        }

        // Twenty removed characters made "hola" too long for the short-text padding.
        cases.Add(new TextCase("short_text", "hola", "ho" + new string('\u0000', 20) + "la"));
        Assert.True(cases.Count > 6);
        return cases;
    }

    public static TheoryData<TextCase> Cases()
    {
        var data = new TheoryData<TextCase>();
        foreach (TextCase c in LoadCases())
        {
            data.Add(c);
        }

        return data;
    }

    private static string AsArgument(string text) => text.Replace('\u0000', '\u007f');

    private static string PhonemeIdLine(int exitCode, string stderr)
    {
        Assert.True(exitCode == 0, stderr);
        string? line = stderr.Split('\n').FirstOrDefault(l => l.Contains("[test-mode] phoneme_ids", StringComparison.Ordinal));
        Assert.True(line is not null, stderr);
        return line!.Trim();
    }

    private static async Task<string> TestModeIdsAsync(string text, params string[] extra)
    {
        (int exitCode, string _, string stderr) = await CliIntegrationTests.RunCliAsync(
            ["--test-mode", "--config", ModelPath + ".json", "--language", "es", "--text", text, .. extra]);
        return PhonemeIdLine(exitCode, stderr);
    }

    [Theory]
    [MemberData(nameof(Cases))]
    [Trait("Category", "CLI")]
    public async Task TestMode_ReadsDirtyLikeClean(TextCase c)
    {
        Assert.Equal(await TestModeIdsAsync(c.Clean), await TestModeIdsAsync(AsArgument(c.Dirty)));
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task TestMode_CustomDictionaryFindsTheWord()
    {
        string dict = Path.Join(Path.GetTempPath(), $"sanitize-dict-{Guid.NewGuid():N}.json");
        await File.WriteAllTextAsync(
            dict,
            """{"version":"2.0","entries":{"hola":{"pronunciation":"pero","priority":9}}}""",
            TestContext.Current.CancellationToken);
        try
        {
            Assert.Equal(
                await TestModeIdsAsync("hola", "--custom-dict", dict),
                await TestModeIdsAsync("ho\u007fla", "--custom-dict", dict));
        }
        finally
        {
            File.Delete(dict);
        }
    }

    private static async Task<long> SynthesizedBytesAsync(string? text, string? jsonl)
    {
        string output = Path.Join(Path.GetTempPath(), $"sanitize-{Guid.NewGuid():N}.wav");
        string[] args = ["--model", ModelPath, "--language", "es", "--noise_w", "0", "--no-warmup", "--output_file", output];
        try
        {
            (int exitCode, string _, string stderr) = jsonl is null
                ? await CliIntegrationTests.RunCliAsync([.. args, "--text", text!])
                : await CliIntegrationTests.RunCliWithInputAsync(jsonl, [.. args, "--json-input"]);
            Assert.True(exitCode == 0, stderr);
            return new FileInfo(output).Length;
        }
        finally
        {
            File.Delete(output);
        }
    }

    [Theory]
    [MemberData(nameof(Cases))]
    [Trait("Category", "CLI")]
    public async Task TextMode_SynthesizesDirtyLikeClean(TextCase c)
    {
        Assert.Equal(
            await SynthesizedBytesAsync(c.Clean, null),
            await SynthesizedBytesAsync(AsArgument(c.Dirty), null));
    }

    [Theory]
    [MemberData(nameof(Cases))]
    [Trait("Category", "CLI")]
    public async Task JsonlText_SynthesizesDirtyLikeClean(TextCase c)
    {
        static string Line(string text) => "{\"text\":\"" + JsonEncodedText.Encode(text) + "\"}\n";
        Assert.Equal(
            await SynthesizedBytesAsync(null, Line(c.Clean)),
            await SynthesizedBytesAsync(null, Line(c.Dirty)));
    }

    // A text of only control characters (the fixture's only_controls case,
    // with DEL for its NUL) is an empty text. Before, it was read as BOS/EOS
    // and synthesized.
    private const string OnlyControls = "\u007f\u0001\u007f\u009f";

    private static async Task<(int ExitCode, string Stderr, bool Wrote)> RunWithTextAsync(string text, params string[] extra)
    {
        string output = Path.Join(Path.GetTempPath(), $"sanitize-{Guid.NewGuid():N}.wav");
        try
        {
            (int exitCode, string _, string stderr) = await CliIntegrationTests.RunCliAsync(
                ["--model", ModelPath, "--language", "es", "--no-warmup", "--output_file", output, .. extra, "--text", text]);
            return (exitCode, stderr, File.Exists(output));
        }
        finally
        {
            File.Delete(output);
        }
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task TextOnlyControls_IsAnEmptyTextError()
    {
        (int exitCode, string stderr, bool wrote) = await RunWithTextAsync(OnlyControls);
        Assert.NotEqual(0, exitCode);
        Assert.False(wrote, "a WAV was written for a text of only control characters");
        Assert.Contains("empty", stderr, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task TestModeOnlyControls_IsAnEmptyTextError()
    {
        (int exitCode, string _, string stderr) = await CliIntegrationTests.RunCliAsync(
            "--test-mode", "--config", ModelPath + ".json", "--language", "es", "--text", OnlyControls);
        Assert.NotEqual(0, exitCode);
        Assert.DoesNotContain("[test-mode] phoneme_ids", stderr, StringComparison.Ordinal);
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task JsonlOnlyControls_ReadsLikeAnEmptyText()
    {
        string output = Path.Join(Path.GetTempPath(), $"sanitize-{Guid.NewGuid():N}.wav");
        string[] args = ["--model", ModelPath, "--language", "es", "--no-warmup", "--output_file", output, "--json-input"];
        try
        {
            (int emptyExit, string _, string emptyErr) = await CliIntegrationTests.RunCliWithInputAsync("{\"text\":\"\"}\n", args);
            (int dirtyExit, string _, string dirtyErr) = await CliIntegrationTests.RunCliWithInputAsync(
                "{\"text\":\"" + JsonEncodedText.Encode("\u0000" + OnlyControls) + "\"}\n", args);
            Assert.NotEqual(0, emptyExit);
            Assert.Equal(emptyExit, dirtyExit);
            Assert.Contains("Missing or empty phoneme_ids", emptyErr, StringComparison.Ordinal);
            Assert.Contains("Missing or empty phoneme_ids", dirtyErr, StringComparison.Ordinal);
        }
        finally
        {
            File.Delete(output);
        }
    }

    [Fact]
    [Trait("Category", "CLI")]
    public async Task JsonlOnlyControlsWithPhonemeIds_UsesTheIds()
    {
        string line = await TestModeIdsAsync("hola");
        string ids = line[(line.IndexOf(": ", StringComparison.Ordinal) + 2)..];
        Assert.StartsWith("[", ids, StringComparison.Ordinal);
        Assert.Equal(
            await SynthesizedBytesAsync(null, "{\"phoneme_ids\":" + ids + "}\n"),
            await SynthesizedBytesAsync(null, "{\"text\":\"\\u0000\\u007f\",\"phoneme_ids\":" + ids + "}\n"));
    }
}
