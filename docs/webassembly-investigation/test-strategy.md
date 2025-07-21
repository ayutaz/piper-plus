# WebAssembly TTS テスト戦略

## 概要
このドキュメントは、Piper WebAssembly実装の包括的なテスト戦略を定義します。

## テストフェーズ

### Phase 1: ユニットテスト

#### 1.1 音素化テスト
```javascript
describe('OpenJTalk Phonemizer', () => {
    test('ひらがな変換', async () => {
        const result = await phonemizer.phonemize('こんにちは');
        expect(result).toEqual(['k', 'o', 'N', 'n', 'i', 'ch', 'i', 'w', 'a']);
    });
    
    test('カタカナ変換', async () => {
        const result = await phonemizer.phonemize('コンニチハ');
        expect(result).toEqual(['k', 'o', 'N', 'n', 'i', 'ch', 'i', 'w', 'a']);
    });
    
    test('漢字変換', async () => {
        const result = await phonemizer.phonemize('今日');
        expect(result).toContain('ky');
        expect(result).toContain('o');
    });
    
    test('PUAマッピング', async () => {
        const result = await phonemizer.convertToPUA(['ky', 'o']);
        expect(result[0]).toBe(0xe006); // kyのPUAコード
    });
});
```

#### 1.2 メモリ管理テスト
```javascript
describe('Memory Management', () => {
    test('メモリリーク検証', async () => {
        const iterations = 100;
        const measurements = [];
        
        for (let i = 0; i < iterations; i++) {
            if (global.gc) global.gc();
            const before = performance.memory.usedJSHeapSize;
            
            await tts.synthesize('テストテキスト');
            
            if (global.gc) global.gc();
            const after = performance.memory.usedJSHeapSize;
            measurements.push(after - before);
        }
        
        // メモリ使用量が安定していることを確認
        const avgGrowth = average(measurements);
        expect(avgGrowth).toBeLessThan(1024); // 1KB以下
    });
    
    test('Unity WebGL 256MB制限', async () => {
        const totalMemory = performance.memory.totalJSHeapSize;
        expect(totalMemory).toBeLessThan(256 * 1024 * 1024);
    });
});
```

### Phase 2: 統合テスト

#### 2.1 エンドツーエンドテスト
```javascript
describe('E2E Tests', () => {
    test('完全な音声合成フロー', async () => {
        // 1. 初期化
        const tts = new PiperTTS();
        await tts.initialize({
            dictLevel: 'minimal',
            modelPath: '/test/models/ja_JP-test.onnx'
        });
        
        // 2. 音声合成
        const text = 'これは統合テストです';
        const audio = await tts.synthesize(text);
        
        // 3. 検証
        expect(audio).toBeInstanceOf(Float32Array);
        expect(audio.length).toBeGreaterThan(22050); // 1秒以上
        expect(audio.some(v => v !== 0)).toBe(true); // 無音でない
    });
});
```

#### 2.2 ブラウザ互換性テスト
```javascript
// Playwright使用
import { test, expect } from '@playwright/test';

const browsers = ['chromium', 'firefox', 'webkit'];

browsers.forEach(browserName => {
    test.describe(`${browserName} compatibility`, () => {
        test('WebAssembly対応', async ({ page }) => {
            await page.goto('/test.html');
            
            const hasWasm = await page.evaluate(() => {
                return typeof WebAssembly !== 'undefined';
            });
            expect(hasWasm).toBe(true);
        });
        
        test('音声合成動作', async ({ page }) => {
            await page.goto('/test.html');
            
            const result = await page.evaluate(async () => {
                const tts = new window.PiperTTS();
                await tts.initialize();
                const audio = await tts.synthesize('テスト');
                return audio.length > 0;
            });
            
            expect(result).toBe(true);
        });
    });
});
```

### Phase 3: パフォーマンステスト

#### 3.1 ベンチマーク
```javascript
class PerformanceBenchmark {
    async runFullBenchmark() {
        const results = {
            initialization: {},
            synthesis: {},
            memory: {}
        };
        
        // 初期化ベンチマーク
        for (const dictLevel of ['minimal', 'standard', 'full']) {
            const start = performance.now();
            await tts.initialize({ dictLevel });
            results.initialization[dictLevel] = performance.now() - start;
        }
        
        // 合成ベンチマーク
        const testTexts = [
            { text: 'こんにちは', type: 'short' },
            { text: '今日は良い天気ですね。散歩に行きましょう。', type: 'medium' },
            { text: '長い文章...'.repeat(10), type: 'long' }
        ];
        
        for (const { text, type } of testTexts) {
            const times = [];
            for (let i = 0; i < 10; i++) {
                const start = performance.now();
                await tts.synthesize(text);
                times.push(performance.now() - start);
            }
            results.synthesis[type] = {
                avg: average(times),
                min: Math.min(...times),
                max: Math.max(...times),
                p95: percentile(times, 95)
            };
        }
        
        return results;
    }
}
```

