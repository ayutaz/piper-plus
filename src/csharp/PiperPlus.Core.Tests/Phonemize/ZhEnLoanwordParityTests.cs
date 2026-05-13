using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using PiperPlus.Core.Phonemize;
using Xunit;

namespace PiperPlus.Core.Tests.Phonemize;

/// <summary>
/// ZH-EN code-switching loanword parity test (C# mirror).
///
/// <para>
/// Loads <c>tests/fixtures/g2p/zh_en_loanword_matrix.json</c> (the canonical
/// cross-runtime fixture introduced in Issue #384 / PR #397) and verifies
/// that the C# <see cref="ChinesePhonemizer.PhonemizeEmbeddedEnglish"/> path
/// (which delegates to <see cref="ChineseEmbeddedEnglish.Convert"/>) agrees
/// with the expected token-count contracts encoded in each case.
/// </para>
/// <para>
/// This test is intentionally a thin parity layer on top of the existing
/// <c>ChineseEmbeddedEnglishTests</c>: those tests pin behavior using
/// hard-coded inputs; this one drives the same logic from the JSON matrix
/// so a future fixture update (e.g. new acronym, new equivalence class) is
/// automatically picked up without editing C# source.
/// </para>
/// <para>
/// Sister tests in Python/Rust/Go/WASM/C++ consume the same fixture; drift
/// between any runtime is caught locally by their respective parity tests
/// plus the global <c>scripts/check_loanword_consistency.py</c> CI gate.
/// </para>
/// </summary>
public sealed class ZhEnLoanwordParityTests
{
    private static readonly Lazy<JsonElement> FixtureRoot = new(LoadFixtureRoot);

    /// <summary>Minimal engine stub: only the default
    /// <see cref="IChineseG2PEngine.ConvertEmbeddedEnglish"/> path is exercised
    /// here (delegates to <see cref="ChineseEmbeddedEnglish.Convert"/>).
    /// <c>Convert</c> for pure Chinese is unused by these tests.</summary>
    private sealed class StubEngine : IChineseG2PEngine
    {
        public ChineseG2PResult Convert(string text) => new(
            Array.Empty<string>(),
            Array.Empty<int>(),
            Array.Empty<int>(),
            Array.Empty<int>());
    }

    /// <summary>Test theory: every case name in the fixture's <c>cases</c>
    /// array becomes one parameterized run. The fixture itself decides which
    /// assertions apply (count / equiv / equiv_sum / relation / forward-compat).</summary>
    public static IEnumerable<object[]> CaseNames()
    {
        JsonElement root = FixtureRoot.Value;
        foreach (JsonElement caseElement in root.GetProperty("cases").EnumerateArray())
        {
            yield return new object[] { caseElement.GetProperty("name").GetString()! };
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
    [MemberData(nameof(CaseNames))]
    public void Parity_FixtureCase(string caseName)
    {
        JsonElement caseElement = FindCase(caseName);

        // Forward-compat case: feeds input_json (not input) to the loader and
        // asserts no exception. Mirrors the Python schema_version=2 loader pin.
        if (caseElement.TryGetProperty("input_json", out JsonElement inputJson))
        {
            byte[] bytes = System.Text.Encoding.UTF8.GetBytes(inputJson.GetRawText());
            PiperPlus.Core.Phonemize.Data.LoanwordData data =
                PiperPlus.Core.Phonemize.Data.LoanwordDataLoader.LoadFromBytes(
                    $"{caseName}.json", bytes);
            Assert.NotNull(data);
            return;
        }

        string input = caseElement.GetProperty("input").GetString()!;
        IReadOnlyList<string> tokens = PhonemizeViaChinesePhonemizer(input);

        // Case dispatch: each fixture entry declares its assertion shape via
        // one of the documented keys. Cases that only carry `notes` (no
        // assertion key) are smoke-tested for "no exception + non-null".
        if (caseElement.TryGetProperty("expected_token_count", out JsonElement expectedCount))
        {
            Assert.Equal(expectedCount.GetInt32(), tokens.Count);
            return;
        }

        if (caseElement.TryGetProperty("expected_token_count_equiv", out JsonElement equivInput))
        {
            // The fixture's *_equiv* fields reference the bare input string
            // (e.g. "GPS"), not a case name. Phonemize that reference input
            // directly and compare token counts.
            IReadOnlyList<string> referenceTokens = PhonemizeViaChinesePhonemizer(
                equivInput.GetString()!);
            Assert.Equal(referenceTokens.Count, tokens.Count);
            return;
        }

        if (caseElement.TryGetProperty("expected_token_count_equiv_sum", out JsonElement sumArr))
        {
            int sum = 0;
            foreach (JsonElement other in sumArr.EnumerateArray())
            {
                sum += PhonemizeViaChinesePhonemizer(other.GetString()!).Count;
            }

            Assert.Equal(sum, tokens.Count);
            return;
        }

        if (caseElement.TryGetProperty("expected_token_count_relation", out JsonElement relation))
        {
            // Currently only `2x_of_input_Z` is encoded in the fixture.
            string rel = relation.GetString()!;
            if (rel == "2x_of_input_Z")
            {
                IReadOnlyList<string> z = PhonemizeViaChinesePhonemizer("Z");
                Assert.Equal(z.Count * 2, tokens.Count);
            }
            else
            {
                throw new InvalidOperationException(
                    $"Unknown expected_token_count_relation '{rel}' in case '{caseName}'. " +
                    "Update ZhEnLoanwordParityTests.Parity_FixtureCase to handle this relation.");
            }

            return;
        }

        if (caseElement.TryGetProperty("expected_token_count_differs_from", out JsonElement differs))
        {
            // Same convention as *_equiv: the value is the reference input string.
            IReadOnlyList<string> other = PhonemizeViaChinesePhonemizer(differs.GetString()!);
            Assert.NotEmpty(tokens);
            Assert.NotEmpty(other);
            Assert.NotEqual(other.Count, tokens.Count);
            return;
        }

        // No assertion key — smoke test only (Issue-384 worked-example cases
        // that document realistic full-sentence inputs; per-runtime exactness
        // is verified by the existing hard-coded ChineseEmbeddedEnglishTests).
        Assert.NotNull(tokens);
    }

    private static IReadOnlyList<string> PhonemizeViaChinesePhonemizer(string text)
    {
        // Use the public ChinesePhonemizer API rather than calling
        // ChineseEmbeddedEnglish.Convert directly, so we exercise the same
        // surface a downstream NuGet consumer would use.
        var phonemizer = new ChinesePhonemizer(new StubEngine());
        return phonemizer.PhonemizeEmbeddedEnglish(text);
    }

    private static JsonElement FindCase(string caseName)
    {
        foreach (JsonElement c in FixtureRoot.Value.GetProperty("cases").EnumerateArray())
        {
            if (c.GetProperty("name").GetString() == caseName)
            {
                return c;
            }
        }

        throw new InvalidOperationException(
            $"Fixture case '{caseName}' not found in zh_en_loanword_matrix.json");
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
        // Mirrors the resolver in OrtSessionContractTests / TextSplitterContractTests.
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            string candidate = Path.Join(
                dir.FullName, "tests", "fixtures", "g2p", "zh_en_loanword_matrix.json");
            if (File.Exists(candidate))
            {
                return candidate;
            }

            dir = dir.Parent;
        }

        throw new FileNotFoundException(
            "Could not locate tests/fixtures/g2p/zh_en_loanword_matrix.json. " +
            "Run dotnet test from the repo root or set the working directory accordingly.");
    }
}
