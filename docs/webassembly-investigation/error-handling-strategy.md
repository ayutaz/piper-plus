# WebAssembly TTS エラーハンドリング戦略

## 概要
このドキュメントは、Piper WebAssembly実装における包括的なエラーハンドリング戦略を定義します。

## エラー分類と対策

### 1. 初期化エラー

#### 1.1 WebAssembly未対応
```javascript
class WebAssemblyDetector {
    static isSupported() {
        try {
            if (typeof WebAssembly === 'undefined') {
                return false;
            }
            
            // 基本的な機能テスト
            const testModule = new WebAssembly.Module(
                new Uint8Array([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00])
            );
            
            return testModule !== undefined;
        } catch (e) {
            return false;
        }
    }
    
    static getMissingFeatures() {
        const features = [];
        
        if (typeof WebAssembly === 'undefined') {
            features.push('WebAssembly');
        }
        
        if (!('instantiateStreaming' in WebAssembly)) {
            features.push('WebAssembly.instantiateStreaming');
        }
        
        if (typeof SharedArrayBuffer === 'undefined') {
            features.push('SharedArrayBuffer');
        }
        
        return features;
    }
}

// 使用例
if (!WebAssemblyDetector.isSupported()) {
    throw new PiperError(
        'WASM_NOT_SUPPORTED',
        'WebAssemblyがサポートされていません。',
        {
            missingFeatures: WebAssemblyDetector.getMissingFeatures(),
            fallbackUrl: 'https://api.piper-tts.com/'
        }
    );
}
```

#### 1.2 メモリ不足
```javascript
class MemoryManager {
    static async checkAvailableMemory() {
        if (!performance.memory) {
            // メモリ情報が利用できない場合は推定
            return { available: true, estimate: null };
        }
        
        const used = performance.memory.usedJSHeapSize;
        const limit = performance.memory.jsHeapSizeLimit;
        const available = limit - used;
        
        // Unity WebGLの場合の特別な処理
        if (window.UNITY_WEBGL) {
            const requiredMemory = 100 * 1024 * 1024; // 100MB
            return {
                available: available > requiredMemory,
                estimate: available,
                required: requiredMemory
            };
        }
        
        return {
            available: available > 50 * 1024 * 1024, // 50MB
            estimate: available
        };
    }
    
    static async freeMemory() {
        // キャッシュクリア
        if (window.caches) {
            const cacheNames = await caches.keys();
            await Promise.all(
                cacheNames.map(name => caches.delete(name))
            );
        }
        
        // 強制GC（利用可能な場合）
        if (global.gc) {
            global.gc();
        }
        
        // カスタムキャッシュクリア
        PiperCache.clear();
    }
}
```

### 2. ランタイムエラー

#### 2.1 辞書ロードエラー
```javascript
class DictionaryLoader {
    constructor() {
        this.retryCount = 3;
        this.retryDelay = 1000;
        this.fallbackUrls = [
            '/dict/', // ローカル
            'https://cdn1.piper-tts.com/dict/', // プライマリCDN
            'https://cdn2.piper-tts.com/dict/'  // セカンダリCDN
        ];
    }
    
    async loadDictionary(level = 'minimal') {
        let lastError;
        
        for (const baseUrl of this.fallbackUrls) {
            try {
                return await this.loadFromUrl(`${baseUrl}${level}.br`);
            } catch (error) {
                lastError = error;
                console.warn(`Dictionary load failed from ${baseUrl}:`, error);
            }
        }
        
        // すべて失敗した場合
        throw new PiperError(
            'DICT_LOAD_FAILED',
            '辞書の読み込みに失敗しました',
            {
                level,
                attempts: this.fallbackUrls.length,
                lastError
            }
        );
    }
    
    async loadFromUrl(url) {
        let attempt = 0;
        
        while (attempt < this.retryCount) {
            try {
                const response = await fetch(url);
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                
                const data = await response.arrayBuffer();
                
                // 破損チェック
                if (!this.validateDictionary(data)) {
                    throw new Error('Invalid dictionary format');
                }
                
                return data;
                
            } catch (error) {
                attempt++;
                
                if (attempt < this.retryCount) {
                    await new Promise(resolve => 
                        setTimeout(resolve, this.retryDelay * attempt)
                    );
                } else {
                    throw error;
                }
            }
        }
    }
    
    validateDictionary(data) {
        // 辞書フォーマットの検証
        if (data.byteLength < 1024) { // 最小サイズチェック
            return false;
        }
        
        // マジックナンバーチェック（例）
        const view = new DataView(data);
        const magic = view.getUint32(0, true);
        
        return magic === 0x4D454342; // 'MECB'
    }
}
```

