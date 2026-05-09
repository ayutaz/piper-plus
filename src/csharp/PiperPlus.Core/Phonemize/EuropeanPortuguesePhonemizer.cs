using System;
using System.Collections.Generic;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// European Portuguese (pt-PT) phonemizer.
/// Mirror of Python <c>_apply_eu_postprocessing</c> in
/// <c>src/python/g2p/piper_plus_g2p/portuguese.py</c>.
/// Reuses the BR <see cref="PortuguesePhonemizer"/> pipeline and rewrites
/// the 5 BR↔EU contrasts in-place. See
/// <c>docs/spec/pt-dialect-contract.toml</c> (spec_version 2,
/// <c>[implementation.differences]</c>) for the typological references
/// (Cruz-Ferreira 1995; Mateus &amp; d'Andrade 2000).
/// </summary>
public sealed class EuropeanPortuguesePhonemizer : IPhonemizer
{
    private readonly PortuguesePhonemizer _br;

    // PUA-mapped tokens for BR's tʃ / dʒ affricates (see token_mapper).
    private const string PuaTch = "";
    private const string PuaDzh = "";

    private static readonly HashSet<char> EuVowels = new(
        new[] { 'a', 'e', 'i', 'o', 'u', 'ɛ', 'ɔ', 'ã', 'ẽ', 'ĩ', 'õ', 'ũ', 'ɨ' });

    private static readonly HashSet<char> EuConsonants = new(
        new[] { 'b', 'd', 'f', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't',
                'v', 'w', 'z', 'ɡ', 'ɲ', 'ɾ', 'ʁ', 'ʃ', 'ʎ', 'ʒ', 'ʔ',
                'h', 'ɫ' });

    private static readonly HashSet<string> Punctuation =
        [".", ",", ";", ":", "!", "?", "¡", "¿", "—", "–", "…"];

    /// <summary>Construct the EU phonemizer with the same G2P engine as BR.</summary>
    public EuropeanPortuguesePhonemizer(IPortugueseG2PEngine engine)
    {
        _br = new PortuguesePhonemizer(engine ?? throw new ArgumentNullException(nameof(engine)));
    }

    /// <inheritdoc />
    public List<string> Phonemize(string text)
    {
        var (tokens, _) = _br.PhonemizeWithProsody(text);
        return ApplyEuPostprocessing(tokens);
    }

    /// <inheritdoc />
    public (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeWithProsody(string text)
    {
        var (tokens, prosody) = _br.PhonemizeWithProsody(text);
        var euTokens = ApplyEuPostprocessing(tokens);
        return (euTokens, prosody);
    }

    /// <inheritdoc />
    public Dictionary<string, int[]>? GetPhonemeIdMap() => _br.GetPhonemeIdMap();

    /// <inheritdoc />
    public (List<int> Ids, List<ProsodyInfo?> Prosody) PostProcessIds(
        List<int> phonemeIds,
        List<ProsodyInfo?> prosodyFeatures,
        Dictionary<string, int[]> phonemeIdMap)
    {
        return _br.PostProcessIds(phonemeIds, prosodyFeatures, phonemeIdMap);
    }

    // -----------------------------------------------------------------
    // EU post-processing — five passes (mirror of Python).
    // -----------------------------------------------------------------

    private static char FirstChar(string s) => string.IsNullOrEmpty(s) ? '\0' : s[0];
    private static bool StartsCons(string s) => EuConsonants.Contains(FirstChar(s));
    private static bool StartsVowel(string s) => EuVowels.Contains(FirstChar(s));

    private static bool NextNonSpaceStartsVowel(List<string> tokens, int idx)
    {
        for (int j = idx + 1; j < tokens.Count; j++)
        {
            if (tokens[j] == " ")
            {
                continue;
            }
            return StartsVowel(tokens[j]);
        }
        return false;
    }

    internal static List<string> ApplyEuPostprocessing(List<string> tokensIn)
    {
        var tokens = new List<string>(tokensIn);
        ApplyPassPalatalisationAndCentralisation(tokens);
        ApplyPassCodaSibilants(tokens);
        ApplyPassCodaW(tokens);
        ApplyPassRhoticH(tokens);
        return tokens;
    }

    // Pass 1: undo BR t/d palatalisation + final-e centralisation.
    private static void ApplyPassPalatalisationAndCentralisation(List<string> tokens)
    {
        int n = tokens.Count;
        for (int i = 0; i < n; i++)
        {
            if (tokens[i] != "i") continue;
            string nxt = (i + 1 < n) ? tokens[i + 1] : "";
            bool isFinal = string.IsNullOrEmpty(nxt) || nxt == " " || Punctuation.Contains(nxt);
            if (!isFinal) continue;
            if (i >= 1 && tokens[i - 1] == PuaTch)
            {
                tokens[i - 1] = "t";
                tokens[i] = "ɨ";
                continue;
            }
            if (i >= 1 && tokens[i - 1] == PuaDzh)
            {
                tokens[i - 1] = "d";
                tokens[i] = "ɨ";
                continue;
            }
            if (i >= 1 && StartsCons(tokens[i - 1]))
            {
                tokens[i] = "ɨ";
            }
        }
    }

    // Pass 2: coda /s/, /z/.
    private static void ApplyPassCodaSibilants(List<string> tokens)
    {
        int n = tokens.Count;
        for (int i = 0; i < n; i++)
        {
            if (tokens[i] != "s" && tokens[i] != "z") continue;
            string nxt = (i + 1 < n) ? tokens[i + 1] : "";
            bool isWordEnd = string.IsNullOrEmpty(nxt) || nxt == " " || Punctuation.Contains(nxt);
            if (isWordEnd)
            {
                if (NextNonSpaceStartsVowel(tokens, i))
                {
                    tokens[i] = "ʒ";
                    continue;
                }
                tokens[i] = (tokens[i] == "s") ? "ʃ" : "ʒ";
            }
            else if (StartsCons(nxt) && !StartsVowel(nxt))
            {
                tokens[i] = (tokens[i] == "s") ? "ʃ" : "ʒ";
            }
        }
    }

    // Pass 3: coda /w/ → /ɫ/.
    private static void ApplyPassCodaW(List<string> tokens)
    {
        int n = tokens.Count;
        for (int i = 0; i < n; i++)
        {
            if (tokens[i] != "w" || i == 0) continue;
            if (!StartsVowel(tokens[i - 1])) continue;
            string nxt = (i + 1 < n) ? tokens[i + 1] : "";
            bool isCoda =
                string.IsNullOrEmpty(nxt) || nxt == " " || Punctuation.Contains(nxt) ||
                (StartsCons(nxt) && !StartsVowel(nxt));
            if (isCoda)
            {
                tokens[i] = "ɫ";
            }
        }
    }

    // Pass 4: h → ʁ.
    private static void ApplyPassRhoticH(List<string> tokens)
    {
        int n = tokens.Count;
        for (int i = 0; i < n; i++)
        {
            if (tokens[i] == "h")
            {
                tokens[i] = "ʁ";
            }
        }
    }
}
