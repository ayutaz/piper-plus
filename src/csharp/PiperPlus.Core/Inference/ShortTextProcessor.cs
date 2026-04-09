using System;
using System.Linq;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Mitigations for short-text synthesis quality degradation in VITS-based TTS.
/// <para>
/// When input text is very short (few phonemes), the VITS duration predictor
/// can produce zero-length or distorted audio. This class provides three
/// complementary strategies:
/// <list type="bullet">
///   <item><b>Strategy A</b> (<see cref="PadPhonemeIds"/>/<see cref="TrimSilence"/>):
///     Pad short phoneme sequences with silence (pause ID = 0) to reach
///     <see cref="MinPhonemeIds"/>, then trim the resulting silent margins.</item>
///   <item><b>Strategy B</b> (<see cref="AdjustScales"/>):
///     Reduce noise and duration-predictor noise for short sequences to
///     stabilise the stochastic duration predictor.</item>
///   <item><b>Strategy C</b> (<see cref="WrapShortTextWithBreaks"/>):
///     Wrap very short plain text in SSML <c>&lt;break&gt;</c> tags so that
///     the phonemizer sees a longer context.</item>
/// </list>
/// </para>
/// </summary>
public static class ShortTextProcessor
{
    // ------------------------------------------------------------------
    // Constants (shared across all strategies)
    // ------------------------------------------------------------------

    /// <summary>
    /// Minimum number of phoneme IDs below which padding is applied.
    /// </summary>
    internal const int MinPhonemeIds = 40;

    /// <summary>
    /// Character count threshold (excluding whitespace) for Strategy C.
    /// </summary>
    internal const int ShortTextChars = 10;

    /// <summary>
    /// Milliseconds of silence injected by Strategy C <c>&lt;break&gt;</c> tags.
    /// </summary>
    public const int SilencePadMs = 300;

    /// <summary>
    /// RMS threshold below which a window is considered silent (Strategy A trim).
    /// </summary>
    internal const float TrimThresholdRms = 0.01f;

    /// <summary>
    /// Minimum number of samples to keep after trimming (22050 Hz * 0.1 s).
    /// </summary>
    internal const int TrimMinSamples = 2205;

    /// <summary>
    /// Window size (in samples) used for RMS-based silence detection.
    /// </summary>
    internal const int TrimWindowSize = 256;

    /// <summary>
    /// Pause phoneme ID used for padding (the <c>_</c> / PAD token).
    /// </summary>
    internal const long PauseId = 0;

    // ------------------------------------------------------------------
    // Strategy A: Silence Padding
    // ------------------------------------------------------------------

    /// <summary>
    /// Determine whether the phoneme ID sequence is short enough to need padding.
    /// </summary>
    internal static bool NeedsPadding(long[] phonemeIds)
        => phonemeIds.Length < MinPhonemeIds;

    /// <summary>
    /// Pad a short phoneme-ID sequence with pause IDs (<c>0</c>) inserted
    /// after BOS and before EOS, distributing evenly between both positions.
    /// <para>
    /// The returned array has length &gt;= <see cref="MinPhonemeIds"/>.
    /// If the input is already long enough, a copy is returned unchanged.
    /// Prosody features are also extended with zero entries for the new
    /// padding positions.
    /// </para>
    /// </summary>
    /// <param name="phonemeIds">Original phoneme ID sequence.</param>
    /// <param name="prosodyFlat">
    /// Optional flat prosody array (length = <c>phonemeIds.Length * 3</c>).
    /// </param>
    /// <returns>
    /// Padded phoneme IDs and (optionally) padded prosody array.
    /// </returns>
    internal static (long[] PaddedIds, long[]? PaddedProsody) PadPhonemeIds(
        long[] phonemeIds, long[]? prosodyFlat)
    {
        if (phonemeIds.Length >= MinPhonemeIds)
            return (phonemeIds, prosodyFlat);

        int deficit = MinPhonemeIds - phonemeIds.Length;
        int afterBos = deficit / 2;       // pause IDs inserted after index 0 (BOS)
        int beforeEos = deficit - afterBos; // pause IDs inserted before last index (EOS)

        int newLength = phonemeIds.Length + deficit;
        var padded = new long[newLength];

        // Copy: BOS
        padded[0] = phonemeIds[0];

        // Insert pause IDs after BOS
        for (int i = 1; i <= afterBos; i++)
            padded[i] = PauseId;

        // Copy: body (everything between BOS and EOS)
        int bodyStart = 1;
        int bodyEnd = phonemeIds.Length - 1;
        int bodyLength = bodyEnd - bodyStart;
        Array.Copy(phonemeIds, bodyStart, padded, 1 + afterBos, bodyLength);

        // Insert pause IDs before EOS
        int eosInsertStart = 1 + afterBos + bodyLength;
        for (int i = 0; i < beforeEos; i++)
            padded[eosInsertStart + i] = PauseId;

        // Copy: EOS
        padded[newLength - 1] = phonemeIds[phonemeIds.Length - 1];

        // Extend prosody (pad with zeros)
        long[]? paddedProsody = null;
        if (prosodyFlat is not null && prosodyFlat.Length == phonemeIds.Length * 3)
        {
            paddedProsody = new long[newLength * 3];

            // BOS prosody
            paddedProsody[0] = prosodyFlat[0];
            paddedProsody[1] = prosodyFlat[1];
            paddedProsody[2] = prosodyFlat[2];

            // After-BOS padding: zeros (already initialised)

            // Body prosody
            int bodyProsodyOffset = (1 + afterBos) * 3;
            Array.Copy(prosodyFlat, bodyStart * 3, paddedProsody, bodyProsodyOffset, bodyLength * 3);

            // Before-EOS padding: zeros (already initialised)

            // EOS prosody
            int eosSrcOffset = (phonemeIds.Length - 1) * 3;
            int eosDstOffset = (newLength - 1) * 3;
            paddedProsody[eosDstOffset] = prosodyFlat[eosSrcOffset];
            paddedProsody[eosDstOffset + 1] = prosodyFlat[eosSrcOffset + 1];
            paddedProsody[eosDstOffset + 2] = prosodyFlat[eosSrcOffset + 2];
        }

        return (padded, paddedProsody);
    }

