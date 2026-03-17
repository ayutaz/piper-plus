using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.ML.OnnxRuntime;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Factory for creating ONNX Runtime <see cref="InferenceSession"/> instances
/// with optional CUDA execution provider support.
/// </summary>
/// <remarks>
/// <para>
/// Mirrors the C++ implementation in <c>piper.cpp:loadModel</c>, which configures
/// <c>SessionOptions</c> and conditionally appends the CUDA execution provider
/// via <c>AppendExecutionProvider_CUDA</c>.
/// </para>
/// <para>
/// When <c>useCuda</c> is <c>true</c> but the CUDA EP is not installed (i.e. the
/// <c>Microsoft.ML.OnnxRuntime.Gpu</c> package is absent), the factory logs a
/// warning and falls back to CPU execution rather than throwing.
/// </para>
/// <para>
/// The <c>testMode</c> parameter does not alter session creation.
/// The caller (<c>Program.cs</c>) is responsible for skipping <c>Synthesize()</c>
/// and outputting phoneme IDs only when test mode is active.
/// </para>
/// </remarks>
public static class SessionFactory
{
    /// <summary>
    /// Environment variable name for the default GPU device ID.
    /// Checked when <paramref name="gpuDeviceId"/> is left at its default value of 0.
    /// Mirrors the C++ <c>PIPER_GPU_DEVICE_ID</c> environment variable.
    /// </summary>
    private const string GpuDeviceIdEnvVar = "PIPER_GPU_DEVICE_ID";

    /// <summary>
    /// Creates an ONNX <see cref="InferenceSession"/> for the given model,
    /// conditionally enabling the CUDA execution provider.
    /// </summary>
    /// <param name="modelPath">
    /// Path to the <c>.onnx</c> model file. Must exist on disk.
    /// </param>
    /// <param name="useCuda">
    /// When <c>true</c>, attempts to append the CUDA execution provider.
    /// Falls back to CPU with a warning if the CUDA EP is unavailable.
    /// </param>
    /// <param name="gpuDeviceId">
    /// CUDA device index. Defaults to <c>0</c>. When <c>0</c>, the factory also
    /// checks the <c>PIPER_GPU_DEVICE_ID</c> environment variable for a fallback
    /// value, matching the C++ CLI behaviour.
    /// </param>
    /// <param name="testMode">
    /// Reserved for future use. Currently has no effect on session creation;
    /// test-mode inference skipping is handled by the CLI layer.
    /// </param>
    /// <param name="logger">
    /// Optional logger for diagnostic messages. Pass <c>null</c> to suppress output.
    /// </param>
    /// <returns>A configured <see cref="InferenceSession"/> ready for inference.</returns>
    /// <exception cref="ArgumentException">
    /// Thrown when <paramref name="modelPath"/> is null or empty.
    /// </exception>
    /// <exception cref="FileNotFoundException">
    /// Thrown when the model file does not exist at <paramref name="modelPath"/>.
    /// </exception>
    public static InferenceSession Create(
        string modelPath,
        bool useCuda = false,
        int gpuDeviceId = 0,
        bool testMode = false,
        ILogger? logger = null)
    {
        ArgumentException.ThrowIfNullOrEmpty(modelPath);

        if (!File.Exists(modelPath))
        {
            throw new FileNotFoundException(
                $"Model file not found: {modelPath}", modelPath);
        }

        logger ??= NullLogger.Instance;

        // Resolve GPU device ID from environment variable when the caller
        // uses the default value (0), mirroring the C++ parseArgs behaviour.
        int resolvedDeviceId = ResolveGpuDeviceId(gpuDeviceId, logger);

        var options = new SessionOptions();

        // Match C++ piper.cpp: disable graph optimisation, memory arena, etc.
        options.SetGraphOptimizationLevel(GraphOptimizationLevel.ORT_DISABLE_ALL);

        if (useCuda)
        {
            TryAppendCudaProvider(options, resolvedDeviceId, logger);
        }

        logger.LogDebug(
            "Creating InferenceSession for {ModelPath} (CUDA={UseCuda}, device={DeviceId}, testMode={TestMode})",
            modelPath, useCuda, resolvedDeviceId, testMode);

        return new InferenceSession(modelPath, options);
    }

    // ------------------------------------------------------------------
    // Internal helpers
    // ------------------------------------------------------------------

    /// <summary>
    /// Resolves the effective GPU device ID. When <paramref name="cliDeviceId"/>
    /// is 0 (the default), checks <c>PIPER_GPU_DEVICE_ID</c> for an override.
    /// </summary>
    private static int ResolveGpuDeviceId(int cliDeviceId, ILogger logger)
    {
        if (cliDeviceId != 0)
        {
            return cliDeviceId;
        }

        var envValue = Environment.GetEnvironmentVariable(GpuDeviceIdEnvVar);
        if (!string.IsNullOrEmpty(envValue) && int.TryParse(envValue, out int envDeviceId))
        {
            logger.LogDebug(
                "GPU device ID set from {EnvVar}: {DeviceId}",
                GpuDeviceIdEnvVar, envDeviceId);
            return envDeviceId;
        }

        return 0;
    }

    /// <summary>
    /// Attempts to append the CUDA execution provider. On failure (typically
    /// because <c>Microsoft.ML.OnnxRuntime.Gpu</c> is not installed), logs a
    /// warning and falls back to CPU execution.
    /// </summary>
    /// <remarks>
    /// The C++ implementation in <c>piper.cpp</c> sets:
    /// <code>
    /// OrtCUDAProviderOptions cuda_options{};
    /// cuda_options.device_id = gpuDeviceId;
    /// cuda_options.cudnn_conv_algo_search = OrtCudnnConvAlgoSearchHeuristic;
    /// session.options.AppendExecutionProvider_CUDA(cuda_options);
    /// </code>
    /// The managed API accepts a <c>Dictionary&lt;string, string&gt;</c> with the
    /// equivalent option keys.
    /// </remarks>
    private static void TryAppendCudaProvider(
        SessionOptions options, int deviceId, ILogger logger)
    {
        try
        {
            // OrtCUDAProviderOptions equivalent in managed API.
            // "cudnn_conv_algo_search" = 1 corresponds to OrtCudnnConvAlgoSearchHeuristic
            // in the C++ enum, matching the C++ piper.cpp configuration.
            var cudaOptions = new Dictionary<string, string>
            {
                ["device_id"] = deviceId.ToString(),
                ["cudnn_conv_algo_search"] = "1", // HEURISTIC
            };

            options.AppendExecutionProvider_CUDA(cudaOptions);

            logger.LogInformation(
                "CUDA execution provider enabled (device_id={DeviceId})", deviceId);
        }
        catch (Exception ex)
        {
            // The CUDA EP is an optional native library. When absent, the
            // managed wrapper throws (typically an EntryPointNotFoundException
            // or DllNotFoundException). Fall back to CPU gracefully.
            logger.LogWarning(
                "CUDA execution provider unavailable, falling back to CPU: {Message}",
                ex.Message);
        }
    }
}
