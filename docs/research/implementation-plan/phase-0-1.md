# Phase 0-1 実装計画: PE-A PoC + Style Vector Conditioning 学習側統合

**実装主体**: Claude Code (AIエージェント)
**Phase 0 Claude Code 工数**: 30分〜1h (PoC、HF ダウンロード待ち含む)
**Phase 1 Claude Code 工数**: 4〜8h (fork cherry-pick + テスト + CI)
**依存**: なし (Phase 0)、Phase 0 完了 (Phase 1)
**後続**: Phase 2 (ONNX+ランタイム)、Phase 3 (Style bank)、Phase 4 (PE-A loss)

> **参考**: 人間エンジニア想定の工数目安は Phase 0 = 1〜2h、Phase 1 = 1 週間 (21.5h)。
> Claude Code では並列 tool 実行・Agent 起動・テスト自動生成により短縮される。

---

## Phase 0: facebook/pe-av-small PoC

### 0.1 モデル概要

`facebook/pe-av-small` は Meta の Perception Encoder (Audio-Visual) モデル。arxiv:2512.19687 (2025-12発表) で公開。HuggingFace Hub で利用可能。

| 項目 | 値 |
|-----|-----|
| ライセンス | Apache-2.0 (MIT と互換、商用可) |
| フォーマット | safetensors |
| 推定モデルサイズ | 50〜150MB (small variant) |
| 用途 | 知覚感情空間への音声埋め込み抽出 (PE-A loss 用) |

### 0.2 読み込み方法 (想定)

**推測**: 以下のいずれかで動く可能性が高いが、**Phase 0 で実検証が必要**:

```python
# Option A (第一候補): AutoModel + trust_remote_code
from transformers import AutoModel
model = AutoModel.from_pretrained(
    "facebook/pe-av-small",
    trust_remote_code=True
)

# Option B (フォールバック): カスタムクラス
# fork コードの import 先を参考に、perception_models リポジトリから
# PeAudioVideoModel クラスを取得する可能性
```

Phase 0 で確認する項目:
1. `trust_remote_code=True` で動くか、手動ダウンロード必要か
2. API 名: `get_audio_embeds()` が存在するか、`forward()` か、別名か
3. 入力 shape: `[batch, samples]` か `[batch, 1, samples]` か
4. 入力 sample rate: 16kHz 固定か
5. 出力 embedding dimension: 256/512/その他

### 0.3 依存パッケージ

```toml
# pyproject.toml への追加候補
transformers >= 4.30.0  # AutoModel、trust_remote_code support
torchaudio >= 0.13.0    # resampling
torch >= 2.0.0          # 既存要件と合致
```

新規依存候補:
- `soundfile`: テスト時に音声ロード (既に torchaudio に含まれる可能性あり)

### 0.4 PoC スクリプト

**配置**: `src/python/piper_train/tools/test_pe_av_small.py`

