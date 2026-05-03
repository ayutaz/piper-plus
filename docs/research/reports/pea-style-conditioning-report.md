# Style Vector Conditioning + PE-A Emotion Loss 最終レポート (template)

> **Status (2026-04-23)**: このレポートは Phase 0〜5 (スクリプト + テスト)
> の完了時点のテンプレートです。実機 GPU 2 日の fine-tune 学習は別セッ
> ションで実施します。学習完了後、第 3/4/5 章の **TODO** 欄を実測値で埋め、
> Phase 5 の採択判定 (§6) を確定させてください。

## 1. 概要

piper-plus の多言語 TTS (6 言語: ja/en/zh/es/fr/pt) に、PE-AV (Meta
Perception Encoder Audio-Visual) 由来の Style Vector Conditioning と
PE-A Emotion Loss を追加しました。Fork `yusuke-ai/piper-plus` コミット
`314b3355` を基礎にしつつ、本家のコーディング規約・CI・ABI 互換性を守
りながら統合したものです。

### 1.1 採択目的

| 既存ポジション | 追加要素 | 保証事項 |
|-------------|---------|---------|
| 軽量・多言語・オフライン | 感情表現 (emotion-conditioned TTS) | モデルサイズ・推論速度は不変 (style_vector_dim=0 で bit-for-bit 後方互換) |

### 1.2 成功基準 (gate)

| 指標 | 基準 | 採択判定 |
|------|-----|---------|
| 英語 SER 精度 | 65% 以上 | TODO (P5-T03 実行後) |
| MOS 自然性 (PESQ/STOI proxy) | PESQ 2.8+, STOI 0.85+ | TODO |
| 多言語 regression | ベース比 PESQ -0.2 以下 | TODO |
| `style_vector_dim=0` 後方互換 | bit-for-bit 一致 | PASS (Phase 1 P1-T06 で検証済み) |

### 1.3 設計判断 (なぜこの構成にしたか)

| 判断 | 採択 | 不採択候補と却下理由 |
|------|------|--------------------|
| Emotion embedding ソース | **PE-AV (Meta)** | wav2vec2-emotion: ライセンス GPL/non-commercial が混在、PE-AV は Apache-2.0 で商用可。/ ESD 自前学習: 6言語 dataset との regression リスク。 |
| 注入箇所 | **VITS 大域条件 `g`** (decoder + flow + DP に伝播) | TextEncoder のみ: emotion がイントネーションに乗りにくい。/ 全層への projection: 学習負荷増、改善幅が不確か。 |
| `style_vector_dim` のデフォルト | **`0` (無効化)** | デフォルト有効: 既存 ckpt が再学習なしに動かなくなる。 / `--style-vector-dim` 指定必須: ABI 互換性でランタイム実装が複雑化。 |
| ONNX 入力の Optional 表現 | **mask パターン** (`style_vector` + `style_vector_mask` の2 入力) | Optional 入力 (None): ONNX Runtime の旧バージョン非対応。/ 別モデル分岐: モデルファイル数 2 倍。 |
| PE-A loss 算出位置 | **`training_step_g` 内** (warmup + every_n_steps + NaN guard 付き) | callback hook: lightning の grad accumulation と整合しない。/ 別 module: GAN loss と重み付けが疎結合化。 |
| 6 ランタイム横断仕様 | **`docs/spec/style-vector-contract.toml` で固定** | 実装ごとにドキュメント: divergence のリスク、cross-runtime test (P2-T08) のソースが不在になる。 |
| C++ ABI 維持 | **`_reserved[5]` → `_reserved[3]` + style_vector 2 フィールド** | フィールド純粋追加: `sizeof(PiperPlusSynthOptions)` が変わり Dart FFI / Godot GDExtension の既存ビルド互換性が壊れる。 |
| Optional dep の管理 | **`pyproject.toml` の `[pea]` extra** | デフォルト依存: 大量の transitive deps (torchcodec/decord/opencv-python/tiktoken) が CI を肥大化させる。 |

## 2. 実装の流れ (Phase 0〜5)

### 2.1 Phase 0 — facebook/pe-av-small PoC

- Option A (`AutoModel.from_pretrained` + `trust_remote_code=True`) は
  transformers 4.57.6 でロード **不可** (`model_type=pe_audio_video` が
  `CONFIG_MAPPING` に未登録)。
- Option B (`facebookresearch/perception_models` 手動 import) へ切替必須。
- インストール: `uv sync --extra pea` (`pyproject.toml` の
  `[project.optional-dependencies].pea` で git 依存を管理)。
- ライセンス: `LICENSE.PE` が **Apache-2.0** (商用可、MIT 互換)。
- 詳細: `docs/research/implementation-plan/tickets/phase-0/P0-T01.md §10`

