# P5-T05: 最終レポート + CLAUDE.md 更新

| 項目 | 値 |
|------|-----|
| Phase | 5 |
| マイルストーン | [#15](https://github.com/ayutaz/piper-plus/milestone/15) |
| ステータス | 未着手 |
| 優先度 | 高 |
| Claude Code 工数 | 2〜3h |
| 依存チケット | P5-T01, P5-T02, P5-T03, P5-T04 (全 Phase 5 タスク完了) |
| 後続チケット | なし (Phase 5 最終タスク) |
| 関連 PR | PR-G (final commit) |
| 期日 | 2026-05-08 |

## 1. タスク目的とゴール

### 1.1 目的

Phase 0〜5 の全成果を統合し、`docs/research/reports/pea-style-conditioning-report.md` に最終レポートとしてまとめる。また `CLAUDE.md` にも、「つくよみちゃん 6langベースファインチューニング」と同じパターンで CREMA-D モデル情報・学習コマンド・推論例・モデルパスを記載し、プロジェクト上位ドキュメントに反映する。

レポートは以下の読者を想定:
- プロジェクトメンテナ (ayousanz): Go/No-go 判断、本家統合の判定材料
- 外部コントリビューター: 実装詳細、再現手順、参考文献
- 将来の自分 (Claude Code): リファクタリング時の前提情報、失敗事例の記録

### 1.2 ゴール (Definition of Done)

- [ ] `docs/research/reports/pea-style-conditioning-report.md` (新規) に以下のセクションが揃っている
    - [ ] Executive Summary (3〜5 行)
    - [ ] Phase 0 〜 5 の成果サマリ (phase ごとに 1〜3 段落)
    - [ ] 実験結果 (SER 精度、MOS、多言語 regression) を表形式で提示
    - [ ] 成功基準達成状況 (phase-5.md §5.7 の 3 段階: 最低基準 / 目標 / ストレッチ)
    - [ ] 学び (特に Phase 1〜4 で得た知見、fork との diff ポイント)
    - [ ] 今後の課題 (ストレッチ未達項目、シナリオ B/C 検討、ベース再学習提言)
    - [ ] 参考文献・成果物 URL 一覧
- [ ] `CLAUDE.md` に CREMA-D emotion モデルセクションが追加されている
    - [ ] 「つくよみちゃん 6langベースファインチューニング」と同等の構成 (dataset パス、学習コマンド、推論例、モデルパス、HuggingFace Hub URL)
    - [ ] 「ファイルパス > 学習済みモデル」テーブルに Stage 5a (+ Stage 5b optional) モデルを追加
    - [ ] 「実装済み機能」セクションに「Style Vector Conditioning (--style-vector-dim)」の簡潔な説明を追加
    - [ ] 「HuggingFaceリソース」テーブルに `ayousanz/piper-plus-crema-d-emotion` を追加
- [ ] レポート Markdown の内部リンク (phase-*.md, peav-style-conditioning.md, CLAUDE.md) が有効
- [ ] CLAUDE.md 差分で既存機能ドキュメントの構成・粒度に整合

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `docs/research/reports/pea-style-conditioning-report.md` (新規、+500〜800 行想定)
- `CLAUDE.md` (既存、+100〜150 行追加想定)
- `docs/research/reports/phase-5-evaluation.md` (P5-T03 成果物、本レポートから参照)
- `docs/research/reports/phase-5-runtime-verification.md` (P5-T04 成果物、本レポートから参照)

### 2.2 実装手順

1. **Phase 0〜5 の全チケット成果を集約**:
    - P0 (PoC): facebook/pe-av-small ロード可否、embedding 次元確定
    - P1 (学習側統合): models.py / dataset.py / lightning.py / CLI 3 オプション
    - P2 (ONNX + 6 ランタイム): export_onnx 拡張、Python/C++/Rust/C#/Go/WASM 統合
    - P3 (Style bank): build_pea_style_bank.py / inject_style_labels.py / CREMA-D DL
    - P4 (PE-A loss): emotion loss 統合、warmup、weight 設計
    - P5 (Fine-tune): dataset 準備、Stage 5a 学習、評価、ONNX + 6 ランタイム確認
2. **成功基準の達成状況を整理**:
    - 最低基準 (Go/No-go): 英語 SER >= 65%, MOS >= 3.8 (ベース比 -0.2 以下), レグレッションなし
    - 目標: 英語 SER >= 75%, MOS >= 4.0, 日本語声質維持
    - ストレッチ: 多言語感情認識 60%+, 補間自然, 他話者対応
3. **Phase 別の学びを抽出**:
    - Phase 0: AutoModel + trust_remote_code の実用性、embedding dim の実測値
    - Phase 1: fork diff 最小化の戦略、style_proj ゼロ初期化による bit-for-bit 互換
    - Phase 2: mask パターンによる Optional 入力の 6 ランタイム実装パターン
    - Phase 3: CREMA-D のファイル名フォーマット活用、style bank の centroid 安定性
    - Phase 4: PE-A loss の warmup + every_n_steps による安定化
    - Phase 5: fine-tune の catastrophic forgetting 対策 (freeze-dp + LR 1/10)
4. **今後の課題を明文化**:
    - 多言語感情対応の不足 → ESD/JTES 追加のシナリオ C
    - ストレッチ未達 (例: 補間品質) → ベース再学習での改善余地
    - Stage 5b (PE-A loss) の実施判断 → Phase 4 完了後に再検討
    - 人間評価 MOS の実施 → 評価者確保 1〜2 週間の別枠
5. **CLAUDE.md 更新**:
    - 既存「つくよみちゃん 6langベースファインチューニング」セクションの直後に「CREMA-D 感情 finetune」セクションを追加
    - dataset パス、学習コマンド (phase-5.md §5.4.1 完全形を流用)、推論例 (emotion ごとの style_vector 切替)、モデルパス、HuggingFace Hub URL を記述
    - 「実装済み機能」に「Style Vector Conditioning」を追加 (CLI オプション、実装パス、テスト)
    - 「学習済みモデル」テーブルに Stage 5a エントリを追加
    - 「HuggingFaceリソース」テーブルに CREMA-D モデルエントリを追加
6. **Markdown リンク確認**: `grep -n "](" docs/research/reports/pea-style-conditioning-report.md` で内部リンクを確認、相対パスが正しいか検証

### 2.3 最終レポート構成 (`pea-style-conditioning-report.md`)

```markdown
# Style Vector Conditioning + PE-A Emotion Loss 実装報告書

**作成日**: 2026-05-XX
**Phase 0〜5 完了日**: 2026-05-08
**対象機能**: fork `yusuke-ai/piper-plus` の PE-AV style conditioning + emotion loss を本家 `ayutaz/piper-plus` に統合
**実装主体**: Claude Code (AIエージェント)

## Executive Summary

(3〜5 行で結論。例: Phase 5 Stage 5a で英語 SER XX%, MOS YY.YY を達成し最低基準をクリア/未達。Stage 5b は Go/No-go ...)

## Phase 0〜5 成果サマリ

### Phase 0: facebook/pe-av-small PoC
- ロード方法: AutoModel + trust_remote_code (成功/失敗)
- embedding dim: 256 (実測)
- API: get_audio_embeds()
- 推論速度: XX ms / sample (V100)

### Phase 1: 学習側統合
- models.py: TextEncoder/SynthesizerTrn に style_vector_dim + style_condition_dropout 追加
- dataset.py: Utterance/Batch に style_vector_path + emotion 注入
- CLI: --style-vector-dim, --style-condition-mode, --style-condition-dropout
- 互換性: style_vector_dim=0 で bit-for-bit 互換 (zero init)

### Phase 2: ONNX + 6 ランタイム
- export_onnx.py: style_vector + style_vector_mask 入力追加 (mask パターン)
- metadata_props: style_vector_dim / style_condition_mode 書き込み
- 6 ランタイム統合: Python/C++/Rust/C#/Go/WASM

### Phase 3: Style bank + inject labels
- build_pea_style_bank.py: CREMA-D → emotion_centroids (.npz)
- inject_style_labels.py: 既存 dataset.jsonl に emotion/style_vector_path 注入

### Phase 4: PE-A emotion loss
- direction loss + centroid loss + margin loss
- warmup: 2000 step
- every_n_steps: 4 (計算コスト削減)

### Phase 5: CREMA-D Fine-tune
- データセット: /data/piper/dataset-crema-d-emotion/ (7,442 発話, 91 話者)
- Stage 5a: 6lang ベースから 200 epoch fine-tune (GPU 2 日)
- 評価: 英語 SER XX%, MOS YY.YY
- ONNX: crema-d-finetune-v1.onnx (FP16)
- 6 ランタイム動作確認: 全 OK

## 実験結果

### SER (英語感情認識精度)

| 感情 | 精度 | サンプル数 |
|------|------|----------|
| angry | XX% | NN |
| disgusted | XX% | NN |
| ... | ... | ... |
| **総合** | **XX%** | 216 |

### MOS (自然性)

| モデル | PESQ | STOI | 自動 MOS |
|-------|------|------|----------|
| Baseline 6lang | Y.YY | 0.YY | Z.ZZ |
| Stage 5a | Y.YY | 0.YY | Z.ZZ |

### 多言語 regression

| 言語 | 生成成功 | 音響劣化 | 備考 |
|------|--------|---------|------|
| JA | ○ | なし | - |
| EN | ○ | なし | CREMA-D 学習言語 |
| ZH | ○ | 軽微 | duration 短縮傾向 |
| ... | ... | ... | ... |

## 成功基準達成状況

### 最低基準 (Go/No-go)
- [x] 英語 SER >= 65%: XX% で達成
- [x] MOS >= 3.8: Y.YY で達成
- [x] レグレッションなし: OK

### 目標
- [△] 英語 SER >= 75%: XX% で未達
- [x] MOS >= 4.0: Y.YY で達成
- [△] 日本語声質維持: 軽微劣化

### ストレッチ
- [ ] 多言語感情認識 60%+: 未測定
- [ ] 補間自然: 未検証
- [ ] 他話者対応: 未検証

## 学び

### Phase 1 (学習側統合)
(fork diff 最小化戦略、style_proj ゼロ初期化による互換性担保、etc.)

### Phase 4 (PE-A loss)
(warmup の重要性、every_n_steps によるコスト削減、etc.)

### Phase 5 (Fine-tune)
(catastrophic forgetting の実測、freeze-dp の効果、etc.)

## 今後の課題

1. 多言語感情対応: シナリオ C (ESD 追加) の検討
2. Stage 5b 実施: Phase 4 完了後の PE-A loss 追加学習
3. 人間評価 MOS: 評価者 10 名 × 30 サンプル × 5 点尺度
4. ベース再学習: 現在のストレッチ未達を解消する大規模実験 (別 Phase)

## 参考文献・成果物

- Phase 0〜5 実装計画: `docs/research/implementation-plan/`
- 全体調査: `docs/research/peav-style-conditioning.md`
- Fork 元: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- モデル (HuggingFace Hub): https://huggingface.co/ayousanz/piper-plus-crema-d-emotion
- 評価レポート: `docs/research/reports/phase-5-evaluation.md`
- ランタイム検証レポート: `docs/research/reports/phase-5-runtime-verification.md`
```

### 2.4 CLAUDE.md 追記テンプレート

「つくよみちゃん 6langベースファインチューニング」セクションの直後に以下を追加:

```markdown
## CREMA-D 感情 finetune (2026-05-XX 完了)

6言語マルチリンガルモデル (571話者, 75 epoch) をベースとして、CREMA-D 感情データ (7,442発話, 91話者, 6 感情) を style vector conditioning 付きで fine-tune。Stage 5a 200 epoch完了。

**ワークフロー:**
1. **学習時**: `--style-vector-dim 256` + `--style-condition-mode global` + `--style-condition-dropout 0.1` で感情条件付け
2. **推論時**: `--style-vector <emotion_centroid>.npy` で感情を指定 (happy / sad / angry / neutral / disgusted / fearful)
3. **Style bank**: P3 で生成した `/data/piper/style_bank_crema_d.npz` から各感情の centroid を抽出

**データセット:** `/data/piper/dataset-crema-d-emotion/` (7,442発話, 91話者, 173 シンボル, en)

**学習コマンド (Stage 5a):**
(phase-5.md §5.4.1 完全形をそのまま引用)

**推論結果:**

| テキスト | 言語 | 感情 | 音声長 |
|---------|------|------|--------|
| "Don't forget a jacket." | EN | angry | X.XXs |
| "Don't forget a jacket." | EN | happy | X.XXs |
| "Don't forget a jacket." | EN | sad | X.XXs |

**生成モデル:** `/data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx`
**チェックポイント:** `output-emotion-fine-tune-v1/lightning_logs/version_0/checkpoints/best.ckpt`
**HuggingFace Hub:** `ayousanz/piper-plus-crema-d-emotion`
```

「実装済み機能」セクションに以下を追加:

```markdown
### Style Vector Conditioning (--style-vector-dim)

Fine-tune 時に PE-A (Perception Encoder Audio-Visual) で抽出した style vector を条件付け入力として追加。感情 TTS に利用可能。デフォルト無効 (`--style-vector-dim 0`)、Phase 5 で CREMA-D 対応済み。

**CLIオプション:** `--style-vector-dim N` (デフォルト: 0), `--style-condition-mode {global,text}` (デフォルト: global), `--style-condition-dropout F` (デフォルト: 0.0)
**実装:** `vits/models.py`, `vits/lightning.py`, `vits/dataset.py`, `__main__.py`, `export_onnx.py`, `infer_onnx.py`
**ランタイム:** Python, C++, Rust, C#, Go, WASM (全 6 ランタイム対応)
**テスト:** `tests/test_style_vector_conditioning.py`, `test/python/test_style_vector.py`, etc.
**関連ツール:** `src/python/piper_train/tools/build_pea_style_bank.py`, `inject_style_labels.py`
```

「ファイルパス > 学習済みモデル」テーブルに以下を追加:

```markdown
| **CREMA-D emotion v1 (Stage 5a)** | `/data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx` | 200 epoch完了 (2026-05-XX) -- 6langベースから転移、91話者、6感情対応 |
```

「HuggingFaceリソース」テーブルに以下を追加:

```markdown
| CREMA-D emotion モデル | `ayousanz/piper-plus-crema-d-emotion` |
```

## 3. エージェントチーム構成

| 役割 | 人数 | 主な責務 |
|------|------|---------|
| Aggregator | 1 | Phase 0〜5 全チケットの成果物を集約、レポート構成を組み立て |
| Writer | 1 | `pea-style-conditioning-report.md` の Markdown 整形、数値差し込み |
| CLAUDE.md Updater | 1 | CLAUDE.md への追記、既存構成との整合性確認、リンク検証 |

## 4. 提供範囲 (Deliverables)

- [ ] `docs/research/reports/pea-style-conditioning-report.md` (新規)
- [ ] `CLAUDE.md` (更新)
- [ ] PR-G final commit (全 Phase 5 変更 + docs 更新)

**提供範囲外**:
- 人間評価 MOS 集計 (optional、別セッション)
- シナリオ B/C 実行 (評価結果次第で別 Phase にスコープ切り出し)
- ベース再学習提言の詳細計画 (別 Phase)

## 5. テスト項目

### 5.1 Unit テスト

- 該当なし (ドキュメント作成のみ)

### 5.2 E2E テスト

- `pea-style-conditioning-report.md` の Markdown が正常レンダリング (GitHub プレビューで確認)
- 内部リンク (`docs/research/...`, `CLAUDE.md`, etc.) が 404 にならない
- CLAUDE.md の追記箇所がテンプレート構造と一致 (Markdown prettier or mdformat でチェック)
- CLAUDE.md の mermaid 図や表フォーマットが崩れていない

### 5.3 人間レビュー (必須)

- ユーザー (ayousanz) がレポートと CLAUDE.md を最終確認
- 表現のニュアンス、数値の解釈、今後の課題の優先順位を調整

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **成功基準未達の場合のレポート表現**: 最低基準を満たさない場合、本家統合「NG」と明記する必要あり。ユーザーの期待と異なる場合があるため、レポート前に簡単なサマリを提示して合意取得
- **Stage 5b 実施可否**: Phase 4 完了 + Stage 5a 評価 OK が前提。どちらかが未完了なら「未実施」と明記し、Phase 5 の完了条件から除外
- **人間評価 MOS の扱い**: optional なのでレポート段階では「自動評価のみ」と明記、後日追記可能な構造にする
- **CLAUDE.md の肥大化**: 現状でも 600+ 行あり、Phase 5 追加で 700+ 行に。既存セクションの簡略化 (例: アーカイブ情報の外部 Markdown 化) を別チケットで検討
- **多言語 regression 結果の解釈**: CREMA-D 英語のみ fine-tune の影響で他言語品質が落ちた場合、それを「失敗」と捉えるか「trade-off」と捉えるかは価値判断。レポートでは両解釈を併記
- **HuggingFace Hub 公開ライセンス表記**: ODbL の要件 (帰属表示 + share-alike) を README に明記しないと violation。ユーザー判断で公開可否決定

### 6.2 レビュー項目

- [ ] Executive Summary が 3〜5 行で Go/No-go を明示
- [ ] 成功基準 3 段階 (最低/目標/ストレッチ) 全てについて ○/×/△ が付いている
- [ ] 学びセクションが Phase ごとに 2〜3 文で簡潔
- [ ] 今後の課題が具体的な次アクション (シナリオ B/C, 別 Phase 起票等) に落ちている
- [ ] CLAUDE.md の追記が既存セクション (つくよみちゃん 6lang-v2) と並列的に整合
- [ ] 「学習済みモデル」テーブルに Stage 5a エントリが追加
- [ ] 「HuggingFaceリソース」テーブルに CREMA-D モデルエントリが追加
- [ ] Markdown の内部リンク全て有効 (相対パス + 見出しアンカー)

## 7. 一から作り直すとしたら

### 7.1 代替案の検討

- **代替案 A: レポートを英語で書く**
    - 利点: 国際的な読者層にリーチ、Hugging Face Hub README と整合
    - 欠点: プロジェクト主言語が日本語、翻訳工数追加
- **代替案 B: レポートを Jupyter Notebook 形式で作成**
    - 利点: 数値・図・コード混在、再現性高い
    - 欠点: GitHub プレビューで閲覧性低下、編集がしにくい
- **代替案 C: CLAUDE.md ではなく別ファイル (`docs/features/crema-d-emotion.md`) に詳細記述**
    - 利点: CLAUDE.md の肥大化回避、機能単位のドキュメント分離
    - 欠点: プロジェクト全体像 (CLAUDE.md) から情報が分散、Claude Code 起動時のコンテキスト取得が複雑化
- **代替案 D: レポートを Notion / Confluence 等の外部ドキュメント化**
    - 利点: リッチな編集・コラボレーション
    - 欠点: リポジトリ外でバージョン管理が分離、Claude Code からのアクセス不可

### 7.2 現在の実装を選んだ理由

- プロジェクト慣習 (`docs/research/reports/`) に沿う、既存のバイリンガル調査レポート等と統一
- CLAUDE.md は Claude Code 起動時の必須コンテキストのため、主要機能はここに集約
- Markdown で PR レビュー時の diff が見やすい、GitHub プレビューで即閲覧可能

### 7.3 リファクタ機会 (将来)

- `pea-style-conditioning-report.md` を将来の Phase 6+ の入口ドキュメント化、継続的な追記を前提に構造化
- CLAUDE.md のアーカイブ情報 (バイリンガル v2/v3/v4) を `docs/archive/` に外部化、CLAUDE.md 本体を軽量化
- CI で CLAUDE.md の lint (Markdown リンク + 表の整合性) を自動化

## 8. 後続タスクへの連絡事項

- **PR-G final commit**: 本チケット完了後、PR-G (`exp(finetune): CREMA-D fine-tune of 6lang base + evaluation report`) をマージ候補に。ユーザーレビュー後の commit は Claude Code が `git commit` で実施
- **Phase 5 完了宣言**: 本チケット + P5-T01〜T04 完了で Phase 5 完了、マイルストーン #15 close
- **Phase 6 起票判断**: ストレッチ未達項目があれば Phase 6 (シナリオ B/C, 多言語感情対応, ベース再学習) を別 Phase として起票。ユーザー判断
- **人間評価 MOS 実施**: 評価者確保後に別チケットで実施、結果を `pea-style-conditioning-report.md` に追記

## 9. 参考リンク

- `phase-5.md §5.7` 成功基準
- `phase-5.md §5.10` 判定フロー
- CLAUDE.md 「つくよみちゃん 6langベースファインチューニング」 (テンプレート参考)
- CLAUDE.md 「実装済み機能」 (Style Vector Conditioning 追記テンプレート参考)
- CLAUDE.md 「HuggingFaceリソース」 (新エントリ追加先)
- 既存レポート例: `docs/research/peav-style-conditioning.md`
- GitHub Flavored Markdown: https://github.github.com/gfm/
