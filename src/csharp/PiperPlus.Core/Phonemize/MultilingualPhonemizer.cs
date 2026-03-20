using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Phonemizer that handles code-switching between N languages.
/// <para>
/// Segments the input text by language using Unicode ranges, delegates to
/// language-specific phonemizers, and concatenates results in a unified
/// phoneme space.
/// </para>
/// <para>
/// Port of the Python <c>MultilingualPhonemizer</c> in
/// <c>piper_train/phonemize/multilingual.py</c>.
/// </para>
/// <para>
/// <b>Thread safety:</b> A single instance may be used from multiple
/// threads concurrently.  The EOS token captured during
/// <see cref="PhonemizeWithProsody"/> is stored in thread-local storage
/// so that each thread's subsequent <see cref="PostProcessIds"/> call
/// sees the correct value.
/// </para>
/// </summary>
public sealed class MultilingualPhonemizer : IPhonemizer
{
    private readonly Dictionary<string, IPhonemizer> _phonemizers;
    private readonly UnicodeLanguageDetector _detector;

    /// <summary>
    /// Per-thread EOS token captured during <see cref="PhonemizeWithProsody"/>
    /// and read by <see cref="PostProcessIds"/> to determine the correct EOS ID.
    /// Thread-local storage ensures concurrent callers do not interfere.
    /// </summary>
    private readonly ThreadLocal<string> _lastEos = new(() => "$");

    // -----------------------------------------------------------------
    // BOS / EOS token sets
    // -----------------------------------------------------------------

    /// <summary>
    /// Tokens that are stripped from individual language segments.
    /// Includes BOS (^), standard EOS ($, ?), and PUA-mapped question
    /// markers (?!, ?., ?~).
    /// </summary>
    private static readonly HashSet<string> s_bosEosTokens = new()
    {
        "^",        // BOS
        "$",        // EOS (standard)
        "?",        // EOS (question)
        "\uE016",   // ?! (PUA)
        "\uE017",   // ?. (PUA)
        "\uE018",   // ?~ (PUA)
    };

    /// <summary>
    /// Subset of <see cref="s_bosEosTokens"/> that are EOS-like tokens.
    /// Used to track the last EOS seen across segments.
    /// </summary>
    private static readonly HashSet<string> s_eosTokens = new()
    {
        "$",        // EOS (standard)
        "?",        // EOS (question)
        "\uE016",   // ?! (PUA)
        "\uE017",   // ?. (PUA)
        "\uE018",   // ?~ (PUA)
    };

