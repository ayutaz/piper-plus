# Unity Piper TTS テストケース仕様書

## 1. ユニットテスト仕様

### 1.1 Core API テスト

#### PiperTTS クラステスト
```csharp
[TestFixture]
public class PiperTTSTests
{
    // 初期化テスト
    [Test]
    public async Task Initialize_WithValidConfig_Succeeds()
    [Test]
    public async Task Initialize_WithNullConfig_UsesDefaults()
    [Test]
    public async Task Initialize_WithInvalidDictPath_ThrowsException()
    [Test]
    public async Task Initialize_CalledTwice_ResetsState()
    
    // 音声生成テスト
    [Test]
    public async Task GenerateSpeech_WithValidText_ReturnsAudioClip()
    [Test]
    public async Task GenerateSpeech_WithEmptyText_ReturnsNull()
    [Test]
    public async Task GenerateSpeech_WithNullText_ThrowsArgumentNullException()
    [Test]
    public async Task GenerateSpeech_BeforeInitialize_ThrowsInvalidOperationException()
    [Test]
    public async Task GenerateSpeech_WithLongText_HandlesCorrectly()
    [Test]
    public async Task GenerateSpeech_WithSpecialCharacters_ProcessesCorrectly()
    
    // 言語切り替えテスト
    [TestCase("ja", "こんにちは")]
    [TestCase("en", "Hello")]
    [TestCase("es", "Hola")]
    public async Task GenerateSpeech_WithDifferentLanguages_ProducesOutput(string lang, string text)
    
    // キャンセレーションテスト
    [Test]
    public async Task GenerateSpeech_WithCancellation_StopsProcessing()
    [Test]
    public async Task GenerateSpeech_MultipleRequests_HandlesCorrectly()
    
    // エラーハンドリングテスト
    [Test]
    public async Task GenerateSpeech_WithUnsupportedLanguage_FallsBackToDefault()
    [Test]
    public async Task GenerateSpeech_OutOfMemory_ThrowsOutOfMemoryException()
}
```

### 1.2 音素化エンジンテスト

#### OpenJTalkPhonemizer テスト
```csharp
[TestFixture]
public class OpenJTalkPhonemizerTests
{
    // 基本機能テスト
    [Test]
    public void Phonemize_WithHiragana_ReturnsCorrectPhonemes()
    [Test]
    public void Phonemize_WithKatakana_ReturnsCorrectPhonemes()
    [Test]
    public void Phonemize_WithKanji_ReturnsCorrectPhonemes()
    [Test]
    public void Phonemize_WithRomaji_ReturnsCorrectPhonemes()
    [Test]
    public void Phonemize_WithNumbers_ConvertsToReading()
    [Test]
    public void Phonemize_WithMixedText_HandlesCorrectly()
    
    // エッジケーステスト
    [TestCase("")]
    [TestCase(" ")]
    [TestCase("\n")]
    public void Phonemize_WithWhitespace_ReturnsEmpty(string input)
    
    [Test]
    public void Phonemize_WithEmojiAndSymbols_FiltersCorrectly()
    [Test]
    public void Phonemize_WithVeryLongText_DoesNotCrash()
    
    // アクセント・抑揚テスト
    [Test]
    public void Phonemize_PreservesAccentInformation()
    [Test]
    public void Phonemize_HandlesCompoundWords()
    
    // パフォーマンステスト
    [Test]
    [Timeout(100)] // 100ms以内
    public void Phonemize_Performance_MeetsRequirements()
}
```

#### EspeakPhonemizer テスト
```csharp
[TestFixture]
public class EspeakPhonemizerTests
{
    // 多言語テスト
    [TestCase("en", "Hello world", new[] {"h", "ə", "l", "əʊ", "w", "ɜː", "l", "d"})]
    [TestCase("es", "Hola mundo", new[] {"o", "l", "a", "m", "u", "n", "d", "o"})]
    [TestCase("fr", "Bonjour", new[] {"b", "ɔ̃", "ʒ", "u", "ʁ"})]
    public void Phonemize_WithDifferentLanguages_ReturnsIPAPhonemes(
        string lang, string text, string[] expected)
    
    // 言語自動検出テスト
    [Test]
    public void Phonemize_WithAutoDetect_IdentifiesLanguageCorrectly()
    
    // フォールバックテスト
    [Test]
    public void Phonemize_WithUnsupportedLanguage_FallsBackToEnglish()
}
```

### 1.3 プラットフォーム抽象化テスト

