# piper-plus-g2p (Android)

Multilingual Grapheme-to-Phoneme (G2P) library for Android — engine-less,
espeak-ng-free, MIT licensed. Supports 8 languages: `ja`, `en`, `zh`, `ko`,
`es`, `fr`, `pt`, `sv`.

> Coordinates: `io.github.ayutaz:piper-plus-g2p-android`
> Sources: [`android/piper-plus-g2p/`](.) ([Issue #388](https://github.com/ayutaz/piper-plus/issues/388))

---

## Quick start (3 steps)

### 1. Add the dependency

```kotlin
// settings.gradle.kts
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

// app/build.gradle.kts
dependencies {
    implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")
}
```

### 2. Phonemize text

```kotlin
import com.piperplus.g2p.PiperPlusG2p

PiperPlusG2p.create(context).use { g2p ->
    val result = g2p.phonemize("Hello, world!", "en")
    println(result.phonemes)        // "h ə l ˈoʊ , w ˈɝ l d !"
    println(result.phonemeList)     // [h, ə, l, ˈoʊ, ,, w, ˈɝ, l, d, !]
    println(result.numPhonemes)     // 10
    println(result.language)        // "en"
}
```

### 3. (Optional) Enable Japanese

Japanese requires the OpenJTalk dictionary (~102 MB). Bundle it as an asset
or fetch it at runtime from Hugging Face Hub:

```kotlin
// Option A: bundled in `assets/open_jtalk_dic/` (see Dictionary guide)
val dict = OpenJTalkDictionary.fromAssets(context)
PiperPlusG2p.create(context, dict).use { g2p ->
    g2p.phonemize("こんにちは", "ja")
}

// Option B: download once at runtime
val dict = DictionaryDownloader.downloadFromHuggingFace(context)
```

> See [Dictionary distribution guide](../../docs/guides/platform/android-g2p-dictionary.md)
> for the full walkthrough.

---

## API surface

| Class / Function | Purpose |
|------------------|---------|
| `PiperPlusG2p.create(context, dictionary?)` | Factory; returns an `AutoCloseable`. |
| `PiperPlusG2p.phonemize(text, language?)`   | Convert text → `PhonemeResult`. |
| `PiperPlusG2p.availableLanguages()`         | List of 8 supported codes. |
| `PiperPlusG2p.loadCustomDict(path)`         | Load a JSON v1.0 / v2.0 custom dictionary. |
| `PiperPlusG2p.setZhEnDispatchEnabled(bool)` | Toggle ZH-EN code-switching (Issue #384). |
| `data class PhonemeResult`                  | `phonemes` / `phonemeList` / `language` / `numPhonemes`. |
| `class PiperPlusG2pException`               | Thrown on native error. Subclass of `RuntimeException`. |
| `class OpenJTalkDictionary`                 | Handle to an extracted OpenJTalk dictionary directory. |
| `object DictionaryDownloader`               | `suspend` helper that fetches the dictionary from Hugging Face Hub. |

---

## Supported languages

| Code | Language       | Dictionary needed? | Notes |
|------|----------------|--------------------|-------|
| `ja` | Japanese       | Yes (OpenJTalk)    | See dictionary guide. |
| `en` | English        | No                 | g2p-en data embedded in `.so`. |
| `zh` | Mandarin       | No                 | pypinyin data embedded; ZH-EN code-switching enabled by default. |
| `ko` | Korean         | No                 | g2pk2 data embedded. |
| `es` | Spanish        | No                 | Rule-based. |
| `fr` | French         | No                 | Rule-based. |
| `pt` | Portuguese     | No                 | Rule-based. |
| `sv` | Swedish        | No                 | Rule-based. |

`PhonemeResult.phonemes` is a space-separated UTF-8 string of IPA tokens.
Some tokens are mapped into the Unicode Private Use Area (U+E020..U+E04A
for Chinese tones, U+E016..U+E01C for Japanese question / `N` markers). See
[`docs/spec/pua-contract.toml`](../../docs/spec/pua-contract.toml).

---

## Threading & lifecycle

Each `PiperPlusG2p` instance is **single-threaded**. Public methods are
guarded with `@Synchronized` for safety, but you should still treat the
instance as if it were owned by one thread. Use multiple instances for
parallelism.

Always close the instance:

```kotlin
PiperPlusG2p.create(context).use { g2p -> /* ... */ }
// or
val g2p = PiperPlusG2p.create(context)
try { /* ... */ } finally { g2p.close() }
```

After `close()` further calls throw `IllegalStateException`. The native
handle is freed via `piper_plus_g2p_free()`.

---

## ABIs and minimum SDK

- `arm64-v8a` (production)
- `armeabi-v7a` (legacy phones)
- `x86_64` (emulators / Chromebooks)

| Property | Value |
|----------|-------|
| `minSdk` | 24 (Android 7.0) |
| `compileSdk` | 35 |
| Kotlin | 2.1.0+ |
| Java | 17 |
| 16 KB page size (Android 15+) | All `.so` linked with `-Wl,-z,max-page-size=16384`. |

The AAR ships `libpiper_plus.so` and `libpiper_plus_g2p_jni.so` for the
above ABIs. AAR size (excluding the OpenJTalk dictionary) is **< 10 MB**.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|--------|------------|-----|
| `UnsatisfiedLinkError: libpiper_plus.so` | The consumer app stripped JNI libs. | Disable shrinking for `lib/<abi>/` or switch to a non-stripped flavor. |
| `phonemize("こんにちは", "ja")` returns empty | OpenJTalk dictionary not loaded. | Pass an `OpenJTalkDictionary` to `create()`. |
| Empty phoneme list for `en` | CMU dict not found in `dict_dir`. | Embedded data still works — verify the input is non-empty. |
| Crash on Android 15 emulator | 16 KB page size mismatch. | Re-install (CI gates this — should not occur in shipping builds). |

---

## License

MIT — see [LICENSE.md](../../LICENSE.md). The OpenJTalk dictionary
distributed separately is Modified BSD (naist-jdic).

---

## Related docs

- [Requirements](../../docs/reference/kotlin-g2p-requirements.md)
- [Design](../../docs/reference/kotlin-g2p-design.md)
- [Dictionary distribution guide](../../docs/guides/platform/android-g2p-dictionary.md)
- [Issue #388](https://github.com/ayutaz/piper-plus/issues/388)
