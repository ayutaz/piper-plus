# Unity WebGL統合ガイド

最終更新: 2025-07-21

## 概要

Piper WebAssembly実装をUnity WebGLプロジェクトに統合するための詳細ガイドです。

## Unity WebGL特有の制約

### メモリ制限
- **ヒープサイズ**: 256MB（デフォルト）
- **推奨使用量**: 200MB以下
- **AudioClip**: 追加のメモリ消費に注意

### スレッド制限
- **シングルスレッド**: Web Workerは別コンテキスト
- **メインスレッドブロック**: 長時間処理は避ける
- **非同期処理**: コルーチンまたはasync/await推奨

## 実装アーキテクチャ

```
Unity C# Layer
    ↓
Unity WebGL JavaScript Bridge (.jslib)
    ↓
Piper WebAssembly Module
    ↓
Browser Audio API
```

## JavaScript Plugin (.jslib)

### 基本構造
```javascript
// PiperWebGL.jslib
var PiperWebGLPlugin = {
    $PiperState: {
        initialized: false,
        module: null,
        audioContext: null,
        pendingCallbacks: {},
        memoryPool: []
    },

    PiperWebGL_Initialize: function(modelPathPtr, dictPathPtr, callbackPtr) {
        var modelPath = UTF8ToString(modelPathPtr);
        var dictPath = UTF8ToString(dictPathPtr);
        
        // AudioContext初期化
        if (!PiperState.audioContext) {
            PiperState.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        
        // WebAssemblyモジュール読み込み
        loadPiperModule({
            modelPath: modelPath,
            dictPath: dictPath,
            onSuccess: function() {
                Module.dynCall_vi(callbackPtr, 1);
            },
            onError: function(error) {
                console.error('Piper initialization failed:', error);
                Module.dynCall_vi(callbackPtr, 0);
            }
        });
    },

    PiperWebGL_SetMemoryLimit: function(limitMB) {
        // メモリ使用量制限設定
        PiperState.memoryLimit = limitMB * 1024 * 1024;
    },

    PiperWebGL_GetMemoryUsage: function() {
        if (performance.memory) {
            return performance.memory.usedJSHeapSize;
        }
        return 0;
    }
};

autoAddDeps(PiperWebGLPlugin, '$PiperState');
mergeInto(LibraryManager.library, PiperWebGLPlugin);
```

### メモリ管理
```javascript
// メモリプール実装
var MemoryManager = {
    allocateAudioBuffer: function(size) {
        // プールから再利用
        for (var i = 0; i < PiperState.memoryPool.length; i++) {
            var buffer = PiperState.memoryPool[i];
            if (buffer.byteLength >= size) {
                PiperState.memoryPool.splice(i, 1);
                return buffer;
            }
        }
        
        // 新規割り当て
        return _malloc(size);
    },
    
    freeAudioBuffer: function(ptr, size) {
        // プールに返却（最大10個）
        if (PiperState.memoryPool.length < 10) {
            PiperState.memoryPool.push({
                ptr: ptr,
                byteLength: size
            });
        } else {
            _free(ptr);
        }
    }
};
```

## C#インターフェース

