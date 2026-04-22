# P4-T03: training_step_g への loss 合算 + warmup

| 項目 | 値 |
|------|-----|
| Phase | 4 |
| マイルストーン | [#14](https://github.com/ayutaz/piper-plus/milestone/14) |
| ステータス | 未着手 |
| 優先度 | 高 |
| Claude Code 工数 | 2〜3h |
| 依存チケット | P4-T01 (loader), P4-T02 (loss 計算) |
| 後続チケット | P4-T05 (テスト) |
| 関連 PR | PR-F |
| 期日 | 2026-05-02 |

## 1. タスク目的とゴール

### 1.1 目的

`VitsModel.training_step_g` に PE-A emotion loss を統合し、以下の機能を追加する:

1. **Generator loss への合算**: `_compute_pea_emotion_loss(y_hat, batch)` の戻り値を `loss_gen_all` に加算
2. **Warmup scheduling**: 最初 `pea_emotion_warmup_steps` (default 2000) は weight=0、その後線形に `c_pea_emotion` まで上昇
3. **every_n_steps による計算コスト削減**: `pea_emotion_loss_every_n_steps` (default 1、推奨 4) ごとに計算、他 step は skip
4. **NaN 検出時 skip**: `on_after_backward` で NaN/Inf を検出したら backward を skip + warning ログ
5. **wandb ログ**: `loss_pea_emotion` を total loss とは別に記録

Fork `yusuke-ai/piper-plus` コミット `314b3355` の `lightning.py:831-833` 実装を起点に、warmup / every_n_steps を含めて統合する。

### 1.2 ゴール (Definition of Done)

- [ ] `training_step_g` に `_compute_pea_emotion_loss` 呼び出しが追加されている
- [ ] PE-A loss の計算タイミングが以下の条件で gated されている:
  - [ ] `self.global_step < self.hparams.pea_emotion_warmup_steps` で None (warmup 中は計算自体をスキップ)
  - [ ] `self.global_step % max(1, self.hparams.pea_emotion_loss_every_n_steps) != 0` で None
- [ ] Warmup 線形ランプ: `weight_scale = min(1.0, (step - warmup_steps + ramp_length) / ramp_length)` またはシンプルに `step < warmup_steps: 0.0, else 1.0` のステップ関数
  - [ ] 本チケットでは**ステップ関数** (warmup 完了後一気に weight=full) を採用 (fork 実装踏襲)
  - [ ] 線形ランプはオプション (`pea_emotion_linear_ramp_steps` を追加する案も §7 に記載)
- [ ] PE-A loss が計算されたとき、`loss_gen_all = loss_gen_all + loss_pea_emotion` で加算
- [ ] wandb ログ: `self.log("loss_pea_emotion", loss_pea_emotion, on_step=True, on_epoch=True, prog_bar=True)`
- [ ] `on_after_backward` hook で gradient の NaN/Inf を検査し、検出時は `self.zero_grad()` + warning ログ
- [ ] `pea_emotion_loss_enabled == False` (全 weight=0) のとき、既存 training_step_g の挙動に影響を与えない (bit-for-bit 一致)

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `src/python/piper_train/vits/lightning.py` (修正、+40 行想定)

### 2.2 実装手順

1. `training_step_g` 内で、既存の Generator loss 計算 (`loss_gen_all = ...`) の**直後**に PE-A loss 呼び出しを追加
2. Warmup gating をメソッド内で実装:
    ```python
    warmup_steps = self.hparams.pea_emotion_warmup_steps
    every_n_steps = max(1, self.hparams.pea_emotion_loss_every_n_steps)
    if self.global_step < warmup_steps or self.global_step % every_n_steps != 0:
        loss_pea_emotion = None
    else:
        loss_pea_emotion = self._compute_pea_emotion_loss(y_hat, batch)
    ```
    - **設計判断**: warmup / every_n_steps の gating は `_compute_pea_emotion_loss` 内ではなく `training_step_g` 側で行う (loss 計算メソッドは純粋な数値計算に専念させるため)
3. Loss 加算:
    ```python
    if loss_pea_emotion is not None:
        loss_gen_all = loss_gen_all + loss_pea_emotion
        self.log(
            "loss_pea_emotion",
            loss_pea_emotion,
            on_step=True,
            on_epoch=True,
            prog_bar=True,
            sync_dist=True,
        )
    ```
4. `on_after_backward` hook を実装 (既存メソッドがあれば修正、なければ追加):
    ```python
    def on_after_backward(self):
        if not self._pea_emotion_loss_enabled:
            return
        for name, param in self.named_parameters():
            if param.grad is not None:
                if torch.isnan(param.grad).any() or torch.isinf(param.grad).any():
                    _LOGGER.warning(
                        "NaN/Inf gradient detected at step=%d param=%s, zeroing gradient",
                        self.global_step,
                        name,
                    )
                    self.zero_grad(set_to_none=True)
                    break
    ```
    - **注意**: `zero_grad` で全勾配をクリアすると optimizer.step() 時に何も更新されない。意図通り
5. `training_step_g` のシグネチャは変更せず、既存の loss 計算フローに挿入するだけ
6. Fork commit `314b3355` の `lightning.py:831-833` 該当箇所を確認し、diff が最小になるよう統合
7. **既存挙動への影響ゼロ確認**: `--pea-emotion-loss-weight 0.0` (default) の場合、`_pea_emotion_loss_enabled == False` で `_compute_pea_emotion_loss` は即 None 返却、loss_gen_all に変化なし

### 2.3 コード例

```python
# training_step_g 内の既存 loss 計算の直後に追加
# ... 既存の loss_gen_all = loss_fm + loss_mel + loss_kl + loss_gen_adv ...

# PE-A emotion loss (Phase 4)
loss_pea_emotion = None
if self._pea_emotion_loss_enabled:
    warmup_steps = self.hparams.pea_emotion_warmup_steps
    every_n_steps = max(1, self.hparams.pea_emotion_loss_every_n_steps)
    if (
        self.global_step >= warmup_steps
        and self.global_step % every_n_steps == 0
    ):
        loss_pea_emotion = self._compute_pea_emotion_loss(y_hat, batch)

if loss_pea_emotion is not None:
    loss_gen_all = loss_gen_all + loss_pea_emotion
    self.log(
        "loss_pea_emotion",
        loss_pea_emotion,
        on_step=True,
        on_epoch=True,
        prog_bar=True,
        sync_dist=True,
    )

# ... 既存の self.manual_backward(loss_gen_all) / return loss_gen_all ...


# on_after_backward hook (クラス全体に追加)
def on_after_backward(self):
    if not self._pea_emotion_loss_enabled:
        return
    # 既存処理があればそれも呼ぶ
    super().on_after_backward() if hasattr(super(), "on_after_backward") else None
    # NaN/Inf gradient check
    for name, param in self.named_parameters():
        if param.grad is not None:
            if torch.isnan(param.grad).any() or torch.isinf(param.grad).any():
                _LOGGER.warning(
                    "PE-A loss produced NaN/Inf gradient at step=%d (param=%s), "
                    "zeroing all gradients for this step",
                    self.global_step,
                    name,
                )
                self.zero_grad(set_to_none=True)
                return
```

## 3. エージェントチーム構成

- **Implementation Agent**: 1 名 (Claude Code、`lightning.py` の `training_step_g` + `on_after_backward` 修正)
  - Fork commit `314b3355` の `lightning.py:831-833` を確認して diff を最小化
  - 既存の `loss_gen_all` 計算ロジック (loss_fm / loss_mel / loss_kl / loss_gen_adv) を理解して正しい位置に挿入
- **Verification Agent**: 1 名 (Claude Code、既存挙動との整合確認)
  - `--pea-emotion-loss-weight 0.0` で training_step_g の挙動が変わらない (bit-for-bit loss 一致) ことを確認
  - `automatic_optimization` (自動 or manual) の設定によって backward 呼び出しが異なる点をレビュー
  - `sync_dist=True` が DDP でのログ集約に必要 (`--devices 4`)

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| training_step_g 統合 | `src/python/piper_train/vits/lightning.py` |
| on_after_backward hook | `src/python/piper_train/vits/lightning.py` |

**提供範囲外**:
- Loader 実装 (P4-T01 で完了)
- 3 項 loss 計算本体 (P4-T02 で完了)
- CLI オプション 9 個 (P4-T04 で実装)
- Unit テスト (P4-T05 で実装)

## 5. テスト項目

### 5.1 Unit テスト (P4-T05 で実装)

本チケットでは実装しないが、以下が P4-T05 で必須:

- `test_warmup_returns_none_below_threshold`: `global_step < warmup_steps` で loss が None (training_step_g 内の gating)
- `test_every_n_steps_skip`: `global_step % every_n_steps != 0` で loss が None
- `test_loss_accumulation`: `_compute_pea_emotion_loss` が非 None のとき `loss_gen_all` に加算される
- `test_disabled_no_overhead`: `--pea-emotion-enabled=False` で既存学習に影響なし (loss_gen_all が Phase 1 時点と bit-for-bit 一致)
- `test_nan_gradient_triggers_zero_grad`: NaN gradient 検出時 `zero_grad` が呼ばれる
- `test_warmup_linear_ramp` (§1.2 で線形ランプ採用時のみ): `step=0` で `weight_scale=0`, `step=warmup_steps` で `weight_scale=1.0` (本チケットはステップ関数採用のため ramp テストは不要、代替として `test_warmup_step_function` を追加)

### 5.2 E2E テスト (本チケットのスモーク)

- `--pea-emotion-loss-weight 0.0` で既存 dry-run (1 epoch) が NaN なく完走
- `--pea-emotion-loss-weight 0.1 --pea-emotion-style-bank <path>` で 100 step dry-run が完走 (warmup 中のため loss=0)
- `--pea-emotion-warmup-steps 50 --pea-emotion-loss-weight 0.1` で 100 step dry-run で step 50 以降に `loss_pea_emotion` が wandb に記録される

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **PE-A loss が NaN になって学習停止 (warmup + NaN guard で対策)**: `_compute_pea_emotion_loss` 側の NaN ガードは loss 値のみを検査。backward 後の gradient に NaN が発生するケースは `on_after_backward` でカバー。両方の層で防御する
- **GPU メモリ追加 (PE-A model 500MB-1GB)**: `_ensure_pea_emotion_model()` は warmup 完了後の最初の step でロード。DDP (`--devices 4`) では各 GPU に個別ロードされるため、総計 2-4GB 追加。V100 16GB での余裕確認が必要
- **loss 計算が重く、学習速度低下 (every_n_steps 4 で対策)**: V100 での概算: PE-A forward ~50ms/batch × every_n_steps=4 → 平均 12.5ms/step オーバーヘッド。Base VITS step (~200ms) の 6% 程度で許容範囲
- **direction loss の定義曖昧 (fork 側の実装を要確認)**: P4-T02 §6.1 で明記済み。training_step_g 側では loss 値をそのまま加算するだけなので本チケットでは影響なし
- **DDP での sync_dist**: `self.log(..., sync_dist=True)` で 4 GPU の loss が正しく集約されることを確認。`sync_dist=False` だと rank=0 のログのみ記録される
- **`automatic_optimization=False` の場合**: Piper-plus の training_step_g は manual backward の可能性あり。その場合 `self.manual_backward(loss_gen_all)` への影響を確認
- **`loss_gen_all` の gradient scale**: PE-A loss のスケール (0〜1 程度) が既存の loss_gen_adv (数値 0.1〜5 程度) と同程度かを確認。過小なら weight を上げる必要あり (fork 実装の `pea_emotion_loss_weight=0.1` が妥当性の根拠)
- **warmup step のカウント**: `self.global_step` は optimizer.step() のカウント。DDP では各 rank で同じ値になるはず (Lightning の仕様)
- **on_after_backward の位置**: Lightning の `automatic_optimization` モードでは `manual_backward` 後に hook が呼ばれる。`automatic_optimization=False` (manual) では明示的に `self.manual_backward()` 後に `self.on_after_backward()` を呼ぶ必要があるかも。Lightning バージョンで挙動差あり、PyTorch Lightning 2.x では automatic に呼ばれる

### 6.2 レビュー項目

- [ ] `_compute_pea_emotion_loss` 呼び出しが `loss_gen_all` の計算直後に配置されている
- [ ] warmup / every_n_steps の gating が正しく (`>= warmup_steps` かつ `step % every_n_steps == 0`)
- [ ] `loss_pea_emotion is not None` のガード後に加算とログ出力
- [ ] `sync_dist=True` が指定されている (DDP 対応)
- [ ] `on_after_backward` で NaN/Inf 検出時 `zero_grad(set_to_none=True)` を呼ぶ
- [ ] `--pea-emotion-loss-weight 0.0` で既存 training_step_g の挙動に影響なし
- [ ] fork commit `314b3355` の `lightning.py:831-833` との diff が loss 加算箇所で一致

## 7. 一から作り直すとしたら

### 7.1 代替案の検討

- **代替案 A**: Warmup を線形ランプ化 (step function → linear ramp)
  - 実装: `weight_scale = min(1.0, (step - warmup_steps) / linear_ramp_steps)`
  - 利点: 学習初期の急激な loss 変動を避け、収束が安定
  - 欠点: CLI オプション追加 (`--pea-emotion-linear-ramp-steps`)、fork 実装との diff 増大
  - 結論: 本チケットでは fork 踏襲 (step function)。Phase 5 の実験で不安定なら P4-T04 で追加検討
- **代替案 B**: Warmup scheduling を LearningRateScheduler 風の Callback に切り出し
  - 実装: `PEALossWarmupCallback` を `configure_callbacks()` で登録
  - 利点: lightning.py の複雑度が下がる、複数の warmup ポリシーを切り替え可能
  - 欠点: fork 実装とのずれが大きい、レビュー負荷増
  - 結論: リファクタ候補として §7.3 に記録
- **代替案 C**: every_n_steps の代わりに gradient accumulation
  - 実装: 4 step 分の PE-A loss を accumulate してから backward
  - 利点: 4 step 全てで loss を計算するため情報損失なし
  - 欠点: GPU メモリ 4 倍、実装複雑
  - 結論: 不採用
- **代替案 D**: NaN ガードを on_before_backward で実施 (backward 前に loss 値をチェック)
  - Loss 値のチェックは既に `_compute_pea_emotion_loss` 内で実施済み
  - Backward 後の gradient チェックは `on_after_backward` でカバー
  - 両方の層で防御済みなので追加不要

### 7.2 現在の実装を選んだ理由

- Fork commit `314b3355` の実装は step function warmup を採用しており、実験的に動作確認済み
- Warmup 完了後の weight=full が loss 計算の意図を明確にする (線形ランプは実装複雑度の割にメリット限定的)
- `on_after_backward` hook は Lightning 2.x で標準的な NaN handling 方式

### 7.3 リファクタ機会 (将来)

- `PEALossScheduler` Callback を新設し、warmup / every_n_steps / NaN handling を分離
- `loss_pea_emotion_dir`, `loss_pea_emotion_centroid`, `loss_pea_emotion_margin` を個別に wandb ログ (Phase 5 のデバッグに有用)
- warmup を線形ランプ化 (CLI オプション `--pea-emotion-linear-ramp-steps`)
- `--pea-emotion-warmup-steps` を epoch ベースに変更 (現状 step ベース、epoch が直感的)

## 8. 後続タスクへの連絡事項

- **P4-T04 へ**: CLI オプション 9 個のうち、`--pea-emotion-warmup-steps` と `--pea-emotion-loss-every-n-steps` は本チケットの gating ロジックで参照される。デフォルト値 `warmup_steps=0` (fork 実装)、`every_n_steps=1` (毎 step) を維持、ユーザ推奨値は `2000` と `4`
- **P4-T05 へ**: 以下のテストを実装
  - `test_warmup_returns_none_below_threshold`
  - `test_every_n_steps_skip`
  - `test_loss_accumulation`
  - `test_disabled_no_overhead` (最重要、既存挙動との bit-for-bit 一致)
  - `test_nan_gradient_triggers_zero_grad`
- **Phase 5 (PR-G) へ**: CREMA-D fine-tune コマンドに `--pea-emotion-warmup-steps 2000` + `--pea-emotion-loss-every-n-steps 4` + `--pea-emotion-loss-weight 0.1` + `--pea-emotion-centroid-weight 0.1` + `--pea-emotion-margin-weight 0.05` を推奨プリセットとして指定 (phase-3-4.md §4.5)

## 9. 参考リンク

- Fork commit (取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- Fork 実装箇所 (推定): `lightning.py:831-833` (`training_step_g` への loss 統合)
- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- phase-3-4.md §4.2 `training_step_g` への統合
- phase-3-4.md §4.5 推奨プリセット
- P4-T01: `tickets/phase-4/P4-T01-pea-loader-style-bank.md`
- P4-T02: `tickets/phase-4/P4-T02-compute-pea-emotion-loss.md`
- Lightning `on_after_backward`: https://lightning.ai/docs/pytorch/stable/common/lightning_module.html#on-after-backward
