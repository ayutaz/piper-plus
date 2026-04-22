# Phase 5 チケット INDEX (Fine-tune 実験 CREMA-D)

**Phase 5 の目的**: 6lang ベースモデル (`epoch=74-step=504712.ckpt`) に CREMA-D データセットを style vector conditioning 付きで fine-tune し、感情 TTS の性能を定量評価する。ベース再学習は行わず、fine-tune のみでの実装方針。

**マイルストーン**: [#15](https://github.com/ayutaz/piper-plus/milestone/15)
**期日**: 2026-05-08
**Claude Code 工数目安**: 1〜2 日 (実装・評価) + GPU 2 日 (学習、バックグラウンド)
**関連 PR**: PR-G (`exp(finetune): CREMA-D fine-tune of 6lang base + evaluation report`)

---

## 1. 概要

Phase 0〜4 の実装完了後、実際に学習・評価を実施するフェーズ。Stage 5a (style conditioning のみ) と Stage 5b (PE-A loss 追加、Phase 4 完了時のみ) の 2 段階設計だが、本 Phase 5 の必須範囲は Stage 5a のみ。Stage 5b は P5-T03 評価結果が成功基準をクリアした場合にオプションで実施する。

主要成果物:

- `/data/piper/dataset-crema-d-emotion/` (CREMA-D fine-tune データセット)
- `/data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx` (Stage 5a モデル)
- `docs/research/reports/phase-5-evaluation.md` (SER + MOS 評価レポート)
- `docs/research/reports/phase-5-runtime-verification.md` (6 ランタイム動作確認)
- `docs/research/reports/pea-style-conditioning-report.md` (Phase 0〜5 最終レポート)
- `CLAUDE.md` 更新 (CREMA-D emotion モデルセクション追加)
- HuggingFace Hub `ayousanz/piper-plus-crema-d-emotion` (optional)

---

## 2. チケット一覧

| チケット | タイトル | 優先度 | Claude Code 工数 | 依存 | 状態 |
|---------|---------|--------|----------------|------|------|
| [P5-T01](P5-T01-crema-d-finetune-dataset.md) | CREMA-D ベース finetune データセット準備 | 最高 | 2〜3h | P3-T01/T02/T03, Phase 1 全完了 | 未着手 |
| [P5-T02](P5-T02-finetune-stage-5a.md) | Fine-tune Stage 5a 実行 (CREMA-D ベース 6lang) | 最高 | 1h + GPU 2 日 | P5-T01, Phase 1 全完了, Phase 4 全完了 (Stage 5b のみ) | 未着手 |
| [P5-T03](P5-T03-evaluation-ser-mos.md) | 評価 (SER 精度、自然性 MOS、ベース比較) | 高 | 4〜6h | P5-T02 | 未着手 |
| [P5-T04](P5-T04-onnx-export-runtime-verification.md) | ONNX エクスポート + 6 ランタイム動作確認 | 高 | 2〜3h | P5-T02, Phase 2 全完了 | 未着手 |
| [P5-T05](P5-T05-final-report-claude-md.md) | 最終レポート + CLAUDE.md 更新 | 高 | 2〜3h | P5-T01〜T04 | 未着手 |

**Claude Code 合計稼働**: 約 11〜16 h (1.5〜2 日相当)
**GPU 学習時間 (バックグラウンド)**: 20〜24 h (1 日)
**総カレンダー時間**: 2〜3 日 (学習と実装の並行を考慮)

---

## 3. 依存関係図

```
[事前条件]
  Phase 1 全完了  ─┐
  Phase 2 全完了  ─┤
  Phase 3 全完了  ─┤
  Phase 4 全完了  ─┤  (Stage 5b のみ必須)
                   │
                   ▼
  P5-T01 (dataset 準備)
                   │
                   ▼
  P5-T02 (Stage 5a 学習) ─── GPU 20〜24h バックグラウンド
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
  P5-T03 (評価)         P5-T04 (ONNX + 6 ランタイム)
        │                     │
        └──────────┬──────────┘
                   ▼
  P5-T05 (最終レポート + CLAUDE.md)
                   │
                   ▼
              PR-G マージ
```

**並列可能**:
- P5-T03 と P5-T04 は P5-T02 完了後に並列起動可能 (評価と ONNX 化は独立)
- GPU 学習 (P5-T02 バックグラウンド) 中に Claude Code は他 Phase の残タスクや評価ツール準備 (P5-T03) を並行実施可

**クリティカルパス**: P5-T01 → P5-T02 → min(T03, T04) → P5-T05

---

## 4. 一から考えたら

Phase 5 を白紙から再設計する場合に検討したい論点を列挙する。本 Phase 5 実装時の判断材料として、また将来のリファクタリング/Phase 6+ 起票時の参考として残す。

### 4.1 Fine-tune vs from-scratch の再考

- **現行: Fine-tune (6lang ベース継承)**
    - 利点: 既存 6 言語品質維持、GPU 2 日で完了、実装パターン (CLAUDE.md のつくよみちゃん事例) が確立
    - 欠点: CREMA-D 英語のみの感情学習で多言語感情表現が不十分、catastrophic forgetting リスク
- **代替: From-scratch**
    - 利点: 感情表現に最適化された model、6lang 制約から解放
    - 欠点: 学習時間 10 倍以上 (75 epoch × 4GPU → 500+ epoch × 1GPU)、既存多言語品質を失う、Phase 5 工数範囲外

phase-5.md §5.x の想定効果差: from-scratch なら英語 SER 80%+ を狙えるが、多言語品質と工数を考慮すると fine-tune が現実解。

### 4.2 CREMA-D vs ESD (多言語) の選択

- **現行: CREMA-D (英語のみ、7,442 発話, 91 話者)**
    - 商用可 (ODbL)、話者多、感情バランス良好、入手容易
- **代替: ESD (英語+中国語、35,000 発話、言語別 10 話者)**
    - 6lang との言語整合性高、大規模
    - 欠点: 研究目的ライセンス (商用不可懸念)、Web フォーム登録 1〜2 営業日待ち
- **代替: CREMA-D + EmoV-DB (英語, 14,442 発話)**
    - CC-BY で商用 OK、話者多様性増
    - 感情ラベル定義不一致 (`amused` vs `happy`) で前処理負荷
- **代替: CREMA-D + JTES (日本語拡張、入手難易度高)**
    - つくよみちゃんでの日本語感情制御に直接寄与
    - 学内申請 1〜2 週間、Phase 5 期日に間に合わず

本 Phase 5 では CREMA-D のみ採用し、ESD/JTES は Phase 6+ のシナリオ C (多言語感情対応) として切り出し。

### 4.3 評価指標: SER 精度 vs 主観 MOS vs A/B テスト

- **現行: 自動 SER (Hugging Face hubert-large-superb-er) + PESQ/STOI**
    - 利点: 完全自動化、再現性高、工数 4〜6h で完結
    - 欠点: SER classifier 自体の精度に依存、音質劣化の主観判定は不十分
- **代替: 主観 MOS (リスナーテスト、評価者 10〜20 名)**
    - 利点: 最終的な音質判定として信頼性高
    - 欠点: 評価者確保 1〜2 週間、集計工数、再現性低
- **代替: A/B blind test (ベース vs Stage 5a)**
    - 利点: 相対比較で感情差を捉えやすい
    - 欠点: 絶対的な品質基準が得られない
- **代替: 6 軸評価 (自然性/感情明瞭度/話者類似度/発話リズム/音素明瞭度/多言語品質)**
    - 利点: 失敗原因の切り分けが容易
    - 欠点: 工数 3 倍、期日内に実施困難

Phase 5 では「自動 SER + PESQ/STOI + 多言語 regression spot check」を必須とし、主観 MOS と A/B test はユーザー判断の optional。

### 4.4 Stage 5a のみ vs Stage 5a + 5b 全部走らせる

- **現行: Stage 5a 必須、Stage 5b は評価結果次第 (Go/No-go)**
    - 利点: 段階的にリスクを抑えられる、Stage 5a 単独の効果を測定可能
    - 欠点: Stage 5b の効果測定は別セッション、Phase 4 完了待ち
- **代替: Stage 5a + 5b を無条件で両方走らせる**
    - 利点: PE-A loss の効果を最大化、1 Phase で完結
    - 欠点: GPU 4 日、Phase 4 未完了時に着手不能
- **代替: Stage 5a を skip して直接 Stage 5b**
    - 利点: 学習回数 1 回で済む、PE-A loss の効果を直接検証
    - 欠点: PE-A loss の NaN リスクが高まる、baseline 比較ができない

Phase 5 は段階的 A → B 方針 (phase-5.md §5.3.4) を採用し、Stage 5a 評価で SER >= 65% を満たした場合のみ Stage 5b を起動。

### 4.5 HuggingFace Hub 自動 CI 化 (学習完了時に自動 release)

- **現行: P5-T04 で手動アップロード**
    - 利点: 単純、失敗時に即 rollback 可能
    - 欠点: 手動作業、複数モデル公開時に工数増
- **代替: GitHub Actions で自動化 (タグ付きリリース → HF Hub 自動 upload)**
    - 利点: 新モデル公開が git tag push のみで完結
    - 欠点: CI infrastructure 整備工数、credentials 管理 (HF_TOKEN secrets)

将来、Phase 6+ で複数モデル (シナリオ B/C) を公開する場合は CI 化を検討。本 Phase 5 では手動で十分。

### 4.6 失敗時のリカバリ: ベース再学習 (別 Phase にスコープ切り出し)

- phase-5.md §5.10 判定フローで「根本問題 → ベース再学習に格上げ」と記載されているが、ベース再学習は Phase 5 の工数 (GPU 2 日) では無理
- ベース再学習は 6lang データセット (508K 発話) から style_vector_dim=256 付きで再学習する大規模実験となり、最低 GPU 10 日以上必要
- 本 Phase 5 で最低基準未達だった場合、Phase 6 として以下を別途起票
    - Phase 6a: データ補強シナリオ B (つくよみちゃん neutral 混入)
    - Phase 6b: データ補強シナリオ C (ESD 中国語追加)
    - Phase 6c: ベース再学習 (最終手段、スコープ大)

Phase 5 最終レポート (P5-T05) で Phase 6+ の推奨スコープを明記する方針。

---

## 5. 成功基準 (phase-5.md §5.7 準拠)

### 5.1 最低基準 (Go/No-go)

以下をすべて満たせば **本家統合成功**:

- 英語感情認識精度: **65% 以上** (自動分類器)
- MOS 自然性: **3.8 以上** (ベース 6lang 比 -0.2 以下)
- 学習収束、validation loss 安定
- `style_vector_dim=0` でのレグレッションなし (既存モデル互換)

### 5.2 目標

実用的品質:

- 英語感情認識精度: **75% 以上**
- MOS 自然性: **4.0 以上** (ベース同等)
- MOS 感情表現: **3.5 以上** (リスナーテスト実施時)
- 日本語 (シナリオ B 時) の声質維持

### 5.3 ストレッチ

理想:

- 多言語感情認識精度: **60% 以上** (英語以外)
- MOS 感情表現: **4.0 以上**
- Style vector 補間で中間感情が自然に出る
- 他話者 (つくよみちゃん等) でも感情制御動作

---

## 6. Phase 5 完了後の判定フロー (phase-5.md §5.10 準拠)

```
P5-T02 完了 (Stage 5a 200 epoch)
     │
     ▼
P5-T03 評価 (SER + MOS)
     │
     ▼
 合格 (最低基準クリア)?
   ├── Yes ──→ P5-T04 (ONNX + 6 ランタイム)
   │             │
   │             ▼
   │         Stage 5b 起動判断 (Phase 4 完了済みなら)
   │             │
   │             ▼
   │         P5-T05 (最終レポート) → PR-G マージ
   │
   └── No  ──→ 原因分析
                 ├── データ不足 → Phase 6a/6b 起票
                 ├── catastrophic forgetting → LR/freeze 調整で P5-T02 再実行
                 └── 根本問題 → Phase 6c (ベース再学習) 起票
```

---

## 7. リスクと対策 (phase-5.md §5.9 準拠)

| リスク | 対策 |
|-------|------|
| CREMA-D DL 長時間 (27GB) | P3-T01 で事前 DL、P5 着手前に完了 |
| fine-tune catastrophic forgetting | `--base_lr 2e-5` + `--freeze-dp` + EMA 0.9995 |
| validation loss 振動 | batch-size 削減 or LR schedule 調整 |
| PE-A loss 不安定 (Stage 5b のみ) | warmup 2000 step、every_n_steps 4 |
| MOS 評価者確保困難 | 内部評価者 + クラウドサービス併用 (optional) |
| 日本語感情表現の弱さ | Phase 6a (シナリオ B) で対応 |
| つくよみちゃん品質劣化 | `--freeze-dp` + 低 LR + ベース比較テスト必須 |
| GPU 2 日のインフラ障害 (OOM, 電源断) | tmux/screen 使用、`--checkpoint-epochs 20` で定期保存 |
| クロスランタイム MD5 不一致 | MEL spectrogram 相関 0.95+ を代替基準 |
| HuggingFace Hub ODbL 表記漏れ | README.md に帰属表示明記 (P5-T04/T05) |

---

## 8. 参考リンク

- Phase 5 詳細計画: [`../phase-5.md`](../../phase-5.md)
- Phase 0〜4 実装計画: [`../README.md`](../README.md)
- 全体調査: [`../../peav-style-conditioning.md`](../../peav-style-conditioning.md)
- CREMA-D: https://github.com/CheyneyComputerScience/CREMA-D
- ESD: https://hltsingapore.github.io/ESD/
- EmoV-DB: https://github.com/numediart/EmoV-DB
- 感情認識モデル: https://huggingface.co/superb/hubert-large-superb-er
- CLAUDE.md「つくよみちゃん 6langベースファインチューニング」 (fine-tune パターン参考)
