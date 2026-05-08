using System.IO;
using System.Text.Json;
using Microsoft.ML.OnnxRuntime;
using PiperPlus.Core.Inference;
using Xunit;

namespace PiperPlus.Core.Tests;

/// <summary>
/// ORT session contract parity test (C# runtime).
///
/// Loads tests/fixtures/ort_session/contract.json and verifies that the
/// C# implementation in <see cref="SessionFactory"/> agrees with the
/// canonical contract values for graph optimization level, intra/inter
/// threads, memory arena, warmup parameters, cache file extensions, and
/// env vars. Sister tests in Python/Rust/Go load the same fixture and
/// assert their own runtime constants — drift in any of them is caught
/// locally.
/// </summary>
public class OrtSessionContractTests
{
    private static readonly string FixturePath = ResolveFixturePath();

    private static string ResolveFixturePath()
    {
        // Walk up from the test bin directory until we find tests/fixtures.
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(
                dir.FullName, "tests", "fixtures", "ort_session", "contract.json");
            if (File.Exists(candidate))
            {
                return candidate;
            }
            dir = dir.Parent;
        }
        throw new FileNotFoundException(
            "Could not locate tests/fixtures/ort_session/contract.json");
    }

    private static JsonElement LoadFixture()
    {
        var text = File.ReadAllText(FixturePath);
        return JsonDocument.Parse(text).RootElement.Clone();
    }

    [Fact]
    public void Fixture_HasExpectedSchemaVersion()
    {
        var fixture = LoadFixture();
        Assert.Equal(1, fixture.GetProperty("schema_version").GetInt32());
    }

    [Fact]
    public void Fixture_HasAllRequiredSections()
    {
        var fixture = LoadFixture();
        foreach (var section in new[] { "session", "warmup", "cache", "env_vars" })
        {
            Assert.True(
                fixture.TryGetProperty(section, out _),
                $"fixture missing '{section}' section");
        }
    }

    [Fact]
    public void Session_GraphOptimizationLevel_MatchesContract()
    {
        var fixture = LoadFixture();
        Assert.Equal(
            "ORT_ENABLE_ALL",
            fixture.GetProperty("session").GetProperty("graph_optimization_level").GetString());

        using var options = SessionFactory.ConfigureSessionOptions();
        Assert.Equal(GraphOptimizationLevel.ORT_ENABLE_ALL, options.GraphOptimizationLevel);
    }

    [Fact]
    public void Session_ExecutionMode_Sequential()
    {
        var fixture = LoadFixture();
        Assert.Equal(
            "SEQUENTIAL",
            fixture.GetProperty("session").GetProperty("execution_mode").GetString());

        using var options = SessionFactory.ConfigureSessionOptions();
        Assert.Equal(ExecutionMode.ORT_SEQUENTIAL, options.ExecutionMode);
    }

    [Fact]
    public void Session_InterOpThreads_IsOne()
    {
        var fixture = LoadFixture();
        Assert.Equal(1, fixture.GetProperty("session").GetProperty("inter_op_threads").GetInt32());

        using var options = SessionFactory.ConfigureSessionOptions();
        Assert.Equal(1, options.InterOpNumThreads);
    }

    [Fact]
    public void Session_IntraOpThreads_CappedToMaxIntraThreads()
    {
        var fixture = LoadFixture();
        var maxIntra = fixture.GetProperty("session").GetProperty("max_intra_threads").GetInt32();

        using var options = SessionFactory.ConfigureSessionOptions();
        // Auto-detected count = min(logical_cores / 2, max_intra_threads).
        // The hard upper bound is max_intra_threads.
        Assert.True(
            options.IntraOpNumThreads >= 1 && options.IntraOpNumThreads <= maxIntra,
            $"IntraOpNumThreads ({options.IntraOpNumThreads}) outside [1, {maxIntra}]");
    }

    [Fact]
    public void Session_MemoryArena_And_Pattern_Enabled()
    {
        var fixture = LoadFixture();
        Assert.True(fixture.GetProperty("session").GetProperty("enable_cpu_mem_arena").GetBoolean());
        Assert.True(fixture.GetProperty("session").GetProperty("enable_memory_pattern").GetBoolean());

        using var options = SessionFactory.ConfigureSessionOptions();
        Assert.True(options.EnableCpuMemArena);
        Assert.True(options.EnableMemoryPattern);
    }

    [Fact]
    public void Session_DynamicBlockBase_Is4()
    {
        var fixture = LoadFixture();
        Assert.Equal(4, fixture.GetProperty("session").GetProperty("dynamic_block_base").GetInt32());
    }

    [Fact]
    public void Session_MaxIntraThreads_Is4()
    {
        var fixture = LoadFixture();
        Assert.Equal(4, fixture.GetProperty("session").GetProperty("max_intra_threads").GetInt32());
    }

    [Fact]
    public void Warmup_PhonemeLength_Is100()
    {
        var fixture = LoadFixture();
        Assert.Equal(100, fixture.GetProperty("warmup").GetProperty("phoneme_length").GetInt32());
    }

    [Fact]
    public void Warmup_DefaultRuns_Is2()
    {
        var fixture = LoadFixture();
        Assert.Equal(2, fixture.GetProperty("warmup").GetProperty("default_runs").GetInt32());
    }

    [Fact]
    public void Warmup_TokenIds_Match()
    {
        var fixture = LoadFixture();
        var warmup = fixture.GetProperty("warmup");
        Assert.Equal(1, warmup.GetProperty("bos_token").GetInt32());
        Assert.Equal(2, warmup.GetProperty("eos_token").GetInt32());
        Assert.Equal(8, warmup.GetProperty("dummy_phoneme").GetInt32());
    }

    [Fact]
    public void Warmup_Scales_Match()
    {
        var fixture = LoadFixture();
        var warmup = fixture.GetProperty("warmup");
        Assert.Equal(0.667, warmup.GetProperty("noise_scale").GetDouble(), 9);
        Assert.Equal(1.0, warmup.GetProperty("length_scale").GetDouble(), 9);
        Assert.Equal(0.8, warmup.GetProperty("noise_w").GetDouble(), 9);
    }

    [Fact]
    public void Cache_OptimizedExtension_Match()
    {
        var fixture = LoadFixture();
        Assert.Equal(
            "opt.onnx",
            fixture.GetProperty("cache").GetProperty("optimized_extension").GetString());
    }

    [Fact]
    public void Cache_SentinelExtension_Match()
    {
        var fixture = LoadFixture();
        Assert.Equal(
            "opt.onnx.ok",
            fixture.GetProperty("cache").GetProperty("sentinel_extension").GetString());
    }

    [Fact]
    public void Cache_SentinelContent_Match()
    {
        var fixture = LoadFixture();
        Assert.Equal(
            "ok",
            fixture.GetProperty("cache").GetProperty("sentinel_content").GetString());
    }

    [Fact]
    public void Cache_DeviceLabelCpu_Match()
    {
        var fixture = LoadFixture();
        Assert.Equal(
            "cpu",
            fixture.GetProperty("cache").GetProperty("device_label_cpu").GetString());
    }

    [Fact]
    public void EnvVars_DisableWarmup_Name()
    {
        var fixture = LoadFixture();
        Assert.Equal(
            "PIPER_DISABLE_WARMUP",
            fixture.GetProperty("env_vars").GetProperty("disable_warmup").GetString());
    }

    [Fact]
    public void EnvVars_DisableCache_Name()
    {
        var fixture = LoadFixture();
        Assert.Equal(
            "PIPER_DISABLE_CACHE",
            fixture.GetProperty("env_vars").GetProperty("disable_cache").GetString());
    }

    [Fact]
    public void EnvVars_IntraThreads_Name()
    {
        var fixture = LoadFixture();
        Assert.Equal(
            "PIPER_INTRA_THREADS",
            fixture.GetProperty("env_vars").GetProperty("intra_threads").GetString());
    }
}
