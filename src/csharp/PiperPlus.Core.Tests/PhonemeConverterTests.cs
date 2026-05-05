using PiperPlus.Core.Mapping;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="PiperPhonemeConverter"/> and
/// <see cref="OpenJTalkToPiperMapping"/>.
/// Covers PUA mapping (29 entries), question-type detection, and
/// context-dependent N-phoneme mutation rules.
/// </summary>
public sealed class PhonemeConverterTests
{
    // ================================================================
    // PUA Mapping tests
    // ================================================================

    [Fact]
    public void All29Entries_MatchPythonMapping()
    {
        // The fixed PUA entries must exactly match Python's FIXED_PUA_MAPPING
        // in token_mapper.py and C++ language-specific phonemize files.
        // Originally 29 JA entries; expanded to 87 for 6-language multilingual.
        var expected = new Dictionary<string, char>(29)
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
            ["N_m"] = '\uE019',
            ["N_n"] = '\uE01A',
            ["N_ng"] = '\uE01B',
            ["N_uvular"] = '\uE01C',
        };

        var actual = OpenJTalkToPiperMapping.TokenToChar;

        // PUA v2: 99 total = 29 JA + 2 shared + 43 ZH + 8 KO + 2 ES/PT + 3 FR + 9 SV + 3 multi-CP v2
        Assert.Equal(99, actual.Count);

