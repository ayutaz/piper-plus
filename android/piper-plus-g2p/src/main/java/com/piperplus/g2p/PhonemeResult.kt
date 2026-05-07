package com.piperplus.g2p

/**
 * Result of a single [PiperPlusG2p.phonemize] call.
 *
 * @property phonemes      Space-separated UTF-8 IPA phoneme string. May
 *                         contain Private Use Area codepoints
 *                         (U+E020..U+E04A for Chinese tones,
 *                          U+E016..U+E01C for Japanese question / N markers).
 * @property phonemeList   The same phonemes split on whitespace. Convenience
 *                         for callers that need an indexable list.
 * @property language      The language code that was either passed in
 *                         explicitly or auto-detected (e.g. `"en"`, `"ja"`,
 *                         `"unknown"` if detection failed).
 * @property numPhonemes   Number of tokens produced. Always equals
 *                         `phonemeList.size`.
 */
data class PhonemeResult(
    val phonemes: String,
    val phonemeList: List<String>,
    val language: String,
    val numPhonemes: Int,
)
