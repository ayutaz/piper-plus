// Issue #499 EOS-region trim on every PiperSession entry point.
//
// Synthesize() and SynthesizeToFloat() ran inference without requesting the
// `durations` output, so the EOS-region trim (and the durations-based
// Strategy A trim) never ran on them; only SynthesizeWithDurations() was
// trimmed. runtime-parity-deep caught it: the C# CLI wrote 48,128 samples
// for the parity fixture while Python / Rust / Go / C++ wrote 46,592.
//
// Fixture: test/models/multilingual-test-medium.onnx (in git) +
//          tests/fixtures/audio-corpus/parity/deterministic_phoneme_ids.jsonl.

using System.Text.Json;
using Microsoft.ML.OnnxRuntime;
using PiperPlus.Core.Config;
using PiperPlus.Core.Inference;
using Xunit;

namespace PiperPlus.Core.Tests.Integration;

public class EosTrimInferenceTests
{
    private static string FindRepoFile(params string[] segments)
    {
        string? dir = AppContext.BaseDirectory;
        while (!string.IsNullOrEmpty(dir))
        {
            string candidate = Path.Join([dir, .. segments]);
            if (File.Exists(candidate))
            {
                return candidate;
            }

            string? parent = Directory.GetParent(dir)?.FullName;
            if (parent == dir)
            {
                break;
            }

            dir = parent;
        }

        // The model and the fixture are checked into git, so a miss is a
        // broken checkout rather than an optional fixture.
        throw new FileNotFoundException(string.Join('/', segments));
    }

    private static SynthesisInput LoadParityInput()
    {
        string path = FindRepoFile(
            "tests", "fixtures", "audio-corpus", "parity", "deterministic_phoneme_ids.jsonl");
        string line = File.ReadLines(path).First(l => !string.IsNullOrWhiteSpace(l));
        using JsonDocument doc = JsonDocument.Parse(line);
        long[] ids = doc.RootElement.GetProperty("phoneme_ids")
            .EnumerateArray().Select(e => e.GetInt64()).ToArray();
        int languageId = doc.RootElement.GetProperty("language_id").GetInt32();
        return new SynthesisInput(
            PhonemeIds: ids,
            LanguageId: languageId,
            NoiseScale: 0f,
            LengthScale: 1f,
            NoiseW: 0f);
    }

    [Fact]
    public void EveryEntryPointTrimsTheEosRegion()
    {
        string modelPath = FindRepoFile("test", "models", "multilingual-test-medium.onnx");
        PiperConfig config = PiperConfig.LoadFromFile(modelPath + ".json");
        using var model = new PiperModel(new InferenceSession(modelPath, new SessionOptions()), config);
        Assert.True(model.HasDurationOutput);

        var session = new PiperSession(model) { SentenceSilenceSeconds = 0f };
        SynthesisInput input = LoadParityInput();
        Assert.True(input.PhonemeIds.Length >= ShortTextProcessor.MinPhonemeIds);

        SynthesisResult withDurations = session.SynthesizeWithDurations(input);
        Assert.NotNull(withDurations.Durations);

        // Non-vacuous: the EOS phoneme spans at least one frame, so an
        // untrimmed output would be longer than the trimmed one.
        Assert.True(Math.Ceiling(withDurations.Durations![^1]) >= 1);

        Assert.Equal(withDurations.Audio.Length, session.Synthesize(input).Length);
        Assert.Equal(withDurations.Audio.Length, session.SynthesizeToFloat(input).Length);
    }
}