#### 3.2 Unity WebGLフレームレートテスト
```javascript
test('60fps維持テスト', async () => {
    let frameCount = 0;
    let synthesisComplete = false;
    
    // フレームカウント
    const countFrames = () => {
        frameCount++;
        if (!synthesisComplete) {
            requestAnimationFrame(countFrames);
        }
    };
    
    countFrames();
    const startTime = performance.now();
    
    // 音声合成実行
    await tts.synthesize('フレームレートテスト用の長い文章です');
    synthesisComplete = true;
    
    const duration = performance.now() - startTime;
    const expectedFrames = (duration / 1000) * 60;
    const actualFps = (frameCount / duration) * 1000;
    
    expect(actualFps).toBeGreaterThan(55); // 55fps以上
});
```

### Phase 4: 品質テスト

#### 4.1 音質評価
```python
# MOS (Mean Opinion Score) 自動評価
import numpy as np
from pesq import pesq
from pystoi import stoi

def evaluate_audio_quality(reference_path, generated_path):
    # 参照音声と生成音声を読み込み
    ref_audio = load_audio(reference_path)
    gen_audio = load_audio(generated_path)
    
    # PESQ評価
    pesq_score = pesq(16000, ref_audio, gen_audio, 'wb')
    
    # STOI評価
    stoi_score = stoi(ref_audio, gen_audio, 16000)
    
    # 推定MOS
    estimated_mos = (pesq_score * 0.5 + stoi_score * 4.5)
    
    return {
        'pesq': pesq_score,
        'stoi': stoi_score,
        'estimated_mos': estimated_mos
    }
```

#### 4.2 日本語エッジケーステスト
```javascript
const edgeCases = [
    // 文字種混在
    'ABC123あいうえお',
    '㈱㈲㊤㊦㊧㊨',
    
    // 特殊記号
    '【重要】※注意：＃タグ',
    '♪♫♬♩',
    
    // 絵文字
    '😀😃😄😁',
    '🇯🇵日本',
    
    // 長音・促音
    'コーヒー',
    'がっこう',
    
    // 難読漢字
    '鬱蒼',
    '檸檬',
    
    // URL・メール
    'https://example.com',
    'test@example.jp'
];

edgeCases.forEach(text => {
    test(`エッジケース: ${text}`, async () => {
        const result = await tts.synthesize(text);
        expect(result).toBeDefined();
        expect(() => tts.synthesize(text)).not.toThrow();
    });
});
```

## CI/CD統合

### GitHub Actions設定
```yaml
name: WebAssembly TTS Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Setup Emscripten
      uses: mymindstorm/setup-emsdk@v11
      with:
        version: 3.1.61
    
    - name: Build WebAssembly
      run: |
        mkdir build && cd build
        emcmake cmake ..
        emmake make
    
    - name: Run Unit Tests
      run: npm test
    
    - name: Run E2E Tests
      run: |
        npx playwright install
        npm run test:e2e
    
    - name: Performance Benchmark
      run: |
        npm run benchmark
        # 結果をアーティファクトとして保存
        
    - name: Memory Profile
      run: |
        npm run test:memory
        # メモリ使用量レポート生成
```

## 監視とレポート

### パフォーマンスダッシュボード
```javascript
class PerformanceReporter {
    constructor() {
        this.metrics = [];
    }
    
    track(operation, duration, memory) {
        this.metrics.push({
            operation,
            duration,
            memory,
            timestamp: Date.now(),
            userAgent: navigator.userAgent
        });
        
        // リアルタイム送信（必要に応じて）
        if (this.metrics.length >= 100) {
            this.send();
        }
    }
    
    async send() {
        if (navigator.sendBeacon) {
            navigator.sendBeacon('/api/metrics', 
                JSON.stringify(this.metrics));
        }
        this.metrics = [];
    }
}
```

## テスト環境

### 必要なツール
- Node.js 18+
- Emscripten 3.1.61+
- Playwright (E2Eテスト)
- Jest (ユニットテスト)
- Python 3.9+ (音質評価)

### テストデータ
```
test-data/
├── texts/
│   ├── basic.json      # 基本テキスト
│   ├── edge-cases.json # エッジケース
│   └── performance.json # パフォーマンステスト用
├── models/
│   └── ja_JP-test.onnx # テスト用軽量モデル
└── audio/
    └── reference/       # 参照音声（音質評価用）
```

---

更新日: 2025-07-21