package com.github.ayousanz.piper.sample

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.github.ayousanz.piper.AudioPlayer
import com.github.ayousanz.piper.PiperConfig
import com.github.ayousanz.piper.PiperTts
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.buffer
import kotlinx.coroutines.launch

class TtsViewModel(application: Application) : AndroidViewModel(application) {

    private val _playbackState = MutableStateFlow<PlaybackState>(PlaybackState.Uninitialized)
    val playbackState: StateFlow<PlaybackState> = _playbackState.asStateFlow()

    private val _selectedLanguage = MutableStateFlow(TtsLanguage.JAPANESE)
    val selectedLanguage: StateFlow<TtsLanguage> = _selectedLanguage.asStateFlow()

    private val _speakerId = MutableStateFlow(0)
    val speakerId: StateFlow<Int> = _speakerId.asStateFlow()

    private val _noiseScale = MutableStateFlow(PiperConfig.DEFAULT_NOISE_SCALE)
    val noiseScale: StateFlow<Float> = _noiseScale.asStateFlow()

    private val _lengthScale = MutableStateFlow(PiperConfig.DEFAULT_LENGTH_SCALE)
    val lengthScale: StateFlow<Float> = _lengthScale.asStateFlow()

    private var tts: PiperTts? = null
    private var audioPlayer: AudioPlayer? = null
    private var currentJob: Job? = null

    /**
     * Initialize the TTS engine from assets.
     */
    fun initialize(modelAssetPath: String, configAssetPath: String? = null) {
        if (_playbackState.value != PlaybackState.Uninitialized) return

        viewModelScope.launch {
            _playbackState.value = PlaybackState.Loading
            try {
                val configPath = configAssetPath ?: modelAssetPath.replace(".onnx", ".json")
                val engine = PiperTts.load(
                    getApplication(),
                    assetModelPath = modelAssetPath,
                    assetConfigPath = configPath,
                )
                tts = engine
                audioPlayer = AudioPlayer(engine.sampleRate)
                _playbackState.value = PlaybackState.Idle
            } catch (e: Exception) {
                _playbackState.value = PlaybackState.Error("Failed to load model: ${e.message}")
            }
        }
    }

    /**
     * Initialize from file paths (for models stored on device).
     */
    fun initializeFromPath(modelPath: String, configPath: String) {
        tts?.close()
        audioPlayer?.close()

        viewModelScope.launch {
            _playbackState.value = PlaybackState.Loading
            try {
                val config = PiperConfig(modelPath = modelPath, configPath = configPath)
                val engine = PiperTts.load(config)
                tts = engine
                audioPlayer = AudioPlayer(engine.sampleRate)
                _playbackState.value = PlaybackState.Idle
            } catch (e: Exception) {
                _playbackState.value = PlaybackState.Error("Failed to load model: ${e.message}")
            }
        }
    }

    /**
     * Synthesize and play text.
     */
    fun speak(text: String) {
        val engine = tts ?: return
        val player = audioPlayer ?: return

        // Cancel any ongoing synthesis/playback
        stop()

        currentJob = viewModelScope.launch {
            _playbackState.value = PlaybackState.Synthesizing(text)
            try {
                val audio = engine.synthesize(
                    text = text,
                    language = _selectedLanguage.value.code,
                    speakerId = _speakerId.value,
                )

                _playbackState.value = PlaybackState.Playing(audio.durationSeconds)
                player.play(audio)
                _playbackState.value = PlaybackState.Idle

            } catch (e: CancellationException) {
                _playbackState.value = PlaybackState.Idle
                throw e
            } catch (e: Exception) {
                _playbackState.value = PlaybackState.Error("Synthesis failed: ${e.message}")
            }
        }
    }

    /**
     * Synthesize and play with streaming (lower latency for long text).
     */
    fun speakStreaming(text: String) {
        val engine = tts ?: return
        val player = audioPlayer ?: return

        stop()

        currentJob = viewModelScope.launch {
            _playbackState.value = PlaybackState.Synthesizing(text)
            try {
                val audioFlow = engine.synthesizeStream(
                    text = text,
                    language = _selectedLanguage.value.code,
                    speakerId = _speakerId.value,
                ).buffer(2)

                _playbackState.value = PlaybackState.Playing(0f)
                player.playStream(audioFlow)
                _playbackState.value = PlaybackState.Idle

            } catch (e: CancellationException) {
                _playbackState.value = PlaybackState.Idle
                throw e
            } catch (e: Exception) {
                _playbackState.value = PlaybackState.Error("Streaming failed: ${e.message}")
            }
        }
    }

    /**
     * Stop current synthesis/playback.
     */
    fun stop() {
        try {
            currentJob?.cancel()
            currentJob = null
        } finally {
            audioPlayer?.stop()
        }
        if (_playbackState.value !is PlaybackState.Uninitialized &&
            _playbackState.value !is PlaybackState.Loading) {
            _playbackState.value = PlaybackState.Idle
        }
    }

    /**
     * Save the last synthesized audio to a WAV file.
     */
    fun saveToWav(text: String, outputPath: String) {
        val engine = tts ?: return

        viewModelScope.launch {
            try {
                val audio = engine.synthesize(
                    text = text,
                    language = _selectedLanguage.value.code,
                    speakerId = _speakerId.value,
                )
                audio.save(outputPath)
            } catch (e: Exception) {
                _playbackState.value = PlaybackState.Error("Save failed: ${e.message}")
            }
        }
    }

    fun setLanguage(language: TtsLanguage) { _selectedLanguage.value = language }
    fun setSpeakerId(id: Int) { _speakerId.value = id }
    fun setNoiseScale(value: Float) { _noiseScale.value = value }
    fun setLengthScale(value: Float) { _lengthScale.value = value }
    fun setError(message: String) { _playbackState.value = PlaybackState.Error(message) }

    override fun onCleared() {
        super.onCleared()
        currentJob?.cancel()
        audioPlayer?.close()
        tts?.close()
    }
}
