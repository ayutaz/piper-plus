# Unity Integration Guide

piper-plus provides a Unity Package Manager (UPM) package for integrating multilingual neural text-to-speech into Unity projects. 8 languages (JA, EN, ZH, KO, ES, FR, PT, SV) are supported with MIT license and no eSpeak-ng dependency.

## Requirements

- Unity 2021.3 LTS or later
- Native plugin: `libpiper_plus` shared library for your target platform

## Installation

### UPM (Git URL)

1. Open **Window > Package Manager**
2. Click **+** > **Add package from git URL...**
3. Enter:
   ```
   https://github.com/ayutaz/piper-plus.git?path=com.piper-plus.tts
   ```

### UPM (Local)

1. Clone or download this repository
2. Open **Window > Package Manager**
3. Click **+** > **Add package from disk...**
4. Select `com.piper-plus.tts/package.json`

### Manual Installation

Copy the `com.piper-plus.tts/` directory into your project's `Packages/` folder.

## Quick Start (3 Lines of Code)

```csharp
using PiperPlus;
using UnityEngine;

public class QuickStart : MonoBehaviour
{
    void Start()
    {
        var tts  = PiperTTS.Create("path/to/model.onnx");
        var clip = tts.Synthesize("Hello, world!");
        GetComponent<AudioSource>().PlayOneShot(clip);
    }
}
```

The `PiperTTS.Create()` method accepts an ONNX model path and optionally a config JSON path (auto-resolved to `model_path + ".json"` if omitted).

## Model Setup

### File Placement

Place model files under `Assets/StreamingAssets/piper-plus/`:

```
Assets/
  StreamingAssets/
    piper-plus/
      model.onnx          # ONNX model file
      model.onnx.json     # Config JSON (auto-detected if named model_path + ".json")
      custom-dict.json     # Optional custom dictionary
```

### PiperModel ScriptableObject

For Inspector-friendly configuration, create a PiperModel asset:

1. Right-click in the Project window
2. **Create > Piper Plus > Model**
3. Set the model path (relative to StreamingAssets or absolute)
4. Choose the default language and speaker ID

```csharp
[SerializeField] private PiperModel model;

void Start()
{
    var tts = PiperTTS.Create(model);
}
```

### Platform-Specific Path Notes

| Platform | StreamingAssets behavior |
|----------|------------------------|
| Windows / macOS / Linux | Direct file system access via `Application.streamingAssetsPath` |
| Android | Files are packed inside the APK. Use `UnityWebRequest` to copy to `Application.persistentDataPath` first |
| iOS | Direct file system access via `Application.streamingAssetsPath` |

Android example:

```csharp
using UnityEngine.Networking;

async Task<string> ExtractModelAsync(string fileName)
{
    string src = System.IO.Path.Combine(Application.streamingAssetsPath, fileName);
    string dst = System.IO.Path.Combine(Application.persistentDataPath, fileName);

    if (System.IO.File.Exists(dst))
        return dst;

    var request = UnityWebRequest.Get(src);
    request.SendWebRequest();

    while (!request.isDone)
        await Task.Yield();

    if (request.result == UnityWebRequest.Result.Success)
    {
        System.IO.File.WriteAllBytes(dst, request.downloadHandler.data);
        return dst;
    }

    throw new System.Exception($"Failed to extract {fileName}: {request.error}");
}
```

## Basic Usage

### Synchronous Synthesis

`PiperTTS` performs synthesis on the calling thread. Suitable for short texts where blocking is acceptable.

```csharp
using PiperPlus;
using UnityEngine;

public class SyncExample : MonoBehaviour
{
    [SerializeField] private PiperModel model;

    private PiperTTS _tts;
    private AudioSource _audioSource;

    void Start()
    {
        _audioSource = GetComponent<AudioSource>();
        _tts = PiperTTS.Create(model);
    }

    void OnDestroy()
    {
        _tts?.Dispose();
    }

    public void Speak(string text)
    {
        var clip = _tts.Synthesize(text, "ja");
        _audioSource.PlayOneShot(clip);
    }
}
```

### Asynchronous Synthesis

`PiperTTSAsync` runs synthesis on a worker thread so the main thread stays responsive. AudioClip creation is automatically marshalled back to the main thread.

