# チケット一覧 (Style Vector Conditioning + PE-A Emotion Loss)

Fork `yusuke-ai/piper-plus` の Style Vector Conditioning + PE-A Emotion Loss 機能を本家 `ayutaz/piper-plus` に取り込むための個別チケット管理ディレクトリです。

- **前提調査**: [../../peav-style-conditioning.md](../../peav-style-conditioning.md)
- **フェーズ別実装計画**: [../README.md](../README.md)
- **作成日**: 2026-04-23
- **実装主体**: Claude Code (AIエージェント)

---

## Phase 構成

| Phase | マイルストーン | 期日 | チケット数 | 合計工数 (Claude Code) | 主な PR |
|-------|--------------|-----|----------|--------------------|--------|
| [0](phase-0/README.md) | [#10](https://github.com/ayutaz/piper-plus/milestone/10) | 2026-04-25 | 3 | 30 分〜1h | PR-A |
| [1](phase-1/README.md) | [#11](https://github.com/ayutaz/piper-plus/milestone/11) | 2026-04-28 | 7 | 4〜8h | PR-B |
| [2](phase-2/README.md) | [#12](https://github.com/ayutaz/piper-plus/milestone/12) | 2026-05-04 | 8 | 2〜3 日 (並列) | PR-C + PR-D-{Py,Cpp,Rust,CSharp,Go,Wasm} |
| [3](phase-3/README.md) | [#13](https://github.com/ayutaz/piper-plus/milestone/13) | 2026-04-30 | 4 | 4〜8h | PR-E |
| [4](phase-4/README.md) | [#14](https://github.com/ayutaz/piper-plus/milestone/14) | 2026-05-02 | 5 | 1〜2 日 | PR-F |
| [5](phase-5/README.md) | [#15](https://github.com/ayutaz/piper-plus/milestone/15) | 2026-05-08 | 5 | 1〜2 日 + GPU 2 日 | PR-G |
| **合計** | - | - | **32** | **約 5〜8 日 + GPU 2 日** | **12 PR** |

---

## 全チケット一覧

### Phase 0: facebook/pe-av-small PoC

| ID | タイトル | 優先度 | 工数 | 依存 |
|----|--------|------|-----|------|
| [P0-T01](phase-0/P0-T01.md) | facebook/pe-av-small の HF Hub ロード検証 | 高 | 15 分 | なし |
| [P0-T02](phase-0/P0-T02.md) | 音声入力 + Embedding 抽出推論の検証 | 高 | 15 分 | P0-T01 |
| [P0-T03](phase-0/P0-T03.md) | ベンチマーク + PoC レポート作成 | 高 | 15〜30 分 | P0-T02 |

### Phase 1: Style Vector Conditioning 学習側統合

| ID | タイトル | 優先度 | 工数 | 依存 |
|----|--------|------|-----|------|
| [P1-T01](phase-1/P1-T01-models-style-vector.md) | models.py に style_vector 層を追加 | 高 | 30 分〜1h | P0-T03 |
| [P1-T02](phase-1/P1-T02-dataset-style-vector.md) | dataset.py に style_vector フィールドを追加 | 高 | 30 分〜1h | なし (T01 と並列可) |
| [P1-T03](phase-1/P1-T03-lightning-commons.md) | lightning.py 伝播 + commons.slice_segments 一般化 | 高 | 20 分 | P1-T01, P1-T02 |
| [P1-T04](phase-1/P1-T04-main-cli-load-weights.md) | CLI 4 オプション + shape-aware loader | 高 | 30 分〜1h | P1-T01 |
| [P1-T05](phase-1/P1-T05-infer-style-vector.md) | infer.py に style_vector 推論統合 | 中 | 15〜30 分 | P1-T01 |
| [P1-T06](phase-1/P1-T06-unit-tests.md) | Unit テスト 11 件 (style 8 + load_weights 3) | 高 | 1h | P1-T05 |
| [P1-T07](phase-1/P1-T07-docs-ci-regression.md) | CLAUDE.md 更新 + CI リグレッション確認 | 中 | 10 分 + CI 待ち | P1-T06 |

### Phase 2: ONNX + 6 ランタイム対応

| ID | タイトル | 優先度 | 工数 | 依存 |
|----|--------|------|-----|------|
| [P2-T01](phase-2/P2-T01.md) | ONNX エクスポート拡張 (mask パターン) | 高 | 4〜6h | Phase 1 全完了 |
| [P2-T02](phase-2/P2-T02.md) | Python ランタイム統合 | 高 | 2〜4h | P2-T01 |
| [P2-T03](phase-2/P2-T03.md) | C++ ランタイム統合 | 高 | 6〜8h | P2-T01 |
| [P2-T04](phase-2/P2-T04.md) | Rust ランタイム統合 | 高 | 4〜6h | P2-T01 |
| [P2-T05](phase-2/P2-T05.md) | C# ランタイム統合 | 高 | 4〜6h | P2-T01 |
| [P2-T06](phase-2/P2-T06.md) | Go ランタイム統合 | 高 | 4〜6h | P2-T01 |
| [P2-T07](phase-2/P2-T07.md) | WASM/JS ランタイム統合 (npm) | 高 | 4〜6h | P2-T01 + P2-T04 |
| [P2-T08](phase-2/P2-T08.md) | クロスランタイム互換性テスト | 高 | 3〜4h | P2-T02〜T07 |

### Phase 3: Style Bank 生成ツール

| ID | タイトル | 優先度 | 工数 | 依存 |
|----|--------|------|-----|------|
| [P3-T01](phase-3/P3-T01.md) | CREMA-D データセット DL + 整形 | 高 | 2〜3h | なし |
| [P3-T02](phase-3/P3-T02.md) | build_pea_style_bank.py 実装 | 高 | 2〜3h | P0-T03 + P3-T01 |
| [P3-T03](phase-3/P3-T03.md) | inject_style_labels.py 実装 | 中 | 1h | P3-T02 |
| [P3-T04](phase-3/P3-T04.md) | 検証スクリプト + docs/features/style-bank.md | 中 | 1h | P3-T02 |

### Phase 4: PE-A Emotion Loss 学習側統合

| ID | タイトル | 優先度 | 工数 | 依存 |
|----|--------|------|-----|------|
| [P4-T01](phase-4/P4-T01-pea-loader-style-bank.md) | PE-A loader + style bank loader 実装 | 高 | 2〜3h | P0-T03 + P3-T02 |
| [P4-T02](phase-4/P4-T02-compute-pea-emotion-loss.md) | _compute_pea_emotion_loss 実装 (3 項合成) | 高 | 2〜3h | P4-T01 |
| [P4-T03](phase-4/P4-T03-training-step-integration.md) | training_step_g への合算 + warmup | 高 | 2〜3h | P4-T02 |
| [P4-T04](phase-4/P4-T04-cli-pea-emotion-options.md) | CLI 9 オプション (--pea-emotion-*) | 中 | 1h | P4-T03 |
| [P4-T05](phase-4/P4-T05-pea-emotion-loss-tests.md) | PE-A loss Unit テスト 6 件 | 高 | 1〜2h | P4-T04 |

### Phase 5: Fine-tune 実験 (CREMA-D)

| ID | タイトル | 優先度 | 工数 | 依存 |
|----|--------|------|-----|------|
| [P5-T01](phase-5/P5-T01-crema-d-finetune-dataset.md) | CREMA-D ベース finetune データセット準備 | 高 | 2〜3h | P3-T01〜T03 |
| [P5-T02](phase-5/P5-T02-finetune-stage-5a.md) | Fine-tune Stage 5a 実行 (GPU 2 日) | 高 | 1h + GPU 2 日 | P5-T01 + Phase 1〜4 |
| [P5-T03](phase-5/P5-T03-evaluation-ser-mos.md) | 評価 (SER + MOS + 多言語 regression) | 高 | 4〜6h | P5-T02 |
| [P5-T04](phase-5/P5-T04-onnx-export-runtime-verification.md) | ONNX export + 6 ランタイム動作確認 | 高 | 2〜3h | P5-T02 + Phase 2 |
| [P5-T05](phase-5/P5-T05-final-report-claude-md.md) | 最終レポート + CLAUDE.md 更新 | 中 | 2〜3h | P5-T04 |

---

## 全体依存関係図

```
Phase 0 (PoC)
  P0-T01 → P0-T02 → P0-T03
                      │
           ┌──────────┴──────────┐
           │                     │
           ▼                     ▼
  Phase 1 (学習統合)    Phase 3 (Style bank)
  T01 ┐                   P3-T01
  T02 ┤                     │
      ├→ T03 → T04          ▼
      │         │         P3-T02
      │         ▼           │
      │        T05         ├─→ P3-T03
      │         │           │
      │         ▼           ▼
      │        T06       P3-T04
      │         │
      │         ▼
      └──────→ T07
                │
     ┌──────────┴──────────┐
     │                     │
     ▼                     ▼
Phase 2 (ONNX+6 runtime)  Phase 4 (PE-A loss)
  P2-T01                    P4-T01 (P3-T02 も前提)
    │                         │
  P2-T02〜T07 並列 (6 並列)    P4-T02
    │                         │
    └→ P2-T08 (互換性)      ┌──┴──┐
                           T03   T04
                             └─┬─┘
                               ▼
                             P4-T05
                               │
                               ▼
                         Phase 5 (Fine-tune)
                           P5-T01 → P5-T02 → P5-T03 → P5-T04 → P5-T05
                                   (GPU 2 日 BG)
```

**並列可能ポイント**:
- Phase 1 と Phase 3: P0-T03 完了後は並列開始可能
- Phase 2 と Phase 4: Phase 1 + Phase 3 完了後は並列開始可能
- Phase 2 内部 T02〜T07 は 6 Agent 並列で同時着手可能

---

## 使い方

### チケットの進め方

1. **新しいチケットに着手する前に**:
    - 依存チケットが完了していることを確認 (各チケット先頭の表の「依存チケット」欄を参照)
    - 該当 Phase README の「依存関係図」を確認
2. **着手時**:
    - チケットの §1.2 (Definition of Done) を読み、完了条件を把握
    - §3 (エージェントチーム構成) を確認し、必要な Agent を起動
3. **実装中**:
    - §6 (懸念事項とレビュー項目) を随時参照
    - §7 (一から作り直すとしたら) を読み、現在の実装方針の理由を把握
4. **完了時**:
    - §4 (提供範囲 Deliverables) のチェックリストを全て満たすこと
    - §5 (テスト項目) の Unit/E2E テストをパス
    - §8 (後続タスクへの連絡事項) を次チケットに引き継ぎ

### ステータス管理

チケット本体の「ステータス」欄を以下のいずれかに書き換えます:

- **未着手** (デフォルト、作成時)
- **着手中** (Agent が作業開始時)
- **レビュー中** (実装完了、レビュー待ち)
- **完了**
- **ブロック** (依存関係待ち、または懸念事項で停止中)

---

## 一から考えたら (プロジェクト全体)

このプロジェクトを白紙から設計し直すとしたら、以下の論点を検討します。Phase 単位の「一から考えたら」(各 Phase README に記載) は個別観点の深掘り、こちらは統合観点のレビューです。

### 論点 1: Fork cherry-pick vs ゼロから再実装

- **現状 (採用)**: Fork `yusuke-ai/piper-plus` コミット `314b3355` を cherry-pick ベースに取り込み、PE-A loss 部分を Phase 4 に分離
- **代替 A**: 完全にゼロから再実装
    - 利点: 本家コーディング規約に完全整合、不要コード混入なし
    - 欠点: PE-A loss の定義 (direction + centroid + margin) の実験的知見を失う、re-invent the wheel
- **代替 B**: Fork を submodule 化して追従
    - 利点: upstream 追従が容易
    - 欠点: 本家の CI/ビルドパイプラインに馴染まない
- **採用理由**: cherry-pick は fork の設計判断 (loss 定義、scaling 順序、style_proj ゼロ初期化) を継承しつつ、PE-A 除外で段階導入できる

### 論点 2: Phase 1 + Phase 4 を 1 つの PR に統合するか

- **現状 (採用)**: 分割 (PR-B = Style Vector, PR-F = PE-A Loss)
- **代替**: 統合 PR で一度に merge
    - 利点: 依存関係がシンプル、レビュー一回で完結
    - 欠点: PR が巨大化し、レビュー負荷が爆発
- **採用理由**: PE-A Loss は PE-A model のロード失敗リスクがあり、Style Vector Conditioning (dim=0 で後方互換) だけでも独立価値がある

### 論点 3: Phase 2 の 6 ランタイム同時対応 vs Python 先行

- **現状 (採用)**: ONNX エクスポート (PR-C) 後、6 ランタイム (PR-D-*) を並列実施
- **代替**: Python のみ先行 merge、他ランタイムは別リリース
    - 利点: Python ユーザーに早期価値提供
    - 欠点: ランタイム間の API 非整合が長期化、CLAUDE.md の「8 言語対応」宣言と矛盾
- **採用理由**: 既存 Phoneme Timing / Speaker Encoder も同様に 6 ランタイム同時対応しており、先例に沿う

### 論点 4: データセット選択 (CREMA-D vs ESD)

- **現状 (採用)**: CREMA-D 単独 (ODbL、商用可、英語 7,442 発話)
- **代替 A**: ESD (多言語、CC-NonCommercial)
    - 利点: 最初から多言語感情対応
    - 欠点: 商用利用不可、piper-plus のライセンス方針と不整合
- **代替 B**: CREMA-D + EmoV-DB (英語 2 データセット合成)
    - 利点: データ量増、話者多様性向上
    - 欠点: 前処理コスト 2 倍
- **代替 C**: JTES (日本語感情)
    - 利点: piper-plus の主要言語 (JA) で感情対応
    - 欠点: 研究目的ライセンス、Phase 5 の成功基準 (英語 SER 65%+) と不整合
- **採用理由**: CREMA-D は ODbL で商用可、英語データ量が十分、Phase 5 失敗時にシナリオ B (ESD 追加) で拡張可能

### 論点 5: 評価プロトコル (自動のみ vs MOS も実施)

- **現状 (採用)**: 自動評価 (SER + PESQ/STOI) 必須、MOS は optional
- **代替**: MOS を必須化
    - 利点: 自然性を人間で定量評価
    - 欠点: 評価者手配 (Google Form + 回答者募集) で 1〜2 週間追加
- **採用理由**: 自動評価で phase 5 の採否判定は可能、MOS はリリース後の検証で実施

### 論点 6: GitHub Milestone vs Project Board vs Linear

- **現状 (採用)**: GitHub Milestone (#10〜#15) + チケット docs を相互リンク
- **代替 A**: GitHub Projects (kanban)
    - 利点: drag & drop で状態管理、beta v2 で柔軟な view
    - 欠点: 非公開 repo で可視性が劣る、docs との一貫性が取りにくい
- **代替 B**: Linear / Jira
    - 利点: 進捗集計・レポートが強力
    - 欠点: 外部サービス依存、piper-plus は OSS なので GitHub 内完結が望ましい
- **採用理由**: GitHub Milestone は期日管理が可能で、Issue/PR 連携も標準、docs/tickets との相互リンクで進捗可視化

### 論点 7: チケット粒度 (詳細 32 件 vs 粗い 12 件)

- **現状 (採用)**: 32 件 (各 15 分〜8h の粒度)
- **代替**: Phase 内を粗く 2〜3 件にまとめる
    - 利点: チケット管理オーバーヘッド削減
    - 欠点: 並列作業できない、進捗の見える化が粗い
- **採用理由**: Claude Code が Agent 並列で作業する前提なので、細粒度の方が並列化と進捗管理に有利

---

## 成功基準 (プロジェクト全体)

以下を全て満たせば本家統合成功と判定:

- [ ] **機能**: Phase 0〜5 全チケット完了 (32/32)
- [ ] **品質**: 英語感情認識精度 **65% 以上** (自動分類器、Phase 5)
- [ ] **自然性**: MOS **3.8 以上** (ベース 6lang 比で -0.2 以下、Phase 5)
- [ ] **互換性**: 6 ランタイムで byte-for-byte 一致 (Phase 2 P2-T08)
- [ ] **後方互換**: `style_vector_dim=0` で既存モデルに影響なし (Phase 1 P1-T06)
- [ ] **学習安定性**: 1 epoch dry-run で NaN なし (Phase 4 P4-T05)

---

## 進捗サマリー

| Phase | 完了 | 着手中 | 未着手 | 合計 |
|-------|-----|-------|-------|------|
| 0 | 0 | 0 | 3 | 3 |
| 1 | 0 | 0 | 7 | 7 |
| 2 | 0 | 0 | 8 | 8 |
| 3 | 0 | 0 | 4 | 4 |
| 4 | 0 | 0 | 5 | 5 |
| 5 | 0 | 0 | 5 | 5 |
| **合計** | **0** | **0** | **32** | **32** |

進捗は各 Phase README の「進捗」セクションおよび GitHub Milestone で確認できます。

---

## 参考リンク

- 全体調査: [../../peav-style-conditioning.md](../../peav-style-conditioning.md)
- 実装計画 (Phase 単位): [../README.md](../README.md)
- 詳細設計 (Phase 別): [../phase-0-1.md](../phase-0-1.md), [../phase-2.md](../phase-2.md), [../phase-3-4.md](../phase-3-4.md), [../phase-5.md](../phase-5.md)
- GitHub Milestones: https://github.com/ayutaz/piper-plus/milestones
- Fork 元: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
