package com.github.ayousanz.piper

/**
 * Configuration for Piper TTS engine.
 *
 * @param modelPath Path to the ONNX model file
 * @param configPath Path to the model config.json file
 * @param speakerId Default speaker ID (0 for single-speaker models)
 * @param noiseScale Controls phoneme-level variability (default: 0.667)
 * @param lengthScale Controls speech speed (< 1.0 = faster, > 1.0 = slower)
 * @param noiseW Controls phoneme width variability (default: 0.8)
 */
data class PiperConfig @JvmOverloads constructor(
    @JvmField val modelPath: String,
    @JvmField val configPath: String,
    @JvmField val speakerId: Int = DEFAULT_SPEAKER_ID,
    @JvmField val noiseScale: Float = DEFAULT_NOISE_SCALE,
    @JvmField val lengthScale: Float = DEFAULT_LENGTH_SCALE,
    @JvmField val noiseW: Float = DEFAULT_NOISE_W,
) {
    init {
        require(noiseScale >= 0f) { "noiseScale must be non-negative" }
        require(lengthScale > 0f) { "lengthScale must be positive" }
        require(noiseW in 0f..1f) { "noiseW must be in range [0, 1]" }
        require(speakerId >= 0) { "speakerId must be non-negative" }
        require(modelPath.isNotEmpty()) { "modelPath must not be empty" }
        require(configPath.isNotEmpty()) { "configPath must not be empty" }
    }

    companion object {
        const val DEFAULT_SPEAKER_ID = 0
        const val DEFAULT_NOISE_SCALE = 0.667f
        const val DEFAULT_LENGTH_SCALE = 1.0f
        const val DEFAULT_NOISE_W = 0.8f
    }
}
