# P1-T01: models.py に style_vector 層を追加

| 項目 | 値 |
|------|-----|
| Phase | 1 |
| マイルストーン | [#11](https://github.com/ayutaz/piper-plus/milestone/11) |
| ステータス | 未着手 |
| 優先度 | 高 |
| Claude Code 工数 | 30分〜1h |
| 依存チケット | P0-T03 (embedding 次元確定) |
| 後続チケット | P1-T03, P1-T04, P1-T05, P1-T06 |
| 関連 PR | PR-B |

## 1. タスク目的とゴール

### 1.1 目的

`src/python/piper_train/vits/models.py` の `TextEncoder` と `SynthesizerTrn` に Style Vector Conditioning 機構を追加する。Fork `yusuke-ai/piper-plus` のコミット `314b3355` を最終形として、PE-A emotion loss 関連コードを除いた最小スコープで取り込む。

既存モデル (style_vector_dim=0) の挙動が bit-for-bit 一致することが最重要要件。既定値を 0 にし、style_proj をゼロ初期化することで、後方互換性を担保する。

### 1.2 ゴール (Definition of Done)

- [ ] `TextEncoder.__init__` に `style_vector_dim`, `style_condition_dropout` パラメータが追加されている
- [ ] `TextEncoder._style_embedding()` メソッドが実装されている (style_vector を hidden_channels に射影)
- [ ] `TextEncoder.forward()` に `style_vector` 引数が追加され、scaling 順序が修正されている
- [ ] `SynthesizerTrn.__init__` に `style_vector_dim`, `style_condition_dropout`, `style_condition_mode` が追加されている
- [ ] `SynthesizerTrn._add_style_condition()` メソッドが実装されている (global mode 時に g に加算)
- [ ] `SynthesizerTrn.forward/infer` が `style_vector` 引数を受け取り、mode に応じて TextEncoder または `_add_style_condition` に委譲する
- [ ] `style_condition_mode ∈ {"global", "text"}` のバリデーションが実装されている
- [ ] `global` mode かつ `style_vector_dim > 0` の場合に `gin_channels > 0` を要求するバリデーションが実装されている
- [ ] `style_proj` 層の weight/bias が `nn.init.zeros_()` で初期化されている (既存挙動との bit-for-bit 一致)
- [ ] `style_vector=None` で zeros fallback が動作する
- [ ] ローカル import のみでファイル単位の python -c で Syntax OK が確認できる

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `src/python/piper_train/vits/models.py` (修正、+150 行想定)

### 2.2 実装手順

1. Fork `yusuke-ai/piper-plus` commit `314b3355` の `models.py` 差分を `gh api "repos/yusuke-ai/piper-plus/commits/314b3355"` で取得する
2. PE-A 関連コード (emotion loss 関連) が混入していないことを確認する
3. `TextEncoder.__init__` に `style_vector_dim` (default 0) と `style_condition_dropout` (default 0.0) を追加
4. `style_vector_dim > 0` のときのみ `self.style_proj = nn.Linear(style_vector_dim, self.hidden_channels)` を構築。weight/bias を `nn.init.zeros_()` で初期化
5. `_style_embedding(style_vector, batch_size, device, dtype)` メソッドを追加。None の場合は zeros を返す
6. `forward(x, x_lengths, style_vector=None)` に引数を追加し、style_vector を射影後の埋め込みに加算する (scaling 順序: 射影 → dropout → broadcast add)
7. `SynthesizerTrn.__init__` に `style_vector_dim` (default 0), `style_condition_dropout` (default 0.0), `style_condition_mode` (default "global") を追加
8. `style_condition_mode` バリデーション: `{"global", "text"}` 以外は `ValueError`
9. `global` mode + `dim > 0` の場合は `gin_channels > 0` を検証、違反時は `ValueError`
10. `global` mode の `style_proj = nn.Sequential(Linear(dim, gin), SiLU, Linear(gin, gin))` を定義
11. `_add_style_condition(g, style_vector)` メソッドを追加 (g に style 射影結果を加算)
12. `forward()` / `infer()` で mode に応じて分岐: `"text"` → TextEncoder 経由、`"global"` → `_add_style_condition` で g に加算
13. `g` が None の場合 (多話者でも多言語でもない場合) に `_add_style_condition` が適切にエラー or 初期化される挙動を確認

### 2.3 コード例 (phase-0-1.md §1.4 Patch 1 より抜粋)

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

完全な patch は `gh api "repos/yusuke-ai/piper-plus/commits/314b3355"` で取得し、PE-A 関連コードを除外して適用する。

## 3. エージェントチーム構成

- **Implementation Agent**: 1 名 (Claude Code、`models.py` 修正)
  - `gh api` で fork diff 取得 → PE-A loss 除外 → patch 適用 → Syntax OK 確認
- **Verification Agent**: 1 名 (Claude Code、CLAUDE.md と既存 models.py 構造の整合確認)
  - `gin_channels` 条件 `(num_speakers > 1 or num_languages > 1)` との干渉がないこと
  - `WavLMDiscriminator`, `prosody_features` 系の既存拡張と衝突しないこと

Phase 1 内の他チケット (P1-T02〜T05) と並行実装可能だが、T03/T04/T05 は SynthesizerTrn の forward シグネチャ変更に依存するため、本チケットのマージを待って着手するのが安全。

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| 修正済み models.py | `src/python/piper_train/vits/models.py` |
| diff サマリ (PR 本文用) | PR-B コメントに埋め込み (`TextEncoder`/`SynthesizerTrn` の追加 API 一覧) |

**提供範囲外**:
- Unit テスト (P1-T06 で実装)
- CLI 統合 (P1-T04 で実装)
- Dataset 側の style_vector 受け渡し (P1-T02 で実装)
- PE-A emotion loss (Phase 4 で取り込み)

## 5. テスト項目

### 5.1 Unit テスト (P1-T06 で実装)

本チケットでは実装しないが、以下が P1-T06 で必須:

- `test_backwards_compatible_dim_0`: `style_vector_dim=0` で既存挙動と完全等価
- `test_global_mode_projection_zero_init`: `style_proj` がゼロ初期化されている
- `test_style_vector_none_fallback`: `style_vector=None` で zeros fallback
- `test_text_mode_works_with_dim_0`: text mode + dim=0 で `style_proj is None`
- `test_global_mode_requires_gin_channels`: gin_channels<=0 で ValueError
- `test_invalid_mode_raises`: 未知の mode で ValueError

### 5.2 E2E テスト (本チケットのスモーク)

- `python -c "from piper_train.vits.models import TextEncoder, SynthesizerTrn; print('ok')"` が成功
- Fork の commit `314b3355` の構造と diff レベルで比較し、PE-A 関連がないこと
- 1 epoch dry-run (dim=0) で NaN が出ないこと (P1-T07 での CI フックで確認)

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **style_proj 初期化が実は非ゼロ**: fork 実装が後方互換を保証しない場合、既存 6lang モデルからの resume に影響する。→ P1-T06 の `test_global_mode_projection_zero_init` と `test_backwards_compatible_dim_0` で verify
- **gin_channels=0 の場合のエラーハンドリング**: シングルスピーカー + シングル言語モデル (`num_speakers <= 1 and num_languages <= 1`) で gin_channels=0 になる可能性。global mode を要求されたら明示エラーを出す
- **既存の emb_g / emb_lang との干渉**: `_add_style_condition` が g を加算するため、`emb_g + emb_lang` のすぐ後に挿入する必要がある。fork 実装の順序を厳密に追従
- **`scaling 順序修正` の意図**: コミット `314b3355` のコメントに scaling 順序修正 (text mode での射影 → dropout → add の順) とある。既存の TextEncoder の positional encoding scale (`* math.sqrt(self.hidden_channels)`) との順序を誤ると音質に影響する

### 6.2 レビュー項目

- [ ] `style_condition_mode ∈ {"global", "text"}` のバリデーションが `__init__` で実行される
- [ ] `dim=0` で既存挙動と bit-for-bit 一致 (P1-T06 で検証)
- [ ] `style_proj` の zero init が確認できる (weight と bias 両方)
- [ ] `SynthesizerTrn.forward()` / `infer()` のシグネチャに `style_vector=None` がデフォルト付きで追加されている
- [ ] PE-A loss 関連コード (`pea_emotion_*`) が models.py に混入していない (Phase 4 用)
- [ ] fork commit `314b3355` の `scaling 順序修正` が再現されている

## 7. 一から作り直すとしたら

- **代替案 A**: SynthesizerTrn.__init__ で継承する enum 型で mode を管理 (`StyleConditionMode.GLOBAL` / `StyleConditionMode.TEXT`)。Python 3.11+ の `StrEnum` を利用
  - メリット: 型安全、IDE 補完、文字列リテラル typo 防止
  - デメリット: fork との diff が増える、既存の CLI 値マッピングが必要
- **代替案 B**: `style_proj` をモジュール化して `StyleProjection` クラスに抽出 (global/text 両対応)
  - メリット: 責務分離、テスト容易性向上
  - デメリット: fork との diff が増える
- **代替案 C**: dim=0 のときも空の `nn.Identity()` を入れて `if self.style_proj is not None` 判定を消す
  - メリット: コードパスが単純化
  - デメリット: 既存チェックポイントとの load 時に Unexpected key が発生し shape-aware loader で warning が出る

**採用理由**: fork 実装 (`314b3355`) との diff を最小化してレビュー負荷を軽減する。将来的に P2 以降で ONNX エクスポート側と整合取る際に切り出す余地あり。

## 8. 後続タスクへの連絡事項

- **P1-T02 へ**: dataset.py の `Batch.style_vectors: FloatTensor` は `TextEncoder.forward(style_vector=...)` の引数形式に合わせて shape `[batch, style_vector_dim]` で送出すること
- **P1-T03 へ**: `VitsModel.training_step` / `validation_step` で `style_vector=batch.style_vectors` を SynthesizerTrn.forward へ伝播する必要がある
- **P1-T04 へ**: CLI 3 オプション (`--style-vector-dim`, `--style-condition-dropout`, `--style-condition-mode`) を `VitsModel` 初期化時に hparams 経由で渡すこと
- **P1-T05 へ**: `SynthesizerTrn.infer(style_vector=...)` のシグネチャ追加は取り込み済み。`infer.py` 側は `_style_vector_to_tensor()` で生成したテンソルを渡すだけでよい
- **P1-T06 へ**: 以下の API/プロパティをテストで利用する
  - `TextEncoder.style_vector_dim`
  - `TextEncoder.style_proj`
  - `SynthesizerTrn.style_condition_mode`
  - `SynthesizerTrn.style_proj`

## 9. 参考リンク

- Fork commit (取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- Fork commit (初版): https://github.com/yusuke-ai/piper-plus/commit/b9e98236
- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- phase-0-1.md §1.2-A `src/python/piper_train/vits/models.py`
- phase-0-1.md §1.4 Patch 1: `vits/models.py`
- CLAUDE.md 「実装済み機能」セクション (gin_channels 条件の記述)
- 全体調査: `docs/research/peav-style-conditioning.md`
