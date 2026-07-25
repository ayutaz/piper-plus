package com.piperplus

/**
 * 合成オプション。C API の `PiperPlusSynthOptions` に 1:1 対応する。
 *
 * 既定値は `src/cpp/piper_plus.h` の規定に合わせてある。
 *
 * @param speakerId          話者インデックス (0 始まり)
 * @param languageId         言語インデックス。-1 で自動判定
 * @param lengthScale        大きいほど遅い
 * @param noiseScale         VITS noise_scale
 * @param noiseW             VITS noise_w
 * @param sentenceSilenceSec 文間の無音 (秒)
 */
data class SynthOptions(
    val speakerId: Int = 0,
    val languageId: Int = -1,
    val lengthScale: Float = 1.0f,
    val noiseScale: Float = 0.4f,
    val noiseW: Float = 0.5f,
    val sentenceSilenceSec: Float = 0.2f,
)
