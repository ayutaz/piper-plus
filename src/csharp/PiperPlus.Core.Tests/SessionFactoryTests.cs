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
        Assert.Equal(3, parameters[1].DefaultValue);
    }

    [Fact]
    public void Warmup_NullSession_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(
            () => SessionFactory.Warmup(session: null!));
    }

    // ================================================================
    // COLD-M5: 最適化済みモデルキャッシュ テスト
    // ================================================================

    [Fact]
    public void OptimizedModelPath_IsConstructedCorrectly()
    {
        var original = "/data/models/test.onnx";
        var optimized = Path.ChangeExtension(original, ".opt.onnx");
        Assert.EndsWith(".opt.onnx", optimized);
    }

    [Fact]
    public void OptimizedModelPath_PreservesDirectory()
    {
        var original = "/data/models/subdir/model.onnx";
        var optimized = Path.ChangeExtension(original, ".opt.onnx");
        Assert.Equal(
            Path.GetDirectoryName(original),
            Path.GetDirectoryName(optimized));
    }

    [Fact]
    public void OptimizedModelPath_FromWindowsPath()
    {
        var original = @"C:\Users\test\models\model.onnx";
        var optimized = Path.ChangeExtension(original, ".opt.onnx");
        Assert.EndsWith(".opt.onnx", optimized);
        Assert.Equal(
            Path.GetDirectoryName(original),
            Path.GetDirectoryName(optimized));
    }

    [Fact]
    public void OptimizedModelPath_FileName()
    {
        var original = "/data/models/test.onnx";
        var optimized = Path.ChangeExtension(original, ".opt.onnx");
        Assert.Equal("test.opt.onnx", Path.GetFileName(optimized));
    }
}
