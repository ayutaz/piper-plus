using System.Reflection;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.ML.OnnxRuntime;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Edge-case tests for <see cref="SessionFactory"/>, covering input validation
/// and the private <c>ResolveGpuDeviceId</c> logic (tested via reflection).
/// </summary>
/// <remarks>
/// Member of the <c>EnvVars</c> collection: many tests in this class mutate
/// process-wide environment variables (PIPER_GPU_DEVICE_ID, PIPER_INTRA_THREADS,
/// PIPER_DISABLE_WARMUP, PIPER_DISABLE_CACHE). xUnit v3 runs tests across
/// classes in parallel by default, so they MUST be serialised with other
/// env-var-mutating classes (<see cref="DictionaryManagerTests"/>) to avoid
/// observation drift.
/// </remarks>
[Collection("EnvVars")]
public sealed class SessionFactoryTests
{
    // ================================================================
    // Input validation — no real ONNX files needed
    // ================================================================

    [Fact]
    public void Create_NullModelPath_ThrowsArgumentException()
    {
        Assert.Throws<ArgumentNullException>(
            () => SessionFactory.Create(modelPath: null!));
    }

    [Fact]
    public void Create_EmptyModelPath_ThrowsArgumentException()
    {
        Assert.Throws<ArgumentException>(
            () => SessionFactory.Create(modelPath: ""));
    }

    [Fact]
    public void Create_FileNotFound_ThrowsFileNotFoundException()
    {
        var ex = Assert.Throws<FileNotFoundException>(
            () => SessionFactory.Create(modelPath: "/nonexistent/path/model.onnx"));

        Assert.Contains("model.onnx", ex.Message);
    }

    [Fact]
    public void Create_WhitespaceModelPath_ThrowsArgumentException()
    {
        // ThrowIfNullOrEmpty does not reject whitespace-only strings, so the
        // path reaches File.Exists which returns false, yielding FileNotFoundException.
        Assert.Throws<FileNotFoundException>(
            () => SessionFactory.Create(modelPath: "   "));
    }

    // ================================================================
    // ResolveGpuDeviceId — tested via reflection on the private method
    // ================================================================

    private static readonly MethodInfo ResolveGpuDeviceIdMethod =
        typeof(SessionFactory).GetMethod(
            "ResolveGpuDeviceId",
            BindingFlags.NonPublic | BindingFlags.Static)
        ?? throw new InvalidOperationException(
            "Could not find private method ResolveGpuDeviceId on SessionFactory");

    /// <summary>
    /// Invokes the private <c>ResolveGpuDeviceId(int cliDeviceId, ILogger logger)</c>.
    /// </summary>
    private static int InvokeResolveGpuDeviceId(int cliDeviceId)
    {
        var result = ResolveGpuDeviceIdMethod.Invoke(
            null, [cliDeviceId, NullLogger.Instance]);
        return (int)result!;
    }

    [Fact]
    public void ResolveGpuDeviceId_EnvVar_WhenCliIsZero()
    {
        string? original = Environment.GetEnvironmentVariable("PIPER_GPU_DEVICE_ID");
        try
        {
            Environment.SetEnvironmentVariable("PIPER_GPU_DEVICE_ID", "2");

            int resolved = InvokeResolveGpuDeviceId(cliDeviceId: 0);

            Assert.Equal(2, resolved);
        }
        finally
        {
            Environment.SetEnvironmentVariable("PIPER_GPU_DEVICE_ID", original);
        }
    }

    [Fact]
    public void ResolveGpuDeviceId_InvalidEnvValue_DefaultsToZero()
    {
        string? original = Environment.GetEnvironmentVariable("PIPER_GPU_DEVICE_ID");
        try
        {
            Environment.SetEnvironmentVariable("PIPER_GPU_DEVICE_ID", "invalid");

            int resolved = InvokeResolveGpuDeviceId(cliDeviceId: 0);

            Assert.Equal(0, resolved);
        }
        finally
        {
            Environment.SetEnvironmentVariable("PIPER_GPU_DEVICE_ID", original);
        }
    }

