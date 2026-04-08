# piper-plus マイルストーン計画 (2026年 H1-H2)

**作成日**: 2026-04-08
**最終更新**: 2026-04-08 (レビュー反映)
**ベース文書**: `docs/v1.11.0-market-reaction-and-improvements-2026-04.md`
**現況**: 113 stars / 9 forks / 外部コントリビューター 1名 / 外部Issue 0件
**チケット管理**: [docs/tickets/](tickets/README.md) (全53チケット)

---

## KPI ダッシュボード

| 指標 | 現在 (4月) | M1完了 (4/22) | M2完了 (6/22) | M3完了 (12/31) |
|------|-----------|--------------|--------------|---------------|
| GitHub Stars | 113 | 125 | 250 | 500 |
| Forks | 9 | 12 | 25 | 60 |
| 外部コントリビューター | 1 | 2 | 4 | 10 |
| npm DL/月 | 223 | 350 | 1,500 | 5,000 |
| PyPI DL/月 | 1,396 | 2,000 | 5,000 | 15,000 |
| crates.io DL 総計 | 44 | 100 | 500 | 2,000 |
| HF tsukuyomi DL | 1,509 | 2,000 | 5,000 | 15,000 |
| 外部 Issue 数 | 0 | 2 | 8 | 25 |
| 外部 PR 数 | 1 | 2 | 5 | 12 |
| 第三者記事 (日本語) | 2 | 3 | 8 | 15 |
| 第三者記事 (英語) | 0 | 0 | 2 | 5 |
| HF モデル数 | 3 | 3 | 5 | 12 |

> **Note:** KPI は Show HN / Reddit バズの成否に左右されるため、M2 以降は「楽観」「現実」の2段階で追跡を推奨。上記は現実ラインの目標値。

---

## M1: First Impression (v1.12.0)

**期間**: 2026-04-08 〜 2026-04-22 (2週間)
**テーマ**: 「初めて触った人が30秒で音を出せる」状態を作る
**リリース**: v1.12.0

### タスク一覧

