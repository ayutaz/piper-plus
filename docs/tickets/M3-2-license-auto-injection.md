# [M3.2] Model card / license auto-injection

**親マイルストーン**: [M3 ABI & Ecosystem Hardening](./M3-overview.md)
**親調査**: [ci-expansion-2026-05.md §Top 10 #7](../proposals/ci-expansion-2026-05.md)
**Top 10 内番号**: #7
**ステータス**: 未着手
**想定工数**: 2 PR (~15h)
**優先度**: 中
**作成日**: 2026-05-18

---

## 1. タスクの目的とゴール

### 目的

HF Hub にアップロードされる ONNX 同梱物に、 **学習データセット (LibriTTS-R / AISHELL-3 / CML-TTS / MOE-Speech) の attribution / license 情報** を build 時に
自動 injection する。

### なぜ必要か

- **法務リスクの非対称性**: 各データセットには attribution 要件がある
  (CML-TTS は CC BY 4.0 で attribution required、 AISHELL-3 は Apache-2.0、
  LibriTTS-R は CC BY 4.0、 MOE-Speech は CC BY-SA 4.0 想定 — 要確認)。
  HF Hub 上の ONNX を再配布する downstream が attribution を持たないと
  license violation の連鎖が発生する。
- **手動忘れの再発防止**: release engineer が手動で `MODEL_CARD.md` を書く運用は、
  quarterly release / patch release の頻度が上がると attribution 漏れ確率が線形上昇。
- **deterministic injection の副次効果**: 「どの commit のどの dataset 状態で生成された
  ONNX か」 が HF Hub 上の README から追跡可能になり、 reproducibility に寄与。

### ゴール (完了基準)

- `data-sources.yml` (canonical source) を repository root に commit
- `scripts/generate_model_card.py` が `data-sources.yml` から `MODEL_CARD.md` +
  `LICENSE_ATTRIBUTIONS.md` を deterministic 生成
- `.github/workflows/release-shared-lib.yml` と `deploy-huggingface.yml` の publish 直前に
  hook が動作し、 ONNX 同梱物に attribution が含まれる
- 次回 HF Hub release で `MODEL_CARD.md` が auto-injection されることを手動確認

---

## 2. 実装する内容の詳細

### 2.1 対象データセット (6 言語マルチリンガル base)

CLAUDE.md のデータセット表より、 `dataset-multilingual-6lang-filtered` の内訳:

| 言語 | データセット | 話者数 | 発話数 | License (推定) | URL |
|------|------------|--------|--------|----------------|-----|
| ja | MOE-Speech (20 speakers) | 20 | 60,148 | CC BY-SA 4.0 (要確認) | <https://huggingface.co/datasets/ayousanz/moe-speech-20speakers-ljspeech> |
| en | LibriTTS-R | 310 | 74,912 | CC BY 4.0 | <https://www.openslr.org/141/> |
| zh | AISHELL-3 | 142 | 63,223 | Apache-2.0 | <https://www.aishelltech.com/aishell_3> |
| es | CML-TTS (es subset) | 63 | 168,374 | CC BY 4.0 | <https://github.com/freds0/CML-TTS-Dataset> |
| fr | CML-TTS (fr subset) | 28 | 107,464 | CC BY 4.0 | <https://github.com/freds0/CML-TTS-Dataset> |
| pt | CML-TTS (pt subset) | 8 | 34,066 | CC BY 4.0 | <https://github.com/freds0/CML-TTS-Dataset> |

つくよみちゃん FT 版は別途 つくよみちゃんコーパスの license 表記 (CC BY 4.0 + 個別商用利用条件) が必要。

### 2.2 `data-sources.yml` の schema 設計

canonical source として repository root に配置。 `scripts/generate_model_card.py` の
input。 forward-compat を考慮した `schema_version` 付き:

```yaml
# data-sources.yml
schema_version: 1
last_reviewed: "2026-05-18"
review_period_months: 3  # quarterly review 推奨

datasets:
  - id: moe-speech-20speakers
    language: ja
    language_code: 0
    title: "MOE-Speech (20 speakers, LJSpeech format)"
    speakers: 20
    utterances: 60148
    license:
      spdx: "CC-BY-SA-4.0"  # TODO: 要確認 (placeholder)
      verified: false        # verified=true まで MODEL_CARD に warning 表記
      url: "https://creativecommons.org/licenses/by-sa/4.0/"
    source:
      url: "https://huggingface.co/datasets/ayousanz/moe-speech-20speakers-ljspeech"
      commit_or_version: "HF Hub revision @ 2026-03-16"
    attribution_required: true
    attribution_text: |
      MOE-Speech 20 speakers corpus, distributed under CC BY-SA 4.0 by ayousanz.

  - id: libritts-r
    language: en
    language_code: 1
    title: "LibriTTS-R"
    speakers: 310
    utterances: 74912
    license:
      spdx: "CC-BY-4.0"
      verified: true
      url: "https://creativecommons.org/licenses/by/4.0/"
    source:
      url: "https://www.openslr.org/141/"
      commit_or_version: "v1.0"
    attribution_required: true
    attribution_text: |
      LibriTTS-R: A Restored Multi-Speaker Text-to-Speech Corpus, Y. Koizumi et al., 2023.
      Distributed under CC BY 4.0.

  - id: aishell-3
    language: zh
    language_code: 2
    title: "AISHELL-3"
    speakers: 142
    utterances: 63223
    license:
      spdx: "Apache-2.0"
      verified: true
      url: "https://www.apache.org/licenses/LICENSE-2.0"
    source:
      url: "https://www.aishelltech.com/aishell_3"
      commit_or_version: "v1.0"
    attribution_required: true
    attribution_text: |
      AISHELL-3 multi-speaker Mandarin TTS corpus, Y. Shi et al., 2020.
      Licensed under Apache-2.0.

  - id: cml-tts
    languages: [es, fr, pt]
    title: "CML-TTS (Multilingual TTS Dataset)"
    splits:
      - {language: es, language_code: 3, speakers: 63, utterances: 168374}
      - {language: fr, language_code: 4, speakers: 28, utterances: 107464}
      - {language: pt, language_code: 5, speakers: 8, utterances: 34066}
    license:
      spdx: "CC-BY-4.0"
      verified: true
      url: "https://creativecommons.org/licenses/by/4.0/"
    source:
      url: "https://github.com/freds0/CML-TTS-Dataset"
      commit_or_version: "2023-10-01"
    attribution_required: true
    attribution_text: |
      CML-TTS Dataset, F. S. Oliveira et al., 2023. Distributed under CC BY 4.0.

# Finetuned model (Tsukuyomi-chan) の場合、 追加で記載
finetune_overrides:
  - finetune_id: tsukuyomi-6lang-v2
    base_datasets: [moe-speech-20speakers, libritts-r, aishell-3, cml-tts]
    additional_dataset:
      id: tsukuyomi-chan-corpus
      title: "つくよみちゃんコーパス Vol.1 〜 Vol.2"
      license:
        spdx: "CC-BY-4.0"  # 商用利用は別途条件あり
        verified: true
        url: "https://tyc.rei-yumesaki.net/material/corpus/"
      attribution_required: true
      attribution_text: |
        つくよみちゃんコーパス (CV: 夢前黎)
        © Rei Yumesaki / 夢前黎
        Distributed under CC BY 4.0 (商用利用は別途規約参照)
```

### 2.3 `MODEL_CARD.md` template

`scripts/generate_model_card.py` が `data-sources.yml` + git commit hash から生成:

```markdown
# Piper-Plus Multilingual Model Card

**Model**: piper-plus-multilingual-6lang
**Version**: v1.13.0
**Commit**: 121698b5
**Generated**: 2026-05-18T10:30:00Z

## Training Data

This model was trained on the following datasets:

| Language | Dataset | Speakers | Utterances | License |
|----------|---------|----------|------------|---------|
| ja | MOE-Speech (20 speakers) | 20 | 60,148 | CC BY-SA 4.0 |
| en | LibriTTS-R | 310 | 74,912 | CC BY 4.0 |
| zh | AISHELL-3 | 142 | 63,223 | Apache-2.0 |
| es | CML-TTS (es) | 63 | 168,374 | CC BY 4.0 |
| fr | CML-TTS (fr) | 28 | 107,464 | CC BY 4.0 |
| pt | CML-TTS (pt) | 8 | 34,066 | CC BY 4.0 |

**Total**: 571 speakers / 508,187 utterances across 6 languages.

## Attribution Requirements

If you redistribute this model or use it in a product, you MUST include the
following attributions (see `LICENSE_ATTRIBUTIONS.md` for full text):

- MOE-Speech 20 speakers corpus (CC BY-SA 4.0)
- LibriTTS-R (CC BY 4.0)
- AISHELL-3 (Apache-2.0)
- CML-TTS Dataset (CC BY 4.0)

## Model Architecture

- VITS-based multilingual TTS
- MB-iSTFT decoder (replaces HiFi-GAN, 2.21x faster on CPU)
- WavLM discriminator (training only)
- Prosody features (A1/A2/A3) from OpenJTalk

## Intended Use

- Research and non-commercial TTS applications
- Commercial use requires individual review of each dataset's license
  (see `LICENSE_ATTRIBUTIONS.md`)

## Limitations

- 6 languages only (ja/en/zh/es/fr/pt); Korean / Swedish not included in training data
- Single-speaker fine-tuning (e.g., Tsukuyomi-chan) requires additional dataset attribution
```

### 2.4 `LICENSE_ATTRIBUTIONS.md` template

template 全体 (fence なしで直接展開):

```text
# License Attributions

This file lists the attribution requirements for all training datasets used in
piper-plus models. Compliance with these attributions is required for
redistribution.

## MOE-Speech 20 speakers corpus

- License: CC BY-SA 4.0
- URL: https://huggingface.co/datasets/ayousanz/moe-speech-20speakers-ljspeech
- Attribution:
  > MOE-Speech 20 speakers corpus, distributed under CC BY-SA 4.0 by ayousanz.

## LibriTTS-R

- License: CC BY 4.0
- URL: https://www.openslr.org/141/
- Citation (BibTeX):
    @inproceedings{koizumi23_interspeech,
      author={Yuma Koizumi and Heiga Zen and Shigeki Karita et al.},
      title={LibriTTS-R: A Restored Multi-Speaker Text-to-Speech Corpus},
      year=2023, booktitle={Interspeech 2023}
    }

## AISHELL-3

- License: Apache-2.0
- URL: https://www.aishelltech.com/aishell_3
- Citation (BibTeX):
    @inproceedings{shi2021aishell,
      title={AISHELL-3: A multi-speaker mandarin TTS corpus},
      author={Yao Shi and Hui Bu and Xin Xu et al.},
      year={2021}
    }

## CML-TTS

- License: CC BY 4.0
- URL: https://github.com/freds0/CML-TTS-Dataset
- Citation (BibTeX):
    @article{oliveira2023cml,
      title={CML-TTS: A Multilingual Dataset for Speech Synthesis in Low-Resource Languages},
      author={Frederico S. Oliveira et al.}, year={2023}
    }
```

### 2.5 `release-shared-lib.yml` / `deploy-huggingface.yml` への hook

既存 workflow の publish step 直前に `generate_model_card.py` 実行を挿入:

```yaml
# .github/workflows/deploy-huggingface.yml (抜粋)
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Download ONNX artifact
        # ... existing ...

      - name: Generate MODEL_CARD.md and LICENSE_ATTRIBUTIONS.md
        run: |
          python scripts/generate_model_card.py \
            --data-sources data-sources.yml \
            --model-id piper-plus-multilingual-6lang \
            --commit-hash ${{ github.sha }} \
            --output-dir ./hf-upload/

      - name: Validate attribution completeness
        run: |
          python scripts/check_attribution_completeness.py \
            --model-card ./hf-upload/MODEL_CARD.md \
            --required-spdx CC-BY-4.0,Apache-2.0,CC-BY-SA-4.0
        # fail if any required attribution is missing

      - name: Upload to HF Hub with metadata
        uses: huggingface/hub-action@v1
        with:
          path: ./hf-upload/
          repo: ayousanz/piper-plus-base
          token: ${{ secrets.HF_TOKEN }}
```

### 2.6 forward-compat loader

`data-sources.yml` は `schema_version` を持ち、 未知フィールドを warning で受理:

```python
# scripts/generate_model_card.py (抜粋)
import yaml
from pathlib import Path

SUPPORTED_SCHEMA_VERSIONS = [1]

def load_data_sources(path: Path) -> dict:
    data = yaml.safe_load(path.read_text())
    if data["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS:
        if data["schema_version"] > max(SUPPORTED_SCHEMA_VERSIONS):
            print(f"WARNING: data-sources.yml schema_version {data['schema_version']} "
                  f"is newer than supported ({SUPPORTED_SCHEMA_VERSIONS}). "
                  f"Forward-compat: unknown fields will be ignored.", file=sys.stderr)
        else:
            raise ValueError(f"Unsupported schema_version: {data['schema_version']}")
    return data
```

### 2.7 license verification status の扱い

`license.verified: false` のエントリは MODEL_CARD に明示的 warning:

```markdown
## Training Data

> **Note**: license `verified: false` の dataset は upstream への問い合わせで未確定。
> 商用利用前に必ず upstream の最新条件を確認してください。

| Language | Dataset | License | Verified |
|----------|---------|---------|----------|
| ja | MOE-Speech | CC BY-SA 4.0 (推定) | NO - upstream confirmation pending |
```

quarterly review (`review_period_months: 3`) で `verified: true` 化を目指す。

---

## 3. エージェントチームの役割と人数

合計 **4 名** で実装:

| 役割 | 人数 | 主な担当 |
|------|------|----------|
| Legal / License researcher | 1 | 各 dataset の license 確認 / SPDX identifier 確定 / upstream 問い合わせ |
| Script author | 1 | `generate_model_card.py` / `check_attribution_completeness.py` / forward-compat loader |
| Release engineer | 1 | `release-shared-lib.yml` / `deploy-huggingface.yml` への hook 実装 |
| Docs writer | 1 | `MODEL_CARD.md` / `LICENSE_ATTRIBUTIONS.md` template / README 連携 |

**進行モデル**: Legal researcher が `data-sources.yml` の license 情報を確定 (1 週間)、
並行して script author が generator を実装。 release engineer が hook を組み込み、
docs writer が template を仕上げる。

---

## 4. 提供範囲とテスト項目

### Unit テスト

- `generate_model_card.py` の `data-sources.yml` parsing (schema_version 1 / 99 future)
- `MODEL_CARD.md` deterministic generation (同 input → 同 output、 改行・空白まで byte 一致)
- `check_attribution_completeness.py` で `CC-BY-4.0` 必須宣言時に欠落で fail
- forward-compat loader が unknown field を warning で許容
- `finetune_overrides` 経路 (Tsukuyomi-chan FT) で base + additional dataset 両方が
  attribution に含まれる

### E2E / 統合テスト

- `deploy-huggingface.yml` の dry-run で `MODEL_CARD.md` + `LICENSE_ATTRIBUTIONS.md` が
  artifact に含まれることを確認
- HF Hub staging repo に test upload し、 README として正しくレンダリングされるか
- 既存の HF Hub release (`ayousanz/piper-plus-base`) と比較し、 attribution の
  完全性が向上しているか

### 手動検証項目

- 各 dataset の license URL が live で 404 でないことを quarterly review
- 商用利用条件 (e.g., つくよみちゃんコーパスの個別条件) が MODEL_CARD で明示されているか
- 6 言語の attribution 順序が言語コード (ja=0, en=1, zh=2, es=3, fr=4, pt=5) に従っているか
- `license.verified: false` の dataset が次回 review で `verified: true` 化されるか
  追跡できる (Issue label `legal:license-review` で管理)

---

## 5. 懸念事項とレビュー観点

### 懸念事項

1. **license 情報の正確性**
   現状の `data-sources.yml` の license 値は **placeholder を含む** (特に MOE-Speech)。
   実装前に upstream への確認が必須。 確認結果次第で attribution_text を書き換える。

2. **upstream license の時間経過変更**
   CC BY 4.0 → CC BY-NC 4.0 への変更可能性 (低いが非ゼロ)。 quarterly review で
   `data-sources.yml` を update する運用が必要。

3. **HF Hub upload metadata の挙動差**
   HF Hub の README.md は YAML frontmatter (`---`) を model metadata として
   parse する。 既存 `deploy-huggingface.yml` の YAML frontmatter と整合性を取る必要。

4. **既存 `license-check.yml` との関係**
   既存 workflow は dependency license (cargo / pip / npm) のみで、 dataset license は
   対象外。 重複しないため併設で OK だが、 README で役割分担を明示する。

5. **Finetuned model の attribution chain**
   Tsukuyomi-chan FT 版は base model (6lang) の dataset attribution +
   つくよみちゃんコーパス attribution の **両方** が必要。 `finetune_overrides`
   schema が正しく chain しているか要確認。

### レビュー観点

- [ ] `data-sources.yml` の license SPDX identifier が正しい
- [ ] `verified: false` のエントリが MODEL_CARD で warning として表示される
- [ ] forward-compat loader が `schema_version: 99` で panic しない
- [ ] HF Hub README YAML frontmatter と generator output が衝突しない
- [ ] Finetuned model で base + additional dataset 両方が attribution chain される
- [ ] generator が deterministic (同 input → 同 output、 timestamp / random seed なし)
- [ ] PR sticky comment が `feedback_pr_body_over_comments` 準拠 (本文 update のみ)

---

## 6. 一から作り直すとしたら

### 案 A: license attribution を build 時 injection せず、 release artifact に常時同梱

ONNX export 時に `MODEL_CARD.md` を ONNX ファイルの metadata (custom op metadata key)
として埋め込み、 ranlib / objcopy のような post-processing で attribution を分離不可能化する。

| 比較軸 | build 時 injection (現案) | metadata embed |
|--------|--------------------------|----------------|
| 分離耐性 | downstream が README を消せば attribution chain 破壊 | metadata は ONNX 内に常駐 |
| toolchain 依存 | Python script のみ | ONNX SDK / protobuf 知識必要 |
| 実装複雑度 | 低 | 中 |
| 法的拘束力 | 同等 (どちらも attribution を提供したことは事実) | 同等 |

**結論**: 現案 (build 時 injection) が piper-plus の現状に適合。 metadata embed は
M-Stretch で検討。 ただし `LICENSE_ATTRIBUTIONS.md` を ONNX ファイルと **必ず同梱
(別ファイルでも OK)** とする運用ルールを README で明示する。

### 案 B: 完全手動 (CI 化せず、 release process checklist で対応)

`MODEL_CARD.md` を release engineer が手動で記述し、 PR review で確認する。

- pros: CI 工数ゼロ
- cons: M3 overview §3 で論じた通り、 release 頻度が上がると attribution 漏れ確率が
  線形上昇。 法務リスクの非対称性 (失敗時の damage が大きい) を考えると CI 化が ROI 高い

**結論**: 不採用。 ただし license 確定情報がない (verified: false) 状況では
generator が正しく warning を出す設計とし、 「CI で auto-generation + 人間が
最終チェック」 の hybrid 運用が現実解。

### 案 C: HF Hub の Model Card schema を canonical source にする

HF Hub の Model Card schema (`huggingface_hub.ModelCard`) を canonical source とし、
`data-sources.yml` を廃止して HF Hub schema 直書きにする。

- pros: HF Hub native でレンダリングが綺麗
- cons: HF Hub 以外 (PyPI / NuGet / npm) で同じ attribution を使い回しできない、
  schema が HF Hub のロックインに依存

**結論**: 不採用。 `data-sources.yml` を canonical source とし、 HF Hub / PyPI README /
GitHub Releases / docs/ それぞれの format に generator で展開する設計が柔軟。

---

## 7. 後続タスクへの連絡事項

### M3.1 / M3.3 への影響

- M3.1 の JSON schema 設計パターン (`schema_version` + forward-compat loader) を
  `data-sources.yml` で同様採用。 schema 設計の一貫性を保つ。
- M3.3 (typosquatting) の検出時 Issue に M3.2 で生成された attribution chain を
  記載することで、 typosquatting package が attribution を持たないことを示す材料に使える。

### M-Stretch への接続

- M-Stretch SLSA Build L3 の provenance に `data-sources.yml` の commit hash を
  含めることで、 「どの dataset 状態で build したか」 を SLSA attestation で証明可能。
- M-Stretch OpenSSF Scorecard 9.3+ の `Maintained` / `License` カテゴリで加点。

### 関連 phase / 既存仕組みとの接続

- `CHANGELOG.md` の `[Unreleased] > Added` 節に新 dataset 追加時のエントリを書く
  運用を `data-sources.yml` 更新と連動させる (M1.2 migration lint との関係整理)
- `CONTRIBUTING_MODELS.md` (既存) に `data-sources.yml` 更新ガイドを追記
- quarterly review schedule を `.github/workflows/license-quarterly-review.yml` 等で
  schedule trigger (cron: `0 0 1 */3 *`) し、 Issue auto-create する仕組みは
  M-Stretch で検討

---

## 8. 関連ファイル

### 新規作成

- `data-sources.yml` — canonical source (repository root)
- `scripts/generate_model_card.py` — `MODEL_CARD.md` + `LICENSE_ATTRIBUTIONS.md` generator
- `scripts/check_attribution_completeness.py` — attribution 漏れ検出
- `docs/spec/data-sources-contract.toml` — `data-sources.yml` schema 仕様
- `tests/test_generate_model_card.py` — generator unit test
- `tests/fixtures/data-sources-sample.yml` — test fixture

### 既存ファイルへの影響

- `.github/workflows/deploy-huggingface.yml` — generator hook 追加
- `.github/workflows/release-shared-lib.yml` — generator hook 追加 (iOS / Android shared lib にも attribution 同梱)
- `CLAUDE.md` — データセット表が `data-sources.yml` の参照と連動することを明記
- `CONTRIBUTING_MODELS.md` — 新規 dataset 追加時の `data-sources.yml` 更新フロー記載
- `README.md` — license badge / model card への link 追加検討

---

## 9. 参照

- 親調査: [ci-expansion-2026-05.md §5 Top 10 #7](../proposals/ci-expansion-2026-05.md)
- マイルストーン詳細: [ci-expansion-milestones.md §M3.2](../proposals/ci-expansion-milestones.md)
- M3 overview: [M3-overview.md](./M3-overview.md)
- 既存 license check: `.github/workflows/license-check.yml`
- 既存 HF deploy: `.github/workflows/deploy-huggingface.yml`
- HF Hub Model Card spec: <https://huggingface.co/docs/hub/model-cards>
- SPDX license identifiers: <https://spdx.org/licenses/>
- CC BY 4.0: <https://creativecommons.org/licenses/by/4.0/>
- CC BY-SA 4.0: <https://creativecommons.org/licenses/by-sa/4.0/>
- LibriTTS-R: <https://www.openslr.org/141/>
- AISHELL-3: <https://www.aishelltech.com/aishell_3>
- CML-TTS: <https://github.com/freds0/CML-TTS-Dataset>
- つくよみちゃんコーパス: <https://tyc.rei-yumesaki.net/material/corpus/>
