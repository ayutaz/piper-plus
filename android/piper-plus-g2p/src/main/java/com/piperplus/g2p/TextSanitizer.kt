package com.piperplus.g2p

/**
 * Strips control characters from a text before it is read, by the rule every
 * piper-plus runtime shares (`docs/spec/input-sanitize-contract.toml`).
 *
 * libpiper_plus strips too, but it cannot see a NUL: JNI hands it the text
 * as modified UTF-8, where U+0000 is the two bytes `C0 80`, and the native
 * strip keeps bytes that are not valid UTF-8. [PiperPlusG2p.phonemize]
 * therefore strips before the native call.
 */
object TextSanitizer {
    /**
     * Return [text] cleaned by the input-sanitize rule: `\n`, `\t` and `\r`
     * stay (sentence splitting and SSML use them); VT, FF and NEL (U+000B,
     * U+000C, U+0085) become a space; every other control character (Unicode
     * category Cc: U+0000-001F, U+007F-009F) is removed. Format characters,
     * separators, NBSP and surrogates stay. Idempotent.
     */
    @JvmStatic
    fun stripControlChars(text: String): String {
        val out = StringBuilder(text.length)
        for (ch in text) {
            when {
                ch == '\n' || ch == '\t' || ch == '\r' -> out.append(ch)
                ch == VT || ch == FF || ch == NEL -> out.append(' ')
                ch <= C0_LAST || ch in DEL..C1_LAST -> Unit
                else -> out.append(ch)
            }
        }
        return out.toString()
    }

    private const val VT = '\u000B'
    private const val FF = '\u000C'
    private const val NEL = '\u0085'
    private const val C0_LAST = '\u001F'
    private const val DEL = '\u007F'
    private const val C1_LAST = '\u009F'
}
