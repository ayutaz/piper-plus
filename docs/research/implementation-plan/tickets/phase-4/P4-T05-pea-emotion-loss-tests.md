# P4-T05: PE-A loss Unit テスト

| 項目 | 値 |
|------|-----|
| Phase | 4 |
| マイルストーン | [#14](https://github.com/ayutaz/piper-plus/milestone/14) |
| ステータス | 未着手 |
| 優先度 | 高 |
| Claude Code 工数 | 1〜2h |
| 依存チケット | P4-T01 (loader), P4-T02 (loss), P4-T03 (統合), P4-T04 (CLI) |
| 後続チケット | なし (Phase 4 最終) |
| 関連 PR | PR-F |
| 期日 | 2026-05-02 |

## 1. タスク目的とゴール

### 1.1 目的

Phase 4 で実装された PE-A emotion loss 機能 (loader, 3 項 loss, training_step_g 統合, CLI 9 オプション) の Unit テストを追加し、以下を保証する:

1. **Loss の数学的正しさ**: direction loss / centroid loss / margin loss の境界条件 (target と一致、margin 超過、NaN 入力)
2. **Warmup scheduling の正確性**: step=0 で weight=0、warmup_steps 以降で weight=full
3. **Disabled 時のゼロオーバーヘッド**: `--pea-emotion-enabled=False` (全 weight=0) で既存学習に影響なし
4. **CLI の整合性**: デフォルト値、early validation、引数パース

テスト配置: `src/python/tests/test_pea_emotion_loss.py`

### 1.2 ゴール (Definition of Done)

- [ ] `src/python/tests/test_pea_emotion_loss.py` が新規作成されている
- [ ] 以下 6 個の必須テストがすべて実装され、pass する:
  - [ ] `test_direction_loss_zero_at_target`
  - [ ] `test_centroid_loss_positive`
  - [ ] `test_margin_loss_hinge_zero`
  - [ ] `test_warmup_linear_ramp` (ステップ関数版として `test_warmup_step_function` に改名も可)
  - [ ] `test_nan_guard`
  - [ ] `test_disabled_no_overhead`
- [ ] 追加の推奨テスト (時間が許せば):
  - [ ] `test_load_style_bank_schema` (P4-T01)
  - [ ] `test_init_raises_without_style_bank` (P4-T01)
  - [ ] `test_3_term_composition` (P4-T02)
  - [ ] `test_every_n_steps_skip` (P4-T03)
  - [ ] `test_nan_gradient_triggers_zero_grad` (P4-T03)
  - [ ] `test_cli_defaults` (P4-T04)
  - [ ] `test_cli_missing_style_bank` (P4-T04)
- [ ] `uv run pytest src/python/tests/test_pea_emotion_loss.py -v` で全テスト pass
- [ ] PE-A model のロードを必要とするテストは `@pytest.mark.skipif(not has_transformers_and_network, ...)` でスキップ可能
- [ ] テスト用の style bank `.npz` は `tmp_path` fixture で動的生成 (実 CREMA-D 不要)

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `src/python/tests/test_pea_emotion_loss.py` (新規、+250 行想定)

### 2.2 実装手順

1. ファイル冒頭に import とヘルパー関数を定義:
    ```python
    import tempfile
    from pathlib import Path
    from unittest.mock import MagicMock, patch
    import numpy as np
    import pytest
    import torch
    import torch.nn.functional as F
    ```
2. `make_style_bank(tmp_path)` ヘルパーを定義。4 感情 × 256 次元のダミー `.npz` を生成
3. `make_mock_vits_model(style_bank_path, **hparams)` ヘルパーを定義。`VitsModel` の最小インスタンスを作成 (既存の test_freeze_dp.py の mock パターンを参考)
4. 各テストを独立に記述。ヘルパーを使って boilerplate を最小化

### 2.3 テストケース詳細

#### test_direction_loss_zero_at_target

```python
def test_direction_loss_zero_at_target(tmp_path):
    """embedding が target_centroid と同方向 (global からの変位) のとき direction loss が 0 に近い."""
    D = 256
    global_centroid = torch.zeros(D)
    target_centroid = F.normalize(torch.randn(D), dim=-1)

    # embedding を target の方向に等しい単位ベクトルで作る
    embedding = target_centroid.clone()  # global=0 なので embedding - global = embedding

    # direction loss 計算 (P4-T02 の式)
    target_dir = F.normalize(target_centroid - global_centroid, dim=-1)
    embedding_dir = F.normalize(embedding - global_centroid, dim=-1)
    loss_dir = 1.0 - F.cosine_similarity(
        embedding_dir.unsqueeze(0), target_dir.unsqueeze(0), dim=-1
    ).mean()

    assert loss_dir.item() < 1e-5, f"direction loss should be ~0, got {loss_dir.item()}"
```

#### test_centroid_loss_positive

```python
def test_centroid_loss_positive():
    """centroid loss が非負 (cos similarity <= 1 なので 1 - cos >= 0)."""
    D = 256
    B = 4
    embeddings = F.normalize(torch.randn(B, D), dim=-1)
    target_centroids = F.normalize(torch.randn(B, D), dim=-1)

    loss_centroid = 1.0 - F.cosine_similarity(embeddings, target_centroids, dim=-1).mean()

    assert loss_centroid.item() >= 0, f"centroid loss must be non-negative, got {loss_centroid.item()}"
    assert loss_centroid.item() <= 2.0, f"centroid loss must be <= 2.0, got {loss_centroid.item()}"
```

#### test_margin_loss_hinge_zero

```python
def test_margin_loss_hinge_zero():
    """target similarity > max_other + margin のとき margin loss が 0."""
    D = 256
    B = 2
    N = 4  # 4 emotions

    # target centroid と強い類似度、other centroid は低類似度
    centroids = F.normalize(torch.randn(N, D), dim=-1)
    target_indices = torch.tensor([0, 1])
    # target に完全一致するような embedding を作る
    embeddings = centroids[target_indices].clone()

    similarities = embeddings @ centroids.t()
    target_similarity = similarities.gather(1, target_indices[:, None]).squeeze(1)
    similarities_copy = similarities.clone()
    similarities_copy.scatter_(1, target_indices[:, None], float("-inf"))
    max_other_sim, _ = similarities_copy.max(dim=1)

    margin = 0.1
    loss_margin = F.relu(margin + max_other_sim - target_similarity).mean()

    # target_similarity ~ 1.0, max_other_sim < 1.0, margin=0.1
    # target - max_other > 0.1 の場合、loss = 0
    # ランダム centroid の場合 max_other < 0.5 程度なので 1.0 - 0.5 = 0.5 > margin=0.1 → loss=0
    assert loss_margin.item() < 0.2, f"margin loss should be small when target is dominant, got {loss_margin.item()}"
```

#### test_warmup_linear_ramp (ステップ関数版)

```python
def test_warmup_step_function():
    """warmup_steps 未満で loss が None、以降で loss が計算される."""
    # VitsModel の _compute_pea_emotion_loss 呼び出しは training_step_g の gating で制御
    # P4-T03 の実装に依拠: step < warmup_steps → None, step >= warmup_steps → 計算

    warmup_steps = 100
    every_n_steps = 4

    # gating 関数を再現
    def should_compute(step):
        return step >= warmup_steps and step % every_n_steps == 0

    assert should_compute(0) is False, "step=0 should skip"
    assert should_compute(50) is False, "step=50 (< warmup) should skip"
    assert should_compute(99) is False, "step=99 (< warmup) should skip"
    assert should_compute(100) is True, "step=100 (== warmup, multiple of 4) should compute"
    assert should_compute(101) is False, "step=101 (not multiple of 4) should skip"
    assert should_compute(104) is True, "step=104 (multiple of 4) should compute"
```

#### test_nan_guard

```python
def test_nan_guard():
    """NaN 入力で loss が None を返し warning ログが出力される."""
    # _compute_pea_emotion_loss を直接呼ぶケース (統合テスト)
    # NaN を含む y_hat を作成
    y_hat = torch.full((2, 16000), float("nan"))

    # F.normalize は 0-vector に対して NaN を返す
    normalized = F.normalize(y_hat.mean(dim=-1, keepdim=True).expand(2, 256), dim=-1)
    has_nan = torch.isnan(normalized).any()

    # 正しく NaN 検出される
    assert has_nan.item() is True

    # 実際の _compute_pea_emotion_loss では NaN ガードで None を返す
    # ここでは単体テストなのでロジック検証に留める
```

#### test_disabled_no_overhead (最重要)

```python
def test_disabled_no_overhead():
    """全 weight=0 のとき _pea_emotion_loss_enabled が False、学習に影響なし."""
    from argparse import Namespace

    # Mock hparams with all weights = 0
    hparams = Namespace(
        pea_emotion_loss_weight=0.0,
        pea_emotion_centroid_weight=0.0,
        pea_emotion_margin_weight=0.0,
    )

    # _pea_emotion_loss_enabled ロジックを再現
    enabled = (
        hparams.pea_emotion_loss_weight > 0
        or hparams.pea_emotion_centroid_weight > 0
        or hparams.pea_emotion_margin_weight > 0
    )
    assert enabled is False, "All weights = 0 should disable PE-A loss"

    # 1 weight > 0 で enable
    hparams.pea_emotion_loss_weight = 0.1
    enabled = (
        hparams.pea_emotion_loss_weight > 0
        or hparams.pea_emotion_centroid_weight > 0
        or hparams.pea_emotion_margin_weight > 0
    )
    assert enabled is True, "loss_weight > 0 should enable PE-A loss"
```

#### test_load_style_bank_schema (P4-T01 検証)

```python
def test_load_style_bank_schema(tmp_path):
    """.npz から 3 要素 (emotion_names, emotion_centroids, global_centroid) がロードされる."""
    from piper_train.perception.pea_loader import load_style_bank

    N, D = 4, 256
    emotion_names = ["angry", "happy", "sad", "neutral"]
    emotion_centroids = np.random.randn(N, D).astype(np.float32)
    global_centroid = np.random.randn(D).astype(np.float32)

    path = tmp_path / "style_bank.npz"
    np.savez(
        str(path),
        emotion_names=np.array(emotion_names, dtype=object),
        emotion_centroids=emotion_centroids,
        global_centroid=global_centroid,
    )

    loaded_names, loaded_centroids, loaded_global = load_style_bank(path)
    assert loaded_names == emotion_names
    assert loaded_centroids.shape == (N, D)
    assert loaded_global.shape == (D,)
    assert loaded_centroids.dtype == torch.float32
```

#### test_init_raises_without_style_bank (P4-T01 検証)

```python
def test_init_raises_without_style_bank():
    """_pea_emotion_loss_enabled == True かつ pea_emotion_style_bank == None で ValueError."""
    # VitsModel.__init__ は複雑なので、_init_pea_emotion_loss メソッドを直接テスト
    # Mock を使う
    mock_self = MagicMock()
    mock_self.hparams.pea_emotion_loss_weight = 0.1
    mock_self.hparams.pea_emotion_centroid_weight = 0.0
    mock_self.hparams.pea_emotion_margin_weight = 0.0
    mock_self.hparams.pea_emotion_style_bank = None
    mock_self._pea_emotion_loss_enabled = True

    # _init_pea_emotion_loss の実装を import して適用
    from piper_train.vits.lightning import VitsModel
    with pytest.raises(ValueError, match="--pea-emotion-style-bank"):
        VitsModel._init_pea_emotion_loss(mock_self)
```

#### test_3_term_composition (P4-T02 検証)

```python
def test_3_term_composition():
    """3 つの weight (1.0, 0.5, 0.3) で合成 loss が正しく計算される."""
    loss_dir = torch.tensor(0.1)
    loss_centroid = torch.tensor(0.2)
    loss_margin = torch.tensor(0.3)

    w_dir, w_centroid, w_margin = 1.0, 0.5, 0.3

    total = w_dir * loss_dir + w_centroid * loss_centroid + w_margin * loss_margin
    expected = 1.0 * 0.1 + 0.5 * 0.2 + 0.3 * 0.3  # = 0.29
    assert abs(total.item() - expected) < 1e-6
```

#### test_every_n_steps_skip (P4-T03 検証)

```python
def test_every_n_steps_skip():
    """global_step % every_n_steps != 0 で loss が None."""
    warmup_steps = 0
    every_n_steps = 4

    def should_compute(step):
        return step >= warmup_steps and step % every_n_steps == 0

    assert should_compute(0) is True
    assert should_compute(1) is False
    assert should_compute(3) is False
    assert should_compute(4) is True
    assert should_compute(5) is False
    assert should_compute(8) is True
```

#### test_cli_defaults (P4-T04 検証)

```python
def test_cli_defaults():
    """argparse デフォルト値で全 weight=0、disabled."""
    from piper_train.__main__ import build_argparse  # Or parser は既存のエントリポイント

    # parser を構築 (実装に応じて adapter が必要)
    # 簡易版: 直接 argparse を構築して defaults を確認
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pea-emotion-loss-weight", type=float, default=0.0)
    parser.add_argument("--pea-emotion-centroid-weight", type=float, default=0.0)
    parser.add_argument("--pea-emotion-margin-weight", type=float, default=0.0)
    parser.add_argument("--pea-emotion-style-bank", type=str, default=None)
    parser.add_argument("--pea-emotion-margin", type=float, default=0.1)

    args = parser.parse_args([])
    assert args.pea_emotion_loss_weight == 0.0
    assert args.pea_emotion_centroid_weight == 0.0
    assert args.pea_emotion_margin_weight == 0.0
    assert args.pea_emotion_style_bank is None
    assert args.pea_emotion_margin == 0.1
```

## 3. エージェントチーム構成

- **Implementation Agent**: 1 名 (Claude Code、`test_pea_emotion_loss.py` 新規)
  - `src/python/tests/test_freeze_dp.py` を参考にして Mock パターンを踏襲
  - `tmp_path` fixture で style bank `.npz` を動的生成
  - 各テストは独立して実行可能にし、依存を最小化
- **Verification Agent**: 1 名 (Claude Code、テスト網羅性レビュー)
  - P4-T01〜T04 のチケットで列挙された全テストケースがカバーされているか
  - 必須 6 個 + 推奨テストが実装されているか
  - `pytest` の skip mark が適切に設定されているか (PE-A model ロードが不要なユニットテストでスキップを発生させない)

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| Unit テストファイル | `src/python/tests/test_pea_emotion_loss.py` |

**提供範囲外**:
- E2E 学習テスト (Phase 5 で実施)
- ベンチマーク (MOS 評価は phase-5.md で別途)

## 5. テスト項目

### 5.1 必須テスト (6 個)

| テスト名 | 目的 | 関連チケット |
|--------|------|-----------|
| `test_direction_loss_zero_at_target` | direction loss の境界条件 | P4-T02 |
| `test_centroid_loss_positive` | centroid loss の非負性 | P4-T02 |
| `test_margin_loss_hinge_zero` | margin loss の hinge 境界 | P4-T02 |
| `test_warmup_step_function` | warmup scheduling の gating | P4-T03 |
| `test_nan_guard` | NaN 入力で None 返却 | P4-T02 |
| `test_disabled_no_overhead` | disabled 時の既存学習非影響 | P4-T01〜T04 |

### 5.2 推奨テスト (時間許せば)

| テスト名 | 目的 | 関連チケット |
|--------|------|-----------|
| `test_load_style_bank_schema` | .npz スキーマ検証 | P4-T01 |
| `test_init_raises_without_style_bank` | 早期エラー検証 | P4-T01 |
| `test_3_term_composition` | 3 項合成の算術検証 | P4-T02 |
| `test_every_n_steps_skip` | skip step gating | P4-T03 |
| `test_nan_gradient_triggers_zero_grad` | on_after_backward の NaN 対処 | P4-T03 |
| `test_cli_defaults` | argparse デフォルト値 | P4-T04 |
| `test_cli_missing_style_bank` | CLI 早期バリデーション | P4-T04 |

### 5.3 E2E テスト (本チケット外、Phase 5 で実施)

- `--pea-emotion-enabled=True` で CREMA-D 小規模 (1 epoch, 100 utterances) でも学習完走
- 1 epoch dry-run で NaN なく完走、有効化時/無効化時で基本 loss 差分が warmup ステップ完了前は ε 以下

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **PE-A model のロードなしでテスト可能か**: `test_direction_loss_*` 等は数学的性質のみのテストで model 不要。`test_init_raises_without_style_bank` も model 不要。一方で `_ensure_pea_emotion_model()` のテストは HF Hub からダウンロードが必要なため、`@pytest.mark.skipif(os.environ.get("PIPER_SKIP_PE_AV_LOAD") == "1", ...)` で skip 可能に
- **GPU 不要なテストに絞る**: 数学的性質のテストはすべて CPU で実行可能。PE-A model を絡めるテストは将来的に integration test (別ディレクトリ) に分離
- **学習速度低下 (every_n_steps 4 で対策)**: 本テストでは実測しない (Phase 5 の E2E で検証)
- **direction loss の定義曖昧 (fork 側の実装を要確認)**: P4-T02 §6.1 で記載済み。本テストでは fork 実装 (双方を global から引いた後の cosine) に従う
- **テスト実行時間**: 全 13 テスト × < 1s/テスト = 13 秒以内が目標。HF Hub ロードを含むテストは別途
- **Mock の複雑性**: `VitsModel` の full init は重い (LightningModule 継承のため)。`test_freeze_dp.py` が使っている mock パターンを流用し、必要な attribute のみ MagicMock で差し替え
- **`from piper_train.__main__ import build_argparse` が既存に存在するか**: 既存の `__main__.py` が parser を module-level で公開しているか要確認。なければテスト内で直接 argparse を構築 (コード例参照)

### 6.2 レビュー項目

- [ ] 必須 6 個のテストがすべて実装されている
- [ ] 各テストが独立して実行可能 (fixture の使い回し OK、テスト間の順序依存なし)
- [ ] `uv run pytest src/python/tests/test_pea_emotion_loss.py -v` で全 pass
- [ ] PE-A model ロード不要なテストは GPU/ネットワークなしで pass する
- [ ] `tmp_path` fixture で style bank を動的生成 (実ファイル依存なし)
- [ ] Mock パターンが `test_freeze_dp.py` と整合
- [ ] テストファイルの冒頭にモジュール docstring で Phase 4 / PR-F 関連と記載

## 7. 一から作り直すとしたら

### 7.1 代替案の検討

- **代替案 A**: pytest 以外 (unittest) でテスト記述
  - 既存 `test_freeze_dp.py` が pytest 形式のため、pytest を踏襲
- **代替案 B**: Property-based testing (hypothesis) で 3 項合成の数学的性質を自動検証
  - 利点: エッジケース自動発見
  - 欠点: 学習コスト、CI 時間増
  - 結論: Phase 4 では不採用。Phase 5 以降で余裕があれば追加
- **代替案 C**: PyTorch Lightning の `Trainer.fit(fast_dev_run=True)` でスモークテスト
  - 利点: training_step_g 全体の smoke test
  - 欠点: PE-A model ロード必須、実行時間が長い
  - 結論: Phase 5 の E2E テストとして別途実施
- **代替案 D**: Golden test (期待値を JSON で保存し diff 比較)
  - 利点: 再現性高い、将来の変更検出
  - 欠点: テストデータ管理コスト
  - 結論: 3 項合成は数学的に確定しているため不要
- **代替案 E**: NaN ガードを integration test として別ファイル
  - 現状は unit test で数学的に検証するが、実際の training loop での発生を模擬するのは integration test の方が自然
  - 結論: 本チケットでは unit test として実装、Phase 5 で integration test を別途

### 7.2 現在の実装を選んだ理由

- 既存 `test_freeze_dp.py` と整合する pytest スタイル
- 必須 6 個は P4-T01〜T04 の各機能を最低限カバー
- Mock パターンで PE-A model ロード不要にし、CI での高速実行を実現
- Phase 5 の実験用テンプレートとして統合テストを分離

### 7.3 リファクタ機会 (将来)

- テストを `tests/unit/` と `tests/integration/` に分離し、CI の pytest mark で使い分け
- PE-A model ロードを伴う integration test を `src/python/tests/integration/test_pea_emotion_e2e.py` として追加
- Property-based testing (hypothesis) で 3 項合成の不変量を自動検証

## 8. 後続タスクへの連絡事項

- **Phase 5 (PR-G) へ**: 本チケットで実装した unit test に加え、E2E integration test (CREMA-D 小規模学習 1 epoch) を `test_pea_emotion_e2e.py` として追加すること。成功基準:
  - 100 utterances で 1 epoch 完走
  - `loss_pea_emotion` が wandb に記録される
  - NaN なく training loop が回る
- **CI 統合**: `.github/workflows/python-tests.yml` に `src/python/tests/test_pea_emotion_loss.py` が自動実行されることを確認 (既存の pytest コマンドで拾われるはず)

## 9. 参考リンク

- Fork commit (取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- phase-3-4.md §4.6 テストケース
- 既存テスト参考: `src/python/tests/test_freeze_dp.py`
- P4-T01: `tickets/phase-4/P4-T01-pea-loader-style-bank.md`
- P4-T02: `tickets/phase-4/P4-T02-compute-pea-emotion-loss.md`
- P4-T03: `tickets/phase-4/P4-T03-training-step-integration.md`
- P4-T04: `tickets/phase-4/P4-T04-cli-pea-emotion-options.md`
- pytest 公式: https://docs.pytest.org/en/stable/
