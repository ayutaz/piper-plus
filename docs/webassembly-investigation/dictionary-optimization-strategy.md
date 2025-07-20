# OpenJTalk辞書データ最適化戦略

## 現状分析

### 辞書サイズ内訳（合計: 103MB）
- **sys.dic**: 99MB（システム辞書 - 単語と読み情報）
- **matrix.bin**: 3.7MB（連接コスト行列）
- **char.bin**: 257KB（文字定義）
- **その他**: 約300KB（ID定義、書き換えルール等）

### 問題点
- WebAssemblyでの103MBダウンロードは非現実的
- 初期化時のメモリ使用量が大きい
- モバイル環境での使用が困難

## 最適化戦略

### 1. 辞書の段階的構成（Progressive Loading）

**Tier 1: 最小辞書（2-3MB）**
```javascript
const minimalDict = {
    // 基本漢字（教育漢字1006字）
    basicKanji: 'basic-kanji.dic',      // ~1MB
    // ひらがな・カタカナ・記号
    kana: 'kana.dic',                    // ~100KB
    // 頻出語彙TOP 5000
    commonWords: 'common-5k.dic',        // ~1MB
    // 必須文法情報
    grammar: 'grammar-min.dic'           // ~500KB
};
```

**Tier 2: 標準辞書（10-15MB）**
```javascript
const standardDict = {
    ...minimalDict,
    // 常用漢字（2136字）
    joyoKanji: 'joyo-kanji.dic',        // ~3MB
    // 頻出語彙TOP 30000
    commonWords: 'common-30k.dic',       // ~8MB
    // 地名・人名基本
    properNouns: 'proper-basic.dic'      // ~2MB
};
```

**Tier 3: 完全辞書（30-40MB）**
```javascript
const fullDict = {
    ...standardDict,
    // 全漢字
    allKanji: 'all-kanji.dic',          // ~10MB
    // 専門用語
    technical: 'technical.dic',          // ~10MB
    // 完全な固有名詞
    properNounsFull: 'proper-full.dic'   // ~10MB
};
```

### 2. 圧縮技術の適用

**A. 辞書圧縮（Build時）**
```bash
# Brotli圧縮（最高圧縮率）
brotli -q 11 sys.dic -o sys.dic.br
# 99MB → ~20MB（約80%削減）

# 分割圧縮
split -b 5M sys.dic sys.dic.part.
for part in sys.dic.part.*; do
    brotli -q 11 $part -o $part.br
done
```

**B. 転送時圧縮**
```javascript
// サーバー設定
app.use(compression({
    filter: (req, res) => {
        // .dic ファイルは必ず圧縮
        return req.path.endsWith('.dic') || 
               compression.filter(req, res);
    },
    level: 9
}));
```

**C. ランタイム展開**
```javascript
// WebAssembly側で展開
async function loadCompressedDict(url) {
    const response = await fetch(url);
    const compressed = await response.arrayBuffer();
    
    // Brotli展開（WebAssembly実装）
    const decompressed = await decompress(compressed);
    
    // メモリマップドファイルとして登録
    FS.writeFile('/dict/sys.dic', new Uint8Array(decompressed));
}
```

### 3. インデックス化と最適化

**A. 頻度ベースインデックス**
```cpp
// 高頻度語彙を先頭に配置
struct OptimizedDict {
    // 頻度順TOP 10000（高速アクセス）
    FrequentWords frequent[10000];  // ~2MB
    
    // ハッシュテーブル（中頻度）
    HashMap medium;                  // ~5MB
    
    // B-Tree（低頻度・完全検索用）
    BTree rare;                     // 残り
};
```

**B. メモリマップ最適化**
```javascript
// 必要な部分のみメモリに展開
class LazyDict {
    constructor(dictPath) {
        this.header = this.loadHeader(dictPath);
        this.indices = this.loadIndices(dictPath);
        this.cache = new LRUCache(1000); // 1000語キャッシュ
    }
    
    async lookup(word) {
        if (this.cache.has(word)) {
            return this.cache.get(word);
        }
        
        const offset = this.indices[word.charCodeAt(0)];
        const data = await this.loadChunk(offset);
        const result = this.searchInChunk(data, word);
        
        this.cache.set(word, result);
        return result;
    }
}
```

### 4. 辞書データ配信最適化

**A. CDN活用**
```javascript
const DICT_CDN = 'https://cdn.jsdelivr.net/npm/piper-wasm-dict@1.0.0/';

async function loadDictWithCDN(tier = 'minimal') {
    const manifest = await fetch(`${DICT_CDN}/manifest.json`).then(r => r.json());
    const files = manifest[tier];
    
    // 並列ダウンロード
    const promises = files.map(file => 
        fetch(`${DICT_CDN}/${file}`)
            .then(r => r.arrayBuffer())
    );
    
    return Promise.all(promises);
}
```

**B. Service Worker キャッシュ**
```javascript
// sw.js
self.addEventListener('fetch', event => {
    if (event.request.url.includes('.dic')) {
        event.respondWith(
            caches.match(event.request).then(response => {
                return response || fetch(event.request).then(response => {
                    return caches.open('dict-v1').then(cache => {
                        cache.put(event.request, response.clone());
                        return response;
                    });
                });
            })
        );
    }
});
```

### 5. 実装例：最小辞書での動作

```javascript
// 最小限の実装（2-3MB）
class MinimalOpenJTalk {
    constructor() {
        this.dictSize = 0;
    }
    
    async initialize() {
        // 基本辞書のみロード
        const files = [
            'char.bin',        // 257KB
            'matrix-min.bin',  // 500KB（圧縮版）
            'sys-min.dic',     // 2MB（基本5000語）
            'unk.dic'          // 5.6KB
        ];
        
        for (const file of files) {
            const data = await this.loadDict(file);
            this.dictSize += data.byteLength;
        }
        
        console.log(`辞書サイズ: ${(this.dictSize / 1024 / 1024).toFixed(1)}MB`);
    }
    
    async loadDict(filename) {
        // Brotli圧縮ファイルを取得
        const response = await fetch(`/dict/${filename}.br`);
        const compressed = await response.arrayBuffer();
        
        // WebAssembly側で展開
        return this.decompress(compressed);
    }
}
```

## パフォーマンス目標

| 指標 | 現状 | 目標（最小） | 目標（標準） |
|------|------|------------|------------|
| 辞書サイズ | 103MB | 2-3MB | 10-15MB |
| 初期化時間 | 10秒+ | <1秒 | <3秒 |
| メモリ使用 | 200MB+ | 20MB | 50MB |
| 認識精度 | 100% | 90% | 98% |

## 実装優先度

1. **最小辞書の作成**（1週間）
   - 頻度分析による語彙選定
   - 圧縮フォーマット設計
   
2. **段階的ロード実装**（3-4日）
   - 非同期ロード機構
   - キャッシュシステム
   
3. **Unity WebGL統合**（1週間）
   - メモリ効率的なバインディング
   - プリロード最適化

## 結論

103MBの辞書を2-3MBまで削減することで、WebAssembly環境での実用的な日本語TTSが実現可能。段階的ロードとキャッシュにより、初期化時間を大幅に短縮しつつ、必要に応じて精度を向上させることができる。