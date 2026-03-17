using System.Collections.ObjectModel;

namespace PiperPlus.Core.Mapping;

/// <summary>
/// Provides bidirectional mapping between OpenJTalk multi-character phoneme tokens
/// and single PUA (Private Use Area) codepoints used by the Piper TTS pipeline.
/// <para>
/// The 29 fixed entries mirror <c>FIXED_PUA_MAPPING</c> in the Python
/// <c>token_mapper.py</c> and the C++ <c>openjtalk_phonemize.cpp</c>.
/// </para>
/// </summary>
public static class OpenJTalkToPiperMapping
{
    // ----------------------------------------------------------------
    // Fixed PUA mapping table (U+E000 .. U+E01C) -- 29 entries
    // ----------------------------------------------------------------

    /// <summary>
    /// Multi-character token to single PUA character.
    /// </summary>
    public static IReadOnlyDictionary<string, char> TokenToChar { get; } =
        new Dictionary<string, char>(29)
        {
            // Long vowels
            ["a:"] = '\uE000',
            ["i:"] = '\uE001',
            ["u:"] = '\uE002',
            ["e:"] = '\uE003',
            ["o:"] = '\uE004',

            // Special consonants
            ["cl"] = '\uE005',

            // Palatalized consonants
            ["ky"] = '\uE006',
            ["kw"] = '\uE007',
            ["gy"] = '\uE008',
            ["gw"] = '\uE009',
            ["ty"] = '\uE00A',
            ["dy"] = '\uE00B',
            ["py"] = '\uE00C',
            ["by"] = '\uE00D',

            // Affricates and special sounds
            ["ch"] = '\uE00E',
            ["ts"] = '\uE00F',
            ["sh"] = '\uE010',
            ["zy"] = '\uE011',
            ["hy"] = '\uE012',

            // Palatalized nasals / liquids
            ["ny"] = '\uE013',
            ["my"] = '\uE014',
            ["ry"] = '\uE015',

            // Question type markers (Issue #204)
            ["?!"] = '\uE016',
            ["?."] = '\uE017',
            ["?~"] = '\uE018',

            // N phoneme variants (Issue #207)
            ["N_m"]      = '\uE019',
            ["N_n"]      = '\uE01A',
            ["N_ng"]     = '\uE01B',
            ["N_uvular"] = '\uE01C',
        }.AsReadOnly();

    /// <summary>
    /// PUA character back to original multi-character token.
    /// </summary>
    public static IReadOnlyDictionary<char, string> CharToToken { get; } =
        BuildReverse(TokenToChar);

    // ----------------------------------------------------------------
    // Public helpers
    // ----------------------------------------------------------------

    /// <summary>
    /// Convert a single token.
    /// <list type="bullet">
    ///   <item>Single-character tokens are returned unchanged.</item>
    ///   <item>Multi-character tokens found in <see cref="TokenToChar"/> are replaced
    ///         with the corresponding PUA character as a string.</item>
    ///   <item>Multi-character tokens <em>not</em> in the fixed table are returned
    ///         unchanged (no dynamic allocation in Phase 2).</item>
    /// </list>
    /// </summary>
    public static string MapToken(string token)
    {
        if (token.Length <= 1)
        {
            return token;
        }

        return TokenToChar.TryGetValue(token, out var pua)
            ? pua.ToString()
            : token;
    }

    /// <summary>
    /// Convert every token in <paramref name="tokens"/> using <see cref="MapToken"/>.
    /// </summary>
    public static IReadOnlyList<string> MapSequence(IReadOnlyList<string> tokens)
    {
        var result = new string[tokens.Count];
        for (var i = 0; i < tokens.Count; i++)
        {
            result[i] = MapToken(tokens[i]);
        }

        return result;
    }

    // ----------------------------------------------------------------
    // Internal helpers
    // ----------------------------------------------------------------

    private static ReadOnlyDictionary<char, string> BuildReverse(
        IReadOnlyDictionary<string, char> forward)
    {
        var reverse = new Dictionary<char, string>(forward.Count);
        foreach (var (token, ch) in forward)
        {
            reverse[ch] = token;
        }

        return new ReadOnlyDictionary<char, string>(reverse);
    }
}
