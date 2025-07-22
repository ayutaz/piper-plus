# GitHub Pages デプロイメント手順

## セットアップ

### 1. リポジトリ設定

1. GitHubリポジトリの Settings > Pages に移動
2. Source を "GitHub Actions" に設定

### 2. 必要なシークレット（不要）

このワークフローは自動的にGITHUB_TOKENを使用するため、追加のシークレットは不要です。

## デプロイ方法

### 自動デプロイ

以下の条件で自動的にデプロイされます：
- `main` または `feat/webassembly-support` ブランチへのプッシュ
- `src/wasm/` ディレクトリ内のファイル変更時

### 手動デプロイ

1. GitHub Actions タブに移動
2. "Deploy WASM Demo to GitHub Pages" ワークフローを選択
3. "Run workflow" をクリック

## ローカルでのビルドテスト

```bash
cd src/wasm
./build-demo.sh
cd ../../demo-site
python3 serve.py
```

## デプロイされるコンテンツ

- `/` - デモ一覧ページ
- `/mecab-test.html` - MeCab形態素解析デモ
- `/openjtalk-test.html` - OpenJTalk音素変換デモ  
- `/full-tts-demo.html` - 完全統合TTSデモ
- `/streaming-tts-demo.html` - ストリーミングTTSデモ
- `/real-model-demo.html` - 実モデル音声合成デモ

## デプロイURL

デプロイ後、以下のURLでアクセス可能：
- `https://<username>.github.io/<repository-name>/`

## トラブルシューティング

### ビルドが失敗する場合

1. Emscriptenのバージョンを確認（3.1.61以上）
2. Node.jsのバージョンを確認（20以上）
3. Git LFSが有効になっているか確認

### ページが表示されない場合

1. GitHub Pages が有効になっているか確認
2. デプロイが完了しているか Actions タブで確認
3. ブラウザのキャッシュをクリア

### CORS エラーが発生する場合

GitHub Pagesではヘッダーのカスタマイズができないため、一部の機能（SharedArrayBuffer等）が制限される可能性があります。

## 注意事項

- 大きなファイル（辞書、モデル）は Git LFS を使用することを推奨
- 初回ロードには時間がかかる場合があります
- モバイルデバイスでは動作保証外です