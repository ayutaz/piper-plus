package com.piperplus.tts

import android.speech.tts.TextToSpeechService
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * manifest の Service 配線を固定する。
 *
 * `android:name` のタイポやクラスの移動、intent-filter の綴りミスは
 * `assembleDebug` を通過する。APK は問題なくできあがり、CI も緑のまま、
 * 端末の 設定 → 音声出力 にエンジンが 1 つも現れない。
 */
class ManifestWiringTest {

    private val manifest: String by lazy { manifestFile().readText() }

    @Test
    fun `the declared service resolves to a TextToSpeechService`() {
        val declared = SERVICE_NAME.find(manifest)?.groupValues?.get(1)
        assertNotNull("manifest に service の android:name が無い", declared)

        // ".PiperPlusTtsService" のような相対名を applicationId で絶対名にする。
        // namespace を変えたときに黙って陳腐化しないよう、ハードコードしない。
        val absolute = if (declared!!.startsWith(".")) {
            BuildConfig.APPLICATION_ID + declared
        } else {
            declared
        }

        val loaded = Class.forName(absolute, false, javaClass.classLoader)
        assertTrue(
            "$absolute は TextToSpeechService を継承していない",
            TextToSpeechService::class.java.isAssignableFrom(loaded),
        )
    }

    @Test
    fun `the service is exported with the TTS intent filter`() {
        // action が 1 文字でも違うとシステムがエンジンとして認識しない。
        // lint では守れないため、ここで文字列として固定する。
        assertTrue(
            "TTS_SERVICE の action が無い",
            manifest.contains("""<action android:name="android.intent.action.TTS_SERVICE" />"""),
        )
        assertTrue(
            "DEFAULT の category が無い",
            manifest.contains("""<category android:name="android.intent.category.DEFAULT" />"""),
        )
        // exported=false だとシステムから bind できない。
        assertTrue("service が exported されていない", manifest.contains("""android:exported="true""""))
    }

    @Test
    fun `the service points at the tts engine metadata`() {
        assertTrue(
            "android.speech.tts の meta-data が無い",
            manifest.contains("""android:name="android.speech.tts""""),
        )
        assertTrue(
            "@xml/tts_engine を参照していない",
            manifest.contains("""android:resource="@xml/tts_engine""""),
        )
    }

    private fun manifestFile(): File = resolve("src/main/AndroidManifest.xml")

    /**
     * モジュール相対のファイルを解決する。見つからない場合は skip せず落とす —
     * 契約検査が黙って無効化されるのはテストが無いより悪い。
     */
    private fun resolve(relative: String): File {
        var dir: File? = File(System.getProperty("user.dir") ?: ".").absoluteFile
        while (dir != null) {
            for (prefix in listOf("", "android/piper-plus-tts-engine/")) {
                val candidate = File(dir, prefix + relative)
                if (candidate.isFile) return candidate
            }
            dir = dir.parentFile
        }
        throw AssertionError("ファイルが見つからない: $relative")
    }

    private companion object {
        val SERVICE_NAME = Regex("""<service\s+android:name="([^"]+)"""")
        val LANGUAGE_ATTR = Regex("""android:name="([a-z]{3})"""")
    }
}
