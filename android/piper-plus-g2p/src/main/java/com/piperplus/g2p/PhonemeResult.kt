package com.piperplus.g2p

/**
 * Result of a single [PiperPlusG2p.phonemize] call.
 *
 * @property phonemes      Space-separated UTF-8 IPA phoneme string. May
 *                         contain Private Use Area codepoints
 *                         (U+E020..U+E04A for Chinese tones,
 *                          U+E016..U+E01C for Japanese question / N markers).
 * @property phonemeList   The same phonemes as an indexable list. A word
 *                         boundary is its own `" "` element (written as three
 *                         spaces in [phonemes]).
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

/**
 * Split the C API's space-joined phoneme string back into tokens.
 *
 * Tokens are joined with a single space, so a word-boundary token `" "`
 * appears as three spaces and splits into two empty parts. Dropping empty
 * parts would lose word boundaries, which `num_phonemes` counts.
 */
internal fun splitPhonemeString(phonemes: String): List<String> {
    if (phonemes.isEmpty()) return emptyList()
    val tokens = mutableListOf<String>()
    var emptyParts = 0
    for (part in phonemes.split(' ')) {
        if (part.isNotEmpty()) {
            emptyParts = 0
            tokens += part
        } else if (++emptyParts == 2) {
            emptyParts = 0
            tokens += " "
        }
    }
    return tokens
}
