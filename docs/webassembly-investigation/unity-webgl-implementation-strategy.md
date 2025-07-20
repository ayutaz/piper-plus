# Unity WebGL向けPiper-WASM実装方針

## アーキテクチャ概要

```
[Unity C#] 
    ↓ (P/Invoke)
[WebGL Native Plugin (.jslib)]
    ↓ (JavaScript)
[piper-wasm.js]
    ↓ (WebAssembly)
[piper-openjtalk.wasm]
```

## Phase 1: Unity WebGLプラグイン基盤（1週間）

### ディレクトリ構成
```
uPiper/
├── Assets/
│   └── Plugins/
│       ├── WebGL/
│       │   ├── PiperWebGL.jslib      # Unity-JS ブリッジ
│       │   ├── piper-wasm.js         # Piperコア
│       │   └── piper-openjtalk.wasm  # OpenJTalk
│       └── PiperWebGL.cs              # C# API
```

### WebGLプラグイン実装（.jslib）

```javascript
// Assets/Plugins/WebGL/PiperWebGL.jslib
var PiperWebGLPlugin = {
    $PiperWASM: {
        instance: null,
        audioContext: null,
        initialized: false,
        callbacks: {},
        
        initialize: async function() {
            if (this.initialized) return;
            
            // AudioContext初期化
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            
            // Piper-WASM初期化
            const { PiperTTS } = await import('./piper-wasm.js');
            this.instance = new PiperTTS();
            await this.instance.initialize({
                wasmPath: './piper-openjtalk.wasm',
                dictPath: './dict-minimal/'
            });
            
            this.initialized = true;
        }
    },
    
    PiperWebGL_Initialize: async function(callbackPtr) {
        try {
            await PiperWASM.initialize();
            Module.dynCall_vi(callbackPtr, 1); // Success
        } catch (error) {
            console.error('PiperWebGL initialization failed:', error);
            Module.dynCall_vi(callbackPtr, 0); // Failure
        }
    },
    
    PiperWebGL_Synthesize: async function(textPtr, callbackPtr) {
        const text = UTF8ToString(textPtr);
        
        try {
            // テキスト→音素変換
            const phonemes = await PiperWASM.instance.textToPhonemes(text);
            
            // 音素→音声合成
            const audioData = await PiperWASM.instance.synthesize(phonemes);
            
            // Float32Array → Unity用バッファ
            const bufferPtr = _malloc(audioData.length * 4);
            HEAPF32.set(audioData, bufferPtr >> 2);
            
            // コールバック（ポインタ、長さ）
            Module.dynCall_vii(callbackPtr, bufferPtr, audioData.length);
            
        } catch (error) {
            console.error('Synthesis failed:', error);
            Module.dynCall_vii(callbackPtr, 0, 0);
        }
    },
    
    PiperWebGL_LoadModel: async function(modelPathPtr, callbackPtr) {
        const modelPath = UTF8ToString(modelPathPtr);
        
        try {
            await PiperWASM.instance.loadModel(modelPath);
            Module.dynCall_vi(callbackPtr, 1); // Success
        } catch (error) {
            console.error('Model loading failed:', error);
            Module.dynCall_vi(callbackPtr, 0); // Failure
        }
    },
    
    PiperWebGL_SetSpeaker: function(speakerId) {
        if (PiperWASM.instance) {
            PiperWASM.instance.setSpeaker(speakerId);
        }
    },
    
    PiperWebGL_Free: function(ptr) {
        _free(ptr);
    }
};

autoAddDeps(PiperWebGLPlugin, '$PiperWASM');
mergeInto(LibraryManager.library, PiperWebGLPlugin);
```

### C# API実装