```csharp
using System.Threading;
using PiperPlus;
using UnityEngine;

public class AsyncExample : MonoBehaviour
{
    [SerializeField] private PiperModel model;

    private PiperTTSAsync _tts;
    private AudioSource _audioSource;
    private CancellationTokenSource _cts;

    void Start()
    {
        _audioSource = GetComponent<AudioSource>();
        _tts = PiperTTSAsync.Create(model);  // Must be called on the main thread
    }

    void OnDestroy()
    {
        _cts?.Cancel();
        _cts?.Dispose();
        _tts?.Dispose();
    }

    public async void Speak(string text)
    {
        _cts?.Cancel();
        _cts = new CancellationTokenSource();

        try
        {
            var clip = await _tts.SynthesizeAsync(text, "ja", null, _cts.Token);
            if (clip != null)
            {
                _audioSource.clip = clip;
                _audioSource.Play();
            }
        }
        catch (System.OperationCanceledException)
        {
            // Request was cancelled
        }
    }
}
```

### Streaming Synthesis

For longer texts, split into sentences and synthesize each one sequentially. Prefetch the next sentence while the current one plays for smooth playback.

```csharp
public async void SpeakStreaming(string[] sentences)
{
    Task<AudioClip> nextClip = _tts.SynthesizeAsync(sentences[0], "ja");

    for (int i = 0; i < sentences.Length; i++)
    {
        var clip = await nextClip;

        // Prefetch next
        if (i + 1 < sentences.Length)
            nextClip = _tts.SynthesizeAsync(sentences[i + 1], "ja");

        _audioSource.clip = clip;
        _audioSource.Play();

        // Wait for playback
        while (_audioSource.isPlaying)
            await Task.Yield();
    }
}
```

See `StreamingTTSDemo.cs` in the samples for a complete implementation with cancellation support.

## Multilingual Support

### Language Parameter

Pass a language code as the second argument to `Synthesize()` or `SynthesizeAsync()`:

```csharp
// Explicit language
var clip = tts.Synthesize("Hello", "en");
var clip = tts.Synthesize("Bonjour", "fr");

// Auto-detect (pass null)
var clip = tts.Synthesize("Hello", null);
```

### Querying Available Languages

```csharp
// Comma-separated list of language codes
string langs = tts.AvailableLanguages;  // e.g., "ja,en,zh,es,fr,pt"

// Total number of languages
int count = tts.NumLanguages;

// Resolve code to numeric ID
int jaId = tts.GetLanguageId("ja");  // e.g., 0
```

### PiperConfig for Fine-Grained Control

```csharp
var config = new PiperConfig
{
    speakerId   = 0,
    languageId  = tts.GetLanguageId("en"),
    noiseScale  = 0.667f,
    lengthScale = 1.0f,
    noiseW      = 0.8f,
    sentenceSilence = 0.3f,
};

var clip = tts.Synthesize("Hello", null, config);
```

## Custom Dictionary

Load a JSON dictionary file to override pronunciations:

```csharp
tts.LoadCustomDict("path/to/custom-dict.json");

// Later, to remove custom entries:
tts.ClearCustomDict();
```

The dictionary format is compatible with the Rust/C++/C# CLI tools. See the project documentation for the JSON schema.

## Performance Optimization

### Pre-Load the Model

Create the engine during a loading screen or `Awake()`, not during gameplay:

```csharp
void Awake()
{
    _tts = PiperTTS.Create(model);  // ~200-500ms depending on model size
}
```

### Reuse AudioClips

Avoid creating a new AudioClip for every short phrase. For repeated phrases (e.g., UI sounds), cache the result:

```csharp
private readonly Dictionary<string, AudioClip> _clipCache = new Dictionary<string, AudioClip>();

public AudioClip GetOrSynthesize(string text, string language)
{
    string key = $"{language}:{text}";
    if (!_clipCache.TryGetValue(key, out var clip))
    {
        clip = _tts.Synthesize(text, language);
        _clipCache[key] = clip;
    }
    return clip;
}
```

### Use Worker Threads

Always use `PiperTTSAsync` for gameplay scenarios. Synchronous synthesis blocks the main thread for 50-200ms per sentence, which causes frame drops.

### Raw PCM for Advanced Pipelines

If you are feeding audio into a custom pipeline (e.g., AudioSource.OnAudioRead), use `SynthesizeRaw()` to skip AudioClip creation:

```csharp
int sampleRate;
float[] samples = tts.SynthesizeRaw(text, "ja", null, out sampleRate);
```

## Platform-Specific Notes

### Windows / macOS / Linux

