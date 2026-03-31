using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace PiperPlus.Core.Phonemize;

/// <summary>
/// Full rule-based Swedish G2P engine implementing <see cref="ISwedishG2PEngine"/>.
/// <para>
/// Pipeline (per word):
/// <list type="number">
///   <item>Stage 1: Normalization (lowercase, NFC, tokenize)</item>
///   <item>Stage 2: Loanword suffix detection (-tion/-sion/-age etc.)</item>
///   <item>Stage 3-4: Consonant conversion (trigraphs, digraphs, soft/hard k/g) + vowel length</item>
///   <item>Stage 5: Retroflex assimilation (r+C -> retroflex, 3-state machine)</item>
///   <item>Stage 6: Stress detection + marker insertion</item>
/// </list>
/// </para>
/// <para>
/// Matches the Python <c>phonemize_swedish()</c> in
/// <c>piper_train/phonemize/swedish.py</c> exactly.
/// </para>
/// </summary>
public sealed class SwedishG2PEngine : ISwedishG2PEngine
{
    // =================================================================
    // Character classification
    // =================================================================

    private static readonly HashSet<char> FrontVowels =
        ['e', 'i', 'y', '\u00e4', '\u00f6']; // e i y ä ö

    private static readonly HashSet<char> BackVowels =
        ['a', 'o', 'u', '\u00e5']; // a o u å

    private static readonly HashSet<char> AllVowels;

    private static readonly HashSet<char> Consonants =
        ['b', 'c', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'm',
         'n', 'p', 'q', 'r', 's', 't', 'v', 'w', 'x', 'z'];

    private static readonly HashSet<char> Punctuation =
        ['.', ',', ';', ':', '!', '?'];

    static SwedishG2PEngine()
    {
        AllVowels = new HashSet<char>(FrontVowels);
        foreach (char c in BackVowels)
            AllVowels.Add(c);
    }

    // =================================================================
    // Default consonant -> IPA (single-letter fallback)
    // =================================================================

    private static readonly Dictionary<char, string> ConsonantDefault = new()
    {
        ['b'] = "b",
        ['c'] = "k",
        ['d'] = "d",
        ['f'] = "f",
        ['g'] = "\u0261",   // ɡ (IPA U+0261)
        ['h'] = "h",
        ['j'] = "j",
        ['k'] = "k",
        ['l'] = "l",
        ['m'] = "m",
        ['n'] = "n",
        ['p'] = "p",
        ['q'] = "k",
        ['r'] = "r",
        ['s'] = "s",
        ['t'] = "t",
        ['v'] = "v",
        ['w'] = "v",
        ['x'] = "ks",
        ['z'] = "s",
    };

    // =================================================================
    // Exception word lists (match Python exactly)
    // =================================================================

    private static readonly HashSet<string> HardKWords =
    [
        "kille", "kissa", "kiosk", "kebab", "kennel", "keps", "ketchup",
        "kick", "kilt", "kimono", "kitsch", "kibbutz", "kiwi", "kilo",
        "kex", "kent", "kerna", "keso", "kikare", "kines", "kinesisk",
        "leker", "leken", "lekerska", "steker", "steket", "söker", "söket",
        "tänker", "tänket", "dyker", "dyket", "ryker", "röker", "röket",
        "smeker", "läker", "läket", "märker", "märket", "räcker", "väcker",
        "viker", "stryker", "sjunker", "sticker",
        "pojke", "fröken", "onkel", "sockel", "socker", "ocker", "märke",
        "mörker", "tecken", "vacker", "naken", "säker", "enkel", "paket",
        "raket", "staket", "silke", "vinkel", "skelett",
        "ficka", "dricka", "docka", "backe", "flicka", "bricka", "trycke",
        "skicka", "rike", "kirke",
    ];

    private static readonly HashSet<string> HardKStems =
    [
        "lek", "stek", "sök", "tänk", "dyk", "ryk", "rök", "smek",
        "läk", "märk", "räck", "väck", "vik", "stryk", "sjunk", "stick",
        "back", "block", "trick", "tryck", "skick", "flick", "brick",
        "drick", "dock", "fick", "sick", "tack", "sack", "pack", "lock",
        "sock", "rock",
    ];