```csharp
// Assets/Plugins/PiperWebGL.cs
using System;
using System.Runtime.InteropServices;
using UnityEngine;
using AOT;

#if UNITY_WEBGL && !UNITY_EDITOR
public class PiperWebGL : MonoBehaviour
{
    // コールバックデリゲート
    private delegate void InitializeCallback(int success);
    private delegate void SynthesizeCallback(IntPtr audioPtr, int length);
    private delegate void LoadModelCallback(int success);
    
    // JavaScript関数のインポート
    [DllImport("__Internal")]
    private static extern void PiperWebGL_Initialize(InitializeCallback callback);
    
    [DllImport("__Internal")]
    private static extern void PiperWebGL_Synthesize(string text, SynthesizeCallback callback);
    
    [DllImport("__Internal")]
    private static extern void PiperWebGL_LoadModel(string modelPath, LoadModelCallback callback);
    
    [DllImport("__Internal")]
    private static extern void PiperWebGL_SetSpeaker(int speakerId);
    
    [DllImport("__Internal")]
    private static extern void PiperWebGL_Free(IntPtr ptr);
    
    // Unity Events
    public event Action<bool> OnInitialized;
    public event Action<float[]> OnSynthesized;
    public event Action<bool> OnModelLoaded;
    
    private static PiperWebGL instance;
    
    void Awake()
    {
        if (instance == null)
        {
            instance = this;
            DontDestroyOnLoad(gameObject);
        }
        else
        {
            Destroy(gameObject);
        }
    }
    
    public void Initialize()
    {
        PiperWebGL_Initialize(OnInitializeCallback);
    }
    
    [MonoPInvokeCallback(typeof(InitializeCallback))]
    private static void OnInitializeCallback(int success)
    {
        instance?.OnInitialized?.Invoke(success == 1);
    }
    
    public void Synthesize(string text)
    {
        if (string.IsNullOrEmpty(text)) return;
        PiperWebGL_Synthesize(text, OnSynthesizeCallback);
    }
    
    [MonoPInvokeCallback(typeof(SynthesizeCallback))]
    private static void OnSynthesizeCallback(IntPtr audioPtr, int length)
    {
        if (audioPtr == IntPtr.Zero || length == 0)
        {
            instance?.OnSynthesized?.Invoke(null);
            return;
        }
        
        // ネイティブメモリからFloat配列にコピー
        float[] audioData = new float[length];
        Marshal.Copy(audioPtr, audioData, 0, length);
        
        // メモリ解放
        PiperWebGL_Free(audioPtr);
        
        instance?.OnSynthesized?.Invoke(audioData);
    }
    
    public void LoadModel(string modelPath)
    {
        PiperWebGL_LoadModel(modelPath, OnLoadModelCallback);
    }
    
    [MonoPInvokeCallback(typeof(LoadModelCallback))]
    private static void OnLoadModelCallback(int success)
    {
        instance?.OnModelLoaded?.Invoke(success == 1);
    }
    
    public void SetSpeaker(int speakerId)
    {
        PiperWebGL_SetSpeaker(speakerId);
    }
}
#endif
```

## Phase 2: Unity統合とAudio再生（1週間）

### AudioSource統合

```csharp
// Assets/Scripts/PiperAudioPlayer.cs
using UnityEngine;
using System.Collections;

public class PiperAudioPlayer : MonoBehaviour
{
    private AudioSource audioSource;
    private PiperWebGL piper;
    
    void Start()
    {
        audioSource = GetComponent<AudioSource>();
        if (audioSource == null)
        {
            audioSource = gameObject.AddComponent<AudioSource>();
        }
        
        #if UNITY_WEBGL && !UNITY_EDITOR
        piper = FindObjectOfType<PiperWebGL>();
        if (piper == null)
        {
            GameObject piperObj = new GameObject("PiperWebGL");
            piper = piperObj.AddComponent<PiperWebGL>();
        }
        
        piper.OnInitialized += OnPiperInitialized;
        piper.OnSynthesized += OnAudioSynthesized;
        piper.OnModelLoaded += OnModelLoaded;
        
        // 初期化
        StartCoroutine(InitializePiper());
        #endif
    }
    
    IEnumerator InitializePiper()
    {
        yield return new WaitForSeconds(0.5f); // WebGL準備待ち
        piper.Initialize();
    }
    
    void OnPiperInitialized(bool success)
    {
        if (success)
        {
            Debug.Log("Piper-WASM initialized successfully");
            // モデルロード
            piper.LoadModel("StreamingAssets/models/ja-model.onnx");
        }
        else
        {
            Debug.LogError("Failed to initialize Piper-WASM");
        }
    }
    
    void OnModelLoaded(bool success)
    {
        if (success)
        {
            Debug.Log("Model loaded successfully");
        }
    }
    
    void OnAudioSynthesized(float[] audioData)
    {
        if (audioData == null || audioData.Length == 0)
        {
            Debug.LogError("Audio synthesis failed");
            return;
        }
        
        // AudioClip作成
        int sampleRate = 22050; // Piperのデフォルト
        AudioClip clip = AudioClip.Create("TTS", audioData.Length, 1, sampleRate, false);
        clip.SetData(audioData, 0);
        
        // 再生
        audioSource.clip = clip;
        audioSource.Play();
    }
    
    public void Speak(string text)
    {
        #if UNITY_WEBGL && !UNITY_EDITOR
        piper.Synthesize(text);
        #else
        Debug.LogWarning("Piper-WASM is only available in WebGL builds");
        #endif
    }
}
```

### Unity WebGLビルド設定

