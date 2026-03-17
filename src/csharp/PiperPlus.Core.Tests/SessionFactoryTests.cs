using System.Reflection;
using Microsoft.Extensions.Logging.Abstractions;
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
}