### 基本実装
```csharp
using System;
using System.Runtime.InteropServices;
using UnityEngine;
using System.Threading.Tasks;

namespace PiperTTS.WebGL
{
    public class PiperWebGLManager : MonoBehaviour
    {
        #if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")]
        private static extern void PiperWebGL_Initialize(
            string modelPath, string dictPath, Action<int> callback);
        
        [DllImport("__Internal")]
        private static extern void PiperWebGL_Synthesize(
            string text, Action<IntPtr, int, int> callback);
        
        [DllImport("__Internal")]
        private static extern void PiperWebGL_SetMemoryLimit(int limitMB);
        
        [DllImport("__Internal")]
        private static extern int PiperWebGL_GetMemoryUsage();
        #endif

        private static PiperWebGLManager instance;
        private bool isInitialized = false;
        
        public static PiperWebGLManager Instance
        {
            get
            {
                if (instance == null)
                {
                    GameObject go = new GameObject("PiperWebGLManager");
                    instance = go.AddComponent<PiperWebGLManager>();
                    DontDestroyOnLoad(go);
                }
                return instance;
            }
        }

        private void Awake()
        {
            if (instance != null && instance != this)
            {
                Destroy(gameObject);
                return;
            }
            instance = this;
        }

        public async Task<bool> InitializeAsync(PiperConfig config)
        {
            #if UNITY_WEBGL && !UNITY_EDITOR
            var tcs = new TaskCompletionSource<bool>();
            
            // メモリ制限設定
            PiperWebGL_SetMemoryLimit(config.MemoryLimitMB ?? 100);
            
            PiperWebGL_Initialize(
                config.ModelPath,
                config.DictPath,
                (success) => {
                    isInitialized = success == 1;
                    tcs.SetResult(isInitialized);
                }
            );
            
            return await tcs.Task;
            #else
            Debug.LogWarning("PiperTTS WebGL is only supported in WebGL builds");
            return false;
            #endif
        }

        public async Task<AudioClip> GenerateAudioAsync(string text)
        {
            if (!isInitialized)
            {
                throw new InvalidOperationException("PiperTTS is not initialized");
            }

            #if UNITY_WEBGL && !UNITY_EDITOR
            var tcs = new TaskCompletionSource<AudioClip>();
            
            PiperWebGL_Synthesize(text, (dataPtr, length, sampleRate) => {
                StartCoroutine(CreateAudioClipCoroutine(dataPtr, length, sampleRate, tcs));
            });
            
            return await tcs.Task;
            #else
            return null;
            #endif
        }

        private System.Collections.IEnumerator CreateAudioClipCoroutine(
            IntPtr dataPtr, int length, int sampleRate, 
            TaskCompletionSource<AudioClip> tcs)
        {
            // メインスレッドでAudioClip作成
            float[] audioData = new float[length];
            Marshal.Copy(dataPtr, audioData, 0, length);
            
            AudioClip clip = AudioClip.Create(
                "TTS_Output",
                length,
                1, // モノラル
                sampleRate,
                false
            );
            
            clip.SetData(audioData, 0);
            tcs.SetResult(clip);
            
            // メモリ解放
            Marshal.FreeHGlobal(dataPtr);
            
            yield return null;
        }

        public float GetMemoryUsageMB()
        {
            #if UNITY_WEBGL && !UNITY_EDITOR
            return PiperWebGL_GetMemoryUsage() / (1024f * 1024f);
            #else
            return 0f;
            #endif
        }
    }
}
```

### 使用例
```csharp
public class TTSExample : MonoBehaviour
{
    [SerializeField] private AudioSource audioSource;
    [SerializeField] private Text statusText;
    [SerializeField] private InputField textInput;
    
    async void Start()
    {
        statusText.text = "初期化中...";
        
        var config = new PiperConfig
        {
            ModelPath = "StreamingAssets/models/ja_JP-kokoro-medium.onnx",
            DictPath = "StreamingAssets/dict/minimal",
            MemoryLimitMB = 100
        };
        
        bool success = await PiperWebGLManager.Instance.InitializeAsync(config);
        
        if (success)
        {
            statusText.text = "準備完了";
        }
        else
        {
            statusText.text = "初期化失敗";
        }
    }
    
    public async void OnSynthesizeButton()
    {
        try
        {
            statusText.text = "音声生成中...";
            
            var audioClip = await PiperWebGLManager.Instance.GenerateAudioAsync(
                textInput.text
            );
            
            audioSource.clip = audioClip;
            audioSource.Play();
            
            statusText.text = $"再生中 (メモリ: {PiperWebGLManager.Instance.GetMemoryUsageMB():F1}MB)";
        }
        catch (Exception e)
        {
            statusText.text = $"エラー: {e.Message}";
        }
    }
}
```