### 2.2 Phase 1 — Style Vector Conditioning 学習側統合

- 修正ファイル: `models.py`, `dataset.py`, `lightning.py`, `commons.py`,
  `__main__.py`, `infer.py` (6 ファイル、Phase 1 全 7 チケット)
- CLI: `--style-vector-dim` (default 0), `--style-condition-dropout`,
  `--style-condition-mode`, `--load_weights_from_checkpoint` (shape-aware)
- テスト: Unit 11 件 PASS + 既存 875 件リグレッションなし

### 2.3 Phase 2 — ONNX + 6 ランタイム対応

- mask パターンで ONNX に `style_vector` + `style_vector_mask` を追加、
  `metadata_props["style_vector_dim"]` で dim を伝搬。
- 各ランタイムに `--style-vector PATH` / `--style-vector-inline` を統一実装。
- `docs/spec/style-vector-contract.toml` で 6 ランタイム共通仕様を固定。
- テスト: spec 整合性 24 件 PASS (Python) + 6 件 PASS (WASM/JS)。

### 2.4 Phase 3 — Style Bank 生成ツール

- `build_pea_style_bank.py` (~651 行): 感情音声 → PE-A embedding →
  centroid (.npz) を生成。
- `inject_style_labels.py`: 既存 dataset.jsonl に `style_vector_path` /
  `emotion` を注入。
- `validate_style_bank.py`: L2 ノルム・次元整合・global/emotion 整合
  を検証。
- テスト: 58 件 PASS (モック PE-A で完結)。

### 2.5 Phase 4 — PE-A Emotion Loss 学習側統合

- `_compute_pea_emotion_loss()` を 3 項合成 (direction + centroid + margin)
  で実装。fork の loss 定義を忠実に再現。
- `training_step_g` で warmup (2,000 steps) + `every_n_steps=4` + NaN guard。
- CLI 9 個 (`--pea-emotion-*`): `--pea-emotion-enabled` は fork 方式 (3 weight
  のいずれか > 0 で自動有効) に合わせて追加しない。
- テスト: 20 件 PASS + 既存 879 件リグレッションなし。

### 2.6 Phase 5 — Fine-tune 実験 (テンプレート)

- データセット準備: `prepare_emotion_finetune_dataset.py` (CREMA-D 7,442
  発話 → piper-train 形式、Phase 3 の `.npy` を参照)。
- 学習 driver: `scripts/run_crema_d_finetune.sh` (stage5a / stage5b)。
- 評価ハーネス: `tools/benchmark/evaluate_emotion_finetune.py` (SER + MOS
  + multilingual regression + success gate)。
- Runtime 検証: `scripts/export_and_verify_emotion_runtimes.sh` (Python +
  Rust で MD5 取得、他 4 runtime は build 後の手動確認)。

## 3. 実験結果 (TODO: 学習完了後に埋める)

### 3.1 Stage 5a — Style conditioning only

| 項目 | 値 |
|------|-----|
| 学習日時 | TODO |
| GPU 時間 | TODO (想定: 約 2 日) |
| 最終 epoch | TODO |
| 最終 checkpoint | TODO |
| 生成 ONNX | TODO |

### 3.2 Stage 5b — Style + PE-A loss (optional)

| 項目 | 値 |
|------|-----|
| 実施判定 | TODO (Stage 5a 評価後) |

## 4. 評価結果 (TODO: 評価完了後に埋める)

### 4.1 SER (Speech Emotion Recognition)

| Emotion | accuracy | sample count |
|---------|---------|--------------|
| angry | TODO | TODO |
| disgusted | TODO | TODO |
| fearful | TODO | TODO |
| happy | TODO | TODO |
| neutral | TODO | TODO |
| sad | TODO | TODO |
| **top-1 total** | TODO | TODO |

### 4.2 MOS (PESQ / STOI proxy)

| 項目 | 値 |
|------|-----|
| PESQ mean | TODO |
| PESQ median | TODO |
| STOI mean | TODO |
| STOI median | TODO |

### 4.3 多言語 regression

| 言語 | PESQ (base) | PESQ (ft) | drop |
|------|-------------|-----------|------|
| ja | TODO | TODO | TODO |
| zh | TODO | TODO | TODO |
| es | TODO | TODO | TODO |
| fr | TODO | TODO | TODO |
| pt | TODO | TODO | TODO |

## 5. Cross-runtime 動作確認 (TODO)

