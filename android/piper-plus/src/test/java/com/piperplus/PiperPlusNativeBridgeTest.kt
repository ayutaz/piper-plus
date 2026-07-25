package com.piperplus

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Kotlin の `external` 宣言と JNI 側の C++ 定義が一致していることを固定する。
 *
 * この一致はコンパイラが見ていない。片方だけ変えても Kotlin のビルドも
 * C++ のビルドも APK のパッケージングも成功し、実機の初回合成で
 * `UnsatisfiedLinkError` になる。
 *
 * さらに厄介なのが引数の並べ替えで、`nativeSynthesizeWithOptions` の末尾 4 つは
 * すべて `Float` / `jfloat` のため、入れ替えても JNI シグネチャ
 * `(JLjava/lang/String;IIFFFF)[S` は変わらずリンクも通る。
 * `length_scale` と `noise_scale` が入れ替われば常時 2.5 倍速になるが、
 * 型検査もリンクも何も言わない。
 *
 * reflection だけでは足りない — Kotlin 側の `external fun` をリネームすれば
 * 呼び出し元が即コンパイルエラーになるので、compiler が既に強制している。
 * C++ のソースを読むことがこのテストの本体である。
 */
class PiperPlusNativeBridgeTest {
    // ------------------------------------------------------------ 期待する対応

    /** Kotlin の型 → JNI の型。 */
    private val paramTypes =
        mapOf(
            "Long" to "jlong",
            "String" to "jstring",
            "Int" to "jint",
            "Float" to "jfloat",
        )

    private val returnTypes =
        mapOf(
            "Long" to "jlong",
            "Int" to "jint",
            "ShortArray" to "jshortArray",
            "Unit" to "void",
        )

    // ------------------------------------------------------------------ 検証

    @Test
    fun `every external declaration has a matching JNI definition`() {
        val kotlin = parseKotlin()
        val native = parseNative()

        assertTrue("external 宣言が読めていない", kotlin.isNotEmpty())
        assertEquals(
            "Kotlin の external と JNI の実装が対応していない " +
                "(片側だけの rename は実機の初回合成まで気付けない)",
            kotlin.keys.sorted(),
            native.keys.sorted(),
        )
    }

    @Test
    fun `parameter names line up positionally`() {
        val native = parseNative()

        for ((name, kf) in parseKotlin()) {
            val nf = native.getValue(name)
            assertEquals(
                "$name: 引数の並びが Kotlin と JNI でずれている",
                kf.params.map { it.name },
                nf.params.map { it.name },
            )
        }
    }

    @Test
    fun `parameter and return types line up`() {
        val native = parseNative()

        for ((name, kf) in parseKotlin()) {
            val nf = native.getValue(name)
            assertEquals(
                "$name: 引数の型が Kotlin と JNI でずれている",
                kf.params.map { paramTypes.getValue(it.type) },
                nf.params.map { it.type },
            )
            assertEquals(
                "$name: 戻り値の型が Kotlin と JNI でずれている",
                returnTypes.getValue(kf.returnType),
                nf.returnType,
            )
        }
    }

    @Test
    fun `each option field is assigned from the identically named parameter`() {
        // opts.noise_w = noiseScale のような本体側の取り違えを捕まえる。
        // 引数の並びが合っていても、代入で入れ替われば同じことが起きる。
        val assignments =
            parseNative()
                .values
                .flatMap { fn -> OPTS_ASSIGN.findAll(fn.body).map { fn.name to it } }

        assertTrue("opts への代入が 1 つも見つからない", assignments.isNotEmpty())

        for ((fnName, match) in assignments) {
            val field = match.groupValues[1]
            val source = match.groupValues[2]
            assertEquals(
                "$fnName: opts.$field に $source を代入している",
                snakeToCamel(field),
                source,
            )
        }
    }

    @Test
    fun `the options overloads forward every SynthOptions field`() {
        val native = parseNative()

        for (name in listOf("nativeSynthesizeWithOptions", "nativeSynthStartWithOptions")) {
            val assigned =
                OPTS_ASSIGN
                    .findAll(native.getValue(name).body)
                    .map { snakeToCamel(it.groupValues[1]) }
                    .toSet()
            assertEquals(
                "$name: SynthOptions のフィールドが JNI に渡されていない " +
                    "(追加したフィールドの配線漏れ)",
                synthOptionsFields(),
                assigned,
            )
        }
    }

    @Test
    fun `call sites bind each named argument to the field of the same name`() {
        // PiperPlus.kt は named argument で呼んでいるが、
        // lengthScale = options.noiseScale と書いてもコンパイルは通る。
        val source = sourceFile("src/main/java/com/piperplus/PiperPlus.kt").readText()
        val bindings = NAMED_OPTION_ARG.findAll(source).toList()

        // options 版が 2 つ、それぞれ 6 フィールド。
        assertEquals(
            "PiperPlus.kt の options 渡しが期待数と違う",
            2 * synthOptionsFields().size,
            bindings.size,
        )
        for (match in bindings) {
            assertEquals(
                "PiperPlus.kt: ${match.value} は名前とフィールドが食い違っている",
                match.groupValues[2],
                match.groupValues[1],
            )
        }
    }

