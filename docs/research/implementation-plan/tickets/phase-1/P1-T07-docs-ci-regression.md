# P1-T07: CLAUDE.md 更新 + CI リグレッション確認

| 項目 | 値 |
|------|-----|
| Phase | 1 |
| マイルストーン | [#11](https://github.com/ayutaz/piper-plus/milestone/11) |
| ステータス | 完了 |
| 優先度 | 中 |
| Claude Code 工数 | 10分 + CI 待ち (1〜3h) |
| 依存チケット | P1-T01, P1-T02, P1-T03, P1-T04, P1-T05, P1-T06 |
| 後続チケット | (Phase 2 着手) |
| 関連 PR | PR-B |

## 1. タスク目的とゴール

### 1.1 目的

Phase 1 の実装結果を反映するドキュメント更新と、Python CI が既存テスト + 新規テストで green であることを確認する。具体的には:

1. `CLAUDE.md` の「実装済み機能」セクションに `### Style Vector Conditioning (--style-vector-dim)` を追加
2. `.github/workflows/python-tests.yml` の確認 (新テストが自動で拾われるか)
3. `style_vector_dim=0` (default) で既存 6lang 学習がレグレッションしないことを確認 (dry-run or 短時間実行)

### 1.2 ゴール (Definition of Done)

- [ ] `CLAUDE.md` の「実装済み機能」に `Style Vector Conditioning` セクションが追加されている
- [ ] 新セクションには CLI オプション 4 個 / 実装ファイル一覧 / テストファイル一覧が記載されている
- [ ] 「重要なファイルパス」セクションに追加したテストファイル 2 個が追加されている (必要に応じて)
- [ ] `.github/workflows/python-tests.yml` を確認し、新テストが `tests/` ディレクトリ配下で自動的に pytest に拾われることを確認
- [ ] PR-B のブランチで CI が全て green
- [ ] 既存 `style_vector_dim=0` (default) で 1 epoch dry-run が NaN なく完了 (既存 6lang ckpt から resume or 小データセット)
- [ ] Fork との main 側 diff サマリを PR-B 本文に記載

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `CLAUDE.md` (修正、+30 行想定)
- `.github/workflows/python-tests.yml` (確認のみ、修正不要なら変更なし)

### 2.2 実装手順

1. phase-0-1.md §1.6 のサンプルをベースに CLAUDE.md に新セクションを挿入
2. 「実装済み機能」セクション中の適切な位置 (Speaker Embedding セクション付近、またはその下) に追加
3. CLI オプション一覧を表形式で明示
4. 「重要なファイルパス」セクションに新規テストファイルを追加
5. `python-tests.yml` のテストパスが `tests/` であることを確認。新ファイル `tests/test_style_vector_conditioning.py` と `tests/test_load_weights_from_checkpoint.py` が自動的に拾われることを確認
6. ローカルで `pytest tests/ -v` を実行し、既存テスト + 新規 11 テストが全て green であることを確認
7. 既存 6lang checkpoint を使った dry-run:
   ```bash
   # 簡易 dry-run (style_vector_dim=0 で既存挙動と一致確認)
   # max_epochs 2, limit_train_batches 10 など短時間実行
   ```
8. CI (GitHub Actions) の green を待ち、PR-B を ready for review 状態にする

### 2.3 CLAUDE.md 追加セクション案 (phase-0-1.md §1.6)

```markdown
### Style Vector Conditioning (--style-vector-dim)

スタイルベクトル条件付けにより、音声のスタイル・感情表現を制御可能。既存モデルは `--style-vector-dim 0` (既定) で完全後方互換。Fork `yusuke-ai/piper-plus` コミット `314b3355` をベースに取り込み (PE-A emotion loss は Phase 4 で別途対応)。

**CLI オプション (学習):**
- `--style-vector-dim N` (デフォルト: 0): スタイルベクトル次元 (0=無効)
- `--style-condition-dropout FLOAT` (デフォルト: 0.0): training 時の条件付け dropout 確率
- `--style-condition-mode STR` (デフォルト: "global"): 注入モード ("global" で `g` に加算、"text" で TextEncoder 内)
- `--load_weights_from_checkpoint PATH`: shape-aware partial load (fine-tune で dim 拡張時に使用)

**CLI オプション (推論):**
- `--style-vector`: .npy / .pt / カンマ区切り文字列から style vector を指定

**実装:**
- `vits/models.py` (TextEncoder / SynthesizerTrn 拡張、style_proj ゼロ初期化)
- `vits/dataset.py` (Utterance.style_vector_path, BatchCollator で事前割当)
- `vits/lightning.py` (batch.style_vectors を SynthesizerTrn.forward に伝播)
- `vits/commons.py` (slice_segments を N-D 一般化)
- `__main__.py` (argparse + shape-aware load_weights_from_checkpoint)
- `infer.py` (_style_vector_to_tensor helper、.npy/.pt/inline 対応)

**テスト:**
- `tests/test_style_vector_conditioning.py` (8 テスト)
- `tests/test_load_weights_from_checkpoint.py` (3 テスト)

**fine-tune 推奨コマンド:**
Phase 5 `docs/research/implementation-plan/phase-5.md` 参照 (Style bank からの query を含む完全な recipe を提供予定)
```

### 2.4 既存 6lang dry-run 確認

```bash
# 既存 6lang でレグレッションなしを確認 (style_vector_dim=0 default)
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
/data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-multilingual-6lang-filtered \
  --prosody-dim 16 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 1 --batch-size 20 --samples-per-speaker 2 \
  --quality medium --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --max-phoneme-ids 400 \
  --no-wavlm --audio-log-epochs 0 \
  --val-every-n-epochs 1 --limit-val-batches 2 \
  --limit_train_batches 10 \
  --default_root_dir /tmp/dry-run-test \
  2>&1 | tail -100
```

NaN loss が出ないこと、backward が完了することを確認。

## 3. エージェントチーム構成

- **Documentation Agent**: 1 名 (Claude Code、CLAUDE.md 編集)
- **CI Watcher Agent**: 1 名 (Claude Code、GitHub Actions 結果確認)
  - `gh run list --branch <PR-B-branch>` で進捗監視
  - 失敗時は原因特定 → 該当チケット (T01-T06) に修正依頼

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| 更新済み CLAUDE.md | `CLAUDE.md` |
| CI 実行ログ (PR-B) | GitHub Actions の URL を PR 本文に添付 |
| dry-run 実行ログ | PR-B コメントに添付 |

**提供範囲外**:
- 本番 75 epoch 学習 (Phase 5 の fine-tune 検証で実施)
- Style bank 生成 (Phase 3)
- PE-A emotion loss 検証 (Phase 4)

## 5. テスト項目

### 5.1 Unit テスト (既に P1-T06 で実装)

全 11 テスト green を CI で確認 (`pytest tests/ -v`)。

### 5.2 E2E リグレッションテスト (本チケット)

| テスト名 | 実行コマンド | 期待結果 |
|---------|------------|---------|
| default dim=0 レグレッション | 上記 dry-run コマンド | NaN なし、10 batches 完走 |
| ckpt resume レグレッション | `--resume-from-multispeaker-checkpoint` 併用 | エラーなく resume |
| shape-aware load | `--load_weights_from_checkpoint /data/piper/output-multilingual-6lang/lightning_logs/version_0/checkpoints/epoch=74-step=504712.ckpt --style-vector-dim 256` | warning ログ出力 + 学習開始 |

### 5.3 CI 確認項目

- [ ] `python-tests.yml` が全 OS (Linux/macOS/Windows?) で green
- [ ] `ruff` / `pyright` などの lint が green (設定されていれば)
- [ ] 新規テストが auto-discovered されている

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **CLAUDE.md の肥大化**: 既存セクションが多く、1 セクション追加で 30 行増。目次から探しにくい可能性。→ 「実装済み機能」セクション内で章立てを整理する提案を別タスクで出す (今回は追加のみ)
- **CI 時間増**: 新規 11 テストで CI が数秒〜数十秒増える可能性。pytest timeout の設定を確認
- **dry-run 環境依存**: `/data/piper` 環境は GPU サーバ側。ローカル Mac (M1/M2) では `--accelerator cpu --precision 32-true` で代替
- **`--load_weights_from_checkpoint` の warning ログ**: 既存ユーザが初見で驚く可能性あり。docstring で「shape 拡張時は warning が出るが正常動作」と明記
- **python-tests.yml の更新要否**: 新ファイル追加のみで設定変更不要のはずだが、万一 `tests/test_style_*.py` を明示的に除外している設定があれば修正

### 6.2 レビュー項目

- [ ] CLAUDE.md の新セクションが既存のスタイル (表形式、CLI オプション表記) に準拠
- [ ] 「重要なファイルパス」セクションにテストファイルが追加 (または判定不要として見送り)
- [ ] Fork commit SHA (`314b3355`) が CLAUDE.md または PR-B 本文に明示されている
- [ ] dry-run ログに NaN がないこと
- [ ] CI green
- [ ] PR-B 本文に「PE-A emotion loss は Phase 4 で取り込み」と明記 (スコープ明確化)

## 7. 一から作り直すとしたら

- **代替案 A**: CLAUDE.md の分割 (`docs/features/style-vector.md` に詳細、CLAUDE.md はリンクのみ)
  - メリット: CLAUDE.md 肥大化を抑制、検索容易性
  - デメリット: 既存機能セクションとのスタイル不統一
- **代替案 B**: 変更の度にチェンジログ (`CHANGELOG.md`) を更新
  - メリット: 差分追跡が容易
  - デメリット: 既存プロジェクトにないため運用コスト増
- **代替案 C**: CI に style_vector 専用の dedicated job を追加 (`python-tests-style-vector.yml`)
  - メリット: 失敗時に原因切り分けが容易
  - デメリット: CI 分散で総実行時間増

**採用理由**: 既存 CLAUDE.md のスタイル踏襲が最も整合的。将来的に features/ ディレクトリへの分割は Phase 5 以降で判断。

## 8. 後続タスクへの連絡事項

- **Phase 2 着手へ**: Phase 1 完了の前提条件として、CLAUDE.md の新セクションと Fork 参照コミットが確認できていること
- **Phase 4 (PE-A loss) へ**: CLAUDE.md 新セクションに「PE-A emotion loss は Phase 4 で取り込み予定」と記載し、Phase 4 チケット着手時の cross-reference を容易にすること
- **Phase 5 (fine-tune recipe) へ**: CLAUDE.md 「つくよみちゃん 6langベースファインチューニング」セクションに並べて、Style Vector 版の fine-tune 節を追加予定

## 9. 参考リンク

- phase-0-1.md §1.6 CLAUDE.md 更新 (本チケットのベース)
- phase-0-1.md §1.8 リスクと対策 (特に「既存 CI 落ち」対策)
- CLAUDE.md 「実装済み機能」 (既存セクションのスタイル参考)
- `.github/workflows/python-tests.yml` (CI 設定)
- PR-B: (作成後に URL を追記)
