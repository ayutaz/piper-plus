using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Tests for <see cref="ShortTextProcessor"/> — short-text synthesis quality
/// mitigations (Strategies A, B, C).
/// </summary>
public class ShortTextProcessorTests
{
    // ==================================================================
    // Constants validation
    // ==================================================================

    [Fact]
    public void Constants_HaveExpectedValues()
    {
        Assert.Equal(15, ShortTextProcessor.MinPhonemeIds);
        Assert.Equal(3, ShortTextProcessor.MinBodyForStrategyA);
        Assert.Equal(10, ShortTextProcessor.ShortTextChars);
        Assert.Equal(300, ShortTextProcessor.SilencePadMs);
        Assert.Equal(0.01f, ShortTextProcessor.TrimThresholdRms);
        Assert.Equal(2205, ShortTextProcessor.TrimMinSamples);
        Assert.Equal(256, ShortTextProcessor.TrimWindowSize);
        Assert.Equal(0L, ShortTextProcessor.PauseId);
        Assert.Equal(0, ShortTextProcessor.TrimEosMaxFrames);
        Assert.Equal(256, ShortTextProcessor.DefaultHopSize);
    }

    // ==================================================================
    // Strategy A: NeedsPadding
    // ==================================================================

    [Fact]
    public void NeedsPadding_ShortSequence_ReturnsTrue()
    {
        // Length < MinPhonemeIds and body >= MinBodyForStrategyA → padding applies.
        var ids = new long[10];
        Assert.True(ShortTextProcessor.NeedsPadding(ids));
    }

    [Fact]
    public void NeedsPadding_BodyTooShort_ReturnsFalse()
    {
        // The current contract is MinBodyForStrategyA == 3.
        Assert.Equal(3, ShortTextProcessor.MinBodyForStrategyA);

        // body=0 (BOS+EOS only): Strategy A skipped (issue #356).
        Assert.False(ShortTextProcessor.NeedsPadding(new long[2]));

        // body=1
        Assert.False(ShortTextProcessor.NeedsPadding(new long[3]));

        // body=2 (e.g. 「あ。」)
        Assert.False(ShortTextProcessor.NeedsPadding(new long[4]));
    }

    [Fact]
    public void NeedsPadding_BodyAtMinimum_ReturnsTrue()
    {
        // body == MinBodyForStrategyA: Strategy A applies if length < MinPhonemeIds.
        var ids = new long[2 + ShortTextProcessor.MinBodyForStrategyA];
        Assert.True(ShortTextProcessor.NeedsPadding(ids));
    }

    [Fact]
    public void NeedsPadding_ExactMinimum_ReturnsFalse()
    {
        var ids = new long[ShortTextProcessor.MinPhonemeIds];
        Assert.False(ShortTextProcessor.NeedsPadding(ids));
    }

    [Fact]
    public void NeedsPadding_LongSequence_ReturnsFalse()
    {
        var ids = new long[100];
        Assert.False(ShortTextProcessor.NeedsPadding(ids));
    }

    [Fact]
    public void NeedsPadding_OneAboveMinimum_ReturnsFalse()
    {
        var ids = new long[ShortTextProcessor.MinPhonemeIds + 1];
        Assert.False(ShortTextProcessor.NeedsPadding(ids));
    }

    [Fact]
    public void NeedsPadding_OneBelowMinimum_ReturnsTrue()
    {
        var ids = new long[ShortTextProcessor.MinPhonemeIds - 1];
        Assert.True(ShortTextProcessor.NeedsPadding(ids));
    }

    // ==================================================================
    // Strategy A: PadPhonemeIds
    // ==================================================================

    [Fact]
    public void PadPhonemeIds_ShortSequence_PaddedToMinLength()
    {
        // BOS=1, body=[10,11,12], EOS=2 => 5 elements
        long[] ids = [1, 10, 11, 12, 2];

        var (padded, _, _, _) = ShortTextProcessor.PadPhonemeIds(ids, null);

        Assert.Equal(ShortTextProcessor.MinPhonemeIds, padded.Length);
    }

    [Fact]
    public void PadPhonemeIds_PreservesBosAndEos()
    {
        // body must be >= MinBodyForStrategyA for Strategy A to apply.
        long[] ids = [1, 10, 11, 12, 2];

        var (padded, _, _, _) = ShortTextProcessor.PadPhonemeIds(ids, null);

        Assert.Equal(1L, padded[0]);          // BOS preserved
        Assert.Equal(2L, padded[^1]);         // EOS preserved
    }

