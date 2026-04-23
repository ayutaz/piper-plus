using Microsoft.ML.OnnxRuntime;
using PiperPlus.Core.Config;

namespace PiperPlus.Core.Inference;

/// <summary>
/// Wraps an ONNX Runtime <see cref="InferenceSession"/> for a Piper TTS model,
/// exposing model capabilities detected from input tensor metadata.
/// </summary>
/// <remarks>
/// Capability detection mirrors the C++ implementation in <c>piper.cpp:loadModel</c>
/// and the Python implementation in <c>infer_onnx.py</c>, which inspect input names
/// for optional tensors such as <c>sid</c> (multi-speaker) and
/// <c>prosody_features</c> (A1/A2/A3 prosody).
/// </remarks>
public sealed class PiperModel : IDisposable
{
    private readonly InferenceSession _session;
    private bool _disposed;

    /// <summary>
    /// Initializes a new <see cref="PiperModel"/> by inspecting the session's
    /// input metadata for optional capabilities.
    /// </summary>
    /// <param name="session">
    /// A pre-created <see cref="InferenceSession"/>. Ownership is transferred;
    /// the session will be disposed when this instance is disposed.
    /// </param>
    /// <param name="config">
    /// The parsed <c>config.json</c> that accompanies the ONNX model.
    /// </param>
    public PiperModel(InferenceSession session, PiperConfig config)
    {
        ArgumentNullException.ThrowIfNull(session);
        ArgumentNullException.ThrowIfNull(config);

        _session = session;

        // Materialise input names once for capability detection and public access.
        InputNames = _session.InputMetadata.Keys.ToList().AsReadOnly();

        // Detect optional capabilities from tensor names.
        HasSpeakerId = _session.InputMetadata.ContainsKey("sid");
        HasLanguageId = _session.InputMetadata.ContainsKey("lid");
        HasProsody = _session.InputMetadata.ContainsKey("prosody_features");

        // Detect duration output capability (mirrors C++ piper.cpp:loadModel).
        HasDurationOutput = _session.OutputMetadata.ContainsKey("durations");

        // Detect voice cloning capability (speaker_embedding + speaker_embedding_mask).
        HasSpeakerEmbedding = _session.InputMetadata.ContainsKey("speaker_embedding");

        // Phase 2 (P2-T05): Detect style_vector conditioning capability.
        HasStyleVector = _session.InputMetadata.ContainsKey("style_vector");
        if (HasStyleVector)
        {
            // Resolution order: ONNX custom metadata → ONNX input shape → 0.
            StyleVectorDim = 0;

            var customMeta = _session.ModelMetadata.CustomMetadataMap;
            if (customMeta != null
                && customMeta.TryGetValue("style_vector_dim", out var dimStr)
                && int.TryParse(dimStr, out var dimFromMeta))
            {
                StyleVectorDim = dimFromMeta;
            }

            if (StyleVectorDim <= 0
                && _session.InputMetadata.TryGetValue("style_vector", out var styleMeta))
            {
                // Dimensions[1] is the dim (axis 0 is dynamic batch).
                if (styleMeta.Dimensions.Length >= 2 && styleMeta.Dimensions[1] > 0)
                {
                    StyleVectorDim = styleMeta.Dimensions[1];
                }
            }
        }

        SampleRate = config.Audio.SampleRate;

        // Hop size needed for durations-based Strategy A trim (issue #356).
        // Falls back to ShortTextProcessor.DefaultHopSize when the config
        // omits audio.hop_size (older configs).
        int hop = config.Audio.HopSize ?? 0;
        HopSize = hop > 0 ? hop : ShortTextProcessor.DefaultHopSize;
    }

    // ----------------------------------------------------------------
    // Model capabilities
    // ----------------------------------------------------------------

    /// <summary>
    /// <c>true</c> when the model accepts a <c>sid</c> (speaker-id) tensor,
    /// indicating a multi-speaker model.
    /// </summary>
    public bool HasSpeakerId { get; }

    /// <summary>
    /// <c>true</c> when the model accepts a <c>lid</c> (language-id) tensor,
    /// indicating a multilingual model.
    /// </summary>
    public bool HasLanguageId { get; }

    /// <summary>
    /// <c>true</c> when the model accepts a <c>prosody_features</c> tensor
    /// (A1/A2/A3 accent information from OpenJTalk).
    /// </summary>
    public bool HasProsody { get; }

    /// <summary>
    /// <c>true</c> when the model produces a <c>durations</c> output tensor,
    /// providing per-phoneme duration information.
    /// Mirrors <c>hasDurationOutput</c> in the C++ implementation (<c>piper.cpp</c>).
    /// </summary>
    public bool HasDurationOutput { get; }

    /// <summary>
    /// <c>true</c> when the model accepts <c>speaker_embedding</c> (float32)
    /// and <c>speaker_embedding_mask</c> (int64) inputs for voice cloning.
    /// </summary>
    public bool HasSpeakerEmbedding { get; }

    /// <summary>
    /// Phase 2 (P2-T05): <c>true</c> when the model accepts
    /// <c>style_vector</c> (float32) and <c>style_vector_mask</c>
    /// (int64) inputs for PE-AV / PE-A style conditioning.
    /// </summary>
    public bool HasStyleVector { get; }

    /// <summary>
    /// Expected <c>style_vector</c> dimension. Resolved from ONNX custom
    /// metadata (<c>style_vector_dim</c>) first, falling back to the ONNX
    /// input shape. 0 when the feature is not present.
    /// </summary>
    public int StyleVectorDim { get; }

    /// <summary>
    /// Audio sample rate in Hz, sourced from the accompanying config.json.
    /// </summary>
    public int SampleRate { get; }

    /// <summary>
    /// VITS hop length (samples per acoustic frame) used by the
    /// durations-based Strategy A post-trim (issue #356). Defaults to
    /// <see cref="ShortTextProcessor.DefaultHopSize"/> (256) when the
    /// config does not declare <c>audio.hop_size</c>.
    /// </summary>
    public int HopSize { get; }

    /// <summary>
    /// Ordered list of input tensor names exposed by the ONNX model.
    /// </summary>
    public IReadOnlyList<string> InputNames { get; }

    // ----------------------------------------------------------------
    // Internal access for the inference pipeline
    // ----------------------------------------------------------------

    /// <summary>
    /// The underlying ONNX Runtime session. Intended for use by the
    /// inference pipeline within this assembly.
    /// </summary>
    internal InferenceSession Session
    {
        get
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            return _session;
        }
    }

    // ----------------------------------------------------------------
    // IDisposable
    // ----------------------------------------------------------------

    /// <inheritdoc/>
    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _session.Dispose();
        _disposed = true;
    }
}
