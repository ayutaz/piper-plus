# piper-plus ユーザビリティ課題レポート (2026年3月)

## 概要

外部ユーザー A-Uta 氏の記事「[軽量TTS piper-plusビルド＆実行ガイド — Windowsでつくよみちゃんの声を作る！](https://note.com/aoya_uta/n/na501c8a6cc1b)」(2026-03-15公開) を起点に、コードベース・ドキュメント・GitHub Issues/PRs を総合調査し、ユーザビリティ課題を洗い出した。

### 調査対象

| ソース | 内容 |
|--------|------|
| 外部記事 | A-Uta氏のWindows環境でのビルド＆実行体験記 |
| コードベース | `src/cpp/main.cpp`, `docs/`, `README.md`, `pyproject.toml` 等 |
| GitHub Issues | 17件のopen issue, 12件のclosed issue |
| GitHub PRs | 5件のopen PR |
| GitHub Releases | v1.6.0 (2026-03-04) のリリースアセット |

### 記事の著者プロフィール

- **プロジェクト**: Stack-chan ミニマル (小型ロボット)
- **環境**: Windows
- **動機**: AquesTalk ESP32 (プロプライエタリ) → piper-plus (MIT) への移行
- **スキル**: コマンドライン操作可能、C++ビルド環境は専門外
- **選定理由**: 軽さ、自然な音質、MITライセンス

### 対応状況サマリ (2026-03-15 更新)

- [PR #241](https://github.com/ayutaz/piper-plus/pull/241) (マージ済み, commit `1dc64b6`) により、ドキュメント改善を実施。
- [PR #242](https://github.com/ayutaz/piper-plus/pull/242) (マージ済み, commit `b20b116`) により、WebUI セッションキャッシュを導入。
- [PR #243](https://github.com/ayutaz/piper-plus/pull/243) (マージ済み, commit `932cceb`) により、config.json フォールバック検索を統一。

| # | 優先度 | 課題 | 状態 | 種別 |
|---|--------|------|------|------|
| 1 | P0 | プリビルドバイナリの導線 | **解決済み** | ドキュメント |
| 2 | P0 | config.json 命名規則 | **解決済み** | PR #243 でフォールバック検索実装; HFリネーム不要に |
| 3 | P0 | Windows 日本語エンコーディング | **解決済み** | C++ `--text` オプション追加、`speak.bat`/`speak.ps1` 同梱 |
| 4 | P0 | WebUI パフォーマンス (#235) | **解決済み** | PR #242 でセッションキャッシュ導入 |
| 5 | P1 | ORT SessionOptions (#233) | **未解決** | コード変更が必要; Issue OPEN |
| 6 | P1 | コマンドが長い / `--text` | **解決済み** | `--text` オプション追加、環境変数サポート |
| 7 | P1 | モデルダウンロード手動 | **解決済み** | `--list-models`、`--download-model` 実装 |
| 8 | P1 | 学習ガイド陳腐化 | **解決済み** | ドキュメント |
| 9 | P1 | ドキュメント構造 | **解決済み** | ドキュメント |
| 10 | P2 | 多言語ドキュメント | **未解決** | 機能PR完了待ち |
| 11 | P2 | ビルド時警告 | **一部解決** | ドキュメント注記追加済み; CMake抑制未実施 |
| 12 | P2 | HTTP サーバーモード | **未解決** | 機能追加が必要 |
| 13 | P2 | ユースケース別ガイド | **未解決** | ドキュメント作成が必要 |
| 14 | P2 | PyPI パッケージ品質 | **未解決** | CI変更が必要 |
| 15 | P2 | FP16 変換ツール (#236) | **未解決** | コード変更が必要; Issue OPEN |

**結果**: 15件中 10件完全解決、1件一部解決、4件未解決

---

## P0: 今すぐ対処すべき課題

### 1. プリビルドバイナリの導線が見つけにくい ✅ 解決済み

> **PR #241 で対応済み**: クイックスタートの先頭に「プリビルドバイナリ (ビルド不要)」セクションを配置。Windows/macOS/Linux別のダウンロード→モデル取得→音声生成の3ステップガイドを追加。

**現象**

記事の著者は Visual Studio 2022 のインストールから始まる6ステップのソースビルドを行った。しかし [GitHub Releases v1.6.0](https://github.com/ayutaz/piper-plus/releases/tag/v1.6.0) には `piper-windows-x64.zip` が既に存在し、ビルド不要で利用可能。

---

### 2. config.json 命名規則の不一致 ✅ 解決済み

> **PR #241 で対応済み (ドキュメント)**: README に命名規則の説明と `--config` ワークアラウンドを追記。troubleshooting.md に「Model config doesn't exist」セクションを追加。

> **PR #243 で対応済み (コード)**: 全コンポーネントに config.json フォールバック検索を実装。
> - 検索順序: `{model}.onnx.json` → `{dir}/config.json`
> - 対象: C++ CLI, Python SDK, Python推論, Docker推論
> - ドキュメント (README.md, troubleshooting.md) も更新済み
> - これにより HuggingFace 上のリネームが不要に

**現象**

C++ CLI は `モデル名.onnx.json` を自動検出する (`src/cpp/main.cpp:834`):
```cpp
filesystem::path(runConfig.modelPath.string() + ".json");
```

しかし HuggingFace 上のつくよみちゃんモデルの設定ファイルは `config.json`。
ユーザーは `--config models\config.json` を毎回明示する必要があった (PR #243 で解決)。

---

### 3. Windows 日本語テキスト エンコーディング問題 ✅ 解決済み

> **PR #241 で対応済み (ドキュメント)**: windows-setup.md にエンコーディング対策セクション追加

> **feat/cpp-cli-ux で対応済み (コード)**:
> - (A) piper.exe に `--text "テキスト"` オプション追加 — Windows パイプのエンコーディング問題を完全回避
> - (B) 公式 `speak.bat` / `speak.ps1` を `scripts/` に同梱
> - (C) 環境変数 `PIPER_DEFAULT_MODEL` / `PIPER_DEFAULT_CONFIG` サポート

**現象**

PowerShell から piper.exe に日本語テキストをパイプすると文字化けし、OpenJTalk が `No phoneme` で失敗する。

記事の著者は70行以上の `speak.bat` を自作して回避。

---

### 4. WebUI パフォーマンス問題 (Issue #235) ✅ 解決済み

> **PR #242 で対応済み**: モジュールレベルのセッションキャッシュを導入。モデルパスをキーとして `InferenceSession` / `PiperVoice` をキャッシュし、2回目以降のリクエストでモデルロード（100ms〜1s）をスキップ。`threading.Lock()` によるスレッドセーフ実装。対象: `webui.py`, `docker/webui/app.py`, `huggingface-space/app.py` の3ファイル。

**現象**

ONNX `InferenceSession` がリクエスト毎に再生成されている。

**影響**: 不要なレイテンシとメモリ消費。

**状態**: Issue #235 CLOSED (PR #242 で解決)。

---

## P1: 早期に対処すべき課題

### 5. ORT SessionOptions 未最適化 (Issue #233) ❌ 未解決

**現象**: ONNX Runtime の SessionOptions が最適化されていない。

**改善案**: 3行の変更で10-15%の推論速度改善が見込める。

**状態**: Issue #233 OPEN。

---

### 6. 実行コマンドが長すぎる ✅ 解決済み

> **feat/cpp-cli-ux で対応済み**:
> - `--text` オプション: パイプ不要で直接テキスト入力
> - 環境変数: `PIPER_DEFAULT_MODEL`, `PIPER_DEFAULT_CONFIG` サポート
> - 公式 `speak.bat` / `speak.ps1` ヘルパースクリプト同梱
>
> 使用例:
> ```
> piper.exe --model model.onnx --text "こんにちは" -f output.wav
> ```

---

### 7. モデルダウンロードの手動作業 ✅ 解決済み

> **PR #241 で対応済み (ドキュメント)**: README にモデルカタログ表とダウンロードコマンドを追加

> **feat/cpp-cli-ux で対応済み (コード)**:
> - `--list-models [LANG]` でモデル一覧表示
> - `--download-model NAME` でHuggingFaceからモデル自動ダウンロード
> - `--model-dir DIR` でダウンロード先指定
> - piper-plus 固有モデル（つくよみちゃん、20話者ベース）と upstream piper-voices を統合カタログで提供

---

### 8. 学習ガイドの陳腐化 ✅ 解決済み

> **PR #241 で対応済み**: training-guide.md を `uv` ベースに全面更新。NCCL環境変数追加、WavLM Discriminatorセクション追加、テスト手順をONNX変換→推論の正しいフローに修正。

---

### 9. ドキュメント構造の問題 ✅ 解決済み

> **PR #241 で対応済み**:
> - windows-setup.md に cmd 例を PowerShell と併記
> - WavLM 推論パラメータを README、japanese-usage.md、専用ガイド (wavlm-guide.md) に公開
> - docs/README.md に「はじめての方へ」セクション追加（初心者/開発者向け導線）
> - ビルド警告 (C4996) の説明を追加

---

## P2: 中期的に対処すべき課題

### 10. 多言語ドキュメントの不足 ❌ 未解決

**現象**: PRs #218 (日英バイリンガル), #219 (6言語対応) が開発中だが、多言語モデルの学習・利用に関するドキュメントがない。

**改善案**: 多言語対応が完了次第、ユーザー向けガイドを作成。

---

### 11. ビルド時の大量警告 🟡 一部解決

> **PR #241 で対応済み (ドキュメント)**: windows-setup.md に「C4996 警告は正常」の注意書きを追加。

> **残課題 (コード)**: CMakeLists.txt での警告抑制 (`/wd4996`) 未実施。

---

### 12. HTTP サーバーモード (C++ CLI) ❌ 未解決

**現象**: IoT/組み込み用途 (Stack-chan 等) では HTTP サーバーとしての利用需要がある。

**現状**: WebUI (Gradio) と Python HTTP サーバーはあるが、C++ CLI にはない。

**改善案**: C++ CLI に `--http-server` オプションを追加、または軽量 HTTP ラッパーの提供。

---

### 13. ユースケース別ガイドの不足 ❌ 未解決

不足しているガイド:
- Android Termux での使い方
- ESP32 / IoT デバイスとの連携
- ストリーミングモードの実用例
- Unity (uPiper) / Godot との連携

---

### 14. PyPI パッケージの品質 ❌ 未解決

**前例**: Issue #171 で日本語音素マップモジュールが pip パッケージに含まれていなかった。

**改善案**: CI に PyPI パッケージのインストールテストを追加。

---

### 15. FP16 モデル変換ツール (Issue #236, PR #239) ❌ 未解決

モデルサイズ 50% 削減が可能。PR #239 が 3/4 タスク完了済み。IoT/モバイル用途で特に有用。

**状態**: Issue #236 OPEN。

---

## GitHub Issues/PRs から見える追加の機会

### 要望が多いカテゴリ

| カテゴリ | Issues | 概要 |
|----------|--------|------|
| 多言語対応 | #23, #137, #141, #142 | 中国語・韓国語が最も要望多い |
| Zero-shot TTS | #223, PR #222 | 新話者のファインチューニング不要化 |
| 音質改善 | #200, #202, #206 | Multi-Resolution STFT, Duration正則化 |
| ゲームエンジン | #153 | Godot対応 (Unity=uPiper は既存) |
| 日本語固有 | #110, #203 | 間(ま)のランダム性、アクセント強度 |
| Speaker Morphing | #237 | SLERP補間による話者ブレンド |
| モデル軽量化 | #236, PR #239 | FP16変換で50%サイズ削減 |
| アーキテクチャ | PR #240 | VITS2改善 (品質向上 + 34%サイズ削減) |

---

## 次のアクション優先順位 (残課題)

| # | アクション | 工数 | 効果 | 関連Issue | 状態 |
|---|-----------|------|------|-----------|------|
| 1 | ORT SessionOptions 最適化 | 小 | 中 | #233 | ❌ 未着手 |
| ~~2~~ | ~~C++ CLI に `--text` オプション追加~~ | ~~中~~ | ~~大~~ | - | ✅ 完了 |
| ~~3~~ | ~~公式 speak.bat/ps1 同梱~~ | ~~小~~ | ~~中~~ | - | ✅ 完了 |
| 4 | ビルド時警告の CMake 抑制 | 小 | 小 | - | ❌ 未着手 |

---

## 参考資料

- 記事: [軽量TTS piper-plusビルド＆実行ガイド](https://note.com/aoya_uta/n/na501c8a6cc1b) (A-Uta, 2026-03-15)
- 開発者記事: [piper-plusの開発 - yousanのメモ](https://ayousanz.hatenadiary.jp/)
- GitHub: [ayutaz/piper-plus](https://github.com/ayutaz/piper-plus)
- HuggingFace: [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)
- GitHub Releases: [v1.6.0](https://github.com/ayutaz/piper-plus/releases/tag/v1.6.0)
- 対応PR: [#241](https://github.com/ayutaz/piper-plus/pull/241) (マージ済み) — ドキュメント改善
- 対応PR: [#242](https://github.com/ayutaz/piper-plus/pull/242) (マージ済み) — WebUI セッションキャッシュ
- 対応PR: [#243](https://github.com/ayutaz/piper-plus/pull/243) (マージ済み) — config.json フォールバック検索統一