    [Fact]
    public void PadPhonemeIds_InsertsOnlyPauseIds()
    {
        // body must be >= MinBodyForStrategyA for Strategy A to apply.
        long[] ids = [1, 10, 11, 12, 2]; // body = 3
        var originalSet = new HashSet<long>(ids);

        var (padded, _, _, _) = ShortTextProcessor.PadPhonemeIds(ids, null);

        // Every element that wasn't in the original must be PauseId (0)
        foreach (long id in padded)
        {
            if (!originalSet.Contains(id))
                Assert.Equal(ShortTextProcessor.PauseId, id);
        }
    }

    [Fact]
    public void PadPhonemeIds_SkipsWhenBodyTooShort()
    {
        // body=2 ("あ。" case) → Strategy A skipped, returns input unchanged.
        long[] ids = [1, 10, 11, 2]; // body = 2
        var (padded, prosody, _, _) = ShortTextProcessor.PadPhonemeIds(ids, null);

        // The current contract is MinBodyForStrategyA == 3, so this body=2
        // input must be returned untouched. If MinBodyForStrategyA is ever
        // lowered below 3 we will need to revisit this assertion.
        Assert.Equal(3, ShortTextProcessor.MinBodyForStrategyA);
        Assert.Same(ids, padded);
        Assert.Null(prosody);
    }

    [Fact]
    public void PadPhonemeIds_BodyPreserved()
    {
        long[] ids = [1, 10, 11, 12, 13, 2];

        var (padded, _, _, _) = ShortTextProcessor.PadPhonemeIds(ids, null);

        // The body elements (10, 11, 12, 13) should appear in order somewhere
        // between the first pause-block and the second pause-block.
        var paddedList = padded.ToList();
        int idx10 = paddedList.IndexOf(10);
        int idx11 = paddedList.IndexOf(11);
        int idx12 = paddedList.IndexOf(12);
        int idx13 = paddedList.IndexOf(13);

        Assert.True(idx10 > 0, "Body element 10 should come after BOS");
        Assert.True(idx11 > idx10, "Body elements should be in order");
        Assert.True(idx12 > idx11, "Body elements should be in order");
        Assert.True(idx13 > idx12, "Body elements should be in order");
        Assert.True(idx13 < padded.Length - 1, "Body should be before EOS");
    }

    [Fact]
    public void PadPhonemeIds_AlreadyLongEnough_ReturnsOriginal()
    {
        var ids = new long[50];
        ids[0] = 1; // BOS
        ids[^1] = 2; // EOS

        var (padded, _, _, _) = ShortTextProcessor.PadPhonemeIds(ids, null);

        Assert.Same(ids, padded); // No allocation when not needed
    }

    [Fact]
    public void PadPhonemeIds_WithProsody_ProsodyExtended()
    {
        // body must be >= MinBodyForStrategyA so Strategy A applies.
        long[] ids = [1, 10, 11, 12, 2]; // 5 elements (body=3)
        long[] prosody = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]; // 5 * 3

        var (padded, paddedProsody, _, _) = ShortTextProcessor.PadPhonemeIds(ids, prosody);

        Assert.NotNull(paddedProsody);
        Assert.Equal(padded.Length * 3, paddedProsody.Length);

        // BOS prosody preserved
        Assert.Equal(1L, paddedProsody[0]);
        Assert.Equal(2L, paddedProsody[1]);
        Assert.Equal(3L, paddedProsody[2]);

