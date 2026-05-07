package com.piperplus.g2p

import android.content.Context
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * Downloads the OpenJTalk dictionary from a remote source (typically
 * Hugging Face Hub) into the consumer app's `filesDir`.
 *
 * The default repository is `ayousanz/piper-plus-base`, which ships the
 * dictionary as a single tar archive plus a SHA-256 sum. Callers can override
 * the host / repo / file name when they prefer to host the dictionary
 * themselves (e.g. CDN, F-Droid mirror).
 *
 * F-Droid note: this method makes a non-deterministic network call, so
 * F-Droid distributions must mark the consumer app with the
 * "Non-Free Network Services" anti-feature when they expose the download
 * path through the UI.
 */
object DictionaryDownloader {

    private const val DEFAULT_HF_HOST  = "https://huggingface.co"
    private const val DEFAULT_HF_REPO  = "ayousanz/piper-plus-base"
    private const val DEFAULT_FILE     = "open_jtalk_dic.tar"
    private const val DEFAULT_SHA256_FILE = "open_jtalk_dic.tar.sha256"
    private const val BUFFER_SIZE      = 32 * 1024
    private const val DEST_DIR_NAME    = "open_jtalk_dic"

    /**
     * Download the OpenJTalk dictionary archive into `context.filesDir`,
     * verify its SHA-256 against a sidecar file, extract it, and return the
     * resulting [OpenJTalkDictionary].
     *
     * The function is idempotent: if a previous extraction already exists
     * (non-empty `filesDir/open_jtalk_dic/`) the function returns immediately
     * without re-downloading.
     *
     * @throws IOException on network / IO / checksum failures.
     */
    @JvmStatic
    @JvmOverloads
    suspend fun downloadFromHuggingFace(
        context: Context,
        repo: String = DEFAULT_HF_REPO,
        archiveFile: String = DEFAULT_FILE,
        shaFile: String = DEFAULT_SHA256_FILE,
        host: String = DEFAULT_HF_HOST,
        onProgress: (bytesRead: Long, total: Long) -> Unit = { _, _ -> },
    ): OpenJTalkDictionary {
        val destDir = File(context.filesDir, DEST_DIR_NAME)
        if (destDir.isDirectory && (destDir.list()?.isNotEmpty() == true)) {
            return OpenJTalkDictionary(destDir.absolutePath)
        }
        destDir.mkdirs()

        val baseUrl = "${host.trimEnd('/')}/${repo.trim('/')}/resolve/main"
        val archiveUrl = "$baseUrl/$archiveFile"
        val shaUrl     = "$baseUrl/$shaFile"

        // 1. Download SHA-256 sidecar (small text file) first so we can
        //    abort early if it's missing.
        val expectedSha = downloadString(shaUrl).trim().substringBefore(' ')
        if (expectedSha.length != 64) {
            throw IOException("invalid sha256 sidecar at $shaUrl")
        }

        // 2. Download archive into a temp file and verify checksum.
        val tmp = File.createTempFile("piperplus-dic-", ".tar", context.cacheDir)
        try {
            downloadToFile(archiveUrl, tmp, onProgress)
            val actualSha = sha256(tmp)
            if (!actualSha.equals(expectedSha, ignoreCase = true)) {
                throw IOException("sha256 mismatch: expected=$expectedSha actual=$actualSha")
            }
            // 3. Extract the tar archive into destDir.
            extractTar(tmp, destDir)
        } finally {
            tmp.delete()
        }

        return OpenJTalkDictionary(destDir.absolutePath)
    }

    private fun downloadString(url: String): String {
        val conn = openConnection(url)
        try {
            return conn.inputStream.bufferedReader().use { it.readText() }
        } finally {
            conn.disconnect()
        }
    }

    private fun downloadToFile(
        url: String,
        dest: File,
        onProgress: (Long, Long) -> Unit,
    ) {
        val conn = openConnection(url)
        try {
            val total = conn.contentLengthLong
            FileOutputStream(dest).use { out ->
                conn.inputStream.use { input ->
                    val buf = ByteArray(BUFFER_SIZE)
                    var read = 0L
                    while (true) {
                        val n = input.read(buf)
                        if (n <= 0) break
                        out.write(buf, 0, n)
                        read += n
                        onProgress(read, total)
                    }
                }
            }
        } finally {
            conn.disconnect()
        }
    }

    private fun openConnection(url: String): HttpURLConnection {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.requestMethod = "GET"
        conn.connectTimeout = 30_000
        conn.readTimeout = 60_000
        conn.instanceFollowRedirects = true
        if (conn.responseCode !in 200..299) {
            val rc = conn.responseCode
            conn.disconnect()
            throw IOException("HTTP $rc fetching $url")
        }
        return conn
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buf = ByteArray(BUFFER_SIZE)
            while (true) {
                val n = input.read(buf)
                if (n <= 0) break
                digest.update(buf, 0, n)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    /**
     * Minimal POSIX TAR (ustar) extractor sufficient for the OpenJTalk
     * dictionary distribution. Skips file types other than regular files
     * and directories. Symlink-safe: refuses entries with absolute paths
     * or `..` components.
     */
    private fun extractTar(archive: File, destDir: File) {
        archive.inputStream().use { input ->
            val header = ByteArray(512)
            while (true) {
                if (!readFully(input, header)) break
                if (header.all { it == 0.toByte() }) break  // end-of-archive
                val name    = String(header, 0, 100).trimEndZeros()
                val sizeStr = String(header, 124, 12).trim().trimEnd(0.toChar())
                val typeFlag = header[156]
                if (name.isEmpty()) continue

                if (name.contains("..") || name.startsWith("/")) {
                    throw IOException("refusing to extract unsafe path: $name")
                }

                val size = if (sizeStr.isNotEmpty()) sizeStr.toLong(8) else 0L
                val out = File(destDir, name)
                when (typeFlag.toInt()) {
                    '5'.code -> out.mkdirs()
                    '0'.code, 0 -> {
                        out.parentFile?.mkdirs()
                        FileOutputStream(out).use { fos ->
                            var remaining = size
                            val buf = ByteArray(BUFFER_SIZE)
                            while (remaining > 0) {
                                val toRead = minOf(buf.size.toLong(), remaining).toInt()
                                val n = input.read(buf, 0, toRead)
                                if (n <= 0) throw IOException("unexpected EOF in tar")
                                fos.write(buf, 0, n)
                                remaining -= n
                            }
                        }
                    }
                    else -> {
                        // Skip unsupported entry types (symlink, etc.)
                        skipFully(input, size)
                    }
                }
                // Tar pads each entry to 512-byte boundary
                val padding = ((size + 511) / 512) * 512 - size
                skipFully(input, padding)
            }
        }
    }

    private fun readFully(input: java.io.InputStream, buf: ByteArray): Boolean {
        var read = 0
        while (read < buf.size) {
            val n = input.read(buf, read, buf.size - read)
            if (n < 0) return read > 0  // partial = treat as EOF
            read += n
        }
        return true
    }

    private fun skipFully(input: java.io.InputStream, count: Long) {
        var remaining = count
        while (remaining > 0) {
            val skipped = input.skip(remaining)
            if (skipped <= 0) {
                if (input.read() < 0) return
                remaining -= 1
            } else {
                remaining -= skipped
            }
        }
    }

    private fun String.trimEndZeros(): String {
        val idx = this.indexOf(0.toChar())
        return if (idx >= 0) this.substring(0, idx) else this
    }
}