- Place `piper_plus.dll` / `libpiper_plus.dylib` / `libpiper_plus.so` in the `Plugins/` folder with correct platform settings
- Download pre-built binaries from [Releases](https://github.com/ayutaz/piper-plus/releases)

### Android

- Build `libpiper_plus.so` for `arm64-v8a` (and optionally `armeabi-v7a`)
- Place under `Plugins/Android/arm64-v8a/` with platform import settings
- StreamingAssets files require extraction:

```csharp
// Extract model from APK on first launch
string modelPath = await ExtractModelAsync("piper-plus/model.onnx");
string configPath = await ExtractModelAsync("piper-plus/model.onnx.json");
var tts = PiperTTS.Create(modelPath, configPath);
```

### iOS

- Build `libpiper_plus.a` as a static library (iOS does not allow dynamic libraries)
- The P/Invoke declaration automatically uses `__Internal` for iOS builds
- StreamingAssets are accessible directly via `Application.streamingAssetsPath`

## Native Plugin Setup

Place the native library under `com.piper-plus.tts/Plugins/` or your project's `Assets/Plugins/`:

| Platform | File | Plugins Path |
|----------|------|-------------|
| Windows x64 | `piper_plus.dll` | `Plugins/x86_64/piper_plus.dll` |
| macOS arm64 | `libpiper_plus.dylib` | `Plugins/macOS/libpiper_plus.dylib` |
| macOS x64 | `libpiper_plus.dylib` | `Plugins/macOS/libpiper_plus.dylib` |
| Linux x64 | `libpiper_plus.so` | `Plugins/x86_64/libpiper_plus.so` |
| Android arm64 | `libpiper_plus.so` | `Plugins/Android/arm64-v8a/libpiper_plus.so` |
| iOS | `libpiper_plus.a` | `Plugins/iOS/libpiper_plus.a` |

## Samples

Import samples via **Window > Package Manager > Piper Plus TTS > Samples**:

| Sample | Description |
|--------|-------------|
| **BasicTTSDemo** | Minimal 3-line synthesis example |
| **AsyncTTSDemo** | Non-blocking synthesis with loading indicator and cancellation |
| **StreamingTTSDemo** | Sentence-by-sentence streaming with prefetch |
| **NPCDialogDemo** | NPC dialog system with subtitles and auto-advance |
| **LanguageSwitchDemo** | Runtime language switching with dropdown |

## Troubleshooting

### DllNotFoundException

**Symptom:** `DllNotFoundException: piper_plus`

**Causes and fixes:**
1. Native library not placed in the correct `Plugins/` directory -- check platform/architecture
2. Library architecture mismatch (e.g., x86 library on arm64 macOS) -- use the correct build
3. Missing runtime dependencies (e.g., ONNX Runtime) -- ensure all `.dll`/`.dylib`/`.so` dependencies are included

### Audio Not Playing

**Symptom:** `Synthesize()` returns a clip but no sound is heard

**Fixes:**
1. Ensure an `AudioSource` component is attached and enabled
2. Check `AudioSource.volume` and `AudioListener` presence in the scene
3. Verify the clip is not empty: `Debug.Log(clip.length)` should be > 0
4. For `PlayOneShot`, the AudioSource must not be muted

### Memory Leak

**Symptom:** Memory usage grows over time

**Fixes:**
1. Always call `Dispose()` on `PiperTTS` / `PiperTTSAsync` in `OnDestroy()`
2. Destroy old AudioClips when they are no longer needed: `Destroy(oldClip)`
3. If caching clips, limit the cache size and evict old entries

### Synthesis Returns Null

**Symptom:** `Synthesize()` returns `null`

**Fixes:**
1. Check the input text is not empty or whitespace-only
2. Verify the model file exists at the resolved path
3. Check the Unity Console for `[PiperPlus]` error messages
4. Ensure the config JSON matches the ONNX model (same training run)

### Android: Model File Not Found

**Symptom:** Works in the Editor but fails on Android

**Fix:** StreamingAssets are packed inside the APK on Android and cannot be accessed via normal file I/O. Extract them using `UnityWebRequest` to `Application.persistentDataPath` first. See the Android section above.

### iOS: Crash on Startup

**Symptom:** App crashes immediately on iOS

**Fixes:**
1. Ensure you are using a static library (`.a`), not a dynamic library
2. Check that the library is built for the correct architecture (arm64)
3. The `__Internal` P/Invoke name is used automatically for iOS builds