#### Platform Base テスト
```csharp
[TestFixture]
public class PlatformTests
{
    [Test]
    public void GetPlatform_OnWindows_ReturnsWindowsPlatform()
    [Test]
    public void GetPlatform_OnAndroid_ReturnsAndroidPlatform()
    [Test]
    public void GetPlatform_OnWebGL_ReturnsWebGLPlatform()
    
    // ファイルパステスト
    [Test]
    public void GetDataPath_ReturnsValidPath()
    [Test]
    public void GetPersistentDataPath_ReturnsWritablePath()
    
    // ネイティブライブラリテスト
    [Test]
    public void LoadNativeLibrary_WithValidPath_Succeeds()
    [Test]
    public void LoadNativeLibrary_WithInvalidPath_ThrowsException()
}
```

### 1.4 ユーティリティテスト

#### AudioClipHelper テスト
```csharp
[TestFixture]
public class AudioClipHelperTests
{
    [Test]
    public void CreateAudioClip_WithValidData_ReturnsValidClip()
    [Test]
    public void CreateAudioClip_WithEmptyData_ReturnsNull()
    [Test]
    public void ConvertToWav_ProducesValidWavFile()
    [Test]
    public void ResampleAudio_MaintainsQuality()
    
    // ストリーミングテスト
    [Test]
    public void CreateStreamingClip_HandlesDataInChunks()
    [Test]
    public void StreamingClip_PlaysWhileLoading()
}
```

#### CacheManager テスト
```csharp
[TestFixture]
public class CacheManagerTests
{
    [Test]
    public void Add_WithNewKey_StoresValue()
    [Test]
    public void Get_WithExistingKey_ReturnsValue()
    [Test]
    public void Get_WithNonExistentKey_ReturnsNull()
    [Test]
    public void Add_ExceedsMaxSize_EvictsOldestEntry()
    [Test]
    public void Clear_RemovesAllEntries()
    
    // TTLテスト
    [Test]
    public async Task Get_AfterTTLExpires_ReturnsNull()
    
    // スレッドセーフティテスト
    [Test]
    public async Task ConcurrentAccess_RemainsThreadSafe()
}
```

---

## 2. 統合テスト仕様

### 2.1 エンドツーエンドテスト

```csharp
[TestFixture]
[Category("Integration")]
public class EndToEndTests
{
    [Test]
    public async Task FullPipeline_JapaneseText_ProducesPlayableAudio()
    {
        // Arrange
        var config = new PiperConfig
        {
            Language = "ja",
            VoiceModel = "japanese_voice_v1",
            SampleRate = 22050
        };
        var tts = new PiperTTS();
        
        // Act
        await tts.InitializeAsync(config);
        var audioClip = await tts.GenerateSpeechAsync("本日は晴天なり");
        
        // Assert
        Assert.NotNull(audioClip);
        Assert.Greater(audioClip.length, 1.0f); // 1秒以上
        Assert.AreEqual(22050, audioClip.frequency);
        
        // 音声品質チェック
        var samples = new float[audioClip.samples];
        audioClip.GetData(samples, 0);
        Assert.That(samples, Has.Some.GreaterThan(0.1f)); // 無音でない
    }
    
    [Test]
    public async Task MultiLanguage_SwitchingLanguages_WorksCorrectly()
    {
        var tts = new PiperTTS();
        await tts.InitializeAsync(new PiperConfig());
        
        // 日本語
        var jpClip = await tts.GenerateSpeechAsync("こんにちは", "ja");
        Assert.NotNull(jpClip);
        
        // 英語
        var enClip = await tts.GenerateSpeechAsync("Hello", "en");
        Assert.NotNull(enClip);
        
        // スペイン語
        var esClip = await tts.GenerateSpeechAsync("Hola", "es");
        Assert.NotNull(esClip);
    }
}
```

### 2.2 プラットフォーム別統合テスト

```csharp
[TestFixture]
[Category("Platform")]
public class PlatformIntegrationTests
{
    [Test]
    [UnityPlatform(RuntimePlatform.Android)]
    public async Task Android_LoadsNativeLibrary_Successfully()
    {
        var platform = new AndroidPlatform();
        await platform.InitializeAsync();
        Assert.IsTrue(platform.IsInitialized);
    }
    
    [Test]
    [UnityPlatform(RuntimePlatform.WebGLPlayer)]
    public async Task WebGL_InitializesWASM_Successfully()
    {
        var platform = new WebGLPlatform();
        await platform.InitializeAsync();
        Assert.IsTrue(platform.IsInitialized);
    }
    
    [Test]
    public async Task AllPlatforms_HandleMemoryPressure_Gracefully()
    {
        var tts = new PiperTTS();
        await tts.InitializeAsync(new PiperConfig());
        
        // メモリプレッシャーをシミュレート
        for (int i = 0; i < 100; i++)
        {
            var clip = await tts.GenerateSpeechAsync($"Test {i}");
            // Unity自動GCに依存
        }
        
        // クラッシュしないことを確認
        Assert.Pass();
    }
}
```

