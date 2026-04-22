# P4-T04: CLI オプション 9 個 追加 (--pea-emotion-*)

| 項目 | 値 |
|------|-----|
| Phase | 4 |
| マイルストーン | [#14](https://github.com/ayutaz/piper-plus/milestone/14) |
| ステータス | 未着手 |
| 優先度 | 中 |
| Claude Code 工数 | 1h |
| 依存チケット | P4-T01 (loader)、P4-T02 (loss)、P4-T03 (統合) |
| 後続チケット | P4-T05 (テスト) |
| 関連 PR | PR-F |
| 期日 | 2026-05-02 |

## 1. タスク目的とゴール

### 1.1 目的

`src/python/piper_train/__main__.py` の argparse に PE-A emotion loss 関連の CLI オプション 9 個を追加する。Fork `yusuke-ai/piper-plus` コミット `314b3355` の `add_model_specific_args` 実装を忠実に移植し、`VitsModel.__init__` に kwargs として渡す。

全オプションは既定値で「無効化」される設計 (全 weight=0 のとき `_pea_emotion_loss_enabled == False`)。ユーザが `--pea-emotion-style-bank PATH` と `--pea-emotion-loss-weight 0.1` (または centroid/margin weight) のいずれかを指定することで有効化される。

### 1.2 ゴール (Definition of Done)

- [ ] `__main__.py` の argparse に以下 9 個のオプションが追加されている:
  - [ ] `--pea-emotion-loss-weight` (float, default 0.0)
  - [ ] `--pea-emotion-centroid-weight` (float, default 0.0)
  - [ ] `--pea-emotion-margin-weight` (float, default 0.0)
  - [ ] `--pea-emotion-style-bank` (str/Path, default None)
  - [ ] `--pea-emotion-model-name` (str, default `"facebook/pe-av-small"`)
  - [ ] `--pea-emotion-sample-rate` (int, default 16000)
  - [ ] `--pea-emotion-loss-every-n-steps` (int, default 1)
  - [ ] `--pea-emotion-warmup-steps` (int, default 0)
  - [ ] `--pea-emotion-margin` (float, default 0.1)
- [ ] `VitsModel(...)` 初期化時に kwargs として `pea_emotion_*=args.pea_emotion_*` が渡される
- [ ] `--help` で各オプションの説明文が表示される (fork 実装と同等の日本語 or 英語説明)
- [ ] `--pea-emotion-enabled` (ユーザ要望のエイリアス) は実装しない代わりに、loss_weight/centroid_weight/margin_weight のいずれかが > 0 であることで enable 判定
- [ ] `args.pea_emotion_style_bank` が `None` かつ loss weight > 0 のとき argparse パース後に ValueError (P4-T01 の `_init_pea_emotion_loss` で検査されるが、早期 fail も可)
- [ ] Syntax OK: `python -m piper_train --help` で 9 個のオプションが表示される

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `src/python/piper_train/__main__.py` (修正、+30 行想定)
- `src/python/piper_train/vits/lightning.py` (修正、`__init__` に 9 個の kwargs 追加、+20 行想定)

### 2.2 実装手順

1. `__main__.py` の argparse 設定箇所 (既存の `--style-vector-dim` や `--freeze-dp` などの定義の近く) に 9 個のオプションを追加
2. 各オプションの定義:
    ```python
    parser.add_argument(
        "--pea-emotion-loss-weight", type=float, default=0.0,
        help="PE-A direction loss weight (default: 0.0, disabled)",
    )
    parser.add_argument(
        "--pea-emotion-centroid-weight", type=float, default=0.0,
        help="PE-A centroid loss weight (default: 0.0, disabled)",
    )
    parser.add_argument(
        "--pea-emotion-margin-weight", type=float, default=0.0,
        help="PE-A margin loss weight (default: 0.0, disabled)",
    )
    parser.add_argument(
        "--pea-emotion-style-bank", type=str, default=None,
        help="Path to .npz style bank (required when PE-A loss enabled)",
    )
    parser.add_argument(
        "--pea-emotion-model-name", type=str, default="facebook/pe-av-small",
        help="HuggingFace model name for PE-A (default: facebook/pe-av-small)",
    )
    parser.add_argument(
        "--pea-emotion-sample-rate", type=int, default=16000,
        help="PE-A input sample rate (default: 16000)",
    )
    parser.add_argument(
        "--pea-emotion-loss-every-n-steps", type=int, default=1,
        help="Compute PE-A loss every N steps (default: 1, recommended 4)",
    )
    parser.add_argument(
        "--pea-emotion-warmup-steps", type=int, default=0,
        help="Delay PE-A loss by N steps (default: 0, recommended 2000)",
    )
    parser.add_argument(
        "--pea-emotion-margin", type=float, default=0.1,
        help="Cosine margin for margin loss (default: 0.1)",
    )
    ```
3. `VitsModel(...)` 初期化時の kwargs に 9 個追加:
    ```python
    model = VitsModel(
        # ... 既存引数 ...
        pea_emotion_loss_weight=args.pea_emotion_loss_weight,
        pea_emotion_centroid_weight=args.pea_emotion_centroid_weight,
        pea_emotion_margin_weight=args.pea_emotion_margin_weight,
        pea_emotion_style_bank=args.pea_emotion_style_bank,
        pea_emotion_model_name=args.pea_emotion_model_name,
        pea_emotion_sample_rate=args.pea_emotion_sample_rate,
        pea_emotion_loss_every_n_steps=args.pea_emotion_loss_every_n_steps,
        pea_emotion_warmup_steps=args.pea_emotion_warmup_steps,
        pea_emotion_margin=args.pea_emotion_margin,
    )
    ```
4. `VitsModel.__init__` シグネチャに 9 個の kwargs を追加 (default 付き):
    ```python
    def __init__(
        self,
        # ... 既存パラメータ ...
        pea_emotion_loss_weight: float = 0.0,
        pea_emotion_centroid_weight: float = 0.0,
        pea_emotion_margin_weight: float = 0.0,
        pea_emotion_style_bank: Optional[str] = None,
        pea_emotion_model_name: str = "facebook/pe-av-small",
        pea_emotion_sample_rate: int = 16000,
        pea_emotion_loss_every_n_steps: int = 1,
        pea_emotion_warmup_steps: int = 0,
        pea_emotion_margin: float = 0.1,
        **kwargs,
    ):
    ```
5. `self.save_hyperparameters()` の呼び出しタイミングで 9 個の hparams が snapshot されることを確認 (通常、親クラスの `LightningModule.__init__` 前に呼ばれる)
6. CLAUDE.md の「`--freeze-dp` の hparams snapshot 問題」と同じパターンで、`_init_pea_emotion_loss()` は `save_hyperparameters()` 後かつ `VitsModel.__init__` 末尾近くで呼ぶこと (P4-T01 で実装済み)
7. `args.pea_emotion_style_bank` の早期バリデーションを `__main__.py` に追加 (optional):
    ```python
    if (args.pea_emotion_loss_weight > 0 or args.pea_emotion_centroid_weight > 0
        or args.pea_emotion_margin_weight > 0):
        if not args.pea_emotion_style_bank:
            parser.error(
                "--pea-emotion-style-bank is required when PE-A loss weight > 0"
            )
    ```

### 2.3 コード例 (phase-3-4.md §4.4 テーブルより)

CLI オプションの完全な一覧:

| オプション | 既定 | 型 | 説明 |
|----------|------|-----|------|
| `--pea-emotion-loss-weight` | 0.0 | float | 方向ロスの重み (c_dir) |
| `--pea-emotion-centroid-weight` | 0.0 | float | セントロイドロスの重み (c_centroid) |
| `--pea-emotion-margin-weight` | 0.0 | float | マージンロスの重み (c_margin) |
| `--pea-emotion-style-bank` | None | Path | `.npz` style bank ファイル |
| `--pea-emotion-model-name` | `"facebook/pe-av-small"` | str | HF モデル ID |
| `--pea-emotion-sample-rate` | 16000 | int | PE-A 入力 SR |
| `--pea-emotion-loss-every-n-steps` | 1 | int | Skip-step (毎 N step) |
| `--pea-emotion-warmup-steps` | 0 | int | 開始遅延 |
| `--pea-emotion-margin` | 0.1 | float | Cosine margin |

## 3. エージェントチーム構成

- **Implementation Agent**: 1 名 (Claude Code、`__main__.py` + `lightning.py` 修正)
  - fork commit `314b3355` の argparse 実装を確認し、オプション名・デフォルト値・help テキストを一致させる
  - `--style-vector-dim` や `--freeze-dp` の定義順序を参考に、関連性の高い位置に配置
- **Verification Agent**: 1 名 (Claude Code、CLI 出力・デフォルト値のレビュー)
  - `python -m piper_train --help` の出力を確認
  - 9 個のオプションが既存の `--help` 出力と競合しない (name clash なし)
  - `args.pea_emotion_*` の attribute が argparse パース後に存在する

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| argparse 定義 | `src/python/piper_train/__main__.py` |
| VitsModel.__init__ 受け取り | `src/python/piper_train/vits/lightning.py` |

**提供範囲外**:
- Loader 実装 (P4-T01)
- Loss 計算本体 (P4-T02)
- training_step_g 統合・warmup (P4-T03)
- Unit テスト (P4-T05)

## 5. テスト項目

### 5.1 Unit テスト (P4-T05 で実装)

本チケットでは実装しないが、以下が P4-T05 で必須:

- `test_cli_defaults`: 9 個のオプションが全てデフォルト値で `_pea_emotion_loss_enabled == False` を返す
- `test_cli_loss_weight_positive`: `--pea-emotion-loss-weight 0.1` で `_pea_emotion_loss_enabled == True`
- `test_cli_missing_style_bank`: `--pea-emotion-loss-weight 0.1` かつ `--pea-emotion-style-bank` なしで argparse error (parser.error 経由)
- `test_cli_parser_error_message`: エラーメッセージが `"--pea-emotion-style-bank is required"` を含む

### 5.2 E2E テスト (本チケットのスモーク)

- `python -m piper_train --help 2>&1 | grep pea-emotion` で 9 行以上が表示される
- `python -m piper_train --dataset-dir /tmp/fake --pea-emotion-loss-weight 0.1 2>&1 | grep "style-bank"` でエラー表示

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **オプション名のハイフンとアンダースコア変換**: argparse は `--pea-emotion-loss-weight` を `args.pea_emotion_loss_weight` に変換する (自動)。既存の `--base-lr` / `args.base_lr` などと整合
- **デフォルト値の設計**: 全 weight=0 で無効化、`warmup_steps=0` / `every_n_steps=1` でフル計算。ユーザ要望との差分:
  - ユーザ要望: `warmup=2000`, `every_n_steps=4`, `margin=0.2`
  - fork 実装: `warmup=0`, `every_n_steps=1`, `margin=0.1`
  - 結論: **fork 実装のデフォルト値を採用**。推奨値は phase-3-4.md §4.5 の「推奨プリセット」に記載済み。ユーザは明示的に指定する
- **`--pea-emotion-enabled` boolean フラグの有無**: ユーザ要望には `--pea-emotion-enabled` が含まれるが、fork 実装にはない。設計判断:
  - Fork 式: 3 つの weight のいずれかが > 0 で自動有効化 → CLI がシンプル
  - ユーザ要望式: `--pea-emotion-enabled=True` で明示有効化、その後 weight を指定
  - 結論: **fork 実装 (weight > 0 で自動有効化) を採用**。`--pea-emotion-enabled` は実装しない (ユーザ要望の意図は「有効化する簡易フラグ」と解釈できるが、3 weight のいずれかを > 0 にする行為で同等に表現可能)
- **CLI オプション 9 個のオーダー**: argparse の `--help` 出力順序を考慮し、関連オプションをグループ化 (例: weight 系 3 個、config 系 3 個、scheduling 系 3 個)
- **既存 CLI との衝突**: 既存に `--pea-*` 名のオプションはないはず。念のため `git grep "pea-" src/python/piper_train/__main__.py` で確認
- **`parser.error` と `raise ValueError`**: `__main__.py` の早期バリデーションでは `parser.error` を推奨 (非 0 exit code + usage 表示)。`raise ValueError` はスタックトレースが表示されるため UX が悪い

### 6.2 レビュー項目

- [ ] 9 個のオプション名が fork commit `314b3355` と完全一致
- [ ] デフォルト値が fork 実装と一致 (全 weight=0、model_name="facebook/pe-av-small"、margin=0.1、warmup=0、every_n_steps=1、sample_rate=16000)
- [ ] `VitsModel(...)` 初期化で 9 個の kwargs が正しく渡されている
- [ ] `VitsModel.__init__` シグネチャに 9 個の kwargs が追加されている
- [ ] `--help` 出力で 9 個のオプションが表示される
- [ ] 早期バリデーション (`parser.error`) が `--pea-emotion-loss-weight 0.1` + no `--pea-emotion-style-bank` でトリガーされる
- [ ] `args.pea_emotion_*` attribute が argparse パース後に `hasattr(args, "pea_emotion_loss_weight")` で存在する

## 7. 一から作り直すとしたら

### 7.1 代替案の検討

- **代替案 A**: CLI オプションを `--pea-emotion-config YAML_PATH` に集約し、YAML ファイル 1 本で 9 個のパラメータを管理
  - 利点: CLI が短くなる、再現性向上
  - 欠点: 9 個個別指定できないため実験的な weight 調整が不便、既存 piper-plus の CLI スタイル (個別フラグ) と不整合
  - 結論: 不採用。既存 CLI スタイルを維持
- **代替案 B**: `--pea-emotion-enabled` boolean フラグ追加 (ユーザ要望)
  - 実装: `--pea-emotion-enabled` をトリガーに、3 weight を default 0.1 に自動設定 (または単に loss_weight=0.1 をセット)
  - 利点: 「有効化」の意図が明確、docs でクイックスタートが書きやすい
  - 欠点: 暗黙的に weight を設定するのはユーザが意図しない挙動の原因になる、fork との diff 増大
  - 結論: 不採用。「3 weight のいずれかを > 0 にする」という明示的な操作を要求
- **代替案 C**: プリセット機能 (`--pea-emotion-preset initial` / `--pea-emotion-preset quality`)
  - 実装: phase-3-4.md §4.5 の「初期実験」「品質重視」を name で選択
  - 利点: 使いやすい、ドキュメント不要
  - 欠点: 個別オプションとの競合ロジックが複雑 (どちらが優先か)
  - 結論: Phase 5 の実験テンプレートとしてシェルスクリプトで提供する方が柔軟
- **代替案 D**: すべてのオプションを環境変数にフォールバック (`PIPER_PEA_EMOTION_LOSS_WEIGHT` 等)
  - CLAUDE.md の CPU 推論最適化では環境変数 (`PIPER_DISABLE_WARMUP` 等) を併用
  - 結論: CLI のみで十分、環境変数は Phase 5 以降で必要に応じて追加

### 7.2 現在の実装を選んだ理由

- Fork commit `314b3355` の argparse 実装をそのまま移植することで、Phase 4 の他チケットとの整合性を最大化
- 個別オプション (9 個) はユーザが実験段階で個別調整したいため、集約 (YAML/preset) より柔軟
- 既存 piper-plus の `--freeze-dp`, `--c-wavlm`, `--wavlm-every-n-steps` などの CLI スタイルと整合

### 7.3 リファクタ機会 (将来)

- `--pea-emotion-preset {initial,quality,debug}` を追加し、9 個の個別オプションを上書き可能に
- 環境変数フォールバック (`PIPER_PEA_EMOTION_*`) を追加 (Phase 5 の CI/CD 用途)
- `phase-3-4.md §4.5` の「推奨プリセット」をシェルスクリプトとしてリポジトリに同梱 (`scripts/train_pea_emotion_*.sh`)

## 8. 後続タスクへの連絡事項

- **P4-T05 へ**: 以下のテストを実装
  - `test_cli_defaults`
  - `test_cli_loss_weight_positive`
  - `test_cli_missing_style_bank`
  - `test_cli_parser_error_message`
- **Phase 5 (PR-G) へ**: CREMA-D fine-tune コマンドに以下の 5 オプションを推奨指定:
  - `--pea-emotion-loss-weight 0.1`
  - `--pea-emotion-centroid-weight 0.1`
  - `--pea-emotion-margin-weight 0.05`
  - `--pea-emotion-loss-every-n-steps 4`
  - `--pea-emotion-warmup-steps 2000`
  - `--pea-emotion-style-bank /data/piper/style_bank_crema_d.npz`
- **ドキュメント更新**: CLAUDE.md の「実装済み機能」セクションに「PE-A Emotion Loss (--pea-emotion-*)」を追加 (工数は他チケットに含むため本チケットでは未実施、Phase 5 完了時に一括更新)

## 9. 参考リンク

- Fork commit (取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- Fork 実装箇所 (推定): `__main__.py` の `add_model_specific_args` 付近
- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- phase-3-4.md §4.4 CLI オプション設計
- phase-3-4.md §4.5 推奨プリセット
- argparse 公式: https://docs.python.org/3/library/argparse.html
- 既存 CLI 参考: `src/python/piper_train/__main__.py` (`--freeze-dp`, `--c-wavlm`, `--wavlm-every-n-steps`)
