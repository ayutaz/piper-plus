package com.piperplus.tts

import android.speech.tts.SynthesisCallback
import android.speech.tts.TextToSpeech

/**
 * 呼び出し列を記録する [SynthesisCallback]。
 *
 * 「何が呼ばれたか」だけでなく「**何が呼ばれなかったか**」を検証できるよう、
 * 全イベントを [events] に順番どおり積む。
 *
 * `android.jar` のスタブ実装は使わないこと — `isReturnDefaultValues = true` の
 * 下では [getMaxBufferSize] が 0 を返し、[PcmEmitter] のループが進まなくなる。
 *
 * @param bufferSize        [getMaxBufferSize] が返す値
 * @param onAudioAvailable  [audioAvailable] の直後に呼ばれるフック。
 *                          引数は「今回が何回目の呼び出しか」(1 始まり)。
 *                          合成の途中で `stop()` を起こすために使う。
 */
internal class FakeSynthesisCallback(
    private val bufferSize: Int = DEFAULT_BUFFER_SIZE,
    private val onAudioAvailable: (callCount: Int) -> Unit = {},
) : SynthesisCallback {

    /** 呼び出し列。`start` / `audio(offset=..,length=..)` / `done` / `error(..)`。 */
    val events = mutableListOf<String>()

    /** 受け取った音声。production は 1 本の配列を使い回すため必ず複製する。 */
    val audio = mutableListOf<ByteArray>()

    /** [start] に渡された (sampleRate, audioFormat, channelCount)。 */
    var startArgs: Triple<Int, Int, Int>? = null
        private set

    private var started = false
    private var finished = false
    private var audioCallCount = 0

    /** 受け取った音声を 1 本に連結したもの。 */
    fun audioBytes(): ByteArray {
        val out = ByteArray(audio.sumOf { it.size })
        var offset = 0
        for (part in audio) {
            part.copyInto(out, offset)
            offset += part.size
        }
        return out
    }

    override fun getMaxBufferSize(): Int = bufferSize

    override fun start(sampleRateInHz: Int, audioFormat: Int, channelCount: Int): Int {
        started = true
        startArgs = Triple(sampleRateInHz, audioFormat, channelCount)
        events += "start"
        return TextToSpeech.SUCCESS
    }

    override fun audioAvailable(buffer: ByteArray, offset: Int, length: Int): Int {
        // production は :emit で確保した 1 本の配列を全反復で共有するため、
        // 参照のまま保持すると全チャンクが同一内容に見えてしまう。
        audio += buffer.copyOfRange(offset, offset + length)
        events += "audio(offset=$offset,length=$length)"
        audioCallCount += 1
        onAudioAvailable(audioCallCount)
        return TextToSpeech.SUCCESS
    }

    override fun done(): Int {
        finished = true
        events += "done"
        return TextToSpeech.SUCCESS
    }

    override fun error() {
        events += "error"
    }

    override fun error(errorCode: Int) {
        events += "error($errorCode)"
    }

    override fun hasStarted(): Boolean = started

    override fun hasFinished(): Boolean = finished

    companion object {
        /** AOSP の PlaybackSynthesisCallback / FileSynthesisCallback と同値。 */
        const val DEFAULT_BUFFER_SIZE = 8192
    }
}
