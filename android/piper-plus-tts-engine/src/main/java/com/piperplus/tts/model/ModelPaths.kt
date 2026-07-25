package com.piperplus.tts.model

import java.io.File

/**
 * 端末上のモデル・辞書のパスを解決する。
 *
 * 配置は次の通り (すべて内部ストレージ `context.filesDir` 配下):
 * ```
 * models/<model-id>/model.onnx
 * models/<model-id>/model.onnx.json
 * open_jtalk_dic/
 * ```
 *
 * @param filesDir アプリの内部ストレージルート (`context.filesDir`)
 */
class ModelPaths(private val filesDir: File) {

    fun modelDir(modelId: String): File = File(File(filesDir, MODELS_DIR), modelId)

    fun modelFile(modelId: String): File = File(modelDir(modelId), MODEL_FILE)

    fun configFile(modelId: String): File = File(modelDir(modelId), CONFIG_FILE)

    fun dictDir(): File = File(filesDir, DICT_DIR)

    /**
     * モデル・設定・辞書がすべて揃っているか。
     *
     * 辞書は日本語合成にのみ必要だが、初版では言語によらず必須として扱う
     * (言語ごとの遅延取得は複雑さに見合わない)。
     */
    fun isInstalled(modelId: String): Boolean =
        modelFile(modelId).isFile && configFile(modelId).isFile && dictDir().isDirectory

    companion object {
        /**
         * 初版で使う既定モデル (6 言語すべてを話す)。
         *
         * `piper-core` の組込みレジストリ (`model_download.rs:builtin_registry`)
         * のモデル名と一致させてある。
         */
        const val DEFAULT_MODEL_ID = "css10-6lang"

        private const val MODELS_DIR = "models"
        private const val MODEL_FILE = "model.onnx"
        private const val CONFIG_FILE = "model.onnx.json"
        private const val DICT_DIR = "open_jtalk_dic"
    }
}
