// PiperConfig.cs — Synthesis configuration for PiperTTS

namespace PiperPlus
{
    /// <summary>
    /// Configuration for TTS synthesis parameters.
    /// All values of 0 use the engine defaults.
    /// </summary>
    [System.Serializable]
    public class PiperConfig
    {
        /// <summary>Speaker index (default: 0).</summary>
        public int speakerId;

        /// <summary>
        /// Language index. -1 for auto-detect (default).
        /// Use <see cref="PiperTTS.GetLanguageId"/> to resolve a language code to an index.
        /// </summary>
        public int languageId = -1;

        /// <summary>VITS noise_scale. 0 uses default (0.667).</summary>
        public float noiseScale;

        /// <summary>VITS length_scale. 0 uses default (1.0).</summary>
        public float lengthScale;

        /// <summary>VITS noise_w. 0 uses default (0.8).</summary>
        public float noiseW;

        /// <summary>Silence between sentences in seconds. 0 uses default (0.2).</summary>
        public float sentenceSilence;

        /// <summary>
        /// Convert to native PiperPlusSynthOptions struct.
        /// </summary>
        internal PiperPlusSynthOptions ToNative()
        {
            return new PiperPlusSynthOptions
            {
                speaker_id           = speakerId,
                language_id          = languageId,
                noise_scale          = noiseScale,
                length_scale         = lengthScale,
                noise_w              = noiseW,
                sentence_silence_sec = sentenceSilence,
            };
        }

        /// <summary>
        /// Create a default configuration.
        /// </summary>
        public static PiperConfig Default => new PiperConfig();
    }
}