| ランタイム | MD5 | 結果 |
|-----------|-----|------|
| Python (infer_onnx.py) | TODO | TODO |
| Rust (piper-plus-cli) | TODO | TODO |
| C++ (piper_plus) | TODO (build 要) | TODO |
| C# (PiperPlus.Cli) | TODO (dotnet build 要) | TODO |
| Go (piper-plus) | TODO (go build 要) | TODO |
| WASM/JS | TODO (browser fixture 要) | TODO |

全ランタイムで同一 MD5 が得られれば Phase 2 の契約整合は **実機検証**
完了と判定。

## 6. 採否判定 (TODO: §3/4/5 結果確定後)

### 6.1 成功基準チェック

| 基準 | 結果 | コメント |
|------|------|---------|
| SER ≥ 65% | TODO | TODO |
| MOS PESQ ≥ 2.8 | TODO | TODO |
| MOS STOI ≥ 0.85 | TODO | TODO |
| 多言語 drop ≤ 0.2 | TODO | TODO |
| 後方互換 (dim=0) | PASS | Phase 1 P1-T06 で確認済み |

### 6.2 判定

- [ ] **採択**: 上記すべて PASS、`ayousanz/piper-plus-crema-d-emotion`
      として HF Hub リリース、CLAUDE.md に追記
- [ ] **条件付き採択**: SER のみ未達 → Stage 5b (PE-A loss) へ
- [ ] **不採択**: MOS または多言語 regression で gate 割れ → ESD
      or ベース再学習シナリオへ移行

## 7. 学び

### 7.1 実装中の知見

- Option A (AutoModel) は **動作しない**: perception_models の直 import
  が必須。Phase 0 で判明した時点で `pea_loader.py` に 2 段 fallback を組
  み込んだ。
- fork の loss 定義 (direction 3 項) は仕様として固定価値が高い: 論
  文には詳述されていないため、fork の `_compute_pea_emotion_loss` を
  忠実にコピーした上で Unit テストで数値的性質を固定。
- 6 ランタイム同時対応で最もコストが高いのは C++ の ABI 互換: Dart FFI /
  Godot GDExtension が既存の `PiperPlusSynthOptions` サイズに依存する
  ため `_reserved[5]` → `_reserved[3]` と `style_vector` 2 フィールド追
  加で `sizeof` を維持した (P2-T03)。

### 7.2 次フェーズで修正したい点

- `style_vector_dim` を ONNX graph の input shape にハードコードしない
  オプション (全 runtime が metadata_props 経由で統一的に読む設計に寄せる)。
- `build_pea_style_bank.py` のバッチ推論 OOM 対策 (大規模 corpus で検証
  したときに顕在化する可能性)。
- 評価ハーネスの SER inference loop を実モデル + 実データで wire する。

## 8. CLAUDE.md 更新ガイド (学習完了後に実施)

学習・評価結果が確定し、成功判定が出た場合、CLAUDE.md に以下を追記:

```markdown
## PE-AV Emotion 対応モデル (CREMA-D fine-tune)

6lang ベースモデル (571 話者, 75 epoch) をベースとして、CREMA-D (7,442
発話, 91 話者, 6 感情, 英語) を転移学習したモデル。`--style-vector-dim 256`
+ PE-A loss で感情表現を獲得。

| 項目 | 値 |
|------|-----|
| データセット | /data/piper/dataset-crema-d-emotion/ |
| 発話数 | 7,442 |
| 話者数 | 91 |
| 感情 | 6 (ANG/DIS/FEA/HAP/NEU/SAD) |
| 状態 | 200 epoch 完了 (YYYY-MM-DD)、epoch=NNN-step=SSS.ckpt |

学習コマンド: `scripts/run_crema_d_finetune.sh stage5a`

推論例 (style_vector=angry centroid):
...

生成 ONNX: /data/piper/output-emotion-fine-tune-v1/emotion-v1.onnx
HuggingFace Hub: ayousanz/piper-plus-crema-d-emotion
```

また、「学習済みモデル」テーブルに以下を追加:

```markdown
| **CREMA-D Emotion v1** | `/data/piper/output-emotion-fine-tune-v1/emotion-v1.onnx` | 200 epoch 完了 (YYYY-MM-DD) -- style_vector_dim=256、Phase 5 採択基準 PASS |
```

## 9. 関連資料

- 前提調査: `docs/research/peav-style-conditioning.md`
- 実装計画: `docs/research/implementation-plan/README.md`
- 契約書: `docs/spec/style-vector-contract.toml`
- チケット: `docs/research/implementation-plan/tickets/` (32 件)
- Fork: https://github.com/yusuke-ai/piper-plus/commit/314b3355
- HF Hub (PE-AV): https://huggingface.co/facebook/pe-av-small
- perception_models: https://github.com/facebookresearch/perception_models
