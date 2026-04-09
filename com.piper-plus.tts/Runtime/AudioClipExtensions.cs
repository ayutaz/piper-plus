// AudioClipExtensions.cs — AudioClip creation helpers for PCM data

using UnityEngine;

namespace PiperPlus
{
    /// <summary>
    /// Extension methods and helpers for creating Unity AudioClips from raw PCM data.
    /// </summary>
    public static class AudioClipExtensions
    {
        /// <summary>
        /// Create an AudioClip from float PCM samples (range -1.0 to 1.0).
        /// </summary>
        /// <param name="samples">Float PCM sample data.</param>
        /// <param name="sampleRate">Sample rate in Hz (default: 22050).</param>
        /// <param name="name">Name for the AudioClip.</param>
        /// <returns>A new AudioClip containing the audio data.</returns>
        public static AudioClip CreateFromPcm(float[] samples, int sampleRate = 22050, string name = "piper_tts")
        {
            if (samples == null || samples.Length == 0)
            {
                Debug.LogWarning("[PiperPlus] Cannot create AudioClip from empty samples.");
                return null;
            }

            var clip = AudioClip.Create(name, samples.Length, 1, sampleRate, false);
            clip.SetData(samples, 0);
            return clip;
        }

        /// <summary>
        /// Create an AudioClip from 16-bit integer PCM samples.
        /// Converts int16 range (-32768 to 32767) to float range (-1.0 to 1.0).
        /// </summary>
        /// <param name="samples">Int16 PCM sample data.</param>
        /// <param name="sampleRate">Sample rate in Hz (default: 22050).</param>
        /// <param name="name">Name for the AudioClip.</param>
        /// <returns>A new AudioClip containing the audio data.</returns>
        public static AudioClip CreateFromInt16(short[] samples, int sampleRate = 22050, string name = "piper_tts")
        {
            if (samples == null || samples.Length == 0)
            {
                Debug.LogWarning("[PiperPlus] Cannot create AudioClip from empty samples.");
                return null;
            }

            const float scale = 1.0f / 32768.0f;
            float[] floatSamples = new float[samples.Length];
            for (int i = 0; i < samples.Length; i++)
            {
                floatSamples[i] = samples[i] * scale;
            }

            return CreateFromPcm(floatSamples, sampleRate, name);
        }
    }
}
