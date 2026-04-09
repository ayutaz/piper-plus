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
    /// Default number of warmup inference runs.
    /// ORT JIT cache stabilises in 1-2 runs; 2 provides a safety margin.
    /// </summary>
    private const int DefaultWarmupRuns = 2;

    /// <summary>
    /// Length of the dummy phoneme input used during warmup.
    /// Matches typical production input length (50-200) to warm ORT memory allocations.
    /// </summary>
    private const int WarmupPhonemeLength = 100;

    /// <summary>VITS 小モデルの intra-op スレッド上限。</summary>
    private const int MaxIntraThreads = 4;

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
    /// <remarks>
    /// <para>
    /// <b>Side effect:</b> 初回呼び出し時、モデルと同じディレクトリに
    /// <c>{model}.opt.onnx</c> を生成する。このキャッシュファイルは
    /// ORT バージョンおよびデバイスに依存するため、変更後は削除して再生成が必要。
    /// 書き込み権限がない場合は警告を出力してスキップする（推論への影響なし）。
    /// </para>
    /// </remarks>
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

        var options = ConfigureSessionOptions();

        if (useCuda)
        {
            TryAppendCudaProvider(options, resolvedDeviceId, logger);
        }

        // COLD-M5 + F1/D5: 最適化済みモデルキャッシュ
        // キャッシュパスにデバイス名を含める (D5: CPU/CUDA 混用防止)。
        // センチネルファイル (.ok) で書き込み完了を保証 (F1: 中断耐性)。
        var deviceLabel = useCuda ? $"cuda{resolvedDeviceId}" : "cpu";
        var optimizedPath = Path.ChangeExtension(modelPath, $".{deviceLabel}.opt.onnx");
        var sentinelPath = optimizedPath + ".ok";
        string effectiveModelPath;

        // キャッシュ有効: .opt.onnx と .ok の両方が存在する場合のみ
        bool useCached = File.Exists(optimizedPath) && File.Exists(sentinelPath);

        if (useCached)
        {
            logger.LogInformation("Loading pre-optimized model from {Path}", optimizedPath);
            options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_DISABLE_ALL;
            effectiveModelPath = optimizedPath;
        }
        else
        {
            // 不完全なキャッシュがあれば削除
            if (File.Exists(optimizedPath) && !File.Exists(sentinelPath))
            {
                logger.LogWarning(
                    "Removing incomplete cache {Path} (missing sentinel)", optimizedPath);
                try { File.Delete(optimizedPath); } catch { /* best effort */ }
            }

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

        var session = new InferenceSession(effectiveModelPath, options);

        // F1: セッション作成成功後にセンチネルファイルを書き込む
        if (!useCached && File.Exists(optimizedPath))
        {
            try
            {
                File.WriteAllText(sentinelPath, "ok");
                logger.LogInformation("Cache sentinel written: {Path}", sentinelPath);
            }
            catch (Exception ex)
            {
                logger.LogWarning("Failed to write sentinel {Path}: {Message}", sentinelPath, ex.Message);
            }
        }

        return session;
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
    /// ダミー入力は本番と同程度の長さ (100 トークン) を使用する。ORT は形状変更時に
    /// 内部バッファを再割り当てするため、本番と同程度の形状で warmup することで
    /// メモリアロケーションも温まり、初回推論の遅延を最小化できる。
    /// </para>
    /// <para>
    /// Any exception during warmup is caught and logged as a warning.
    /// Warmup failure must never prevent the application from starting.
    /// </para>
    /// </remarks>
    /// <param name="session">A configured <see cref="InferenceSession"/>.</param>
    /// <param name="runs">Number of warmup inferences to execute (default: <see cref="DefaultWarmupRuns"/>).</param>
    /// <param name="logger">Optional logger for diagnostic messages.</param>
    public static void Warmup(
        InferenceSession session,
        int runs = DefaultWarmupRuns,
        ILogger? logger = null)
    {
        ArgumentNullException.ThrowIfNull(session);
        logger ??= NullLogger.Instance;

        try
        {
            var sw = Stopwatch.StartNew();

            // Dummy phoneme IDs with production-like length: BOS(1) + dummy phonemes(8) + EOS(2)
            long[] phonemeIds = new long[WarmupPhonemeLength];
            phonemeIds[0] = 1; // BOS
            for (int j = 1; j < WarmupPhonemeLength - 1; j++)
                phonemeIds[j] = 8; // dummy phoneme
            phonemeIds[WarmupPhonemeLength - 1] = 2; // EOS
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

            // speaker_embedding: float32 [1, embDim] = zeros (no cloning during warmup)
            // speaker_embedding_mask: int64 [1, 1] = 0
            // ONNX Runtime requires ALL declared inputs, so both tensors must be
            // provided when the model supports speaker_embedding.
            OrtValue? speakerEmbTensor = null;
            OrtValue? speakerEmbMaskTensor = null;
            if (metadata.ContainsKey("speaker_embedding"))
            {
                int embDim = 256; // ECAPA-TDNN default
                if (metadata.TryGetValue("speaker_embedding", out var embMeta)
                    && embMeta.Dimensions.Length >= 2 && embMeta.Dimensions[1] > 0)
                {
                    embDim = embMeta.Dimensions[1];
                }

                float[] zeroEmb = new float[embDim];
                speakerEmbTensor = OrtValue.CreateTensorValueFromMemory(zeroEmb, [1, embDim]);
                inputNames.Add("speaker_embedding");
                inputValues.Add(speakerEmbTensor);

                long[] mask = [0];
                speakerEmbMaskTensor = OrtValue.CreateTensorValueFromMemory(mask, [1, 1]);
                inputNames.Add("speaker_embedding_mask");
                inputValues.Add(speakerEmbMaskTensor);
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
                speakerEmbTensor?.Dispose();
                speakerEmbMaskTensor?.Dispose();
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
    /// Creates and configures a <see cref="SessionOptions"/> with the standard
    /// VITS-optimized settings: graph optimization, thread counts, execution mode,
    /// memory arena, and dynamic block base.
    /// </summary>
    /// <remarks>
    /// Extracted from <see cref="Create"/> to enable direct unit testing without
    /// requiring a real ONNX model file on disk.
    /// </remarks>
    /// <returns>A configured <see cref="SessionOptions"/> instance.</returns>
    internal static SessionOptions ConfigureSessionOptions()
    {
        var options = new SessionOptions();

        // ORT_ENABLE_ALL: セッション作成時にグラフ最適化を一度実行し、
        // 以降の推論コストを削減する (COLD-M1)。
        options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL;

        // COLD-M1: VITS は小モデルのためスレッド数を制限する。
        // 物理コア数の半分（最大4）を intra-op スレッドに割り当て。
        options.IntraOpNumThreads = Math.Max(
            Math.Min(Environment.ProcessorCount / 2, MaxIntraThreads), 1);
        options.InterOpNumThreads = 1;
        // VITS は単一グラフで並列サブグラフがないため Sequential が最適。
        options.ExecutionMode = ExecutionMode.ORT_SEQUENTIAL;

        // メモリ最適化: 事前アロケーションとバッファ再利用で 5-15% 高速化
        options.EnableCpuMemArena = true;
        options.EnableMemoryPattern = true;

        // 動的ブロックサイズ: intra-op スレッドの作業分割を細粒度化しレイテンシ分散を低減
        options.AddSessionConfigEntry("session.dynamic_block_base", "4");

        return options;
    }

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
