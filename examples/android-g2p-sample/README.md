# piper-plus-g2p — Android sample app

Minimal Compose application that demonstrates the [`piper-plus-g2p-android`](../../android/piper-plus-g2p/)
library:

- 8 language tabs (`en`, `es`, `fr`, `ja`, `ko`, `pt`, `sv`, `zh`)
- Free-form `TextField` input
- "Phonemize" button → IPA phoneme string + token count + resolved language

## Build

```bash
cd examples/android-g2p-sample
gradle :app:assembleDebug
```

The `settings.gradle.kts` uses a Gradle composite build to consume the
sibling `android/piper-plus-g2p/` module directly. Outside the repository,
delete the `includeBuild(...)` block and rely on the published Maven
Central artifact (`io.github.ayutaz:piper-plus-g2p-android:X.Y.Z`).

## Run

Install the debug APK on a connected device or emulator:

```bash
gradle :app:installDebug
adb shell am start -n com.piperplus.g2p.sample/.MainActivity
```

## Notes on Japanese

The Japanese path (`ja` tab) requires the OpenJTalk dictionary (~102 MB),
which is intentionally not bundled. For a working JA demo bundle the
dictionary under `app/src/main/assets/open_jtalk_dic/` and update
`MainActivity.kt` to pass an `OpenJTalkDictionary.fromAssets(context)`
to `PiperPlusG2p.create(context, dictionary)`. See
[`docs/guides/platform/android-g2p-dictionary.md`](../../docs/guides/platform/android-g2p-dictionary.md)
for the full walkthrough.
