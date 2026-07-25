package com.piperplus.tts

import android.speech.tts.TextToSpeech
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.piperplus.tts.model.ModelPaths
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/**
 * モデル未導入の端末での可用性判定を確認する。
 *
 * 実モデルを使った合成の検証は、モデルを配置できる CI ジョブで別途行う。
 */
@RunWith(AndroidJUnit4::class)
class PiperPlusTtsServiceTest {

    @Test
    fun `reports missing data for a supported language when no model is installed`() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val paths = ModelPaths(context.filesDir)
        // 事前条件: 既定モデルが未導入であること
        assertEquals(false, paths.isInstalled(ModelPaths.DEFAULT_MODEL_ID))

        assertEquals(
            TextToSpeech.LANG_MISSING_DATA,
            LocaleResolver.availability("jpn", paths.isInstalled(ModelPaths.DEFAULT_MODEL_ID)),
        )
    }

    @Test
    fun `reports not supported for an unsupported language`() {
        assertEquals(
            TextToSpeech.LANG_NOT_SUPPORTED,
            LocaleResolver.availability("kor", modelInstalled = true),
        )
    }
}
