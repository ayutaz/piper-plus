using System.IO;
using System.Linq;
using System.Text;
using PiperPlus.Core.Mapping;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Unit tests for <see cref="PinyinDictionaryChineseG2PEngine"/> with small
/// dictionaries. The golden comparison in PiperPlus.Cli.Tests covers the
/// shipped dictionaries; these pin the paths its sentences do not reach
/// (erhua, phrases longer than two characters, unknown characters) and the
/// A1/A2/A3 prosody, following the Go implementation it was ported from.
/// </summary>
public sealed class PinyinDictionaryChineseG2PEngineTests
{
    private static readonly string[] ToneTokens = ["tone1", "tone2", "tone3", "tone4", "tone5"];

    private static PinyinDictionaryChineseG2PEngine Engine(
        Dictionary<int, string>? single = null,
        Dictionary<string, string[]>? phrases = null) =>
        new(single ?? [], phrases ?? []);

    private static string[] Tones(ChineseG2PResult result) =>
        result.Phonemes
            .Select(p => OpenJTalkToPiperMapping.CharToToken.TryGetValue(p[0], out string? t) ? t : p)
            .Where(t => ToneTokens.Contains(t))
            .ToArray();

    [Fact]
    public void LongestPhraseWinsOverShorterPrefix()
    {
        var engine = Engine(phrases: new()
        {
            ["中华"] = ["zhong1", "hua2"],
            ["中华人"] = ["zhong4", "hua4", "ren4"],
        });

        Assert.Equal(["tone4", "tone4", "tone4"], Tones(engine.Convert("中华人")));
    }

    [Fact]
    public void ErhuaInsertsRhotacizedVowelBeforeTone()
    {
        var engine = Engine(single: new() { ['玩'] = "wanr2" });

        List<string> expected = PinyinToIpa.Convert("uan", 2);
        expected.Insert(expected.Count - 1, "ɚ");
        Assert.Equal(OpenJTalkToPiperMapping.MapSequence(expected), engine.Convert("玩").Phonemes);
    }

    [Fact]
    public void StandaloneErIsNotErhua()
    {
        var engine = Engine(single: new() { ['儿'] = "er2" });

        Assert.Equal(OpenJTalkToPiperMapping.MapSequence(["ɚ", "tone2"]), engine.Convert("儿").Phonemes);
    }

    [Fact]
    public void ProsodyCarriesToneAndPositionInEachRun()
    {
        var engine = Engine(single: new()
        {
            ['你'] = "ni3",
            ['好'] = "hao3",
            ['世'] = "shi4",
            ['界'] = "jie4",
        });

        ChineseG2PResult result = engine.Convert("你好。世界");

        // 你 gets the 3-3 sandhi; 。 becomes "." with zero prosody and ends the run.
        int dot = result.Phonemes.ToList().IndexOf(".");
        Assert.True(dot > 0);
        Assert.Equal((0, 0, 0), (result.A1[dot], result.A2[dot], result.A3[dot]));
        Assert.Equal((2, 1, 2), (result.A1[0], result.A2[0], result.A3[0]));
        Assert.Equal((3, 2, 2), (result.A1[dot - 1], result.A2[dot - 1], result.A3[dot - 1]));
        Assert.Equal((4, 1, 2), (result.A1[dot + 1], result.A2[dot + 1], result.A3[dot + 1]));
        Assert.Equal((4, 2, 2), (result.A1[^1], result.A2[^1], result.A3[^1]));
    }

    [Fact]
    public void UnknownCharacterIsSkippedAndSplitsTheSandhiGroup()
    {
        var engine = Engine(single: new() { ['你'] = "ni3", ['好'] = "hao3" });

        Assert.Equal(["tone3", "tone3"], Tones(engine.Convert("你龘好")));
    }

    [Fact]
    public void FromJsonUsesFirstReadingAndFirstPhraseAlternative()
    {
        using var single = new MemoryStream(Encoding.UTF8.GetBytes("{\"34892\": \"hang2,xing2\"}"));
        using var phrases = new MemoryStream(Encoding.UTF8.GetBytes(
            "{\"银行\": [[\"yin2\"], [\"hang2\", \"xing2\"]]}"));
        PinyinDictionaryChineseG2PEngine engine = PinyinDictionaryChineseG2PEngine.FromJson(single, phrases);

        IReadOnlyList<string> hang = engine.Convert("行").Phonemes;
        IReadOnlyList<string> bank = engine.Convert("银行").Phonemes;
        Assert.Equal(["tone2"], Tones(engine.Convert("行")));
        Assert.Equal(["tone2", "tone2"], Tones(engine.Convert("银行")));
        Assert.Equal(hang, bank.Skip(bank.Count - hang.Count));
    }
}
