package com.piperplus.g2p

import android.content.Context
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext

/**
 * Downloads the OpenJTalk dictionary from a remote source (typically
 * Hugging Face Hub) into the consumer app's `filesDir`.
 *
 * The default repository is `ayousanz/piper-plus-base`, which ships the
 * dictionary as a single tar archive plus a SHA-256 sum. Callers can override
 * the repo / file name; the host must be in [ALLOWED_HOSTS] (see
 * NFR-SEC-2 — only TLS-enabled, well-known hosts are accepted to keep the
 * trust model simple).
 *
 * F-Droid note: this method makes a non-deterministic network call, so
 * F-Droid distributions must mark the consumer app with the
 * "Non-Free Network Services" anti-feature when they expose the download
 * path through the UI.
 */
object DictionaryDownloader {

    /** Hosts the downloader will accept. Add new mirrors here, not via param. */
    val ALLOWED_HOSTS: Set<String> = setOf(
        "https://huggingface.co",
        "https://hf-mirror.com",
    )

    private const val DEFAULT_HF_HOST     = "https://huggingface.co"
    private const val DEFAULT_HF_REPO     = "ayousanz/piper-plus-base"
    private const val DEFAULT_FILE        = "open_jtalk_dic.tar"
    private const val DEFAULT_SHA256_FILE = "open_jtalk_dic.tar.sha256"
    private const val BUFFER_SIZE         = 32 * 1024
    private const val DEST_DIR_NAME       = "open_jtalk_dic"

    // TAR safety bounds — OpenJTalk dict ≈ 102 MB; 256 MB total / 64 MB per
    // entry leaves comfortable headroom while killing tar-bomb attacks.
    private const val MAX_TOTAL_BYTES     = 256L * 1024 * 1024
    private const val MAX_ENTRY_BYTES     =  64L * 1024 * 1024

