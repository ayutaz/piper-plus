package com.piperplus.g2p

import android.content.Context
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream

/**
 * Reference to an extracted OpenJTalk dictionary directory.
 *
 * The dictionary is required only for Japanese G2P (other 7 languages work
 * without it). It is intentionally NOT bundled inside the AAR (~102 MB) —
 * the consuming app supplies it via one of these strategies:
 *
 * 1. **Bundled assets** — place the dictionary under `assets/open_jtalk_dic/`
 *    in your APK and call [fromAssets].
 * 2. **Filesystem path** — use [fromPath] when the dictionary lives at a
 *    known absolute path (e.g. `Context.filesDir`).
 * 3. **Runtime download** — use `DictionaryDownloader` (M6) to fetch from
 *    Hugging Face Hub on first launch.
 *
 * The returned [path] is what gets passed to [PiperPlusG2p.create] which in
 * turn forwards it to the native C API as `dict_dir`.
 */
class OpenJTalkDictionary internal constructor(val path: String) {

    /** True if the directory exists and contains at least one file. */
    fun exists(): Boolean {
        val dir = File(path)
        return dir.isDirectory && (dir.list()?.isNotEmpty() == true)
    }

    companion object {
        private const val DEFAULT_ASSET_PATH = "open_jtalk_dic"
        private const val EXTRACT_DIR_NAME   = "open_jtalk_dic"
        private const val BUFFER_SIZE        = 8 * 1024

        /**
         * Extract `assets/<assetPath>/` into `context.filesDir` (idempotent)
         * and return a handle to the resulting directory.
         *
         * Re-extraction is skipped when the destination is non-empty.
         */
        @JvmStatic
        @JvmOverloads
        fun fromAssets(
            context: Context,
            assetPath: String = DEFAULT_ASSET_PATH,
        ): OpenJTalkDictionary {
            val destDir = File(context.filesDir, EXTRACT_DIR_NAME)
            if (!destDir.exists() || (destDir.list()?.isEmpty() != false)) {
                destDir.mkdirs()
                extractAssetTree(context, assetPath, destDir)
            }
            return OpenJTalkDictionary(destDir.absolutePath)
        }

        /** Wrap a known absolute filesystem path. The path is not validated. */
        @JvmStatic
        fun fromPath(absolutePath: String): OpenJTalkDictionary =
            OpenJTalkDictionary(absolutePath)

        private fun extractAssetTree(context: Context, assetSubdir: String, destDir: File) {
            val assetManager = context.assets
            val children = assetManager.list(assetSubdir).orEmpty()
            for (entry in children) {
                val assetPath = "$assetSubdir/$entry"
                val outFile = File(destDir, entry)
                val nested = assetManager.list(assetPath)
                if (nested != null && nested.isNotEmpty()) {
                    outFile.mkdirs()
                    extractAssetTree(context, assetPath, outFile)
                } else {
                    assetManager.open(assetPath).use { input ->
                        copyTo(input, outFile)
                    }
                }
            }
        }

        private fun copyTo(input: InputStream, dest: File) {
            FileOutputStream(dest).use { out ->
                val buf = ByteArray(BUFFER_SIZE)
                while (true) {
                    val n = input.read(buf)
                    if (n <= 0) break
                    out.write(buf, 0, n)
                }
            }
        }
    }
}
