using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using PiperPlus.Core.Phonemize;
using Xunit;

namespace PiperPlus.Cli.Tests;

/// <summary>
/// <c>--language en / es / pt / fr</c> are read by the PiperPlus.Core engines
/// that port the Python G2P (<see cref="EnglishG2PEngine"/>,
/// <see cref="SpanishG2PEngine"/>, <see cref="PortugueseG2PEngine"/>,
/// <see cref="FrenchG2PEngine"/>), not by the external DotNetG2P.English /
/// .Spanish / .Portuguese / .French packages, whose rules and dictionaries
/// differ from the ones the models were trained with (Issue #832, #822, #821).
/// </summary>
public class TextModeCoreEnginesTests
{
#pragma warning disable IL2026 // the CLI suppresses the same warning at its call sites
    private static IPhonemizer CliPhonemizer(string language) =>
        Program.ResolveTextModePhonemizer(language);
#pragma warning restore IL2026

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

    /// <summary>The engine over the canonical CMU dictionary in the repository.</summary>
    private static EnglishG2PEngine CanonicalEnglishEngine()
    {
        using FileStream stream = File.OpenRead(
            Path.Join(RepoRoot(), "src", "rust", "piper-plus-g2p", "data", "cmudict_data.json"));
        return EnglishG2PEngine.FromJson(stream);
    }

    /// <summary>
    /// The CLI assembly does not reference the package, and the package is not
    /// among the CLI's dependencies: a PackageReference in PiperPlus.Cli.csproj
    /// would put it in this test project's deps.json even while unused.
    /// </summary>
    [Theory]
    [InlineData("DotNetG2P.English")]
    [InlineData("DotNetG2P.Spanish")]
    [InlineData("DotNetG2P.Portuguese")]
    [InlineData("DotNetG2P.French")]
    public void Cli_DoesNotDependOnExternalG2PPackage(string package)
    {
#pragma warning disable IL2026 // the tests are not trimmed
        Assert.DoesNotContain(
            typeof(Program).Assembly.GetReferencedAssemblies(),
            a => string.Equals(a.Name, package, StringComparison.Ordinal));
#pragma warning restore IL2026

        string depsFile = Path.Join(
            AppContext.BaseDirectory,
            typeof(TextModeCoreEnginesTests).Assembly.GetName().Name + ".deps.json");
        using JsonDocument deps = JsonDocument.Parse(File.ReadAllText(depsFile));
        List<string> libraries = deps.RootElement.GetProperty("libraries")
            .EnumerateObject()
            .Select(p => p.Name)
            .ToList();

        Assert.NotEmpty(libraries);
        Assert.DoesNotContain(libraries, name => name.StartsWith(package + "/", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData("en", "It's 3 o'clock, e.g. at café ChatGPT.")]
    [InlineData("es", "¿Dónde está el baño?")]
    [InlineData("pt", "Bom dia, como você está?")]
    [InlineData("fr", "Les amis sont là.")]
    public void ResolveTextModePhonemizer_ReadsWithTheCoreEngine(string language, string text)
    {
        IPhonemizer core = language switch
        {
            "en" => new EnglishPhonemizer(CanonicalEnglishEngine()),
            "es" => new SpanishPhonemizer(new SpanishG2PEngine()),
            "pt" => new PortuguesePhonemizer(new PortugueseG2PEngine()),
            _ => new FrenchPhonemizer(new FrenchG2PEngine()),
        };
        var expected = new MultilingualPhonemizer(
            new Dictionary<string, IPhonemizer> { [language] = core },
            language);

        Assert.Equal(expected.Phonemize(text), CliPhonemizer(language).Phonemize(text));
    }
}
