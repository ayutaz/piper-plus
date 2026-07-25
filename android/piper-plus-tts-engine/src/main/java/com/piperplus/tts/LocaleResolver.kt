package com.piperplus.tts

import android.speech.tts.TextToSpeech

/**
 * Android の ISO-639-3 言語コードを piper-plus の `language_id` に対応付ける。
 *
 * `language_id_map` は 6lang モデル共通で `{ja:0, en:1, zh:2, es:3, fr:4, pt:5}`。
 * 1 つの 6lang モデルが 6 言語すべてを話すため、言語切替はモデルの入れ替えでは
 * なく `language_id` の変更で行う。
 *
 * 国・方言コードは区別しない。`ja-JP` と `ja` は同一に扱うため
 * `LANG_COUNTRY_AVAILABLE` は返さない。
 */
object LocaleResolver {

    /** ISO-639-3 → language_id。`cmn` は Android が返す `zho` の別名として受理する。 */
    private val ISO3_TO_LANGUAGE_ID: Map<String, Int> = mapOf(
        "jpn" to 0,
        "eng" to 1,
        "zho" to 2,
        "cmn" to 2,
        "spa" to 3,
        "fra" to 4,
        "por" to 5,
    )

    /** `onGetLanguage` などで提示する代表コード (`cmn` の別名は含めない)。 */
    val SUPPORTED_ISO3: List<String> = listOf("jpn", "eng", "zho", "spa", "fra", "por")

    /** 対応言語なら `language_id`、非対応なら null を返す。 */
    fun languageIdOf(iso3Language: String): Int? =
        ISO3_TO_LANGUAGE_ID[iso3Language.lowercase()]

    /**
     * `TextToSpeechService.onIsLanguageAvailable` / `onLoadLanguage` の戻り値を求める。
     *
     * @param modelInstalled モデルと辞書が端末に揃っているか
     */
    fun availability(iso3Language: String, modelInstalled: Boolean): Int = when {
        languageIdOf(iso3Language) == null -> TextToSpeech.LANG_NOT_SUPPORTED
        !modelInstalled -> TextToSpeech.LANG_MISSING_DATA
        else -> TextToSpeech.LANG_AVAILABLE
    }
}