```python
#!/usr/bin/env python3
"""
Phase 0 PoC: facebook/pe-av-small 動作確認スクリプト

実行:
  uv run python src/python/piper_train/tools/test_pe_av_small.py
"""

import logging
import time
import torch

_LOGGER = logging.getLogger(__name__)


def test_loading():
    """Test model loading from HuggingFace Hub."""
    from transformers import AutoModel

    _LOGGER.info("Loading facebook/pe-av-small from HF Hub...")
    model = AutoModel.from_pretrained(
        "facebook/pe-av-small",
        trust_remote_code=True,
    )
    _LOGGER.info(f"Model loaded: {type(model).__name__}")
    return model


def test_inference(model):
    """Test inference with dummy audio."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device).eval()

    # Dummy audio: 16kHz, 3 seconds, mono
    sample_rate = 16000
    duration_s = 3
    audio = torch.randn(1, sample_rate * duration_s, dtype=torch.float32, device=device)

    _LOGGER.info(f"Input audio shape: {audio.shape}")

    with torch.no_grad():
        # Try get_audio_embeds() first
        if hasattr(model, "get_audio_embeds"):
            embeddings = model.get_audio_embeds(audio)
            method = "get_audio_embeds"
        else:
            _LOGGER.info("get_audio_embeds() not found, trying forward()...")
            output = model(audio)
            if isinstance(output, dict):
                embeddings = output.get("audio_embeds") or output.get("embeddings")
            else:
                embeddings = output
            method = "forward"

    _LOGGER.info(f"Method used: {method}")
    _LOGGER.info(f"Embedding shape: {embeddings.shape}")
    _LOGGER.info(f"Embedding dim: {embeddings.size(-1)}")

    # L2 normalize check
    norm = torch.norm(embeddings, dim=-1).item()
    _LOGGER.info(f"L2 norm (before normalization): {norm:.4f}")

    embeddings_normalized = torch.nn.functional.normalize(embeddings, dim=-1)
    norm_after = torch.norm(embeddings_normalized, dim=-1).item()
    _LOGGER.info(f"L2 norm (after normalization): {norm_after:.4f}")

    return embeddings, method


def benchmark(model, n_runs=5):
    """Benchmark inference latency."""
    device = next(model.parameters()).device

    # Warmup
    audio = torch.randn(1, 16000 * 3, device=device)
    with torch.no_grad():
        _ = model.get_audio_embeds(audio) if hasattr(model, "get_audio_embeds") else model(audio)

    times = []
    for i in range(n_runs):
        audio = torch.randn(1, 16000 * 3, device=device)
        start = time.perf_counter()
        with torch.no_grad():
            _ = model.get_audio_embeds(audio) if hasattr(model, "get_audio_embeds") else model(audio)
        end = time.perf_counter()
        times.append((end - start) * 1000)
        _LOGGER.info(f"Run {i+1}: {times[-1]:.2f} ms")

    avg = sum(times) / len(times)
    _LOGGER.info(f"Average latency: {avg:.2f} ms")

    # GPU memory
    if device.type == "cuda":
        mem_mb = torch.cuda.max_memory_allocated(device) / 1024**2
        _LOGGER.info(f"Peak GPU memory: {mem_mb:.1f} MB")

    return avg


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    _LOGGER.info("=== Phase 0 PoC: facebook/pe-av-small ===")

    # Test 1: Loading
    _LOGGER.info("\n[Test 1] Loading model...")
    model = test_loading()

    # Test 2: Inference
    _LOGGER.info("\n[Test 2] Running inference...")
    embeddings, method = test_inference(model)

    # Test 3: Benchmark
    _LOGGER.info("\n[Test 3] Benchmarking...")
    benchmark(model)

    _LOGGER.info("\n=== PoC Complete ===")
    _LOGGER.info(f"Summary: method={method}, embedding_dim={embeddings.size(-1)}")


if __name__ == "__main__":
    main()
```

### 0.5 動作確認コマンド

```bash
# 環境セットアップ
cd /Users/s19447/Documents/piper-plus

# PoC 実行
uv run python src/python/piper_train/tools/test_pe_av_small.py
```

### 0.6 期待される結果 (仮説)

| 項目 | 推定値 | 根拠 |
|------|-------|------|
| モデルサイズ | 50-150MB | small variant、safetensors 圧縮 |
| 埋め込み次元 | 256 or 512 | 推測 (要検証) |
| 推論時間 (16kHz, 3s) | 40-80ms | 軽量 small variant 推定 |
| GPU メモリ (推論) | 200-500MB | embedding 抽出のみ |
| 学習時 GPU メモリ追加 | 500MB-1GB | gradient + optimizer states 推定 |

**Phase 0 完了条件**: `test_pe_av_small.py` が成功実行し、embedding shape と method 名がログに出力される。

### 0.7 Phase 0 で判明する設計決定

- Phase 1 の `--style-vector-dim` デフォルト値 (PoC で確定した embedding 次元を基準)
- Phase 3 の `build_pea_style_bank.py` で使用する model loader コード
- Phase 4 の PE-A loss の input preprocessing (sample rate, normalization)

---

## Phase 1: Style Vector Conditioning 学習側統合

### 1.1 取り込み対象コミット

Fork `yusuke-ai/piper-plus` から以下を取り込む:

| # | SHA | 取り込み対象 |
|---|-----|-----------|
| 1 | `b9e98236` | style vector conditioning 実装 (PE-A loss 部分は除外) |
| 2 | `3afe266c` | global mode 限定化 (参考、最終形は次コミットで復活) |
| 3 | `314b3355` | **最終形 (これをベースに取り込み)**、text mode 復活 + scaling 順序修正 |

