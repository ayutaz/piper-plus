package com.piperplus.tts

import android.speech.tts.SynthesisCallback

/**
 * PCM チャンクを [SynthesisCallback] に渡す。
 *
 * Android の TTS framework は 16bit little-endian のバイト列を受け取るため、
 * ネイティブ層が返す [ShortArray] をここで詰め替える。
 * バイト順を取り違えても長さもチャンク数も変わらないため、
 * 端末で音が壊れるまで誰も気付かない。[PcmEmitterTest] で固定している。
 *
 * [PiperPlusTtsService] から切り出してあるのは、この変換を Android の
 * Service を起動せずに検証できるようにするため。
 */
internal object PcmEmitter {

    /** 16bit PCM の 1 サンプルあたりのバイト数。 */
    const val BYTES_PER_SAMPLE = 2

    /**
     * [chunk] を little-endian のバイト列にして [callback] へ渡す。
     *
     * [SynthesisCallback.getMaxBufferSize] を超えないよう分割する。
     * 分割の合間に [isStopped] を確認し、停止要求が出ていれば残りを捨てる。
     *
     * @param callback  framework 側の受け口
     * @param chunk     1 文分の PCM サンプル
     * @param isStopped 停止要求の有無を返す関数
     */
    fun emit(callback: SynthesisCallback, chunk: ShortArray, isStopped: () -> Boolean) {
        val bytes = ByteArray(chunk.size * BYTES_PER_SAMPLE)
        for (i in chunk.indices) {
            val value = chunk[i].toInt()
            bytes[i * BYTES_PER_SAMPLE] = (value and 0xFF).toByte()
            bytes[i * BYTES_PER_SAMPLE + 1] = ((value shr 8) and 0xFF).toByte()
        }

        // AOSP の実装はいずれも 8192 を返すが、0 以下を返す callback を
        // 渡されると offset が進まず無限ループになる。1 サンプル分を下限に
        // 置いて、遅くはなっても必ず終わるようにする。
        val maxBufferSize = callback.maxBufferSize.coerceAtLeast(BYTES_PER_SAMPLE)
        var offset = 0
        while (offset < bytes.size) {
            if (isStopped()) return
            val length = minOf(maxBufferSize, bytes.size - offset)
            callback.audioAvailable(bytes, offset, length)
            offset += length
        }
    }
}
