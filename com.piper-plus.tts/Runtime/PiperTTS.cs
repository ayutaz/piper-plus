// PiperTTS.cs — Synchronous high-level TTS API for Unity

using System;
using System.Runtime.InteropServices;
using UnityEngine;

namespace PiperPlus
{
    /// <summary>
    /// Synchronous text-to-speech engine wrapping the piper-plus native library.
    /// Thread-safe: all native calls are serialized via an internal lock.
    /// Implements IDisposable for deterministic resource cleanup.
    /// </summary>
    public sealed class PiperTTS : IDisposable
    {
        private IntPtr _engine;
        private readonly object _lock = new object();
        private bool _disposed;

        private PiperTTS(IntPtr engine)
        {
            _engine = engine;
        }

        ~PiperTTS()
        {
            Dispose(false);
        }

        /// <summary>
        /// Create a TTS engine from an ONNX model.
        /// </summary>
        /// <param name="modelPath">Path to the .onnx model file.</param>
        /// <param name="configPath">
        /// Path to the .json config file. Pass null to auto-resolve (model_path + ".json").
        /// </param>
        /// <param name="dictDir">Optional OpenJTalk dictionary directory. Null for auto-detect.</param>
        /// <param name="provider">Execution provider: "cpu", "cuda", "coreml", "directml". Null for CPU.</param>
        /// <returns>A new PiperTTS instance.</returns>
        /// <exception cref="PiperException">Thrown if engine creation fails.</exception>
        public static PiperTTS Create(
            string modelPath,
            string configPath = null,
            string dictDir = null,
            string provider = null)
        {
            if (string.IsNullOrEmpty(modelPath))
                throw new ArgumentNullException(nameof(modelPath));

            IntPtr modelPathUtf8  = IntPtr.Zero;
            IntPtr configPathUtf8 = IntPtr.Zero;
            IntPtr dictDirUtf8    = IntPtr.Zero;
            IntPtr providerUtf8   = IntPtr.Zero;

            try
            {
                modelPathUtf8  = Utf8Marshaller.StringToUtf8(modelPath);
                configPathUtf8 = Utf8Marshaller.StringToUtf8(configPath);
                dictDirUtf8    = Utf8Marshaller.StringToUtf8(dictDir);
                providerUtf8   = Utf8Marshaller.StringToUtf8(provider);

                var config = new PiperPlusConfig
                {
                    model_path    = modelPathUtf8,
                    config_path   = configPathUtf8,
                    dict_dir      = dictDirUtf8,
                    provider      = providerUtf8,
                    num_threads   = 0,
                    gpu_device_id = 0,
                };

                IntPtr engine;
                var status = PiperPlusNative.piper_plus_create(ref config, out engine);
                if (status != PiperPlusStatus.Ok)
                {
                    string error = Utf8Marshaller.Utf8ToString(PiperPlusNative.piper_plus_get_last_error());
                    throw new PiperException(status, error ?? "Failed to create engine");
                }

                return new PiperTTS(engine);
            }
            finally
            {
                FreeIfNotZero(modelPathUtf8);
                FreeIfNotZero(configPathUtf8);
                FreeIfNotZero(dictDirUtf8);
                FreeIfNotZero(providerUtf8);
            }
        }

        /// <summary>
        /// Create a TTS engine from a PiperModel ScriptableObject.
        /// </summary>
        public static PiperTTS Create(PiperModel model)
        {
            if (model == null)
                throw new ArgumentNullException(nameof(model));

            return Create(
                model.ResolvedModelPath,
                model.ResolvedConfigPath,
                string.IsNullOrEmpty(model.dictDir) ? null : model.dictDir,
                string.IsNullOrEmpty(model.provider) ? null : model.provider);
        }

        /// <summary>
        /// Synthesize text to a Unity AudioClip.
        /// </summary>
        /// <param name="text">Text to synthesize.</param>
        /// <param name="language">Language code (e.g., "ja", "en"). Null for auto-detect.</param>
        /// <param name="config">Optional synthesis configuration. Null for defaults.</param>
        /// <returns>An AudioClip containing the synthesized audio.</returns>
        public AudioClip Synthesize(string text, string language = null, PiperConfig config = null)
        {
            int sampleRate;
            float[] samples = SynthesizeRaw(text, language, config, out sampleRate);
            if (samples == null || samples.Length == 0)
                return null;

            return AudioClipExtensions.CreateFromPcm(samples, sampleRate);
        }

        /// <summary>
        /// Synthesize text to raw float PCM samples.
        /// </summary>
        /// <param name="text">Text to synthesize.</param>
        /// <param name="language">Language code. Null for auto-detect.</param>
        /// <param name="config">Optional synthesis configuration.</param>
        /// <returns>Float array of PCM samples (range -1.0 to 1.0).</returns>
        public float[] SynthesizeRaw(string text, string language = null, PiperConfig config = null)
        {
            int sampleRate;
            return SynthesizeRaw(text, language, config, out sampleRate);
        }

