# Phase 3: Style Bank 生成ツール

| 項目 | 値 |
|------|-----|
| Phase | 3 |
| マイルストーン | [#13 Style Bank 生成ツール](https://github.com/ayutaz/piper-plus/milestone/13) |
| 期日 | 2026-04-30 |
| Claude Code 工数目安 | 4〜8h (CREMA-D DL 待ち含む) |
| 関連 PR | PR-E (`feat(tools): build_pea_style_bank.py + inject_style_labels.py + CREMA-D loader`) |
| 前提 | Phase 0 完了 (PE-A loader 確定) |
| 後続 | Phase 4 (PE-A emotion loss 学習側統合) |

## 概要

Phase 3 は、fork `yusuke-ai/piper-plus` の PE-A emotion loss で使用される style bank (.npz) を自前で生成するツールを作成することが目的。yusuke-ai fork の .npz スキーマ (`emotion_names`, `emotion_centroids`, `global_centroid`) は既に解析済みで、本家 `ayutaz/piper-plus` で独自生成する工程を本 Phase で確立する。

成果物は以下の 3 種類のツールと関連ドキュメント:

1. **CREMA-D データセットローダ**: 商用可能な ODbL ライセンスの英語感情データセット (7,442 発話、6 感情、91 話者) を自動取得
2. **`build_pea_style_bank.py`**: 感情ラベル付き音声データセットから PE-A model で embedding を抽出し style bank を生成
3. **`inject_style_labels.py`**: 既存 dataset manifest (LibriTTS-R, MOE-Speech, 6lang 等) に感情ラベルと style_vector_path を注入
4. **`validate_style_bank.py` + ドキュメント**: .npz の完全性検証と、他の感情データセット (ESD/EmoV-DB/JTES) への対応ガイド

## チケット一覧

| # | タイトル | 工数 | 優先度 | 依存 | ステータス |
|---|--------|------|-------|------|----------|
| [P3-T01](P3-T01.md) | CREMA-D データセットダウンロード + 整形 | 2〜3h | 高 | なし | 未着手 |
| [P3-T02](P3-T02.md) | build_pea_style_bank.py 実装 | 2〜3h | 高 | P0-T03, P3-T01 | 未着手 |
| [P3-T03](P3-T03.md) | inject_style_labels.py 実装 (既存データセット拡張) | 1h | 中 | P3-T02 | 未着手 |
| [P3-T04](P3-T04.md) | .npz 検証スクリプト + ドキュメント | 1h | 中 | P3-T02 | 未着手 |

**合計**: 6〜8h (Claude Code 工数、CREMA-D DL 待ち 2〜3h を含む)

## 依存関係図

```
              P0-T03 (PE-A loader)
                       │
                       ▼
  P3-T01 ──────────► P3-T02 ─┬─► P3-T03
(CREMA-D DL)      (style_bank 生成)  │ (manifest 注入)
                                    │
                                    └─► P3-T04
                                         (検証 + docs)
```

**並列実施可能**:
- P3-T01 は P3-T02 の入力だが、先行して DL 開始しておける (2〜3h 並行)
- P3-T03 と P3-T04 は P3-T02 完了後に並列開始可能

**クリティカルパス**: P3-T01 → P3-T02 → P3-T03 (合計 5〜7h、うち DL 2〜3h)

## 成功基準

Phase 3 の完了判定基準:

- [ ] P3-T01: CREMA-D 7,442 WAV ファイルが `/data/piper/datasets/CREMA-D/AudioWAV/` に配置され、`metadata.csv` と `emotions.csv` が生成されている
- [ ] P3-T02: `style_bank_crema_d.npz` が生成され、`emotion_names=["angry","disgusted","fearful","happy","neutral","sad"]` と `emotion_centroids.shape=(6, D)` を持つ
- [ ] P3-T03: 6lang dataset manifest (508,187 行) に `emotion=neutral`, `style_vector_path=None` が注入されている
- [ ] P3-T04: `validate_style_bank.py --style-bank style_bank_crema_d.npz` が exit code 0 で PASS
- [ ] docs/features/style-bank.md が公開されている
- [ ] 全ユニットテスト PASS (`tests/test_build_pea_style_bank.py`, `tests/test_inject_style_labels.py`, `tests/test_validate_style_bank.py`)

## 一から考えたら

Phase 3 のスコープを一から設計するとしたら、以下の選択肢を検討する。本計画での採択判断理由も合わせて記載。

### 1. 自動感情クラスタリング vs ラベル依存

**選択肢**:
- A. ラベル依存 (CREMA-D の 6 感情ラベルを使用) ← **採用**
- B. K-means クラスタリングで教師なし感情抽出
- C. ハイブリッド (ラベル初期化 + K-means 微調整)

**判断**:
- fork `yusuke-ai/piper-plus` の PE-A loss が `emotion_names: list[str]` を前提にしているため、ラベル依存が互換性の観点で最もリスクが低い
- 教師なしクラスタリングは将来の拡張機能 (`--clustering-mode kmeans`) として残し、Phase 3 では採用しない
- 複数言語への展開は、CREMA-D 以外の dataset を追加 manifest として注入する形で対応 (言語中立な emotion 空間を学習するため)

### 2. Style bank の形式 (.npz vs .safetensors vs sqlite)

**選択肢**:
- A. `.npz` (numpy native、fork 互換) ← **採用**
- B. `.safetensors` (secure、メタデータリッチ)
- C. SQLite (検索可能、インクリメンタル更新)

**判断**:
- fork との byte-for-byte 互換性が最優先 → `.npz` 一択
- `.safetensors` は将来 PE-A loss を safetensors に切り替える場合の拡張候補
- SQLite は大規模 emotion bank (1000+ emotions) が必要になった場合の将来オプション

### 3. PE-A 抽出を毎回実行 vs 話者 embedding 再利用

**選択肢**:
- A. PE-A model で毎回抽出 ← **採用**
- B. MOE-Speech 等の既存話者 embedding を再利用 (DimReduction)
- C. 両方を並列抽出して平均

**判断**:
- PE-A (Perception Encoder Audio-Visual) は感情特化モデルで、話者 embedding (speaker identity) とは別の情報空間を学習している
- 話者 embedding は「誰が話しているか」、PE-A embedding は「どう話しているか (感情)」を表現するため、単純な再利用は不適切
- 計算コスト削減のため、`--per-utterance-dir` で PE-A embedding を disk にキャッシュし、再利用可能な形で保存する

### 4. CREMA-D 以外のデフォルト感情 dataset

**選択肢**:
- A. CREMA-D のみ (英語、ODbL、商用可) ← **採用**
- B. CREMA-D + EmoV-DB (英語、CC-BY、商用可)
- C. CREMA-D + ESD (英語+中国語、研究目的)
- D. CREMA-D + JTES (日本語、研究目的)

**ライセンス整理** (`peav-style-conditioning.md §12` より):

| Dataset | 言語 | 感情数 | 発話数 | ライセンス | 商用可否 |
|---------|------|------|-------|----------|---------|
| CREMA-D | EN | 6 | 7,442 | ODbL 1.0 + Community | ✅ |
| EmoV-DB | EN | 5 | 7,000 | CC-BY 4.0 | ✅ |
| ESD | EN+ZH | 5 | 35,000 | 研究目的 | ⚠ (商用時は attribution 厳格化) |
| JTES | JA | 4 | ~20,000 | 研究目的 | ⚠ |

**判断**:
- Phase 3 の初期スコープでは CREMA-D 単独で十分 (7,442 発話 × 6 感情)
- EmoV-DB は将来 EN 拡張で併用候補 (CC-BY で商用可)
- ESD/JTES は商用利用時のリスクがあるため、Phase 5 以降の研究用途に限定
- 多言語感情 bank が必要な場合、将来的に CREMA-D + EmoV-DB + MOE-Speech (日本語、自前) の混成を検討

### 5. Style bank を Hugging Face Hub に置いて自動 DL

**選択肢**:
- A. ユーザーが自前で生成 ← **採用 (Phase 3)**
- B. 公式 style bank を HF Hub に公開 (例: `ayousanz/piper-plus-pea-style-bank`) ← **将来 (Phase 5 以降)**
- C. build_pea_style_bank.py を pip パッケージ化し HF にキャッシュ

**判断**:
- Phase 3 段階では、ユーザーが自前で生成できるツールを整備することが優先 (再現性とカスタマイズ性)
- Phase 5 完了後、品質が確認された時点で公式 style bank を HF Hub 公開する計画
- 将来的に `piper-plus --style-bank-preset english-emotion-6` のような CLI フラグで HF 自動 DL する UX を追加

### 6. 感情オントロジーの選択 (6 感情 vs Plutchik 8 vs OCEAN 5)

**選択肢**:
- A. Ekman 6 (angry, disgusted, fearful, happy, neutral, sad) ← **採用 (CREMA-D 準拠)**
- B. Plutchik 8 (+ anticipation, trust)
- C. OCEAN 5 personality (openness, conscientiousness, extraversion, agreeableness, neuroticism)

**判断**:
- CREMA-D が Ekman 6 で収録されているため、初期版は Ekman 6 で統一
- 将来的に感情の混合 (joy + surprise = excitement) を表現したい場合、Plutchik 8 や soft labeling (distribution) への拡張を検討
- OCEAN 5 は personality 軸であり、短時間の感情表現には適さない

## ライセンスと attribution

本 Phase で使用するデータセットとモデルのライセンス:

- **CREMA-D**: Open Database License (ODbL) 1.0 + Community License → 商用可、attribution 推奨
- **facebook/pe-av-small**: Apache-2.0 License → 商用可
- **piper-plus (本家)**: MIT License → 商用可

attribution 記載場所:
- `LICENSE_CREMA_D.txt` (dataset_dir 直下)
- `docs/features/style-bank.md` (ドキュメント内)
- `config.json` の `style_bank.source` フィールド (将来的に)

## 参考リンク

### Phase 3 内部リンク

- [P3-T01: CREMA-D データセットダウンロード + 整形](P3-T01.md)
- [P3-T02: build_pea_style_bank.py 実装](P3-T02.md)
- [P3-T03: inject_style_labels.py 実装 (既存データセット拡張)](P3-T03.md)
- [P3-T04: .npz 検証スクリプト + ドキュメント](P3-T04.md)

### 関連 Phase

- [Phase 0-1](../../phase-0-1.md): PE-A loader (P0-T03) が Phase 3 の前提
- [Phase 3-4](../../phase-3-4.md): Phase 3 と Phase 4 の詳細実装計画 (本チケットの元ドキュメント)
- [Phase 5](../../phase-5.md): Phase 3 で生成した style bank を fine-tune で使用

### 外部リソース

- CREMA-D: https://github.com/CheyneyComputerScience/CREMA-D
- facebook/pe-av-small: https://huggingface.co/facebook/pe-av-small
- Perception Encoder 論文: https://arxiv.org/abs/2512.19687
- Fork (yusuke-ai/piper-plus): https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- ODbL 1.0: https://opendatacommons.org/licenses/odbl/1-0/

### 前提資料

- 全体調査: [`../../../peav-style-conditioning.md`](../../../peav-style-conditioning.md)
- 実装計画トップ: [`../../README.md`](../../README.md)
