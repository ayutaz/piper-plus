using System.IO;
using System.Linq;
using System.Text.Json;
using PiperPlus.Core.Phonemize;

namespace PiperPlus.Core.Tests;

/// <summary>
/// English text normalization parity with Python's g2p_en (Issue #821, #832).
/// <para>
/// Reads <c>tests/fixtures/g2p/english_normalize_cases.json</c>, which
/// <c>scripts/build_english_normalize_fixture.py</c> generates from the
/// vendored Python code, the same fixture the C++, Rust and Go ports read:
/// <list type="bullet">
///   <item><c>numbers</c>: g2p_en's <c>normalize_numbers(input)</c> (inflect spelling);</item>
///   <item><c>tokens</c>: the lowercased words after number expansion, accent
///         stripping, the character filter, the i.e./e.g. replacement and
///         nltk's <c>TweetTokenizer</c>.</item>
/// </list>
/// Every case must match. All mismatches are reported at once, and a fixture
/// with no case fails rather than passing vacuously.
/// </para>
/// </summary>
public sealed class EnglishNormalizeTests
{
    private static string RepoRoot()
    {
        DirectoryInfo? d = new(AppContext.BaseDirectory);
        for (int i = 0; i < 8 && d is not null; i++)
        {
            if (Directory.Exists(Path.Join(d.FullName, "tests", "fixtures", "g2p")))
            {
                return d.FullName;
            }

            d = d.Parent;
        }

        throw new DirectoryNotFoundException(
            "Could not locate repo root from " + AppContext.BaseDirectory);
    }

    private static JsonDocument LoadFixture()
    {
        string path = Path.Join(RepoRoot(), "tests", "fixtures", "g2p", "english_normalize_cases.json");
        return JsonDocument.Parse(File.ReadAllText(path));
    }

    [Fact]
    public void NormalizeNumbers_MatchesPython()
    {
        using JsonDocument fixture = LoadFixture();
        int compared = 0;
        var failures = new List<string>();
        foreach (JsonElement c in fixture.RootElement.GetProperty("numbers").EnumerateArray())
        {
            string input = c.GetProperty("input").GetString()!;
            string expected = c.GetProperty("output").GetString()!;
            string actual = EnglishTextNormalizer.NormalizeNumbers(input);
            compared++;
            if (actual != expected)
            {
                failures.Add($"'{input}'\n  expected: '{expected}'\n  actual:   '{actual}'");
            }
        }

        Assert.True(compared > 0, "no 'numbers' case compared");
        Assert.True(
            failures.Count == 0,
            $"{failures.Count} of {compared} 'numbers' case(s) differ:\n" + string.Join("\n", failures));
    }

    [Fact]
    public void Tokens_MatchPython()
    {
        using JsonDocument fixture = LoadFixture();
        int compared = 0;
        var failures = new List<string>();
        foreach (JsonElement c in fixture.RootElement.GetProperty("tokens").EnumerateArray())
        {
            string input = c.GetProperty("input").GetString()!;
            List<string> expected = c.GetProperty("tokens").EnumerateArray().Select(t => t.GetString()!).ToList();
            List<string> actual = EnglishTextNormalizer.NormalizeAndTokenize(input)
                .Select(t => t.ToLowerInvariant())
                .ToList();
            compared++;
            if (!expected.SequenceEqual(actual))
            {
                failures.Add(
                    $"'{input}'\n  expected: [{string.Join(", ", expected)}]\n  actual:   [{string.Join(", ", actual)}]");
            }
        }

        Assert.True(compared > 0, "no 'tokens' case compared");
        Assert.True(
            failures.Count == 0,
            $"{failures.Count} of {compared} 'tokens' case(s) differ:\n" + string.Join("\n", failures));
    }

    [Fact]
    public void NormalizeNumbers_BeyondQuintillion_ReadsDigitByDigit()
    {
        Assert.Equal(
            "one two three four five six seven eight nine zero one two three four five six "
            + "seven eight nine zero one two",
            EnglishTextNormalizer.NormalizeNumbers("1234567890123456789012"));
        Assert.Equal(
            "nine hundred ninety-nine quintillion, nine hundred ninety-nine quadrillion, "
            + "nine hundred ninety-nine trillion, nine hundred ninety-nine billion, "
            + "nine hundred ninety-nine million, nine hundred ninety-nine thousand, "
            + "nine hundred ninety-nine",
            EnglishTextNormalizer.NormalizeNumbers("999999999999999999999"));
    }

    [Fact]
    public void NormalizeAndTokenize_KeepsCase()
    {
        // Python lowercases; the port keeps the case for the CamelCase split.
        Assert.Equal(
            ["ChatGPT", ",", "for", "example", "Mr", ".", "Smith"],
            EnglishTextNormalizer.NormalizeAndTokenize("ChatGPT, e.g. Mr. Smith"));
    }

    [Theory]
    [InlineData("Crème Brûlée", "Creme, Brulee")]
    [InlineData("Kelvin", "Kelvin")]
    [InlineData("a\tb\nc;d:e\"f", "a, b, cdef")]
    [InlineData("a b　c\u0085d", "a, b, c, d")]
    [InlineData("日本 ß æ", "")]
    [InlineData("I.e. x i.E.", "that, is, x, that, is")]
    [InlineData("foo.bar-baz", "foo.bar, -, baz")]
    [InlineData("!!!!", "!, !, !")]
    [InlineData("a----b", "a---b")]
    public void NormalizeAndTokenize_FoldsFiltersAndSplits(string text, string expected)
    {
        // Accents folded (NFD minus combining marks), characters outside
        // a-z A-Z ' . , ? ! - removed, any Unicode whitespace a word break,
        // i.e. / e.g. replaced ignoring case, runs of 4+ symbols shortened to 3.
        Assert.Equal(
            expected.Length == 0 ? [] : expected.Split(", "),
            EnglishTextNormalizer.NormalizeAndTokenize(text));
    }
}
