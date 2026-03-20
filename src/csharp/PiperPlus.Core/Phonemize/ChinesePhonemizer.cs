using System;
using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

// -----------------------------------------------------------------
// ChinesePhonemizer
// -----------------------------------------------------------------

/// <summary>
/// Chinese (Mandarin) phonemizer that wraps an <see cref="IChineseG2PEngine"/>.
/// <para>
/// The engine already returns PUA-mapped tokens and per-token prosody
/// (tone, syllable position, word length), so this class is a thin
/// pass-through that validates array consistency and delegates
/// <see cref="PostProcessIds"/> using the same BOS + PAD + EOS pattern
/// as <see cref="EnglishPhonemizer"/> (matching the Python
/// <c>base.py</c> algorithm for all non-Japanese languages).
/// </para>
/// </summary>
public sealed class ChinesePhonemizer : IPhonemizer
{
    private readonly IChineseG2PEngine _engine;

    /// <summary>
    /// Create a new <see cref="ChinesePhonemizer"/> backed by the given G2P engine.
    /// </summary>
    /// <param name="engine">
    /// Chinese G2P engine that produces PUA-mapped phonemes with prosody.
    /// </param>
    public ChinesePhonemizer(IChineseG2PEngine engine)
    {
        _engine = engine ?? throw new ArgumentNullException(nameof(engine));
    }

    /// <inheritdoc />
    public List<string> Phonemize(string text)
    {
        var (tokens, _) = PhonemizeCore(text);
        return tokens;
    }

    /// <inheritdoc />
    public (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeWithProsody(string text)
    {
        return PhonemizeCore(text);
    }

    /// <inheritdoc />
    /// <remarks>
    /// Returns <c>null</c> --- Chinese models use the phoneme-ID map from config.json.
    /// </remarks>
    public Dictionary<string, int[]>? GetPhonemeIdMap() => null;

    /// <inheritdoc />
    /// <remarks>
    /// Chinese requires inter-phoneme padding and BOS/EOS wrapping
    /// (identical to the English / espeak-ng compatible algorithm).
    /// This mirrors the Python <c>base.py post_process_ids()</c> used
    /// by all non-Japanese languages.
    /// <para>
    /// Transformation:
    /// <code>
    /// Input:  [10, 59, 24]
    /// PAD:    [10, 0, 59, 0, 24, 0]
    /// BOS/EOS: [BOS, 0, 10, 0, 59, 0, 24, 0, EOS]
    /// </code>
    /// </para>
    /// </remarks>
    public (List<int> Ids, List<ProsodyInfo?> Prosody) PostProcessIds(
        List<int> phonemeIds,
        List<ProsodyInfo?> prosodyFeatures,
        Dictionary<string, int[]> phonemeIdMap)
    {
        return PiperPhonemeConverter.EspeakPostProcessIds(phonemeIds, prosodyFeatures, phonemeIdMap);
    }

    // -----------------------------------------------------------------
    // Core implementation
    // -----------------------------------------------------------------

    /// <summary>
    /// Shared implementation for both <see cref="Phonemize"/> and
    /// <see cref="PhonemizeWithProsody"/>. The engine already handles
    /// PUA mapping and prosody extraction, so this method only validates
    /// and repackages the result.
    /// </summary>
    private (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeCore(string text)
    {
        var result = _engine.Convert(text);
        var phonemes = result.Phonemes;
        var a1 = result.A1;
        var a2 = result.A2;
        var a3 = result.A3;

        int count = phonemes.Count;

        if (a1.Count != count || a2.Count != count || a3.Count != count)
            throw new InvalidOperationException(
                $"Chinese G2P result lists have inconsistent lengths: phonemes={count}, A1={a1.Count}, A2={a2.Count}, A3={a3.Count}");

        var tokens = new List<string>(count);
        var prosody = new List<ProsodyInfo?>(count);

        for (int i = 0; i < count; i++)
        {
            tokens.Add(phonemes[i]);
            prosody.Add(new ProsodyInfo(a1[i], a2[i], a3[i]));
        }

        return (tokens, prosody);
    }
}
