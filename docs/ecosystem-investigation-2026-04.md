# piper-plus エコシステム調査レポート (2026年4月)

**調査日**: 2026-04-07
**リポジトリ現況**: 108 stars / 9 forks / 直近14日 Clone 18,522 (770ユニーク)

---

## 1. フォーク調査

### 1-A. yeager (Daniel Nylander, Stockholm) — 唯一の外部コントリビューター

- **dev から 3 commits ahead**
- スウェーデン語 G2P の完全実装を含む PR #294 を提出 (2026-03-30)
- 変更: 16ファイル / +1,229行 (ルールベースG2P、PUAマッピング、テスト20件以上、NST学習準備スクリプト)
- 初版が espeak-ng 依存 (GPL) → 指摘を受けルールベースに書き直し → upstream では独自に PR #297 で対応済みのため close
- yeager の発音修正テーブル (hej, och, jag 等) は #297 の参考として活用された
- **SVネイティブの言語知識は貴重。継続的なフィードバック依頼を推奨**

### 1-B. endo5501 (日本) — Flutter FFI 統合

- **feat/support_cpp_library から 1 commit ahead**
- Flutter FFI 用の C API ラッパーを独自実装 (2026-03-22、305行)
- upstream の PR #309 で完全な C API (`libpiper_plus`) + Dart FFI サンプルが既にマージ済み
- **本人がupstreamの対応を知らない可能性が高い → 通知推奨**

### 1-C. ishine (上海、音声研究者、followers: 162)

- 2026-04-07 にフォーク。変更なし、ウォッチ目的
- 中国語圏の音声研究コミュニティからの関心シグナル

### 1-D. その他 (shiena, GodLoveOnly, kapmuantuang2-maker, shigeyukey, rajuaryan21, fightseed)

- 独自変更なし

### 1-E. コミュニティ Issue / リクエスト

- 外部ユーザーからの Issue: **0件** (全18件は全て ayutaz 自身が作成)
- 外部からの PR: yeager の #294 の **1件のみ**

---

## 2. 第三者による記事・コミュニティの反応

### 2-A. 第三者記事

