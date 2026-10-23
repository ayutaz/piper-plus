package com.piperplus.g2p

import android.content.Context
import android.system.ErrnoException
import android.system.Os
import android.util.Log
import java.io.File
import java.io.IOException
import java.io.InputStream

/**
 * English (CMU) and Mandarin (pinyin) dictionaries bundled in the AAR.
 *
 * `piper_plus_g2p_create` reads `cmudict_data.json` / `pinyin_single.json` /
 * `pinyin_phrases.json` from `dict_dir`, then from the
 * `PIPER_PLUS_DICTIONARIES_PATH` environment variable. Without them most
 * English words and Chinese characters produce no phonemes, so
 * [PiperPlusG2p.create] extracts the assets once and points the environment
 * variable at them. `dict_dir` stays free for the OpenJTalk dictionary.
 */
internal object BundledDictionaries {
    const val ASSET_DIR = "piper_plus_g2p_dicts"
    const val ENV_VAR = "PIPER_PLUS_DICTIONARIES_PATH"
    val FILES = listOf("cmudict_data.json", "pinyin_single.json", "pinyin_phrases.json")

    private const val MARKER = ".complete"
    private const val TAG = "PiperPlusG2p"

    @Volatile
    private var configured = false

    /**
     * Extract the dictionaries (first call only) and export their directory
     * through [ENV_VAR]. A value the app already set is kept. On failure
     * English and Chinese degrade, the other languages keep working.
     */
    @Synchronized
    fun configure(context: Context) {
        if (configured) return
        try {
            val dir = extract(
                File(context.noBackupFilesDir, ASSET_DIR),
                PiperPlusG2pNative.nativeVersion(),
            ) { name -> context.assets.open("$ASSET_DIR/$name") }
            Os.setenv(ENV_VAR, dir.absolutePath, false)
            configured = true
        } catch (e: IOException) {
            Log.w(TAG, "English/Chinese dictionaries unavailable: $e")
        } catch (e: ErrnoException) {
            Log.w(TAG, "could not set $ENV_VAR: $e")
        }
    }

    /**
     * Copy [FILES] into `root/v<version>` unless an earlier call completed
     * there, and delete directories left by other versions. Each file is
     * written to a temporary name first so an interrupted copy is redone.
     */
    fun extract(root: File, version: String, open: (String) -> InputStream): File {
        // The "v" prefix keeps names like ".." from leaving [root].
        val dir = File(root, "v" + version.replace(Regex("[^A-Za-z0-9._-]"), "_"))
        val marker = File(dir, MARKER)
        if (!marker.isFile) {
            if (!dir.isDirectory && !dir.mkdirs()) throw IOException("cannot create $dir")
            for (name in FILES) {
                val tmp = File(dir, "$name.tmp")
                open(name).use { input -> tmp.outputStream().use { input.copyTo(it) } }
                val dest = File(dir, name)
                dest.delete()
                if (!tmp.renameTo(dest)) throw IOException("cannot move $tmp to $dest")
            }
            marker.writeText(version)
        }
        root.listFiles()?.filter { it != dir }?.forEach { it.deleteRecursively() }
        return dir
    }
}
