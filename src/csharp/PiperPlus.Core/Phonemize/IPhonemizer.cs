using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Prosody information attached to each phoneme token.
/// The meaning of each field depends on the language:
/// <list type="table">
///   <listheader>
///     <term>Field</term>
///     <description>Japanese / English</description>
///   </listheader>
///   <item>
///     <term>A1</term>
///     <description>
///       Japanese: relative position from accent nucleus.
///       English: fixed at 0.
///     </description>
///   </item>
///   <item>
///     <term>A2</term>
///     <description>
///       Japanese: mora position in accent phrase (1-based).
///       English: stress level (0=none, 1=secondary, 2=primary).
///     </description>
///   </item>
///   <item>
///     <term>A3</term>
///     <description>
///       Japanese: total morae in accent phrase.
///       English: number of phonemes in the word.
///     </description>
///   </item>
/// </list>
/// </summary>
/// <param name="A1">Language-dependent prosody dimension 1.</param>
/// <param name="A2">Language-dependent prosody dimension 2.</param>
/// <param name="A3">Language-dependent prosody dimension 3.</param>
public record struct ProsodyInfo(int A1, int A2, int A3);

/// <summary>
/// Language-agnostic phonemizer contract.
/// <para>
/// Mirrors the Python <c>Phonemizer</c> ABC defined in
/// <c>piper_train/phonemize/base.py</c>. Each language implements
/// this interface and is resolved through the phonemizer registry.
/// </para>
/// </summary>
public interface IPhonemizer
{
    /// <summary>
    /// Convert <paramref name="text"/> to a list of phoneme tokens.
    /// </summary>
    /// <param name="text">Input text in the target language.</param>
    /// <returns>Ordered phoneme token strings.</returns>
    List<string> Phonemize(string text);

    /// <summary>
    /// Convert <paramref name="text"/> to phoneme tokens together with
    /// per-token prosody information (A1/A2/A3).
    /// </summary>
    /// <param name="text">Input text in the target language.</param>
    /// <returns>
    /// A tuple of phoneme tokens and corresponding <see cref="ProsodyInfo"/>
    /// values. Entries may be <c>null</c> when prosody is unavailable for a
    /// given token (e.g. punctuation, special symbols).
    /// </returns>
    (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeWithProsody(string text);

    /// <summary>
    /// Return a language-specific phoneme-to-ID mapping, or <c>null</c> to
    /// fall back to the map provided by <c>config.json</c>.
    /// </summary>
    /// <returns>
    /// A dictionary mapping phoneme strings to integer ID arrays, or
    /// <c>null</c> when the config-provided map should be used.
    /// </returns>
    Dictionary<string, int[]>? GetPhonemeIdMap();

    /// <summary>
    /// Post-process phoneme IDs after token-to-ID conversion.
    /// <para>
    /// Override this to inject BOS/EOS tokens, inter-phoneme padding, or
    /// any other language-specific ID-level transformations. The default
    /// implementation returns the inputs unchanged (no-op).
    /// </para>
    /// </summary>
    /// <param name="phonemeIds">Phoneme IDs produced by the token mapper.</param>
    /// <param name="prosodyFeatures">Per-ID prosody values (may contain <c>null</c> entries).</param>
    /// <param name="phonemeIdMap">The active phoneme-to-ID map (from the language or config).</param>
    /// <returns>The (possibly modified) phoneme IDs and prosody features.</returns>
    (List<int> Ids, List<ProsodyInfo?> Prosody) PostProcessIds(
        List<int> phonemeIds,
        List<ProsodyInfo?> prosodyFeatures,
        Dictionary<string, int[]> phonemeIdMap)
    {
        return (phonemeIds, prosodyFeatures);
    }
}
