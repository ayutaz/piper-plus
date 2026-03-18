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
    val modelPath: String,
    val configPath: String,
    val speakerId: Int = 0,
    val noiseScale: Float = 0.667f,
    val lengthScale: Float = 1.0f,
    val noiseW: Float = 0.8f,
)
