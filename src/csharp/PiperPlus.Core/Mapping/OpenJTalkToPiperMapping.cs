using System.Collections.ObjectModel;

namespace PiperPlus.Core.Mapping;

/// <summary>
/// Provides bidirectional mapping between multi-character phoneme tokens
/// and single PUA (Private Use Area) codepoints used by the Piper TTS pipeline.
/// <para>
/// The 96 fixed entries mirror <c>FIXED_PUA_MAPPING</c> in the Python
/// <c>token_mapper.py</c> and the C++ phonemizer implementations.
/// </para>
/// </summary>
public static class OpenJTalkToPiperMapping
{
    // ----------------------------------------------------------------
    // Fixed PUA mapping table (U+E000 .. U+E064) -- 99 entries
    // ----------------------------------------------------------------

    /// <summary>
    /// Multi-character token to single PUA character.
    /// </summary>
    public static IReadOnlyDictionary<string, char> TokenToChar { get; } =
        new Dictionary<string, char>(99)
        {
            // =============================================================
            // Japanese (JA) — U+E000–U+E01C (29 entries)
            // =============================================================

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
            ["N_m"] = '\uE019',
            ["N_n"] = '\uE01A',
            ["N_ng"] = '\uE01B',
            ["N_uvular"] = '\uE01C',

            // =============================================================
            // Multilingual shared — U+E01D–U+E01E (2 entries)
            // =============================================================
            ["rr"] = '\uE01D',       // Spanish trill r
            ["y_vowel"] = '\uE01E',  // Close front rounded vowel [y] (FR/ZH)
            // 0xE01F reserved

            // =============================================================
            // Chinese (ZH) — U+E020–U+E04A (43 entries)
            // =============================================================

            // --- Initials (aspirated/affricate) ---
            ["p\u02B0"] = '\uE020',          // pʰ  aspirated bilabial (pinyin p)
            ["t\u02B0"] = '\uE021',          // tʰ  aspirated alveolar (pinyin t)
            ["k\u02B0"] = '\uE022',          // kʰ  aspirated velar (pinyin k)
            ["t\u0255"] = '\uE023',          // tɕ  alveolo-palatal affricate (pinyin j)
            ["t\u0255\u02B0"] = '\uE024',    // tɕʰ aspirated alveolo-palatal (pinyin q)
            ["t\u0282"] = '\uE025',          // tʂ  retroflex affricate (pinyin zh)
            ["t\u0282\u02B0"] = '\uE026',    // tʂʰ aspirated retroflex (pinyin ch)
            ["ts\u02B0"] = '\uE027',         // tsʰ aspirated alveolar affricate (pinyin c)

            // --- Diphthongs ---
            ["a\u026A"] = '\uE028',          // aɪ  (pinyin ai)
            ["e\u026A"] = '\uE029',          // eɪ  (pinyin ei)
            ["a\u028A"] = '\uE02A',          // aʊ  (pinyin ao)
            ["o\u028A"] = '\uE02B',          // oʊ  (pinyin ou)

            // --- Nasal finals ---
            ["an"] = '\uE02C',               // an  (pinyin an)
            ["\u0259n"] = '\uE02D',          // ən  (pinyin en)
            ["a\u014B"] = '\uE02E',          // aŋ  (pinyin ang)
            ["\u0259\u014B"] = '\uE02F',     // əŋ  (pinyin eng)
            ["u\u014B"] = '\uE030',          // uŋ  (pinyin ong)

            // --- i-compound finals (齐齿呼) ---
            ["ia"] = '\uE031',               // ia  (pinyin ia/ya)
            ["i\u025B"] = '\uE032',          // iɛ  (pinyin ie/ye)
            ["iou"] = '\uE033',              // iou (pinyin iu/you)
            ["ia\u028A"] = '\uE034',         // iaʊ (pinyin iao/yao)
            ["i\u025Bn"] = '\uE035',         // iɛn (pinyin ian/yan)
            ["in"] = '\uE036',               // in  (pinyin in/yin)
            ["ia\u014B"] = '\uE037',         // iaŋ (pinyin iang/yang)
            ["i\u014B"] = '\uE038',          // iŋ  (pinyin ing/ying)
            ["iu\u014B"] = '\uE039',         // iuŋ (pinyin iong/yong)

            // --- u-compound finals (合口呼) ---
            ["ua"] = '\uE03A',               // ua  (pinyin ua/wa)
            ["uo"] = '\uE03B',               // uo  (pinyin uo/wo)
            ["ua\u026A"] = '\uE03C',         // uaɪ (pinyin uai/wai)
            ["ue\u026A"] = '\uE03D',         // ueɪ (pinyin ui/wei)
            ["uan"] = '\uE03E',              // uan (pinyin uan/wan)
            ["u\u0259n"] = '\uE03F',         // uən (pinyin un/wen)
            ["ua\u014B"] = '\uE040',         // uaŋ (pinyin uang/wang)
            ["u\u0259\u014B"] = '\uE041',    // uəŋ (pinyin ueng/weng)

            // --- ü-compound finals (撮口呼) ---
            ["y\u025B"] = '\uE042',          // yɛ  (pinyin üe/yue)
            ["y\u025Bn"] = '\uE043',         // yɛn (pinyin üan/yuan)
            ["yn"] = '\uE044',               // yn  (pinyin ün/yun)

            // --- Syllabic consonants ---
            ["\u027B\u0329"] = '\uE045',     // ɻ̩  syllabic retroflex (zhi/chi/shi/ri)

            // --- Tone markers ---
            ["tone1"] = '\uE046',            // 阴平 (high level)
            ["tone2"] = '\uE047',            // 阳平 (rising)
            ["tone3"] = '\uE048',            // 上声 (dipping)
            ["tone4"] = '\uE049',            // 去声 (falling)
            ["tone5"] = '\uE04A',            // 轻声 (neutral)

            // =============================================================
            // Korean (KO) — U+E04B–U+E052 (8 entries)
            // =============================================================

            // --- Tense consonants (fortis / 경음) ---
            ["p\u0348"] = '\uE04B',          // p͈  tense bilabial (ㅃ)
            ["t\u0348"] = '\uE04C',          // t͈  tense alveolar (ㄸ)
            ["k\u0348"] = '\uE04D',          // k͈  tense velar (ㄲ)
            ["s\u0348"] = '\uE04E',          // s͈  tense sibilant (ㅆ)
            ["t\u0348\u0255"] = '\uE04F',    // t͈ɕ tense alveolo-palatal (ㅉ)

            // --- Unreleased finals (내파음) ---
            ["k\u031A"] = '\uE050',          // k̚  unreleased velar
            ["t\u031A"] = '\uE051',          // t̚  unreleased alveolar
            ["p\u031A"] = '\uE052',          // p̚  unreleased bilabial
            // 0xE053 reserved

            // =============================================================
            // Spanish (ES) / Portuguese (PT) — U+E054–U+E055 (2 entries)
            // =============================================================
            ["t\u0283"] = '\uE054',          // tʃ  voiceless postalveolar affricate
            ["d\u0292"] = '\uE055',          // dʒ  voiced postalveolar affricate

            // =============================================================
            // French (FR) — U+E056–U+E058 (3 entries)
            // =============================================================
            ["\u025B\u0303"] = '\uE056',     // ɛ̃  nasal open-mid front unrounded
            ["\u0251\u0303"] = '\uE057',     // ɑ̃  nasal open back unrounded
            ["\u0254\u0303"] = '\uE058',     // ɔ̃  nasal open-mid back rounded

            // =============================================================
            // Swedish (SV) — U+E059–U+E061 (9 entries)
            // =============================================================

            // --- Long vowels (Complementary Quantity) ---
            ["i\u02D0"] = '\uE059',          // iː  close front unrounded long
            ["y\u02D0"] = '\uE05A',          // yː  close front rounded long
            ["e\u02D0"] = '\uE05B',          // eː  close-mid front unrounded long
            ["\u025B\u02D0"] = '\uE05C',     // ɛː  open-mid front unrounded long
            ["\u00F8\u02D0"] = '\uE05D',     // øː  close-mid front rounded long
            ["\u0251\u02D0"] = '\uE05E',     // ɑː  open back unrounded long
            ["o\u02D0"] = '\uE05F',          // oː  close-mid back rounded long
            ["u\u02D0"] = '\uE060',          // uː  close back rounded long
            ["\u0289\u02D0"] = '\uE061',     // ʉː  close central rounded long

            // =============================================================
            // Additional multi-codepoint diphthongs / nasal vowels (PUA v2) — 3 entries
            // =============================================================
            ["ɔɪ"] = '',     // ɔɪ  English diphthong (OY)
            ["œ̃"] = '',     // œ̃   French nasal open-mid front rounded vowel
            ["ɐ̃"] = '',     // ɐ̃   Portuguese nasal near-open central vowel
        }.AsReadOnly();

    /// <summary>
    /// PUA character back to original multi-character token.
    /// </summary>
    public static IReadOnlyDictionary<char, string> CharToToken { get; } =
        BuildReverse(TokenToChar);

    /// <summary>Pre-computed char→string cache to avoid per-call ToString() allocations.</summary>
    private static readonly Dictionary<char, string> s_charToString = BuildCharToString();

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
            ? s_charToString[pua]
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

    private static Dictionary<char, string> BuildCharToString()
    {
        var dict = new Dictionary<char, string>(TokenToChar.Count);
        foreach (var (_, ch) in TokenToChar)
        {
            dict[ch] = ch.ToString();
        }
        return dict;
    }
}
