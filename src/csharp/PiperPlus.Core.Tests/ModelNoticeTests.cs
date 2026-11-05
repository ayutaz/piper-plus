using System.Text.Json;
using PiperPlus.Core.Config;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Model usage notice (docs/reference/model-resolution.md §9): detection by
/// <see cref="ModelManager.GetModelNotice(string)"/>, the catalog copy of the
/// canonical notice, and the <c>PIPER_PLUS_DISABLE_MODEL_NOTICE</c> value rule.
/// Pure functions only — no console or environment mutation here (see
/// <see cref="ModelNoticeEnvTests"/> for the environment-reading path).
/// </summary>
public sealed class ModelNoticeTests
{
    private const string TsukuyomiKey = "ja_JP-tsukuyomi-chan-medium";

    internal static string RepoRoot()
    {
        DirectoryInfo? d = new(AppContext.BaseDirectory);
        for (int i = 0; i < 8 && d is not null; i++)
        {
            if (File.Exists(Path.Join(d.FullName, "test", "model_resolution_vectors.json")))
            {
                return d.FullName;
            }

            d = d.Parent;
        }

        throw new DirectoryNotFoundException(
            "Could not locate repo root from " + AppContext.BaseDirectory);
    }

    private static (string[] Notice, string[] NoticeFiles) LoadCanonicalTsukuyomi()
    {
        string path = Path.Join(RepoRoot(), "test", "model_resolution_vectors.json");
        using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(path));
        JsonElement entry = doc.RootElement.GetProperty("voice_catalog").GetProperty(TsukuyomiKey);
        return (
            entry.GetProperty("notice").EnumerateArray().Select(e => e.GetString()!).ToArray(),
            entry.GetProperty("notice_files").EnumerateArray().Select(e => e.GetString()!).ToArray());
    }

    private static VoiceInfo Tsukuyomi()
        => VoiceCatalog.LoadBuiltInCatalog().Single(v => v.Key == TsukuyomiKey);

    // ================================================================
    // Catalog copy of the canonical notice
    // ================================================================
    [Fact]
    public void Catalog_TsukuyomiNotice_MatchesCanonicalVectors()
    {
        (string[] notice, string[] noticeFiles) = LoadCanonicalTsukuyomi();

        Assert.Equal(notice, Tsukuyomi().Notice);
        Assert.Equal(noticeFiles, Tsukuyomi().NoticeFiles);
    }

    [Theory]
    [InlineData("ja_JP-css10-6lang-medium")]
    [InlineData("multilingual-zero-shot-base-zs-v1")]
    public void Catalog_OtherModels_HaveNoNotice(string key)
    {
        VoiceInfo voice = VoiceCatalog.LoadBuiltInCatalog().Single(v => v.Key == key);

        Assert.Empty(voice.Notice);
        Assert.Empty(voice.NoticeFiles);
    }

    // ================================================================
    // Detection
    // ================================================================
    [Theory]
    [InlineData("ja_JP-tsukuyomi-chan-medium")]
    [InlineData("tsukuyomi")]
    [InlineData("tsukuyomi-chan")]
    [InlineData("ja-tsukuyomi")]
    [InlineData("ayousanz/piper-plus-tsukuyomi-chan")]
    [InlineData("  tsukuyomi  ")]
    [InlineData("https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/model.onnx")]
    [InlineData("https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/main")]
    [InlineData("tsukuyomi.onnx")]
    [InlineData("tsukuyomi-chan-6lang-fp16.onnx")]
    [InlineData("/home/user/models/tsukuyomi.onnx")]
    [InlineData("./tsukuyomi-chan-6lang-fp16.onnx")]
    [InlineData(@"C:\Users\user\models\tsukuyomi-chan-6lang-fp16.onnx")]
    [InlineData(@"models\tsukuyomi.onnx")]
    [InlineData("C:/mixed\\sep/tsukuyomi.onnx")]
    public void GetModelNotice_Tsukuyomi_ReturnsNotice(string input)
    {
        IReadOnlyList<string> notice = ModelManager.GetModelNotice(input);

        Assert.Equal(Tsukuyomi().Notice, notice);
        Assert.Equal(6, notice.Count);
    }

    [Theory]
    [InlineData("css10")]
    [InlineData("ja_JP-css10-6lang-medium")]
    [InlineData("ayousanz/piper-plus-css10-ja-6lang")]
    [InlineData("/models/css10-ja-6lang-fp16.onnx")]
    [InlineData("base")]
    [InlineData("multilingual-zero-shot-base-zs-v1")]
    [InlineData("ayousanz/piper-plus-base")]
    [InlineData("https://huggingface.co/ayousanz/piper-plus-base/resolve/main/releases/zs-v1/base.onnx")]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("unknown-model")]
    [InlineData("Tsukuyomi")]
    [InlineData("/models/TSUKUYOMI.ONNX")]
    [InlineData("/models/tsukuyomi.onnx.json")]
    [InlineData("/models/tsukuyomi.onnx/other.onnx")]
    [InlineData("/data/ayousanz/piper-plus-tsukuyomi-chan/model.onnx")]
    [InlineData("https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan-other/model.onnx")]
    public void GetModelNotice_OtherInputs_ReturnsEmpty(string input)
    {
        Assert.Empty(ModelManager.GetModelNotice(input));
    }

    [Fact]
    public void GetModelNotice_Null_ReturnsEmpty()
    {
        Assert.Empty(ModelManager.GetModelNotice(null, VoiceCatalog.LoadBuiltInCatalog()));
    }

    [Fact]
    public void GetModelNotice_ExternalEntryWithNotice_IsDetected()
    {
        VoiceInfo custom = new(
            Key: "xx-custom-medium", Name: "custom", LanguageCode: "xx", LanguageFamily: "xx",
            LanguageNameNative: "X", LanguageNameEnglish: "X", Quality: "medium",
            NumSpeakers: 1, Source: "piper-plus", RepoId: "someone/custom-voice",
            Files: [], Aliases: ["custom"])
        {
            Notice = ["line 1", "line 2"],
            NoticeFiles = ["custom.onnx"],
        };

        Assert.Equal(["line 1", "line 2"], ModelManager.GetModelNotice("custom", [custom]));
        Assert.Equal(["line 1", "line 2"], ModelManager.GetModelNotice("/a/custom.onnx", [custom]));
        Assert.Empty(ModelManager.GetModelNotice("custom", []));
    }

    // ================================================================
    // Footer and disable rule
    // ================================================================
    [Fact]
    public void Footer_MatchesSpec()
    {
        Assert.Equal(
            "(この表示は PIPER_PLUS_DISABLE_MODEL_NOTICE=1 で消せます / Set PIPER_PLUS_DISABLE_MODEL_NOTICE=1 to hide this notice.)",
            ModelManager.ModelNoticeFooter);
        Assert.Equal("PIPER_PLUS_DISABLE_MODEL_NOTICE", ModelManager.DisableModelNoticeEnvVar);
    }

    [Theory]
    [InlineData("1", true)]
    [InlineData("true", true)]
    [InlineData(" TRUE ", true)]
    [InlineData("yes", true)]
    [InlineData("Yes\n", true)]
    [InlineData("0", false)]
    [InlineData("false", false)]
    [InlineData("no", false)]
    [InlineData("on", false)]
    [InlineData("", false)]
    [InlineData("   ", false)]
    [InlineData(null, false)]
    public void IsModelNoticeDisabled_ValueRule(string? value, bool expected)
    {
        Assert.Equal(expected, ModelManager.IsModelNoticeDisabled(value));
    }
}

/// <summary>
/// Reads <c>PIPER_PLUS_DISABLE_MODEL_NOTICE</c> from the process environment.
/// Member of the <c>EnvVars</c> collection because it mutates the environment.
/// </summary>
[Collection("EnvVars")]
public sealed class ModelNoticeEnvTests
{
    [Theory]
    [InlineData(" TRUE ", true)]
    [InlineData("yes", true)]
    [InlineData("1", true)]
    [InlineData("0", false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    public void IsModelNoticeDisabled_ReadsEnvironment(string? value, bool expected)
    {
        string? original = Environment.GetEnvironmentVariable(ModelManager.DisableModelNoticeEnvVar);
        try
        {
            Environment.SetEnvironmentVariable(ModelManager.DisableModelNoticeEnvVar, value);
            Assert.Equal(expected, ModelManager.IsModelNoticeDisabled());
        }
        finally
        {
            Environment.SetEnvironmentVariable(ModelManager.DisableModelNoticeEnvVar, original);
        }
    }
}
