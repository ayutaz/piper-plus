// Tests for the Issue #426 / PR #320 input-feed contract on the C# side.
//
// MB-iSTFT-VITS2 + Voice Cloning exports declare speaker_embedding /
// speaker_embedding_mask unconditionally; the C# runtime
// (PiperPlus.Core/Inference/PiperSession.cs:353-389) feeds zero embedding
// + mask=0 when the request omits the embedding so the model falls back
// to emb_g(sid). These tests pin the public API contract — full ONNX
// feed assertions require an integration test with a real model session.

using PiperPlus.Core.Inference;
using Xunit;

namespace PiperPlus.Core.Tests;

public class SynthesisInputSpeakerEmbeddingTests
{
    [Fact]
    public void Validate_AllowsMissingSpeakerEmbedding_WhenSpeakerIdProvided()
    {
        // Issue #426: a model that declares speaker_embedding must still
        // accept inputs with SpeakerEmbedding=null. The engine fills in
        // zero+mask=0 (PiperSession.cs:368-389).
        var input = new SynthesisInput(
            PhonemeIds: [1, 10, 5, 2],
            SpeakerId: 0,
            SpeakerEmbedding: null);

        // Must not throw.
        input.Validate();
    }

    [Fact]
    public void Validate_AllowsSpeakerEmbeddingWithoutSpeakerId()
    {
        // Voice cloning request: SpeakerEmbedding provided, SpeakerId omitted
        // (defaults to 0 — the multispeaker-default sentinel). The Validate()
        // contract permits this because mutual-exclusivity is enforced only
        // when SpeakerId > 0 (see PiperSession.cs:SynthesisInput.Validate).
        var input = new SynthesisInput(
            PhonemeIds: [1, 10, 5, 2],
            SpeakerEmbedding: new float[256]);

        input.Validate();
    }

    [Fact]
    public void Validate_RejectsBothSpeakerIdAndSpeakerEmbedding()
    {
        // Mutual exclusivity (matches Python / Rust / Go behaviour).
        var input = new SynthesisInput(
            PhonemeIds: [1, 10, 5, 2],
            SpeakerId: 3,
            SpeakerEmbedding: new float[256]);

        var ex = Assert.Throws<ArgumentException>(() => input.Validate());
        Assert.Contains("mutually exclusive", ex.Message);
    }

    [Fact]
    public void Validate_AcceptsEmptyEmbeddingArrayAsAbsent()
    {
        // An empty array is treated the same as null: the runtime feeds
        // the zero+mask=0 fallback (PiperSession.cs:355).
        var input = new SynthesisInput(
            PhonemeIds: [1, 10, 5, 2],
            SpeakerId: 5,
            SpeakerEmbedding: []);

        input.Validate();
    }

    [Fact]
    public void SynthesisInput_DefaultsAreSafeForLegacyModels()
    {
        // Defaults must not surface speaker_embedding to legacy
        // (non-MB-iSTFT) sessions that do not declare the input.
        var input = new SynthesisInput(PhonemeIds: [1, 10, 5, 2]);
        Assert.Null(input.SpeakerEmbedding);
    }
}