    private static readonly HashSet<string> HardGWords =
    [
        "bagel", "bageri", "bygel", "bygge", "båge", "dager", "flygel",
        "gecko", "hage", "hagel", "hunger", "lager", "läge", "läger",
        "mage", "nagel", "regel", "segel", "seger", "stege", "tagel",
        "tegel", "tiger", "tygel", "finger", "ängel", "fågel", "spegel",
        "fogel", "duger", "flyger", "ligger", "ljuger", "lägger", "stiger",
        "suger", "tigger", "väger", "äger", "ger",
        "agera", "delegera", "reagera", "segregera", "tangera", "engagera",
        "arrangera", "ignorera", "navigera", "negera", "intrigera",
        "ge", "gel", "berg", "borg",
    ];

    private static readonly HashSet<string> HardGStems =
    [
        "lig", "stig", "sug", "tig", "väg", "äg", "flyg", "ljug",
        "lägg", "dug", "drag", "lag", "dag", "mag", "nag", "bag",
        "byg", "tag", "seg", "vag", "reg", "berg", "borg",
    ];

    private static readonly HashSet<string> OLongAsOo =
    [
        "son", "mor", "bror", "lov", "dom", "ton", "zon", "fon",
        "ion", "ko", "lo", "ro", "tro", "bo", "god", "jord", "ord",
        "kol", "pol", "kontroll", "roll", "mol", "fot", "rot", "blod",
        "flod", "mod", "nod", "rod", "tog",
    ];

    private static readonly HashSet<string> FinalMShortWords =
    [
        "hem", "rum", "fem", "lem", "kam", "dam", "ham", "lam",
        "ram", "stam", "tom", "som", "dom", "dum", "gum", "glöm",
        "dröm", "ström",
    ];

    private static readonly HashSet<string> FunctionWords =
    [
        "jag", "du", "han", "hon", "vi", "de", "dem", "den", "det",
        "sig", "sin", "min", "din", "av", "i", "på", "för", "med",
        "om", "till", "från", "hos", "ur", "och", "men", "att", "som",
        "när", "var", "en", "ett", "är", "har", "kan", "ska", "vill",
        "inte",
    ];

    private static readonly HashSet<string> SkBackVowelExceptions =
    [
        "människa", "marskalk",
    ];

    private static readonly HashSet<string> ChExceptionsK =
    [
        "kristus", "krist", "kron", "kronik", "och",
    ];

    private static readonly HashSet<string> AgeNativeWords =
    [
        "bage", "lage", "sage", "dage", "mage", "hage", "tage",
        "klage", "frage", "plage", "drage",
    ];

    // =================================================================
    // Vowel mappings (Complementary Quantity)
    // =================================================================

    private static readonly Dictionary<char, string> LongVowelMap = new()
    {
        ['a'] = "\u0251\u02d0",       // ɑː
        ['e'] = "e\u02d0",            // eː
        ['i'] = "i\u02d0",            // iː
        ['o'] = "u\u02d0",            // uː (default; /oː/ from OLongAsOo)
        ['u'] = "\u0289\u02d0",       // ʉː
        ['y'] = "y\u02d0",            // yː
        ['\u00e5'] = "o\u02d0",       // å → oː
        ['\u00e4'] = "\u025b\u02d0",  // ä → ɛː
        ['\u00f6'] = "\u00f8\u02d0",  // ö → øː
    };

    private static readonly Dictionary<char, string> ShortVowelMap = new()
    {
        ['a'] = "a",
        ['e'] = "\u025b",             // ɛ
        ['i'] = "\u026a",             // ɪ
        ['o'] = "\u0254",             // ɔ
        ['u'] = "\u0275",             // ɵ
        ['y'] = "\u028f",             // ʏ
        ['\u00e5'] = "\u0254",        // å → ɔ
        ['\u00e4'] = "\u025b",        // ä → ɛ
        ['\u00f6'] = "\u0153",        // ö → œ
    };

    // =================================================================
    // Retroflex assimilation
    // =================================================================

    private static readonly Dictionary<string, string> RetroflexMap = new()
    {
        ["t"] = "\u0288",   // ʈ
        ["d"] = "\u0256",   // ɖ
        ["s"] = "\u0282",   // ʂ
        ["n"] = "\u0273",   // ɳ
        ["l"] = "\u026d",   // ɭ
    };

