package com.piperplus.tts

/** Android TTS の合成パラメータを piper-plus の scales に変換する。 */
object SynthesisParams {
    /** Android TTS が等速を表す値 (`SynthesisRequest.speechRate`)。 */
    private const val NORMAL_SPEECH_RATE = 100

    /**
     * `speechRate` を piper-plus の `length_scale` に変換する。
     *
     * Android は「大きいほど速い」、piper-plus の `length_scale` は
     * 「大きいほど遅い」ため逆数を取る。
     * 0 以下は不正値として等速にフォールバックする (ゼロ除算の回避も兼ねる)。
     */
    fun lengthScaleOf(speechRate: Int): Float =
        if (speechRate <= 0) {
            1.0f
        } else {
            NORMAL_SPEECH_RATE.toFloat() / speechRate.toFloat()
        }
}