---

## 3. パフォーマンステスト仕様

### 3.1 ベンチマークテスト

```csharp
[TestFixture]
[Category("Performance")]
public class PerformanceBenchmarks
{
    private PiperTTS _tts;
    
    [OneTimeSetUp]
    public async Task Setup()
    {
        _tts = new PiperTTS();
        await _tts.InitializeAsync(new PiperConfig());
    }
    
    [Test]
    [TestCase("短い文章", 10)]
    [TestCase("これは少し長めの文章で、複数の文節を含んでいます。", 50)]
    [TestCase("非常に長い文章..." /* 500文字 */, 200)]
    public async Task GenerateSpeech_Performance_MeetsTarget(
        string text, int maxMilliseconds)
    {
        var sw = Stopwatch.StartNew();
        var clip = await _tts.GenerateSpeechAsync(text);
        sw.Stop();
        
        Assert.Less(sw.ElapsedMilliseconds, maxMilliseconds,
            $"Processing took {sw.ElapsedMilliseconds}ms, expected < {maxMilliseconds}ms");
    }
    
    [Test]
    public async Task MemoryUsage_StaysWithinLimits()
    {
        var initialMemory = GC.GetTotalMemory(true);
        
        for (int i = 0; i < 10; i++)
        {
            await _tts.GenerateSpeechAsync("メモリテスト");
        }
        
        GC.Collect();
        GC.WaitForPendingFinalizers();
        GC.Collect();
        
        var finalMemory = GC.GetTotalMemory(true);
        var memoryIncrease = finalMemory - initialMemory;
        
        Assert.Less(memoryIncrease, 10 * 1024 * 1024, // 10MB以下
            $"Memory increased by {memoryIncrease / 1024 / 1024}MB");
    }
}
```

### 3.2 ストレステスト

```csharp
[TestFixture]
[Category("Stress")]
[Explicit] // 手動実行のみ
public class StressTests
{
    [Test]
    [Timeout(300000)] // 5分
    public async Task ContinuousGeneration_RunsFor5Minutes()
    {
        var tts = new PiperTTS();
        await tts.InitializeAsync(new PiperConfig());
        
        var endTime = DateTime.Now.AddMinutes(5);
        var count = 0;
        
        while (DateTime.Now < endTime)
        {
            var clip = await tts.GenerateSpeechAsync($"ストレステスト {count++}");
            Assert.NotNull(clip);
            await Task.Delay(100); // 少し待機
        }
        
        Assert.Greater(count, 0);
    }
    
    [Test]
    public async Task ConcurrentRequests_HandledCorrectly()
    {
        var tts = new PiperTTS();
        await tts.InitializeAsync(new PiperConfig());
        
        var tasks = Enumerable.Range(0, 50)
            .Select(i => tts.GenerateSpeechAsync($"並行処理 {i}"))
            .ToArray();
        
        var results = await Task.WhenAll(tasks);
        
        Assert.That(results, Has.All.Not.Null);
        Assert.AreEqual(50, results.Length);
    }
}
```

---

## 4. 受け入れテスト仕様

### 4.1 ユーザーシナリオテスト

```csharp
[TestFixture]
[Category("Acceptance")]
public class UserScenarioTests
{
    [Test]
    public async Task Scenario_GameDialog_WorksAsExpected()
    {
        // ゲーム内ダイアログのシナリオ
        var tts = new PiperTTS();
        await tts.InitializeAsync(new PiperConfig
        {
            Language = "ja",
            VoiceModel = "character_voice_female"
        });
        
        // NPCの会話
        var dialogues = new[]
        {
            "こんにちは、冒険者さん！",
            "今日はいい天気ですね。",
            "何かお手伝いできることはありますか？"
        };
        
        foreach (var dialogue in dialogues)
        {
            var clip = await tts.GenerateSpeechAsync(dialogue);
            Assert.NotNull(clip);
            
            // 実際のゲームでは AudioSource.PlayClipAtPoint() など
            await Task.Delay(2000); // 再生時間をシミュレート
        }
    }
    
    [Test]
    public async Task Scenario_AccessibilityReader_ReadsUICorrectly()
    {
        // アクセシビリティ機能のシナリオ
        var tts = new PiperTTS();
        await tts.InitializeAsync(new PiperConfig
        {
            Language = "ja",
            Speed = 1.2f // 少し速め
        });
        
        // UI要素のテキスト
        var uiTexts = new[]
        {
            "新規ゲーム",
            "続きから",
            "オプション",
            "終了"
        };
        
        foreach (var text in uiTexts)
        {
            var clip = await tts.GenerateSpeechAsync(text);
            Assert.NotNull(clip);
            Assert.Less(clip.length, 2.0f); // 短いUI読み上げ
        }
    }
}
```

