package com.github.ayousanz.piper.sample

/**
 * Represents the current state of TTS playback.
 */
sealed interface PlaybackState {
    /** Engine not loaded yet. */
    data object Uninitialized : PlaybackState

    /** Ready to synthesize. */
    data object Idle : PlaybackState

    /** Loading the TTS model. */
    data object Loading : PlaybackState

    /** Synthesizing audio from text. */
    data class Synthesizing(val text: String) : PlaybackState

    /** Playing synthesized audio. */
    data class Playing(val durationSeconds: Float) : PlaybackState

    /** An error occurred. */
    data class Error(val message: String) : PlaybackState
}

/**
 * Supported languages with display names.
 */
enum class TtsLanguage(val code: String, val displayName: String) {
    JAPANESE("ja", "日本語"),
    ENGLISH("en", "English"),
    CHINESE("zh", "中文"),
    SPANISH("es", "Español"),
    FRENCH("fr", "Français"),
    PORTUGUESE("pt", "Português"),
}
