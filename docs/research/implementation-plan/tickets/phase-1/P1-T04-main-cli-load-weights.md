# P1-T04: __main__.py に CLI オプション + --load_weights_from_checkpoint (shape-aware)

| 項目 | 値 |
|------|-----|
| Phase | 1 |
| マイルストーン | [#11](https://github.com/ayutaz/piper-plus/milestone/11) |
| ステータス | 完了 |
| 優先度 | 高 |
| Claude Code 工数 | 30分〜1h |
| 依存チケット | P1-T01, P1-T02, P1-T03 |
| 後続チケット | P1-T06, P1-T07 |
| 関連 PR | PR-B |

## 1. タスク目的とゴール

### 1.1 目的

`src/python/piper_train/__main__.py` に Style Vector Conditioning 用の argparse オプション 3 個と、fine-tune 用の shape-aware `--load_weights_from_checkpoint` を 1 個追加する。

CLI で渡された値を `VitsModel` の hparams 経由で SynthesizerTrn に伝播させる。既存の `--resume-from-multispeaker-checkpoint` は strict=True に近い挙動だが、今回追加する `--load_weights_from_checkpoint` は shape 不一致テンソルを **skip + warning** で処理する。

PE-A 関連の 13 個の CLI (`--pea-emotion-*`) は Phase 4 で追加。Phase 1 では取り込まない。

### 1.2 ゴール (Definition of Done)

- [ ] `--style-vector-dim N` (default 0, int) が argparse に追加されている
- [ ] `--style-condition-dropout FLOAT` (default 0.0, float) が追加されている
- [ ] `--style-condition-mode STR` (default "global", choices=["global", "text"]) が追加されている
- [ ] `--load_weights_from_checkpoint PATH` (default None) が追加されている
- [ ] CLI で指定された style 系 3 オプションが `VitsModel` の __init__ に渡されている
- [ ] `--load_weights_from_checkpoint` 指定時に shape-aware loader が起動し、shape 不一致テンソルは skip + warning ログ出力
- [ ] `--load_weights_from_checkpoint` と `--resume-from-multispeaker-checkpoint` が排他的でないことを確認 (同時指定時の優先順位を明記)
- [ ] strict=True モード (厳格 load) のオプションも追加 (default は shape-aware)、または `--load_weights_from_checkpoint_strict` フラグを別途追加する (fork 実装に準拠)
- [ ] `--pea-emotion-*` は取り込まない (Phase 4)
- [ ] `save_last=True → False` は取り込まない (別 PR で検討)
- [ ] `--style-vector-dim 0` (default) でレグレッションなし

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `src/python/piper_train/__main__.py` (修正、+40 行想定)

### 2.2 実装手順

1. Fork commit `314b3355` の `__main__.py` 差分を取得し、PE-A 関連 CLI を除外
2. argparse に以下を追加:
   - `--style-vector-dim` (type=int, default=0)
   - `--style-condition-dropout` (type=float, default=0.0)
   - `--style-condition-mode` (choices=["global", "text"], default="global")
   - `--load_weights_from_checkpoint` (type=str, default=None)
3. `VitsModel(args)` 初期化箇所で上記 3 オプションを渡す (既存の `args.freeze_dp` と同様の取り扱い)
4. `args.freeze_dp = True` のように **`VitsModel()` 作成の前に** `save_hyperparameters` に入るように設定する (CLAUDE.md 注意事項を遵守)
5. shape-aware loader を実装:
   - `torch.load(path, map_location="cpu")` で state_dict 取得
   - `model.state_dict()` をキーリスト取得
   - 各 key で shape を比較 → 一致すれば load、不一致は skip + `_LOGGER.warning(...)` 出力
   - `model.load_state_dict(filtered_sd, strict=False)` で適用
6. warning ログは `key: expected shape X, got Y → skipped` 形式で明示
7. `--resume-from-multispeaker-checkpoint` との同時指定時は `--resume-from-multispeaker-checkpoint` を優先、または排他エラー (fork 実装確認)

### 2.3 コード例 (phase-0-1.md §1.4 Patch 5)

```python
# argparse 追加部分
parser.add_argument("--style-vector-dim", type=int, default=0,
                    help="Dimension of style vector (0 = disabled, backwards-compatible)")
parser.add_argument("--style-condition-dropout", type=float, default=0.0,
                    help="Probability of dropping style condition during training")
parser.add_argument("--style-condition-mode", choices=["global", "text"], default="global",
                    help="Where to inject style vector: 'global' (g) or 'text' (TextEncoder)")
parser.add_argument("--load_weights_from_checkpoint", type=str, default=None,
                    help="Shape-aware partial weight loading (for fine-tuning with architecture change)")

# shape-aware loader (VitsModel 初期化後)
if args.load_weights_from_checkpoint:
    _LOGGER.info(f"Loading weights from {args.load_weights_from_checkpoint}")
    checkpoint = torch.load(args.load_weights_from_checkpoint, map_location="cpu")
    state_dict = checkpoint.get("state_dict", checkpoint)

    model_sd = model.state_dict()
    filtered_sd = {}
    skipped = []
    for key, tensor in state_dict.items():
        if key not in model_sd:
            skipped.append(f"{key}: missing in current model")
            continue
        if model_sd[key].shape != tensor.shape:
            skipped.append(f"{key}: shape {tensor.shape} -> expected {model_sd[key].shape}")
            continue
        filtered_sd[key] = tensor
    missing, unexpected = model.load_state_dict(filtered_sd, strict=False)
    if skipped:
        for msg in skipped:
            _LOGGER.warning(f"Skipped: {msg}")
    _LOGGER.info(f"Loaded {len(filtered_sd)}/{len(state_dict)} tensors")
```

完全な fork diff は `gh api "repos/yusuke-ai/piper-plus/commits/314b3355"` で取得。

## 3. エージェントチーム構成

- **Implementation Agent**: 1 名 (Claude Code、argparse + load_weights 実装)
  - fork diff 取得 → PE-A 系を除外 → patch 適用
- **Review Agent**: 1 名 (Claude Code、既存 CLI との衝突確認)
  - `--resume-from-multispeaker-checkpoint` との相互作用
  - `--freeze-dp` 自動有効化ロジック (P0 の save_hyperparameters タイミング注意)

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| 修正済み __main__.py | `src/python/piper_train/__main__.py` |
| CLI ヘルプ (`--help`) 更新 | 自動 (argparse) |

**提供範囲外**:
- `--pea-emotion-*` (Phase 4)
- `save_last=True → False` (独立 PR で議論)
- YAML/TOML 設定ファイル読み込み (スコープ外)

## 5. テスト項目

### 5.1 Unit テスト (P1-T06 で実装)

- `test_shape_aware_partial_load`: 既存 6lang checkpoint (dim=0) から style_proj 付きモデル (dim=256) へロード成功
- `test_skip_mismatched_shape_logs_warning`: shape 不一致テンソルは skip + warning ログ (caplog で verify)
- `test_strict_true_raises_on_missing`: strict=True なら不足テンソルで RuntimeError (オプション)

### 5.2 E2E テスト (本チケットのスモーク)

- `python -m piper_train --help | grep style-vector-dim` で表示確認
- `python -m piper_train --help | grep load_weights_from_checkpoint` で表示確認
- `python -m piper_train --style-vector-dim 0 --style-condition-mode global ...` (default 相当) で既存 6lang 学習が問題なく起動することを dry-run
- `--load_weights_from_checkpoint /data/piper/output-multilingual-6lang/lightning_logs/version_0/checkpoints/epoch=74-step=504712.ckpt --style-vector-dim 256` で shape 警告ログが出ること、学習が起動すること

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **`save_hyperparameters` のタイミング**: `args.freeze_dp = True` が `VitsModel()` 作成の**前**に設定される必要あり、と CLAUDE.md にある (`freeze_dp` セクション参照)。style 系 3 オプションも同様の注意が必要
- **CLI 命名規則**: 既存が `--freeze-dp` (ハイフン区切り)、`--resume-from-multispeaker-checkpoint` (ハイフン区切り) に対し、fork の `--load_weights_from_checkpoint` はアンダースコア区切り。本家のスタイル統一か fork 準拠か判断必要 → fork 準拠 (アンダースコア) を採用し、同時に alias `--load-weights-from-checkpoint` を提供することも検討
- **`--resume-from-multispeaker-checkpoint` との重複**: 両方指定された場合の優先順位。fork 実装を確認し、明示エラーまたは優先順位を docstring に記載
- **shape-aware loader の誤検知**: `dim=0` → `dim=256` で `style_proj.weight` が shape 不一致になるのは想定動作。warning ログが出るが正常。ユーザが混乱しないよう `--load_weights_from_checkpoint` docstring にその旨を記載
- **checkpoint の Lightning 互換性**: `.ckpt` は `{'state_dict': ...}` の辞書、`.pt` は state_dict 直接の場合あり。両方サポート

### 6.2 レビュー項目

- [ ] style 系 3 CLI がヘルプメッセージで日本語/英語どちらかで統一
- [ ] `--style-vector-dim 0` default でレグレッションなし
- [ ] `--style-condition-mode` が `choices` で制限されている
- [ ] `--load_weights_from_checkpoint` が shape 不一致テンソルを skip + warning ログ
- [ ] PE-A 関連 CLI が紛れ込んでいない (Phase 4 用)
- [ ] `save_last=True → False` の変更が混入していない (別 PR)
- [ ] `args.freeze_dp = True` と同様のタイミング規約を守っている
- [ ] ckpt と pt の両フォーマットに対応

## 7. 一から作り直すとしたら

- **代替案 A**: CLI オプションを group 化 (`--style-*` prefix を argparse group でまとめる)
  - メリット: `--help` 出力が整理される、将来の拡張が容易
  - デメリット: fork との diff 増加
- **代替案 B**: hydra / omegaconf / pydantic-based 設定ファイルに置換 (`training_config.yaml`)
  - メリット: CLI が短くなる、設定の再現性向上
  - デメリット: 既存 CLI ユーザーへの影響大、移行工数増
- **代替案 C**: `--load_weights_from_checkpoint` を既存の `--resume-from-multispeaker-checkpoint` と統合し、内部で自動判定
  - メリット: CLI が 1 つに集約、ユーザ学習コスト減
  - デメリット: 自動判定ロジックのバグリスク、behavior 変更で後方互換性喪失

**採用理由**: fork 実装との diff 最小化を優先。group 化 (代替案 A) は Phase 4 で `--pea-emotion-*` が加わった後に検討。

## 8. 後続タスクへの連絡事項

- **P1-T05 へ**: `infer.py` 側にも `--style-vector-dim` に対応した CLI (`--style-vector`) を追加する必要がある。本チケットの argparse スタイルを参考にすること
- **P1-T06 へ**: `--load_weights_from_checkpoint` の Unit テストは `tmp_path` を使った checkpoint 保存→load→shape 比較パターンで書く
- **P1-T07 へ**: CLAUDE.md の「実装済み機能」セクションに CLI オプション一覧を反映すること
- **P5 (Fine-tune スクリプト) へ**: fine-tune 推奨コマンドに `--load_weights_from_checkpoint` を含めたテンプレートを docs に記載

## 9. 参考リンク

- Fork commit (取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- phase-0-1.md §1.2-E `src/python/piper_train/__main__.py`
- phase-0-1.md §1.3 最小取り込みスコープ (CLI 4 個)
- phase-0-1.md §1.4 Patch 5: `__main__.py`
- CLAUDE.md 「転移学習 (--resume-from-multispeaker-checkpoint)」セクション
- CLAUDE.md 「Duration Predictor 凍結 (--freeze-dp)」セクション (save_hyperparameters タイミング注意)
