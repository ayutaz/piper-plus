package com.github.ayousanz.piper

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext

/**
 * AudioTrack-based audio player for Piper TTS output.
 *
 * Supports both one-shot and streaming playback.
 *
 * Usage:
 * ```kotlin
 * AudioPlayer().use { player ->
 *     // One-shot playback
 *     player.play(audio)
 *
 *     // Streaming playback
 *     player.playStream(tts.synthesizeStream("text"))
 * }
 * ```
 */
class AudioPlayer @JvmOverloads constructor(
    private val sampleRate: Int = 22050,
) : AutoCloseable {

    private val lock = Any()
    private var audioTrack: AudioTrack? = null
    @Volatile
    private var isPlaying = false

    private fun ensureAudioTrack(): AudioTrack {
        audioTrack?.let { return it }

        val bufferSize = AudioTrack.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        ).coerceAtLeast(sampleRate * 2) // At least 1 second buffer

        return AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(sampleRate)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setTransferMode(AudioTrack.MODE_STREAM)
            .setBufferSizeInBytes(bufferSize)
            .build()
            .also { audioTrack = it }
    }

    /**
     * Play a [PiperAudio] instance (one-shot).
     * Suspends until playback is complete.
     */
    suspend fun play(audio: PiperAudio) = withContext(Dispatchers.IO) {
        if (audio.samples.isEmpty()) return@withContext

        val track = ensureAudioTrack()
        synchronized(lock) {
            track.play()
            isPlaying = true
        }
        try {
            track.write(audio.samples, 0, audio.samples.size)
            // Wait for playback to finish
            track.stop()
        } finally {
            synchronized(lock) {
                isPlaying = false
            }
        }
    }

    /**
     * Play a stream of audio chunks from [Flow].
     * Suspends until all chunks are played.
     */
    suspend fun playStream(audioFlow: Flow<ShortArray>) = withContext(Dispatchers.IO) {
        val track = ensureAudioTrack()
        synchronized(lock) {
            track.play()
            isPlaying = true
        }
        try {
            audioFlow.collect { chunk ->
                if (chunk.isNotEmpty()) {
                    track.write(chunk, 0, chunk.size)
                }
            }
            track.stop()
        } catch (e: Exception) {
            synchronized(lock) {
                isPlaying = false
            }
            throw e
        } finally {
            synchronized(lock) {
                isPlaying = false
            }
        }
    }

    /**
     * Stop current playback immediately.
     */
    fun stop() {
        synchronized(lock) {
            if (isPlaying) {
                audioTrack?.apply {
                    pause()
                    flush()
                }
                isPlaying = false
            }
        }
    }

    override fun close() {
        try {
            stop()
        } finally {
            audioTrack?.release()
            audioTrack = null
        }
    }
}