    private static readonly HashSet<string> PropagatingRetroflexes =
    [
        "\u0288", "\u0256", "\u0282", "\u0273",  // ʈ ɖ ʂ ɳ
    ];

    // =================================================================
    // Stress detection
    // =================================================================

    private static readonly string[] UnstressedPrefixes =
        ["för", "be", "ge", "er", "an"];

    private static readonly string[] StressAttractingSuffixes =
    [
        "ssion", "tion", "sion", "itet", "eri", "era", "ist",
        "ör", "ment", "ans", "ens", "ell", "ent", "ant", "ik", "ur", "al", "ös",
    ];

    // =================================================================
    // Loanword suffix rules
    // =================================================================

    private static readonly (string Suffix, string[] Phonemes)[] LoanwordSuffixRules =
    [
        ("ssion", ["\u0267", "u\u02d0", "n"]),              // ɧ uː n
        ("tion",  ["\u0267", "u\u02d0", "n"]),              // ɧ uː n
        ("sion",  ["\u0267", "u\u02d0", "n"]),              // ɧ uː n
        ("age",   ["\u0251\u02d0", "\u0267"]),               // ɑː ɧ
        ("eur",   ["\u00f8\u02d0", "r"]),                    // øː r
        ("eum",   ["e\u02d0", "\u0275", "m"]),               // eː ɵ m
        ("ium",   ["\u026a", "\u0275", "m"]),                // ɪ ɵ m
    ];

    // =================================================================
    // Tokenizer regex
    // =================================================================

