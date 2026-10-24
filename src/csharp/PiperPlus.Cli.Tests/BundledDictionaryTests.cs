using System;
using System.IO;
using System.Security.Cryptography;
using Xunit;

namespace PiperPlus.Cli.Tests;

/// <summary>
/// The dictionaries embedded in the CLI are the canonical copies in
/// <c>src/rust/piper-plus-g2p/data</c>, byte for byte. PiperPlus.Cli.csproj
/// links those files instead of keeping its own copies, so a copy that drifts
/// (or a link that is redirected to another file) fails here.
/// </summary>
public class BundledDictionaryTests
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

    [Theory]
    [InlineData("PiperPlus.Cli.cmudict_data.json", "cmudict_data.json")]
    [InlineData("PiperPlus.Cli.pinyin_single.json", "pinyin_single.json")]
    [InlineData("PiperPlus.Cli.pinyin_phrases.json", "pinyin_phrases.json")]
    public void EmbeddedDictionary_IsTheCanonicalFile(string resource, string canonical)
    {
        using Stream? embedded = typeof(Program).Assembly.GetManifestResourceStream(resource);
        Assert.NotNull(embedded);

        byte[] expected = File.ReadAllBytes(
            Path.Join(RepoRoot(), "src", "rust", "piper-plus-g2p", "data", canonical));
        Assert.NotEmpty(expected);
        Assert.Equal(SHA256.HashData(expected), SHA256.HashData(embedded));
    }

    /// <summary>
    /// Every embedded dictionary is redistributed in the NuGet package, so its
    /// license must ship with it: THIRD_PARTY_NOTICES.md is packed and names
    /// each embedded file.
    /// </summary>
    [Fact]
    public void EmbeddedDictionaries_HaveTheirLicensesPacked()
    {
        string cliDir = Path.Join(RepoRoot(), "src", "csharp", "PiperPlus.Cli");
        string csproj = File.ReadAllText(Path.Join(cliDir, "PiperPlus.Cli.csproj"));
        Assert.Contains(
            "<None Include=\"THIRD_PARTY_NOTICES.md\" Pack=\"true\" PackagePath=\"/\" />",
            csproj,
            StringComparison.Ordinal);

        string notices = File.ReadAllText(Path.Join(cliDir, "THIRD_PARTY_NOTICES.md"));
        int dictionaries = 0;
        foreach (string resource in typeof(Program).Assembly.GetManifestResourceNames())
        {
            if (!resource.EndsWith(".json", StringComparison.Ordinal))
            {
                continue;
            }

            dictionaries++;
            string file = resource["PiperPlus.Cli.".Length..];
            Assert.Contains("`" + file + "`", notices, StringComparison.Ordinal);
        }

        Assert.True(dictionaries >= 3, "expected the CMU and pinyin dictionaries to be embedded");
        Assert.Contains("CMU Pronouncing Dictionary License", notices, StringComparison.Ordinal);
        Assert.Contains("pypinyin License (MIT)", notices, StringComparison.Ordinal);
    }
}