**方針**: コミット `314b3355` の状態をベースに、PE-A emotion loss 関連コードを除外して取り込む。

### 1.2 ファイル別変更マッピング (fork → 本家)

#### A. `src/python/piper_train/vits/models.py`

| Fork 側の変更 | 取り込み判定 |
|------------|-----------|
| `TextEncoder.__init__`: `style_vector_dim`, `style_condition_dropout` パラメータ追加 | ✅ 取り込み |
| `TextEncoder._style_embedding()`: 新規メソッド | ✅ 取り込み |
| `TextEncoder.forward()`: `style_vector` 引数追加、scaling 順序修正 | ✅ 取り込み |
| `SynthesizerTrn.__init__`: `style_vector_dim`, `style_condition_dropout`, `style_condition_mode` | ✅ 取り込み |
| `SynthesizerTrn._add_style_condition()`: 新規メソッド | ✅ 取り込み |
| `SynthesizerTrn.forward/infer`: style_vector ルーティング | ✅ 取り込み |
| WavLM の `use_safetensors=False` 修正 | ⏭ 本家で既に PR #353 でマージ済み |

#### B. `src/python/piper_train/vits/lightning.py`

| Fork 側の変更 | 取り込み判定 |
|------------|-----------|
| Model 呼び出し時の `style_vector=batch.style_vectors` 伝播 | ✅ 取り込み |
| `_init_pea_emotion_loss()` | ❌ **Phase 4 で取り込み** |
| `_ensure_pea_emotion_model()` | ❌ **Phase 4 で取り込み** |
| `_compute_pea_emotion_loss()` | ❌ **Phase 4 で取り込み** |
| `training_step_g` への PE-A loss 合算 | ❌ **Phase 4 で取り込み** |
| `__init__` の `pea_emotion_*` hparams | ❌ **Phase 4 で取り込み** |

#### C. `src/python/piper_train/vits/dataset.py`

| Fork 側の変更 | 取り込み判定 |
|------------|-----------|
| `Utterance.style_vector_path: Path \| None` | ✅ 取り込み |
| `Utterance.emotion: str \| None` | ✅ 取り込み (オプション、Phase 1 では読み込むだけ) |
| `UtteranceTensors.style_vector: FloatTensor` | ✅ 取り込み |
| `UtteranceTensors.emotion: str` | ✅ 取り込み |
| `Batch.style_vectors: FloatTensor` | ✅ 取り込み |
| `Batch.emotions: list[str]` | ✅ 取り込み |
| `__getitem__`: style_vector ロード | ✅ 取り込み |
| `BatchCollator`: style_vectors 事前割当 + slice-copy | ✅ 取り込み |

#### D. `src/python/piper_train/vits/commons.py`

| Fork 側の変更 | 取り込み判定 |
|------------|-----------|
| `slice_segments()` の shape 一般化 (3行変更) | ✅ 取り込み |

#### E. `src/python/piper_train/__main__.py`

| Fork 側の変更 | 取り込み判定 |
|------------|-----------|
| `--style-vector-dim` (default 0) | ✅ 取り込み |
| `--style-condition-dropout` (default 0.0) | ✅ 取り込み |
| `--style-condition-mode` (default "global") | ✅ 取り込み |
| `--load_weights_from_checkpoint` (shape-aware loader) | ✅ 取り込み (fine-tune 必須) |
| `--pea-emotion-*` (13個の CLI オプション) | ❌ **Phase 4 で取り込み** |
| `save_last=True → False` | ⚠️ 別 PR で検討 (PE-A と独立な変更) |

#### F. `src/python/piper_train/infer.py`

| Fork 側の変更 | 取り込み判定 |
|------------|-----------|
| `_style_vector_to_tensor()` helper | ✅ 取り込み |
| 推論ループでの `style_vector=...` 引数 | ✅ 取り込み |
| GPU device 対応 | ⚠️ 既存の GPU 対応状況に依存、差分のみ取り込み |

### 1.3 最小取り込みスコープ (PE-A 関連を除外)

Phase 1 で取り込む CLI オプション:

