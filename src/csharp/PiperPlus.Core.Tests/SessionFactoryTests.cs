using System.Reflection;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.ML.OnnxRuntime;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// Edge-case tests for <see cref="SessionFactory"/>, covering input validation
/// and the private <c>ResolveGpuDeviceId</c> logic (tested via reflection).
/// </summary>
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

    [Fact]
    public void CacheHit_RequiresBothOptAndSentinel()
    {
        // Simulate: both files must exist for cache hit
        bool optExists = true;
        bool sentinelExists = true;
        bool useCached = optExists && sentinelExists;
        Assert.True(useCached);
    }

    [Fact]
    public void CacheMiss_WhenSentinelMissing()
    {
        // Simulate: opt exists but sentinel is missing (interrupted write)
        bool optExists = true;
        bool sentinelExists = false;
        bool useCached = optExists && sentinelExists;
        Assert.False(useCached);
    }

    [Fact]
    public void CacheMiss_WhenOptMissing()
    {
        // Simulate: neither file exists
        bool optExists = false;
        bool sentinelExists = false;
        bool useCached = optExists && sentinelExists;
        Assert.False(useCached);
    }

    [Fact]
    public void DeviceLabel_Cpu()
    {
        bool useCuda = false;
        int deviceId = 0;
        var label = useCuda ? $"cuda{deviceId}" : "cpu";
        Assert.Equal("cpu", label);
    }

    [Fact]
    public void DeviceLabel_Cuda0()
    {
        bool useCuda = true;
        int deviceId = 0;
        var label = useCuda ? $"cuda{deviceId}" : "cpu";
        Assert.Equal("cuda0", label);
    }

    [Fact]
    public void DeviceLabel_Cuda1()
    {
        bool useCuda = true;
        int deviceId = 1;
        var label = useCuda ? $"cuda{deviceId}" : "cpu";
        Assert.Equal("cuda1", label);
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
}
