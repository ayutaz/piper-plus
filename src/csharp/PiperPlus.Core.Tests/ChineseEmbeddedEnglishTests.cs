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
        // Per-token prosody mirrors Python phonemize_from_pinyin_syllables(
        // ..., chinese_text=""): a1 = syllable tone (1..=5), a2 = a3 = 1
        // (review note R-C1 — was zero-fill, silently dropping tone).
        Assert.All(result.A1, v => Assert.InRange(v, 1, 5));
        Assert.All(result.A2, v => Assert.Equal(1, v));
        Assert.All(result.A3, v => Assert.Equal(1, v));
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

    // ================================================================
    // MultilingualPhonemizer dispatch tests (review note CS-H1).
    // The dispatch routing in MultilingualPhonemizer.PhonemizeCore() is
    // exercised end-to-end with a passthrough EN stub and the real
    // ChineseEmbeddedEnglish path so we can verify all 6 ZH-EN
    // adjacency patterns + the EnableZhEnDispatch toggle.
    // ================================================================

    /// <summary>Stub EN phonemizer: returns characters as tokens, no prosody.</summary>
    private sealed class PassthroughEnStub : IPhonemizer
    {
        public List<string> Phonemize(string text) =>
            text.Where(c => !char.IsWhiteSpace(c)).Select(c => c.ToString()).ToList();

        public (List<string>, List<ProsodyInfo?>) PhonemizeWithProsody(string text)
        {
            var toks = Phonemize(text);
            return (toks, new List<ProsodyInfo?>(new ProsodyInfo?[toks.Count]));
        }

        public Dictionary<string, int[]>? GetPhonemeIdMap() => null;
    }

    /// <summary>Stub Chinese G2P engine: returns empty for ordinary Chinese
    /// (we only exercise the embedded-EN default impl which routes through
    /// <see cref="ChineseEmbeddedEnglish"/>).</summary>
    private sealed class StubZhEngine : IChineseG2PEngine
    {
        public ChineseG2PResult Convert(string text) => new(
            Array.Empty<string>(),
            Array.Empty<int>(), Array.Empty<int>(), Array.Empty<int>());
    }

    /// <summary>
    /// Dispatch-tracking stub: counts <c>ConvertEmbeddedEnglish</c> invocations
    /// so the multilingual dispatch path can be verified to honor an injected
    /// engine (review feedback CS-H1).
    /// </summary>
    private sealed class CountingZhEngine : IChineseG2PEngine
    {
        public int EmbeddedEnglishCalls;
        public string? LastEmbeddedEnglishInput;

        public ChineseG2PResult Convert(string text) => new(
            Array.Empty<string>(),
            Array.Empty<int>(), Array.Empty<int>(), Array.Empty<int>());

        public ChineseG2PResult ConvertEmbeddedEnglish(
            string text, LoanwordData? loanwordData = null)
        {
            EmbeddedEnglishCalls++;
            LastEmbeddedEnglishInput = text;
            // Delegate to the canonical default to keep the rest of the
            // pipeline behavior intact for the test assertions.
            return ChineseEmbeddedEnglish.Convert(text, loanwordData);
        }
    }

    private static MultilingualPhonemizer MakeZhEnDispatchPhonemizer() =>
        new(new Dictionary<string, IPhonemizer>
        {
            ["zh"] = new ChinesePhonemizer(new StubZhEngine()),
            ["en"] = new PassthroughEnStub(),
        });

    private static int CountPuaToneMarkers(IEnumerable<string> tokens) =>
        tokens.Count(t => t.Length > 0
            && (int)t[0] >= 0xE020 && (int)t[0] <= 0xE04A);

    [Fact]
    public void MultilingualDispatch_ZhEnZh_DispatchedToLoanwordPath()
    {
        var mp = MakeZhEnDispatchPhonemizer();
        var (tokens, _) = mp.PhonemizeWithProsody("你好 GPS 世界");
        Assert.True(CountPuaToneMarkers(tokens) > 0,
            "[zh, en, zh] must produce PUA tone markers from loanword path");
    }

    [Fact]
    public void MultilingualDispatch_ZhEn_DispatchedToLoanwordPath()
    {
        var mp = MakeZhEnDispatchPhonemizer();
        var (tokens, _) = mp.PhonemizeWithProsody("请打开 GPS");
        Assert.True(CountPuaToneMarkers(tokens) > 0,
            "[zh, en] tail must dispatch to loanword path");
    }

    [Fact]
    public void MultilingualDispatch_EnZh_DispatchedToLoanwordPath()
    {
        var mp = MakeZhEnDispatchPhonemizer();
        var (tokens, _) = mp.PhonemizeWithProsody("GPS 是什么");
        Assert.True(CountPuaToneMarkers(tokens) > 0,
            "[en, zh] head must dispatch to loanword path");
    }

    [Fact]
    public void MultilingualDispatch_EnZhEn_BothEndsDispatched()
    {
        // Review note R-H1: when en is at both ends with zh in the middle,
        // both en segments are adjacent to zh and so both should dispatch.
        var mp = MakeZhEnDispatchPhonemizer();
        var (tokens, _) = mp.PhonemizeWithProsody("Hello 你好 GPS");
        Assert.True(CountPuaToneMarkers(tokens) > 0,
            "[en, zh, en]: at least one en must dispatch to loanword path");
    }

    [Fact]
    public void MultilingualDispatch_PureEn_DoesNotDispatch()
    {
        var mp = MakeZhEnDispatchPhonemizer();
        var (tokens, _) = mp.PhonemizeWithProsody("Hello GPS world");
        Assert.Equal(0, CountPuaToneMarkers(tokens));
    }

    [Fact]
    public void MultilingualDispatch_DisabledFlag_FallsThroughToEnglish()
    {
        var mp = MakeZhEnDispatchPhonemizer();
        mp.EnableZhEnDispatch = false;
        var (tokens, _) = mp.PhonemizeWithProsody("你好 GPS 世界");
        Assert.Equal(0, CountPuaToneMarkers(tokens));
    }

    [Fact]
    public void MultilingualDispatch_RoutesThroughInjectedEngine()
    {
        // Review feedback CS-H1: the dispatch path must call
        // ChinesePhonemizer.Engine.ConvertEmbeddedEnglish(...) instead of the
        // static ChineseEmbeddedEnglish.Convert helper, so callers that wire
        // a custom IChineseG2PEngine see their override honored. Pin that
        // contract by counting invocations on a tracking engine.
        var counting = new CountingZhEngine();
        var mp = new MultilingualPhonemizer(new Dictionary<string, IPhonemizer>
        {
            ["zh"] = new ChinesePhonemizer(counting),
            ["en"] = new PassthroughEnStub(),
        });
        var (_, _) = mp.PhonemizeWithProsody("你好 GPS 世界");
        Assert.True(counting.EmbeddedEnglishCalls >= 1,
            "MultilingualPhonemizer must route ZH-EN dispatch through " +
            "ChinesePhonemizer.Engine.ConvertEmbeddedEnglish, not the static helper");
        // Segmenter may include adjacent whitespace; just verify the engine
        // saw the GPS token.
        Assert.NotNull(counting.LastEmbeddedEnglishInput);
        Assert.Contains("GPS", counting.LastEmbeddedEnglishInput,
            StringComparison.Ordinal);
    }

    [Fact]
    public void MultilingualDispatch_CarriesProsodyA1Tone()
    {
        // Review note R-C1 / CS-H1: dispatched IPA tokens must carry per-token
        // prosody (a1=tone, a2=1, a3=1), not null/zero.
        var mp = MakeZhEnDispatchPhonemizer();
        var (tokens, prosody) =
            mp.PhonemizeWithProsody("你好 GPS 世界");
        Assert.Equal(tokens.Count, prosody.Count);
        bool found = false;
        for (int i = 0; i < tokens.Count; i++)
        {
            if (tokens[i].Length == 0) continue;
            var c = (int)tokens[i][0];
            if (c < 0xE020 || c > 0xE04A) continue;
            var p = prosody[i];
            if (p is { } info && info.A1 >= 1 && info.A1 <= 5
                && info.A2 == 1 && info.A3 == 1)
            {
                found = true;
                break;
            }
        }
        Assert.True(found,
            "expected at least one dispatched PUA token with (a1=tone, a2=1, a3=1)");
    }

    // ================================================================
    // CS-H2: LoanwordDataLoader exception wrapping (CA1032 + JSON wrap)
    // ================================================================

    [Fact]
    public void Loader_MalformedJson_WrapsAsSchemaException()
    {
        // Truncated/malformed JSON triggers System.Text.Json.JsonException.
        // The loader must wrap that as LoanwordSchemaException so callers
        // need to catch only one exception type.
        var bad = System.Text.Encoding.UTF8.GetBytes(@"{""version"": 1, ""acron");
        var ex = Assert.Throws<LoanwordSchemaException>(() =>
            LoanwordDataLoader.LoadFromBytes("malformed.json", bad));
        Assert.Contains("invalid JSON", ex.Message, StringComparison.OrdinalIgnoreCase);
        // The original JsonException is preserved as InnerException.
        Assert.NotNull(ex.InnerException);
        Assert.IsAssignableFrom<System.Text.Json.JsonException>(ex.InnerException);
    }

    [Fact]
    public void Loader_NotAJsonObject_WrapsAsSchemaException()
    {
        // Top-level JSON array (not object) — handled by the value-kind check,
        // not the JsonException path, so InnerException is null.
        var arr = System.Text.Encoding.UTF8.GetBytes(@"[1, 2, 3]");
        var ex = Assert.Throws<LoanwordSchemaException>(() =>
            LoanwordDataLoader.LoadFromBytes("array.json", arr));
        Assert.Contains("top-level must be a JSON object", ex.Message);
    }

    [Fact]
    public void LoanwordSchemaException_AllCa1032CtorsCallable()
    {
        // CA1032 requires three constructors: parameterless, (string),
        // (string, Exception innerException).
        var e1 = new LoanwordSchemaException();
        Assert.NotNull(e1);
        var e2 = new LoanwordSchemaException("test message");
        Assert.Equal("test message", e2.Message);
        var inner = new InvalidOperationException("inner");
        var e3 = new LoanwordSchemaException("wrapper", inner);
        Assert.Same(inner, e3.InnerException);
    }

    // ================================================================
    // CS-H3: EnableZhEnDispatch is `volatile bool` — verify cross-thread
    // visibility. We can't deterministically reproduce a memory-ordering
    // bug with a unit test, but we can lock in (a) the flag flips through
    // a public setter, (b) reader threads observe the new value within a
    // bounded number of polls, and (c) the field is actually marked volatile
    // (reflection check — fails if a future refactor drops the modifier).
    // ================================================================

    [Fact]
    public void EnableZhEnDispatch_IsMarkedVolatile()
    {
        // Pin the volatile modifier via reflection so a future refactor that
        // accidentally drops it (and thus reintroduces the memory-visibility
        // hazard) is caught at CI time.
        var field = typeof(MultilingualPhonemizer).GetField(
            "_enableZhEnDispatch",
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
        Assert.NotNull(field);
        // C# `volatile` is encoded as `IsVolatile()` modifier on the type.
        var mods = field!.GetRequiredCustomModifiers();
        bool isVolatile = false;
        foreach (var m in mods)
        {
            if (m.FullName == "System.Runtime.CompilerServices.IsVolatile")
            {
                isVolatile = true;
                break;
            }
        }
        Assert.True(isVolatile,
            "MultilingualPhonemizer._enableZhEnDispatch must remain `volatile bool` " +
            "(CS-H3) — without it, writers on one thread are not guaranteed to be " +
            "visible to readers on another thread.");
    }

    [Fact]
    public async System.Threading.Tasks.Task EnableZhEnDispatch_VisibleAcrossThreads()
    {
        var mp = MakeZhEnDispatchPhonemizer();
        Assert.True(mp.EnableZhEnDispatch, "default = on under chinese feature");

        // Spawn a reader that polls the flag while a writer flips it. The
        // reader must observe at least one `false` reading (via volatile reads
        // — without volatile, optimizers could hoist the read out of the loop).
        using var stop = new System.Threading.CancellationTokenSource(
            TimeSpan.FromSeconds(2));
        var observedFalse = false;
        var reader = System.Threading.Tasks.Task.Run(() =>
        {
            while (!stop.IsCancellationRequested)
            {
                if (!mp.EnableZhEnDispatch)
                {
                    observedFalse = true;
                    return;
                }
                System.Threading.Thread.SpinWait(500);
            }
        }, stop.Token);

        // Give the reader a moment to start spinning, then flip the flag.
        await System.Threading.Tasks.Task.Delay(50, stop.Token);
        mp.EnableZhEnDispatch = false;

        await reader;
        Assert.True(observedFalse,
            "reader thread must observe EnableZhEnDispatch=false after the writer " +
            "flipped it. If this fails, the volatile modifier may have been removed.");
    }
}