## Unity プロジェクト設定

### Player Settings
```json
{
  "WebGLMemorySize": 256,
  "WebGLExceptionSupport": "None",
  "WebGLCompressionFormat": "Brotli",
  "WebGLLinkerTarget": "Wasm",
  "WebGLThreadsSupport": false,
  "WebGLDecompressionFallback": true
}
```

### ビルド設定
1. **Code Optimization**: "Runtime Speed"
2. **IL2CPP Code Generation**: "Faster Runtime"
3. **Managed Stripping Level**: "Medium"

## パフォーマンス最適化

### 1. オーディオキャッシング
```csharp
public class AudioClipCache : MonoBehaviour
{
    private Dictionary<string, AudioClip> cache = new Dictionary<string, AudioClip>();
    private Queue<string> lruQueue = new Queue<string>();
    private const int MAX_CACHE_SIZE = 10;
    
    public bool TryGetCached(string text, out AudioClip clip)
    {
        return cache.TryGetValue(text, out clip);
    }
    
    public void AddToCache(string text, AudioClip clip)
    {
        if (cache.Count >= MAX_CACHE_SIZE)
        {
            var oldest = lruQueue.Dequeue();
            var oldClip = cache[oldest];
            cache.Remove(oldest);
            Destroy(oldClip);
        }
        
        cache[text] = clip;
        lruQueue.Enqueue(text);
    }
}
```

### 2. バッチ処理
```csharp
public class TTSBatchProcessor : MonoBehaviour
{
    private Queue<TTSRequest> requestQueue = new Queue<TTSRequest>();
    private bool isProcessing = false;
    
    public void QueueSynthesis(string text, Action<AudioClip> callback)
    {
        requestQueue.Enqueue(new TTSRequest { Text = text, Callback = callback });
        
        if (!isProcessing)
        {
            StartCoroutine(ProcessQueue());
        }
    }
    
    private IEnumerator ProcessQueue()
    {
        isProcessing = true;
        
        while (requestQueue.Count > 0)
        {
            var request = requestQueue.Dequeue();
            
            var clip = await PiperWebGLManager.Instance.GenerateAudioAsync(request.Text);
            request.Callback?.Invoke(clip);
            
            // フレームレート維持のため少し待機
            yield return new WaitForSeconds(0.1f);
        }
        
        isProcessing = false;
    }
}
```

## トラブルシューティング

### メモリ不足エラー
```csharp
// メモリ監視とGC
private void Update()
{
    if (Time.frameCount % 300 == 0) // 5秒ごと
    {
        float memoryMB = PiperWebGLManager.Instance.GetMemoryUsageMB();
        if (memoryMB > 180) // 180MB超えたら警告
        {
            Debug.LogWarning($"Memory usage high: {memoryMB}MB");
            System.GC.Collect();
            Resources.UnloadUnusedAssets();
        }
    }
}
```

### フレームレート低下
```csharp
// 非同期処理でメインスレッドをブロックしない
public async void GenerateMultipleAudios(List<string> texts)
{
    foreach (var text in texts)
    {
        var clip = await PiperWebGLManager.Instance.GenerateAudioAsync(text);
        
        // フレームごとに処理を分散
        await Task.Yield();
    }
}
```

## ベストプラクティス

1. **初期化タイミング**: シーンロード時ではなく、アプリ起動時に初期化
2. **辞書レベル**: モバイルブラウザでは最小辞書を使用
3. **エラーハンドリング**: try-catchで必ずエラー処理
4. **メモリ管理**: 不要なAudioClipは即座にDestroy
5. **プロファイリング**: Unity ProfilerとChrome DevToolsを併用

---

Unity WebGL環境でPiper TTSを安定して動作させるための実装ガイドです。