        /// <summary>
        /// Synthesize text to raw float PCM samples with sample rate output.
        /// </summary>
        public float[] SynthesizeRaw(string text, string language, PiperConfig config, out int sampleRate)
        {
            ThrowIfDisposed();

            if (string.IsNullOrEmpty(text))
                throw new ArgumentNullException(nameof(text));

            config = config ?? PiperConfig.Default;

            // Resolve language to ID if provided
            var opts = config.ToNative();
            if (!string.IsNullOrEmpty(language) && opts.language_id < 0)
            {
                opts.language_id = GetLanguageId(language);
            }

            IntPtr textUtf8 = IntPtr.Zero;
            IntPtr samplesPtr = IntPtr.Zero;

            try
            {
                textUtf8 = Utf8Marshaller.StringToUtf8(text);

                int numSamples;
                int outSampleRate;
                PiperPlusStatus status;

                lock (_lock)
                {
                    ThrowIfDisposed();
                    status = PiperPlusNative.piper_plus_synthesize(
                        _engine, textUtf8, ref opts,
                        out samplesPtr, out numSamples, out outSampleRate);
                }

                if (status != PiperPlusStatus.Ok)
                {
                    string error = Utf8Marshaller.Utf8ToString(PiperPlusNative.piper_plus_get_last_error());
                    throw new PiperException(status, error ?? "Synthesis failed");
                }

                sampleRate = outSampleRate;

                // Copy native float array to managed
                float[] result = new float[numSamples];
                if (numSamples > 0)
                {
                    Marshal.Copy(samplesPtr, result, 0, numSamples);
                }

                return result;
            }
            finally
            {
                FreeIfNotZero(textUtf8);
                if (samplesPtr != IntPtr.Zero)
                    PiperPlusNative.piper_plus_free_audio(samplesPtr);
            }
        }

        /// <summary>Model sample rate in Hz.</summary>
        public int SampleRate
        {
            get
            {
                ThrowIfDisposed();
                lock (_lock) { return PiperPlusNative.piper_plus_sample_rate(_engine); }
            }
        }

        /// <summary>Number of speakers in the model.</summary>
        public int NumSpeakers
        {
            get
            {
                ThrowIfDisposed();
                lock (_lock) { return PiperPlusNative.piper_plus_num_speakers(_engine); }
            }
        }

        /// <summary>Number of languages in the model.</summary>
        public int NumLanguages
        {
            get
            {
                ThrowIfDisposed();
                lock (_lock) { return PiperPlusNative.piper_plus_num_languages(_engine); }
            }
        }

        /// <summary>
        /// Get the language index for a language code.
        /// </summary>
        /// <param name="languageCode">Language code (e.g., "ja", "en").</param>
        /// <returns>Language index, or -1 if not found.</returns>
        public int GetLanguageId(string languageCode)
        {
            ThrowIfDisposed();

            if (string.IsNullOrEmpty(languageCode))
                return -1;

            IntPtr langUtf8 = Utf8Marshaller.StringToUtf8(languageCode);
            try
            {
                lock (_lock)
                {
                    return PiperPlusNative.piper_plus_language_id(_engine, langUtf8);
                }
            }
            finally
            {
                FreeIfNotZero(langUtf8);
            }
        }

        /// <summary>
        /// Get comma-separated list of available language codes.
        /// </summary>
        public string AvailableLanguages
        {
            get
            {
                ThrowIfDisposed();
                lock (_lock)
                {
                    IntPtr ptr = PiperPlusNative.piper_plus_available_languages(_engine);
                    return Utf8Marshaller.Utf8ToString(ptr) ?? string.Empty;
                }
            }
        }

        /// <summary>
        /// Load a custom dictionary file.
        /// </summary>
        public void LoadCustomDict(string dictPath)
        {
            ThrowIfDisposed();

            IntPtr pathUtf8 = Utf8Marshaller.StringToUtf8(dictPath);
            try
            {
                PiperPlusStatus status;
                lock (_lock)
                {
                    status = PiperPlusNative.piper_plus_load_custom_dict(_engine, pathUtf8);
                }

                if (status != PiperPlusStatus.Ok)
                {
                    string error = Utf8Marshaller.Utf8ToString(PiperPlusNative.piper_plus_get_last_error());
                    throw new PiperException(status, error ?? "Failed to load custom dictionary");
                }
            }
            finally
            {
                FreeIfNotZero(pathUtf8);
            }
        }

        /// <summary>
        /// Clear the custom dictionary.
        /// </summary>
        public void ClearCustomDict()
        {
            ThrowIfDisposed();

            lock (_lock)
            {
                PiperPlusNative.piper_plus_clear_custom_dict(_engine);
            }
        }

        /// <summary>
        /// Get the piper-plus native library version string.
        /// </summary>
        public static string NativeVersion
        {
            get
            {
                IntPtr ptr = PiperPlusNative.piper_plus_version();
                return Utf8Marshaller.Utf8ToString(ptr) ?? "unknown";
            }
        }

        public void Dispose()
        {
            Dispose(true);
            GC.SuppressFinalize(this);
        }

        private void Dispose(bool disposing)
        {
            if (_disposed) return;

            lock (_lock)
            {
                if (_disposed) return;
                _disposed = true;

                if (_engine != IntPtr.Zero)
                {
                    PiperPlusNative.piper_plus_free(_engine);
                    _engine = IntPtr.Zero;
                }
            }
        }

        private void ThrowIfDisposed()
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(PiperTTS));
        }

        private static void FreeIfNotZero(IntPtr ptr)
        {
            if (ptr != IntPtr.Zero)
                Marshal.FreeHGlobal(ptr);
        }
    }

    /// <summary>
    /// Exception thrown by piper-plus native operations.
    /// </summary>
    public class PiperException : Exception
    {
        /// <summary>Native status code.</summary>
        public PiperPlusStatus Status { get; }

        public PiperException(PiperPlusStatus status, string message)
            : base($"[PiperPlus] {status}: {message}")
        {
            Status = status;
        }
    }
}
