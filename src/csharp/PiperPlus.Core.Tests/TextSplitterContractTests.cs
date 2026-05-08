using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using PiperPlus.Core.Phonemize;
using Xunit;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Cross-runtime parity test: C# TextSplitter against contract.json.
///
/// Loads tests/fixtures/text_splitter/contract.json and asserts the C#
/// canonical implementation matches the runtimes.csharp.* projection of the
/// toml-generated fixture:
///
///   1. Each closing-punctuation codepoint listed in runtimes.csharp.closing_punctuation
///      is greedily consumed after a sentence terminator (post-consume strategy).
///   2. Each sentence-terminator codepoint listed in runtimes.csharp.sentence_terminators
///      triggers a chunk split.
///   3. The known terminator omitted from C# (U+FF0E fullwidth full stop) is
///      NOT recognised today (current divergence — pinned to detect realignment).
///
/// The drift gate (text-splitter-parity.yml) ensures the fixture stays in sync
/// with docs/spec/text-splitter-contract.toml.
/// </summary>
public class TextSplitterContractTests
{
    private static string FindFixturePath()
    {
        // PiperPlus.runsettings copies cross-runtime fixtures into TestData/.
        // First try that path; otherwise walk up to repo root and look in
        // tests/fixtures/text_splitter/.
        var here = Path.GetDirectoryName(typeof(TextSplitterContractTests).Assembly.Location)!;
        var local = Path.Join(here, "TestData", "text_splitter_contract.json");
        if (File.Exists(local))
        {
            return local;
        }

        var dir = new DirectoryInfo(here);
        while (dir != null)
        {
            var candidate = Path.Join(dir.FullName, "tests", "fixtures", "text_splitter", "contract.json");
            if (File.Exists(candidate))
            {
                return candidate;
            }
            dir = dir.Parent;
        }

        throw new FileNotFoundException(
            "Could not locate tests/fixtures/text_splitter/contract.json. Set PIPER_TEXT_SPLITTER_FIXTURE or copy via PiperPlus.runsettings."
        );
    }

    private static JsonElement LoadFixture()
    {
        var path = FindFixturePath();
        var doc = JsonDocument.Parse(File.ReadAllText(path));
        return doc.RootElement.Clone();
    }

    [Fact]
    public void Fixture_LoadsAndExposesCsharpRuntime()
    {
        var fixture = LoadFixture();
        Assert.Equal(1, fixture.GetProperty("schema_version").GetInt32());
        var csharp = fixture.GetProperty("runtimes").GetProperty("csharp");
        Assert.Equal("post-consume", csharp.GetProperty("strategy").GetString());
    }

    public static IEnumerable<object[]> CsharpClosingPunctuation()
    {
        var fixture = LoadFixture();
        var arr = fixture.GetProperty("runtimes").GetProperty("csharp").GetProperty("closing_punctuation");
        return arr.EnumerateArray().Select(v => new object[] { v.GetInt32() });
    }

    [Theory]
    [MemberData(nameof(CsharpClosingPunctuation))]
    public void Csharp_ConsumesEachListedClosingPunctuation(int codepoint)
    {
        var close = char.ConvertFromUtf32(codepoint);
        var input = $"Hi.{close} Next.";
        var chunks = TextSplitter.SplitSentences(input);
        Assert.Equal(2, chunks.Count);
        Assert.EndsWith(close, chunks[0]);
        Assert.False(chunks[1].StartsWith(close), $"closing punct U+{codepoint:X4} leaked into second chunk: {chunks[1]}");
    }

    public static IEnumerable<object[]> CsharpSentenceTerminators()
    {
        var fixture = LoadFixture();
        var arr = fixture.GetProperty("runtimes").GetProperty("csharp").GetProperty("sentence_terminators");
        return arr.EnumerateArray().Select(v => new object[] { v.GetInt32() });
    }

    [Theory]
    [MemberData(nameof(CsharpSentenceTerminators))]
    public void Csharp_SplitsOnEachListedSentenceTerminator(int codepoint)
    {
        var term = char.ConvertFromUtf32(codepoint);
        var input = $"a{term} b{term}";
        var chunks = TextSplitter.SplitSentences(input);
        Assert.Equal(2, chunks.Count);
    }

    [Fact]
    public void Csharp_DoesNotRecogniseOmittedFullwidthFullStop()
    {
        // U+FF0E is canonical but currently absent from C#'s IsSentenceTerminator.
        // A future realignment PR should update both this test and the OMITS table.
        var input = "a． b．";
        var chunks = TextSplitter.SplitSentences(input);
        Assert.Single(chunks);
    }

    [Fact]
    public void Csharp_RuntimeMatchesCanonicalExceptOmits()
    {
        // Pin the per-runtime divergence: csharp.closing == canonical.closing,
        // csharp.terminators == canonical.terminators MINUS [U+FF0E].
        var fixture = LoadFixture();
        var canonical = fixture.GetProperty("canonical");
        var csharp = fixture.GetProperty("runtimes").GetProperty("csharp");

        var canonicalClose = canonical.GetProperty("closing_punctuation").EnumerateArray()
            .Select(v => v.GetInt32()).ToHashSet();
        var csharpClose = csharp.GetProperty("closing_punctuation").EnumerateArray()
            .Select(v => v.GetInt32()).ToHashSet();
        Assert.Equal(canonicalClose, csharpClose);

        var canonicalTerm = canonical.GetProperty("sentence_terminators").EnumerateArray()
            .Select(v => v.GetInt32()).ToHashSet();
        var csharpTerm = csharp.GetProperty("sentence_terminators").EnumerateArray()
            .Select(v => v.GetInt32()).ToHashSet();

        var omitted = canonicalTerm.Except(csharpTerm).ToList();
        Assert.Equal(new[] { 0xFF0E }, omitted);
    }
}