    // ------------------------------------------------------------------
    // Strategy A: Post-inference silence trimming
    // ------------------------------------------------------------------

    /// <summary>
    /// Trim leading and trailing silence from float32 audio using a sliding
    /// RMS window. Ensures at least <see cref="TrimMinSamples"/> remain.
    /// </summary>
    /// <param name="audio">Raw float32 audio samples.</param>
    /// <returns>Trimmed audio. Returns the original array if no trimming is needed.</returns>
    internal static float[] TrimSilence(float[] audio)
    {
        if (audio.Length <= TrimMinSamples)
            return audio;

        int totalWindows = audio.Length / TrimWindowSize;
        if (totalWindows < 2)
            return audio;

        // Find first non-silent window (from the front)
        int firstNonSilent = 0;
        bool foundFront = false;
        for (int w = 0; w < totalWindows; w++)
        {
            if (WindowRms(audio, w * TrimWindowSize) > TrimThresholdRms)
            {
                firstNonSilent = w * TrimWindowSize;
                foundFront = true;
                break;
            }
        }

        if (!foundFront)
        {
            // Entire audio is silent within windowed regions; keep TrimMinSamples
            firstNonSilent = 0;
        }

        // Find last non-silent window (from the back).
        // Include the tail portion beyond the last full window.
        int lastNonSilentEnd = audio.Length;
        bool foundBack = false;

        // Check the tail portion (samples after the last full window)
        int tailStart = totalWindows * TrimWindowSize;
        if (tailStart < audio.Length && WindowRms(audio, tailStart) > TrimThresholdRms)
        {
            lastNonSilentEnd = audio.Length;
            foundBack = true;
        }

        if (!foundBack)
        {
            for (int w = totalWindows - 1; w >= 0; w--)
            {
                if (WindowRms(audio, w * TrimWindowSize) > TrimThresholdRms)
                {
                    lastNonSilentEnd = Math.Min(audio.Length, (w + 1) * TrimWindowSize);
                    foundBack = true;
                    break;
                }
            }
        }

        if (!foundBack)
        {
            lastNonSilentEnd = firstNonSilent;
        }

        // Enforce minimum length
        int trimmedLength = lastNonSilentEnd - firstNonSilent;
        if (trimmedLength < TrimMinSamples)
        {
            // Centre the minimum window around the midpoint of the detected range
            int midpoint = (firstNonSilent + lastNonSilentEnd) / 2;
            firstNonSilent = Math.Max(0, midpoint - TrimMinSamples / 2);
            lastNonSilentEnd = Math.Min(audio.Length, firstNonSilent + TrimMinSamples);
            firstNonSilent = Math.Max(0, lastNonSilentEnd - TrimMinSamples);
        }

        if (firstNonSilent == 0 && lastNonSilentEnd == audio.Length)
            return audio;

        return audio.AsSpan(firstNonSilent, lastNonSilentEnd - firstNonSilent).ToArray();
    }

    /// <summary>
    /// Compute the RMS of a window of <see cref="TrimWindowSize"/> samples
    /// starting at <paramref name="offset"/>.
    /// </summary>
    private static float WindowRms(float[] audio, int offset)
    {
        int end = Math.Min(offset + TrimWindowSize, audio.Length);
        int count = end - offset;
        if (count <= 0)
            return 0f;

        float sumSq = 0f;
        for (int i = offset; i < end; i++)
            sumSq += audio[i] * audio[i];

        return MathF.Sqrt(sumSq / count);
    }

    // ------------------------------------------------------------------
    // Strategy B: Dynamic Scales Adjustment
    // ------------------------------------------------------------------

