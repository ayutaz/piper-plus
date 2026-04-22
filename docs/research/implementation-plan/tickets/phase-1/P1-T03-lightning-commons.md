# P1-T03: lightning.py に style_vector 伝播 + commons.py の slice_segments 一般化

| 項目 | 値 |
|------|-----|
| Phase | 1 |
| マイルストーン | [#11](https://github.com/ayutaz/piper-plus/milestone/11) |
| ステータス | 未着手 |
| 優先度 | 高 |
| Claude Code 工数 | 20分 |
| 依存チケット | P1-T01, P1-T02 |
| 後続チケット | P1-T04, P1-T06 |
| 関連 PR | PR-B |

## 1. タスク目的とゴール

### 1.1 目的

2 つの小さな修正を 1 チケットで実施する:

1. **lightning.py**: `VitsModel.training_step` / `validation_step` で SynthesizerTrn を呼び出す際に `style_vector=batch.style_vectors` を伝播する (+20 行程度)
2. **commons.py**: `slice_segments()` の shape を 3D 固定から N-D 一般化 (+5 行程度)

PE-A emotion loss 関連のコードは Phase 4 で取り込むため、本チケットでは伝播のみに限定する。

### 1.2 ゴール (Definition of Done)

- [ ] `VitsModel.training_step` (または `training_step_g`) で `style_vector=batch.style_vectors` が SynthesizerTrn.forward に渡されている
- [ ] `VitsModel.validation_step` でも同様に style_vector が伝播されている
- [ ] `commons.slice_segments()` の shape が `list(x.shape)` ベースに一般化されている
- [ ] `ret_shape = list(x.shape); ret_shape[-1] = segment_size; ret = x.new_zeros(ret_shape)` パターンが適用されている
- [ ] 既存の 3D テンソル呼び出しで regression しないこと (`[B, C, T]`)
- [ ] Phase 4 用の PE-A loss 関連コードは**取り込まない** (`_init_pea_emotion_loss` など)
- [ ] `python -c "from piper_train.vits.lightning import VitsModel; from piper_train.vits.commons import slice_segments; print('ok')"` が成功

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `src/python/piper_train/vits/lightning.py` (修正、+20 行想定)
- `src/python/piper_train/vits/commons.py` (修正、+5 行想定)

### 2.2 実装手順

#### lightning.py 側

1. `VitsModel.__init__` で `style_vector_dim`, `style_condition_dropout`, `style_condition_mode` を hparams から取得して SynthesizerTrn に渡す (P1-T01 の SynthesizerTrn.__init__ 追加引数に対応)
2. `training_step` (または generator step) 内で SynthesizerTrn.forward を呼ぶ箇所に `style_vector=batch.style_vectors` を追加
3. `validation_step` で validation 用 forward を呼ぶ箇所にも同様に追加
4. `save_hyperparameters` 後に args の style 系パラメータが hparams 経由で復元できることを確認 (`--freeze-dp` と同様の取り扱い)
5. fork の lightning.py から PE-A 関連メソッド (`_init_pea_emotion_loss`, `_ensure_pea_emotion_model`, `_compute_pea_emotion_loss`, `training_step_g` への PE-A loss 合算) は**取り込まない**
6. `emotions` は batch にあるが Phase 1 では未使用なので `batch.emotions` の参照もしない

#### commons.py 側

1. Fork commit `314b3355` の `commons.py` 差分 (`slice_segments()`) を取得
2. `ret = torch.zeros_like(x[:, :, :segment_size])` を以下に置換:
   ```python
   ret_shape = list(x.shape)
   ret_shape[-1] = segment_size
   ret = x.new_zeros(ret_shape)
   ```
3. slicing ロジック (`ret[i] = x[i, :, idx_str:idx_end]`) が N-D に対して正しく動くか確認 (既存の `[:, :, ...]` パターンは後方互換)
4. `slice_segments` を呼び出す他の箇所で影響ないことを grep で確認 (現行は VITS のセグメント切り出しのみ)

### 2.3 コード例 (phase-0-1.md §1.4 Patch 2 および Patch 4)

```python
# Patch 2: vits/lightning.py (VitsModel.training_step 内、抜粋)
# 既存:
# y_hat, l_length, attn, ids_slice, x_mask, z_mask, \
#     (z, z_p, m_p, logs_p, m_q, logs_q) = self.model_g(
#         batch.phoneme_ids, batch.phoneme_lengths,
#         batch.spectrograms, batch.spectrogram_lengths,
#         speaker_ids=batch.speaker_ids, language_ids=batch.language_ids,
#         prosody=batch.prosody,
#     )
# 変更後:
y_hat, l_length, attn, ids_slice, x_mask, z_mask, \
    (z, z_p, m_p, logs_p, m_q, logs_q) = self.model_g(
        batch.phoneme_ids, batch.phoneme_lengths,
        batch.spectrograms, batch.spectrogram_lengths,
        speaker_ids=batch.speaker_ids, language_ids=batch.language_ids,
        prosody=batch.prosody,
        style_vector=batch.style_vectors,  # 追加
    )

# Patch 4: vits/commons.py (slice_segments 一般化)
def slice_segments(x, ids_str, segment_size=4):
    # Before:
    # ret = torch.zeros_like(x[:, :, :segment_size])
    # After:
    ret_shape = list(x.shape)
    ret_shape[-1] = segment_size
    ret = x.new_zeros(ret_shape)
    for i in range(x.size(0)):
        idx_str = ids_str[i]
        idx_end = idx_str + segment_size
        ret[i] = x[i, ..., idx_str:idx_end]  # ... で N-D 対応
    return ret
```

> **注意**: `x[i, :, idx_str:idx_end]` のままでも 3D ならばそのまま動くため、最小 diff を保つなら既存 slice を維持してもよい。fork 側の実装に合わせる。

## 3. エージェントチーム構成

- **Implementation Agent**: 1 名 (Claude Code、両ファイルをまとめて修正)
  - 変更量が小さいため 1 エージェントで完遂可能
- **Verification Agent**: 1 名 (Claude Code、既存 `--freeze-dp` との相互作用確認)
  - `freeze_dp` が optimizer 除外をしているため、SynthesizerTrn.forward のシグネチャ変更でエラーが出ないこと
  - `WavLMDiscriminator` との training_step 順序を変えないこと

**順序制約**: P1-T01 (models.py) と P1-T02 (dataset.py) の両方がマージされてから着手。どちらか片方だけだと lightning の呼び出しが失敗する。

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| 修正済み lightning.py | `src/python/piper_train/vits/lightning.py` |
| 修正済み commons.py | `src/python/piper_train/vits/commons.py` |

**提供範囲外**:
- PE-A emotion loss 関連 (Phase 4 で取り込み)
- `save_last=True → False` の変更 (CLAUDE.md の `save_last` 論点と独立評価のため別 PR)
- `--pea-emotion-*` CLI オプション (Phase 4)

## 5. テスト項目

### 5.1 Unit テスト (P1-T06 で一部カバー)

本チケットでは以下を P1-T06 側のテストとして依頼:
- `test_training_step_forwards_style_vector`: `batch.style_vectors` が SynthesizerTrn.forward に渡ることを mock で検証
- `test_slice_segments_backwards_compatible_3d`: 既存の 3D テンソル入力で以前と bit-for-bit 一致

### 5.2 E2E テスト (本チケットのスモーク)

- `python -c "from piper_train.vits.lightning import VitsModel; m = VitsModel.__init__; print(m.__doc__)"`
- 1 epoch dry-run (既存 6lang データセット + `style_vector_dim=0`) で NaN が出ないこと (P1-T07 で確認)
- `slice_segments(x, ids, 4)` を `x.shape=(2, 3, 100)` で呼び出し、`[2, 3, 4]` が返ること

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **`training_step_g` vs `training_step`**: 既存実装の generator 相当 step の正しい関数名を特定すること。fork も同一の関数名のはず
- **`batch.style_vectors` が空 (dim=0) の場合**: `torch.zeros((B, 0))` を渡して SynthesizerTrn 側でエラーにならないこと。P1-T01 と連携して None を明示的に渡すのも一案
- **`slice_segments` の互換性**: 既存で `[B, C, T]` (3D) としてしか呼ばれていないことを確認。N-D 化は安全だが `x[i, :, ...]` を `x[i, ..., ...]` に変えるとスタイルが変わる
- **PE-A loss 漏れ**: fork の `training_step_g` が PE-A loss を差し込んでいる場所を確実に除外する

### 6.2 レビュー項目

- [ ] `batch.style_vectors` が `training_step` / `validation_step` の両方で SynthesizerTrn に渡されている
- [ ] `commons.slice_segments` が 3D 既存呼び出しで動作する
- [ ] PE-A 関連メソッド (`_init_pea_emotion_loss` など) が lightning.py に混入していない
- [ ] `VitsModel.__init__` で style 系 hparams が SynthesizerTrn に渡されている
- [ ] `save_hyperparameters()` 後の hparams 復元で `style_vector_dim` が取れる

## 7. 一から作り直すとしたら

- **代替案 A**: `batch` をそのまま SynthesizerTrn に渡して内部で unpack
  - メリット: 呼び出し側のシグネチャ変更なし、将来の拡張で引数追加が容易
  - デメリット: SynthesizerTrn が torch.nn.Module の純粋性を失う (batch dataclass 依存)
- **代替案 B**: `slice_segments` を `torch.narrow` ベースで書き直し
  - メリット: ベクトル化、for ループ削除
  - デメリット: fork との diff 増加、実運用で速度差ほぼなし (N バッチの for ループ)
- **代替案 C**: style_vector 伝播を Hook ベースに変更
  - メリット: 各 step コードを汚さない
  - デメリット: 複雑化、デバッグ難化

**採用理由**: fork `314b3355` のシンプルな引数追加アプローチを踏襲。変更量が少なく、レビュー容易。

## 8. 後続タスクへの連絡事項

- **P1-T04 へ**: `VitsModel.__init__` は `style_vector_dim` / `style_condition_dropout` / `style_condition_mode` を受け取れるようになる。`__main__.py` 側で args からの渡し方を実装すること
- **P1-T06 へ**: lightning.py のテストは mock を使った training_step 1 step 実行で style_vectors の forward 渡しを verify する。`torch.zeros(B, 0)` と `torch.randn(B, 256)` の両方をカバー
- **Phase 4 (PE-A loss) へ**: fork の `training_step_g` に PE-A loss を差し込む位置は既存実装で確認済み。commit `314b3355` の該当 hunk を参照

## 9. 参考リンク

- Fork commit (取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- phase-0-1.md §1.2-B `src/python/piper_train/vits/lightning.py`
- phase-0-1.md §1.2-D `src/python/piper_train/vits/commons.py`
- phase-0-1.md §1.4 Patch 2: `vits/lightning.py`
- phase-0-1.md §1.4 Patch 4: `vits/commons.py`
- CLAUDE.md 「Duration Predictor 凍結 (--freeze-dp)」セクション (同様の hparams 取り扱い手本)
