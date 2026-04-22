# Style Vector Conditioning + PE-A Emotion Loss 調査レポート

**調査日**: 2026-04-22
**調査対象 fork**: [`yusuke-ai/piper-plus`](https://github.com/yusuke-ai/piper-plus) — branch `feature/2026-04-14-2312-peav-style-conditioning`
**実装者**: `mera-chan[bot]` (AIエージェント)
**PR状況**: 本家 (`ayutaz/piper-plus`) 未提出

---

## 1. TL;DR

fork に、VITS にスタイルベクトル条件付け (style vector conditioning) と知覚感情損失 (PE-A emotion loss) を追加する大規模パッチが存在する。3コミット、変更 6 ファイル、約 500 行追加。既存モデル・既存データセットは `style_vector_dim=0` の既定値により **完全後方互換** で、追加機能は opt-in。ただし取り込みには以下の未解決事項がある:

- **ONNX エクスポート側が未対応** — fork 側でも `export_onnx.py` は変更なし。機能を使ったチェックポイントを ONNX 化しても style_vector は機能しない
- **PE-A style bank (.npz) 生成ツールが fork に同梱されていない** — 学習データとして emotion_centroids を事前計算する必要があるが、その生成スクリプトが見当たらない
- **C++/Rust/C#/Go/JS/WASM ランタイム全てで style_vector 入力追加が必要** — 既存の `speaker_embedding` のマスクパターンを踏襲する形の拡張になる

**推奨アクション**: 取り込むなら段階的 (Phase 1: feature flag で学習側のみ → Phase 2: ONNX + ランタイム対応 → Phase 3: style bank 生成ツール)。取り込まないなら、yusuke-ai 側 (kizuna-intelligence プロジェクト) との協業モデルを模索。

---

## 2. 対象コミット

| # | SHA | 日付 | 目的 |
|---|-----|-----|------|
| 1 | `b9e98236` | 2026-04-16 | feat: style vector conditioning + PE-A emotion loss を追加 (メインコミット) |
| 2 | `3afe266c` | 2026-04-16 | Restrict style conditioning to global mode (text モード一時削除) |
| 3 | `314b3355` | 2026-04-17 | Restore stable text style conditioning (text モード復活 + 安定化) |

### 変更ファイル (コミット b9e98236、最大コミット)

| ファイル | +行 | -行 | 主な変更 |
|---------|-----|-----|---------|
| `src/python/piper_train/vits/lightning.py` | 291 | 1 | PE-A emotion loss 初期化・計算、training_step への組込、CLI |
| `src/python/piper_train/vits/models.py` | 126 | 6 | `TextEncoder`/`SynthesizerTrn` に style 経路追加 |
| `src/python/piper_train/infer.py` | 65 | 7 | style_vector ロード・推論時注入 |
| `src/python/piper_train/__main__.py` | 49 | 5 | `--load_weights_from_checkpoint` 追加、checkpoint ロード再構築 |
| `src/python/piper_train/vits/dataset.py` | 43 | 0 | `Utterance.style_vector_path` / `emotion`、batch collator 拡張 |
| `src/python/piper_train/vits/commons.py` | 3 | 1 | `slice_segments()` を任意 shape に対応 |

**合計**: +577 / -20

---

## 3. アーキテクチャ (models.py)

### 3.1 2 モード設計 (最終形: 314b3355)

Style vector は **global モード** / **text モード** のどちらかに投入される (排他的選択):

```
                           style_vector [B, style_vector_dim]
                                        │
                  ┌─────────────────────┴────────────────────┐
                  │ global mode                   text mode  │
                  ▼                                          ▼
        style_proj (Sequential)                    style_proj (Linear)
        [style_dim → gin_ch → SiLU                  [style_dim → hidden_ch]
         → gin_ch]                                        │
                  │                                       │ +
                  ▼                                       ▼
   g = g + style_g  ────► 既存 global            x = emb(x)*sqrt(h) + style_emb
   (speaker/lang と加算)                          (TextEncoder 入力)
                  │                                       │
                  ▼                                       ▼
    decoder / flow / DP                           encoder → m_p, logs_p
```

### 3.2 主な変更箇所 (fork 側行番号、コミット 314b3355 時点)

**TextEncoder.__init__** (`models.py:186-230`)
- 新規パラメータ: `style_vector_dim: int = 0`, `style_condition_dropout: float = 0.0`
- `style_proj: nn.Linear | None` をゼロ初期化 (weight/bias ともに)
  → 学習開始時は恒等的に「何もしない」ため既存モデルと等価

**TextEncoder._style_embedding** (新規メソッド, `models.py:232-258`)
- None 入力はゼロテンソルにフォールバック
- `training` かつ `dropout > 0` のみバッチ単位で確率的ゼロマスク
- 返り値は `[B, 1, hidden_channels]` (token 次元 broadcast)

**TextEncoder.forward** (`models.py:260-273`)
```python
def forward(self, x, x_lengths, g=None, style_vector=None):
    x = self.emb(x)  # [B, T, H]
    style_emb = self._style_embedding(style_vector, ...)
    if style_emb is not None:
        x = x + style_emb              # ← scaling 前に加算しない (b9e98236)
    x = x * math.sqrt(self.hidden_channels)  # ← scaling は加算後 (314b3355 で修正)
    ...
```
**注**: b9e98236 では scaling 前に加算していたが、314b3355 で scaling 後に変更。コメント「PE-A emotion vectors can be intentionally amplified; scaling by sqrt(hidden_channels) destabilizes duration」から、推論時のスタイル強調との相性を考慮した修正と推測。

**SynthesizerTrn.__init__** (`models.py:821-940`)
- 新規パラメータ: `style_vector_dim`, `style_condition_dropout`, `style_condition_mode: str = "global"`
- `style_condition_mode` は `{"global", "text"}` 以外で `ValueError`
- Global モード時のみ `style_proj = nn.Sequential(Linear, SiLU, Linear)` を生成 (`gin_channels <= 0` の場合はエラー)
- Text モード時は TextEncoder に `style_vector_dim` を伝播し、SynthesizerTrn 側の `style_proj` は `None`

**SynthesizerTrn._add_style_condition** (`models.py:942-976`)
- Global モード専用。`style_proj` 通過後、gin_channels 次元で既存 `g` に加算
- `g is None` の場合は style_g をそのまま global condition として採用

**SynthesizerTrn.forward / infer** (`models.py:1064-1078, 1219-1232`)
- `style_condition_mode == "global"` で `g = _add_style_condition(g, style_vector, ...)`
- 否 (text) で `text_style_vector = style_vector` を TextEncoder へ転送

### 3.3 3 コミットの設計変遷

| 項目 | b9e98236 | 3afe266c | 314b3355 |
|------|----------|----------|----------|
| TextEncoder style_proj | 実装 | **削除** | 再実装 |
| SynthesizerTrn style_proj | 実装 (2層 MLP) | あり | あり |
| `style_condition_mode` パラメータ | あり | **なし** (global 固定) | あり |
| Scaling 順序 (TextEncoder) | 加算 → sqrt | — | sqrt → 加算 **(修正)** |

**解釈**: 最初に両モード実装 → text モードで不安定性 → 一度 global のみに restrict → scaling 順序などを修正して text モードを安定化し再投入、という試行錯誤の経緯。

### 3.4 後方互換性

全ての新規パラメータは既定値 `0` / `0.0` / `"global"`。これらの既定値では:
- `style_proj = None` (TextEncoder/SynthesizerTrn 両方)
- Forward pass で style 系演算は全て `if ... is None: return` で skip
- ゼロ初期化されているため、ダミーで有効化してもロス増加なし

**結論**: 既存チェックポイントは strict load 可能で、forward 出力は完全に同一。

---

## 4. PE-A Emotion Loss (lightning.py)

### 4.1 PE-A とは

**推測**: "PE-AV" = Meta の **Perception Encoder (Audio-Visual)** の略。`facebook/pe-av-small` を HuggingFace Hub から読み込み、内部で DAC (Discrete Audio Codec) を経由して低次元埋め込みを抽出する。

**公式ドキュメント等での定義は fork 側でも明示されておらず**、原理的には「知覚ベースの特徴空間 (perceptual feature space) 上で、生成音声を目標感情セントロイドに引き寄せる」ための補助ロス。

### 4.2 損失の定式化

3 項合成:

```
L_PEA = c_dir · L_dir + c_centroid · L_centroid + c_margin · L_margin

L_dir      = 1 − cos( (ẑ − ḡ), (c_e − ḡ) )         # 方向ベクトルの cosine
L_centroid = 1 − cos( ẑ, c_e )                       # セントロイド引き寄せ
L_margin   = ReLU( margin + max_{j≠e}(sim_j) − sim_e ) # クラス間マージン
```

記号:
- `ẑ`: PE-A で抽出・L2正規化された生成音声埋め込み
- `c_e`: バッチサンプルのターゲット感情セントロイド
- `ḡ`: グローバル中心 (全感情の平均、style bank に保存)
- `sim_j`: `cos(ẑ, c_j)` (全感情 j に対するコサイン類似度)

### 4.3 実装フロー (`lightning.py:280-375` 付近)

**初期化** (`_init_pea_emotion_loss`):
- `pea_emotion_style_bank` (.npz) から `emotion_names: list[str]`, `emotion_centroids: ndarray[N, D]`, `global_centroid: ndarray[D]` を読み込み
- 全セントロイドを `F.normalize()` で事前正規化 (buffer 登録)
- `facebook/pe-av-small` は遅延ロード (最初の training_step で `_ensure_pea_emotion_model()`)

**計算** (`_compute_pea_emotion_loss`):
1. `batch.emotions` (list[str]) を index に変換、対応セントロイドを lookup
2. `y_hat` (生成波形) を PE-A が期待する 16kHz にリサンプリング
3. `facebook/pe-av-small` の audio encoder を通して埋め込み抽出
4. L2 正規化 → 3 項計算 → 加重合算
5. `every_n_steps` 対応 (skip-step 時は `None` を返す)

**統合** (`training_step_g` 内, `lightning.py:831-833`):
```python
loss_pea_emotion = self._compute_pea_emotion_loss(y_hat, batch)
if loss_pea_emotion is not None:
    loss_gen_all = loss_gen_all + loss_pea_emotion
```

標準の adversarial + mel + kl + duration loss 合計にただ加算されるだけ。optimizer は通常の generator optimizer に包含。

### 4.4 DAC 勾配制御

`_ensure_pea_emotion_model()` で PE-A モデルのフォワードを `grad_enabled_embedder_forward` でラップし、`cudnn.flags(enabled=False)` で cuDNN を無効化。**意図**: DAC 自体 (離散化レイヤ) は勾配を止めつつ、DAC 後の連続投影層には勾配を通すことで、生成音声に対する差分可能な経路を確保している。

---

## 5. データフロー (dataset.py)

### 5.1 Utterance / Batch の拡張

```python
# Utterance (dataset.py:38-41)
style_vector_path: Path | None = None
emotion: str | None = None

# UtteranceTensors
style_vector: torch.FloatTensor  # [style_vector_dim]
emotion: str

# Batch (dataset.py:70-72)
style_vectors: torch.FloatTensor  # [B, style_vector_dim]
emotions: list[str]
```

### 5.2 ロード経路

**JSON マニフェスト** (推定スキーマ、fork 側の `load_utterance` の変更より):
```json
{
  "phoneme_ids": [...],
  "audio_norm_path": "...",
  "audio_spec_path": "...",
  "speaker_id": 0,
  "language_id": 0,
  "style_vector_path": "style_vectors/utt001.npy",   // ← 新規
  "emotion": "happy"                                 // ← 新規
}
```

- `style_vector_path` は `dataset_dir` 相対で解決
- `__getitem__` で `_load_tensor(style_vector_path).float().view(-1)` で読み込み・フラット化
- 未設定時は `None` → model 側で zeros fallback

### 5.3 BatchCollator

- 全 utterance から `style_vector_dim` を検出 (`dataset.py:308-309`)
- `style_vectors = FloatTensor(B, dim)` を事前割当
- 各サンプルの style_vector を slice-copy (`dataset.py:383-384`)
- `emotion: list[str]` は生のまま collate (PE-A loss 内でセントロイド index に変換)

### 5.4 既存データセットへの影響

`style_vector_path` / `emotion` が **欠落していても通常読み込み可能** (どちらも `None` デフォルト)。したがって:

- `dataset-multilingual-6lang-filtered` — そのまま学習再開可能
- `dataset-tsukuyomi-finetune-6lang` — そのまま fine-tune 可能
- ただし PE-A emotion loss を**有効化**する場合は:
  - 全 utterance に `style_vector_path` を追加
  - 全 utterance に `emotion` ラベルを付与
  - Style bank `.npz` を事前計算 (**生成ツールは fork に未同梱**)

---

## 6. 推論・エクスポートへの影響

### 6.1 `infer.py` (学習内推論 / validation)

- 新規 helper `_style_vector_to_tensor()` — インライン値または `.npy`/`.pt` から style_vector を読み込み
- 推論ループで `style_vector=_style_vector_to_tensor(utt)` を model へ渡す
- GPU 対応追加 (全入力テンソルを device へ)

### 6.2 `__main__.py` (CLI)

新規オプション (style vector / PE-A 専用) — 合計約 13 個:

| オプション | 既定 | 説明 |
|----------|------|------|
| `--style-vector-dim` | 0 | 0 = 無効 |
| `--style-condition-dropout` | 0.0 | バッチ単位ランダム mask |
| `--style-condition-mode` | `"global"` | `"global"` or `"text"` |
| `--pea-emotion-loss-weight` | 0.0 | 方向項 c_dir |
| `--pea-emotion-centroid-weight` | 0.0 | セントロイド項 c_centroid |
| `--pea-emotion-margin-weight` | 0.0 | マージン項 c_margin |
| `--pea-emotion-style-bank` | None | `.npz` パス |
| `--pea-emotion-model-name` | `"facebook/pe-av-small"` | HF モデル ID |
| `--pea-emotion-sample-rate` | 16000 | PE-A 入力 SR |
| `--pea-emotion-loss-every-n-steps` | 1 | Skip-step |
| `--pea-emotion-warmup-steps` | 0 | 開始遅延 |
| `--pea-emotion-margin` | 0.1 | cosine margin |
| `--segment-size` | 8192 | 訓練セグメント長 |

**その他 (style と直接関係ない変更)**:
- `--load_weights_from_checkpoint` — **shape-aware** な部分的 weight loader (新規 embedding レイヤ追加時に既存チェックポイントから互換テンソルのみロード)。style_vector 関連とは独立に単独取り込み可能な有用な機能。
- `save_last=True` → `False` — `top_k` のみ保存、last 保存停止 (debate あり)

### 6.3 ONNX エクスポート (`export_onnx.py`)

**fork 側でも未変更**。影響:
- 現行 `export_onnx.py` は style_vector 入力を dummy input に含めないため、学習で style_vector を使ったチェックポイントをエクスポートしても **style_vector は ONNX グラフで常に None** (機能しない)
- 入力シグネチャは変わらない → 既存 ONNX モデルとの後方互換は維持
- **本家統合時は `export_onnx.py` に style_vector 入力追加 (speaker_embedding のマスクパターンに倣う) が必須**

### 6.4 ランタイム (C++/Rust/C#/Go/JS/WASM)

本家は既に `speaker_embedding` を **optional な float32 テンソル + mask** として 5 ランタイムで実装済み。同じパターンで style_vector も拡張可能:

```c
// 例: src/cpp/piper_plus.h
struct PiperPlusSynthOptions {
    /* 既存 */
    const float *speaker_embedding;
    int32_t speaker_embedding_dim;
    /* 追加案 */
    const float *style_vector;
    int32_t style_vector_dim;
};
```

- `style_vector = NULL, style_vector_dim = 0` がデフォルトで動作継続
- 5 ランタイム全てで同等対応が必要 (1 機能あたり過去実績では 1〜2 週間)

---

## 7. 既存機能との競合・相互作用

| 既存機能 | 競合 | 備考 |
|---------|------|------|
| `gin_channels` (speaker/language embedding) | なし (共存) | Global モードで同じ `g` に加算 |
| `prosody_features` (A1/A2/A3) | なし | Duration predictor 入力に concat される。style_vector と直交 |
| `speaker_embedding` (Voice Cloning) | なし | 推論時のみ。Global モードで `g` 内で共存 |
| `freeze-dp` | なし | DP には style_vector が伝わらない (global も text も) |
| `unify-emb-lang` (シングル多言語) | なし | 別次元のエクスポート時後処理 |
| `WavLMDiscriminator` | なし | Discriminator 系で conditioning パスに無関係 |
| `--resume-from-multispeaker-checkpoint` | 注意 | 既存チェックポイントには `style_proj` パラメータがないが、`style_vector_dim=0` なら `style_proj=None` で無問題 |

---

## 8. 統合コストの概算

| 項目 | 規模感 |
|-----|--------|
| コード追加 (learning side) | +500 行、修正なし |
| テスト追加 | `style_vector_dim=0` レグレッション、text/global 両モード、PE-A enable/disable、dropout 動作 |
| ONNX エクスポート対応 | `export_onnx.py` 拡張 (+50 行程度) — 未実装 |
| 5 ランタイム対応 | C++/Rust/C#/Go/JS/WASM それぞれ数十〜数百行 — 未実装 |
| Style bank 生成ツール | 別スクリプト (emotion centroid 計算) — 未実装 |
| ドキュメント | CLAUDE.md 更新、CLI リファレンス、データセット形式ガイド |

---

## 9. 取り込み戦略 (選択肢)

### 選択肢 A: Feature Flag 段階統合 (推奨)

**Phase 1** — 学習側のみ、`--style-vector-dim 0` がデフォルト・既存動作維持:
- models.py / lightning.py / dataset.py / commons.py / infer.py / __main__.py を一括取り込み
- テスト: style_vector_dim=0 でのレグレッションを重点的に

**Phase 2** — ONNX + ランタイム:
- `export_onnx.py` に style_vector 入力追加
- 5 ランタイムで optional 入力対応 (speaker_embedding と同パターン)

**Phase 3** — データ準備ツール:
- `src/python/piper_train/tools/extract_style_vectors.py` (新規)
- `src/python/piper_train/tools/build_style_bank.py` (新規)

**メリット**: 最小侵襲、既存学習と新規学習が両立、PR 単位の review 負担を分散
**デメリット**: コード複雑度増加、3 PR に分割する運用コスト

### 選択肢 B: ツール先行で機能を後追い

Phase 3 を先に提案して、コミュニティで style bank の有用性を検証してから本体統合判断。
**メリット**: 本体コードに手を入れる前にツールの妥当性が検証できる
**デメリット**: style extraction のための前提 (style_vector_dim > 0 の VITS) が本体にない状態でツールだけあっても使えない

### 選択肢 C: yusuke-ai との協業

CONTRIBUTING_MODELS.md 等の枠組みに従って、style_vector 機能付きチェックポイントを**カスタム拡張**として扱い、本家のコアは触らない。
**メリット**: 本家の複雑度を抑制
**デメリット**: 相互運用性低下、ユーザー採用障壁 (fork と本家で別物になる)

---

## 10. 疑問点・未解決事項

1. **PE-A style bank (.npz) の生成方法** — fork 側に emotion_centroids / global_centroid 計算スクリプトが含まれていない。前提データが存在しない状態では PE-A loss は有効化できない
2. **Text モード再投入の動機** — 3afe266c で一度 restrict してから 314b3355 で復活させた正確な理由が不明 (性能差か、ユースケースか)
3. **Style dropout の目的** — Regularization か、style-free な合成を明示的にサポートするためか
4. **Emotion ラベルの由来** — fork 側の dataset.json でどのフィールドから取得するか明文化されていない。`style_vector_path` と `emotion` は別管理なのか、あるいは 1 sample = 1 emotion という厳密な対応なのか
5. **Save last の変更理由** — `save_last=True → False` は PE-A 機能と無関係に見えるが、副次的な影響があるか
6. **`facebook/pe-av-small` の重み可用性・ライセンス** — 本家取り込み時に学習時ダウンロード依存が発生。ライセンスと再配布可否の確認が必要
7. **DAC 勾配制御の性能影響** — cuDNN 無効化による学習速度への影響は fork 側でも未検証
8. **スケーリング順序** — `embedding * sqrt(h)` の後に style 加算するのが最終仕様だが、その理由コメントが「PE-A emotion vectors can be intentionally amplified」と抽象的

---

## 11. 推奨アクション

1. **今すぐ**: yusuke-ai 側 (mera-chan[bot] の運用者) に連絡し、以下を確認:
   - PE-A style bank の生成スクリプトの有無・共有可否
   - 本家取り込みへの協力意向 (kizuna-intelligence プロジェクトとの関係)
   - ライセンス (MIT 適合性、PE-A の依存ライセンス)
2. **短期** (協力合意後): 選択肢 A の Phase 1 (学習側のみ feature flag 統合) を試行
3. **中期**: Phase 2 (ONNX + ランタイム) の設計レビュー
4. **長期**: Phase 3 (ツール整備 + ドキュメント) で完結

**取り込まない判断をする場合**: 選択肢 C に相当する「カスタム拡張」としてドキュメント化するか、fork のまま放置。fork 側は `kizuna-intelligence` 用途のため、本家への圧力はない。

---

## Appendix: 参考リンク

- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- Main commit (b9e98236): https://github.com/yusuke-ai/piper-plus/commit/b9e98236
- Restrict commit (3afe266c): https://github.com/yusuke-ai/piper-plus/commit/3afe266c
- Restore commit (314b3355): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- 本家 Voice Cloning 先例: `src/cpp/piper_plus.h` (`speaker_embedding` マスクパターン)