    private static readonly Regex TokenRegex = new(
        @"([a-z\u00e5\u00e4\u00f6\u00e9\u00e0\u00fc\u00e1\u00e8\u00eb\u00ef]+|[,.;:!?]+)",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    // =================================================================
    // Public API
    // =================================================================

    /// <inheritdoc />
    public List<string> ToPhonemeList(string text)
    {
        string normalized = Normalize(text);
        var matches = TokenRegex.Matches(normalized);

        var phonemes = new List<string>(normalized.Length * 2);
        bool needSpace = false;

        foreach (Match match in matches)
        {
            string token = match.Value;

            // Check if token is all punctuation
            if (IsAllPunctuation(token))
            {
                for (int i = 0; i < token.Length; i++)
                    phonemes.Add(token[i].ToString());
                continue;
            }

            // Word token
            if (needSpace)
                phonemes.Add(" ");

            var wordPhonemes = PhonemizeWord(token);
            phonemes.AddRange(wordPhonemes);
            needSpace = true;
        }

        return phonemes;
    }

    // =================================================================
    // Stage 1: Normalization
    // =================================================================

    private static string Normalize(string text)
    {
        return text.ToLowerInvariant().Normalize(NormalizationForm.FormC);
    }

    private static bool IsAllPunctuation(string token)
    {
        for (int i = 0; i < token.Length; i++)
        {
            if (!Punctuation.Contains(token[i]))
                return false;
        }
        return true;
    }

    // =================================================================
    // Full word pipeline (Stage 2-6)
    // =================================================================

    private static List<string> PhonemizeWord(string word)
    {
        if (string.IsNullOrEmpty(word))
            return [];

        // Stage 6 prep: Detect stress syllable
        int stressedSyl = DetectStress(word);

        // Stage 2: Check loanword suffix
        List<string> rawPhonemes;
        var loanword = DetectLoanwordSuffix(word);
        if (loanword != null)
        {
            string stem = loanword.Value.Stem;
            string[] suffixPhonemes = loanword.Value.Phonemes;

            // Stem syllables before suffix stress -> unstressed
            int stemSylCount = CountSyllables(stem);
            int stemStressed = stressedSyl >= stemSylCount ? -1 : stressedSyl;
            var stemPhonemes = ConvertWordNative(stem, word, stemStressed);
            rawPhonemes = stemPhonemes;
            rawPhonemes.AddRange(suffixPhonemes);
        }
        else
        {
            // Stage 4: Native conversion
            rawPhonemes = ConvertWordNative(word, word, stressedSyl);
        }

        // Stage 5: Retroflex assimilation
        var phonemes = ApplyRetroflex(rawPhonemes);

        // Stage 6: Stress markers
        phonemes = InsertStressMarker(phonemes, stressedSyl);

        return phonemes;
    }

    // =================================================================
    // Stage 2: Loanword suffix detection
    // =================================================================

    private static (string Stem, string[] Phonemes)? DetectLoanwordSuffix(string word)
    {
        foreach (var (suffix, phonemes) in LoanwordSuffixRules)
        {
            if (word.EndsWith(suffix, StringComparison.Ordinal) && word.Length > suffix.Length)
            {
                // Check native exceptions for -age
                if (suffix == "age" && AgeNativeWords.Contains(word))
                    continue;
                string stem = word[..^suffix.Length];
                return (stem, phonemes);
            }
        }
        return null;
    }

    // =================================================================
    // Stage 3-4: Consonant conversion
    // =================================================================

    /// <summary>
    /// Convert consonant(s) starting at <paramref name="pos"/>.
    /// Returns (ipa_phonemes, chars_consumed).
    /// Implements longest-match priority ordering.
    /// </summary>
    private static (List<string> Phonemes, int Consumed) ConvertConsonant(
        string word, int pos, string fullWord)
    {
        int remaining = word.Length - pos;
        char ch = word[pos];
        char nextCh = CharAt(word, pos + 1);

        // === 3-char patterns (highest priority) ===
        if (remaining >= 3)
        {
            string tri = word.Substring(pos, 3);
            if (tri == "skj") return (new List<string> { "\u0267" }, 3);       // ɧ
            if (tri == "stj") return (new List<string> { "\u0267" }, 3);       // ɧ
            if (tri == "sch") return (new List<string> { "\u0267" }, 3);       // ɧ
            if (tri == "sng") return (new List<string> { "s", "n" }, 3);       // simplified
            if (tri == "ckj") return (new List<string> { "\u0255" }, 3);       // ɕ
        }

        // === 2-char patterns ===
        if (remaining >= 2)
        {
            string di = word.Substring(pos, 2);

            // sk + context
            if (di == "sk")
            {
                if (remaining >= 3 && FrontVowels.Contains(CharAt(word, pos + 2)))
                {
                    // sk + front vowel -> /ɧ/ (sj-sound)
                    // Exception: SkBackVowelExceptions
                    if (!SkBackVowelExceptions.Contains(fullWord))
                        return (new List<string> { "\u0267" }, 2);   // ɧ
                }
                // sk + back vowel / consonant / word-final -> /sk/
                return (new List<string> { "s", "k" }, 2);
            }

            if (di == "sj") return (new List<string> { "\u0267" }, 2);   // ɧ
            if (di == "sh") return (new List<string> { "\u0267" }, 2);   // ɧ (loanword)

            if (di == "ch")
            {
                // Check exceptions where ch = /k/
                if (ChExceptionsK.Contains(fullWord))
                    return (new List<string> { "k" }, 2);
                return (new List<string> { "\u0267" }, 2);   // ɧ (loanword)
            }

            if (di == "ph") return (new List<string> { "f" }, 2);       // loanword
            if (di == "th") return (new List<string> { "t" }, 2);       // loanword
            if (di == "tj") return (new List<string> { "\u0255" }, 2);  // ɕ
            if (di == "kj") return (new List<string> { "\u0255" }, 2);  // ɕ

            if (di == "gn")
            {
                // word-initial gn -> /ɡn/, elsewhere /ŋn/
                if (pos == 0)
                    return (new List<string> { "\u0261", "n" }, 2);  // ɡn
                return (new List<string> { "\u014b", "n" }, 2);      // ŋn
            }

            if (di == "ng") return (new List<string> { "\u014b" }, 2);       // ŋ
            if (di == "nk") return (new List<string> { "\u014b", "k" }, 2);  // ŋk
            if (di == "ck") return (new List<string> { "k" }, 2);            // geminate

            if (di == "gj" && pos == 0) return (new List<string> { "j" }, 2);
            if (di == "lj" && pos == 0) return (new List<string> { "j" }, 2);
            if (di == "dj" && pos == 0) return (new List<string> { "j" }, 2);
            if (di == "hj" && pos == 0) return (new List<string> { "j" }, 2);
        }

        // === 1-char patterns ===

        // k + front vowel -> soft /ɕ/ (default) or hard /k/ (exception)
        if (ch == 'k' && FrontVowels.Contains(nextCh))
        {
            if (IsHardK(fullWord))
                return (new List<string> { "k" }, 1);
            return (new List<string> { "\u0255" }, 1);  // ɕ
        }

        // g + front vowel -> soft /j/ (default) or hard /ɡ/ (exception)
        if (ch == 'g' && FrontVowels.Contains(nextCh))
        {
            if (IsHardG(fullWord))
                return (new List<string> { "\u0261" }, 1);  // ɡ
            return (new List<string> { "j" }, 1);
        }

        // g + back vowel / consonant -> /ɡ/
        if (ch == 'g')
            return (new List<string> { "\u0261" }, 1);  // ɡ

        // c before e/i -> /s/, otherwise /k/
        if (ch == 'c')
        {
            if (nextCh == 'e' || nextCh == 'i')
                return (new List<string> { "s" }, 1);
            return (new List<string> { "k" }, 1);
        }

        // x -> /ks/
        if (ch == 'x')
            return (new List<string> { "k", "s" }, 1);

        // Default single consonant
        if (ConsonantDefault.TryGetValue(ch, out string? ipa))
        {
            if (ipa.Length > 1)
            {
                var result = new List<string>(ipa.Length);
                for (int i = 0; i < ipa.Length; i++)
                    result.Add(ipa[i].ToString());
                return (result, 1);
            }
            return (new List<string> { ipa }, 1);
        }

        // Unknown consonant: pass through
        return (new List<string> { ch.ToString() }, 1);
    }

    // =================================================================
    // Soft/Hard consonant decision
    // =================================================================

    private static bool IsHardK(string word)
    {
        if (HardKWords.Contains(word))
            return true;
        // Morphological heuristic: strip common suffixes, check stems
        for (int suffixLen = 3; suffixLen >= 1; suffixLen--)
        {
            if (word.Length > suffixLen)
            {
                string stem = word[..^suffixLen];
                if (HardKStems.Contains(stem))
                    return true;
            }
        }
        return false;
    }

    private static bool IsHardG(string word)
    {
        if (HardGWords.Contains(word))
            return true;
        // -era verb heuristic
        if (word.EndsWith("era", StringComparison.Ordinal) ||
            word.EndsWith("erar", StringComparison.Ordinal) ||
            word.EndsWith("erade", StringComparison.Ordinal))
            return true;
        for (int suffixLen = 3; suffixLen >= 1; suffixLen--)
        {
            if (word.Length > suffixLen)
            {
                string stem = word[..^suffixLen];
                if (HardGStems.Contains(stem))
                    return true;
            }
        }
        return false;
    }

    // =================================================================
    // Stage 4: Vowel phoneme assignment (Complementary Quantity)
    // =================================================================

    private static string GetVowelPhoneme(string word, int pos, string fullWord, bool isStressed)
    {
        char ch = word[pos];

        // Unstressed -> short
        if (!isStressed)
            return ShortVowelMap.GetValueOrDefault(ch, ch.ToString());

        // Function word -> short
        if (FunctionWords.Contains(fullWord))
            return ShortVowelMap.GetValueOrDefault(ch, ch.ToString());

        // Final-m exception -> short
        if (FinalMShortWords.Contains(fullWord))
            return ShortVowelMap.GetValueOrDefault(ch, ch.ToString());

        // Count following consonants
        int nFollowing = CountFollowingConsonants(word, pos);

        // Word-final vowel -> long
        if (nFollowing == 0 && pos == word.Length - 1)
        {
            string vowel = LongVowelMap.GetValueOrDefault(ch, ch.ToString());
            if (ch == 'o' && OLongAsOo.Contains(fullWord))
                vowel = "o\u02d0";  // oː
            return vowel;
        }

        // r + single C exception: vowel stays long (r merges into retroflex)
        // Exception: 'o' is excluded
        if (nFollowing == 2 && ch != 'o' && pos + 1 < word.Length && word[pos + 1] == 'r')
        {
            string vowel = LongVowelMap.GetValueOrDefault(ch, ch.ToString());
            return vowel;
        }

        // Geminate / cluster (2+ consonants) -> short
        if (nFollowing >= 2)
            return ShortVowelMap.GetValueOrDefault(ch, ch.ToString());

        // Single consonant -> long
        {
            string vowel = LongVowelMap.GetValueOrDefault(ch, ch.ToString());
            if (ch == 'o' && OLongAsOo.Contains(fullWord))
                vowel = "o\u02d0";  // oː
            return vowel;
        }
    }

    private static int CountFollowingConsonants(string word, int pos)
    {
        int count = 0;
        int i = pos + 1;
        while (i < word.Length && Consonants.Contains(word[i]))
        {
            count++;
            i++;
        }
        return count;
    }

    // =================================================================
    // Native word conversion (Stage 4)
    // =================================================================

    private static List<string> ConvertWordNative(string word, string fullWord, int stressedSyl)
    {
        var phonemes = new List<string>(word.Length * 2);
        int pos = 0;
        int sylCount = 0;
        bool prevWasVowel = false;

        while (pos < word.Length)
        {
            char ch = word[pos];

            if (AllVowels.Contains(ch))
            {
                if (!prevWasVowel)
                {
                    bool isStressed = sylCount == stressedSyl && stressedSyl >= 0;
                    string vowel = GetVowelPhoneme(word, pos, fullWord, isStressed);
                    phonemes.Add(vowel);
                    sylCount++;
                }
                else
                {
                    // Consecutive vowel in same syllable (rare in Swedish)
                    string vowel = ShortVowelMap.GetValueOrDefault(ch, ch.ToString());
                    phonemes.Add(vowel);
                }
                prevWasVowel = true;
                pos++;
            }
            else if (Consonants.Contains(ch))
            {
                prevWasVowel = false;
                var (ipaList, consumed) = ConvertConsonant(word, pos, fullWord);
                phonemes.AddRange(ipaList);
                pos += consumed;
            }
            else
            {
                // Skip unknown characters
                prevWasVowel = false;
                pos++;
            }
        }

        return phonemes;
    }

    // =================================================================
    // Stage 5: Retroflex assimilation
    // =================================================================

    /// <summary>
    /// Apply retroflex assimilation: r + {t,d,s,n,l} -> retroflex.
    /// State machine: NORMAL -> R_DETECTED -> CASCADING.
    /// </summary>
    /// <summary>
    /// Apply retroflex assimilation. Exposed for testing.
    /// </summary>
    public static List<string> ApplyRetroflex(List<string> phonemes)
    {
        var result = new List<string>(phonemes.Count);
        int i = 0;
        int state = 0;  // 0=NORMAL, 1=R_DETECTED, 2=CASCADING

        while (i < phonemes.Count)
        {
            string ph = phonemes[i];

            switch (state)
            {
                case 0: // NORMAL
                    if (ph == "r")
                    {
                        state = 1; // R_DETECTED
                        i++;
                        continue;
                    }
                    result.Add(ph);
                    break;

                case 1: // R_DETECTED
                    if (ph == "r")
                    {
                        // rr -> geminate block, no assimilation
                        result.Add("r");
                        result.Add("r");
                        state = 0;
                    }
                    else if (RetroflexMap.TryGetValue(ph, out string? retro))
                    {
                        result.Add(retro);
                        if (PropagatingRetroflexes.Contains(retro))
                            state = 2; // CASCADING
                        else
                            state = 0; // ɭ stops cascade
                    }
                    else
                    {
                        // r + non-assimilable -> output r and reprocess
                        result.Add("r");
                        result.Add(ph);
                        state = 0;
                    }
                    break;

                case 2: // CASCADING
                    if (RetroflexMap.TryGetValue(ph, out string? cascadeRetro))
                    {
                        result.Add(cascadeRetro);
                        if (!PropagatingRetroflexes.Contains(cascadeRetro))
                            state = 0; // ɭ stops cascade
                    }
                    else
                    {
                        result.Add(ph);
                        state = 0;
                    }
                    break;
            }

            i++;
        }

        // Flush pending r
        if (state == 1)
            result.Add("r");

        return result;
    }

    // =================================================================
    // Stage 6: Stress detection
    // =================================================================

    /// <summary>
    /// Detect primary stress syllable index (0-based).
    /// Returns -1 for function words (no stress).
    /// </summary>
    /// <summary>
    /// Detect primary stress syllable index (0-based). Exposed for testing.
    /// </summary>
    public static int DetectStress(string word)
    {
        if (FunctionWords.Contains(word))
            return -1;

        int nSyl = CountSyllables(word);
        if (nSyl <= 1)
            return 0;

        // Check stress-attracting suffixes
        foreach (string suffix in StressAttractingSuffixes)
        {
            if (word.EndsWith(suffix, StringComparison.Ordinal) && word.Length > suffix.Length)
            {
                // Count syllables before suffix to find position
                string prefixPart = word[..^suffix.Length];
                return CountSyllables(prefixPart);
            }
        }

        // Check unstressed prefixes
        foreach (string prefix in UnstressedPrefixes)
        {
            if (word.StartsWith(prefix, StringComparison.Ordinal) && word.Length > prefix.Length + 1)
            {
                // Stress on syllable after prefix
                return 1;
            }
        }

        // Default: first syllable
        return 0;
    }

    /// <summary>
    /// Count syllables by counting vowel clusters.
    /// </summary>
    /// <summary>
    /// Count syllables by counting vowel clusters. Exposed for testing.
    /// </summary>
    public static int CountSyllables(string word)
    {
        int count = 0;
        bool prevVowel = false;
        for (int i = 0; i < word.Length; i++)
        {
            if (AllVowels.Contains(word[i]))
            {
                if (!prevVowel)
                    count++;
                prevVowel = true;
            }
            else
            {
                prevVowel = false;
            }
        }
        return Math.Max(count, 1);
    }

    /// <summary>
    /// Insert stress marker before the onset of the stressed syllable.
    /// </summary>
    private static List<string> InsertStressMarker(List<string> phonemes, int stressSyl)
    {
        if (stressSyl < 0 || phonemes.Count == 0)
            return phonemes;

        // 1. Find the index of the first vowel of the target syllable
        int sylCount = 0;
        int vowelIdx = -1;
        bool prevWasVowel = false;

        for (int i = 0; i < phonemes.Count; i++)
        {
            bool isV = IsIpaVowel(phonemes[i]);
            if (isV && !prevWasVowel)
            {
                if (sylCount == stressSyl)
                {
                    vowelIdx = i;
                    break;
                }
                sylCount++;
                prevWasVowel = true;
            }
            else if (!isV)
            {
                prevWasVowel = false;
            }
        }

        if (vowelIdx < 0)
            return phonemes;

        // 2. Walk backwards to find syllable onset (consonants before the vowel)
        int onsetIdx = vowelIdx;
        while (onsetIdx > 0 && !IsIpaVowel(phonemes[onsetIdx - 1]))
            onsetIdx--;

        // For syllable 0, onset starts at beginning
        if (stressSyl == 0)
            onsetIdx = 0;

        var result = new List<string>(phonemes.Count + 1);
        for (int i = 0; i < onsetIdx; i++)
            result.Add(phonemes[i]);
        result.Add("\u02c8");  // ˈ
        for (int i = onsetIdx; i < phonemes.Count; i++)
            result.Add(phonemes[i]);
        return result;
    }

    /// <summary>
    /// Check if a phoneme string represents a vowel.
    /// </summary>
    private static bool IsIpaVowel(string ph)
    {
        // Matches Python _is_ipa_vowel: checks if any character in the phoneme
        // is an IPA vowel character.
        for (int i = 0; i < ph.Length; i++)
        {
            char c = ph[i];
            if (IsIpaVowelChar(c))
                return true;
        }
        return false;
    }

    private static bool IsIpaVowelChar(char c)
    {
        return c switch
        {
            'a' or 'e' or 'i' or 'o' or 'u' or 'y' => true,
            '\u00e5' or '\u00e4' or '\u00f6' => true,                    // å ä ö
            '\u0251' or '\u025b' or '\u026a' or '\u0254' => true,        // ɑ ɛ ɪ ɔ
            '\u028a' or '\u0289' or '\u028f' => true,                    // ʊ ʉ ʏ
            '\u0153' or '\u00f8' or '\u0275' => true,                    // œ ø ɵ
            _ => false,
        };
    }

    // =================================================================
    // Helper
    // =================================================================

    /// <summary>Safe character access.</summary>
    private static char CharAt(string word, int pos)
    {
        return (pos >= 0 && pos < word.Length) ? word[pos] : '\0';
    }
}