| 記事 | 著者 | 要点 |
|------|------|------|
| [Zenn「piper-plus」を試す](https://zenn.dev/kun432/scraps/449c8261ec0a58) | kun432 | Docker失敗、Python成功、WebUI一部失敗、**Raspberry Pi 4B RTF 0.377で成功・高評価**。「制約環境で貴重な選択肢」 |
| [Note: piper-plusビルド&実行ガイド](https://note.com/aoya_uta/n/na501c8a6cc1b) | A-Uta | 自作「StackChain」でAquesTalk代替として検討。AquesTalkが非OSSのため。音声出力に問題が生じたと報告 |
| [Zenn: ブラウザ完結AITuber](https://zenn.dev/shinshin86/articles/ef4b5e50ecac42) | shinshin86 | **piper-plus WASMをブラウザ内TTSとして採用**。Chrome Built-in AI + piper-plus + ONNX Runtime Web構成。「AITuber用途として最低限成立する品質」 |
| [Neurlang Blog: Training Piper TTS](https://blog.hashtron.cloud/post/2025-09-28-training-a-a-tiny-piper-tts-model-for-any-language/) | Neurlang | 上流Piperの学習チュートリアル (piper-plus自体ではない) |

### 2-B. piper-plusが言及されていないTTS比較記事

| 記事 | 内容 |
|------|------|
| [Zenn「ローカル日本語TTSをいろいろ試す」](https://zenn.dev/megyo9/articles/b273c4c85ad451) (megyo9) | Style-Bert-VITS2、Kokoro等を比較。piper-plus未掲載 |
| [ocdevel「ElevenLabs Alternatives 2026」](https://ocdevel.com/blog/20250720-tts) | Kokoro、Chatterbox等が主役。piper-plus未掲載 |

### 2-C. HN / Reddit / X

- **HN Piper存続議論** (id=43591241): 「Piperは死んだが低スペックデバイスには最良」。piper-plusへの直接言及なし
- **X**: AITuber活用事例の発見に反応。v1.8.0リリース告知。uPiper開発成果の報告

### 2-D. 第三者記事から見えた課題

| 課題 | 報告元 | 現在の状態 |
|------|--------|-----------|
| Docker torchモジュール不在エラー | kun432 | **修正済み** (2026-04-07) |
| WebUI prosody_features エラー | kun432 | **修正済み** (2026-04-07) |
| Windows音声出力の問題 | A-Uta | 未確認 |
| WASM初回ロードの重さ | shinshin86 | 構造的制約 |
| TTS比較記事に未掲載 | megyo9他 | 認知度の課題 |

---

## 3. 競合環境と市場ポジション

### 3-A. 重要な環境変化 (3つの機会窓口)

| イベント | 時期 | piper-plusへの影響 |
|----------|------|-------------------|
| **rhasspy/piper がアーカイブ** | 2025/10 | MIT互換Piperフォークはpiper-plusのみに |
| **OHF-Voice/piper1-gpl が GPL-3.0 に移行** | - | 商用利用に制約。MIT代替を探す開発者の受け皿 |
| **openedai-speech (852 stars) がアーカイブ** | 2026/01 | OpenAI互換セルフホストTTSのポジションが空白 |

### 3-B. Stars・DL比較

| プロジェクト | Stars | ライセンス | 状態 |
|---|---|---|---|
| rhasspy/piper | 10,778 | MIT | **アーカイブ済み** |
| OHF-Voice/piper1-gpl | 3,521 | **GPL-3.0** | アクティブ |
| Kokoro | 6,389 | Apache 2.0 | アクティブ |
| F5-TTS | 14,297 | MIT | アクティブ |
| MeloTTS | 7,316 | MIT | アクティブ |
| **piper-plus** | **108** | **MIT** | **アクティブ** |

| パッケージ | 月間DL | 競合DL |
|---|---|---|
| piper-plus (npm) | 223 | kokoro-js: **177,662** |
| piper-tts-plus (PyPI) | 1,396 | - |
| piper-plus-cli (Rust) | 25 | piper-rs: 6,664 |

### 3-C. 主要競合の特徴と弱点

| 競合 | 強み | piper-plusとの差別化ポイント |
|---|---|---|
| **OHF-Voice/piper1-gpl** | Piperの正式後継、HA統合 | **GPL-3.0**。商用利用に制約。日本語G2P限定的 |
| **Kokoro/kokoro-js** | MOS 4.2高品質、npm 102万DL/年 | **英語に最適化**。日本語品質限定的。espeak-ng依存 |
| **Voxtral** | 4B、9言語、Apache 2.0 | **巨大 (4B)**。エッジ/ブラウザ不可 |
| **F5-TTS** | ゼロショットクローニング、14k stars | エッジ展開困難 |
| **Style-Bert-VITS2** | 日本語品質高い、学習GUI付き | モバイル非対応、サーバー型 |

### 3-D. piper-plusの唯一無二のポジション

> **「MITライセンス + espeak-ng不使用 + 日本語1st-class + 6言語SDK (C++/C#/Rust/Go/Python/npm) + エッジ動作」の組み合わせは他に存在しない**

---

## 4. 提言の対応状況チェック

### 4-A. 即座に実行 (1-2週間)

| # | 施策 | 状態 | 詳細 |
|---|---|---|---|
| 1 | endo5501 への通知 | **未対応** | upstream C API + Dart FFI の存在を通知推奨 |
| 2 | README冒頭に「MIT, no espeak-ng」明示 | **部分対応** | MITバッジは存在。テキストでの強調なし。piper1-gpl GPL移行との対比なし |
| 3 | OpenAI互換API Docker Hub公開 | **部分対応** | API完全実装済み。ghcr.io自動公開済み。**Docker Hub未公開** |
| 4 | kun432報告のDocker/WebUIエラー修正 | **対応済み** | 2026-04-07の複数コミットで修正完了 |

### 4-B. 短期 (1-3ヶ月)

| # | 施策 | 状態 | 詳細 |
|---|---|---|---|
| 5 | yeager へのフォローアップ | **部分対応** | SV実装は #297 で独自マージ済み。追加フィードバック依頼は未実施 |
| 6 | 英語圏での認知施策 | **未対応** | Show HN投稿、英語ブログ記事、Awesome TTS登録なし |
| 7 | npm READMEにKokoro.js比較表 | **未対応** | 技術文書として充実しているが競合比較なし |
| 8 | Issue/PRテンプレート + CONTRIBUTING拡充 | **部分対応** | CONTRIBUTING.md存在。GPL依存禁止ポリシー未記載。Issue/PRテンプレートなし |

### 4-C. 中期 (3-6ヶ月)

| # | 施策 | 状態 | 詳細 |
|---|---|---|---|
| 9 | KO/SVモデルの学習 | **G2P対応済み / モデル未学習** | 全プラットフォームでG2P実装完了。Rust piper-coreのSVのみ未実装。学習スクリプト未準備 |
| 10 | Open WebUI統合ガイド | **未対応** | OpenAI互換APIは完全実装だがガイドなし |
| 11 | Home Assistantコンポーネント | **未対応** | G2P体系が異なりHA標準Piperアドオンと非互換 |
| 12 | Unity Asset Store / Godotアセット登録 | **未確認** | C API + Godot GDExtensionサンプルは存在 |

### 4-D. 将来検討

| # | 施策 | 状態 | 詳細 |
|---|---|---|---|
| 13 | 音声品質ベンチマーク (MOS) 公開 | **未対応** | 客観的比較データなし |
| 14 | ファインチューニング簡略化 | **部分対応** | Template B はあるがワンクリック化は未実装 |
| 15 | 中国語圏アウトリーチ | **未対応** | README_ZH.md は存在。CSDN/知乎での発信なし |

---

## 5. 発見された技術的課題

| 課題 | 重要度 | 詳細 |
|---|---|---|
| **Rust piper-core に SV phonemizer 未実装** | 中 | `piper-plus-g2p` crateには実装済みだが、推論エンジン側 (`piper-core/src/phonemize/`) にSVモジュールがない |
| **Docker Hub 未公開** | 中 | ghcr.ioのみ。Docker Hub credentials + workflow追加で対応可能 |
| **python-inference用 docker-compose.yml なし** | 低 | WebUI用はあるがAPI用がない |

---

## 6. 需要シグナルまとめ

| 需要 | 強さ | piper-plusの対応度 | 機会 |
|------|------|-------------------|------|
| エッジデバイスでの日本語TTS | 高 | **完全対応** | RPi事例の拡充 |
| ブラウザ完結型TTS (WASM) | 高 | **対応済み** | Kokoro.jsとの差別化訴求 |
| Unity/ゲーム向けTTS | 中 | **対応済み** (uPiper, C API, Godot) | Asset Store登録 |
| OpenAI互換セルフホストTTS | 高 | **対応済み** | openedai-speech後継ポジション |
| MITライセンスのPiperフォーク | 高 | **唯一の選択肢** | ライセンス訴求強化 |
| OSS TTS の代替 (AquesTalk等) | 中 | **対応済み** | ドキュメント整備 |
| 音声品質向上 | 中 | 改善余地あり | ベンチマーク公開 |
| 簡単なセットアップ | 中 | **改善済み** (Docker修正) | Quick Start整備 |

---

## 7. 優先アクションリスト

### 最優先 (すぐ対応可能)

1. **README冒頭のMIT/espeak-ng強調** — テキスト追加のみ
2. **endo5501 への通知** — Issueコメントのみ
3. **Docker Hub公開設定** — workflow修正のみ

### 短期重点

4. **英語圏Show HN投稿** — 「Piper was archived. Here are your MIT-licensed options.」
5. **npm README競合比較表** — Kokoro.jsとの差別化
6. **Issue/PRテンプレート追加** — GPL依存禁止ポリシー明記
7. **Rust piper-core SV phonemizer追加** — 技術的な実装漏れ

### 中期重点

8. **KO/SVモデル学習** — G2Pは完成済み、データセット準備から
9. **Open WebUI統合ガイド** — OpenAI互換APIのユースケース拡大
10. **Awesome TTS リスト等への登録** — 認知経路の確保
