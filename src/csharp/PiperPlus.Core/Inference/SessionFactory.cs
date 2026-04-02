using System.Diagnostics;
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

        // ORT_ENABLE_ALL: セッション作成時にグラフ最適化を一度実行し、
        // 以降の推論コストを削減する (COLD-M1)。
        options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL;

        if (useCuda)
        {
            TryAppendCudaProvider(options, resolvedDeviceId, logger);
        }

        // COLD-M5: 最適化済みモデルキャッシュ
        // .opt.onnx が存在すれば直接ロード (最適化スキップ) し、
        // 存在しなければ元モデルをロード＆最適化結果を .opt.onnx に保存する。
        var optimizedPath = Path.ChangeExtension(modelPath, ".opt.onnx");
        string effectiveModelPath;

        if (File.Exists(optimizedPath))
        {
            logger.LogInformation("Loading pre-optimized model from {Path}", optimizedPath);
            options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_DISABLE_ALL;
            effectiveModelPath = optimizedPath;
        }
        else
        {
            try
            {
                options.OptimizedModelFilePath = optimizedPath;
                logger.LogInformation("ORT will save optimized model to {Path}", optimizedPath);
            }
            catch (Exception ex)
            {
                logger.LogWarning(
                    "Could not set optimized model path {Path}: {Message} (continuing without cache)",
                    optimizedPath, ex.Message);
            }

            effectiveModelPath = modelPath;
        }

        logger.LogDebug(
            "Creating InferenceSession for {ModelPath} (CUDA={UseCuda}, device={DeviceId}, testMode={TestMode})",
            effectiveModelPath, useCuda, resolvedDeviceId, testMode);

        return new InferenceSession(effectiveModelPath, options);
    }

    /// <summary>
    /// Warms up the ORT graph-optimization cache by running a small number of
    /// dummy inferences. This eliminates the ~500-800ms JIT overhead that would
    /// otherwise hit the user's first real synthesis call.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The method inspects <see cref="InferenceSession.InputMetadata"/> to
    /// dynamically build the minimal set of required input tensors, so it
    /// works for single-speaker, multi-speaker, multilingual, and prosody
    /// models alike.
    /// </para>
    /// <para>
    /// Any exception during warmup is caught and logged as a warning.
    /// Warmup failure must never prevent the application from starting.
    /// </para>
    /// </remarks>
    /// <param name="session">A configured <see cref="InferenceSession"/>.</param>
    /// <param name="runs">Number of warmup inferences to execute (default: 3).</param>
    /// <param name="logger">Optional logger for diagnostic messages.</param>
    public static void Warmup(
        InferenceSession session,
        int runs = 3,
        ILogger? logger = null)
    {
        ArgumentNullException.ThrowIfNull(session);
        logger ??= NullLogger.Instance;

        try
        {
            var sw = Stopwatch.StartNew();

            // Minimal valid phoneme IDs: BOS(1) + 3 dummy phonemes + EOS(2)
            long[] phonemeIds = [1, 8, 8, 8, 2];
            int phonemeLength = phonemeIds.Length;

            // ---- Build required inputs ----
            using var inputTensor = OrtValue.CreateTensorValueFromMemory(
                phonemeIds, [1, phonemeLength]);

            long[] lengths = [phonemeLength];
            using var inputLengths = OrtValue.CreateTensorValueFromMemory(
                lengths, [1]);

            float[] scales = [0.667f, 1.0f, 0.8f];
            using var scalesTensor = OrtValue.CreateTensorValueFromMemory(
                scales, [3]);

            var inputNames = new List<string>(6) { "input", "input_lengths", "scales" };
            var inputValues = new List<OrtValue>(6) { inputTensor, inputLengths, scalesTensor };

            // ---- Dynamically add optional inputs based on model metadata ----
            var metadata = session.InputMetadata;

            OrtValue? sidTensor = null;
            if (metadata.ContainsKey("sid"))
            {
                long[] sid = [0];
                sidTensor = OrtValue.CreateTensorValueFromMemory(sid, [1]);
                inputNames.Add("sid");
                inputValues.Add(sidTensor);
            }

            OrtValue? lidTensor = null;
            if (metadata.ContainsKey("lid"))
            {
                long[] lid = [0];
                lidTensor = OrtValue.CreateTensorValueFromMemory(lid, [1]);
                inputNames.Add("lid");
                inputValues.Add(lidTensor);
            }

            OrtValue? prosodyTensor = null;
            if (metadata.ContainsKey("prosody_features"))
            {
                long[] prosody = new long[phonemeLength * 3]; // zero-filled
                prosodyTensor = OrtValue.CreateTensorValueFromMemory(
                    prosody, [1, phonemeLength, 3]);
                inputNames.Add("prosody_features");
                inputValues.Add(prosodyTensor);
            }

            string[] outputNames = session.OutputMetadata.ContainsKey("durations")
                ? ["output", "durations"]
                : ["output"];

            try
            {
                for (int i = 0; i < runs; i++)
                {
                    using var runOptions = new RunOptions();
                    using var results = session.Run(
                        runOptions, inputNames, inputValues, outputNames);
                }
            }
            finally
            {
                sidTensor?.Dispose();
                lidTensor?.Dispose();
                prosodyTensor?.Dispose();
            }

            sw.Stop();
            logger.LogInformation(
                "Warmup completed ({Runs} runs in {ElapsedMs}ms)",
                runs, sw.ElapsedMilliseconds);
        }
        catch (Exception ex)
        {
            logger.LogWarning(
                "Warmup failed (non-fatal, inference will still work): {Message}",
                ex.Message);
        }
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
            // The C++ implementation sets OrtCUDAProviderOptions with
            // cudnn_conv_algo_search = OrtCudnnConvAlgoSearchHeuristic.
            // The managed API's int overload uses default CUDA options.
            options.AppendExecutionProvider_CUDA(deviceId);

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