| オプション | 既定値 | 説明 |
|----------|-------|------|
| `--style-vector-dim` | 0 | 0 = 無効化 (後方互換) |
| `--style-condition-dropout` | 0.0 | training 時のみ batch mask |
| `--style-condition-mode` | `"global"` | `"global"` or `"text"` |
| `--load_weights_from_checkpoint` | None | shape-aware partial load (fine-tune 必須) |

**Phase 4 で追加する予定の CLI**: `--pea-emotion-*` 系 (詳細は [phase-3-4.md §4.4](phase-3-4.md#44-cli-オプション設計))

### 1.4 具体的な patch 方針 (ファイル別)

#### Patch 1: `vits/models.py` (+150行程度)

主要な追加:

```python
# TextEncoder.__init__ に追加
self.style_vector_dim = style_vector_dim
self.style_condition_dropout = style_condition_dropout

if style_vector_dim > 0:
    # ゼロ初期化 (既存挙動と等価にする)
    self.style_proj = nn.Linear(style_vector_dim, self.hidden_channels)
    nn.init.zeros_(self.style_proj.weight)
    nn.init.zeros_(self.style_proj.bias)
else:
    self.style_proj = None

# SynthesizerTrn.__init__ に追加
if style_condition_mode not in ("global", "text"):
    raise ValueError(
        f"style_condition_mode must be 'global' or 'text', got {style_condition_mode!r}"
    )

if style_condition_mode == "global" and style_vector_dim > 0:
    if gin_channels <= 0:
        raise ValueError(
            "global mode requires gin_channels > 0"
        )
    self.style_proj = nn.Sequential(
        nn.Linear(style_vector_dim, gin_channels),
        nn.SiLU(),
        nn.Linear(gin_channels, gin_channels),
    )
else:
    self.style_proj = None
```

コミット 314b3355 の完全な patch は `gh api "repos/yusuke-ai/piper-plus/commits/314b3355"` で取得可能。

#### Patch 2: `vits/lightning.py` (+20行程度、Phase 1)

`VitsModel.training_step` / `validation_step` でモデル呼び出し時に `style_vector=batch.style_vectors` を追加するのみ。PE-A loss 関連は除外。

#### Patch 3: `vits/dataset.py` (+80行程度)

- `Utterance`, `UtteranceTensors`, `Batch` にフィールド追加
- `__getitem__` で `_load_tensor(style_vector_path)` 読み込み
- `BatchCollator` で style_vectors テンソル事前割当 + slice-copy

#### Patch 4: `vits/commons.py` (+5行程度)

`slice_segments()` で shape を一般化 (ret_shape を list 化):

```python
# Before
ret = torch.zeros_like(x[:, :, :segment_size])

# After
ret_shape = list(x.shape)
ret_shape[-1] = segment_size
ret = x.new_zeros(ret_shape)
```

#### Patch 5: `__main__.py` (+40行程度)

- argparse に style 系 3 オプション追加
- `--load_weights_from_checkpoint` の処理実装 (shape-aware loader)
- `VitsModel` 初期化時に style パラメータを `hparams` 経由で渡す

#### Patch 6: `infer.py` (+25行程度)

- `_style_vector_to_tensor()` helper (npy/pt/inline から load)
- 推論ループで `style_vector` を model に渡す

### 1.5 テストケース設計

新規: `tests/test_style_vector_conditioning.py`

```python
import pytest
import torch
from piper_train.vits.models import TextEncoder, SynthesizerTrn


class TestStyleVectorConditioning:
    def test_backwards_compatible_dim_0(self):
        """style_vector_dim=0 で既存挙動と完全に等価であることを確認."""
        # ... 2つのエンコーダ (dim=0 明示と default) を生成し forward 出力が一致

    def test_global_mode_projection_zero_init(self):
        """Global mode の style_proj がゼロ初期化されていること."""
        # ... style_proj(x) がゼロに近い出力を返すことを確認

    def test_style_vector_none_fallback(self):
        """style_vector=None で zeros fallback."""

    def test_dropout_training_mode(self):
        """Training mode で dropout が効く (複数回実行で異なる出力)."""

    def test_dropout_eval_mode(self):
        """Eval mode で dropout が効かない (決定的)."""

    def test_text_mode_works_with_dim_0(self):
        """text mode + dim=0 で style_proj=None."""

    def test_global_mode_requires_gin_channels(self):
        """Global mode で gin_channels<=0 なら ValueError."""
        with pytest.raises(ValueError, match="gin_channels"):
            SynthesizerTrn(..., style_condition_mode="global", style_vector_dim=256, gin_channels=0)

    def test_invalid_mode_raises(self):
        """未知の mode で ValueError."""
        with pytest.raises(ValueError):
            SynthesizerTrn(..., style_condition_mode="invalid")
```

新規: `tests/test_load_weights_from_checkpoint.py`

```python
def test_shape_aware_partial_load(tmp_path):
    """既存 6lang checkpoint から style_proj 付きモデルへロード."""
    # 1. 既存モデル (style_vector_dim=0) を保存
    # 2. 新規モデル (style_vector_dim=256) を構築
    # 3. load_weights_from_checkpoint でロード
    # 4. 既存層は復元、style_proj は初期値のまま、を確認

def test_skip_mismatched_shape_logs_warning(caplog):
    """Shape 不一致テンソルはスキップ、warning ログ出力."""

def test_strict_true_raises_on_missing(tmp_path):
    """strict=True なら不足テンソルで RuntimeError."""
```

### 1.6 CLAUDE.md 更新

新規セクション: 実装済み機能 の後半に追加。

```markdown
### Style Vector Conditioning (--style-vector-dim)

スタイルベクトル条件付けにより、音声のスタイル・感情表現を制御可能。既存モデルは `--style-vector-dim 0` (既定) で完全後方互換。

**CLI オプション:**
- `--style-vector-dim N` (デフォルト: 0): スタイルベクトル次元 (0=無効)
- `--style-condition-dropout FLOAT` (デフォルト: 0.0): dropout 確率
- `--style-condition-mode STR` (デフォルト: "global"): 注入モード ("global" または "text")
- `--load_weights_from_checkpoint PATH`: shape-aware 部分ロード (fine-tune 用)

**実装:** `vits/models.py` (TextEncoder / SynthesizerTrn 拡張), `vits/dataset.py` (Utterance.style_vector_path), `__main__.py`, `infer.py`

**テスト:** `tests/test_style_vector_conditioning.py` (8 テスト), `tests/test_load_weights_from_checkpoint.py` (3 テスト)

**fine-tune 推奨コマンド**: Phase 5 docs/research/implementation-plan/phase-5.md 参照
```

### 1.7 工数内訳

| タスク | Claude Code | 人間エンジニア (参考) |
|-------|-----------|----------------|
| Fork から差分取得・マッピング確認 | 5分 | 1h |
| `models.py` patch | 30分 | 4h |
| `lightning.py` patch (Phase 1 スコープのみ) | 15分 | 2h |
| `dataset.py` patch | 30分 | 3h |
| `commons.py` patch | 5分 | 0.5h |
| `__main__.py` patch | 30分 | 3h |
| `infer.py` patch | 15分 | 1h |
| テスト作成 (11 テスト) | 1h | 4h |
| CLAUDE.md 更新 | 10分 | 1h |
| CI 確認 + リグレッション確認 | 1〜3h (CI 待ち含む) | 2h |
| **合計** | **4〜8h** (半日〜1日) | 約 1 週間 (21.5h) |

### 1.8 リスクと対策

| リスク | 可能性 | 対策 |
|-------|-------|------|
| fork 側の style_proj 初期化が実は non-zero で既存モデル影響 | 低 | Phase 0 前に fork コード再確認、テストで verify |
| transformers version が既存 pyproject.toml と衝突 | 中 | Phase 0 PoC で判明次第、version pin |
| shape-aware loader のバグ | 低 | fork 側で実運用、テストカバレッジ高 |
| style_vector 次元不一致 | 低 | dataset 層で collate 時 reshape 強制、エラーメッセージ明確化 |
| 既存 CI (python-tests) 落ち | 中 | dim=0 デフォルトでレグレッション確認を最初に通す |

---

## 参考

- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- 主要 Commit (Phase 1 取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- 全体調査: `../peav-style-conditioning.md`
- Phase 2 計画: [phase-2.md](phase-2.md)
- Phase 3-4 計画: [phase-3-4.md](phase-3-4.md)
- Phase 5 計画: [phase-5.md](phase-5.md)