#### 2.2 音声合成エラー
```javascript
class SynthesisErrorHandler {
    constructor() {
        this.fallbackStrategies = {
            'OUT_OF_MEMORY': this.handleOutOfMemory.bind(this),
            'INVALID_INPUT': this.handleInvalidInput.bind(this),
            'MODEL_ERROR': this.handleModelError.bind(this)
        };
    }
    
    async handleSynthesisError(error, text, options = {}) {
        console.error('Synthesis error:', error);
        
        // エラータイプの判定
        const errorType = this.classifyError(error);
        
        // 対応する戦略を実行
        if (this.fallbackStrategies[errorType]) {
            return await this.fallbackStrategies[errorType](text, options);
        }
        
        // デフォルトフォールバック
        return await this.defaultFallback(text, options);
    }
    
    classifyError(error) {
        if (error.message.includes('memory')) {
            return 'OUT_OF_MEMORY';
        }
        if (error.message.includes('invalid') || error.message.includes('input')) {
            return 'INVALID_INPUT';
        }
        if (error.message.includes('model') || error.message.includes('onnx')) {
            return 'MODEL_ERROR';
        }
        return 'UNKNOWN';
    }
    
    async handleOutOfMemory(text, options) {
        // メモリ解放を試みる
        await MemoryManager.freeMemory();
        
        // テキストを分割して再試行
        const chunks = this.splitText(text, 50); // 50文字ごと
        const results = [];
        
        for (const chunk of chunks) {
            try {
                const audio = await this.synthesizeWithRetry(chunk, options);
                results.push(audio);
            } catch (e) {
                // チャンクも失敗した場合はサーバーフォールバック
                const serverAudio = await this.serverFallback(chunk);
                results.push(serverAudio);
            }
        }
        
        return this.concatenateAudio(results);
    }
    
    async handleInvalidInput(text, options) {
        // テキストのサニタイズ
        const sanitized = this.sanitizeText(text);
        
        if (sanitized !== text) {
            // サニタイズ後に再試行
            return await this.synthesizeWithRetry(sanitized, options);
        }
        
        // それでもダメならエラーメッセージ音声を返す
        return await this.generateErrorAudio('入力テキストが無効です');
    }
    
    sanitizeText(text) {
        return text
            .replace(/[\x00-\x1F\x7F]/g, '') // 制御文字削除
            .replace(/\s+/g, ' ') // 連続空白を単一スペースに
            .trim()
            .substring(0, 1000); // 最大1000文字
    }
    
    async serverFallback(text) {
        const response = await fetch('/api/tts/fallback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, source: 'wasm-fallback' })
        });
        
        if (!response.ok) {
            throw new Error('Server fallback failed');
        }
        
        const audioData = await response.arrayBuffer();
        return new Float32Array(audioData);
    }
}
```

### 3. Unity WebGL固有のエラー

```javascript
class UnityWebGLErrorHandler {
    static handleUnityError(error) {
        const handlers = {
            'Array buffer allocation failed': this.handleMemoryError,
            'INVOKING RANDOM MEMORY': this.handleCorruption,
            'Cannot enlarge memory arrays': this.handleHeapExhaustion
        };
        
        for (const [pattern, handler] of Object.entries(handlers)) {
            if (error.message.includes(pattern)) {
                return handler.call(this, error);
            }
        }
        
        return this.handleGenericError(error);
    }
    
    static handleMemoryError(error) {
        // Unity側にメモリ不足を通知
        if (window.unityInstance) {
            window.unityInstance.SendMessage(
                'TTSManager',
                'OnMemoryError',
                JSON.stringify({
                    used: performance.memory.usedJSHeapSize,
                    limit: performance.memory.jsHeapSizeLimit
                })
            );
        }
        
        // 簡易モードに切り替え
        return {
            action: 'SWITCH_TO_LITE_MODE',
            retry: true
        };
    }
    
    static handleHeapExhaustion(error) {
        // ヒープ枯渇時は再起動を推奨
        return {
            action: 'RECOMMEND_RESTART',
            message: 'メモリ不足です。ページを再読み込みしてください。',
            retry: false
        };
    }
}
```

