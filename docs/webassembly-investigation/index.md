# WebAssembly/WebGL対応 技術調査ドキュメント

このディレクトリには、piper-plusおよびuPiperのWebAssembly/WebGL対応に関する詳細な技術調査結果が含まれています。

## 📚 ドキュメント一覧

### [README.md](./README.md)
調査結果の全体サマリー。実現可能性評価、推奨実装戦略、スケジュールの概要。

### [japanese-tts-implementation.md](./japanese-tts-implementation.md)
日本語TTS機能の最小実装計画。具体的なコード例、ビルド手順、段階的実装アプローチ。

### [dictionary-optimization-strategy.md](./dictionary-optimization-strategy.md)
OpenJTalk辞書データの最適化戦略。103MBから2-3MBへの削減方法、圧縮技術、段階的ロード実装。

### [unity-webgl-implementation-strategy.md](./unity-webgl-implementation-strategy.md)
Unity WebGL環境での実装方針。ネイティブプラグイン作成、C# API設計、デプロイメント設定。

## 🔗 関連Issue

- [piper-plus #106: WebAssembly対応によるブラウザ内TTS実行](https://github.com/ayutaz/piper-plus/issues/106)
- [uPiper #17: WebGL Platform Support for OpenJTalk Phonemizer](https://github.com/ayutaz/uPiper/issues/17)

## 📅 調査実施日

2025年7月20日

## 🎯 調査目的

1. WebAssembly環境でのpiper-plus実行可能性の検証
2. 日本語TTS（OpenJTalk）のブラウザ対応方法の調査
3. Unity WebGL環境での統合方法の検討
4. 実装に必要な工数とリソースの見積もり

## 💡 主な結論

- **実現可能性**: 高い
- **推奨アプローチ**: piper-plus側でWebAssembly基盤を構築後、uPiper側で統合
- **想定期間**: 日本語TTS最小実装まで4-6週間、Unity WebGL統合まで8-10週間
- **最大の課題**: 辞書サイズの最適化（103MB → 2-3MB）

詳細は各ドキュメントをご参照ください。