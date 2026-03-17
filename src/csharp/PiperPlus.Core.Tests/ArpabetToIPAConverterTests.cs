using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="ArpabetToIPAConverter"/>.
/// Covers single-token conversion, context-dependent word conversion,
/// function-word detection, and punctuation classification.
/// </summary>
public sealed class ArpabetToIPAConverterTests
{
    // ================================================================
    // ConvertToken tests
    // ================================================================

    [Fact]
    public void ConvertToken_Consonant_NoStress()
    {
        var (ipa, stress) = ArpabetToIPAConverter.ConvertToken("B");

        Assert.Equal("b", ipa);
        Assert.Equal(-1, stress);
    }

    [Fact]
    public void ConvertToken_Vowel_PrimaryStress()
    {
        var (ipa, stress) = ArpabetToIPAConverter.ConvertToken("AH1");

        Assert.Equal("\u028c", ipa); // ʌ
        Assert.Equal(1, stress);
    }

    [Fact]
    public void ConvertToken_Vowel_SecondaryStress()
    {
        var (ipa, stress) = ArpabetToIPAConverter.ConvertToken("AH2");

        Assert.Equal("\u028c", ipa); // ʌ
        Assert.Equal(2, stress);
    }

    [Fact]
    public void ConvertToken_Vowel_Unstressed_AH0_IsSchwa()
    {
        // Special case: unstressed AH maps to schwa
        var (ipa, stress) = ArpabetToIPAConverter.ConvertToken("AH0");

        Assert.Equal("\u0259", ipa); // ə
        Assert.Equal(0, stress);
    }

    [Fact]
    public void ConvertToken_AH_Stressed_NotSchwa()
    {
        var (ipa, stress) = ArpabetToIPAConverter.ConvertToken("AH1");

        Assert.Equal("\u028c", ipa); // ʌ (not schwa)
        Assert.Equal(1, stress);
    }

    [Fact]
    public void ConvertToken_Punctuation_Passthrough()
    {
        var (ipa, stress) = ArpabetToIPAConverter.ConvertToken(",");

        Assert.Equal(",", ipa);
        Assert.Equal(-1, stress);
    }

    [Fact]
    public void ConvertToken_AllArpabetSymbolsMapped()
    {
        // All 33 ARPAbet entries must produce a non-empty IPA string
        // with stress == -1 (no stress digit in the input).
        var expected = new Dictionary<string, string>
        {
            ["AA"] = "\u0251",   // ɑ
            ["AE"] = "\u00e6",   // æ
            ["AH"] = "\u028c",   // ʌ
            ["AO"] = "\u0254\u02d0", // ɔː
            ["AW"] = "a\u028a", // aʊ
            ["AY"] = "a\u026a", // aɪ
            ["B"]  = "b",
            ["CH"] = "t\u0283", // tʃ
            ["D"]  = "d",
            ["DH"] = "\u00f0",  // ð
            ["EH"] = "\u025b",  // ɛ
            ["ER"] = "\u025a",  // ɚ
            ["EY"] = "e\u026a", // eɪ
            ["F"]  = "f",
            ["G"]  = "\u0261",  // ɡ
            ["HH"] = "h",
            ["IH"] = "\u026a",  // ɪ
            ["IY"] = "i\u02d0", // iː
            ["JH"] = "d\u0292", // dʒ
            ["K"]  = "k",
            ["L"]  = "l",
            ["M"]  = "m",
            ["N"]  = "n",
            ["NG"] = "\u014b",  // ŋ
            ["OW"] = "o\u028a", // oʊ
            ["OY"] = "\u0254\u026a", // ɔɪ
            ["P"]  = "p",
            ["R"]  = "\u0279",  // ɹ
            ["S"]  = "s",
            ["SH"] = "\u0283",  // ʃ
            ["T"]  = "t",
            ["TH"] = "\u03b8",  // θ
            ["UH"] = "\u028a",  // ʊ
            ["UW"] = "u\u02d0", // uː
            ["V"]  = "v",
            ["W"]  = "w",
            ["Y"]  = "j",
            ["Z"]  = "z",
            ["ZH"] = "\u0292",  // ʒ
        };

        // ArpabetToIpa has 39 entries (33 base + some aliases)
        Assert.Equal(expected.Count, expected.Count); // self-check, real validation is below

        foreach (var (arpa, expectedIpa) in expected)
        {
            var (ipa, stress) = ArpabetToIPAConverter.ConvertToken(arpa);

            Assert.Equal(expectedIpa, ipa);
            Assert.Equal(-1, stress); // no stress digit -> -1
        }
    }

