package com.github.ayousanz.piper.sample

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TtsScreen(
    playbackState: PlaybackState,
    selectedLanguage: TtsLanguage,
    speakerId: Int,
    noiseScale: Float,
    lengthScale: Float,
    onSpeak: (String) -> Unit,
    onSpeakStreaming: (String) -> Unit,
    onStop: () -> Unit,
    onLanguageChanged: (TtsLanguage) -> Unit,
    onSpeakerIdChanged: (Int) -> Unit,
    onNoiseScaleChanged: (Float) -> Unit,
    onLengthScaleChanged: (Float) -> Unit,
) {
    var text by remember { mutableStateOf("") }
    var languageMenuExpanded by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Piper TTS") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                ),
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // Status
            StatusCard(playbackState)

            // Text input
            OutlinedTextField(
                value = text,
                onValueChange = { if (it.length <= 1000) text = it },
                label = { Text("Text to synthesize") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 3,
                maxLines = 6,
            )

            // Language selector
            ExposedDropdownMenuBox(
                expanded = languageMenuExpanded,
                onExpandedChange = { languageMenuExpanded = it },
            ) {
                OutlinedTextField(
                    value = selectedLanguage.displayName,
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Language") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = languageMenuExpanded) },
                    modifier = Modifier.menuAnchor().fillMaxWidth(),
                )
                ExposedDropdownMenu(
                    expanded = languageMenuExpanded,
                    onDismissRequest = { languageMenuExpanded = false },
                ) {
                    TtsLanguage.entries.forEach { lang ->
                        DropdownMenuItem(
                            text = { Text("${lang.displayName} (${lang.code})") },
                            onClick = {
                                onLanguageChanged(lang)
                                languageMenuExpanded = false
                            },
                        )
                    }
                }
            }

            // Speaker ID
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("Speaker ID:", style = MaterialTheme.typography.bodyMedium)
                OutlinedTextField(
                    value = speakerId.toString(),
                    onValueChange = { it.toIntOrNull()?.takeIf { id -> id >= 0 }?.let(onSpeakerIdChanged) },
                    modifier = Modifier.width(80.dp),
                    singleLine = true,
                )
            }

            // Noise Scale slider
            SliderWithLabel(
                label = "Noise Scale",
                value = noiseScale,
                valueRange = 0f..1f,
                onValueChange = onNoiseScaleChanged,
            )

            // Length Scale slider
            SliderWithLabel(
                label = "Length Scale",
                value = lengthScale,
                valueRange = 0.5f..2f,
                onValueChange = onLengthScaleChanged,
            )

            // Action buttons
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                val isReady = playbackState is PlaybackState.Idle && text.isNotBlank()
                val isBusy = playbackState is PlaybackState.Synthesizing ||
                        playbackState is PlaybackState.Playing

                Button(
                    onClick = { onSpeak(text) },
                    enabled = isReady,
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Speak")
                }

                OutlinedButton(
                    onClick = { onSpeakStreaming(text) },
                    enabled = isReady,
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Stream")
                }

                FilledTonalButton(
                    onClick = onStop,
                    enabled = isBusy,
                ) {
                    Text("Stop")
                }
            }
        }
    }
}

@Composable
private fun StatusCard(state: PlaybackState) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = when (state) {
                is PlaybackState.Error -> MaterialTheme.colorScheme.errorContainer
                is PlaybackState.Playing -> MaterialTheme.colorScheme.tertiaryContainer
                is PlaybackState.Synthesizing -> MaterialTheme.colorScheme.secondaryContainer
                else -> MaterialTheme.colorScheme.surfaceVariant
            }
        ),
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            when (state) {
                is PlaybackState.Uninitialized -> Text("Engine not loaded")
                is PlaybackState.Loading -> {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                    Text("Loading model...")
                }
                is PlaybackState.Idle -> Text("Ready")
                is PlaybackState.Synthesizing -> {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                    Text("Synthesizing...")
                }
                is PlaybackState.Playing -> Text("Playing (${String.format("%.1fs", state.durationSeconds)})")
                is PlaybackState.Error -> Text(state.message, color = MaterialTheme.colorScheme.onErrorContainer)
            }
        }
    }
}

@Composable
private fun SliderWithLabel(
    label: String,
    value: Float,
    valueRange: ClosedFloatingPointRange<Float>,
    onValueChange: (Float) -> Unit,
) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(label, style = MaterialTheme.typography.bodyMedium)
            Text(String.format("%.3f", value), style = MaterialTheme.typography.bodySmall)
        }
        Slider(
            value = value,
            onValueChange = onValueChange,
            valueRange = valueRange,
        )
    }
}