### 4. グレースフルデグレード戦略

```javascript
class GracefulDegradation {
    constructor() {
        this.degradationLevels = [
            { name: 'full', dictSize: '10MB', quality: 'high' },
            { name: 'standard', dictSize: '5MB', quality: 'medium' },
            { name: 'minimal', dictSize: '2MB', quality: 'basic' },
            { name: 'server', dictSize: '0', quality: 'server' }
        ];
        
        this.currentLevel = 0;
    }
    
    async synthesizeWithDegradation(text) {
        while (this.currentLevel < this.degradationLevels.length) {
            const level = this.degradationLevels[this.currentLevel];
            
            try {
                if (level.name === 'server') {
                    // サーバーフォールバック
                    return await this.serverSynthesize(text);
                }
                
                // WebAssembly合成を試行
                return await this.wasmSynthesize(text, level);
                
            } catch (error) {
                console.warn(`Level ${level.name} failed:`, error);
                
                // 次のレベルにデグレード
                this.currentLevel++;
                
                // ユーザーに通知
                this.notifyDegradation(level.name);
            }
        }
        
        throw new Error('All synthesis methods failed');
    }
    
    notifyDegradation(fromLevel) {
        const event = new CustomEvent('piperDegradation', {
            detail: {
                from: fromLevel,
                to: this.degradationLevels[this.currentLevel]?.name || 'none',
                reason: 'synthesis_failure'
            }
        });
        
        window.dispatchEvent(event);
    }
}
```

### 5. エラー監視とレポート

```javascript
class ErrorReporter {
    constructor() {
        this.errorQueue = [];
        this.reportInterval = 60000; // 1分
        this.maxQueueSize = 100;
        
        // 定期送信
        setInterval(() => this.flush(), this.reportInterval);
        
        // ページ離脱時の送信
        window.addEventListener('unload', () => this.flush(true));
    }
    
    captureError(error, context = {}) {
        const errorData = {
            timestamp: Date.now(),
            type: error.code || error.name || 'Unknown',
            message: error.message,
            stack: error.stack,
            context: {
                ...context,
                userAgent: navigator.userAgent,
                memory: performance.memory ? {
                    used: performance.memory.usedJSHeapSize,
                    limit: performance.memory.jsHeapSizeLimit
                } : null,
                url: window.location.href
            }
        };
        
        this.errorQueue.push(errorData);
        
        // キューサイズ制限
        if (this.errorQueue.length > this.maxQueueSize) {
            this.errorQueue.shift();
        }
        
        // 重大なエラーは即座に送信
        if (this.isCriticalError(error)) {
            this.flush();
        }
    }
    
    isCriticalError(error) {
        const criticalTypes = ['WASM_CRASH', 'OUT_OF_MEMORY', 'INIT_FAILED'];
        return criticalTypes.includes(error.code);
    }
    
    async flush(useBeacon = false) {
        if (this.errorQueue.length === 0) return;
        
        const errors = [...this.errorQueue];
        this.errorQueue = [];
        
        const payload = JSON.stringify({ errors });
        
        if (useBeacon && navigator.sendBeacon) {
            navigator.sendBeacon('/api/errors', payload);
        } else {
            try {
                await fetch('/api/errors', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: payload
                });
            } catch (e) {
                // エラーレポート自体が失敗した場合は諦める
                console.error('Failed to report errors:', e);
            }
        }
    }
}

// グローバルエラーハンドラー
window.addEventListener('error', (event) => {
    if (event.filename?.includes('piper-wasm')) {
        ErrorReporter.instance.captureError(event.error, {
            filename: event.filename,
            lineno: event.lineno,
            colno: event.colno
        });
    }
});
```

---

更新日: 2025-07-21