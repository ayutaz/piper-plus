// Issue #426 C# integration test — speaker_embedding fallback on a real
// InferenceSession.
//
// Verifies that PiperSession.cs:353-389 feeds zero embedding + mask=0
// when a model declares speaker_embedding / speaker_embedding_mask but
// the caller does not provide a SpeakerEmbedding. Without this, ORT
// raises "Required inputs (['speaker_embedding', 'speaker_embedding_mask'])
// are missing from input feed".
//
// Fixture: `tests/fixtures/mb_istft_speaker_embedding/model.onnx` +
//          `model.onnx.json` (built by build_fixture.py). The test
// skips cleanly when the fixture cannot be located so the suite still
// passes on environments without the Python fixture builder.

using Microsoft.ML.OnnxRuntime;
using PiperPlus.Core.Config;
using PiperPlus.Core.Inference;
using Xunit;

namespace PiperPlus.Core.Tests.Integration;

public class SpeakerEmbeddingInferenceTests
{
    private static (string ModelPath, string ConfigPath)? FindFixture()
    {
        // Search upwards from the test assembly location — the fixture
        // lives at <repo>/tests/fixtures/mb_istft_speaker_embedding/.
        string? dir = AppContext.BaseDirectory;
        while (!string.IsNullOrEmpty(dir))
        {
            string candidate = Path.Combine(
                dir, "tests", "fixtures", "mb_istft_speaker_embedding", "model.onnx");
            if (File.Exists(candidate) && File.Exists(candidate + ".json"))
            {
                return (candidate, candidate + ".json");
            }

            string? parent = Directory.GetParent(dir)?.FullName;
            if (parent == dir)
            {
                break;
            }

            dir = parent;
        }

        return null;
    }

    private static PiperModel? LoadFixtureModel()
    {
        var paths = FindFixture();
        if (paths is null)
        {
            return null;
        }

        PiperConfig config = PiperConfig.LoadFromFile(paths.Value.ConfigPath);
        var sessionOptions = new SessionOptions();
        var session = new InferenceSession(paths.Value.ModelPath, sessionOptions);
        return new PiperModel(session, config);
    }

    [Fact]
    public void DetectsSpeakerEmbeddingInput()
    {
        using PiperModel? model = LoadFixtureModel();
        if (model is null)
        {
            // Skip cleanly when the fixture is unavailable.
            return;
        }

        Assert.True(
            model.HasSpeakerEmbedding,
            "PiperModel must detect speaker_embedding declared by the "
            + "fixture (Issue #426 regression).");
    }

    [Fact]
    public void SynthesizeWithoutEmbeddingProducesAudio()
    {
        using PiperModel? model = LoadFixtureModel();
        if (model is null)
        {
            return;
        }

        var piperSession = new PiperSession(model);

        // phoneme_id_map[i]=[i] for ids 4-49 mapped to ASCII letters in
        // build_fixture.py — we feed raw ids directly.
        var input = new SynthesisInput(
            PhonemeIds: new long[] { 1, 10, 20, 30, 40, 2 },
            SpeakerId: 0,
            SpeakerEmbedding: null);

        // The critical assertion: no ORT exception. Without the
        // zero+mask=0 fallback in PiperSession.cs:368-389, this throws
        // OnnxRuntimeException("Required inputs missing").
        short[] audio = piperSession.Synthesize(input);

        Assert.NotEmpty(audio);
        Assert.Contains(audio, sample => sample != 0);
    }
}