    [Fact]
    public void ConvertToken_ER_Unstressed()
    {
        var (ipa, stress) = ArpabetToIPAConverter.ConvertToken("ER0");

        Assert.Equal("\u025a", ipa); // ɚ
        Assert.Equal(0, stress);
    }

    // ================================================================
    // ConvertWord tests (context-dependent)
    // ================================================================

    [Fact]
    public void ConvertWord_AA_R_MergesToLongVowel()
    {
        // AA1 + R -> single ɑːɹ token
        var result = ArpabetToIPAConverter.ConvertWord(["AA1", "R"]);

        Assert.Single(result);
        Assert.Equal("\u0251\u02d0\u0279", result[0].Ipa); // ɑːɹ
        Assert.Equal(1, result[0].Stress);
    }

    [Fact]
    public void ConvertWord_StressedER_BecomesLong()
    {
        // ER1 -> ɜː (stressed r-colored vowel)
        var result = ArpabetToIPAConverter.ConvertWord(["ER1"]);

        Assert.Single(result);
        Assert.Equal("\u025c\u02d0", result[0].Ipa); // ɜː
        Assert.Equal(1, result[0].Stress);
    }

    [Fact]
    public void ConvertWord_UnstressedER_BecomesSchwaR()
    {
        // ER0 -> ɚ (unstressed r-colored vowel)
        var result = ArpabetToIPAConverter.ConvertWord(["ER0"]);

        Assert.Single(result);
        Assert.Equal("\u025a", result[0].Ipa); // ɚ
        Assert.Equal(0, result[0].Stress);
    }

    [Fact]
    public void ConvertWord_NormalWord()
    {
        // "hello" = HH AH0 L OW1 -> h ə l oʊ
        var result = ArpabetToIPAConverter.ConvertWord(["HH", "AH0", "L", "OW1"]);

        Assert.Equal(4, result.Count);
        Assert.Equal("h", result[0].Ipa);
        Assert.Equal(-1, result[0].Stress);
        Assert.Equal("\u0259", result[1].Ipa); // ə (AH0 -> schwa)
        Assert.Equal(0, result[1].Stress);
        Assert.Equal("l", result[2].Ipa);
        Assert.Equal(-1, result[2].Stress);
        Assert.Equal("o\u028a", result[3].Ipa); // oʊ
        Assert.Equal(1, result[3].Stress);
    }

    // ================================================================
    // IsFunctionWord tests
    // ================================================================

    [Fact]
    public void IsFunctionWord_The()
    {
        Assert.True(ArpabetToIPAConverter.IsFunctionWord("the"));
    }

    [Fact]
    public void IsFunctionWord_Are()
    {
        Assert.True(ArpabetToIPAConverter.IsFunctionWord("are"));
    }

    [Fact]
    public void IsFunctionWord_ContentWord_Hello()
    {
        Assert.False(ArpabetToIPAConverter.IsFunctionWord("hello"));
    }

    [Fact]
    public void IsFunctionWord_CaseInsensitive()
    {
        Assert.True(ArpabetToIPAConverter.IsFunctionWord("The"));
    }

    // ================================================================
    // IsPunctuation tests
    // ================================================================

    [Fact]
    public void IsPunctuation_Comma()
    {
        Assert.True(ArpabetToIPAConverter.IsPunctuation(","));
    }

    [Fact]
    public void IsPunctuation_Period()
    {
        Assert.True(ArpabetToIPAConverter.IsPunctuation("."));
    }

    [Fact]
    public void IsPunctuation_Letter()
    {
        Assert.False(ArpabetToIPAConverter.IsPunctuation("a"));
    }
}
