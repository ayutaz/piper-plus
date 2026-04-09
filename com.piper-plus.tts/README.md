# Piper Plus TTS for Unity

Multilingual neural text-to-speech for Unity using the piper-plus engine.
Supports 8 languages (JA, EN, ZH, KO, ES, FR, PT, SV) with MIT license and no eSpeak-ng dependency.

## Requirements

- Unity 2021.3 LTS or later
- Native plugin: `libpiper_plus` shared library for your target platform

## Installation

### Via Git URL (UPM)

1. Open **Window > Package Manager**
2. Click **+** > **Add package from git URL...**
3. Enter: `https://github.com/ayutaz/piper-plus.git?path=com.piper-plus.tts`

### Via Local Folder

1. Clone or download this repository
2. Open **Window > Package Manager**
3. Click **+** > **Add package from disk...**
4. Select `com.piper-plus.tts/package.json`

## Native Plugin Setup

Place the native library for each target platform under `Plugins/`:

| Platform | Library | Path |
|----------|---------|------|
| Windows x64 | `piper_plus.dll` | `Plugins/x86_64/piper_plus.dll` |
| macOS arm64 | `libpiper_plus.dylib` | `Plugins/macOS/libpiper_plus.dylib` |
| Linux x64 | `libpiper_plus.so` | `Plugins/x86_64/libpiper_plus.so` |

Download pre-built binaries from [Releases](https://github.com/ayutaz/piper-plus/releases).

See `Plugins/README.md` for detailed platform configuration instructions.

## Quick Start

```csharp
using PiperPlus;
using UnityEngine;

public class TTSExample : MonoBehaviour
{
    [SerializeField] private PiperModel model;
    [SerializeField] private AudioSource audioSource;

    private PiperTTS tts;

    void Start()
    {
        tts = PiperTTS.Create(model.modelPath, model.configPath);
    }

    void OnDestroy()
    {
        tts?.Dispose();
    }

    public void Speak(string text)
    {
        var clip = tts.Synthesize(text, model.defaultLanguage);
        audioSource.clip = clip;
        audioSource.Play();
    }
}
```

### Async Usage

```csharp
using PiperPlus;
using UnityEngine;

public class AsyncTTSExample : MonoBehaviour
{
    [SerializeField] private PiperModel model;
    [SerializeField] private AudioSource audioSource;

    private PiperTTSAsync tts;

    void Start()
    {
        tts = PiperTTSAsync.Create(model.modelPath, model.configPath);
    }

    void OnDestroy()
    {
        tts?.Dispose();
    }

    public async void Speak(string text)
    {
        var clip = await tts.SynthesizeAsync(text, model.defaultLanguage);
        audioSource.clip = clip;
        audioSource.Play();
    }
}
```

## API Reference

### PiperTTS (Synchronous)

| Method | Description |
|--------|-------------|
| `Create(modelPath, configPath)` | Create a TTS engine instance |
| `Synthesize(text, language)` | Synthesize text to AudioClip |
| `SynthesizeRaw(text, language)` | Synthesize text to float[] PCM samples |
| `SampleRate` | Get model sample rate |
| `NumSpeakers` | Get number of speakers |
| `NumLanguages` | Get number of languages |
| `Dispose()` | Release native resources |

### PiperTTSAsync (Asynchronous)

| Method | Description |
|--------|-------------|
| `Create(modelPath, configPath)` | Create an async TTS engine instance |
| `SynthesizeAsync(text, language, ct)` | Synthesize on worker thread, return AudioClip on main thread |
| `SynthesizeRawAsync(text, language, ct)` | Synthesize on worker thread, return float[] |
| `Dispose()` | Release native resources |

### PiperModel (ScriptableObject)

Create via **Assets > Create > Piper Plus > Model** in the Unity editor.

### AudioClipExtensions

| Method | Description |
|--------|-------------|
| `CreateFromPcm(samples, sampleRate, name)` | Create AudioClip from float[] PCM |

## License

MIT License. See [LICENSE.md](LICENSE.md).
