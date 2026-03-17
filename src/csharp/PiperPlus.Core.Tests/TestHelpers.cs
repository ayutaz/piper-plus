using System.Text.Json;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Static helpers for creating and cleaning up temporary files in tests.
/// </summary>
internal static class TempFileHelper
{
    /// <summary>
    /// Creates a temp file with the given <paramref name="content"/> and returns its path.
    /// The caller is responsible for deleting the file when done.
    /// </summary>
    public static string CreateTempFile(string content)
    {
        var path = Path.GetTempFileName();
        File.WriteAllText(path, content);
        return path;
    }

    /// <summary>
    /// Creates a temp file containing a minimal valid PiperConfig JSON and returns its path.
    /// The caller is responsible for deleting the file when done.
    /// </summary>
    /// <param name="numSpeakers">Value for <c>num_speakers</c>.</param>
    /// <param name="sampleRate">Value for <c>audio.sample_rate</c>.</param>
    public static string CreateTempJsonConfig(int numSpeakers = 1, int sampleRate = 22050)
    {
        var json = $$"""
        {
          "num_speakers": {{numSpeakers}},
          "phoneme_id_map": {
            "_": [0], "^": [1], "$": [2],
            "a": [10], "i": [11], "k": [12]
          },
          "audio": { "sample_rate": {{sampleRate}} },
          "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 }
        }
        """;

        return CreateTempFile(json);
    }
}

/// <summary>
/// <see cref="IDisposable"/> helper that redirects <see cref="Console.Error"/> to
/// a <see cref="StringWriter"/> for the duration of its lifetime, restoring the
/// original writer on disposal.
/// <para>
/// Replaces the per-class <c>CaptureStdErr()</c> + <c>IDisposable</c> pattern
/// found in <c>SecurityTests</c>, <c>ModelManagerTests</c>, and
/// <c>Phase4IntegrationTests</c>.
/// </para>
/// </summary>
/// <example>
/// <code>
/// using var capture = new StdErrCapture();
/// // ... code that writes to Console.Error ...
/// Assert.Contains("expected warning", capture.Output);
/// </code>
/// </example>
internal sealed class StdErrCapture : IDisposable
{
    private readonly TextWriter _original;

    /// <summary>The <see cref="StringWriter"/> receiving stderr output.</summary>
    public StringWriter Writer { get; }

    public StdErrCapture()
    {
        _original = Console.Error;
        Writer = new StringWriter();
        Console.SetError(Writer);
    }

    /// <summary>All text written to <see cref="Console.Error"/> since construction.</summary>
    public string Output => Writer.ToString();

    public void Dispose()
    {
        Console.SetError(_original);
        Writer.Dispose();
    }
}

/// <summary>
/// Fluent builder for constructing <c>Dictionary&lt;string, int[]&gt;</c> phoneme ID
/// maps used throughout the encoder and phonemizer test suites.
/// </summary>
/// <example>
/// <code>
/// var map = new PhonemeIdMapBuilder()
///     .AddStandard()
///     .Add("ə", 11)
///     .Build();
/// </code>
/// </example>
internal sealed class PhonemeIdMapBuilder
{
    private readonly Dictionary<string, int[]> _map = new();

    /// <summary>
    /// Add a phoneme mapped to one or more IDs.
    /// </summary>
    public PhonemeIdMapBuilder Add(string phoneme, params int[] ids)
    {
        _map[phoneme] = ids;
        return this;
    }

    /// <summary>
    /// Seed the map with the standard structural tokens and a minimal set of
    /// Latin/IPA phonemes shared across Japanese and English test fixtures:
    /// <c>_</c> (PAD), <c>^</c> (BOS), <c>$</c> (EOS), space, plus
    /// <c>a-z</c> mapped to IDs 10-35.
    /// </summary>
    public PhonemeIdMapBuilder AddStandard()
    {
        _map["_"] = [0];
        _map["^"] = [1];
        _map["$"] = [2];
        _map[" "] = [3];

        // a-z -> 10-35
        for (int i = 0; i < 26; i++)
        {
            var ch = ((char)('a' + i)).ToString();
            _map[ch] = [10 + i];
        }

        return this;
    }

    /// <summary>
    /// Return a new dictionary containing all accumulated entries.
    /// The builder can be reused after calling <see cref="Build"/>.
    /// </summary>
    public Dictionary<string, int[]> Build() => new(_map);
}