        // EOS prosody preserved
        Assert.Equal(13L, paddedProsody[^3]);
        Assert.Equal(14L, paddedProsody[^2]);
        Assert.Equal(15L, paddedProsody[^1]);
    }

    [Fact]
    public void PadPhonemeIds_WithProsody_PaddingPositionsAreZero()
    {
        // body must be >= MinBodyForStrategyA so Strategy A applies.
        long[] ids = [1, 10, 11, 12, 2]; // 5 elements (body=3)
        long[] prosody = [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5];

        var (padded, paddedProsody, _, _) = ShortTextProcessor.PadPhonemeIds(ids, prosody);

        Assert.NotNull(paddedProsody);

        // Prosody for padding positions should be zero
        // Check one of the after-BOS padding positions (index 1)
        Assert.Equal(0L, paddedProsody[3]);  // a1 of first pad
        Assert.Equal(0L, paddedProsody[4]);  // a2 of first pad
        Assert.Equal(0L, paddedProsody[5]);  // a3 of first pad
    }

    [Fact]
    public void PadPhonemeIds_NullProsody_ReturnsNull()
    {
        // body must be >= MinBodyForStrategyA so PadPhonemeIds actually pads.
        long[] ids = [1, 10, 11, 12, 2];

        var (_, paddedProsody, _, _) = ShortTextProcessor.PadPhonemeIds(ids, null);

        Assert.Null(paddedProsody);
    }

    [Fact]
    public void PadPhonemeIds_MismatchedProsodyLength_ReturnsNull()
    {
        long[] ids = [1, 10, 11, 12, 2];
        long[] prosody = [1, 2]; // wrong length (should be 15)

        var (_, paddedProsody, _, _) = ShortTextProcessor.PadPhonemeIds(ids, prosody);

        Assert.Null(paddedProsody);
    }

    [Fact]
    public void PadPhonemeIds_EvenDistribution()
    {
        // With 5 elements, deficit = 35. afterBos = 17, beforeEos = 18.
        long[] ids = [1, 10, 11, 12, 2];

        var (padded, _, _, _) = ShortTextProcessor.PadPhonemeIds(ids, null);

        // Count pause IDs after BOS (index 1) until first body element
        int afterBosPadding = 0;
        for (int i = 1; i < padded.Length; i++)
        {
            if (padded[i] == ShortTextProcessor.PauseId)
                afterBosPadding++;
            else
                break;
        }

        // Count pause IDs before EOS (scanning backward from second-to-last)
        int beforeEosPadding = 0;
        for (int i = padded.Length - 2; i >= 0; i--)
        {
            if (padded[i] == ShortTextProcessor.PauseId)
                beforeEosPadding++;
            else
                break;
        }

        int totalPadding = afterBosPadding + beforeEosPadding;
        // 5 input IDs → deficit = MinPhonemeIds - 5 pause tokens.
        Assert.Equal(ShortTextProcessor.MinPhonemeIds - 5, totalPadding);
        // Distribution should be roughly even (difference <= 1)
        Assert.True(Math.Abs(afterBosPadding - beforeEosPadding) <= 1,
            $"Padding should be roughly even: afterBos={afterBosPadding}, beforeEos={beforeEosPadding}");
    }

    // ==================================================================
    // Strategy A: TrimPaddingByDurations (precise post-trim, issue #356)
    // ==================================================================
    // Mirrors src/python_run/tests/test_short_text_mitigation.py.

    [Fact]
    public void TrimPaddingByDurations_NoOpWhenNoPadding()
    {
        var audio = Enumerable.Range(0, 1000).Select(i => (float)i).ToArray();
        var durations = new float[] { 1f, 1f, 1f, 1f, 1f };
        var result = ShortTextProcessor.TrimPaddingByDurations(
            audio, durations, frontPad: 0, backPad: 0, hopSize: 256);
        Assert.Equal(audio.Length, result.Length);
    }

    [Fact]
    public void TrimPaddingByDurations_TrimsFrontPaddingOnly()
    {
        // Layout: BOS=2, pad×3 (3+3+3), body=4, EOS=1 → 19 frames total
        var durations = new[] { 2f, 3f, 3f, 3f, 4f, 1f };
        const int hop = 100;
        const int total = 1900;
        var audio = new float[total];
        var result = ShortTextProcessor.TrimPaddingByDurations(
            audio, durations, frontPad: 3, backPad: 0, hopSize: hop, eosMaxFrames: 6);
        // BOS + front padding samples = (2+3+3+3) * 100 = 1100
        Assert.Equal(total - 1100, result.Length);
    }

    [Fact]
    public void TrimPaddingByDurations_DefaultStripsEosCompletely()
    {
        var durations = new[] { 2f, 5f, 5f, 4f, 4f, 5f, 5f, 8f };
        const int hop = 100;
        const int total = 3800;
        var audio = new float[total];
        var result = ShortTextProcessor.TrimPaddingByDurations(
            audio, durations, frontPad: 2, backPad: 2, hopSize: hop);
        // BOS + front padding = (2+5+5)*100 = 1200
        // back padding + entire EOS = (5+5+8)*100 = 1800
        Assert.Equal(total - 1200 - 1800, result.Length);
    }

    [Fact]
    public void TrimPaddingByDurations_ClampsInflatedEos()
    {
        // EOS=10 frames, eosMaxFrames=6 → excess 4 frames trimmed.
        var durations = new[] { 2f, 3f, 3f, 4f, 3f, 3f, 10f };
        const int hop = 100;
        const int total = 2800;
        var audio = new float[total];
        var result = ShortTextProcessor.TrimPaddingByDurations(
            audio, durations, frontPad: 2, backPad: 2, hopSize: hop, eosMaxFrames: 6);
        // BOS + front padding = (2+3+3) * 100 = 800
        // back padding + EOS excess = (3+3 + (10-6)) * 100 = 1000
        Assert.Equal(total - 800 - 1000, result.Length);
    }

    [Fact]
    public void TrimPaddingByDurations_ReturnsInputWhenDurationsNull()
    {
        var audio = new float[1000];
        var result = ShortTextProcessor.TrimPaddingByDurations(
            audio, null, frontPad: 3, backPad: 3, hopSize: 256);
        Assert.Equal(audio.Length, result.Length);
    }

    [Fact]
    public void TrimPaddingByDurations_ReturnsInputWhenDurationsTooShort()
    {
        var audio = new float[1000];
        var durations = new[] { 1f, 1f, 1f };
        var result = ShortTextProcessor.TrimPaddingByDurations(
            audio, durations, frontPad: 5, backPad: 5, hopSize: 256);
        Assert.Equal(audio.Length, result.Length);
    }

    [Fact]
    public void TrimPaddingByDurations_ReturnsInputWhenHopSizeZero()
    {
        var audio = new float[1000];
        var durations = new float[] { 1f, 1f, 1f, 1f, 1f, 1f, 1f, 1f };
        var result = ShortTextProcessor.TrimPaddingByDurations(
            audio, durations, frontPad: 2, backPad: 2, hopSize: 0);
        Assert.Equal(audio.Length, result.Length);
    }

    [Fact]
    public void TrimPaddingByDurations_TruncationMatchesIntCast()
    {
        // Layout (frontPad=1, backPad=1, body=3):
        //   [BOS=0.701, pad=0.701, body=2, body=2, body=2, pad=0.703, EOS=0.701]
        // Front trim = (int)((0.701+0.701)*100) = 140  (truncated, not rounded)
        // Back trim  = (int)(0.703*100) + (int)(0.701*100) = 70 + 70 = 140
        // A round() implementation would diverge by 1 sample → cross-runtime drift.
        var durations = new[] { 0.701f, 0.701f, 2f, 2f, 2f, 0.703f, 0.701f };
        const int hop = 100;
        float sum = 0f;
        foreach (var d in durations) sum += d;
        int total = (int)(sum * hop);
        var audio = new float[total];
        var result = ShortTextProcessor.TrimPaddingByDurations(
            audio, durations, frontPad: 1, backPad: 1, hopSize: hop);
        Assert.Equal(total - 140 - 140, result.Length);
    }

    // ==================================================================
    // Strategy A: TrimSilence
    // ==================================================================

    [Fact]
    public void TrimSilence_AllSilent_KeepsMinSamples()
    {
        // All zeros => entirely silent
        var audio = new float[10000];

        float[] trimmed = ShortTextProcessor.TrimSilence(audio);

        Assert.True(trimmed.Length >= ShortTextProcessor.TrimMinSamples,
            $"Expected at least {ShortTextProcessor.TrimMinSamples} samples, got {trimmed.Length}");
    }

    [Fact]
    public void TrimSilence_NoSilence_ReturnsOriginal()
    {
        // Audio with no silent regions (all 0.5f)
        var audio = new float[5000];
        Array.Fill(audio, 0.5f);

        float[] trimmed = ShortTextProcessor.TrimSilence(audio);

        // Should return the original array (no trimming needed)
        Assert.Same(audio, trimmed);
    }

    [Fact]
    public void TrimSilence_ShortAudio_ReturnsOriginal()
    {
        // Audio shorter than TrimMinSamples
        var audio = new float[ShortTextProcessor.TrimMinSamples - 1];
        Array.Fill(audio, 0.1f);

        float[] trimmed = ShortTextProcessor.TrimSilence(audio);

        Assert.Same(audio, trimmed);
    }

    [Fact]
    public void TrimSilence_SilentLeadingAndTrailing_TrimsCorrectly()
    {
        // 1000 samples silence + 3000 samples audio + 1000 samples silence
        var audio = new float[5000];
        // Fill the middle portion with non-silent audio
        for (int i = 1000; i < 4000; i++)
            audio[i] = 0.5f;

        float[] trimmed = ShortTextProcessor.TrimSilence(audio);

        // Trimmed audio should be shorter than original
        Assert.True(trimmed.Length < audio.Length,
            $"Trimmed ({trimmed.Length}) should be shorter than original ({audio.Length})");
        // But should still contain the non-silent portion
        Assert.True(trimmed.Length >= ShortTextProcessor.TrimMinSamples);
    }

    [Fact]
    public void TrimSilence_VeryShortNonSilent_MaintainsMinSamples()
    {
        // Mostly silent with a very brief blip in the middle
        var audio = new float[10000];
        audio[5000] = 1.0f; // single loud sample

        float[] trimmed = ShortTextProcessor.TrimSilence(audio);

        Assert.True(trimmed.Length >= ShortTextProcessor.TrimMinSamples);
    }

    // ==================================================================
    // Strategy B: AdjustScales
    // ==================================================================

    [Fact]
    public void AdjustScales_LongSequence_NoChange()
    {
        float noiseScale = 0.667f;
        float noiseW = 0.8f;

        var (adjNoise, adjW) = ShortTextProcessor.AdjustScales(
            ShortTextProcessor.MinPhonemeIds, noiseScale, noiseW);

        Assert.Equal(noiseScale, adjNoise);
        Assert.Equal(noiseW, adjW);
    }

    [Fact]
    public void AdjustScales_AboveMinimum_NoChange()
    {
        float noiseScale = 0.667f;
        float noiseW = 0.8f;

        var (adjNoise, adjW) = ShortTextProcessor.AdjustScales(100, noiseScale, noiseW);

        Assert.Equal(noiseScale, adjNoise);
        Assert.Equal(noiseW, adjW);
    }

    [Fact]
    public void AdjustScales_ShortSequence_ReducesScales()
    {
        float noiseScale = 0.667f;
        float noiseW = 0.8f;

        var (adjNoise, adjW) = ShortTextProcessor.AdjustScales(10, noiseScale, noiseW);

        Assert.True(adjNoise < noiseScale,
            $"Adjusted noiseScale ({adjNoise}) should be less than original ({noiseScale})");
        Assert.True(adjW < noiseW,
            $"Adjusted noiseW ({adjW}) should be less than original ({noiseW})");
    }

    [Fact]
    public void AdjustScales_VeryShortSequence_FlooredAtMinimumRatio()
    {
        float noiseScale = 1.0f;
        float noiseW = 1.0f;

        // 1 phoneme: ratio = 1/40 = 0.025, floor applied
        var (adjNoise, adjW) = ShortTextProcessor.AdjustScales(1, noiseScale, noiseW);

        // noiseScale floor: max(0.5, 0.025) = 0.5
        Assert.Equal(0.5f, adjNoise);
        // noiseW floor: max(0.4, 0.025) = 0.4
        Assert.Equal(0.4f, adjW);
    }

    [Fact]
    public void AdjustScales_HalfMinimum_CorrectRatio()
    {
        float noiseScale = 1.0f;
        float noiseW = 1.0f;
        int halfMin = ShortTextProcessor.MinPhonemeIds / 2;

        var (adjNoise, adjW) = ShortTextProcessor.AdjustScales(halfMin, noiseScale, noiseW);

        // ratio = halfMin / MinPhonemeIds, floors clamp where needed.
        float ratio = (float)halfMin / ShortTextProcessor.MinPhonemeIds;
        float nsRatio = MathF.Max(0.5f, ratio);
        float nwRatio = MathF.Max(0.4f, ratio);
        Assert.Equal(nsRatio, adjNoise);
        Assert.Equal(nwRatio, adjW);
    }

    [Fact]
    public void AdjustScales_ZeroLength_UsesFloor()
    {
        float noiseScale = 0.667f;
        float noiseW = 0.8f;

        var (adjNoise, adjW) = ShortTextProcessor.AdjustScales(0, noiseScale, noiseW);

        // ratio = 0, floor applies
        Assert.Equal(noiseScale * 0.5f, adjNoise, 5);
        Assert.Equal(noiseW * 0.4f, adjW, 5);
    }

    [Fact]
    public void AdjustScales_PreservesLengthScale()
    {
        // LengthScale is not part of AdjustScales; just verify the API
        // doesn't affect it implicitly by returning only noiseScale + noiseW.
        var (adjNoise, adjW) = ShortTextProcessor.AdjustScales(10, 0.667f, 0.8f);

        // Both returned values should be positive
        Assert.True(adjNoise > 0f);
        Assert.True(adjW > 0f);
    }

    // ==================================================================
    // Strategy C: WrapShortTextWithBreaks
    // ==================================================================

    [Fact]
    public void WrapShortTextWithBreaks_ShortText_Wrapped()
    {
        string result = ShortTextProcessor.WrapShortTextWithBreaks("Hello");

        Assert.StartsWith("<speak>", result);
        Assert.EndsWith("</speak>", result);
        Assert.Contains("<break time=\"300ms\"/>", result);
        Assert.Contains("Hello", result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_ShortText_HasTwoBreaks()
    {
        string result = ShortTextProcessor.WrapShortTextWithBreaks("Hi");

        // Count <break> occurrences
        int count = 0;
        int idx = 0;
        while ((idx = result.IndexOf("<break", idx, StringComparison.Ordinal)) >= 0)
        {
            count++;
            idx++;
        }
        Assert.Equal(2, count);
    }

    [Fact]
    public void WrapShortTextWithBreaks_ExactlyThreshold_Wrapped()
    {
        // Exactly 10 non-whitespace chars
        string text = "abcdefghij";
        Assert.Equal(ShortTextProcessor.ShortTextChars, text.Length);

        string result = ShortTextProcessor.WrapShortTextWithBreaks(text);

        Assert.StartsWith("<speak>", result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_OneAboveThreshold_NotWrapped()
    {
        // 11 non-whitespace chars
        string text = "abcdefghijk";

        string result = ShortTextProcessor.WrapShortTextWithBreaks(text);

        Assert.Equal(text, result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_LongText_NotWrapped()
    {
        string text = "This is a much longer sentence that should not be wrapped.";

        string result = ShortTextProcessor.WrapShortTextWithBreaks(text);

        Assert.Equal(text, result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_AlreadySsml_NotWrapped()
    {
        string text = "<speak>Hello</speak>";

        string result = ShortTextProcessor.WrapShortTextWithBreaks(text);

        Assert.Equal(text, result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_SsmlWithLeadingWhitespace_NotWrapped()
    {
        string text = "  <speak>Hello</speak>";

        string result = ShortTextProcessor.WrapShortTextWithBreaks(text);

        Assert.Equal(text, result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_EmptyString_ReturnsEmpty()
    {
        string result = ShortTextProcessor.WrapShortTextWithBreaks("");

        Assert.Equal("", result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_NullString_ReturnsNull()
    {
        string result = ShortTextProcessor.WrapShortTextWithBreaks(null!);

        Assert.Null(result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_WhitespaceOnly_Wrapped()
    {
        // 0 non-whitespace chars, which is <= threshold
        string text = "   ";

        string result = ShortTextProcessor.WrapShortTextWithBreaks(text);

        Assert.StartsWith("<speak>", result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_ShortWithSpaces_CountsOnlyNonWhitespace()
    {
        // "Hi   there" has 7 non-whitespace chars (below 10)
        string text = "Hi   there";

        string result = ShortTextProcessor.WrapShortTextWithBreaks(text);

        Assert.StartsWith("<speak>", result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_CjkShortText_Wrapped()
    {
        // Japanese short text: 5 chars
        string text = "Hello";

        string result = ShortTextProcessor.WrapShortTextWithBreaks(text);

        Assert.StartsWith("<speak>", result);
        Assert.Contains(text, result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_SsmlCaseInsensitive()
    {
        string text = "<SPEAK>Hello</SPEAK>";

        string result = ShortTextProcessor.WrapShortTextWithBreaks(text);

        Assert.Equal(text, result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_SsmlWithAttributes_NotWrapped()
    {
        string text = "<speak xml:lang=\"ja\">Hello</speak>";

        string result = ShortTextProcessor.WrapShortTextWithBreaks(text);

        Assert.Equal(text, result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_XmlSpecialChars_Escaped()
    {
        string result = ShortTextProcessor.WrapShortTextWithBreaks("A & B");

        Assert.Contains("&amp;", result);
        Assert.DoesNotContain("& B", result);
        Assert.StartsWith("<speak>", result);
    }

    [Fact]
    public void WrapShortTextWithBreaks_AngleBracket_Escaped()
    {
        string result = ShortTextProcessor.WrapShortTextWithBreaks("1<2");

        Assert.Contains("&lt;", result);
        Assert.StartsWith("<speak>", result);
    }

    // ==================================================================
    // Strategy C: IsShortPlainText
    // ==================================================================

    [Fact]
    public void IsShortPlainText_ShortText_ReturnsTrue()
    {
        Assert.True(ShortTextProcessor.IsShortPlainText("Hello"));
    }

    [Fact]
    public void IsShortPlainText_LongText_ReturnsFalse()
    {
        Assert.False(ShortTextProcessor.IsShortPlainText("This is a long sentence"));
    }

    [Fact]
    public void IsShortPlainText_Ssml_ReturnsFalse()
    {
        Assert.False(ShortTextProcessor.IsShortPlainText("<speak>Hi</speak>"));
    }

    [Fact]
    public void IsShortPlainText_Empty_ReturnsFalse()
    {
        Assert.False(ShortTextProcessor.IsShortPlainText(""));
    }

    [Fact]
    public void IsShortPlainText_Null_ReturnsFalse()
    {
        Assert.False(ShortTextProcessor.IsShortPlainText(null!));
    }

    [Fact]
    public void IsShortPlainText_ExactThreshold_ReturnsTrue()
    {
        Assert.True(ShortTextProcessor.IsShortPlainText("abcdefghij")); // 10 chars
    }

    [Fact]
    public void IsShortPlainText_OneAboveThreshold_ReturnsFalse()
    {
        Assert.False(ShortTextProcessor.IsShortPlainText("abcdefghijk")); // 11 chars
    }

    [Fact]
    public void IsShortPlainText_SsmlWithAttributes_ReturnsFalse()
    {
        Assert.False(ShortTextProcessor.IsShortPlainText("<speak xml:lang=\"ja\">Hi</speak>"));
    }

    // ==================================================================
    // Integration: PadPhonemeIds + TrimSilence round-trip
    // ==================================================================

    [Fact]
    public void PadAndTrim_ShortSequence_OutputReasonableLength()
    {
        // Simulate: pad a 5-element sequence, generate "audio" with silence pads,
        // then trim. This tests the intended A-strategy flow.
        long[] ids = [1, 10, 11, 12, 2];

        var (padded, _, _, _) = ShortTextProcessor.PadPhonemeIds(ids, null);
        Assert.Equal(ShortTextProcessor.MinPhonemeIds, padded.Length);

        // Simulate audio: silence for padding, non-silent for real phonemes
        // Each phoneme produces ~256 samples for simplicity
        var audio = new float[padded.Length * 256];
        int deficit = padded.Length - ids.Length;
        int afterBos = deficit / 2;

        // Mark body region as non-silent
        int bodyStart = (1 + afterBos) * 256;
        int bodyEnd = bodyStart + 3 * 256; // 3 body elements
        for (int i = bodyStart; i < bodyEnd && i < audio.Length; i++)
            audio[i] = 0.5f;

        float[] trimmed = ShortTextProcessor.TrimSilence(audio);

        // Trimmed should be shorter than padded audio but >= TrimMinSamples
        Assert.True(trimmed.Length < audio.Length);
        Assert.True(trimmed.Length >= ShortTextProcessor.TrimMinSamples);
    }

    // ==================================================================
    // Strategy B: AdjustScales with typical default values
    // ==================================================================

    [Fact]
    public void AdjustScales_DefaultScales_ShortInput_ReducedButPositive()
    {
        // Default VITS scales
        float noiseScale = 0.667f;
        float noiseW = 0.8f;

        var (adjNoise, adjW) = ShortTextProcessor.AdjustScales(5, noiseScale, noiseW);

        Assert.True(adjNoise > 0f && adjNoise <= noiseScale);
        Assert.True(adjW > 0f && adjW <= noiseW);
    }

    // ==================================================================
    // Strategy C: WrapShortTextWithBreaks format validation
    // ==================================================================

    [Fact]
    public void WrapShortTextWithBreaks_OutputFormat_Correct()
    {
        string result = ShortTextProcessor.WrapShortTextWithBreaks("Test");

        Assert.Equal(
            "<speak><break time=\"300ms\"/>Test<break time=\"300ms\"/></speak>",
            result);
    }

    // ==================================================================
    // Strategy C: PadSilenceForShortText (audio-level)
    // ==================================================================

    [Fact]
    public void PadSilenceForShortText_AddsLeadingAndTrailingSilence()
    {
        short[] audio = [100, 200, 300];
        int sampleRate = 22050;
        int expectedSilenceSamples = (int)(sampleRate * ShortTextProcessor.SilencePadMs / 1000.0f);

        short[] padded = ShortTextProcessor.PadSilenceForShortText(audio, sampleRate);

        Assert.Equal(audio.Length + 2 * expectedSilenceSamples, padded.Length);
    }

    [Fact]
    public void PadSilenceForShortText_LeadingSilenceIsZero()
    {
        short[] audio = [100, 200, 300];
        int sampleRate = 22050;
        int silenceSamples = (int)(sampleRate * ShortTextProcessor.SilencePadMs / 1000.0f);

        short[] padded = ShortTextProcessor.PadSilenceForShortText(audio, sampleRate);

        // Leading silence should be all zeros
        for (int i = 0; i < silenceSamples; i++)
        {
            Assert.Equal(0, padded[i]);
        }
    }

    [Fact]
    public void PadSilenceForShortText_TrailingSilenceIsZero()
    {
        short[] audio = [100, 200, 300];
        int sampleRate = 22050;
        int silenceSamples = (int)(sampleRate * ShortTextProcessor.SilencePadMs / 1000.0f);

        short[] padded = ShortTextProcessor.PadSilenceForShortText(audio, sampleRate);

        // Trailing silence should be all zeros
        for (int i = padded.Length - silenceSamples; i < padded.Length; i++)
        {
            Assert.Equal(0, padded[i]);
        }
    }

    [Fact]
    public void PadSilenceForShortText_OriginalAudioPreservedInMiddle()
    {
        short[] audio = [100, 200, 300, 400, 500];
        int sampleRate = 22050;
        int silenceSamples = (int)(sampleRate * ShortTextProcessor.SilencePadMs / 1000.0f);

        short[] padded = ShortTextProcessor.PadSilenceForShortText(audio, sampleRate);

        // Original audio should be at offset silenceSamples
        for (int i = 0; i < audio.Length; i++)
        {
            Assert.Equal(audio[i], padded[silenceSamples + i]);
        }
    }

    [Fact]
    public void PadSilenceForShortText_EmptyAudio_ReturnsEmpty()
    {
        short[] audio = [];

        short[] padded = ShortTextProcessor.PadSilenceForShortText(audio, 22050);

        Assert.Empty(padded);
    }

    [Fact]
    public void PadSilenceForShortText_SilenceDurationMatchesSilencePadMs()
    {
        short[] audio = [1];
        int sampleRate = 22050;

        short[] padded = ShortTextProcessor.PadSilenceForShortText(audio, sampleRate);

        // Each silence block = sampleRate * SilencePadMs / 1000
        int expectedSilenceSamples = (int)(sampleRate * ShortTextProcessor.SilencePadMs / 1000.0f);
        int expectedTotal = expectedSilenceSamples + 1 + expectedSilenceSamples;
        Assert.Equal(expectedTotal, padded.Length);
    }

    [Fact]
    public void PadSilenceForShortText_DifferentSampleRate_CorrectDuration()
    {
        short[] audio = [1];
        int sampleRate = 44100; // Different sample rate

        short[] padded = ShortTextProcessor.PadSilenceForShortText(audio, sampleRate);

        int expectedSilenceSamples = (int)(sampleRate * ShortTextProcessor.SilencePadMs / 1000.0f);
        Assert.Equal(1 + 2 * expectedSilenceSamples, padded.Length);
    }

    // ==================================================================
    // Strategy C: Integration — WrapShortTextWithBreaks detection
    // ==================================================================

    [Fact]
    public void WrapShortTextWithBreaks_DetectsShortText_ForAudioPadding()
    {
        // Verify that WrapShortTextWithBreaks can be used as a short-text
        // detector: it returns a different string for short text.
        string shortText = "Hi";
        string wrapped = ShortTextProcessor.WrapShortTextWithBreaks(shortText);

        bool isShort = !ReferenceEquals(wrapped, shortText)
                       && !string.Equals(wrapped, shortText, StringComparison.Ordinal);
        Assert.True(isShort);
    }

    [Fact]
    public void WrapShortTextWithBreaks_LongText_NotDetectedAsShort()
    {
        string longText = "This is a long sentence that exceeds the threshold.";
        string wrapped = ShortTextProcessor.WrapShortTextWithBreaks(longText);

        // For long text, WrapShortTextWithBreaks returns the same string
        bool isShort = !ReferenceEquals(wrapped, longText)
                       && !string.Equals(wrapped, longText, StringComparison.Ordinal);
        Assert.False(isShort);
    }
}
