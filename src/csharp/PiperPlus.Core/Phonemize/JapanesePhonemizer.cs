using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

// -----------------------------------------------------------------
// G2P abstraction layer — allows DotNetG2P to be swapped / mocked.
// -----------------------------------------------------------------

/// <summary>
/// Result returned by a Japanese G2P engine: parallel arrays of
/// phonemes and per-phoneme A1/A2/A3 prosody values.
/// </summary>
/// <param name="Phonemes">
/// OpenJTalk-style phoneme sequence including <c>"sil"</c> and <c>"pau"</c>.
/// </param>
/// <param name="A1">Accent-nucleus relative position for each phoneme.</param>
/// <param name="A2">Mora position in accent phrase (1-based) for each phoneme.</param>
/// <param name="A3">Total morae in accent phrase for each phoneme.</param>
public record G2PResult(string[] Phonemes, int[] A1, int[] A2, int[] A3);

/// <summary>
/// Abstraction over a Japanese G2P engine (e.g. DotNetG2P).
/// <para>
/// Implement this interface to plug in any engine that can produce
/// OpenJTalk-compatible phoneme sequences with A1/A2/A3 prosody values.
/// This keeps <see cref="JapanesePhonemizer"/> testable without a real
/// MeCab/OpenJTalk backend.
/// </para>
/// </summary>
public interface IJapaneseG2PEngine
{
    /// <summary>
    /// Convert Japanese <paramref name="text"/> to phonemes with prosody.
    /// </summary>
    /// <param name="text">Input Japanese text.</param>
    /// <returns>
    /// A <see cref="G2PResult"/> whose arrays are all the same length.
    /// </returns>
    G2PResult Convert(string text);
}

// -----------------------------------------------------------------
// JapanesePhonemizer
// -----------------------------------------------------------------

/// <summary>
/// Japanese phonemizer that mirrors the Python
/// <c>phonemize_japanese_with_prosody()</c> / <c>phonemize_japanese()</c>
/// functions in <c>piper_train/phonemize/japanese.py</c>.
/// <para>
/// Processing flow (1:1 with the Python implementation):
/// <list type="number">
///   <item>Call <see cref="IJapaneseG2PEngine.Convert"/> to obtain phonemes + A1/A2/A3.</item>
///   <item>Map <c>sil</c>/<c>pau</c> to special tokens; attach prosody to real phonemes.</item>
///   <item>Insert prosody marks (<c>]</c>, <c>#</c>, <c>[</c>) using A1/A2/A3 + next-A2.</item>
///   <item>Apply context-dependent N mutation via <see cref="PiperPhonemeConverter.ApplyNPhonemeRules"/>.</item>
///   <item>Map multi-character tokens to PUA codepoints via <see cref="PiperPhonemeConverter.MapSequence"/>.</item>
/// </list>
/// </para>
/// </summary>
public sealed class JapanesePhonemizer : IPhonemizer
{
    private readonly IJapaneseG2PEngine _engine;

    /// <summary>
    /// Create a new <see cref="JapanesePhonemizer"/> backed by the given G2P engine.
    /// </summary>
    /// <param name="engine">
    /// Japanese G2P engine that produces OpenJTalk-compatible output.
    /// </param>
    public JapanesePhonemizer(IJapaneseG2PEngine engine)
    {
        _engine = engine ?? throw new System.ArgumentNullException(nameof(engine));
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
    /// Returns <c>null</c> — Japanese models use the phoneme-ID map from config.json.
    /// </remarks>
    public Dictionary<string, int[]>? GetPhonemeIdMap() => null;

    // PostProcessIds uses the default no-op from the interface (Japanese
    // does not need inter-phoneme PAD / BOS / EOS insertion at the ID level).

    // -----------------------------------------------------------------
    // Core implementation
    // -----------------------------------------------------------------

    /// <summary>
    /// Shared implementation for both <see cref="Phonemize"/> and
    /// <see cref="PhonemizeWithProsody"/>.  Follows the exact same
    /// algorithm as Python <c>phonemize_japanese_with_prosody()</c>.
    /// </summary>
    private (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeCore(string text)
    {
        var g2p = _engine.Convert(text);
        var phonemes = g2p.Phonemes;
        var a1Arr = g2p.A1;
        var a2Arr = g2p.A2;
        var a3Arr = g2p.A3;

        int count = phonemes.Length;
        // Each phoneme may emit itself + one prosody mark (], #, or [), so ~2x capacity.
        var tokens = new List<string>(count * 2);
        var prosody = new List<ProsodyInfo?>(count * 2);

        if (a1Arr.Length != count || a2Arr.Length != count || a3Arr.Length != count)
            throw new System.InvalidOperationException(
                $"G2P result arrays have inconsistent lengths: phonemes={count}, A1={a1Arr.Length}, A2={a2Arr.Length}, A3={a3Arr.Length}");

        for (int idx = 0; idx < count; idx++)
        {
            var phoneme = phonemes[idx];

            // --- sil handling ---
            if (phoneme == "sil")
            {
                if (idx == 0)
                {
                    // BOS
                    tokens.Add("^");
                    prosody.Add(null);
                }
                else if (idx == count - 1)
                {
                    // EOS — question type determined by trailing punctuation
                    tokens.Add(PiperPhonemeConverter.GetQuestionType(text));
                    prosody.Add(null);
                }

                continue;
            }

            // --- pau handling ---
            if (phoneme == "pau")
            {
                tokens.Add("_");
                prosody.Add(null);
                continue;
            }

            // --- regular phoneme ---
            tokens.Add(phoneme);

            int a1 = a1Arr[idx];
            int a2 = a2Arr[idx];
            int a3 = a3Arr[idx];
            prosody.Add(new ProsodyInfo(a1, a2, a3));

            // Look-ahead: fetch a2 of the next phoneme for prosody marks.
            int a2Next = -1;
            if (idx < count - 1)
            {
                a2Next = a2Arr[idx + 1];
            }

            // Accent nucleus mark "]" — pitch descends (H→L).
            // Kurihara rule: a1==0 && a2_next == a2+1
            if (a1 == 0 && a2Next == a2 + 1)
            {
                tokens.Add("]");
                prosody.Add(null);
            }

            // Accent phrase boundary "#" — current mora is last in phrase.
            if (a2 == a3 && a2Next == 1)
            {
                tokens.Add("#");
                prosody.Add(null);
            }

            // Rising mark "[" — phrase head, pitch rises.
            if (a2 == 1 && a2Next == 2)
            {
                tokens.Add("[");
                prosody.Add(null);
            }
        }

        // Step 4: Apply context-dependent N phoneme rules.
        tokens = PiperPhonemeConverter.ApplyNPhonemeRules(tokens);

        // Step 5: Map multi-character tokens to single PUA codepoints.
        var mapped = PiperPhonemeConverter.MapSequence(tokens);

        // Convert IReadOnlyList<string> back to List<string> for the interface.
        var result = new List<string>(mapped.Count);
        for (int i = 0; i < mapped.Count; i++)
        {
            result.Add(mapped[i]);
        }

        return (result, prosody);
    }
}
