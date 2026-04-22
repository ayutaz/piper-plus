# P4-T02: _compute_pea_emotion_loss 実装 (3項合成)

| 項目 | 値 |
|------|-----|
| Phase | 4 |
| マイルストーン | [#14](https://github.com/ayutaz/piper-plus/milestone/14) |
| ステータス | 未着手 |
| 優先度 | 高 |
| Claude Code 工数 | 2〜3h |
| 依存チケット | P4-T01 (loader 実装) |
| 後続チケット | P4-T03 (training_step_g 統合), P4-T05 (テスト) |
| 関連 PR | PR-F |
| 期日 | 2026-05-02 |

## 1. タスク目的とゴール

### 1.1 目的

VITS の Generator 出力 (`y_hat`) から PE-A embedding を抽出し、target 感情 centroid との距離ベースの 3 項合成 loss を計算する `_compute_pea_emotion_loss()` を実装する。Fork `yusuke-ai/piper-plus` コミット `314b3355` の `lightning.py:298-375` 実装を忠実に移植。

3 項の内訳:
- **direction loss**: `1 - cosine(embedding_dir, target_dir)` ただし dir は `F.normalize(vec - global_centroid, dim=-1)`
- **centroid loss**: `1 - cosine(embedding, target_centroid)` (L2 normalize 後の cosine)
- **margin loss**: `ReLU(margin + max_other_sim - target_sim)` (hinge, scatter ベース実装)

合成 loss: `w_direction * L_d + w_centroid * L_c + w_margin * L_m`

本チケットは loss 計算ロジック単体の実装に集中し、training_step_g への統合・warmup・every_n_steps は P4-T03 で行う。

### 1.2 ゴール (Definition of Done)

- [ ] `VitsModel._compute_pea_emotion_loss(y_hat, batch)` が実装されている
- [ ] 戻り値は `Optional[torch.Tensor]` (scalar)。disable 時・warmup 中・skip step 中・batch.emotions 未設定時は `None` を返す (※ warmup/skip は P4-T03 でgate、本チケットでは loss 計算本体のみ)
- [ ] `batch.emotions` 内で `_pea_emotion_to_idx` に存在する有効サンプルのみを抽出する
- [ ] `y_hat` を VITS sample_rate から `pea_emotion_sample_rate` (16000) に `torchaudio.functional.resample` でリサンプリング
- [ ] `grad_enabled_embedder_forward` (P4-T01) を経由して embedding 抽出 (DAC 勾配制御)
- [ ] `F.normalize(embeddings, dim=-1)` で L2 normalize
- [ ] 3 項の loss を条件付き (weight > 0 のみ計算) で加算し、合成 loss を返す
- [ ] 各項は対応する `pea_emotion_loss_weight`, `pea_emotion_centroid_weight`, `pea_emotion_margin_weight` で重み付け
- [ ] NaN/Inf ガード: `torch.isnan(loss).any() or torch.isinf(loss).any()` の場合は warning ログを出力して `None` を返す
- [ ] ファイル単位の `python -c "from piper_train.vits.lightning import VitsModel"` で Syntax OK

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `src/python/piper_train/vits/lightning.py` (修正、+80 行想定)

### 2.2 実装手順

1. `_compute_pea_emotion_loss(y_hat: torch.Tensor, batch)` メソッドを `VitsModel` に追加 (Phase 1 の style vector 関連メソッド直下)
2. ガード条件を順に検査:
    - `if not self._pea_emotion_loss_enabled: return None`
    - `if not getattr(batch, "emotions", None): return None`
3. 有効サンプルの抽出:
    - `valid_indices = [i for i, emo in enumerate(batch.emotions) if emo in self._pea_emotion_to_idx]`
    - `if not valid_indices: return None`
4. emotion index テンソルを作成:
    - `emotion_indices = torch.as_tensor([self._pea_emotion_to_idx[batch.emotions[i]] for i in valid_indices], dtype=torch.long, device=y_hat.device)`
5. 有効サンプルの音声抽出:
    - `audio = y_hat[valid_indices]` (shape: `[num_valid, T]` or `[num_valid, 1, T]`、model により次元調整必要)
6. リサンプリング:
    - `if self.hparams.sample_rate != self.hparams.pea_emotion_sample_rate:`
    - `audio = torchaudio.functional.resample(audio, orig_freq=self.hparams.sample_rate, new_freq=self.hparams.pea_emotion_sample_rate)`
7. Embedding 抽出:
    - `pea_model = self._ensure_pea_emotion_model()`
    - `from piper_train.perception.pea_loader import grad_enabled_embedder_forward`
    - 方法 1: `embeddings = pea_model.get_audio_embeds(audio)` をそのまま使う (Phase 0 で API 確定済み)
    - 方法 2: `grad_enabled_embedder_forward(pea_model, audio)` でラップして DAC 勾配制御
    - 本実装では方法 2 を採用 (fork 実装踏襲)
    - `embeddings = F.normalize(embeddings, dim=-1)` で L2 normalize
8. Target/global centroid を取得:
    - `centroids = self.pea_emotion_centroids` (buffer、shape `[N, D]`)
    - `global_centroid = self.pea_emotion_global_centroid` (buffer、shape `[D]`)
    - `target_centroids = centroids.index_select(0, emotion_indices)` (shape `[num_valid, D]`)
9. Direction loss:
    - `target_dirs = F.normalize(target_centroids - global_centroid.unsqueeze(0), dim=-1)`
    - `embedding_dirs = F.normalize(embeddings - global_centroid.unsqueeze(0), dim=-1)`
    - `loss_dir = 1.0 - F.cosine_similarity(embedding_dirs, target_dirs, dim=-1).mean()`
10. Centroid loss:
    - `loss_centroid = 1.0 - F.cosine_similarity(embeddings, target_centroids, dim=-1).mean()`
    - Note: fork 実装では `||z_hat - target_centroid||_2` ではなく `1 - cosine` を採用 (L2 ではなく角度ベース)
11. Margin loss (hinge):
    - `similarities = embeddings @ centroids.t()` (shape `[num_valid, N]`)
    - `target_similarity = similarities.gather(1, emotion_indices[:, None]).squeeze(1)`
    - `similarities.scatter_(1, emotion_indices[:, None], float("-inf"))` (target 位置を除外)
    - `max_other_sim, _ = similarities.max(dim=1)`
    - `loss_margin = F.relu(self.hparams.pea_emotion_margin + max_other_sim - target_similarity).mean()`
12. 合成 loss:
    - `loss = torch.zeros((), device=y_hat.device)`
    - 各項を weight で条件付き加算
13. NaN/Inf ガード:
    - `if torch.isnan(loss).any() or torch.isinf(loss).any(): _LOGGER.warning("PE-A loss contains NaN/Inf, skipping step"); return None`
14. `return loss`

### 2.3 コード例 (phase-3-4.md §4.2 L708-773 より)

```python
def _compute_pea_emotion_loss(
    self,
    y_hat: torch.Tensor,
    batch,
) -> Optional[torch.Tensor]:
    """Compute PE-A emotion loss (direction + centroid + margin).

    Returns:
        None if disabled, no valid emotion labels, or NaN/Inf detected.
        Scalar torch.Tensor otherwise.
    """
    if not self._pea_emotion_loss_enabled:
        return None

    emotions = getattr(batch, "emotions", None)
    if not emotions:
        return None

    # Filter valid emotion samples
    valid_indices = [
        i for i, emo in enumerate(emotions)
        if emo in self._pea_emotion_to_idx
    ]
    if not valid_indices:
        return None

    emotion_indices = torch.as_tensor(
        [self._pea_emotion_to_idx[emotions[i]] for i in valid_indices],
        dtype=torch.long,
        device=y_hat.device,
    )

    # Resample to PE-A's expected sample rate
    audio = y_hat[valid_indices]
    if self.hparams.sample_rate != self.hparams.pea_emotion_sample_rate:
        audio = torchaudio.functional.resample(
            audio,
            orig_freq=self.hparams.sample_rate,
            new_freq=self.hparams.pea_emotion_sample_rate,
        )

    # Extract embeddings with DAC gradient control
    from piper_train.perception.pea_loader import grad_enabled_embedder_forward
    pea_model = self._ensure_pea_emotion_model()
    embeddings = grad_enabled_embedder_forward(pea_model, audio)
    if hasattr(embeddings, "audio_embeds"):
        embeddings = embeddings.audio_embeds  # ModelOutput fallback
    embeddings = F.normalize(embeddings, dim=-1)

    # Prepare centroids
    centroids = self.pea_emotion_centroids
    global_centroid = self.pea_emotion_global_centroid
    target_centroids = centroids.index_select(0, emotion_indices)

    # 3-term loss
    loss = torch.zeros((), device=y_hat.device)

    if self.hparams.pea_emotion_loss_weight > 0:
        target_dirs = F.normalize(
            target_centroids - global_centroid.unsqueeze(0), dim=-1
        )
        embedding_dirs = F.normalize(
            embeddings - global_centroid.unsqueeze(0), dim=-1
        )
        loss_dir = 1.0 - F.cosine_similarity(embedding_dirs, target_dirs, dim=-1).mean()
        loss = loss + loss_dir * self.hparams.pea_emotion_loss_weight

    if self.hparams.pea_emotion_centroid_weight > 0:
        loss_centroid = 1.0 - F.cosine_similarity(
            embeddings, target_centroids, dim=-1
        ).mean()
        loss = loss + loss_centroid * self.hparams.pea_emotion_centroid_weight

    if self.hparams.pea_emotion_margin_weight > 0:
        similarities = embeddings @ centroids.t()
        target_similarity = similarities.gather(
            1, emotion_indices[:, None]
        ).squeeze(1)
        similarities.scatter_(1, emotion_indices[:, None], float("-inf"))
        max_other_sim, _ = similarities.max(dim=1)
        loss_margin = F.relu(
            self.hparams.pea_emotion_margin + max_other_sim - target_similarity
        ).mean()
        loss = loss + loss_margin * self.hparams.pea_emotion_margin_weight

    # NaN/Inf guard
    if torch.isnan(loss).any() or torch.isinf(loss).any():
        _LOGGER.warning(
            "PE-A loss contains NaN/Inf (step=%d), skipping loss contribution",
            self.global_step,
        )
        return None

    return loss
```

## 3. エージェントチーム構成

- **Implementation Agent**: 1 名 (Claude Code、`lightning.py` 修正)
  - Fork commit `314b3355` の `_compute_pea_emotion_loss` 本体を取得し、そのまま移植
  - `torchaudio.functional.resample` と `F.cosine_similarity` の dim 引数が fork と一致することを確認
- **Verification Agent**: 1 名 (Claude Code、数式・次元の整合確認)
  - embeddings shape `[B, D]` と centroids shape `[N, D]` の broadcast 整合性
  - `scatter_` の in-place 操作が副作用を起こさないこと (similarities を直接書き換えるため、gradient flow に影響しないかを確認)
  - `torch.zeros((), device=...)` の scalar 初期化

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| loss 計算メソッド | `src/python/piper_train/vits/lightning.py` (`_compute_pea_emotion_loss`) |

**提供範囲外**:
- Loader 実装 (P4-T01 で完了)
- training_step_g への統合、warmup、every_n_steps (P4-T03 で実装)
- CLI オプション (P4-T04 で実装)
- Unit テスト (P4-T05 で実装)

## 5. テスト項目

### 5.1 Unit テスト (P4-T05 で実装)

本チケットでは実装しないが、以下が P4-T05 で必須:

- `test_direction_loss_zero_at_target`: embedding が target centroid と同方向のとき direction loss が 0 (許容誤差 1e-5)
- `test_centroid_loss_positive`: centroid loss が非負 (cos similarity <= 1 なので `1 - cos >= 0`)
- `test_margin_loss_hinge_zero`: target similarity が max_other + margin を超えるとき margin loss が 0
- `test_margin_loss_hinge_active`: target similarity が max_other + margin 以下のとき margin loss > 0
- `test_nan_guard`: NaN 入力で `None` を返し warning ログが出ること
- `test_disabled_returns_none`: `_pea_emotion_loss_enabled == False` で `None` を返す
- `test_no_valid_emotions_returns_none`: `batch.emotions` 全てが未知ラベルのとき `None` を返す
- `test_3_term_composition`: 3 つの weight が指定通りに合成されること (1.0/0.5/0.3 で検証)

### 5.2 E2E テスト (本チケットのスモーク)

- `python -c "from piper_train.vits.lightning import VitsModel; print('ok')"` が成功
- Fork commit `314b3355` の `_compute_pea_emotion_loss` と diff が空 (PE-A loss 本体コード限定で)

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **PE-A loss が NaN になって学習停止**: `F.normalize` が全 0 ベクトルに対して NaN を返すリスク。学習初期に y_hat が 0 近辺のときに発生しうる。NaN/Inf ガードで skip して warning 出力することで対策。ただし skip が多発すると loss が実質機能しないため、P4-T03 の warmup (最初 2000 step は weight=0) で学習安定化を図る
- **GPU メモリ追加 (PE-A model 500MB-1GB)**: 初回 `_ensure_pea_emotion_model()` 時にロード。VITS の Generator 出力 y_hat を PE-A に流すため、勾配 tape も保持される。PE-A 側の `requires_grad_(False)` は勾配計算そのものは止めないが、パラメータ更新は止める (学習時 PE-A は凍結)
- **loss 計算が重く、学習速度低下 (every_n_steps 4 で対策)**: `get_audio_embeds` (または forward) の呼び出しは画像エンコーダ並みの計算量。`every_n_steps` は P4-T03 で gating
- **direction loss の定義曖昧 (fork 側の実装を要確認)**: phase-3-4.md §4.2 の「`1 - cosine(target_dir, embedding_dir)`」実装では、global_centroid からの変位ベクトルに対する cosine を採用している。ユーザ要望の「`1 - cosine(z_hat, target_centroid - global_centroid)`」と一致するかは以下の違いに注意:
  - fork 実装: `cosine(F.normalize(z_hat - g, dim=-1), F.normalize(tc - g, dim=-1))` (双方を global から引いた後に cosine)
  - 単純解釈: `cosine(z_hat, tc - g)` (z_hat そのまま、target のみ global から引く)
  - fork 側の「2 つとも global からの変位」の方が幾何的に整合するため、**fork 実装 (両方 `- global_centroid`) を採用**
- **centroid loss の定義 (L2 vs cosine)**: ユーザ要望は「`||z_hat - target_centroid||_2`」だが、fork 実装は `1 - cosine`。 L2 距離は norm に依存し、cosine は方向のみ評価するため、性質が異なる。fork 実装を優先し、§6.1 にて仕様差分を明記、Phase 5 実験で必要なら L2 版を option で追加検討
- **scatter_ in-place の影響**: `similarities.scatter_(1, emotion_indices[:, None], float("-inf"))` は gradient flow に影響しない (scatter は inf 値の書き換えで gradient=0)。ただし autograd graph から見ると similarities 自体は derived tensor なので問題なし。レビューで明示確認
- **PE-A の forward 出力形式が ModelOutput / dict / Tensor のいずれか**: Phase 0 で確認済みだが、fallback として `hasattr(embeddings, "audio_embeds")` で分岐。transformers 標準の `BaseModelOutput` クラスに対応

### 6.2 レビュー項目

- [ ] ガード条件 (`_pea_emotion_loss_enabled`, `batch.emotions`) が順序通り
- [ ] `valid_indices` の抽出ロジックが Phase 4 想定の `emotion` 文字列ベース (not emotion_id)
- [ ] リサンプリング条件が VITS `sample_rate` と PE-A `pea_emotion_sample_rate` の比較
- [ ] `grad_enabled_embedder_forward` 経由で forward が呼ばれている (DAC 勾配制御)
- [ ] F.normalize の `dim=-1` が全箇所で統一されている
- [ ] 3 項それぞれで weight > 0 のみ計算するガードが入っている (無駄な計算回避)
- [ ] NaN/Inf ガードで `None` を返す際に warning ログと step 情報が出力されている
- [ ] `scatter_` in-place の副作用がないことをコメントで明記
- [ ] `loss = torch.zeros((), device=y_hat.device)` は正しく scalar (0-dim) 初期化

## 7. 一から作り直すとしたら

### 7.1 代替案の検討

- **代替案 A**: 3 項合成 loss を単一 loss (contrastive learning like) に簡略化
  - 実装案: InfoNCE loss 一本 (`-log(exp(target_sim) / sum(exp(all_sim)))`)
  - 利点: weight 調整パラメータが 3 つ → 0 個に削減、損失の振る舞いが解釈しやすい
  - 欠点: direction / centroid / margin の各寄与を個別にコントロールできない。Phase 5 のアブレーション実験で fork 実装が最適と判明している想定なので採用しない
- **代替案 B**: PE-A 抽出を pre-compute で dataset に埋め込み、学習時の GPU メモリ削減
  - Target 側の centroid のみ事前計算済み (P3 で対応済み)。Generator 出力 (y_hat) 側はリアルタイムに計算する必要があるため、実質削減できるのは target 抽出部分のみ。既に対応済みと同等
- **代替案 C**: Perceptual loss を WavLM に置き換え (既存の WavLM discriminator を再利用)
  - 既存 `WavLMDiscriminator` の features を抽出して centroid ベースの loss を計算
  - 利点: 追加 GPU メモリなし、CLAUDE.md の「CPU 推論最適化」と整合
  - 欠点: WavLM は感情表現の分離が弱い可能性 (感情認識 task 性能で PE-A に劣る想定)
  - 結論: Phase 5 の比較実験として有効。Phase 4 の範囲外
- **代替案 D**: LoRA で PE-A 側を fine-tune しながら使う
  - P4-T01 の §7.1 と同じ。学習不安定化リスクを避け Phase 4 の範囲外
- **代替案 E**: loss weight を hyperparameter optimization (Optuna) で自動探索
  - 利点: fork 側の手動調整に依存しない、タスク最適化
  - 欠点: HPO の計算コストが膨大 (1 trial あたり学習 1 回)。CREMA-D fine-tune は数時間単位なので実用困難
  - 結論: Phase 5 の検討事項。Phase 4 の範囲外
- **代替案 F**: direction loss と centroid loss を統合 (direction のみ、または centroid のみ)
  - direction loss は「emotion 間の関係 (global からの相対方向)」を学習
  - centroid loss は「emotion の絶対位置」を学習
  - fork 側は両方使うことで冗長性を持たせている。一方のみでも十分かもしれないが、実験的知見に依存

### 7.2 現在の実装を選んだ理由

- Fork `314b3355` の 3 項合成が実験で効果を示している前提で、忠実に移植することで fork 側の実験結果 (audio 感情認識精度 65% 以上) を再現する最短経路を選択
- `1 - cosine` 形式は norm に非依存で、L2 距離よりも学習安定性が高い傾向 (SimCLR / CLIP の慣例)
- ユーザ要望の文言 (「`|| z_hat - target_centroid ||_2`」「`1 - cosine(z_hat, ...)`」) との差分は §6.1 の懸念事項に明記し、fork 実装を優先する旨を合意

### 7.3 リファクタ機会 (将来)

- `_compute_pea_emotion_loss` を `PEAEmotionLoss(nn.Module)` クラスに抽出し、`VitsModel` から分離。single responsibility principle 適用
- 各項の損失値をログ出力する際、合計 `loss` だけでなく `loss_dir`, `loss_centroid`, `loss_margin` を個別に wandb に記録 (既に P4-T03 で検討)
- Phase 5 のアブレーション実験で 3 項の最適な比率が判明したら、デフォルト値を調整

## 8. 後続タスクへの連絡事項

- **P4-T03 へ**: `_compute_pea_emotion_loss(y_hat, batch)` を `training_step_g` で呼び出す前に warmup / every_n_steps の gating を行うこと。本メソッドは「disabled」「no emotion」「NaN」の 3 ケースでのみ `None` を返し、warmup/skip 判定は training_step_g 側で実施
- **P4-T05 へ**: 以下の API をテストで利用
  - `VitsModel._compute_pea_emotion_loss(y_hat, batch)` (public テスト用に public alias もあり)
  - Mock batch 構造: `batch.emotions: list[str]` (例: `["angry", "happy", "sad"]`)
  - Mock y_hat: `torch.randn(B, T)` (B=batch_size, T=audio_length)
- **P4-T04 へ**: `pea_emotion_margin` のデフォルト値を `0.1` (fork 実装踏襲) とするか `0.2` (ユーザ要望) とするか要調整。fork が `0.1` のため `0.1` を推奨、ユーザ側に確認

## 9. 参考リンク

- Fork commit (取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- Fork 実装箇所 (推定): `lightning.py:298-375`
- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- phase-3-4.md §4.2 lightning.py への patch (概要)
- phase-3-4.md §4.5 推奨プリセット (weight の初期値)
- P4-T01: `tickets/phase-4/P4-T01-pea-loader-style-bank.md`
- `torchaudio.functional.resample`: https://pytorch.org/audio/stable/generated/torchaudio.functional.resample.html
- `F.cosine_similarity`: https://pytorch.org/docs/stable/generated/torch.nn.functional.cosine_similarity.html
