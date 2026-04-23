# P4-T01: PE-A model loader + style bank loader 実装

| 項目 | 値 |
|------|-----|
| Phase | 4 |
| マイルストーン | [#14](https://github.com/ayutaz/piper-plus/milestone/14) |
| ステータス | 完了 |
| 優先度 | 高 |
| Claude Code 工数 | 2〜3h |
| 依存チケット | P0 (PE-A loader), P3-T02 (style bank 生成) |
| 後続チケット | P4-T02, P4-T03 |
| 関連 PR | PR-F |
| 期日 | 2026-05-02 |

## 1. タスク目的とゴール

### 1.1 目的

PE-A emotion loss を VITS 学習に統合する前段として、以下の 2 つのロード機構を実装する:

1. **PE-A model loader**: `facebook/pe-av-small` を lightning モジュールから遅延ロードする `_ensure_pea_emotion_model()` を実装。DAC (Discrete Audio Codec) の勾配制御を fork 実装 (`yusuke-ai/piper-plus` コミット `314b3355`) から忠実に移植する。
2. **Style bank loader**: P3-T02 で生成される `.npz` 形式の style bank (`emotion_names`, `emotion_centroids`, `global_centroid`) をロードし、`register_buffer()` で `VitsModel` に登録する `_init_pea_emotion_loss()` を実装。

Phase 0 で確定した PE-A API を起点に、Phase 3 の style bank 形式と整合する loader を構築することで、Phase 4 の残り工程 (loss 計算、training_step_g 統合、CLI 追加) の土台を提供する。

### 1.2 ゴール (Definition of Done)

- [ ] `src/python/piper_train/perception/pea_loader.py` が新規作成され、以下のユーティリティ関数を提供する
  - [ ] `load_pea_emotion_model(model_name: str) -> torch.nn.Module`
  - [ ] `load_style_bank(path: Path) -> tuple[list[str], torch.Tensor, torch.Tensor]`
  - [ ] `grad_enabled_embedder_forward(embedder, x)` (DAC 勾配制御ラッパー)
- [ ] `VitsModel.__init__` に `self._pea_emotion_model = None` と `self._pea_emotion_to_idx: dict[str, int] = {}` が追加されている
- [ ] `VitsModel._pea_emotion_loss_enabled` property が実装されている (3 つの weight のいずれかが > 0 のとき True)
- [ ] `VitsModel._init_pea_emotion_loss()` が `.npz` から以下を読み取り buffer に登録する
  - [ ] `pea_emotion_global_centroid` (`F.normalize(global_centroid, dim=-1)`)
  - [ ] `pea_emotion_centroids` (`F.normalize(emotion_centroids, dim=-1)`)
  - [ ] `self._pea_emotion_to_idx = {name: i for i, name in enumerate(emotion_names)}`
- [ ] `VitsModel._ensure_pea_emotion_model()` が遅延ロード対応 (2 回目以降の呼び出しはキャッシュを返す)
- [ ] style bank が指定されていない (`None`) かつ `_pea_emotion_loss_enabled == True` のときに `ValueError` を raise
- [ ] PE-A モデルは `eval()` モードかつ `.requires_grad_(False)` で凍結 (DAC 勾配制御は forward ラッパーで管理)
- [ ] ファイル単位の `python -c "from piper_train.perception.pea_loader import load_style_bank, load_pea_emotion_model, grad_enabled_embedder_forward"` で Syntax OK を確認

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `src/python/piper_train/perception/pea_loader.py` (新規、+120 行想定)
- `src/python/piper_train/perception/__init__.py` (新規、空ファイル)
- `src/python/piper_train/vits/lightning.py` (修正、+60 行想定)

### 2.2 実装手順

1. `src/python/piper_train/perception/` ディレクトリを作成し、`__init__.py` を空ファイルで作成
2. `pea_loader.py` を新規作成:
    - `load_pea_emotion_model(model_name, device=None)` を実装。`transformers.AutoModel.from_pretrained(..., trust_remote_code=True)` でロード後 `.eval()` + `.requires_grad_(False)` 設定
    - `load_style_bank(path)` を実装。`np.load(path, allow_pickle=True)` で 3 つの要素をロードし、`emotion_names` を `list[str]` に、2 つのセントロイドを `torch.Tensor` (float32) に変換して返す
    - `grad_enabled_embedder_forward(embedder, x)` を実装。fork の `314b3355` 実装を踏襲し `torch.cuda.amp.autocast(enabled=False)` と `torch.backends.cudnn.flags(enabled=False)` の 2 重 context で forward を包む
3. `lightning.py` の `VitsModel.__init__` に以下を追加 (style_condition_mode などの Phase 1 パラメータの後):
    - `self._pea_emotion_model: Optional[torch.nn.Module] = None`
    - `self._pea_emotion_to_idx: dict[str, int] = {}`
    - `if self._pea_emotion_loss_enabled: self._init_pea_emotion_loss()`
4. `_pea_emotion_loss_enabled` を property で定義。3 つの weight (`pea_emotion_loss_weight`, `pea_emotion_centroid_weight`, `pea_emotion_margin_weight`) のいずれかが `> 0` のときに True
5. `_init_pea_emotion_loss()` を実装:
    - `self.hparams.pea_emotion_style_bank` が `None` / 空文字のときに `ValueError("--pea-emotion-style-bank is required when PE-A loss is enabled")`
    - `load_style_bank(path)` を呼び出し、3 つの値を `register_buffer()` で登録 (normalize 済み)
    - `self._pea_emotion_to_idx` を構築
6. `_ensure_pea_emotion_model()` を実装:
    - `self._pea_emotion_model is not None` ならそのまま返す (キャッシュ)
    - `load_pea_emotion_model(self.hparams.pea_emotion_model_name)` でロード
    - `self._pea_emotion_model` に代入して返す
    - DAC 勾配制御は `_compute_pea_emotion_loss()` 側で `grad_enabled_embedder_forward` を明示的に呼び出す設計を選択 (モデル wrap は hparams snapshot 衝突を避けるため)

### 2.3 コード例 (phase-3-4.md §4.2 より)

```python
# src/python/piper_train/perception/pea_loader.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F

_LOGGER = logging.getLogger(__name__)


def load_pea_emotion_model(
    model_name: str = "facebook/pe-av-small",
    device: Optional[torch.device] = None,
) -> torch.nn.Module:
    """Load PE-A model from HuggingFace Hub (frozen, eval mode)."""
    from transformers import AutoModel

    _LOGGER.info("Loading PE-A emotion model: %s", model_name)
    model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
    model.eval()
    model.requires_grad_(False)
    if device is not None:
        model = model.to(device)
    return model


def load_style_bank(path: Path) -> tuple[list[str], torch.Tensor, torch.Tensor]:
    """Load emotion style bank from .npz file.

    Returns:
        emotion_names: list of emotion labels (e.g. ["angry", "happy", ...])
        emotion_centroids: FloatTensor [N, D] (not yet normalized)
        global_centroid: FloatTensor [D] (not yet normalized)
    """
    bank = np.load(str(Path(path)), allow_pickle=True)
    emotion_names = [str(name) for name in bank["emotion_names"].tolist()]
    emotion_centroids = torch.as_tensor(bank["emotion_centroids"], dtype=torch.float32)
    global_centroid = torch.as_tensor(bank["global_centroid"], dtype=torch.float32)
    return emotion_names, emotion_centroids, global_centroid


def grad_enabled_embedder_forward(embedder: torch.nn.Module, x: torch.Tensor) -> torch.Tensor:
    """Wrap PE-A embedder forward to control DAC gradients (fork 314b3355 踏襲)."""
    with torch.cuda.amp.autocast(enabled=False):
        with torch.backends.cudnn.flags(enabled=False):
            return embedder(x)
```

```python
# lightning.py に追加
@property
def _pea_emotion_loss_enabled(self) -> bool:
    return (
        self.hparams.pea_emotion_loss_weight > 0
        or self.hparams.pea_emotion_centroid_weight > 0
        or self.hparams.pea_emotion_margin_weight > 0
    )

def _init_pea_emotion_loss(self) -> None:
    if not self._pea_emotion_loss_enabled:
        return
    style_bank = self.hparams.pea_emotion_style_bank
    if not style_bank:
        raise ValueError(
            "--pea-emotion-style-bank is required when PE-A loss is enabled"
        )
    from piper_train.perception.pea_loader import load_style_bank
    emotion_names, emotion_centroids, global_centroid = load_style_bank(style_bank)
    self._pea_emotion_to_idx = {name: i for i, name in enumerate(emotion_names)}
    self.register_buffer(
        "pea_emotion_global_centroid", F.normalize(global_centroid, dim=-1)
    )
    self.register_buffer(
        "pea_emotion_centroids", F.normalize(emotion_centroids, dim=-1)
    )

def _ensure_pea_emotion_model(self):
    if self._pea_emotion_model is not None:
        return self._pea_emotion_model
    from piper_train.perception.pea_loader import load_pea_emotion_model
    self._pea_emotion_model = load_pea_emotion_model(
        self.hparams.pea_emotion_model_name
    )
    return self._pea_emotion_model
```

## 3. エージェントチーム構成

- **Implementation Agent**: 1 名 (Claude Code、`pea_loader.py` 新規 + `lightning.py` 修正)
  - Phase 0 の PoC 結果から PE-A モデルクラス名を確認し、`get_audio_embeds` の存在を前提にコードを書く
  - `register_buffer` の dtype (float32) と shape ([N, D], [D]) を厳密に合わせる
- **Verification Agent**: 1 名 (Claude Code、fork 実装との差分確認)
  - `yusuke-ai/piper-plus` コミット `314b3355` の `lightning.py:225-297` と diff レベルで一致することを確認
  - `grad_enabled_embedder_forward` の 2 重 context 順序 (autocast 外側、cudnn.flags 内側) が fork と同一

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| PE-A loader モジュール | `src/python/piper_train/perception/pea_loader.py` |
| perception パッケージ初期化 | `src/python/piper_train/perception/__init__.py` |
| lightning.py への init 追加 | `src/python/piper_train/vits/lightning.py` |

**提供範囲外**:
- 3 項合成 loss 計算 (P4-T02 で実装)
- training_step_g への loss 合算 + warmup (P4-T03 で実装)
- CLI オプション追加 (P4-T04 で実装)
- Unit テスト (P4-T05 で実装)

## 5. テスト項目

### 5.1 Unit テスト (P4-T05 で実装)

本チケットでは実装しないが、以下が P4-T05 で必須:

- `test_load_style_bank_schema`: `.npz` の 3 要素 (emotion_names, emotion_centroids, global_centroid) がロードされること
- `test_pea_loader_eval_mode`: `load_pea_emotion_model()` の戻り値が `training == False` かつ `requires_grad == False`
- `test_init_raises_without_style_bank`: `_pea_emotion_loss_enabled == True` かつ `pea_emotion_style_bank == None` で `ValueError`
- `test_buffer_registration`: `pea_emotion_centroids` / `pea_emotion_global_centroid` が `register_buffer` として登録され、`model.state_dict()` に含まれる

### 5.2 E2E テスト (本チケットのスモーク)

- `python -c "from piper_train.perception.pea_loader import load_style_bank, load_pea_emotion_model, grad_enabled_embedder_forward; print('ok')"` が成功
- `python -c "from piper_train.vits.lightning import VitsModel; print('ok')"` が成功
- Fork `314b3355` の該当箇所 (`lightning.py:218`, `225-258`, `261-297`) との diff が PE-A loss 以外で空

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **PE-A loss が NaN になって学習停止**: モデルロード時点では発生しないが、register_buffer した centroid の norm が 0 のとき `F.normalize` が NaN を返す可能性。fork 側はそのまま normalize しているので追従するが、P4-T05 で centroid norm > 1e-8 の境界テストを追加
- **GPU メモリ追加 (PE-A model 500MB-1GB)**: `_ensure_pea_emotion_model()` は最初の `_compute_pea_emotion_loss()` 呼び出し時にロードされる。`--pea-emotion-loss-weight 0.0` なら一切ロードされないことを property で保証
- **hparams snapshot の timing**: `_init_pea_emotion_loss()` は `save_hyperparameters()` より後に呼ばれる必要がある (CLAUDE.md の「`--freeze-dp` の hparams snapshot 問題」と同じパターン)。`VitsModel.__init__` の末尾近くで呼び出す
- **DAC 勾配制御の性能影響**: cuDNN 無効化は phase-3-4.md §4.3 で「-10〜20% 学習速度」と見積もり済み。P4-T03 の `every_n_steps 4` で緩和
- **direction loss の定義曖昧**: fork 側の実装は「target_centroid - global_centroid の方向」を target 方向としている (phase-3-4.md §4.2 L752-753)。独自解釈を避け、そのまま移植
- **transformers `trust_remote_code=True` 依存**: Phase 0 で動作確認済みのはずだが、環境変数 `HF_HUB_OFFLINE=1` 下ではロード不可。CI では `PIPER_SKIP_PE_AV_LOAD=1` のようなフラグで mock 化する余地あり (P4-T05 で検討)
- **`facebook/pe-av-small` API 名の差異**: `get_audio_embeds` 以外の可能性あり。Phase 0 の確定結果に従うが、fallback 実装 (`if hasattr(model, "get_audio_embeds"): ... else: ...`) を P4-T02 で入れるか要確認

### 6.2 レビュー項目

- [ ] `_pea_emotion_loss_enabled` property が 3 つの weight をすべて参照している
- [ ] `register_buffer` で登録された centroid は L2 normalize 済み (F.normalize)
- [ ] DAC 勾配制御ラッパーの 2 重 context 順序が fork と一致
- [ ] `_ensure_pea_emotion_model()` がキャッシュされる (2 回目以降 `from_pretrained` を呼ばない)
- [ ] `__init__` で `self._pea_emotion_model = None` が hparams snapshot 後に設定されている
- [ ] `pea_loader.py` がローカル import のみで syntax ok
- [ ] Phase 0 の loader 実装と重複するコードがあれば `pea_loader.py` 側に寄せる

## 7. 一から作り直すとしたら

### 7.1 代替案の検討

- **代替案 A**: PE-A embedding を pre-compute して dataset に埋め込み、学習時の PE-A model ロード自体を不要にする
  - 利点: GPU メモリ 500MB-1GB 削減、学習速度低下なし (cuDNN 無効化が不要)
  - 欠点: 生成音声 (y_hat) の embedding は学習中に抽出する必要があるため、PE-A model は結局必要。pre-compute できるのは target 側のみ
  - 結論: 本格的な削減にはならないが、validation 時の embedding キャッシュとしては有効。Phase 5 実験後に再検討
- **代替案 B**: PE-A model を LoRA でファインチューニングしながら使う
  - 利点: target embedding が VITS の出力分布に適応し、loss 収束が早まる可能性
  - 欠点: 学習不安定化リスク、LoRA 適用後の centroid 再計算が必要、fork との diff が大きい
  - 結論: Phase 4 の範囲外。Phase 5 の A/B 実験項目として検討
- **代替案 C**: style bank を `.npz` ではなく `.pt` (torch.save) で保存し、直接 Tensor として load
  - 利点: dtype 保持、メタデータ付与が容易
  - 欠点: fork と Phase 3 の実装が `.npz` 前提のため差分増大
  - 結論: Phase 3 の出力形式を尊重して `.npz` を維持
- **代替案 D**: WavLM features (既存の discriminator 用 WavLM モデル) を PE-A の代わりに使う
  - 利点: 既にロード済みのモデルを再利用、追加 GPU メモリなし
  - 欠点: WavLM は発話内容の音韻表現に強いが感情表現の分離は弱い (感情認識 task での f1 score が PE-A より低い想定)
  - 結論: Phase 4 の範囲外だが、「一から設計したら」の選択肢として記録

### 7.2 現在の実装を選んだ理由

- Fork (`yusuke-ai/piper-plus` `314b3355`) の PE-A loss 実装が `AutoModel.from_pretrained` 前提で書かれており、Phase 4 の loss 統合工数を最小化するため同じローダー構造を踏襲
- `.npz` 形式は Phase 3 で既に採択済み (CREMA-D 生成パイプラインが `np.savez` を使用)
- DAC 勾配制御は fork 実装の安定性に依存しており、独自解釈を避ける

### 7.3 リファクタ機会 (将来)

- `perception/` パッケージに PE-A 以外の audio encoder (WavLM, HuBERT, ECAPA-TDNN) を追加する際、共通インタフェース (`EmotionEncoder` ABC) として抽象化
- Phase 5 の実験結果次第で、`every_n_steps` や `warmup_steps` の動的調整ロジックを `PEALossScheduler` として切り出す

## 8. 後続タスクへの連絡事項

- **P4-T02 へ**: `self._ensure_pea_emotion_model()` と `self._pea_emotion_to_idx`、`self.pea_emotion_centroids`、`self.pea_emotion_global_centroid` (buffer) が利用可能。`get_audio_embeds` API 名は Phase 0 で確定済みの値を使用
- **P4-T03 へ**: `self._pea_emotion_loss_enabled` property で gating し、有効時のみ `_compute_pea_emotion_loss` を呼ぶ構造を training_step_g に追加すること
- **P4-T04 へ**: `pea_emotion_style_bank`, `pea_emotion_model_name` は `__init__` の kwargs として既に受け取る設計。CLI 側は `hparams` 経由で渡すだけで OK
- **P4-T05 へ**: 以下の API をテストで利用
  - `piper_train.perception.pea_loader.load_style_bank(path)`
  - `piper_train.perception.pea_loader.load_pea_emotion_model(name)`
  - `piper_train.perception.pea_loader.grad_enabled_embedder_forward(model, x)`
  - `VitsModel._pea_emotion_loss_enabled`
  - `VitsModel._init_pea_emotion_loss()`
  - `VitsModel._ensure_pea_emotion_model()`

## 9. 参考リンク

- Fork commit (取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- Fork 実装箇所 (推定): `lightning.py:218, 225-258, 261-297`
- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- phase-3-4.md §4.1 Fork からの移植マッピング
- phase-3-4.md §4.2 lightning.py への patch (概要)
- phase-3-4.md §4.3 DAC 勾配制御の検証
- Phase 0 (PE-A loader PoC): `tickets/phase-0/P0-T01.md`, `P0-T02.md`
- Phase 3 (style bank 生成): `tickets/phase-3/P3-T02-build-pea-style-bank.md`
- HF Hub: https://huggingface.co/facebook/pe-av-small
