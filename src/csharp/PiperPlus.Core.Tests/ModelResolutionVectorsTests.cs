using System.Text.Json;
using PiperPlus.Core.Config;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Every key and alias of each canonical <c>voice_catalog</c> entry in
/// <c>test/model_resolution_vectors.json</c> must resolve to that entry's
/// <c>repo_id</c>, <c>onnx_file</c>, <c>config_file</c> and <c>revision</c>
/// (docs/reference/model-resolution.md).
/// </summary>
public sealed class ModelResolutionVectorsTests
{
    private sealed record CanonicalEntry(
        string Key, string RepoId, string OnnxFile, string ConfigFile, string Revision);

    private static List<(CanonicalEntry Entry, string Name)> LoadCanonicalNames()
    {
        string path = Path.Join(
            ModelNoticeTests.RepoRoot(), "test", "model_resolution_vectors.json");
        using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(path));
        var result = new List<(CanonicalEntry, string)>();
        foreach (JsonProperty prop in doc.RootElement.GetProperty("voice_catalog").EnumerateObject())
        {
            if (prop.Name.StartsWith('_'))
            {
                continue;
            }

            JsonElement e = prop.Value;
            var entry = new CanonicalEntry(
                e.GetProperty("key").GetString()!,
                e.GetProperty("repo_id").GetString()!,
                e.GetProperty("onnx_file").GetString()!,
                e.GetProperty("config_file").GetString()!,
                e.TryGetProperty("revision", out JsonElement rev) ? rev.GetString()! : "main");
            result.Add((entry, entry.Key));
            foreach (JsonElement alias in e.GetProperty("aliases").EnumerateArray())
            {
                result.Add((entry, alias.GetString()!));
            }
        }

        return result;
    }

    public static TheoryData<string> CanonicalNames()
    {
        var data = new TheoryData<string>();
        foreach ((_, string name) in LoadCanonicalNames())
        {
            data.Add(name);
        }

        return data;
    }

    private static CanonicalEntry EntryFor(string name)
        => LoadCanonicalNames().First(p => p.Name == name).Entry;

    [Fact]
    public void CanonicalNames_IncludeRepoIds()
    {
        // Guard against the vectors silently losing the repo-ID aliases.
        List<string> names = LoadCanonicalNames().Select(p => p.Name).ToList();

        Assert.Contains("ayousanz/piper-plus-tsukuyomi-chan", names);
        Assert.Contains("ayousanz/piper-plus-css10-ja-6lang", names);
        Assert.Contains("ayousanz/piper-plus-base", names);
    }

    [Theory]
    [MemberData(nameof(CanonicalNames))]
    public void FindVoice_CanonicalName_ResolvesToCanonicalEntry(string name)
    {
        CanonicalEntry expected = EntryFor(name);

        VoiceInfo? voice = ModelManager.FindVoice(name);

        Assert.NotNull(voice);
        Assert.Equal(expected.Key, voice!.Key);
        Assert.Equal(expected.RepoId, voice.RepoId);
        Assert.Equal(expected.Revision, voice.Revision);
        Assert.Equal(
            expected.OnnxFile,
            voice.Files.First(f => f.RelativePath.EndsWith(".onnx", StringComparison.OrdinalIgnoreCase))
                .RelativePath);
        Assert.Contains(voice.Files, f => f.RelativePath == expected.ConfigFile);
    }

    [Theory]
    [MemberData(nameof(CanonicalNames))]
    public async Task ResolveModelPathAsync_CanonicalName_UsesCachedCatalogFiles(string name)
    {
        // A name that is not an existing file (repo IDs included) must go
        // through the catalog entry, not be treated as a path or generic repo.
        CanonicalEntry expected = EntryFor(name);
        string dir = Path.Join(Path.GetTempPath(), "piper-plus-resolve-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            foreach (string file in new[] { expected.OnnxFile, expected.ConfigFile })
            {
                File.WriteAllText(Path.Join(dir, Path.GetFileName(file)), "x");
            }

            string resolved = await ModelManager.ResolveModelPathAsync(
                name, dir, TestContext.Current.CancellationToken);

            Assert.Equal(Path.Join(dir, Path.GetFileName(expected.OnnxFile)), resolved);
        }
        finally
        {
            Directory.Delete(dir, recursive: true);
        }
    }
}
