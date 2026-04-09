// PiperTTSAsync.cs — Asynchronous TTS API with Task-based pattern for Unity

using System;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace PiperPlus
{
    /// <summary>
    /// Asynchronous text-to-speech engine for Unity.
    /// Synthesis runs on a worker thread; AudioClip creation happens on the main thread.
    /// Thread-safe: all native calls are serialized via an internal lock.
    /// </summary>
    public sealed class PiperTTSAsync : IDisposable
    {
        private readonly PiperTTS _tts;
        private readonly SynchronizationContext _mainThreadContext;
        private bool _disposed;

        private PiperTTSAsync(PiperTTS tts, SynchronizationContext context)
        {
            _tts = tts;
            _mainThreadContext = context;
        }

        /// <summary>
        /// Create an async TTS engine from an ONNX model.
        /// Must be called from the main Unity thread.
        /// </summary>
        /// <param name="modelPath">Path to the .onnx model file.</param>
        /// <param name="configPath">Path to the .json config file. Null for auto-resolve.</param>
        /// <param name="dictDir">Optional OpenJTalk dictionary directory.</param>
        /// <param name="provider">Execution provider. Null for CPU.</param>
        /// <returns>A new PiperTTSAsync instance.</returns>
        public static PiperTTSAsync Create(
            string modelPath,
            string configPath = null,
            string dictDir = null,
            string provider = null)
        {
            var context = SynchronizationContext.Current;
            var tts = PiperTTS.Create(modelPath, configPath, dictDir, provider);
            return new PiperTTSAsync(tts, context);
        }

        /// <summary>
        /// Create an async TTS engine from a PiperModel ScriptableObject.
        /// Must be called from the main Unity thread.
        /// </summary>
        public static PiperTTSAsync Create(PiperModel model)
        {
            var context = SynchronizationContext.Current;
            var tts = PiperTTS.Create(model);
            return new PiperTTSAsync(tts, context);
        }

        /// <summary>
        /// Synthesize text to an AudioClip asynchronously.
        /// Synthesis runs on a worker thread; the AudioClip is created on the main thread.
        /// </summary>
        /// <param name="text">Text to synthesize.</param>
        /// <param name="language">Language code. Null for auto-detect.</param>
        /// <param name="config">Optional synthesis configuration.</param>
        /// <param name="cancellationToken">Cancellation token.</param>
        /// <returns>An AudioClip containing the synthesized audio.</returns>
        public async Task<AudioClip> SynthesizeAsync(
            string text,
            string language = null,
            PiperConfig config = null,
            CancellationToken cancellationToken = default)
        {
            ThrowIfDisposed();

            int sampleRate;
            float[] samples = await SynthesizeRawInternalAsync(text, language, config, cancellationToken);

            if (samples == null || samples.Length == 0)
                return null;

            sampleRate = _tts.SampleRate;

            // AudioClip.Create must be called on the main thread
            if (_mainThreadContext != null && SynchronizationContext.Current != _mainThreadContext)
            {
                AudioClip clip = null;
                var tcs = new TaskCompletionSource<AudioClip>();
                int capturedSampleRate = sampleRate;
                float[] capturedSamples = samples;

                _mainThreadContext.Post(_ =>
                {
                    try
                    {
                        clip = AudioClipExtensions.CreateFromPcm(capturedSamples, capturedSampleRate);
                        tcs.SetResult(clip);
                    }
                    catch (Exception ex)
                    {
                        tcs.SetException(ex);
                    }
                }, null);

                return await tcs.Task;
            }

            return AudioClipExtensions.CreateFromPcm(samples, sampleRate);
        }

        /// <summary>
        /// Synthesize text to raw float PCM samples asynchronously.
        /// Runs entirely on a worker thread.
        /// </summary>
        /// <param name="text">Text to synthesize.</param>
        /// <param name="language">Language code. Null for auto-detect.</param>
        /// <param name="config">Optional synthesis configuration.</param>
        /// <param name="cancellationToken">Cancellation token.</param>
        /// <returns>Float array of PCM samples.</returns>
        public Task<float[]> SynthesizeRawAsync(
            string text,
            string language = null,
            PiperConfig config = null,
            CancellationToken cancellationToken = default)
        {
            ThrowIfDisposed();
            return SynthesizeRawInternalAsync(text, language, config, cancellationToken);
        }

        private Task<float[]> SynthesizeRawInternalAsync(
            string text,
            string language,
            PiperConfig config,
            CancellationToken cancellationToken)
        {
            return Task.Run(() =>
            {
                cancellationToken.ThrowIfCancellationRequested();
                return _tts.SynthesizeRaw(text, language, config);
            }, cancellationToken);
        }

        /// <inheritdoc cref="PiperTTS.SampleRate"/>
        public int SampleRate => _tts.SampleRate;

        /// <inheritdoc cref="PiperTTS.NumSpeakers"/>
        public int NumSpeakers => _tts.NumSpeakers;

        /// <inheritdoc cref="PiperTTS.NumLanguages"/>
        public int NumLanguages => _tts.NumLanguages;

        /// <inheritdoc cref="PiperTTS.GetLanguageId"/>
        public int GetLanguageId(string languageCode) => _tts.GetLanguageId(languageCode);

        /// <inheritdoc cref="PiperTTS.AvailableLanguages"/>
        public string AvailableLanguages => _tts.AvailableLanguages;

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            _tts.Dispose();
        }

        private void ThrowIfDisposed()
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(PiperTTSAsync));
        }
    }
}