        foreach (var (token, expectedChar) in expected)
        {
            Assert.True(actual.ContainsKey(token), $"Missing token: {token}");
            Assert.Equal(expectedChar, actual[token]);
        }
    }

    [Theory]
    [InlineData("a")]
    [InlineData("i")]
    [InlineData("k")]
    [InlineData("N")]
    [InlineData("^")]
    [InlineData("$")]
    public void SingleCharToken_PassThrough(string token)
    {
        var mapped = OpenJTalkToPiperMapping.MapToken(token);

        Assert.Equal(token, mapped);
    }

    [Fact]
    public void MapSequence_MixedTokens()
    {
        var input = new List<string> { "^", "k", "o", "N_m", "ch", "i", "$" };

        var result = OpenJTalkToPiperMapping.MapSequence(input);

        Assert.Equal(7, result.Count);
        Assert.Equal("^", result[0]);                                  // single char pass-through
        Assert.Equal("k", result[1]);                                  // single char pass-through
        Assert.Equal("o", result[2]);                                  // single char pass-through
        Assert.Equal("\uE019", result[3]);                             // N_m -> U+E019
        Assert.Equal("\uE00E", result[4]);                             // ch  -> U+E00E
        Assert.Equal("i", result[5]);                                  // single char pass-through
        Assert.Equal("$", result[6]);                                  // single char pass-through
    }

    // ================================================================
    // GetQuestionType tests
    // ================================================================

    [Fact]
    public void EmphasisQuestion()
    {
        Assert.Equal("?!", PiperPhonemeConverter.GetQuestionType("本当?!"));
    }

    [Fact]
    public void EmphasisQuestion_FullWidth()
    {
        // Full-width exclamation + full-width question: ！？
        Assert.Equal("?!", PiperPhonemeConverter.GetQuestionType("本当\uFF01\uFF1F"));
    }

    [Fact]
    public void NeutralQuestion()
    {
        Assert.Equal("?.", PiperPhonemeConverter.GetQuestionType("そうなの?."));
    }

    [Fact]
    public void NeutralQuestion_FullWidth()
    {
        // Full-width period (。) + full-width question (？): 。？
        Assert.Equal("?.", PiperPhonemeConverter.GetQuestionType("そうなの\u3002\uFF1F"));
    }

    [Fact]
    public void TagQuestion()
    {
        Assert.Equal("?~", PiperPhonemeConverter.GetQuestionType("行くよね?~"));
    }

    [Fact]
    public void TagQuestion_FullWidth()
    {
        // Full-width tilde (～) + full-width question (？): ～？
        Assert.Equal("?~", PiperPhonemeConverter.GetQuestionType("行くよね\uFF5E\uFF1F"));
    }

    [Fact]
    public void GenericQuestion()
    {
        // Full-width question mark alone -> generic "?"
        Assert.Equal("?", PiperPhonemeConverter.GetQuestionType("何ですか\uFF1F"));
    }

    [Fact]
    public void Declarative()
    {
        Assert.Equal("$", PiperPhonemeConverter.GetQuestionType("今日は良い天気です。"));
    }

    [Fact]
    public void EmptyString()
    {
        Assert.Equal("$", PiperPhonemeConverter.GetQuestionType(""));
    }

    [Fact]
    public void WhitespaceOnly()
    {
        Assert.Equal("$", PiperPhonemeConverter.GetQuestionType("  "));
    }

    // ================================================================
    // ApplyNPhonemeRules tests
    // ================================================================

    [Fact]
    public void N_Before_m()
    {
        // さんぽ: s a N p o -> N becomes N_m (p is bilabial)
        var input = new List<string> { "s", "a", "N", "p", "o" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal(["s", "a", "N_m", "p", "o"], result);
    }

    [Fact]
    public void N_Before_n()
    {
        // あんない: a N n a i -> N becomes N_n (n is alveolar)
        var input = new List<string> { "a", "N", "n", "a", "i" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal(["a", "N_n", "n", "a", "i"], result);
    }

    [Fact]
    public void N_Before_k()
    {
        // ぎんこう: g i N k o o -> N becomes N_ng (k is velar)
        var input = new List<string> { "g", "i", "N", "k", "o", "o" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal(["g", "i", "N_ng", "k", "o", "o"], result);
    }

    [Fact]
    public void N_AtEnd()
    {
        // ほん: h o N -> N becomes N_uvular (end of phrase)
        var input = new List<string> { "h", "o", "N" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal(["h", "o", "N_uvular"], result);
    }

    [Fact]
    public void N_Before_Vowel()
    {
        // N before vowel -> N_uvular
        var input = new List<string> { "N", "a" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal(["N_uvular", "a"], result);
    }

    [Fact]
    public void N_SkipSpecialTokens()
    {
        // N followed by skip token "_" then "k" -> N_ng (skips "_", sees "k")
        var input = new List<string> { "N", "_", "k", "a" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal(["N_ng", "_", "k", "a"], result);
    }

    [Fact]
    public void Multiple_N()
    {
        // Two N tokens: first before p (bilabial), second before k (velar)
        var input = new List<string> { "N", "p", "o", "N", "k", "a" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal(["N_m", "p", "o", "N_ng", "k", "a"], result);
    }

    [Fact]
    public void No_N()
    {
        // No N tokens -> unchanged
        var input = new List<string> { "k", "a", "k", "i" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal(["k", "a", "k", "i"], result);
    }

    // ================================================================
    // Exhaustive N phoneme variant tests
    // ================================================================

    [Theory]
    [InlineData("m")]
    [InlineData("my")]
    [InlineData("b")]
    [InlineData("by")]
    [InlineData("p")]
    [InlineData("py")]
    public void ApplyNPhonemeRules_AllBilabialPhonemes(string following)
    {
        // N before any bilabial phoneme -> N_m
        var input = new List<string> { "a", "N", following, "a" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal("N_m", result[1]);
    }

    [Theory]
    [InlineData("n")]
    [InlineData("ny")]
    [InlineData("t")]
    [InlineData("ty")]
    [InlineData("d")]
    [InlineData("dy")]
    [InlineData("ts")]
    [InlineData("ch")]
    public void ApplyNPhonemeRules_AllAlveolarPhonemes(string following)
    {
        // N before any alveolar phoneme -> N_n
        var input = new List<string> { "a", "N", following, "a" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal("N_n", result[1]);
    }

    [Theory]
    [InlineData("k")]
    [InlineData("ky")]
    [InlineData("kw")]
    [InlineData("g")]
    [InlineData("gy")]
    [InlineData("gw")]
    public void ApplyNPhonemeRules_AllVelarPhonemes(string following)
    {
        // N before any velar phoneme -> N_ng
        var input = new List<string> { "a", "N", following, "a" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal("N_ng", result[1]);
    }

    [Theory]
    [InlineData("a")]
    [InlineData("i")]
    [InlineData("u")]
    [InlineData("e")]
    [InlineData("o")]
    public void ApplyNPhonemeRules_N_BeforeVowel_Uvular(string vowel)
    {
        // N before any vowel -> N_uvular
        var input = new List<string> { "N", vowel };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal("N_uvular", result[0]);
    }

    [Fact]
    public void ApplyNPhonemeRules_SkipMultipleTokens()
    {
        // N followed by "_", "#", then "p" -> N_m (skips both "_" and "#", sees "p")
        var input = new List<string> { "N", "_", "#", "p", "a" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal("N_m", result[0]);
        // The remaining tokens are unchanged
        Assert.Equal(["N_m", "_", "#", "p", "a"], result);
    }

    [Fact]
    public void ApplyNPhonemeRules_OnlySkipTokensAfterN_Uvular()
    {
        // N followed by only skip tokens (no real phoneme) -> N_uvular
        var input = new List<string> { "a", "N", "_", "#", "$" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal("N_uvular", result[1]);
        Assert.Equal(["a", "N_uvular", "_", "#", "$"], result);
    }

    [Fact]
    public void ApplyNPhonemeRules_UnknownPhoneme_Uvular()
    {
        // N before an unknown phoneme "x" -> N_uvular (fallback)
        var input = new List<string> { "N", "x" };

        var result = PiperPhonemeConverter.ApplyNPhonemeRules(input);

        Assert.Equal("N_uvular", result[0]);
        Assert.Equal(["N_uvular", "x"], result);
    }

    // ================================================================
    // Additional GetQuestionType tests
    // ================================================================

    [Fact]
    public void GetQuestionType_NullInput_ReturnsDefault()
    {
        // null.AsSpan() returns ReadOnlySpan<char>.Empty in .NET,
        // so GetQuestionType treats null the same as empty string -> "$"
        Assert.Equal("$", PiperPhonemeConverter.GetQuestionType(null!));
    }

    [Fact]
    public void GetQuestionType_MixedFullWidthAscii()
    {
        // Full-width question ？ followed by ASCII half-width !
        // "？!" does not match any multi-char pattern (expected: "！？" or "？！")
        // The last char is '!' (not '?' or '？'), so -> "$"
        Assert.Equal("$", PiperPhonemeConverter.GetQuestionType("なぜ\uFF1F!"));
    }

    // ================================================================
    // EspeakPostProcessIds tests
    // ================================================================

    [Fact]
    public void EspeakPostProcessIds_BasicSequence()
    {
        var ids = new List<int> { 10, 11 };
        var prosody = new List<ProsodyInfo?> { new(0, 1, 2), new(0, 2, 2) };
        var map = new Dictionary<string, int[]>
        {
            ["_"] = [0],
            ["^"] = [1],
            ["$"] = [2],
        };

        var (resultIds, resultPros) = PiperPhonemeConverter.EspeakPostProcessIds(ids, prosody, map);

        Assert.Equal([1, 0, 10, 0, 11, 0, 2], resultIds);
        Assert.Equal(resultIds.Count, resultPros.Count);
    }

    [Fact]
    public void EspeakPostProcessIds_SkipsPadAfterPadToken()
    {
        var ids = new List<int> { 10, 0, 11 };
        var prosody = new List<ProsodyInfo?> { new(0, 1, 3), null, new(0, 2, 3) };
        var map = new Dictionary<string, int[]>
        {
            ["_"] = [0],
            ["^"] = [1],
            ["$"] = [2],
        };

        var (resultIds, resultPros) = PiperPhonemeConverter.EspeakPostProcessIds(ids, prosody, map);

        // 0 is a PAD token -> no extra PAD after it
        Assert.Equal([1, 0, 10, 0, 0, 11, 0, 2], resultIds);
        Assert.Equal(resultIds.Count, resultPros.Count);
    }

    [Fact]
    public void EspeakPostProcessIds_EmptyInput()
    {
        var ids = new List<int>();
        var prosody = new List<ProsodyInfo?>();
        var map = new Dictionary<string, int[]>
        {
            ["_"] = [0],
            ["^"] = [1],
            ["$"] = [2],
        };

        var (resultIds, resultPros) = PiperPhonemeConverter.EspeakPostProcessIds(ids, prosody, map);

        Assert.Equal([1, 0, 2], resultIds);
        Assert.Equal(resultIds.Count, resultPros.Count);
    }
}