```csharp
// Assets/Editor/WebGLBuildProcessor.cs
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using System.IO;

public class WebGLBuildProcessor : IPreprocessBuildWithReport, IPostprocessBuildWithReport
{
    public int callbackOrder => 0;
    
    public void OnPreprocessBuild(BuildReport report)
    {
        if (report.summary.platform == BuildTarget.WebGL)
        {
            // Player設定の最適化
            PlayerSettings.WebGL.memorySize = 512; // メモリサイズ
            PlayerSettings.WebGL.exceptionSupport = WebGLExceptionSupport.FullWithStacktrace;
            PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Gzip;
            
            // WebAssembly 2023有効化
            PlayerSettings.WebGL.emscriptenArgs = "-s WASM=1 -s ALLOW_MEMORY_GROWTH=1";
        }
    }
    
    public void OnPostprocessBuild(BuildReport report)
    {
        if (report.summary.platform == BuildTarget.WebGL)
        {
            string outputPath = report.summary.outputPath;
            string buildDir = Path.GetDirectoryName(outputPath);
            
            // Piper-WASMファイルをコピー
            CopyPiperFiles(buildDir);
            
            // index.htmlを修正
            ModifyIndexHtml(Path.Combine(buildDir, "index.html"));
        }
    }
    
    void CopyPiperFiles(string buildDir)
    {
        // WASMファイルとJSファイルをコピー
        string[] files = {
            "piper-wasm.js",
            "piper-openjtalk.wasm",
            "dict-minimal.data"
        };
        
        foreach (var file in files)
        {
            string src = Path.Combine(Application.dataPath, "Plugins/WebGL", file);
            string dst = Path.Combine(buildDir, file);
            if (File.Exists(src))
            {
                File.Copy(src, dst, true);
            }
        }
    }
    
    void ModifyIndexHtml(string htmlPath)
    {
        if (!File.Exists(htmlPath)) return;
        
        string html = File.ReadAllText(htmlPath);
        
        // Piper-WASM読み込みスクリプト追加
        string piperScript = @"
    <script type='module'>
        // Piper-WASMの事前ロード
        window.piperWasmReady = import('./piper-wasm.js').then(module => {
            window.PiperWASM = module;
            console.log('Piper-WASM module loaded');
        });
    </script>";
        
        // </head>の前に挿入
        html = html.Replace("</head>", piperScript + "\n</head>");
        
        File.WriteAllText(htmlPath, html);
    }
}
```

## メモリとパフォーマンス最適化

### StreamingAssets配置
```
Assets/
└── StreamingAssets/
    ├── models/
    │   └── ja-model.onnx        # 音響モデル
    └── dict/
        ├── dict-minimal.data    # 最小辞書
        └── dict-manifest.json   # 辞書マニフェスト
```

### 非同期ロードとキャッシュ
```javascript
// 辞書の段階的ロード
PiperWASM.loadDictionary = async function(level = 'minimal') {
    const cached = await caches.open('piper-dict-v1');
    const manifest = await fetch('./StreamingAssets/dict/dict-manifest.json')
        .then(r => r.json());
    
    for (const file of manifest[level]) {
        const cachedResponse = await cached.match(file);
        if (!cachedResponse) {
            const response = await fetch(`./StreamingAssets/dict/${file}`);
            await cached.put(file, response.clone());
        }
    }
};
```

## デプロイメント設定

### Unity WebGLテンプレート
```html
<!-- Assets/WebGLTemplates/PiperTTS/index.html -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Unity WebGL with Piper-TTS</title>
    <style>
        #unity-container { width: 100%; height: 100%; }
        #loading-overlay {
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.8);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: Arial, sans-serif;
        }
    </style>
</head>
<body>
    <div id="unity-container"></div>
    <div id="loading-overlay">
        <div>
            <h2>Loading Piper-TTS...</h2>
            <progress id="loading-progress" max="100" value="0"></progress>
            <p id="loading-status">Initializing...</p>
        </div>
    </div>
    
    <script src="Build/{{{ LOADER_FILENAME }}}"></script>
    <script type="module">
        // Piper-WASM事前ロード
        const loadPiper = async () => {
            document.getElementById('loading-status').textContent = 'Loading TTS engine...';
            await import('./piper-wasm.js');
            document.getElementById('loading-progress').value = 50;
            
            document.getElementById('loading-status').textContent = 'Loading Unity...';
            createUnityInstance(document.querySelector("#unity-container"), {
                dataUrl: "Build/{{{ DATA_FILENAME }}}",
                frameworkUrl: "Build/{{{ FRAMEWORK_FILENAME }}}",
                codeUrl: "Build/{{{ CODE_FILENAME }}}",
                streamingAssetsUrl: "StreamingAssets",
                companyName: "{{{ COMPANY_NAME }}}",
                productName: "{{{ PRODUCT_NAME }}}",
                productVersion: "{{{ PRODUCT_VERSION }}}",
            }).then((unityInstance) => {
                document.getElementById('loading-overlay').style.display = 'none';
            });
        };
        
        loadPiper();
    </script>
</body>
</html>
```

## 実装スケジュール

**Week 1: 基本統合**
- Unity WebGLプラグイン作成
- JavaScript-C#ブリッジ実装
- 基本的な音声合成テスト

**Week 2: 最適化と製品化**
- メモリ使用量最適化
- エラーハンドリング
- UIコンポーネント作成
- Asset Store準備

## 成果物

1. **uPiper WebGL Package**
   - WebGLプラグイン
   - C# API
   - サンプルシーン
   
2. **ドキュメント**
   - セットアップガイド
   - APIリファレンス
   - トラブルシューティング

3. **デモ**
   - Unity WebGLビルド
   - 日本語TTS動作確認