# GitHub Pages デプロイメント手順

## 概要
このドキュメントでは、WebAssembly版Piperのデモページを GitHub Pages にデプロイする手順を説明します。

## 必要な修正

### 1. 相対パスの調整
現在の実装では、すべてのリソースが `../` で始まる相対パスを使用しています。
GitHub Pages でホストする場合は、これらのパスを調整する必要があります。

### 2. config.js の設定
`demo/config.js` を以下のように編集：

```javascript
const deploymentConfig = {
    isGitHubPages: true,  // true に変更
    basePath: '/piper-plus/src/wasm/openjtalk-web/',  // リポジトリとパスに合わせて設定
};
```

### 3. index.html の修正が必要な箇所

```javascript
// 例：カスタム辞書の読み込み
const dictPath = deploymentConfig.getPath('../assets/custom_dictionary.json');
await customDict.loadFromJSON(dictPath);

// OpenJTalk の初期化
await unifiedPhonemizer.initialize({
    openjtalk: {
        jsPath: deploymentConfig.getPath('../dist/openjtalk.js'),
        wasmPath: deploymentConfig.getPath('../dist/openjtalk.wasm'),
        dictPath: deploymentConfig.getPath('../assets/dict')
    }
});
```

## デプロイ方法

### 方法1: gh-pages ブランチを使用

```bash
# gh-pages ブランチを作成
git checkout -b gh-pages

# 必要なファイルをルートにコピー
cp -r src/wasm/openjtalk-web/* .

# コミット & プッシュ
git add .
git commit -m "Deploy to GitHub Pages"
git push origin gh-pages
```

### 方法2: GitHub Actions を使用

`.github/workflows/deploy-demo.yml` を作成：

```yaml
name: Deploy Demo to GitHub Pages

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup directories
        run: |
          mkdir -p public
          cp -r src/wasm/openjtalk-web/* public/
          
      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./public
```

## 必要なディレクトリ構造

GitHub Pages で正しく動作するには、以下の構造が必要：

```
/（GitHub Pages ルート）
├── index.html (demo/index.html)
├── config.js
├── assets/
│   ├── custom_dictionary.json
│   └── dict/
├── dist/
│   ├── openjtalk.js
│   ├── openjtalk.wasm
│   └── espeak-ng/
├── src/
│   ├── index.js
│   ├── model-manager.js
│   ├── dict-manager.js
│   ├── audio-result.js
│   ├── espeak_phoneme_extractor.js
│   └── custom_dictionary.js
└── models/
    ├── multilingual-test-medium.onnx
    └── multilingual-test-medium.onnx.json
```

## 注意事項

1. **ファイルサイズ**: GitHub Pages には 100MB のファイルサイズ制限があります
2. **帯域幅**: 月間 100GB の帯域幅制限があります
3. **HTTPS**: GitHub Pages は HTTPS でのみ提供されます
4. **CORS**: 外部リソースへのアクセスには CORS 設定が必要です

## 代替案：CDN の使用

大きなモデルファイルは CDN にホストすることを検討：

```javascript
// モデルを CDN から読み込む例
const modelPath = 'https://cdn.jsdelivr.net/gh/username/repo@version/models/multilingual-test-medium.onnx';
```

## トラブルシューティング

1. **404 エラー**: パスが正しく設定されているか確認
2. **CORS エラー**: すべてのリソースが同一オリジンからアクセスされているか確認
3. **読み込みエラー**: ブラウザの開発者ツールでネットワークタブを確認