    /// <summary>
    /// Adjust noise and duration-predictor noise scales for short phoneme
    /// sequences. Returns modified copies of the scale values; the originals
    /// are not mutated.
    /// </summary>
    /// <param name="phonemeIdCount">Number of phoneme IDs in the sequence.</param>
    /// <param name="noiseScale">Original noise scale.</param>
    /// <param name="noiseW">Original noise-W scale.</param>
    /// <returns>Adjusted (noiseScale, noiseW) values.</returns>
    internal static (float NoiseScale, float NoiseW) AdjustScales(
        int phonemeIdCount, float noiseScale, float noiseW)
    {
        if (phonemeIdCount >= MinPhonemeIds)
            return (noiseScale, noiseW);

        float ratio = Math.Clamp((float)phonemeIdCount / MinPhonemeIds, 0f, 1f);
        float adjustedNoiseScale = noiseScale * Math.Max(0.5f, ratio);
        float adjustedNoiseW = noiseW * Math.Max(0.4f, ratio);

        return (adjustedNoiseScale, adjustedNoiseW);
    }

    // ------------------------------------------------------------------
    // Strategy C: SSML <break> auto-injection
    // ------------------------------------------------------------------

    /// <summary>
    /// If the text is plain (not SSML) and very short (character count
    /// excluding whitespace &lt;= <see cref="ShortTextChars"/>), wrap it
    /// in <c>&lt;speak&gt;</c> with <c>&lt;break&gt;</c> tags.
    /// <para>
    /// The result can be fed into the normal SSML processing pipeline
    /// (once the C# SSML parser is available), or can be consumed by
    /// the phonemizer directly — the <c>&lt;break&gt;</c> elements
    /// signal pause insertion at the text level.
    /// </para>
    /// </summary>
    /// <param name="text">Input text.</param>
    /// <returns>
    /// The original text (unchanged) if it is already SSML or exceeds the
    /// character threshold; otherwise an SSML-wrapped version.
    /// </returns>
    public static string WrapShortTextWithBreaks(string text)
    {
        if (string.IsNullOrEmpty(text))
            return text;

        // Already SSML?
        var trimmedStart = text.TrimStart();
        if (trimmedStart.StartsWith("<speak>", StringComparison.OrdinalIgnoreCase)
            || trimmedStart.StartsWith("<speak ", StringComparison.OrdinalIgnoreCase))
            return text;

        // Count non-whitespace characters
        int charCount = 0;
        foreach (char c in text)
        {
            if (!char.IsWhiteSpace(c))
                charCount++;
        }

        if (charCount > ShortTextChars)
            return text;

        return $"<speak><break time=\"{SilencePadMs}ms\"/>{System.Security.SecurityElement.Escape(text)}<break time=\"{SilencePadMs}ms\"/></speak>";
    }

    /// <summary>
    /// Check whether the given text qualifies as "short text" for Strategy C
    /// (not SSML, non-whitespace character count &lt;= <see cref="ShortTextChars"/>).
    /// </summary>
    internal static bool IsShortPlainText(string text)
    {
        if (string.IsNullOrEmpty(text))
            return false;

        var trimmedStart = text.TrimStart();
        if (trimmedStart.StartsWith("<speak>", StringComparison.OrdinalIgnoreCase)
            || trimmedStart.StartsWith("<speak ", StringComparison.OrdinalIgnoreCase))
            return false;

        int charCount = 0;
        foreach (char c in text)
        {
            if (!char.IsWhiteSpace(c))
                charCount++;
        }

        return charCount <= ShortTextChars;
    }

    // ------------------------------------------------------------------
    // Strategy C: Audio-level silence padding for short text
    // ------------------------------------------------------------------

    /// <summary>
    /// Prepend and append silence samples to synthesized audio when the
    /// original input text was short (Strategy C, audio-level path).
    /// <para>
    /// This is the audio-level counterpart to <see cref="WrapShortTextWithBreaks"/>:
    /// both inject <see cref="SilencePadMs"/> of silence before and after the
    /// content. This method operates on the synthesized PCM audio directly,
    /// while <see cref="WrapShortTextWithBreaks"/> emits SSML for pipelines
    /// that include an SSML parser.
    /// </para>
    /// </summary>
    /// <param name="audio">Synthesized int16 PCM audio.</param>
    /// <param name="sampleRate">Audio sample rate (e.g. 22050).</param>
    /// <returns>
    /// Audio with silence prepended and appended. If <paramref name="audio"/>
    /// is empty, returns it unchanged.
    /// </returns>
    public static short[] PadSilenceForShortText(short[] audio, int sampleRate)
    {
        if (audio.Length == 0)
            return audio;

        int silenceSamples = (int)(sampleRate * SilencePadMs / 1000.0f);
        var padded = new short[silenceSamples + audio.Length + silenceSamples];
        audio.CopyTo(padded.AsSpan(silenceSamples));
        // Leading and trailing silence are zero-initialized.
        return padded;
    }
}