    /// <summary>
    /// Create a new <see cref="MultilingualPhonemizer"/>.
    /// </summary>
    /// <param name="phonemizers">
    /// Map of language code to the corresponding <see cref="IPhonemizer"/>
    /// instance (e.g. <c>{ "ja" => JapanesePhonemizer, "en" => EnglishPhonemizer }</c>).
    /// </param>
    /// <param name="defaultLatinLanguage">
    /// Language code for Latin-script characters (default: "en"). If not
    /// present in <paramref name="phonemizers"/>, falls back to the first
    /// language in the dictionary.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="phonemizers"/> is null.</exception>
    /// <exception cref="ArgumentException"><paramref name="phonemizers"/> is empty.</exception>
    public MultilingualPhonemizer(
        Dictionary<string, IPhonemizer> phonemizers,
        string defaultLatinLanguage = "en")
    {
        _phonemizers = phonemizers ?? throw new ArgumentNullException(nameof(phonemizers));
        if (_phonemizers.Count == 0)
            throw new ArgumentException("At least one phonemizer is required.", nameof(phonemizers));

        // Validate that defaultLatinLanguage is one of the supported
        // languages. If not, fall back to the first language.
        if (!_phonemizers.ContainsKey(defaultLatinLanguage))
        {
            // Pick the first key deterministically
            using var enumerator = _phonemizers.Keys.GetEnumerator();
            enumerator.MoveNext();
            defaultLatinLanguage = enumerator.Current;
        }

        _detector = new UnicodeLanguageDetector(
            _phonemizers.Keys.ToList(), defaultLatinLanguage);
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
    /// Returns <c>null</c> --- multilingual models use the phoneme-ID map
    /// from <c>config.json</c>.
    /// </remarks>
    public Dictionary<string, int[]>? GetPhonemeIdMap() => null;

    /// <inheritdoc />
    /// <remarks>
    /// Uses the dynamic EOS token (<see cref="_lastEos"/>) captured on the
    /// current thread during the most recent <see cref="PhonemizeWithProsody"/>
    /// call. Falls back to <c>"$"</c> if the captured token is not in the
    /// phoneme-ID map.
    /// <para>
    /// The underlying algorithm is the standard espeak-ng BOS + PAD +
    /// inter-pad + EOS scheme (same as
    /// <see cref="PiperPhonemeConverter.EspeakPostProcessIds"/> but with
    /// dynamic EOS lookup).
    /// </para>
    /// </remarks>
    public (List<int> Ids, List<ProsodyInfo?> Prosody) PostProcessIds(
        List<int> phonemeIds,
        List<ProsodyInfo?> prosodyFeatures,
        Dictionary<string, int[]> phonemeIdMap)
    {
        // Resolve special token IDs from the phoneme-ID map.
        int[] padIds = phonemeIdMap.TryGetValue("_", out int[]? padArr) ? padArr : [0];
        phonemeIdMap.TryGetValue("^", out int[]? bosIds);

        // Try _lastEos (thread-local) first, fall back to "$"
        if (!phonemeIdMap.TryGetValue(_lastEos.Value!, out int[]? eosIds))
            phonemeIdMap.TryGetValue("$", out eosIds);

        // Step 1: Insert PAD after every phoneme ID.
        var paddedIds = new List<int>(phonemeIds.Count * 2);
        var paddedProsody = new List<ProsodyInfo?>(phonemeIds.Count * 2);

        for (int i = 0; i < phonemeIds.Count; i++)
        {
            paddedIds.Add(phonemeIds[i]);
            paddedProsody.Add(prosodyFeatures[i]);

            paddedIds.AddRange(padIds);
            for (int j = 0; j < padIds.Length; j++)
            {
                paddedProsody.Add(null);
            }
        }

        // Step 2: Wrap with BOS + PAD ... EOS.
        if (bosIds is not null)
        {
            var withBos = new List<int>(bosIds.Length + 1 + paddedIds.Count);
            withBos.AddRange(bosIds);
            withBos.Add(padIds[0]);
            withBos.AddRange(paddedIds);

            var withBosProsody = new List<ProsodyInfo?>(bosIds.Length + 1 + paddedProsody.Count);
            for (int i = 0; i < bosIds.Length + 1; i++)
            {
                withBosProsody.Add(null);
            }
            withBosProsody.AddRange(paddedProsody);

            paddedIds = withBos;
            paddedProsody = withBosProsody;
        }

        if (eosIds is not null)
        {
            paddedIds.AddRange(eosIds);
            for (int i = 0; i < eosIds.Length; i++)
            {
                paddedProsody.Add(null);
            }
        }

        return (paddedIds, paddedProsody);
    }

    // -----------------------------------------------------------------
    // Core implementation
    // -----------------------------------------------------------------

    /// <summary>
    /// Shared implementation for <see cref="Phonemize"/> and
    /// <see cref="PhonemizeWithProsody"/>. Segments the text by language,
    /// delegates to per-language phonemizers, strips BOS/EOS from each
    /// segment, and concatenates the results.
    /// </summary>
    private (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeCore(string text)
    {
        var segments = _detector.SegmentText(text);
        if (segments.Count == 0)
            return (new List<string>(), new List<ProsodyInfo?>());

        var allPhonemes = new List<string>(segments.Count * 50);
        var allProsody = new List<ProsodyInfo?>(segments.Count * 50);
        string lastEos = "$";

        foreach (var (lang, segmentText) in segments)
        {
            if (!_phonemizers.TryGetValue(lang, out IPhonemizer? phonemizer))
                continue;

            var (phonemes, prosody) = phonemizer.PhonemizeWithProsody(segmentText);

            // Strip BOS/EOS from individual segments.
            // Track the last EOS token seen (for PostProcessIds).
            for (int i = 0; i < phonemes.Count; i++)
            {
                string ph = phonemes[i];
                if (s_bosEosTokens.Contains(ph))
                {
                    if (s_eosTokens.Contains(ph))
                        lastEos = ph;
                    continue;
                }
                allPhonemes.Add(ph);
                allProsody.Add(prosody[i]);
            }
        }

        _lastEos.Value = lastEos;
        return (allPhonemes, allProsody);
    }
}
