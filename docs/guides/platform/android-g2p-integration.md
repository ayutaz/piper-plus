# piper-plus-g2p (Android) — Integration Guide

This guide walks Android app developers through integrating
`piper-plus-g2p-android` — the engine-less, espeak-ng-free multilingual
G2P (text → IPA phoneme) library — into a Gradle / Kotlin project.

The library handles **8 languages** (`ja`, `en`, `zh`, `ko`, `es`, `fr`,
`pt`, `sv`) and works without an ONNX model. Only the Japanese path
additionally needs an OpenJTalk dictionary; see
[android-g2p-dictionary.md](android-g2p-dictionary.md) for distribution
options.

---

## 1. Add the dependency

```kotlin
// app/build.gradle.kts
android {
    defaultConfig {
        minSdk = 24            // matches the AAR's published minSdk
    }
    // 16 KB page size compatibility (Android 15+).
    // The AAR is already 16 KB-aligned; this just ensures consuming apps
    // do not regress when bundling additional .so files.
    packaging {
        jniLibs {
            useLegacyPackaging = false
        }
    }
}

dependencies {
    implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")
}
```

The artifact ships native binaries for `arm64-v8a`, `armeabi-v7a`, and
`x86_64`, so it runs on phones, tablets, and emulators alike.

---

## 2. Initialise the engine

```kotlin
import com.piperplus.g2p.PiperPlusG2p

class MyViewModel(application: Application) : AndroidViewModel(application) {

    private val g2p = PiperPlusG2p.create(application)

    override fun onCleared() {
        g2p.close()  // release the native handle
        super.onCleared()
    }

    fun describe(text: String, language: String): String {
        val result = g2p.phonemize(text, language)
        return "[${result.language}] ${result.numPhonemes} tokens: ${result.phonemes}"
    }
}
```

`PiperPlusG2p` implements `AutoCloseable`, so a `use { … }` block is also
fine for short-lived workflows:

```kotlin
PiperPlusG2p.create(context).use { g2p ->
    val r = g2p.phonemize("Hello, world!", "en")
}
```

After `close()` any further call throws `IllegalStateException`.

---

## 3. Language-specific notes

| Code | Language | Notes |
|------|----------|-------|
| `en` | English  | g2p-en built-in. Always available. |
| `es` | Spanish  | Rule-based. No dependencies. |
| `fr` | French   | Rule-based. No dependencies. |
| `pt` | Portuguese | Rule-based. Variants: BR / PT. |
| `sv` | Swedish  | Rule-based. |
| `zh` | Chinese  | pypinyin port; ZH-EN code-switching enabled by default. |
| `ko` | Korean   | g2pk2 port; works without external Korean tooling. |
| `ja` | Japanese | **Requires OpenJTalk dictionary (~102 MB).** See dictionary guide. |

`g2p.phonemize(text, language = null)` enables Unicode-script auto-detect.
Passing an explicit `language` overrides the detector and pins the latin
fallback (e.g. `language="es"` makes `"Hola"` route through Spanish G2P
instead of falling back to English).

---

## 4. Custom dictionaries

Override individual word pronunciations at runtime via JSON:

```kotlin
g2p.loadCustomDict("/path/to/custom_dict.json")
val r = g2p.phonemize("My company is GitHub", "en")
```

JSON v1.0 (single-language map) and v2.0 (multi-language map keyed by
language code) are both supported. The format mirrors the upstream
`piper_plus_g2p` Python package.

---

## 5. ZH-EN code-switching

The library ships with the Issue #384 ZH-EN loanword dictionary
(acronyms like `GPS`, `CPU`, plus 40 common loanwords) so an English
token sandwiched between Chinese segments is rendered in Mandarin pinyin.

Disable per-instance if you need pure-English pronunciation of the
embedded segment:

```kotlin
g2p.setZhEnDispatchEnabled(false)
g2p.phonemize("我用 GPS 导航", "zh")
```

---

## 6. Threading

Each `PiperPlusG2p` instance is **single-threaded**. The public methods
are guarded with `@Synchronized` to defend against accidental misuse,
but you should still treat one instance as if it were owned by a single
worker. For parallel pipelines instantiate multiple `PiperPlusG2p`
objects and assign one per worker.

---

## 7. Sample app

A complete Compose-based sample app lives at
[`examples/android-g2p-sample/`](../../../examples/android-g2p-sample/).
It demonstrates language tabs, custom-dictionary loading, and lifecycle
management. Clone the repo and run:

```bash
cd examples/android-g2p-sample
gradle :app:assembleDebug
```

The sample uses a Gradle composite build to consume the in-repo AAR
without waiting on Maven Central.

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `UnsatisfiedLinkError: libpiper_plus_g2p_jni.so` | Wrong ABI / 16 KB page size | Confirm ABI filters include the device's architecture. |
| `PiperPlusG2pException: dict_dir not found` (ja path) | OpenJTalk dictionary missing | Follow [android-g2p-dictionary.md](android-g2p-dictionary.md). |
| Empty phoneme list for non-empty input | Wrong language code | Pass an explicit `language=` or use `null` for auto-detect. |
| `IllegalStateException: PiperPlusG2p has been closed` | Reused instance after `close()` | Create a new instance via `PiperPlusG2p.create(context)`. |
| `IllegalArgumentException: host not in DictionaryDownloader.ALLOWED_HOSTS` | Custom HF mirror not in allowlist | Stick to `huggingface.co` / `hf-mirror.com` or open a PR adding the mirror. |

---

## 9. Where to file feedback

- **Bugs / questions**: open an issue at
  <https://github.com/ayutaz/piper-plus/issues> with the `kotlin-g2p` label.
- **Security findings**: please follow the SECURITY.md disclosure path
  rather than the public tracker.
