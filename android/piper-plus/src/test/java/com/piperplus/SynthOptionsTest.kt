package com.piperplus

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SynthOptionsTest {

    @Test
    fun `defaults match piper_plus_default_options in the C API`() {
        // JNI は piper_plus_default_options() を呼んだ直後に 6 フィールド
        // すべてを Kotlin 由来の値で上書きする。つまり C 側の既定値は
        // Android 経路に一切届かず、ここのリテラルが実効既定値になる。
        // C の値を実際に読んで突き合わせないと、C 側だけが変わったときに
        // Android だけ古い既定値で鳴り続ける。
        val expected = parseCDefaults()
        val actual = kotlinDefaults()

        assertEquals(
            "C API と Kotlin でフィールドの顔ぶれが違う",
            expected.keys.sorted(),
            actual.keys.sorted(),
        )
        for ((field, value) in expected) {
            assertEquals(
                "SynthOptions.$field が C API の既定値と食い違っている",
                value,
                actual.getValue(field),
                TOLERANCE,
            )
        }
    }

    @Test
    fun `allows overriding individual fields`() {
        val options = SynthOptions(languageId = 2, lengthScale = 0.5f)
        assertEquals(2, options.languageId)
        assertEquals(0.5f, options.lengthScale, TOLERANCE.toFloat())
        // 未指定のフィールドは既定値のまま
        assertEquals(0, options.speakerId)
    }

    // ------------------------------------------------------------------ 解析

    /** `piper_plus_default_options()` の本体から `opts.<field> = <value>` を読む。 */
    private fun parseCDefaults(): Map<String, Double> {
        val source = sourceFile("src/cpp/piper_plus_c_api.cpp").readText()
        val start = source.indexOf(DEFAULT_OPTIONS_SIGNATURE)
        assertTrue(
            "piper_plus_default_options() が見つからない (署名が変わった?)",
            start >= 0,
        )
        val end = source.indexOf("\n}", start)
        val body = source.substring(start, if (end >= 0) end else source.length)

        val defaults = ASSIGNMENT.findAll(body).associate { match ->
            snakeToCamel(match.groupValues[1]) to match.groupValues[2].removeSuffix("f").toDouble()
        }
        assertTrue("既定値の代入が読み取れていない", defaults.isNotEmpty())
        return defaults
    }

    private fun kotlinDefaults(): Map<String, Double> {
        val instance = SynthOptions()
        return SynthOptions::class.java.declaredFields
            .filterNot { it.isSynthetic }
            .associate { field ->
                field.isAccessible = true
                field.name to (field.get(instance) as Number).toDouble()
            }
    }

    private fun snakeToCamel(value: String): String =
        value.split("_").mapIndexed { index, part ->
            if (index == 0) part else part.replaceFirstChar { it.uppercase() }
        }.joinToString("")

    private fun sourceFile(relative: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            val candidate = File(dir, relative)
            if (candidate.isFile) return candidate
            dir = dir.parentFile
        }
        throw AssertionError("ソースが見つからない: $relative")
    }

    private companion object {
        const val TOLERANCE = 1e-6
        const val DEFAULT_OPTIONS_SIGNATURE = "piper_plus_default_options(void) {"
        val ASSIGNMENT = Regex("""opts\.(\w+)\s*=\s*(-?[\d.]+f?);""")
    }
}
