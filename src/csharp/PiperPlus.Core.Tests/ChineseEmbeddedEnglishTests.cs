using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using PiperPlus.Core.Phonemize;
using PiperPlus.Core.Phonemize.Data;
using Xunit;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="ChineseEmbeddedEnglish"/> and
/// <see cref="LoanwordDataLoader"/> — TICKET-03 R5 mirror.
/// Byte-for-byte parity with the Python / Rust / Go implementations is
/// enforced by token-count assertions on canonical inputs (GPS, Python,
/// ChatGPT) plus structural checks for lookup priority and forward-compat.
/// </summary>
public sealed class ChineseEmbeddedEnglishTests
{
    [Fact]
    public void Loader_DefaultEmbedded_Loads()
    {
        var data = LoanwordDataLoader.Default;
        Assert.NotNull(data);
        Assert.Equal(1, data.Version);
        Assert.True(data.Acronyms.Count >= 60, $"acronyms count: {data.Acronyms.Count}");
        Assert.True(data.Loanwords.Count >= 35, $"loanwords count: {data.Loanwords.Count}");
        Assert.Equal(26, data.LetterFallback.Count);
    }

    [Fact]
    public void Loader_OnceOnly_SameInstance()
    {
        var d1 = LoanwordDataLoader.Default;
        var d2 = LoanwordDataLoader.Default;
        Assert.Same(d1, d2);
    }

    [Fact]
    public void EmbeddedEnglish_AcronymGPS()
    {
        var result = ChineseEmbeddedEnglish.Convert("GPS");
        // GPS = ji4(3) + pi4(3) + ai1(2 zero initial) + si4(3) = 11
        Assert.Equal(11, result.Phonemes.Count);
        // Prosody filled with zeros (embedded EN no Chinese context).
        Assert.All(result.A1, v => Assert.Equal(0, v));
        Assert.All(result.A2, v => Assert.Equal(0, v));
        Assert.All(result.A3, v => Assert.Equal(0, v));
    }

    [Fact]
    public void EmbeddedEnglish_LoanwordPython_CaseSensitive()
    {
        var result = ChineseEmbeddedEnglish.Convert("Python");
        // pai4(3) + sen1(3) = 6
        Assert.Equal(6, result.Phonemes.Count);
    }

    [Fact]
    public void EmbeddedEnglish_ChatGPT_FiveSyllables()
    {
        var result = ChineseEmbeddedEnglish.Convert("ChatGPT");
        // 5 syllables × 3 IPA = 15
        Assert.Equal(15, result.Phonemes.Count);
    }

    [Fact]
    public void EmbeddedEnglish_LetterFallback_ZZ()
    {
        var zz = ChineseEmbeddedEnglish.Convert("ZZ");
        var z = ChineseEmbeddedEnglish.Convert("Z");
        Assert.Equal(z.Phonemes.Count * 2, zz.Phonemes.Count);
    }

    [Fact]
    public void EmbeddedEnglish_Empty_ReturnsEmpty()
    {
        Assert.Empty(ChineseEmbeddedEnglish.Convert("").Phonemes);
        Assert.Empty(ChineseEmbeddedEnglish.Convert("   ").Phonemes);
        Assert.Empty(ChineseEmbeddedEnglish.Convert(",.!?").Phonemes);
    }

    [Fact]
    public void LookupPriority_LoanwordBeatsAcronym()
    {
        var data = new LoanwordData(
            Version: 1,
            Acronyms: new Dictionary<string, IReadOnlyList<string>> { ["AI"] = new[] { "ji4" } },
            Loanwords: new Dictionary<string, IReadOnlyList<string>> { ["AI"] = new[] { "ma1" } },
            LetterFallback: new Dictionary<string, IReadOnlyList<string>>());
        var got = ChineseEmbeddedEnglish.Convert("AI", data);

        var loanOnly = ChineseEmbeddedEnglish.Convert("AI", new LoanwordData(
            Version: 1,
            Acronyms: new Dictionary<string, IReadOnlyList<string>>(),
            Loanwords: new Dictionary<string, IReadOnlyList<string>> { ["AI"] = new[] { "ma1" } },
            LetterFallback: new Dictionary<string, IReadOnlyList<string>>()));
        Assert.Equal(loanOnly.Phonemes, got.Phonemes);
    }

    [Fact]
    public void LookupPriority_AcronymBeatsFallback()
    {
        var data = new LoanwordData(
            Version: 1,
            Acronyms: new Dictionary<string, IReadOnlyList<string>> { ["ZX"] = new[] { "ma1" } },
            Loanwords: new Dictionary<string, IReadOnlyList<string>>(),
            LetterFallback: new Dictionary<string, IReadOnlyList<string>>
            {
                ["Z"] = new[] { "zi4" },
                ["X"] = new[] { "ai4" },
            });
        var got = ChineseEmbeddedEnglish.Convert("ZX", data);
        // Acronym path: 1 syllable -> ~3 IPA. Letter fallback would be 2 syllables -> ~6.
        Assert.True(got.Phonemes.Count < 6,
            $"acronym path produced {got.Phonemes.Count} tokens, expected fewer than letter-fallback (6)");
    }

    [Fact]
    public void Punctuation_TrailingComma_Equivalent()
    {
        var plain = ChineseEmbeddedEnglish.Convert("GPS").Phonemes;
        foreach (var suffix in new[] { ",", ".", "!", ":" })
        {
            var got = ChineseEmbeddedEnglish.Convert("GPS" + suffix).Phonemes;
            Assert.Equal(plain, got);
        }
    }