    // ------------------------------------------------------------------ 解析

    private data class Param(
        val type: String,
        val name: String,
    )

    private data class KotlinFun(
        val name: String,
        val params: List<Param>,
        val returnType: String,
    )

    private data class NativeFun(
        val name: String,
        val params: List<Param>,
        val returnType: String,
        val body: String,
    )

    private fun parseKotlin(): Map<String, KotlinFun> {
        val source = sourceFile("src/main/java/com/piperplus/PiperPlusNative.kt").readText()
        return EXTERNAL_FUN.findAll(source).associate { match ->
            val name = match.groupValues[1]
            val params =
                splitArgs(match.groupValues[2]).map { arg ->
                    val (paramName, rawType) = arg.split(":", limit = 2)
                    Param(rawType.trim().removeSuffix("?"), paramName.trim())
                }
            val returnType = match.groupValues[3].ifEmpty { "Unit" }.removeSuffix("?")
            name to KotlinFun(name, params, returnType)
        }
    }

    private fun parseNative(): Map<String, NativeFun> {
        val source = sourceFile("src/main/cpp/piper_plus_jni.cpp").readText()
        return JNI_FUN.findAll(source).associate { match ->
            val name = match.groupValues[2]
            // JNIEnv* と jobject は JNI の規約で必ず先頭 2 つ。
            // 名前がコメントアウトされている (JNIEnv * /* env */) こともあるため
            // 位置で落とす。
            val declared = splitArgs(match.groupValues[3].replace(BLOCK_COMMENT, " "))
            val params =
                declared.drop(2).map { arg ->
                    val tokens = arg.split(Regex("[\\s*]+")).filter { it.isNotBlank() }
                    Param(tokens.first(), tokens.last())
                }
            name to
                NativeFun(
                    name = name,
                    params = params,
                    returnType = match.groupValues[1],
                    body = bodyAfter(source, match.range.last),
                )
        }
    }

    /** 関数シグネチャ直後の `{ ... }` を波括弧の対応をとって切り出す。 */
    private fun bodyAfter(
        source: String,
        signatureEnd: Int,
    ): String {
        val open = source.indexOf('{', signatureEnd)
        if (open < 0) return ""
        var depth = 0
        for (i in open until source.length) {
            when (source[i]) {
                '{' -> depth++
                '}' -> {
                    depth--
                    if (depth == 0) return source.substring(open, i + 1)
                }
            }
        }
        return source.substring(open)
    }

    private fun splitArgs(raw: String): List<String> = raw.split(",").map { it.trim() }.filter { it.isNotEmpty() }

    private fun snakeToCamel(value: String): String =
        value
            .split("_")
            .mapIndexed { index, part ->
                if (index == 0) part else part.replaceFirstChar { it.uppercase() }
            }.joinToString("")

    /** [SynthOptions] のプロパティ名。フィールド追加時の配線漏れを検出するため。 */
    private fun synthOptionsFields(): Set<String> =
        SynthOptions::class.java.declaredFields
            .filterNot { it.isSynthetic }
            .map { it.name }
            .toSet()

    /**
     * モジュール相対のソースを解決する。
     *
     * gradle の Test タスクはモジュールディレクトリを作業ディレクトリにするが、
     * 別の場所から起動されても動くよう上位ディレクトリも探す。
     * 見つからない場合は skip せず落とす — 契約検査が黙って無効化されるのは
     * テストが無いより悪い。
     */
    private fun sourceFile(relative: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            for (prefix in listOf("", "android/piper-plus/")) {
                val candidate = File(dir, prefix + relative)
                if (candidate.isFile) return candidate
            }
            dir = dir.parentFile
        }
        assertNotNull("ソースが見つからない: $relative", null)
        error("unreachable")
    }

    private companion object {
        val EXTERNAL_FUN =
            Regex(
                """external fun\s+(\w+)\s*\(([^)]*)\)\s*(?::\s*([\w]+\??))?""",
            )
        val JNI_FUN =
            Regex(
                """JNIEXPORT\s+(\w+)\s+JNICALL\s+Java_com_piperplus_PiperPlusNative_(\w+)\s*\(([^)]*)\)""",
            )
        val OPTS_ASSIGN = Regex("""opts\.(\w+)\s*=\s*(?:static_cast<[^>]+>\()?(\w+)""")
        val NAMED_OPTION_ARG = Regex("""(\w+)\s*=\s*options\.(\w+)""")
        val BLOCK_COMMENT = Regex("""/\*.*?\*/""", RegexOption.DOT_MATCHES_ALL)
    }
}