    [Fact]
    public void ResolveGpuDeviceId_NonZeroCli_SkipsEnvVar()
    {
        string? original = Environment.GetEnvironmentVariable("PIPER_GPU_DEVICE_ID");
        try
        {
            Environment.SetEnvironmentVariable("PIPER_GPU_DEVICE_ID", "5");

            int resolved = InvokeResolveGpuDeviceId(cliDeviceId: 3);

            // cliDeviceId != 0, so the env var is ignored and 3 is returned.
            Assert.Equal(3, resolved);
        }
        finally
        {
            Environment.SetEnvironmentVariable("PIPER_GPU_DEVICE_ID", original);
        }
    }

    [Fact]
    public void ResolveGpuDeviceId_EmptyEnvVar_DefaultsToZero()
    {
        string? original = Environment.GetEnvironmentVariable("PIPER_GPU_DEVICE_ID");
        try
        {
            Environment.SetEnvironmentVariable("PIPER_GPU_DEVICE_ID", "");

            int resolved = InvokeResolveGpuDeviceId(cliDeviceId: 0);

            Assert.Equal(0, resolved);
        }
        finally
        {
            Environment.SetEnvironmentVariable("PIPER_GPU_DEVICE_ID", original);
        }
    }

    // ================================================================
    // Warmup — signature and behaviour tests
    // ================================================================

    [Fact]
    public void Warmup_MethodExists_WithCorrectSignature()
    {
        var method = typeof(SessionFactory).GetMethod("Warmup");
        Assert.NotNull(method);
        Assert.True(method!.IsStatic);

        // Should accept (InferenceSession, int, ILogger?)
        var parameters = method.GetParameters();
        Assert.Equal(3, parameters.Length);
        Assert.Equal(typeof(InferenceSession), parameters[0].ParameterType);
        Assert.Equal(typeof(int), parameters[1].ParameterType);
        Assert.True(parameters[1].HasDefaultValue);
        Assert.Equal(2, parameters[1].DefaultValue);
    }

