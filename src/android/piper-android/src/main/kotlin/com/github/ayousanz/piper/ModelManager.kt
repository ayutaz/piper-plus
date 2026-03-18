package com.github.ayousanz.piper

import android.content.Context
import java.io.File

/**
 * Manages Piper TTS model files on Android.
 *
 * Models are stored in the app's internal storage under `piper/models/`.
 */
class ModelManager(private val context: Context) {

    /** Base directory for Piper models. */
    val modelsDir: File
        get() = File(context.filesDir, "piper/models").apply { mkdirs() }

    /**
     * List all available models (directories containing .onnx + .json).
     */
    fun listModels(): List<ModelInfo> {
        return modelsDir.listFiles()
            ?.filter { it.isDirectory }
            ?.mapNotNull { dir ->
                val onnx = dir.listFiles()?.firstOrNull { it.name.endsWith(".onnx") }
                val json = dir.listFiles()?.firstOrNull { it.name.endsWith(".json") }
                if (onnx != null && json != null) {
                    ModelInfo(
                        name = dir.name,
                        modelPath = onnx.absolutePath,
                        configPath = json.absolutePath,
                        sizeBytes = onnx.length() + json.length(),
                    )
                } else null
            }
            ?: emptyList()
    }

    /**
     * Copy a model from assets to internal storage.
     *
     * @param assetDir Asset directory containing model.onnx and config.json
     * @return ModelInfo for the copied model
     */
    fun installFromAssets(assetDir: String): ModelInfo {
        val targetDir = File(modelsDir, assetDir).apply { mkdirs() }

        context.assets.list(assetDir)?.forEach { fileName ->
            val targetFile = File(targetDir, fileName)
            if (!targetFile.exists()) {
                context.assets.open("$assetDir/$fileName").use { input ->
                    targetFile.outputStream().use { output ->
                        input.copyTo(output)
                    }
                }
            }
        }

        return listModels().first { it.name == assetDir }
    }

    /**
     * Delete a model from internal storage.
     */
    fun deleteModel(name: String): Boolean {
        val dir = File(modelsDir, name)
        return dir.exists() && dir.deleteRecursively()
    }

    /**
     * Check if a model exists.
     */
    fun hasModel(name: String): Boolean {
        val dir = File(modelsDir, name)
        return dir.exists() &&
               dir.listFiles()?.any { it.name.endsWith(".onnx") } == true
    }

    /**
     * Information about an installed model.
     */
    data class ModelInfo(
        val name: String,
        val modelPath: String,
        val configPath: String,
        val sizeBytes: Long,
    ) {
        /** Create a PiperConfig from this model info. */
        fun toConfig(
            speakerId: Int = PiperConfig.DEFAULT_SPEAKER_ID,
            noiseScale: Float = PiperConfig.DEFAULT_NOISE_SCALE,
            lengthScale: Float = PiperConfig.DEFAULT_LENGTH_SCALE,
        ): PiperConfig = PiperConfig(
            modelPath = modelPath,
            configPath = configPath,
            speakerId = speakerId,
            noiseScale = noiseScale,
            lengthScale = lengthScale,
        )

        /** Human-readable model size. */
        val sizeDisplay: String
            get() = when {
                sizeBytes >= 1_000_000 -> String.format("%.1f MB", sizeBytes / 1_000_000.0)
                sizeBytes >= 1_000 -> String.format("%.1f KB", sizeBytes / 1_000.0)
                else -> "$sizeBytes B"
            }
    }
}
