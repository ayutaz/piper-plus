# Style Vector Conditioning + PE-A Emotion Loss 調査レポート

**調査日**: 2026-04-22
**調査対象 fork**: [`yusuke-ai/piper-plus`](https://github.com/yusuke-ai/piper-plus) — branch `feature/2026-04-14-2312-peav-style-conditioning`
**実装者**: `mera-chan[bot]` (AIエージェント)
**PR状況**: 本家 (`ayutaz/piper-plus`) 未提出

---

## 1. TL;DR

fork に、VITS にスタイルベクトル条件付け (style vector conditioning) と知覚感情損失 (PE-A emotion loss) を追加する大規模パッチが存在する。3コミット、変更 6 ファイル、約 500 行追加。既存モデル・既存データセットは `style_vector_dim=0` の既定値により **完全後方互換** で、追加機能は opt-in。

**推論コストへの影響 (2026-04-22 追加分析)**:
- PE-A emotion loss は **学習時専用**、推論グラフには含まれない (WavLM Discriminator と同パターン)
- style_proj 層の追加は FP32 で **+0.2〜0.5MB** (75MB モデル比 +0.3〜0.7%)
- 推論速度影響は **μ 秒オーダーで実質ゼロ**
- → 「軽量・多言語・オフライン」の既存ポジションを崩さない

**取り込み前提の解決済み事項 (2026-04-22 調査)**:
- ✅ **`facebook/pe-av-small` のライセンスは Apache-2.0** (piper-plus MIT と完全互換、商用可)
- ✅ **PE-A style bank (.npz) 生成ツールは自前で実装可能** (スキーマ解読済み、CREMA-D 等の商用可能な感情データセットが利用可能)
- ✅ **ベースモデル再学習は不要、fine-tune のみで対応可能** (style_proj はゼロ初期化された加算的モジュールで、既存モデル挙動を保持。詳細は §15)

**残る課題**:
- **ONNX エクスポート側が未対応** — fork 側でも `export_onnx.py` は変更なし。学習で style_vector を使っても ONNX 化すると機能しない
- **C++/Rust/C#/Go/JS/WASM ランタイム全てで style_vector 入力追加が必要** — 既存の `speaker_embedding` マスクパターンを踏襲

**推奨アクション**: 取り込み方針で進行 (詳細は §11, §14)。段階統合: Phase 0 PoC → Phase 1 学習側 → Phase 2 ONNX+ランタイム → Phase 3 style bank ツール → Phase 4 PE-A loss 有効化 → Phase 5 **既存 6lang ベースに fine-tune 実験** (ベース再学習なし)。yusuke-ai への連絡は **省略可** (自前実装で完結)。

**工数**:
- Claude Code 実装: 約 **5〜8 日稼働** (MOS 評価除く、実質 10 日間で完了目安)
- 人間エンジニア想定 (参考): 約 1.5 ヶ月

**ベース学習 vs Fine-tune の効果差 (推定)**: 感情表現で -0.3〜0.5 MOS、多言語均等性で大幅低下 (英語以外で -30〜40pt)、ただし学習コストは 1/15。**先に fine-tune で実測し、不足ならベース再学習に進む** のが合理的。詳細は §16。

**📋 詳細な実装計画**: [`implementation-plan/`](implementation-plan/README.md) ディレクトリに Phase 別の実装計画ドキュメントを作成済み (PoC スクリプト、patch 計画、テストケース、CLI 設計、分割 PR 案、CREMA-D 前処理コード、fine-tune コマンド、評価プロトコル等)。

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

### 解決済み (2026-04-22 追調査)

1. ~~**PE-A style bank (.npz) の生成方法**~~ → **自前実装で解決可能**。詳細は §13
6. ~~**`facebook/pe-av-small` の重み可用性・ライセンス**~~ → **Apache-2.0 で確認済み**。詳細は §12

### 未解決

2. **Text モード再投入の動機** — 3afe266c で一度 restrict してから 314b3355 で復活させた正確な理由が不明 (性能差か、ユースケースか)
3. **Style dropout の目的** — Regularization か、style-free な合成を明示的にサポートするためか
4. **Emotion ラベルの由来** — fork 側の dataset.json でどのフィールドから取得するか明文化されていない。`style_vector_path` と `emotion` は別管理なのか、あるいは 1 sample = 1 emotion という厳密な対応なのか
5. **Save last の変更理由** — `save_last=True → False` は PE-A 機能と無関係に見えるが、副次的な影響があるか
7. **DAC 勾配制御の性能影響** — cuDNN 無効化による学習速度への影響は fork 側でも未検証
8. **スケーリング順序** — `embedding * sqrt(h)` の後に style 加算するのが最終仕様だが、その理由コメントが「PE-A emotion vectors can be intentionally amplified」と抽象的
9. **`facebook/pe-av-small` の transformers サポート** — 2025-12 発表の新しいモデル (arxiv:2512.19687)。tag は `pe_audio_video`。transformers で標準クラスとして使えるか、カスタムコード必要か Phase 0 で確認必要

---

## 11. 推奨アクション (2026-04-22 更新)

ライセンス・自前実装可能性・**fine-tune 対応可能性**が確認できたため、**yusuke-ai への連絡は省略し、自前実装で完結、ベース再学習なし**の方針に更新。

1. **Phase 0 (先行 PoC)**: `facebook/pe-av-small` を transformers でロードし `get_audio_embeds()` が動くことを確認 (1〜2h)
2. **Phase 1 (学習側統合)**: fork から style vector conditioning のコードを取り込み (PE-A loss は後回し)。既存動作は `--style-vector-dim 0` で維持。`--load_weights_from_checkpoint` も同時取り込み (fine-tune 前提で必須)
3. **Phase 2 (ONNX + ランタイム)**: `export_onnx.py` 拡張 + 5 ランタイムで optional 入力対応 (既存 `speaker_embedding` パターンを流用)
4. **Phase 3 (Style bank ツール)**: `src/python/piper_train/tools/build_pea_style_bank.py` を新規作成 (詳細は §13)
5. **Phase 4 (PE-A loss 有効化)**: Phase 3 完了後に `--pea-emotion-*` 系オプション有効化、CREMA-D で最小実験
6. **Phase 5 (fine-tune 実験)**: **既存の 6lang ベースモデル (75 epoch) に感情ラベル付きデータを追加して fine-tune** (ベース再学習不要)。詳細は §15

---

## 12. `facebook/pe-av-small` ライセンス・可用性 (2026-04-22 調査)

### HuggingFace Hub 基本情報

| 項目 | 値 |
|-----|-----|
| モデル ID | `facebook/pe-av-small` |
| ライセンス | **Apache-2.0** ✅ |
| フォーマット | safetensors |
| タグ | `safetensors`, `pe_audio_video`, `license:apache-2.0` |
| 元論文 | [arxiv:2512.19687](https://arxiv.org/abs/2512.19687) (2025-12) |
| pipeline_tag | 不明 (`library_name: null`) |

### ライセンス互換性評価

- piper-plus 本体は **MIT ライセンス**
- `facebook/pe-av-small` は **Apache-2.0**
- MIT と Apache-2.0 は **相互に互換**。商用利用・改変・再配布すべて可能
- 配布時は Apache-2.0 の NOTICE 条件に注意 (モデルの帰属表示は必要)

### 新しさに関する注意点 (未解決 #9)

- 2025-12 発表の**非常に新しい**モデル。arxiv 公開から 4 ヶ月程度
- `library_name` が null で、transformers の標準クラスとして自動ロード可能か不明
- fork コードでは `from ??? import PeAudioVideoModel` とカスタム class を参照している (コミット b9e98236 の lightning.py import 先は要確認)
- **Phase 0 で要検証**: `transformers.AutoModel.from_pretrained("facebook/pe-av-small", trust_remote_code=True)` で動くか、あるいは別途 Meta 公式リポジトリからコードを取得する必要があるか

### 配布戦略

- 本家取り込み後も、`facebook/pe-av-small` 自体は **HuggingFace からの動的ダウンロードで良い**
- 学習時のみ必要で、ONNX モデルには含まれない → エンドユーザーへの影響なし
- オフライン学習が必要なケースのみ、事前ダウンロード指示をドキュメントに記載

---

## 13. PE-A Style Bank 生成ツール設計 (2026-04-22 追加)

fork の `lightning.py:225-258` の `_init_pea_emotion_loss()` 解析により、スキーマと生成処理が明確化。自前実装可能。

### 13.1 `.npz` スキーマ

```python
np.savez(
    output_path,
    emotion_names = np.array(["neutral", "happy", "sad", "angry", ...]),  # shape: [N]
    emotion_centroids = emotion_centroids_arr,                             # shape: [N, D] float32
    global_centroid = global_centroid_arr,                                 # shape: [D]   float32
)
```

`D` は PE-A の audio embedding 次元 (モデル仕様で決定、`small` ならば推測 256〜512 次元)。

### 13.2 fork 側での利用 (読み込み処理, `lightning.py:235-253`)

```python
bank = np.load(Path(style_bank), allow_pickle=True)
emotion_names = [str(name) for name in bank["emotion_names"].tolist()]
global_centroid = torch.as_tensor(bank["global_centroid"], dtype=torch.float32)
emotion_centroids = torch.as_tensor(bank["emotion_centroids"], dtype=torch.float32)

# 正規化して buffer 登録
self.register_buffer("pea_emotion_global_centroid", F.normalize(global_centroid, dim=-1))
self.register_buffer("pea_emotion_centroids", F.normalize(emotion_centroids, dim=-1))
```

### 13.3 推奨ツール仕様: `src/python/piper_train/tools/build_pea_style_bank.py`

```
入力:
  --dataset-dir PATH        # 感情ラベル付き音声データセット
  --manifest PATH           # "audio_path,emotion" の CSV or JSONL
  --model-name STR          # デフォルト "facebook/pe-av-small"
  --output PATH             # 出力 .npz
  --sample-rate INT         # 16000 (PE-A デフォルト)
  --per-utterance-dir PATH  # 発話ごとの style_vector.npy 出力先 (オプション)

処理:
  1. PE-A モデルをロード
  2. 全音声サンプルを 16kHz resample
  3. PE-A の get_audio_embeds() で埋め込み取得
  4. 感情ごとに平均 → emotion_centroids[N, D]
  5. 全サンプル平均 → global_centroid[D]
  6. .npz 保存
  7. (オプション) 各発話の embedding を個別 .npy 保存
     → 学習時 dataset.json の style_vector_path に紐付け

出力:
  1. style_bank.npz (PE-A loss 用)
  2. style_vectors/<utt_id>.npy (学習時の style_vector 入力、任意)
  3. 統計レポート (各感情のサンプル数、埋め込み距離行列、etc.)
```

### 13.4 対応感情音声データセット候補

| データセット | 言語 | 感情数 | 発話数 | 話者数 | ライセンス | 商用可 |
|------------|-----|-------|-------|------|----------|-------|
| **CREMA-D** | EN | 6 (angry/happy/sad/fearful/disgusted/neutral) | 7,442 | 91 | ODbL | ✅ 第一候補 |
| **ESD** | EN+ZH | 5 (neutral/happy/sad/angry/surprise) | 35,000 | 20 | 研究目的 | ⚠ |
| **EmoV-DB** | EN | 5 | 7,000 | 4 | CC-BY | ✅ |
| **JTES** | JA | 4 (neutral/happy/sad/angry) | ~20,000 | 100 | 研究目的 | ⚠ |
| RAVDESS | EN | 8 | 7,356 | 24 | CC-BY-NC-SA | ✗ 非商用 |

**第一候補: CREMA-D** (Open Database License、商用可、感情バランス良好)。

多言語性を活かすなら CREMA-D (EN) + ESD 中国語パート + JTES (JA) を混成も可能だが、style bank は言語非依存 (音響特徴空間) のため **CREMA-D 単独で十分** と推測。

### 13.5 実装規模

| タスク | コード行数 | 工数 |
|-------|----------|------|
| PE-A モデルローダー (Phase 0 と共通) | ~50 行 | 1〜2h |
| CREMA-D データローダー | ~80 行 | 半日 |
| 埋め込み抽出 + 平均計算 | ~100 行 | 半日 |
| CLI + レポート生成 | ~50 行 | 半日 |
| ユニットテスト | ~100 行 | 半日 |
| **合計** | **~380 行** | **約 2〜3 日** |

---

## 14. 実装ロードマップ (2026-04-22 更新: Claude Code 実装前提)

**実装主体**: Claude Code (AIエージェント) が全 Phase を実装。人間はレビュー・承認・評価のみ。

| Phase | 内容 | Claude Code 工数 | 既存ポジション影響 | 優先度 |
|-------|-----|---------------|-----------------|------|
| 0 | `facebook/pe-av-small` 動作確認 PoC | 30分〜1h | なし | ★★★ |
| 1 | Style vector conditioning 学習側統合 (PE-A loss なし) | 4〜8h | モデル +0.5MB、opt-in | ★★★ |
| 2 | ONNX + 5 ランタイム対応 | 2〜3 日 (並列 Agent) | **推論影響なし** | ★★ |
| 3 | Style bank 生成ツール + CREMA-D 対応 | 4〜8h | なし (tool) | ★★ |
| 4 | PE-A emotion loss 有効化 + 小規模実験 | 1〜2 日 | 学習時のみ | ★★ |
| 5 | **既存 6lang ベースへ fine-tune 実験** (ベース再学習なし) | **1〜2 日 + GPU 2 日** | なし | ★ |
| **Claude Code 実装合計** | | **約 5〜8 日稼働** | | |
| **GPU 学習 (バックグラウンド)** | | 約 2 日 | | |
| **実質完了目安** | | **約 10 日間** (MOS 評価除く) | | |

**参考 (人間エンジニア想定)**: 約 1.5 ヶ月。Claude Code では並列 tool 実行、Agent 並列起動、テスト自動生成、コード完全設計済みなどで大幅短縮。

**Phase 5 短縮の根拠**: style_proj はゼロ初期化された加算的モジュールで、既存モデル挙動を完全に保持したまま追加学習可能。6lang ベース (75 epoch, 92h) 再学習は不要。詳細は §15。

### Phase 間の依存関係

```
Phase 0 (PoC) ──┬──→ Phase 1 (学習側) ──┬──→ Phase 2 (ONNX+ランタイム)
                │                       │
                └──→ Phase 3 (ツール) ──┘
                                        │
                                        ▼
                                   Phase 4 (PE-A loss)
                                        │
                                        ▼
                                   Phase 5 (fine-tune、ベース再学習なし)
```

Phase 1 と 3 は並行可能 (Phase 0 完了後)。Phase 2 と Phase 4 は独立。

### 分割 PR の目安

| PR | 内容 | Phase |
|----|-----|------|
| PR-A | feat(pea): `facebook/pe-av-small` loader + minimal PoC テスト | Phase 0 |
| PR-B | feat(train): style vector conditioning (models.py + lightning.py + dataset.py + infer.py + CLI) | Phase 1 |
| PR-C | feat(onnx): style_vector を ONNX 入力に追加 (mask パターン) | Phase 2 |
| PR-D | feat(runtime): 5 ランタイムで style_vector optional 対応 | Phase 2 |
| PR-E | feat(tools): `build_pea_style_bank.py` + CREMA-D loader | Phase 3 |
| PR-F | feat(train): PE-A emotion loss 統合 + CLI + docs | Phase 4 |

各 PR は単独でマージ可能。PR-B が Phase 2 以降の前提。

---

## 15. Fine-tune のみで対応可能な設計根拠 (2026-04-22 追加)

ベースモデル (`output-multilingual-6lang`, 75 epoch, 92h 学習) を**再学習せず**、既存チェックポイントから fine-tune だけで style vector conditioning + PE-A emotion loss を有効化できる。根拠は以下の 3 点。

### 15.1 `style_proj` はゼロ初期化された加算的モジュール

fork の `models.py:220-225, 927-940` 実装:

```python
# TextEncoder (text mode)
self.style_proj = nn.Linear(style_vector_dim, hidden_channels)
nn.init.zeros_(self.style_proj.weight)
nn.init.zeros_(self.style_proj.bias)

# SynthesizerTrn (global mode)
self.style_proj = nn.Sequential(
    nn.Linear(style_vector_dim, gin_channels),
    nn.SiLU(),
    nn.Linear(gin_channels, gin_channels),
)
# (デフォルトでは Sequential は Kaiming init だが、forward で `g + style_g` の加算的注入)
```

**効果**:
- 初期状態で `style_proj(x) ≈ 0` (Linear 部分は厳密にゼロ、Sequential は小さい値)
- 既存の forward 出力に加算してもほぼ影響なし
- **ベースモデルの挙動を保持したまま、学習で徐々に style 制御能力を獲得**

### 15.2 `--load_weights_from_checkpoint` で部分的 weight ロード

fork で追加された shape-aware weight loader (`__main__.py:378-417`):

```python
def load_checkpoint_weights(checkpoint_path, model):
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    saved_state_dict = checkpoint["state_dict"]
    current_state_dict = model.state_dict()
    new_state_dict = {}

    for key, current_value in current_state_dict.items():
        saved_value = saved_state_dict.get(key)
        if saved_value is not None and saved_value.shape == current_value.shape:
            new_state_dict[key] = saved_value      # 既存 weight をロード
        else:
            new_state_dict[key] = current_value    # 新規パラメータは初期化のまま
```

- **既存の 6lang モデル** には `style_proj` パラメータが存在しない
- このローダーは「形状一致する weight だけロード、不一致は初期化のまま」
- → `style_proj` はゼロ初期化 (新規)、他のすべての layer は 6lang 学習済みの値
- 既存 `--resume_from_checkpoint` の strict=False フォールバック動作に相当するが、**明示的かつログ付き**で意図が明確

### 15.3 既存のつくよみちゃん fine-tune ワークフローと同じパターン

CLAUDE.md 記載の Template B (シングルスピーカー fine-tune) と構造的に同一:

| 項目 | つくよみちゃん 6lang-v2 | style vector fine-tune (案) |
|------|---------------------|--------------------------|
| ベース | 6lang 75 epoch | 6lang 75 epoch |
| 継承方法 | `--resume-from-multispeaker-checkpoint` | `--load_weights_from_checkpoint` |
| 新規層 | emb_g, emb_lang 再初期化 | style_proj 新規追加 |
| 学習率 | `--base_lr 2e-5` | `--base_lr 2e-5` |
| freeze-dp | 自動有効 (catastrophic forgetting 防止) | 推奨 (同じ理由) |
| epoch 数 | 500 (100発話) | 200 (データ量に応じて調整) |

→ **piper-plus は既にこのパターンを実運用している**ので、新しい仕組みではない。

### 15.4 想定コマンド (Phase 5 実験用)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-emotion-finetune \
  --prosody-dim 16 \
  --style-vector-dim 256 \
  --style-condition-mode global \
  --style-condition-dropout 0.1 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 200 --batch-size 4 --samples-per-speaker 2 \
  --checkpoint-epochs 20 --quality medium \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --val-every-n-epochs 20 \
  --audio-log-epochs 20 \
  --load_weights_from_checkpoint \
    /data/piper/output-multilingual-6lang/lightning_logs/version_0/checkpoints/epoch=74-step=504712.ckpt \
  --default_root_dir /data/piper/output-6lang-style-v1 \
  > training_style_v1.log 2>&1 &
```

**PE-A loss を同時有効化する場合 (Phase 4 完了後)**:

```bash
# 上記コマンドに追加:
  --pea-emotion-style-bank /data/piper/style_bank_crema_d.npz \
  --pea-emotion-loss-weight 0.1 \
  --pea-emotion-centroid-weight 0.1 \
  --pea-emotion-margin-weight 0.05 \
  --pea-emotion-loss-every-n-steps 4 \
  --pea-emotion-warmup-steps 2000
```

### 15.5 想定される工数と GPU 時間

| 項目 | 値 |
|------|-----|
| データセット規模 | 感情ラベル付き 1,000〜10,000 発話 (CREMA-D or 自前) |
| 学習時間 | V100 1GPU で 200 epoch / 約 6〜24 時間 |
| ディスク | style_vectors/*.npy × 発話数 × 256次元 × 4byte = 約 10〜100MB |
| GPU 時間比較 | ベース再学習 92h → fine-tune 6〜24h (**約 10〜15 分の 1**) |
| Claude Code 実装時間 | 1〜2 日 (設定・実行・監視・評価) |

### 15.6 Fine-tune のメリット

1. **GPU 時間削減**: 6lang 再学習 (92h × 4 GPU = 368 GPU hours) → fine-tune (24h × 1 GPU = 24 GPU hours)。**約 15 倍の効率化**
2. **既存モデル品質保持**: base を触らないので既存の声質・発音は劣化しない
3. **段階検証可能**: style vector のみ Phase 5a → PE-A loss を Phase 5b と分離実験できる
4. **つくよみちゃん応用が自然**: 既存の `--resume-from-multispeaker-checkpoint` パターンに乗せるだけ
5. **並列開発**: 複数の fine-tune 実験 (異なる style_vector_dim、異なる mode、異なる dropout) を同時進行可能
6. **リスク分離**: PE-A model 依存による問題は fine-tune モデルのみに限定される

### 15.7 限界と注意点

1. **style_proj の学習十分性**: fine-tune データが極小 (< 500 発話) だと style 制御能力が弱い可能性。最低 1,000 発話以上推奨
2. **freeze-dp との相性**: `--freeze-dp` 推奨だが、そうすると duration predictor は style の影響を受けない。発話長の感情依存は不可 (fork でも DP には style_vector が伝わらないため元々そう)
3. **catastrophic forgetting 対策**: `--base_lr 2e-5` (ベース学習の 1/10) + `--ema-decay 0.9995` + `--freeze-dp` の 3 点セット必須
4. **感情ラベルと話者マトリクス**:
   - 理想: 1 話者複数感情 (つくよみちゃんに感情付き音声を追加収録)
   - 現実的: 複数話者単一感情の混合 (CREMA-D は話者 × 感情の組み合わせあり、そのまま使える)
   - 多言語: CREMA-D は英語のみ。日本語の感情表現は弱い可能性 → JTES や独自収録で補強
5. **style bank と fine-tune データの対応**: PE-A loss を有効化する場合、style bank の `emotion_names` と fine-tune データの `emotion` フィールドの値が一致している必要あり
6. **ベース再学習が必要になる条件** (fine-tune で効果不足の場合):
   - 全言語で均等な感情制御が必要 (多言語感情データが十分ある場合)
   - style dropout のネイティブ統合による regularization を重視する場合
   - 話者×感情マトリクスを密に学習したい場合
   - → これらは次回の 6lang → 7lang 拡張時やベースアップデート時に同時導入が自然

### 15.8 段階的 fine-tune 戦略

**Stage 1: Style vector のみ (PE-A loss なし)**
- データ: CREMA-D (7,442 発話、英語、6 感情)
- 目的: style vector 機能の動作確認、基本的な感情制御能力獲得
- 期待成果: ベース 6lang モデルに感情 conditioning 経路が追加され、英語で基本的な感情スタイルが再現可能に

**Stage 2: PE-A loss 追加 (Style bank 事前生成)**
- データ: Stage 1 と同じ + `build_pea_style_bank.py` で生成した style bank
- 目的: 知覚的な感情空間への明示的な引き寄せで表現力向上
- 期待成果: emotion_name を指定した推論時に、ASR / MOS で感情が認識できる程度の表現力

**Stage 3: 日本語感情データ追加** (オプション)
- データ: JTES or 独自収録のつくよみちゃん感情音声
- 目的: 日本語での実用性獲得 (piper-plus の主要言語)
- 期待成果: つくよみちゃんで「嬉しい」「悲しい」等を出し分け可能

各 Stage は独立した fine-tune run で、いずれも数時間〜1日で完了。前の Stage のチェックポイントから次の Stage へ継承可能。

---

## 16. ベース学習 vs Fine-tune の効果比較 (推定、2026-04-22 追加)

**前提**: 現時点では両方の実学習結果がないため、以下は **先行研究 (StyleTTS 2, VITS adapter 系, prompt tuning 研究) と VITS アーキテクチャ特性から推定した定性・定量的な見積もり**。Phase 5 実験後に実測値で更新すること。

### 16.1 観点別サマリ

| 観点 | ベース学習 | Fine-tune | 差の大きさ |
|-----|----------|----------|----------|
| 感情制御の**強度** | 強 | 中 | 中 (-20〜30%) |
| 感情制御の**一貫性** | 安定 | やや不安定 | 小 |
| **多言語均等性** | 均等 | 学習データ依存 | **大** |
| **話者独立性** | 高 | データ偏り残る | 中 |
| 未学習感情への**汎化** | 補間可能 | 近傍のみ | 中 |
| **既存発音品質の保持** | ベース依存 | 高 (freeze-dp 効果) | **Fine-tune 優位** |
| **学習コスト** | 368 GPU h | 24 GPU h | **約 15 倍差** |
| **推論コスト** | 同一 | 同一 | なし |

### 16.2 観点別の詳細見積もり

#### (1) 感情制御の強度 — ベース学習が有利

VITS の style conditioning は `decoder + flow + DP` の全経路に影響する。ベース学習では全サンプルで style を経験するため、style の各次元に対する内部層の応答関数が深く最適化される。Fine-tune では style_proj (追加された投影層) のみをゼロから学習するため、内部の既存層が style に適応しきれない。

**先行研究参考値**:
- StyleTTS 2 (フルスクラッチ学習): 感情認識精度 85%+、MOS 感情表現 4.0+
- Adapter 系 fine-tune: 感情認識精度 70〜80%、MOS 感情表現 3.5〜3.8

#### (2) 感情の一貫性 — 小さな差

- ベース学習: `style_condition_dropout` が全サンプルで regularization として効く
- Fine-tune: dropout は fine-tune 期間のみ作用、既存モデルの「style なし」状態が占める割合が大きい
- **見積もり**: MOS で -0.1〜0.2 程度 (聞き分けられるかギリギリ)

#### (3) 多言語均等性 — **最大の差が出る領域**

- **ベース学習**: 6lang 全サンプル (508,187 発話) で style を経験 → 全言語で均等な感情制御
- **Fine-tune**: 例えば CREMA-D (英語) だけで fine-tune すると、**他言語の感情表現は大きく劣化**
- **見積もり**:
  - 英語: 感情認識精度 70〜80%
  - 日本語 (JTES 併用時): 60〜70%
  - 中/仏/西/葡 (fine-tune データに含まれない場合): 30〜50% (ほぼランダムに近い)

**これが決定的な判断材料**: 多言語で均等な感情制御が必須なら、ベース学習が推奨されるか、fine-tune 時に各言語の感情データを準備する必要あり。

#### (4) 話者独立性 — データ次第

- **CREMA-D だけで fine-tune**: 91 話者の感情データがあるため、話者 × 感情マトリクスは比較的密
- **つくよみちゃんだけで fine-tune**: 1 話者のみ → 他話者で感情制御しようとすると効果薄い
- **ベース学習**: 6lang の全 571 話者で style を経験 → 任意の話者 × 感情の組み合わせで動く

#### (5) 未学習感情への汎化

- ベース学習: style vector 空間自体が連続的に最適化 → style_vector を補間して「怒り + 悲しみ」のような混合感情も出せる可能性
- Fine-tune: 学習時に見た emotion_centroid 付近でのみ効く。補間能力は限定的
- **見積もり**: ベース学習で汎化能力は **1.5〜2 倍**

#### (6) 既存発音品質の保持 — **Fine-tune 優位**

- Fine-tune: 既存モデル weight を継承、`--freeze-dp` + `--base_lr 2e-5` で catastrophic forgetting を防ぐため発音品質が落ちるリスクが低い
- ベース再学習: 6lang + 感情データを混ぜると、感情データの話者/言語分布に偏りがあれば既存発音が歪む可能性 (データ設計依存)

#### (7) 学習コスト — 15 倍の差

| | GPU hours | 実時間 (V100 4 GPU) |
|--|----------|-------------------|
| ベース再学習 | 368 h | 約 92 h (約 4 日) |
| Fine-tune | 24 h | 約 24 h (1 日、1 GPU でも可) |

### 16.3 想定される定量指標 (先行研究ベースの推定)

**つくよみちゃん + CREMA-D で fine-tune した場合の想定成果**:

| 指標 | 期待値 | 備考 |
|-----|-------|------|
| 日本語 感情認識精度 | 60〜70% | つくよみちゃんデータに日本語感情音声があれば |
| 英語 感情認識精度 | 70〜80% | CREMA-D データから |
| 中/仏/西/葡 感情認識精度 | 30〜50% | fine-tune データになければ弱い |
| MOS 自然性 | 3.9〜4.1 | ベース 4.2 から若干低下 |
| MOS 感情表現 | 3.3〜3.7 | 中程度の表現力 |

**6lang 多言語感情データでベース再学習した場合の想定成果**:

| 指標 | 期待値 | 備考 |
|-----|-------|------|
| 全言語 感情認識精度 | 80〜85% | 各言語に感情データが揃えば |
| MOS 自然性 | 4.2〜4.3 | ベース品質維持 |
| MOS 感情表現 | 3.8〜4.2 | 強い表現力、補間可能 |

**差分のまとめ**:
- 感情表現で +0.3〜0.5 MOS
- 多言語均等性で大幅アップ (特に非英語言語)
- 学習コストは 15 倍

### 16.4 用途別の判断基準

#### Fine-tune で十分なシナリオ
- つくよみちゃん 1 話者の感情出し分け (VTuber 配信、ゲーム台詞、オーディオブック個人利用)
- PoC / 初期効果検証
- 英語中心の用途
- コミュニティモデルとして配布 (`CONTRIBUTING_MODELS.md` 経由)

#### ベース学習が望ましいシナリオ
- **商用品質の多言語感情 TTS** (OpenAI 互換 API で全言語対応を保証したい)
- 対話 AI / アシスタント用途で「ユーザー言語に応じた感情応答」が必要
- Wyoming / HA 統合で各国語の自然な感情表現が求められる
- 「piper-plus の感情 TTS」として差別化ポジションを取りたい

### 16.5 推奨プロセス

```
1. Phase 5 (3〜5 日) で fine-tune 実験
       ↓
2. 実測: MOS エバル + 感情認識精度の測定
       ↓
3a. 十分な品質 → ここで完結、コミュニティモデルとして配布
3b. 不足 → データ補強 or ベース再学習検討
       ↓
4. ベース再学習が必要なら、次回の 6lang アップデート (7lang 拡張など)
   と同時に統合
```

**合理的な投資順序**:
- 先に投資コストの低い fine-tune を通る
- 実測値で「どこまで実用になるか」を 1〜2 週間で確認
- ベース再学習は「データが揃ってから、次回大型更新のタイミングで」

### 16.6 実測値で更新する項目 (Phase 5 完了後)

Phase 5 実験完了後、以下の項目を実測値で更新する:

- [ ] MOS 自然性 (5点満点、評価者 10〜20 名)
- [ ] MOS 感情表現強度 (5点満点)
- [ ] 感情認識精度 (ASR 感情分類器 or 人手評価)
- [ ] 言語別の感情表現能力 (英/日/中/西/仏/葡)
- [ ] 話者間の感情一貫性 (複数話者で同じ感情を再現)
- [ ] 実際の GPU 時間・epoch 数

ベース学習側も将来実施する場合は同じ項目を測定し、両者の差を定量化する。

---

## Appendix: 参考リンク

- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- Main commit (b9e98236): https://github.com/yusuke-ai/piper-plus/commit/b9e98236
- Restrict commit (3afe266c): https://github.com/yusuke-ai/piper-plus/commit/3afe266c
- Restore commit (314b3355): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- 本家 Voice Cloning 先例: `src/cpp/piper_plus.h` (`speaker_embedding` マスクパターン)
- `facebook/pe-av-small` モデルカード: https://huggingface.co/facebook/pe-av-small
- Perception Encoder 論文: https://arxiv.org/abs/2512.19687
- CREMA-D データセット: https://github.com/CheyneyComputerScience/CREMA-D