| # | タスク | チケット | カテゴリ | 工数 | 依存 | 成果物 |
|---|--------|---------|---------|------|------|--------|
| M1-1 | README「30秒で試す」セクション追加 | [詳細](tickets/M1/M1-01.md) | オンボーディング | 0.5d | なし | README.md 更新 |
| M1-2 | 「Try in Browser」バッジ追加 | [詳細](tickets/M1/M1-02.md) | オンボーディング | 0.5h | なし | README.md 更新 |
| M1-3 | HF 全モデルに `pipeline_tag: text-to-speech` + `library_name: onnxruntime` 追加 | [詳細](tickets/M1/M1-03.md) | モデル配布 | 1d | なし | HF モデルカード更新 x3 |
| M1-4 | HF Collection「piper-plus: Multilingual Neural TTS」作成 | [詳細](tickets/M1/M1-04.md) | モデル配布 | 0.5h | M1-3 | HF Collection |
| M1-5 | tsukuyomi-chan にサンプル音声 wav 追加 (6言語) | [詳細](tickets/M1/M1-05.md) | モデル配布 | 0.5d | なし | samples/*.wav x6 |
| M1-6 | 元祖 Piper との非互換性説明文を全モデルカードに追加 | [詳細](tickets/M1/M1-06.md) | モデル配布 | 0.5d | M1-3 | HF モデルカード更新 |
| M1-7 | ベンチマークスクリプト作成 (`scripts/benchmark.py`) | [詳細](tickets/M1/M1-07.md) | 訴求力 | 1d | なし | scripts/benchmark.py |
| M1-8 | README にベンチマーク比較表追加 (RTF/サイズ/RAM/言語数) | [詳細](tickets/M1/M1-08.md) | 訴求力 | 0.5d | M1-7 | README.md 更新 |
| M1-9 | LLM エコシステム接続ガイド**拡充** | [詳細](tickets/M1/M1-09.md) | エコシステム | 0.5d | なし | docs/guides/ 更新 |
| M1-10 | Ollama + piper-plus docker-compose 作成 | [詳細](tickets/M1/M1-10.md) | エコシステム | 0.5d | なし | docker/ollama-stack/docker-compose.yml |
| M1-11 | endo5501 への upstream C API + Dart FFI 通知 | [詳細](tickets/M1/M1-11.md) | コミュニティ | 0.5h | なし | GitHub Issue コメント |
| M1-12 | Docker Hub 公開 workflow 追加 | [詳細](tickets/M1/M1-12.md) | 配布 | 0.5d | なし | .github/workflows/ 更新 |

**合計工数**: 約 6.5人日

> **M1-1 Python例について:** 高レベル Python API (`PiperPlus` クラス) は M2-4 (v1.13.0) で提供予定。M1 時点の README Python 例はプリビルドバイナリ + 既存 CLI (`piper-tts-plus`) に限定する。
>
> ```bash
> # プリビルドバイナリ (推奨)
> ./piper --download-model tsukuyomi
> ./piper --model tsukuyomi --text "こんにちは" -f hello.wav
>
> # Python (v1.13.0 で高レベル API 提供予定)
> pip install piper-tts-plus
> python -m piper_train.infer_onnx --model /path/to/model.onnx --text "こんにちは" --output-dir .
> ```

> **M1-9 について:** `docs/guides/open-webui-integration.md` が既に存在する。AnythingLLM / LangChain / Ollama セクションの追記が本タスクのスコープ。

### 完了条件 (Definition of Done)

- [ ] README冒頭にバイナリ/Python/npmの3パターン「30秒で試す」が存在する
- [ ] 「Try in Browser」バッジがREADME最上部に表示される
- [ ] HF全モデルが `pipeline_tag: text-to-speech` を持つ
- [ ] HF Collection が作成され、全モデルが含まれている
- [ ] tsukuyomi-chanに6言語のサンプル音声が埋め込まれている
- [ ] `scripts/benchmark.py` が動作し、README上にベンチマーク表がある
- [ ] `docs/guides/` に OpenWebUI / AnythingLLM / LangChain / Ollama の接続手順がある
- [ ] endo5501 のフォークに upstream 対応状況が通知されている
- [ ] Docker Hub に piper-plus 関連イメージが公開されている
- [ ] v1.12.0 としてリリースされている

---

## M2: Developer Experience & Awareness (v1.13.0 - v1.14.0)

**期間**: 2026-04-22 〜 2026-06-22 (2ヶ月)
**テーマ**: 「開発者が自分のアプリに組み込める」+ 「外部に知ってもらう」
**リリース**: v1.13.0 (Python API + CI), v1.14.0 (Wyoming + npm改善)

> **構造:** M2a と M2b は**並列実行可能**。Wyoming は既存 `inference.py` を直接利用するため Python 高レベル API に依存しない。

### M2a: コア開発 + DX (v1.13.0, 4/22 - 5/20)

| # | タスク | チケット | カテゴリ | 工数 | 依存 | 成果物 |
|---|--------|---------|---------|------|------|--------|
| M2-1 | Python 高レベル API (`PiperPlus` クラス) 実装 | [詳細](tickets/M2/M2-01.md) | API設計 | 5d | M1完了 | src/python/piper_plus/api.py |
| M2-2 | `AudioResult` クラス実装 (save/to_bytes/play) | [詳細](tickets/M2/M2-02.md) | API設計 | 1d | M2-1 | src/python/piper_plus/audio.py |
| M2-3 | Python API テスト + ドキュメント | [詳細](tickets/M2/M2-03.md) | API設計 | 2d | M2-2 | tests/, README |
| M2-4 | PyPI `piper-plus` パッケージ公開 (高レベルAPI) | [詳細](tickets/M2/M2-04.md) | API設計 | 0.5d | M2-3 | PyPI piper-plus |
| M2-5 | CI path filter 導入 (dorny/paths-filter) | [詳細](tickets/M2/M2-05.md) | DX | 2d | なし | ci.yml 更新 |
| M2-6 | concurrency group 追加 (全PRトリガーWF) | [詳細](tickets/M2/M2-06.md) | DX | 0.5d | M2-5 | .github/workflows/*.yml |
| M2-7 | PR テンプレート**拡充** (対象コンポーネントチェックリスト追加) | [詳細](tickets/M2/M2-07.md) | DX | 0.25d | なし | .github/PULL_REQUEST_TEMPLATE.md |
| M2-8 | CONTRIBUTING.md 拡充 (全言語テストコマンド + 初PR手順) | [詳細](tickets/M2/M2-08.md) | DX | 1d | なし | CONTRIBUTING.md |
| M2-9 | good first issue ラベル整備 + 初期 Issue 作成 (5件) | [詳細](tickets/M2/M2-09.md) | DX | 0.5d | M2-8 | GitHub Issues |

**合計工数**: 約 12.75人日

> **M2-7 について:** `.github/PULL_REQUEST_TEMPLATE.md` は既に存在し、GPL 依存チェックも含まれている。対象コンポーネント (Python/Rust/C#/C++/Go/WASM/Docker/CI) のチェックリスト追加のみ。

### M2b: エコシステム統合 + 認知度 (v1.14.0, 4/22 - 6/22) ※M2aと並列実行可能

| # | タスク | チケット | カテゴリ | 工数 | 依存 | 成果物 |
|---|--------|---------|---------|------|------|--------|
| M2-10 | Wyoming Protocol アダプタ実装 | [詳細](tickets/M2/M2-10.md) | エコシステム | 5d | なし | docker/wyoming-piper-plus/ |
| M2-11 | Wyoming Dockerfile + docker-compose | [詳細](tickets/M2/M2-11.md) | エコシステム | 1d | M2-10 | Dockerfile, docker-compose.yml |
| M2-12 | Wyoming HA 統合テスト + ドキュメント | [詳細](tickets/M2/M2-12.md) | エコシステム | 2d | M2-11 | docs/guides/home-assistant.md |
| M2-13 | npm README 改善 (importmap サンプル + バリアント案内) | [詳細](tickets/M2/M2-13.md) | ブラウザ体験 | 1d | なし | src/wasm/openjtalk-web/README.npm.md |
| M2-14 | webpack/Vite WASM 配置ガイド | [詳細](tickets/M2/M2-14.md) | ブラウザ体験 | 1d | なし | docs/guides/wasm-bundler.md |
| M2-15 | Qiita 入門記事執筆・投稿 | [詳細](tickets/M2/M2-15.md) | 認知度 | 1d | M1完了 | Qiita 記事 |
| M2-16 | Zenn 技術記事執筆・投稿 (G2P設計 or WASM) | [詳細](tickets/M2/M2-16.md) | 認知度 | 1d | M1完了 | Zenn 記事 |
| M2-17 | Show HN 投稿 | [詳細](tickets/M2/M2-17.md) | 認知度 | 0.5d | M1完了 | HN 投稿 |
| M2-18 | Reddit 投稿 (r/selfhosted, r/LocalLLaMA) | [詳細](tickets/M2/M2-18.md) | 認知度 | 0.5d | M2-17 | Reddit 投稿 x2 |
| M2-19 | Rust API ergonomics 改善 (`SynthesisParams` + Default) | [詳細](tickets/M2/M2-19.md) | API設計 | 2d | なし | src/rust/piper-core/ |
| M2-20 | Rust piper-core SV phonemizer 追加 | [詳細](tickets/M2/M2-20.md) | 技術負債 | 1d | なし | src/rust/piper-core/src/phonemize/ |
| M2-21 | yeager (SV) へのフィードバック依頼 | [詳細](tickets/M2/M2-21.md) | コミュニティ | 0.25d | M2-20 | GitHub Issue/Discussion コメント |

**合計工数**: 約 16.25人日
**M2全体合計**: 約 29人日

### 完了条件 (Definition of Done)

- [ ] `from piper_plus import PiperPlus; tts = PiperPlus("tsukuyomi"); tts.tts_to_file("こんにちは", "out.wav")` が動作する
- [ ] PyPI に `piper-plus` 高レベルAPIパッケージが公開されている
- [ ] Wyoming アダプタが HA から TTS プロバイダーとして認識される
- [ ] CI PRで変更のない言語のテストがスキップされる (path filter動作確認)
- [ ] PRテンプレートに対象コンポーネントチェックリストがある
- [ ] CONTRIBUTING.md に全6言語のテスト実行手順がある
- [ ] npm README に HTML 完結サンプルが存在する
- [ ] Qiita + Zenn に各1本以上の記事が公開されている
- [ ] Show HN に投稿されている
- [ ] Rust `SynthesisParams::default()` パターンが使用可能
- [ ] Rust piper-core で SV phonemizer が動作する
- [ ] yeager に SV 関連のフィードバック依頼が送信されている
- [ ] v1.13.0 + v1.14.0 としてリリースされている

### M1 → M2 依存関係

```
M1-1 (README) ──→ M2-15,16,17,18 (認知度施策の前提)
M1-7,8 (ベンチマーク) ──→ M2-17 (HN投稿の訴求材料)
M2-20 (SV phonemizer) ──→ M2-21 (yeager フォローアップ)
```

> **Note:** M2-10 (Wyoming) は M2-1 (Python API) に依存しない。既存 `inference.py` の合成ロジックを直接利用する。これにより M2a と M2b を並列実行可能。

---

## M3: Quality & Ecosystem (v2.0.0 - v2.1.0)

**期間**: 2026-06-22 〜 2026-12-31 (約6ヶ月)
**テーマ**: 「音質で選ばれる」+「エコシステムが自走する」
**リリース**: v2.0.0 (Voice Cloning + VITS2), v2.1.0 (モデルZoo + Unity)

### M3a: 音質・コア機能 (6/22 - 10/31)

| # | タスク | チケット | カテゴリ | 工数 | 依存 | リスク | 成果物 |
|---|--------|---------|---------|------|------|--------|--------|
| M3-1 | Speaker Encoder (ECAPA-TDNN) ONNX 統合 | [詳細](tickets/M3/M3-01.md) | Voice Cloning | 10d | M2完了 | 中: モデルサイズ増大 | src/python/piper_train/speaker_encoder/ |
| **GATE** | **Go/No-Go 判定**: Speaker Encoder 品質検証 | [詳細](tickets/M3/M3-GATE.md) | 判定 | 2d | M3-1 | — | 判定レポート |
| M3-2 | SynthesizerTrn に `speaker_embedding` 入力パス追加 | [詳細](tickets/M3/M3-02.md) | Voice Cloning | 5d | GATE通過 | 高: 既存モデル非互換 | vits/models.py |
| M3-5 | VITS2 adversarial DP アップグレード | [詳細](tickets/M3/M3-05.md) | 音質 | 7d | なし | 中: 学習不安定リスク | vits/models.py |
| M3-3 | Voice Cloning 対応モデル学習 (VITS2ベース) | [詳細](tickets/M3/M3-03.md) | Voice Cloning | 10d | M3-2, M3-5 | 高: GPU時間 ~100h | チェックポイント + ONNX |
| M3-4 | Rust/C#/Go/WASM ランタイムに Voice Cloning 統合 | [詳細](tickets/M3/M3-04.md) | Voice Cloning | 10d | M3-3 | 中: 全実装同期必要 | 各ランタイム更新 |
| M3-6 | ZH データ増量 (63K → 150K+) + 再学習 | [詳細](tickets/M3/M3-06.md) | 音質 | 5d | なし | 低 | データセット + ONNX |
| M3-7 | SSML 基本サポート (break, prosody rate/pitch) | [詳細](tickets/M3/M3-07.md) | 機能 | 5d | なし | 低 | phonemize/ 各言語 |
| M3-8 | MOS ベンチマーク実施 + 結果公開 | [詳細](tickets/M3/M3-08.md) | 訴求力 | 3d | M3-3,5 | 低 | docs/benchmark-mos.md |

**合計工数**: 約 72人日 (研究バッファ +17d 含む)

> **Go/No-Go ゲート:** M3-1 完了後、Speaker Encoder 単体で話者類似度 (cosine similarity > 0.85) を検証。不合格の場合:
> - 選択肢A: F5-TTS 方式 (Flow Matching DiT) に切り替え
> - 選択肢B: Voice Cloning を v2.0.0 スコープから外し、v2.1.0 以降に延期
>
> **M3-5 → M3-3 の順序:** VITS2 アーキテクチャで学習した方が Voice Cloning の品質が高い。ただし、VITS2 が遅延する場合は VITS1 ベースで先にプロトタイプし、VITS2 版を後続とする2段階戦略も可。

### M3b: エコシステム拡張 (6/22 - 12/31)

| # | タスク | チケット | カテゴリ | 工数 | 依存 | リスク | 成果物 |
|---|--------|---------|---------|------|------|--------|--------|
| M3-9 | LJSpeech モデル学習 + 公開 (EN, CC0) | [詳細](tickets/M3/M3-09.md) | モデルZoo | 3d | なし | 低 | HF モデル |
| M3-10 | あみたろモデル学習 + 公開 (JA, 商用OK) | [詳細](tickets/M3/M3-10.md) | モデルZoo | 3d | なし | 中: ライセンス確認 | HF モデル |
| M3-11 | HiFi-TTS モデル学習 + 公開 (EN, CC-BY) | [詳細](tickets/M3/M3-11.md) | モデルZoo | 3d | なし | 低 | HF モデル |
| M3-12 | SIWIS モデル学習 + 公開 (FR, CC-BY) | [詳細](tickets/M3/M3-12.md) | モデルZoo | 3d | なし | 低 | HF モデル |
| M3-13 | 韓国語ベースモデル学習 (KO G2P実装済み) | [詳細](tickets/M3/M3-13.md) | モデルZoo | 5d | なし | 中: KOデータ選定 | HF モデル |
| M3-14 | モデル投稿ガイド + Issue テンプレート | [詳細](tickets/M3/M3-14.md) | モデルZoo | 1d | M3-9 | 低 | CONTRIBUTING_MODELS.md |
| M3-15 | Unity UPM パッケージ作成 (P/Invoke + AudioClip) | [詳細](tickets/M3/M3-15.md) | ゲーム統合 | 7d | なし | 中: iOS/Android CI | com.piper-plus.tts/ |
| M3-16 | Unity サンプルシーン + ドキュメント | [詳細](tickets/M3/M3-16.md) | ゲーム統合 | 3d | M3-15 | 低 | Samples~/ |
| M3-17 | iOS/Android ビルド CI 追加 | [詳細](tickets/M3/M3-17.md) | ゲーム統合 | 3d | M3-15 | 中: クロスコンパイル | release-shared-lib.yml |
| M3-18 | piper_plus_voices.json カタログ拡充 | [詳細](tickets/M3/M3-18.md) | モデルZoo | 1d | M3-9〜13 | 低 | voices.json 更新 |
| M3-19 | Awesome TTS / Awesome Rust 等への登録 | [詳細](tickets/M3/M3-19.md) | 認知度 | 0.5d | M2完了 | 低 | 外部PRs |

**合計工数**: 約 33人日
**M3全体合計**: 約 105人日 (M3a 72d + M3b 33d)

### v2.0.0 破壊的変更 (予定)

| 変更 | 影響範囲 | 既存モデル互換 |
|------|---------|-------------|
| `speaker_embedding` 入力テンソル追加 | ランタイム API | 影響なし (Optional入力) |
| VITS2 アーキテクチャ変更 | 新規学習モデルのみ | **既存 VITS ONNX モデルは v2.0.0 ランタイムでも動作** |
| Rust `synthesize_text()` → `SynthesisParams` API 変更 | Rust ユーザー | v1.14.0 で `#[deprecated]`、v2.0.0 で削除 |

> **Note:** 既存の VITS ONNX モデルは v2.0.0 ランタイムでも動作する (後方互換)。破壊的変更はランタイム API レベルのみ。VITS2 は新規学習モデル専用。

### 完了条件 (Definition of Done)

- [ ] 3-5秒の参照音声から声質クローンが動作する (Python + 1ランタイム以上)
- [ ] MOS ベンチマークが公開され、v1.x 比で改善が示されている
- [ ] SSML `<break>` と `<prosody>` が全言語で動作する
- [ ] HF に 8モデル以上が公開されている (現在3 → 8+)
- [ ] 韓国語ベースモデルが `--list-models ko` で利用可能
- [ ] Unity UPM パッケージが OpenUPM or git URL でインストール可能
- [ ] コミュニティから投稿されたモデルが1つ以上マージされている
- [ ] v2.0.0 + v2.1.0 としてリリースされている

### M2 → M3 依存関係

```
M2-1 (Python API) ──→ M3-1 (Speaker Encoder の Python 統合基盤)
M2-19 (Rust API) ──→ M3-4 (Voice Cloning の Rust 統合)
M2-8 (CONTRIBUTING) ──→ M3-14 (モデル投稿ガイドの基盤)
M3-1 (Speaker Encoder) ──→ GATE ──→ M3-2 (SynthesizerTrn拡張)
M3-5 (VITS2) ──→ M3-3 (Voice Cloning 学習はVITS2ベース)
```

---

## リリースバージョン計画

| バージョン | 予定日 | マイルストーン | 主要変更 |
|-----------|--------|-------------|---------|
| **v1.12.0** | 2026-04-22 | M1 | README刷新, HF整備, ベンチマーク, LLMガイド, Docker Hub |
| **v1.13.0** | 2026-05-20 | M2a | Python高レベルAPI, CI最適化, CONTRIBUTING拡充 |
| **v1.14.0** | 2026-06-22 | M2b | Wyoming Protocol, npm改善, Rust API改善 (`SynthesisParams` deprecated) |
| **v2.0.0** | 2026-10-31 | M3a | Voice Cloning, VITS2, SSML, MOS公開, Rust API breaking change |
| **v2.1.0** | 2026-12-31 | M3b | モデルZoo拡充, Unity UPM, KOモデル |

---

## クリティカルパス

```
M1-1 (README) ─┬─→ M2-15〜18 (認知度) ──→ Stars/DL KPI達成
               │
M1-7 (ベンチマーク) ─→ M2-17 (HN投稿) ──→ 英語圏認知
               │
M2-1 (Python API) ─→ M2-4 (PyPI公開) ─→ M3-1 (Speaker Encoder)
               │                          │
               │                          ↓
               │                   GATE (品質判定) ←── 退路あり
               │                          │
               │                          ↓
               │                   M3-2 (SynthesizerTrn拡張)
               │                          │
               │         M3-5 (VITS2) ──→ M3-3 (再学習) ←── ボトルネック: GPU ~100h
               │                          │
               │                          ↓
               │                   M3-4 (全ランタイム統合) → v2.0.0
               │
M2-10 (Wyoming) ─→ M2-12 (HA統合テスト) ─→ HA コミュニティ認知
  ↑ M2-1に依存しない (inference.py直接利用)
```

**ボトルネック**: M3-3 (Voice Cloning モデル再学習) は GPU 約100時間が必要。M3-2 + M3-5 完了後すぐに開始する必要がある。

**退路**: GATE 不合格時は Voice Cloning を v2.0.0 から除外可能。その場合 v2.0.0 は VITS2 + SSML + Rust API breaking change のみ。

---

## リスクマトリクス

| # | リスク | 確率 | インパクト | スコア | 軽減策 |
|---|--------|------|----------|--------|--------|
| R1 | Voice Cloning の音質が実用水準に達しない | 中 | 高 | **高** | Go/No-Go ゲートで早期判断。不合格なら F5-TTS 方式に切り替え or スコープ除外 |
| R2 | HN/Reddit 投稿が注目されない | 中 | 中 | **中** | 投稿タイミング最適化 (火-木 8-10AM ET)。投稿後5分以内に詳細コメント。複数回投稿戦略 |
| R3 | Python API の PyPI 名前衝突 | 低 | 高 | **中** | `piper-plus` は既に PyPI 確保済みか事前確認。代替名: `piper-tts-plus` |
| R4 | GPU リソース不足で M3 学習遅延 | 中 | 高 | **高** | クラウド GPU (Lambda, Vast.ai) を予備確保。モデルZoo学習は並列化可能 |
| R5 | Wyoming Protocol の仕様変更 | 低 | 中 | **低** | wyoming>=1.5 にピン。HA Core リリースノート監視 |
| R6 | 外部コントリビューター増加に伴うレビュー負荷 | 低 | 中 | **低** | good first issue + 明確な CONTRIBUTING で品質担保。自動CIでゲート |
| R7 | Unity iOS/Android ビルドの CI 複雑化 | 中 | 中 | **中** | まず macOS/Windows/Linux のみ。iOS/Android は v2.1.0 以降に後回し可能 |
| R8 | VITS2 アップグレードで既存モデル非互換 | 中 | 高 | **高** | VITS2 は新規学習のみ対象。既存 VITS モデルのランタイム互換は維持 |
| R9 | M3 工数が研究要素で膨張 | 高 | 中 | **高** | Go/No-Go ゲートで早期判断。Voice Cloning をスコープから外す退路を確保。M3a に +30% バッファ済み |

---

## 並行ワークストリーム

M2 以降は複数ストリームを並行実行可能:

```
M2 並列構造:
  M2a (Python API + DX) ──┐
                          ├──→ 認知度施策 (M2-15〜18, 5月下旬)
  M2b (Wyoming + npm)  ──┘

M3 並列構造:
  Stream A (コア音質):    VITS2 ──→ Voice Cloning学習 → 全ランタイム統合
  Stream B (Voice Cloning前段): Speaker Encoder → GATE → SynthesizerTrn拡張
  Stream C (機能):        SSML + ZHデータ増量 (独立)
  Stream D (モデルZoo):   LJSpeech → あみたろ → HiFi → SIWIS → KO (GPU並列学習可)
  Stream E (エコシステム): Unity UPM → サンプルシーン → iOS/Android CI
  Stream F (認知度):      Awesome リスト登録 + MOS公開
```

**Stream A + B がクリティカルパス。Stream C-F は独立して進行可能。**

---

## 調査ソース

- `docs/v1.11.0-market-reaction-and-improvements-2026-04.md` Part 1-5 全内容
- `docs/ecosystem-investigation-2026-04.md` 提言チェックリスト
- GitHub API (ayutaz/piper-plus) リポジトリ統計
- 競合プロジェクト Stars/DL 推移 (Kokoro, F5-TTS, Coqui)
- 既存成果物確認: `.github/PULL_REQUEST_TEMPLATE.md`, `docs/guides/open-webui-integration.md`, `scripts/benchmark_streaming_comparison.py`