    [Fact]
    public void MultiSegment_TwoEmbeddedEn()
    {
        var combined = ChineseEmbeddedEnglish.Convert("ChatGPT 和 Python").Phonemes;
        var chatgpt = ChineseEmbeddedEnglish.Convert("ChatGPT").Phonemes;
        var python = ChineseEmbeddedEnglish.Convert("Python").Phonemes;
        Assert.Equal(chatgpt.Count + python.Count, combined.Count);
    }

    [Fact]
    public void Digits_Z2Z9_EqualsZZ()
    {
        var z2z9 = ChineseEmbeddedEnglish.Convert("Z2Z9").Phonemes;
        var zz = ChineseEmbeddedEnglish.Convert("ZZ").Phonemes;
        Assert.Equal(zz, z2z9);
    }

    [Fact]
    public void AcronymWithDigits_MP3_DirectHit()
    {
        var data = new LoanwordData(
            Version: 1,
            Acronyms: new Dictionary<string, IReadOnlyList<string>> { ["MP3"] = new[] { "ai1" } },
            Loanwords: new Dictionary<string, IReadOnlyList<string>>(),
            LetterFallback: new Dictionary<string, IReadOnlyList<string>>
            {
                ["M"] = new[] { "ai1", "mu5" },
                ["P"] = new[] { "pi4" },
            });
        var got = ChineseEmbeddedEnglish.Convert("MP3", data);
        var acronymOnly = ChineseEmbeddedEnglish.Convert("MP3", new LoanwordData(
            Version: 1,
            Acronyms: new Dictionary<string, IReadOnlyList<string>> { ["MP3"] = new[] { "ai1" } },
            Loanwords: new Dictionary<string, IReadOnlyList<string>>(),
            LetterFallback: new Dictionary<string, IReadOnlyList<string>>()));
        Assert.Equal(acronymOnly.Phonemes, got.Phonemes);
    }

    [Fact]
    public void CaseSensitivity_PythonVsPYTHON()
    {
        var lower = ChineseEmbeddedEnglish.Convert("Python").Phonemes;
        var upper = ChineseEmbeddedEnglish.Convert("PYTHON").Phonemes;
        Assert.NotEmpty(lower);
        Assert.NotEmpty(upper);
        Assert.NotEqual(lower, upper);
    }

    [Fact]
    public void Loader_InvalidSchemaListType_Throws()
    {
        var bad = System.Text.Encoding.UTF8.GetBytes(
            @"{""version"": 1, ""acronyms"": {""GPS"": ""not_a_list""}}");
        var ex = Assert.Throws<LoanwordSchemaException>(() =>
            LoanwordDataLoader.LoadFromBytes("test.json", bad));
        Assert.Contains("'acronyms.GPS'", ex.Message);
        Assert.Contains("must be list[str]", ex.Message);
    }

    [Fact]
    public void Loader_InvalidSchemaSection_Throws()
    {
        var bad = System.Text.Encoding.UTF8.GetBytes(
            @"{""version"": 1, ""acronyms"": ""not_a_dict""}");
        var ex = Assert.Throws<LoanwordSchemaException>(() =>
            LoanwordDataLoader.LoadFromBytes("test.json", bad));
        Assert.Contains("'acronyms'", ex.Message);
        Assert.Contains("must be a mapping", ex.Message);
    }

    [Fact]
    public void Loader_AcceptsUnknownFieldsInSchemaV2()
    {
        // YELLOW-5: forward-compat loader accepts unknown top-level fields.
        var v2 = System.Text.Encoding.UTF8.GetBytes(@"{
            ""version"": 2,
            ""schema_version"": 2,
            ""metadata"": {""experimental"": true},
            ""acronyms"": {""GPS"": [""ji4""]},
            ""loanwords"": {""Python"": [""pai4""]},
            ""letter_fallback"": {""A"": [""ei1""]},
            ""tone_overrides"": {""GPS"": ""high""}
        }");
        var data = LoanwordDataLoader.LoadFromBytes("future_v2.json", v2);
        Assert.Equal(2, data.Version);
        Assert.Contains("GPS", data.Acronyms.Keys);
    }

    [Fact]
    public void EmbeddedJson_BytesContainCanonicalKeys()
    {
        // The embedded JSON is byte-identical to Python source per CI gate.
        // We sanity-check canonical keys here; full byte parity is enforced by
        // scripts/check_loanword_consistency.py.
        var data = LoanwordDataLoader.Default;
        Assert.Contains("GPS", data.Acronyms.Keys);
        Assert.Contains("USB", data.Acronyms.Keys);
        Assert.Contains("Python", data.Loanwords.Keys);
        Assert.Contains("ChatGPT", data.Loanwords.Keys);
    }

    [Fact]
    public void PinyinToIpa_Initial_b_Beats_p()
    {
        // Mandarin phonology: b=[p], p=[pʰ] (aspiration distinction).
        Assert.Equal("p", PinyinToIpa.InitialToIpa["b"]);
        Assert.Equal("pʰ", PinyinToIpa.InitialToIpa["p"]);
    }

    [Fact]
    public void PinyinToIpa_Final_ang()
    {
        Assert.Equal("aŋ", PinyinToIpa.FinalToIpa["ang"]);
    }

    [Fact]
    public void PinyinToIpa_FullSyllable_pai4()
    {
        // pai4 = pʰ + aɪ + tone4 = 3 IPA tokens before PUA mapping
        var tokens = PinyinToIpa.Convert("pai", 4);
        Assert.Equal(3, tokens.Count);
        Assert.Equal("pʰ", tokens[0]);
        Assert.Equal("aɪ", tokens[1]);
        Assert.Equal("tone4", tokens[2]);
    }
}