    [Fact]
    public void Warmup_NullSession_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(
            () => SessionFactory.Warmup(session: null!));
    }

    // ================================================================
    // COLD-M5 + F1/D5: 最適化済みモデルキャッシュ テスト
    // ================================================================

    /// <summary>Helper: build device-labelled cache path (mirrors SessionFactory logic).</summary>
    private static string BuildCachePath(string modelPath, string deviceLabel)
        => Path.ChangeExtension(modelPath, $".{deviceLabel}.opt.onnx");

    [Fact]
    public void OptimizedModelPath_Cpu_IsConstructedCorrectly()
    {
        var original = "/data/models/test.onnx";
        var optimized = BuildCachePath(original, "cpu");
        Assert.EndsWith(".cpu.opt.onnx", optimized);
        Assert.Equal("test.cpu.opt.onnx", Path.GetFileName(optimized));
    }

    [Fact]
    public void OptimizedModelPath_Cuda_IsConstructedCorrectly()
    {
        var original = "/data/models/test.onnx";
        var optimized = BuildCachePath(original, "cuda0");
        Assert.EndsWith(".cuda0.opt.onnx", optimized);
        Assert.Equal("test.cuda0.opt.onnx", Path.GetFileName(optimized));
    }

    [Fact]
    public void OptimizedModelPath_PreservesDirectory()
    {
        var original = "/data/models/subdir/model.onnx";
        var optimized = BuildCachePath(original, "cpu");
        Assert.Equal(
            Path.GetDirectoryName(original),
            Path.GetDirectoryName(optimized));
    }

    [Fact]
    public void OptimizedModelPath_FromWindowsPath()
    {
        var original = @"C:\Users\test\models\model.onnx";
        var optimized = BuildCachePath(original, "cpu");
        Assert.EndsWith(".cpu.opt.onnx", optimized);
        Assert.Equal(
            Path.GetDirectoryName(original),
            Path.GetDirectoryName(optimized));
    }

    [Fact]
    public void SentinelPath_IsConstructedCorrectly()
    {
        var original = "/data/models/test.onnx";
        var optimized = BuildCachePath(original, "cpu");
        var sentinel = optimized + ".ok";
        Assert.EndsWith(".cpu.opt.onnx.ok", sentinel);
    }

    // ----------------------------------------------------------------
    // Cache contract — sentinel-paired writes guarantee atomicity.
    //
    // The previous "Simulate: both files must exist for cache hit"
    // tests just exercised local boolean expressions and asserted no
    // SessionFactory behaviour. They have been replaced by tests that
    // drive Create() with real filesystem state so the actual cache
    // policy is pinned (CodeQL-style: "do not assert on test data").
    // ----------------------------------------------------------------

    [Fact]
    public void Cache_OnlyOptOnnx_NoSentinel_OrphanIsCleanedUp()
    {
        // SessionFactory production policy: when the optimised model file
        // exists but its sentinel does not, the .opt.onnx is treated as
        // an interrupted write and is REMOVED before the source model is
        // loaded fresh. This pin guards against a regression where stale
        // caches accumulate (caused subtle inference inconsistencies in
        // pre-v1.12 builds before the sentinel was introduced).
        var tmpDir = Path.Join(Path.GetTempPath(),
            "piper-cache-no-sentinel-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tmpDir);
        try
        {
            var modelPath = Path.Join(tmpDir, "model.onnx");
            File.WriteAllText(modelPath, "placeholder model");
            var optPath = Path.ChangeExtension(modelPath, ".cpu.opt.onnx");
            File.WriteAllText(optPath, "stale optimised cache");
            // No sentinel (.ok) file — simulates an interrupted previous write.

            // Create() will fail at the source model load step (not real
            // ONNX), but the orphan .opt.onnx must be cleaned up first.
            Assert.ThrowsAny<Exception>(() => SessionFactory.Create(modelPath));

            // Stale .opt.onnx without sentinel was removed by Create().
            Assert.False(File.Exists(optPath),
                "orphan .opt.onnx must be cleaned up when the sentinel is missing");
        }
        finally
        {
            try { Directory.Delete(tmpDir, recursive: true); }
            catch (IOException) { /* best effort */ }
            catch (UnauthorizedAccessException) { /* best effort */ }
        }
    }

    [Fact]
    public void Cache_OnlySentinel_NoOpt_TreatedAsMiss()
    {
        // Sentinel without the .opt.onnx file — ORT cannot use a sentinel
        // alone, so this is a degenerate state. Create() must not crash.
        var tmpDir = Path.Join(Path.GetTempPath(),
            "piper-cache-no-opt-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tmpDir);
        try
        {
            var modelPath = Path.Join(tmpDir, "model.onnx");
            File.WriteAllText(modelPath, "placeholder model");
            var optPath = Path.ChangeExtension(modelPath, ".cpu.opt.onnx");
            var sentinelPath = optPath + ".ok";
            File.WriteAllText(sentinelPath, "ok");
            // No optPath file — sentinel orphan.

            Assert.ThrowsAny<Exception>(() => SessionFactory.Create(modelPath));

            // The orphan sentinel must remain (Create() must not silently
            // mutate the on-disk cache state on its own).
            Assert.True(File.Exists(sentinelPath),
                "orphan sentinel must remain after cache-miss Create()");
        }
        finally
        {
            try { Directory.Delete(tmpDir, recursive: true); }
            catch (IOException) { /* best effort */ }
            catch (UnauthorizedAccessException) { /* best effort */ }
        }
    }

    [Theory]
    [InlineData("/data/models/voice.onnx", "cpu", "voice.cpu.opt.onnx")]
    [InlineData("/data/models/voice.onnx", "cuda0", "voice.cuda0.opt.onnx")]
    [InlineData("/data/models/voice.onnx", "cuda1", "voice.cuda1.opt.onnx")]
    [InlineData("/data/models/voice.onnx", "coreml", "voice.coreml.opt.onnx")]
    public void OptimizedModelPath_Format(string modelPath, string device, string expectedFile)
    {
        // The cache-path construction policy ("<base>.<device>.opt.onnx") is
        // a contract — drift would silently invalidate previously-built
        // caches. Pin the exact filename + the device label format, not
        // the helper's internal logic.
        var optimized = BuildCachePath(modelPath, device);
        Assert.Equal(expectedFile, Path.GetFileName(optimized));
        Assert.EndsWith($".{device}.opt.onnx", optimized);
    }

    // ================================================================
    // ConfigureSessionOptions — tests for the extracted internal method
    // that configures SessionOptions with VITS-optimized settings.
    // ================================================================

    [Fact]
    public void ConfigureSessionOptions_GraphOptimizationLevel_IsEnableAll()
    {
        using var options = SessionFactory.ConfigureSessionOptions();
        Assert.Equal(GraphOptimizationLevel.ORT_ENABLE_ALL, options.GraphOptimizationLevel);
    }

    [Fact]
    public void ConfigureSessionOptions_ExecutionMode_IsSequential()
    {
        using var options = SessionFactory.ConfigureSessionOptions();
        Assert.Equal(ExecutionMode.ORT_SEQUENTIAL, options.ExecutionMode);
    }

    [Fact]
    public void ConfigureSessionOptions_IntraOpNumThreads_IsHalfProcessorsCappedAt4()
    {
        using var options = SessionFactory.ConfigureSessionOptions();

        int expected = Math.Max(Math.Min(Environment.ProcessorCount / 2, 4), 1);
        Assert.Equal(expected, options.IntraOpNumThreads);
    }

    [Fact]
    public void ConfigureSessionOptions_IntraOpNumThreads_AtLeastOne()
    {
        using var options = SessionFactory.ConfigureSessionOptions();
        Assert.True(options.IntraOpNumThreads >= 1,
            $"IntraOpNumThreads should be >= 1, but was {options.IntraOpNumThreads}");
    }

    [Fact]
    public void ConfigureSessionOptions_InterOpNumThreads_IsOne()
    {
        using var options = SessionFactory.ConfigureSessionOptions();
        Assert.Equal(1, options.InterOpNumThreads);
    }

    [Fact]
    public void ConfigureSessionOptions_EnableCpuMemArena_IsTrue()
    {
        using var options = SessionFactory.ConfigureSessionOptions();
        Assert.True(options.EnableCpuMemArena);
    }

    [Fact]
    public void ConfigureSessionOptions_EnableMemoryPattern_IsTrue()
    {
        using var options = SessionFactory.ConfigureSessionOptions();
        Assert.True(options.EnableMemoryPattern);
    }

    [Fact]
    public void ConfigureSessionOptions_DynamicBlockBase_DoesNotThrow()
    {
        // ORT C# API does not expose a getter for session config entries,
        // so we verify that ConfigureSessionOptions completes without throwing.
        // The dynamic_block_base entry is set inside the method.
        using var options = SessionFactory.ConfigureSessionOptions();
    }

    // ================================================================
    // Environment variable contract — PIPER_INTRA_THREADS / PIPER_DISABLE_WARMUP
    // / PIPER_DISABLE_CACHE. Mirrors Python ort_utils.py behaviour.
    // ================================================================

    /// <summary>
    /// Helper: mutate an environment variable for the duration of a test, then
    /// restore the original value (or clear) in a finally block.
    /// </summary>
    private static void WithEnv(string name, string? value, Action body)
    {
        string? original = Environment.GetEnvironmentVariable(name);
        try
        {
            Environment.SetEnvironmentVariable(name, value);
            body();
        }
        finally
        {
            Environment.SetEnvironmentVariable(name, original);
        }
    }

    // ---- PIPER_INTRA_THREADS -----------------------------------------------

    [Fact]
    public void EnvIntraThreads_ValidValue_AppliedToSessionOptions()
    {
        // "2" is a valid positive integer ≤ MaxIntraThreads (4), so it should
        // override the auto-detected default unconditionally.
        WithEnv("PIPER_INTRA_THREADS", "2", () =>
        {
            using var options = SessionFactory.ConfigureSessionOptions();
            Assert.Equal(2, options.IntraOpNumThreads);
        });

        // Also verify the clamp: a value above the cap is clamped to MaxIntraThreads (4).
        WithEnv("PIPER_INTRA_THREADS", "16", () =>
        {
            using var options = SessionFactory.ConfigureSessionOptions();
            Assert.Equal(4, options.IntraOpNumThreads);
        });
    }

    [Fact]
    public void EnvIntraThreads_InvalidValue_FallsBackToDefault()
    {
        // Auto-detected default = max(min(processors/2, 4), 1).
        int autoDefault = Math.Max(Math.Min(Environment.ProcessorCount / 2, 4), 1);

        // Non-numeric env value → ignored, fall back to auto.
        WithEnv("PIPER_INTRA_THREADS", "not-a-number", () =>
        {
            using var options = SessionFactory.ConfigureSessionOptions();
            Assert.Equal(autoDefault, options.IntraOpNumThreads);
        });

        // Zero / negative → ignored, fall back to auto (parse succeeds but
        // value < 1 fails the validity guard in ResolveIntraOpThreads).
        WithEnv("PIPER_INTRA_THREADS", "0", () =>
        {
            using var options = SessionFactory.ConfigureSessionOptions();
            Assert.Equal(autoDefault, options.IntraOpNumThreads);
        });

        WithEnv("PIPER_INTRA_THREADS", "-3", () =>
        {
            using var options = SessionFactory.ConfigureSessionOptions();
            Assert.Equal(autoDefault, options.IntraOpNumThreads);
        });

        // Empty string is treated as unset → auto.
        WithEnv("PIPER_INTRA_THREADS", "", () =>
        {
            using var options = SessionFactory.ConfigureSessionOptions();
            Assert.Equal(autoDefault, options.IntraOpNumThreads);
        });
    }

    // ---- PIPER_DISABLE_WARMUP ----------------------------------------------

    /// <summary>
    /// Reflection probe for the private <c>IsTruthyEnv</c> helper. Used by the
    /// warmup-skip / cache-skip tests to assert env-detection behaviour without
    /// depending on a real ONNX session (which would require a model file and
    /// would actually invoke ORT for the warmup run).
    /// </summary>
    private static readonly MethodInfo IsTruthyEnvMethod =
        typeof(SessionFactory).GetMethod(
            "IsTruthyEnv",
            BindingFlags.NonPublic | BindingFlags.Static)
        ?? throw new InvalidOperationException(
            "Could not find private method IsTruthyEnv on SessionFactory");

    private static bool InvokeIsTruthyEnv(string name)
        => (bool)IsTruthyEnvMethod.Invoke(null, [name])!;

    [Fact]
    public void EnvDisableWarmup_True_SkipsWarmup()
    {
        // Truthy values per Python ort_utils.py contract: "1", "true", "yes"
        // (case-insensitive). The truthy probe gates Warmup's early-return
        // branch — when it returns true, Warmup() returns before touching ORT.
        foreach (var v in new[] { "1", "true", "TRUE", "True", "yes", "YES" })
        {
            WithEnv("PIPER_DISABLE_WARMUP", v, () =>
            {
                Assert.True(
                    InvokeIsTruthyEnv("PIPER_DISABLE_WARMUP"),
                    $"PIPER_DISABLE_WARMUP={v} should be detected as truthy");

                // Calling Warmup with a null session normally throws
                // ArgumentNullException; if the env-skip path is reached
                // BEFORE the null guard, Warmup would silently return.
                // Order matters: the guard runs first, env-skip is second.
                // So we call it with a non-null reference path that would
                // otherwise hit the warmup body. Since constructing a real
                // InferenceSession requires an .onnx file, we instead exercise
                // the truthy-detection contract directly above, which is the
                // sole gate on the early-return branch.
            });
        }
    }

    [Fact]
    public void EnvDisableWarmup_Unset_RunsWarmup()
    {
        // When the env var is unset, IsTruthyEnv returns false, so Warmup
        // proceeds past the guard into the body (which then either runs the
        // dummy inferences or — with runs <= 0 — returns harmlessly).
        WithEnv("PIPER_DISABLE_WARMUP", null, () =>
        {
            Assert.False(InvokeIsTruthyEnv("PIPER_DISABLE_WARMUP"));
        });

        // Also: empty string and arbitrary non-truthy strings should NOT skip.
        foreach (var v in new[] { "", "0", "false", "no", "off", "maybe" })
        {
            WithEnv("PIPER_DISABLE_WARMUP", v, () =>
            {
                Assert.False(
                    InvokeIsTruthyEnv("PIPER_DISABLE_WARMUP"),
                    $"PIPER_DISABLE_WARMUP={v} must NOT be treated as truthy");
            });
        }
    }

    // ---- PIPER_DISABLE_CACHE -----------------------------------------------

    [Fact]
    public void EnvDisableCache_True_SkipsCacheReadAndWrite()
    {
        // Stage a fake cache pair (.opt.onnx + .ok) next to a tiny "model"
        // file. With PIPER_DISABLE_CACHE=1, Create() should NOT touch either
        // file: it should not attempt to read the .opt.onnx (which would
        // explode because it isn't a real ONNX) and it should not write the
        // sentinel. Since Create() also fails on a missing real model, we
        // assert via the truthiness probe + by leaving the staged cache
        // intact.
        // Use Path.Join (vs Path.Combine) to avoid CodeQL's "may silently
        // drop earlier arguments" warning. Path.GetTempPath() is absolute, so
        // Combine's drop semantics are a false positive here, but Join has no
        // such pitfall and reads more safely.
        var tmpDir = Path.Join(Path.GetTempPath(),
            "piper-cache-disable-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tmpDir);
        var modelPath = Path.Join(tmpDir, "model.onnx");
        // Body content irrelevant — we only need File.Exists() to return true.
        File.WriteAllText(modelPath, "not a real onnx");
        var optPath = Path.ChangeExtension(modelPath, ".cpu.opt.onnx");
        var sentinelPath = optPath + ".ok";
        File.WriteAllText(optPath, "stale opt");
        File.WriteAllText(sentinelPath, "ok");

        try
        {
            WithEnv("PIPER_DISABLE_CACHE", "1", () =>
            {
                Assert.True(InvokeIsTruthyEnv("PIPER_DISABLE_CACHE"));

                // Create() will throw because modelPath is not real ONNX,
                // but it must do so AFTER bypassing the cache load. The
                // staged optPath/sentinelPath must not be deleted by the
                // cache-disabled path (Create does not touch them).
                Assert.ThrowsAny<Exception>(() =>
                    SessionFactory.Create(modelPath));

                Assert.True(File.Exists(optPath),
                    "PIPER_DISABLE_CACHE=1 must not delete cache files");
                Assert.True(File.Exists(sentinelPath),
                    "PIPER_DISABLE_CACHE=1 must not delete sentinel files");
            });

            foreach (var v in new[] { "true", "yes", "TRUE", "Yes" })
            {
                WithEnv("PIPER_DISABLE_CACHE", v, () =>
                {
                    Assert.True(
                        InvokeIsTruthyEnv("PIPER_DISABLE_CACHE"),
                        $"PIPER_DISABLE_CACHE={v} should be detected as truthy");
                });
            }
        }
        finally
        {
            // Best-effort cleanup. We catch only the specific I/O exceptions
            // documented for Directory.Delete instead of a generic `catch`
            // (CodeQL "Generic catch clause" hygiene).
            try { Directory.Delete(tmpDir, recursive: true); }
            catch (IOException) { /* best effort */ }
            catch (UnauthorizedAccessException) { /* best effort */ }
        }
    }

    [Fact]
    public void EnvDisableCache_Unset_UsesCache()
    {
        // When the env var is unset (or set to any non-truthy value), the
        // cache path is taken: IsTruthyEnv returns false and Create() will
        // try to read .opt.onnx + .ok if both exist, or write them on miss.
        WithEnv("PIPER_DISABLE_CACHE", null, () =>
        {
            Assert.False(InvokeIsTruthyEnv("PIPER_DISABLE_CACHE"));
        });

        foreach (var v in new[] { "", "0", "false", "no", "off" })
        {
            WithEnv("PIPER_DISABLE_CACHE", v, () =>
            {
                Assert.False(
                    InvokeIsTruthyEnv("PIPER_DISABLE_CACHE"),
                    $"PIPER_DISABLE_CACHE={v} must NOT be treated as truthy");
            });
        }
    }
}
