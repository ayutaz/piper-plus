using System.Collections.Generic;
using PiperPlus.Core.Phonemize;
using DotNetG2P.Chinese;

namespace PiperPlus.Cli;

/// <summary>
/// Adapter that wraps <see cref="ChineseG2PEngine"/> from the DotNetG2P.Chinese
/// NuGet package to implement <see cref="IChineseG2PEngine"/>.
/// <para>
/// Uses <see cref="ChineseG2PEngine.ToPuaPhonemes"/> for PUA-mapped per-token
/// phonemes (initial + final, without tone markers) and
/// <see cref="ChineseG2PEngine.ToIpaWithProsody"/> for per-syllable prosody.
/// Tone marker PUA characters (U+E046–U+E04A) are inserted after each
/// syllable's tokens, and prosody arrays are aligned 1:1 with the output.
/// </para>
/// </summary>
internal sealed class DotNetChineseG2PEngine : IChineseG2PEngine
{
    /// <summary>Tone number (1–5) to PUA character for tone markers.</summary>
    private static readonly string[] TonePuaStrings =
    [
        "",           // index 0 — unused
        "\uE046",     // tone1 — 阴平
        "\uE047",     // tone2 — 阳平
        "\uE048",     // tone3 — 上声
        "\uE049",     // tone4 — 去声
        "\uE04A",     // tone5 — 轻声
    ];

    private readonly ChineseG2PEngine _engine = new();

    public ChineseG2PResult Convert(string text)
    {
        // ToPuaPhonemes returns PUA-mapped per-token phonemes (initial + final)
        // WITHOUT tone markers (by design in DotNetG2P.Chinese).
        string[] puaPhonemes = _engine.ToPuaPhonemes(text);

        // ToIpaWithProsody returns per-syllable prosody (A1=tone, A2=position, A3=word length).
        var prosodyResult = _engine.ToIpaWithProsody(text);
        int totalSyllables = prosodyResult.Prosody.Count;

        // Edge case: no syllables (empty text or all non-Chinese)
        if (totalSyllables == 0)
        {
            // Pass through any non-Chinese tokens (punctuation etc.) with zero prosody.
            var a1Zero = new int[puaPhonemes.Length];
            var a2Zero = new int[puaPhonemes.Length];
            var a3Zero = new int[puaPhonemes.Length];
            return new ChineseG2PResult(puaPhonemes, a1Zero, a2Zero, a3Zero);
        }

        // Distribute PUA phonemes across syllables and insert tone markers.
        //
        // Strategy: puaPhonemes has (initial + final) per syllable. We know
        // the syllable count from prosody, so we distribute phonemes evenly
        // and insert a tone PUA char after each syllable's group.
        int phonemesPerSyllable = puaPhonemes.Length / totalSyllables;
        int remainder = puaPhonemes.Length % totalSyllables;

        // Guard: if there are fewer phoneme tokens than syllables, the
        // distribution loop cannot assign at least one token per syllable.
        // This shouldn't happen with well-formed DotNetG2P output, but
        // fall back to returning the raw PUA phonemes with tone markers
        // only (no per-syllable distribution) to avoid silent corruption.
        if (phonemesPerSyllable == 0 && remainder == 0)
        {
            var fallback = new List<string>(totalSyllables);
            var fbA1 = new List<int>(totalSyllables);
            var fbA2 = new List<int>(totalSyllables);
            var fbA3 = new List<int>(totalSyllables);

            for (int syl = 0; syl < totalSyllables; syl++)
            {
                var p = prosodyResult.Prosody[syl];
                if (p.A1 >= 1 && p.A1 <= 5)
                {
                    fallback.Add(TonePuaStrings[p.A1]);
                    fbA1.Add(p.A1);
                    fbA2.Add(p.A2);
                    fbA3.Add(p.A3);
                }
            }

            return new ChineseG2PResult(
                Phonemes: fallback,
                A1: fbA1,
                A2: fbA2,
                A3: fbA3);
        }

        // Pre-allocate: each syllable contributes its phonemes + 1 tone marker
        var phonemes = new List<string>(puaPhonemes.Length + totalSyllables);
        var a1 = new List<int>(puaPhonemes.Length + totalSyllables);
        var a2 = new List<int>(puaPhonemes.Length + totalSyllables);
        var a3 = new List<int>(puaPhonemes.Length + totalSyllables);

        int puaIdx = 0;
        for (int syl = 0; syl < totalSyllables; syl++)
        {
            int count = phonemesPerSyllable + (syl < remainder ? 1 : 0);
            var p = prosodyResult.Prosody[syl];

            // Add initial + final PUA phonemes for this syllable
            for (int j = 0; j < count && puaIdx < puaPhonemes.Length; j++, puaIdx++)
            {
                phonemes.Add(puaPhonemes[puaIdx]);
                a1.Add(p.A1);
                a2.Add(p.A2);
                a3.Add(p.A3);
            }

            // Append tone marker PUA (tone1=E046 ... tone5=E04A)
            if (p.A1 >= 1 && p.A1 <= 5)
            {
                phonemes.Add(TonePuaStrings[p.A1]);
                a1.Add(p.A1);
                a2.Add(p.A2);
                a3.Add(p.A3);
            }
        }

        return new ChineseG2PResult(
            Phonemes: phonemes,
            A1: a1,
            A2: a2,
            A3: a3);
    }
}
