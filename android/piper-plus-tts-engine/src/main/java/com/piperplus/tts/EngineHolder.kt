package com.piperplus.tts

import com.piperplus.PiperPlus
import com.piperplus.SynthOptions
import com.piperplus.tts.model.ModelPaths
import kotlinx.coroutines.flow.Flow

/**
 * 合成エンジンの抽象。
 *
 * [PiperPlus] を直接扱うと JVM ユニットテストで JNI のロードが走るため、
 * この境界を挟んでテスト時に差し替えられるようにする。
 */
interface PiperPlusEngine {
    /**
     * ロード済みモデルのサンプルレート (Hz)。
     *
     * `callback.start()` に渡す値なので、モデルの実値と食い違うと
     * 全発話がピッチのずれた音として再生される。
     */
    val sampleRate: Int

    fun synthesizeStream(text: String, options: SynthOptions): Flow<ShortArray>
    fun close()
}

/** モデルのパスからエンジンを生成する。 */
fun interface EngineFactory {
    fun create(modelPath: String, configPath: String, dictDir: String): PiperPlusEngine
}

/**
 * エンジンインスタンスの生存管理。
 *
 * モデルのロードは数百 ms かかるため、同じモデルの間はインスタンスを再利用する。
 * モデルが切り替わったときは前のインスタンスを確実に閉じる。
 */
class EngineHolder(
    private val paths: ModelPaths,
    private val factory: EngineFactory,
) {
    private val lock = Any()
    private var engine: PiperPlusEngine? = null
    private var loadedModelId: String? = null

    /**
     * 指定モデルのエンジンを取得する。キャッシュがあれば再利用する。
     *
     * @throws IllegalStateException モデルまたは辞書が未インストールの場合
     */
    fun acquire(modelId: String): PiperPlusEngine = synchronized(lock) {
        val cached = engine
        if (cached != null && loadedModelId == modelId) {
            return cached
        }
        check(paths.isInstalled(modelId)) { "Model is not installed: $modelId" }

        cached?.close()
        engine = null
        loadedModelId = null

        val created = factory.create(
            paths.modelFile(modelId).absolutePath,
            paths.configFile(modelId).absolutePath,
            paths.dictDir().absolutePath,
        )
        engine = created
        loadedModelId = modelId
        return created
    }

    /** キャッシュ中のエンジンを解放する。複数回呼んでも安全。 */
    fun release() = synchronized(lock) {
        engine?.close()
        engine = null
        loadedModelId = null
    }
}