    /**
     * Download the OpenJTalk dictionary archive into `context.filesDir`,
     * verify its SHA-256 against a sidecar file, extract it, and return the
     * resulting [OpenJTalkDictionary].
     *
     * The function is idempotent: if a previous extraction already exists
     * (non-empty `filesDir/open_jtalk_dic/` AND a `.complete` marker is
     * present) the function returns immediately without re-downloading. The
     * marker is written only after the full extraction succeeds, so a crash
     * mid-extract leaves the directory in a state we can recover from.
     *
     * @throws IOException on network / IO / checksum / unsafe-archive failures.
     * @throws IllegalArgumentException if [host] is not in [ALLOWED_HOSTS].
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
    ): OpenJTalkDictionary = withContext(Dispatchers.IO) {
        val normalisedHost = host.trimEnd('/')
        require(normalisedHost in ALLOWED_HOSTS) {
            "host not in DictionaryDownloader.ALLOWED_HOSTS: $host"
        }
        require(normalisedHost.startsWith("https://")) {
            "host must use TLS: $host"
        }

        val destDir   = File(context.filesDir, DEST_DIR_NAME)
        val marker    = File(destDir, ".complete")
        if (marker.exists() && (destDir.list()?.isNotEmpty() == true)) {
            return@withContext OpenJTalkDictionary(destDir.absolutePath)
        }

        // Stale partial extraction — wipe and start fresh.
        if (destDir.exists()) destDir.deleteRecursively()

        // Atomic-ish: extract into a sibling staging directory, then rename.
        val staging = File(context.filesDir, "$DEST_DIR_NAME.tmp").also {
            if (it.exists()) it.deleteRecursively()
            it.mkdirs()
        }

        val baseUrl    = "$normalisedHost/${repo.trim('/')}/resolve/main"
        val archiveUrl = "$baseUrl/$archiveFile"
        val shaUrl     = "$baseUrl/$shaFile"

        currentCoroutineContext().ensureActive()
        val expectedSha = downloadString(shaUrl).trim().substringBefore(' ')
        if (expectedSha.length != 64 || !expectedSha.all { it.isLetterOrDigit() }) {
            throw IOException("invalid sha256 sidecar at $shaUrl")
        }

        val tmp = File.createTempFile("piperplus-dic-", ".tar", context.cacheDir)
        try {
            downloadToFile(archiveUrl, tmp, onProgress)
            currentCoroutineContext().ensureActive()
            val actualSha = sha256(tmp)
            if (!actualSha.equals(expectedSha, ignoreCase = true)) {
                throw IOException("sha256 mismatch: expected=$expectedSha actual=$actualSha")
            }
            extractTar(tmp, staging)
        } catch (t: Throwable) {
            staging.deleteRecursively()
            throw t
        } finally {
            tmp.delete()
        }

        // Rename staging → destDir. POSIX rename is atomic when both paths
        // share a filesystem (which they do — both live under filesDir).
        if (!staging.renameTo(destDir)) {
            staging.deleteRecursively()
            throw IOException("could not finalise dict directory: $destDir")
        }
        marker.writeText("ok")
        OpenJTalkDictionary(destDir.absolutePath)
    }

    private fun downloadString(url: String): String {
        val conn = openConnection(url)
        try {
            return conn.inputStream.bufferedReader().use { it.readText() }
        } finally {
            conn.disconnect()
        }
    }

    private suspend fun downloadToFile(
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
                        currentCoroutineContext().ensureActive()
                        val n = input.read(buf)
                        if (n <= 0) break
                        out.write(buf, 0, n)
                        read += n
                        if (read > MAX_TOTAL_BYTES) {
                            throw IOException("dict archive exceeds $MAX_TOTAL_BYTES bytes")
                        }
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
     * dictionary distribution.
     *
     * Hardening (NFR-SEC-2):
     *  - Honours the ustar `prefix` field (offset 345, len 155) so long paths
     *    do not silently truncate.
     *  - Rejects entries whose canonical path escapes [destDir].
     *  - Rejects symlinks, hardlinks, character/block devices, FIFOs.
     *  - Caps per-entry size at [MAX_ENTRY_BYTES] and total at
     *    [MAX_TOTAL_BYTES] to defang TAR-bomb / lying-header attacks.
     */
    private fun extractTar(archive: File, destDir: File) {
        val destCanon = destDir.canonicalFile
        var totalExtracted = 0L
        archive.inputStream().use { input ->
            val header = ByteArray(512)
            while (true) {
                if (!readFully(input, header)) break
                if (header.all { it == 0.toByte() }) break  // end-of-archive

                val nameField   = String(header, 0, 100).trimEndZeros()
                val prefixField = String(header, 345, 155).trimEndZeros()
                val name = if (prefixField.isNotEmpty()) "$prefixField/$nameField" else nameField
                if (name.isEmpty()) continue

                val sizeStr = String(header, 124, 12).trim().trimEnd(0.toChar())
                val typeFlag = header[156]

                if (name.contains("..") || name.startsWith("/") || name.startsWith("\\")) {
                    throw IOException("refusing to extract unsafe path: $name")
                }

                val size = if (sizeStr.isNotEmpty()) sizeStr.toLong(8) else 0L
                if (size < 0 || size > MAX_ENTRY_BYTES) {
                    throw IOException("entry size $size exceeds limit ($MAX_ENTRY_BYTES) for $name")
                }
                totalExtracted += size
                if (totalExtracted > MAX_TOTAL_BYTES) {
                    throw IOException("total extracted bytes exceed $MAX_TOTAL_BYTES")
                }

                val out = File(destDir, name)
                if (!out.canonicalPath.startsWith(destCanon.path + File.separator) &&
                    out.canonicalPath != destCanon.path) {
                    throw IOException("refusing to extract outside destDir: $name")
                }

                when (typeFlag.toInt()) {
                    '5'.code -> {
                        out.mkdirs()
                    }
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
                    '1'.code, '2'.code -> {
                        // Hardlink / symlink — explicit refuse so a malicious
                        // archive can't redirect a write to /data/.../victim.
                        throw IOException("refusing tar entry with link type for $name")
                    }
                    '3'.code, '4'.code, '6'.code -> {
                        throw IOException("refusing tar entry with device type for $name")
                    }
                    else -> {
                        // Unknown / future ustar extensions — skip the payload
                        // but don't write anything to disk.
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