### 4.2 エッジケーステスト

```csharp
[TestFixture]
[Category("EdgeCases")]
public class EdgeCaseTests
{
    [Test]
    public async Task VeryLongText_DoesNotCrash()
    {
        var tts = new PiperTTS();
        await tts.InitializeAsync(new PiperConfig());
        
        var longText = string.Join(" ", Enumerable.Repeat("これは長い文章です。", 100));
        var clip = await tts.GenerateSpeechAsync(longText);
        
        Assert.NotNull(clip);
    }
    
    [Test]
    public async Task SpecialCharacters_HandledGracefully()
    {
        var tts = new PiperTTS();
        await tts.InitializeAsync(new PiperConfig());
        
        var specialTexts = new[]
        {
            "🎮 ゲーム 🎯",
            "100% 完了！",
            "メール: test@example.com",
            "¥1,000",
            "「引用文」"
        };
        
        foreach (var text in specialTexts)
        {
            var clip = await tts.GenerateSpeechAsync(text);
            Assert.NotNull(clip);
        }
    }
    
    [Test]
    public async Task RapidLanguageSwitching_WorksCorrectly()
    {
        var tts = new PiperTTS();
        await tts.InitializeAsync(new PiperConfig());
        
        for (int i = 0; i < 10; i++)
        {
            var lang = i % 2 == 0 ? "ja" : "en";
            var text = i % 2 == 0 ? "日本語" : "English";
            
            var clip = await tts.GenerateSpeechAsync(text, lang);
            Assert.NotNull(clip);
        }
    }
}
```

---

## 5. 回帰テスト仕様

### 5.1 バージョン互換性テスト

```csharp
[TestFixture]
[Category("Regression")]
public class CompatibilityTests
{
    [Test]
    public void API_BackwardCompatibility_Maintained()
    {
        // 旧APIが引き続き動作することを確認
        var tts = new PiperTTS();
        
        // v0.x API
        Assert.DoesNotThrow(() => tts.Initialize(null));
        
        // v1.x API
        Assert.DoesNotThrowAsync(async () => 
            await tts.InitializeAsync(new PiperConfig()));
    }
    
    [Test]
    public void SavedData_LoadsInNewVersion()
    {
        // 旧バージョンで保存されたデータが読み込めることを確認
        var oldCacheData = File.ReadAllBytes("TestData/old_cache.dat");
        var cache = CacheManager.LoadFromBytes(oldCacheData);
        
        Assert.NotNull(cache);
        Assert.Greater(cache.Count, 0);
    }
}
```

---

## 6. テスト実行マトリクス

| テストカテゴリ | Unity 2020.3 | Unity 2021.3 | Unity 2022.3 | 実行頻度 |
|--------------|-------------|-------------|-------------|---------|
| Unit Tests | ✓ | ✓ | ✓ | 各コミット |
| Integration | ✓ | ✓ | ✓ | PR時 |
| Performance | ✓ | - | ✓ | 日次 |
| Stress | - | - | ✓ | 週次 |
| Acceptance | ✓ | ✓ | ✓ | リリース前 |

---

## 7. テストデータ管理

### 7.1 テストデータ構造
```
Tests/
├── TestData/
│   ├── Audio/
│   │   ├── expected_output_ja.wav
│   │   ├── expected_output_en.wav
│   │   └── reference_samples.json
│   ├── Text/
│   │   ├── japanese_test_cases.txt
│   │   ├── multilingual_test_cases.txt
│   │   └── edge_cases.txt
│   └── Config/
│       ├── test_config_minimal.json
│       ├── test_config_full.json
│       └── test_config_invalid.json
└── Fixtures/
    ├── MockPhonemizer.cs
    ├── TestAudioSource.cs
    └── TestHelpers.cs
```

### 7.2 テストデータ生成
```csharp
public static class TestDataGenerator
{
    public static string[] GetJapaneseTestCases()
    {
        return new[]
        {
            "ひらがな",
            "カタカナ",
            "漢字",
            "Mixed混在text",
            "数字123",
            "記号！？",
            // ... 他のケース
        };
    }
    
    public static AudioClip CreateTestAudioClip(
        float duration = 1.0f, 
        int frequency = 22050)
    {
        // テスト用の音声クリップ生成
    }
}
```

---

この詳細なテスト仕様により、TDDアプローチでの開発が可能になり、高品質なUnityプラグインの開発が実現できます。