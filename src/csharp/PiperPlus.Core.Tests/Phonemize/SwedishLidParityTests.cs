using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using PiperPlus.Core.Phonemize;
using Xunit;

namespace PiperPlus.Core.Tests.Phonemize;

/// <summary>
/// Cross-runtime Swedish per-word LID parity fixture matrix (Issue #539).
///
/// <para>
/// Loads the canonical <c>tests/fixtures/g2p/swedish_lid_matrix.json</c> — the
/// single shared fixture that EVERY runtime asserts against, mirrored
/// byte-for-byte into each runtime's test dir (including
/// <c>PiperPlus.Core.Tests/Phonemize/TestData/swedish_lid_matrix.json</c>) by
/// <c>scripts/check_swedish_lid_consistency.py</c> — and verifies that the C#
/// <see cref="UnicodeLanguageDetector.SegmentText"/> per-word Swedish post-pass
/// agrees with each case's <c>expect_contains_sv</c> flag.
/// </para>
/// <para>
/// Each case builds a detector with <c>languages = fixture["languages"]</c> and
/// <c>defaultLatinLanguage = fixture["default_latin"]</c>, runs segmentation,
/// and asserts <c>("sv" in segment languages) == expect_contains_sv</c>. The
/// sister tests in Python / Rust×2 / Go / C++ / WASM consume the SAME fixture,
/// so cross-runtime agreement on these cases is the parity proof.
/// </para>
/// <para>
/// Modeled on <see cref="ZhEnLoanwordParityTests"/> (same canonical-fixture
/// walk-up resolver).
/// </para>
/// </summary>
public sealed class SwedishLidParityTests
{
    private static readonly Lazy<JsonElement> FixtureRoot = new(LoadFixtureRoot);

    public static IEnumerable<object[]> Cases()
    {
        JsonElement root = FixtureRoot.Value;
        foreach (JsonElement caseElement in root.GetProperty("cases").EnumerateArray())
        {
            yield return new object[]
            {
                caseElement.GetProperty("text").GetString()!,
                caseElement.GetProperty("expect_contains_sv").GetBoolean(),
            };
        }
    }

    [Fact]
    public void Fixture_HasExpectedSchemaVersion()
    {
        JsonElement root = FixtureRoot.Value;
        Assert.True(
            root.TryGetProperty("schema_version", out JsonElement schemaVersion),
            "fixture must declare schema_version");
        Assert.Equal(1, schemaVersion.GetInt32());
    }

    [Fact]
    public void Fixture_HasNonEmptyCases()
    {
        JsonElement root = FixtureRoot.Value;
        Assert.True(root.TryGetProperty("cases", out JsonElement cases));
        Assert.True(
            cases.GetArrayLength() >= 10,
            $"expected at least 10 fixture cases, got {cases.GetArrayLength()}");
    }

    [Theory]
    [MemberData(nameof(Cases))]
    public void Parity_FixtureCase(string text, bool expectContainsSv)
    {
        JsonElement root = FixtureRoot.Value;
        string[] languages = ReadStringArray(root, "languages");
        string defaultLatin = root.GetProperty("default_latin").GetString()!;

        var detector = new UnicodeLanguageDetector(
            languages, defaultLatinLanguage: defaultLatin);

        bool containsSv = false;
        foreach ((string lang, string _) in detector.SegmentText(text))
        {
            if (lang == "sv")
            {
                containsSv = true;
                break;
            }
        }

        Assert.True(
            containsSv == expectContainsSv,
            $"[sv-lid] \"{text}\": expected contains_sv={expectContainsSv}, " +
            $"got {containsSv}. If intentional, update " +
            "tests/fixtures/g2p/swedish_lid_matrix.json and re-sync via " +
            "`python scripts/check_swedish_lid_consistency.py --fix`.");
    }

    private static string[] ReadStringArray(JsonElement root, string property)
    {
        var list = new List<string>();
        foreach (JsonElement element in root.GetProperty(property).EnumerateArray())
        {
            list.Add(element.GetString()!);
        }

        return list.ToArray();
    }

    private static JsonElement LoadFixtureRoot()
    {
        string path = ResolveFixturePath();
        string json = File.ReadAllText(path);
        return JsonDocument.Parse(json).RootElement.Clone();
    }

    private static string ResolveFixturePath()
    {
        // Walk up from the test bin directory until we find tests/fixtures.
        // Mirrors the resolver in ZhEnLoanwordParityTests.
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            string candidate = Path.Join(
                dir.FullName, "tests", "fixtures", "g2p", "swedish_lid_matrix.json");
            if (File.Exists(candidate))
            {
                return candidate;
            }

            dir = dir.Parent;
        }

        throw new FileNotFoundException(
            "Could not locate tests/fixtures/g2p/swedish_lid_matrix.json. " +
            "Run dotnet test from the repo root or set the working directory accordingly.");
    }
}
