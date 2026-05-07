package com.piperplus.g2p.sample

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import com.piperplus.g2p.PhonemeResult
import com.piperplus.g2p.PiperPlusG2p
import com.piperplus.g2p.PiperPlusG2pException

/**
 * Minimal Compose UI demoing the piper-plus-g2p-android library:
 *   - Tab bar with the 8 supported language codes.
 *   - TextField for arbitrary input.
 *   - "Phonemize" button → result card with the IPA phoneme string,
 *     resolved language, and token count.
 *
 * Japanese is shown but reports a hint when the OpenJTalk dictionary is
 * absent. The dictionary distribution is documented in
 * `docs/guides/android-g2p-dictionary.md`.
 */
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    SampleApp()
                }
            }
        }
    }
}

private val LANGUAGES = listOf("en", "es", "fr", "ja", "ko", "pt", "sv", "zh")

private val SAMPLE_INPUTS = mapOf(
    "en" to "Hello, world!",
    "es" to "Hola, mundo",
    "fr" to "Bonjour le monde",
    "ja" to "こんにちは",
    "ko" to "안녕하세요",
    "pt" to "Olá mundo",
    "sv" to "Hej världen",
    "zh" to "你好世界",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SampleApp() {
    val context = LocalContext.current

    // Owned by Compose so we can release the native handle when the
    // composition leaves the tree.
    var g2p by remember { mutableStateOf<PiperPlusG2p?>(null) }
    var initError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        try {
            g2p = PiperPlusG2p.create(context)
        } catch (e: Throwable) {
            initError = "init failed: ${e.message}"
        }
    }
    DisposableEffect(g2p) {
        onDispose { g2p?.close() }
    }

    var selectedLang by remember { mutableStateOf(0) }
    var inputText by remember { mutableStateOf(SAMPLE_INPUTS[LANGUAGES[0]] ?: "") }
    var lastResult by remember { mutableStateOf<PhonemeResult?>(null) }
    var lastError by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(title = {
                Text("piper-plus-g2p sample")
            })
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (initError != null) {
                Text(
                    text = initError!!,
                    color = MaterialTheme.colorScheme.error,
                )
            }

            TabRow(selectedTabIndex = selectedLang) {
                LANGUAGES.forEachIndexed { idx, code ->
                    Tab(
                        selected = selectedLang == idx,
                        onClick = {
                            selectedLang = idx
                            inputText = SAMPLE_INPUTS[code] ?: ""
                            lastResult = null
                            lastError = null
                        },
                        text = { Text(code.uppercase()) },
                    )
                }
            }

            TextField(
                value = inputText,
                onValueChange = { inputText = it },
                label = { Text("Input text") },
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None),
                modifier = Modifier.fillMaxWidth(),
            )

            Button(
                onClick = {
                    val instance = g2p
                    if (instance == null) {
                        lastError = "G2P not yet initialised"
                    } else {
                        try {
                            lastResult = instance.phonemize(
                                text = inputText,
                                language = LANGUAGES[selectedLang],
                            )
                            lastError = null
                        } catch (e: PiperPlusG2pException) {
                            lastError = e.message
                            lastResult = null
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = g2p != null,
            ) {
                Text("Phonemize")
            }

            Spacer(Modifier.height(4.dp))

            lastResult?.let { result ->
                ResultCard(result)
            }
            lastError?.let { msg ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text("Error", style = MaterialTheme.typography.titleSmall)
                        Text(msg)
                    }
                }
            }

            Spacer(Modifier.height(8.dp))

            HelperText()
        }
    }
}

@Composable
private fun ResultCard(result: PhonemeResult) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Row(
                label = "Language",
                value = result.language,
            )
            Row(
                label = "Tokens",
                value = result.numPhonemes.toString(),
            )
            Text("Phonemes:", style = MaterialTheme.typography.titleSmall)
            Text(
                text = result.phonemes,
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun Row(label: String, value: String) {
    androidx.compose.foundation.layout.Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.titleSmall)
        Text(value, fontFamily = FontFamily.Monospace)
    }
}

@Composable
private fun HelperText() {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = "Tip: Japanese requires the OpenJTalk dictionary " +
                    "(see docs/guides/android-g2p-dictionary.md). The other " +
                    "seven languages run with no dictionary.",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}
