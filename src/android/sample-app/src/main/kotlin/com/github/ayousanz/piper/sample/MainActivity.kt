package com.github.ayousanz.piper.sample

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            MaterialTheme {
                val viewModel: TtsViewModel = viewModel()

                val playbackState = viewModel.playbackState.collectAsStateWithLifecycle()
                val selectedLanguage = viewModel.selectedLanguage.collectAsStateWithLifecycle()
                val speakerId = viewModel.speakerId.collectAsStateWithLifecycle()
                val noiseScale = viewModel.noiseScale.collectAsStateWithLifecycle()
                val lengthScale = viewModel.lengthScale.collectAsStateWithLifecycle()

                // Auto-initialize with model from assets (if available)
                // For testing, copy model.onnx and config.json to app/src/main/assets/
                androidx.compose.runtime.LaunchedEffect(Unit) {
                    if (playbackState.value is PlaybackState.Uninitialized) {
                        try {
                            val assets = assets.list("") ?: emptyArray()
                            val modelFile = assets.firstOrNull { it.endsWith(".onnx") }
                            if (modelFile != null) {
                                viewModel.initialize(modelFile)
                            }
                        } catch (e: Exception) {
                            viewModel.setError("Failed to load model from assets: ${e.message}")
                        }
                    }
                }

                TtsScreen(
                    playbackState = playbackState.value,
                    selectedLanguage = selectedLanguage.value,
                    speakerId = speakerId.value,
                    noiseScale = noiseScale.value,
                    lengthScale = lengthScale.value,
                    onSpeak = viewModel::speak,
                    onSpeakStreaming = viewModel::speakStreaming,
                    onStop = viewModel::stop,
                    onLanguageChanged = viewModel::setLanguage,
                    onSpeakerIdChanged = viewModel::setSpeakerId,
                    onNoiseScaleChanged = viewModel::setNoiseScale,
                    onLengthScaleChanged = viewModel::setLengthScale,
                )
            }
        }
    }
}
