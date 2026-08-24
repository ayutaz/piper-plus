# Piper TTS - プロジェクト概要

VITS ベースの高品質ニューラル TTS。**6言語マルチリンガルモデル**を学習済み、**8言語の G2P コード**を実装済み。ランタイムと配布物の対応は下記のパッケージ表および各仕様書を参照してください。

**基準ブランチ**: `dev`。root `VERSION` は `2.0.2`。v1.12 / v2.0 の破壊的変更は [docs/migration/v1.12-to-v2.0.md](docs/migration/v1.12-to-v2.0.md) と [docs/migration/v1.11-to-v1.12.md](docs/migration/v1.11-to-v1.12.md) を参照してください。

---

## Research / archive and publication pointers

現在の研究ブランチは `feat/zero-shot-v8-dataset-scaling` です。研究用の v7 zero-shot 学習結果と手順は、次の文書を正本とします。

- [v7 学習結果・根本原因](docs/design/multi-6lang-zero-shot-v7-training-results.md) — epoch 32、6言語、571話者、研究上の修正と評価。
- [zero-shot handoff](docs/handoff/zero-shot-tts-handoff-2026-06-20.md) — private/gated 研究保存先、旧 `/data/piper` パス、再現・再開手順。
- [品質改善計画](docs/design/zero-shot-quality-improvement-plan.md) — historical findings と未完了の改善計画。
- [公開モデルカタログ](docs/guides/development/pretrained-models.md) — legacy root、public `releases/zs-v1`、private/gated research stores の区別。
- [public zs-v1 release record](docs/design/zero-shot-base-zs-v1-release-2026-10-10.md) — pinned public base の配布・検証記録。
- [Tsukuyomi publication record](docs/design/tsukuyomi-publication-ready-2026-10-12.md) — public `releases/zs-v1` の公開記録と品質上の制約。

> 旧 root `model.ckpt` / `config.json`、`piper-v11-local`、`output/`、private/gated research stores は歴史的・研究用資産として保持します。public `zs-v1` と legacy root の設定・用途を混同しないでください。

---

## 📦 v8 → v8.1 → v9 zero-shot 学習 (`feat/zero-shot-v8-dataset-scaling`)

> **最新状態 (2026-08-25): v11 (carrier head 構造保証) は R3 安全装置により ep29/80 で正規停止 — 調波構造の技術検証成功 (comb-HNR 14.6dB = GT 超え、v10b 4.6)、実用は学習量不足で不成立。次は v11b (ramp 修正 + CER gate + export 修理)。**
>
> - **v11 最終結論 (2026-08-25)**: [zero-shot-v11-roadmap.md §5](docs/design/zero-shot-v11-roadmap.md) が canonical。要点: ①carrier head で がびがび残存成分 (A3) の構造保証を実証、②ep19→25 で敵対 ramp による dual-encoder 乖離崩壊 (encoder 騙し 6 例目) → R3 が正規停止、③ONNX export の 2 バグは**修理完了 (2026-08-25)**: `--no-ema` フラグ (a12609b1) + main() の infer 手書き複製を build_infer_forward に一本化 (ca76d6ea、AdaLN g_spk 断線の根治、FP16 export で 14.4dB 回復実測)、④評価系の明瞭度盲点は**解消済み** — `piper_train.tools.eval_cer` 実装 (ca12027e) + gate 事前登録 (契約 §7、median ≤ 0.30 / ep40+ 昇格判定。較正: 明瞭 v10b ep79 = 0.095 vs 不明瞭 v11 ep9 = 1.43)。成果物: HF `checkpoints-v11/` + `v11-results/`、ログ/TB はローカル `piper-v11-local/box-evac/`
> - **dev リベース (2026-08-25)**: `origin/dev` を取り込み。#616 (Multi-scale FiLM 導入前 ckpt の自動移行) + #619 (py3.13 pathlib ckpt 読み込み) が入り、ckpt state_dict 正規化は `normalize_checkpoint_state_dict` に一本化 (073062b1 で `--resume-weights-only` 経路も追従)。v7 時代に本ブランチ独自だった FiLM 復活パッチは upstream 化された。**リベースにより本 doc 内の pre-rebase コミットハッシュは非到達** (ローカル `backup/pre-rebase-dev-20260825` に退避済み)
> - v9 (がびがび根治版) 完走・聴感確認済み (2026-08-12) — ただし v10b ep79 でも A3 (調波間ノイズ) は聴感残存 (2026-08-25 ユーザー確認)、根治は v11 系の完走待ち
> 系譜: v8 (7-lang スケール、SECS 0.649 / がびがび有り) → v8.1 (微分可能 SCL InfoNCE + WavLM で SECS 0.712 / UTMOS 改善、がびがび残存) → **v9 (PQMF canonical 修正 + MRD + full-band STFT + データゲートで from scratch 50ep、4-9kHz 非構造ノイズ -5〜-10dB + 倍音構造獲得、がびがび解消)**。
>
> - **がびがびの根本原因** (PQMF 変調位相項欠落 → 学習ターゲット汚染 + データ高域ノイズ床): [`docs/design/zero-shot-noise-root-cause-pqmf.md`](docs/design/zero-shot-noise-root-cause-pqmf.md) が canonical (プロセス考古学 §4: 受け入れ基準 -90dB→5dB の goalpost moving が 15 ヶ月バグを制度化 → pre-commit gate `test-threshold-relaxation` で再発防止)
> - **v9 データ**: 案 Z ゲート (Zeroth 全除外 + hi_ratio/fmax999) で 6 言語 300,443 utts / ~3.7k spk。**ko は除外** (Zeroth が fmax 中央値 3.0kHz の強ローパス + language-balanced sampling は最小言語が epoch サイズを決めるため 356 utts では学習不能) — v10/v11 でも未投入のまま、復活は Emilia 投入判断と併せ v11b 以降で判断
> - **残課題**: zs_ja SECS 0.652 (v8.1 0.712 から -0.06) / 韻律 (強弱) の平板さ (v8 系から持ち越し、noise_scale 引き上げ検証中 + v10 で本格対応)
> - **OOD 参照 zero-shot の実力 (2026-08-12 実測)**: つくよみ参照で cross-utt SECS 0.73 (ceiling 0.888 / ja 女性 floor ~0.7 すれすれ) = 聴感「似ない」。EMA/FP16/ONNX export は 4-way A/B で無罪確定。**SECS は cross-utterance でしか測らない** (same-utt は SCL Goodhart で膨張、0.775 と誤報した事例あり)。特定話者を確実に似せる用途は FT が正道。canonical: [docs/design/zero-shot-speaker-similarity-root-cause.md](docs/design/zero-shot-speaker-similarity-root-cause.md)
> - **Phase 0/1 診断完了 (2026-08-14)**: v9 ep49 からの warm restart 計 7 介入 (LR/c_spk/c_mrd/σ の係数 4 arm + SCL cross-utt 正例化 B-1 + posterior z detach B-3 + dose 増 24ep) が**全て事前登録閾値未達 → warm restart では転写能力を回収できないことを確定**。Arm B (c_spk 2.0) の CAM++↑/ECAPA→ が「SCL same-utt 正例 = Goodhart」の直接証拠。B-1/B-3 は実装済み (`--spk-loss-positives cross_utt` / `--scl-detach-z`、default off) で機構として動作確認済み (gap 縮小 + OOD つくよみ両 encoder 同調 +0.03) — **v10 from-scratch レシピに組込済み (v10a は cross-utt SupCon で完走)**。実行計画・全数値: [docs/design/zero-shot-v10-roadmap.md](docs/design/zero-shot-v10-roadmap.md)、生データ: HF `diag-phase0/` + `diag-phase1/`
> - **v10a 完走 (2026-08-16)**: v9 同一データ + 配線修正 (M1-M3) + cross-utt SupCon で 80ep。**OOD (つくよみ) 0.753/0.634 = v9 比 +0.03 両 encoder 同調 + 帯域 -2.9dB 改善、in-domain は v9 同等 (0.60 plateau、0.70 未達)**。swap-SCL (cosine 版) は ep28-33 で prior 経路を崩壊させ切除 — **固定 encoder のスコアを学習目標にすると、モデルは実際に似せるのではなく encoder を騙す方向に逸れる (グッドハートの法則)。今回で 3 例目** (識別器形式 R2 で v10b 再挑戦)。推奨 ckpt: HF `checkpoints-v10a-r2/epoch=69` (dual-encoder 最良)。全記録: [design doc §9-11](docs/design/zero-shot-v10-design.md)
> - **v10 実装ランディング (2026-08-14、TDD)**: 設計 doc [docs/design/zero-shot-v10-design.md](docs/design/zero-shot-v10-design.md) の 2a を実装。学習系 (全て opt-in、default は v9 挙動維持): `--speaker-cond-layer` (M2 enc_p 層内注入) / `--dp-spk-head` (M3 DP 話者勾配 + spk_proj_dp) / `--use-snac-flow` (M1+E2 SNAC flow、logdet→KL 配線 + 可逆性テスト付) / `--film-init-std` (E1) / `--c-swap-spk` 系 (S1 swap-SCL、同一言語・異話者 derangement) / `--spk-loss-gather` (勾配が通る DDP all_gather) / `--spk-loss-temperature` / `--latent-filling-tau` (LF)。**breaking: `--spk-emb-noise-sigma` default 0.05→0.0** (F7 破壊的 noise の default 除去、v9 スクリプトは明示指定のため再現性維持)。評価系: `eval_zs_secs` に goodhart_flag 自動判定 (`--baseline-json`) + `--require-encoder2`、契約は [docs/spec/zs-eval-contract.md](docs/spec/zs-eval-contract.md)。DINO は c_dino>0 で退化警告 (v10 は 0 推奨)
> - 成果物 (HF `ayousanz/piper-plus-zero-shot-multi-7lang-v8`): `checkpoints-v9/` + `onnx/v9-zs-ep49.onnx` + `v9-data/` (ゲート済み jsonl + 帯域 metrics) + 各評価 JSON。聴感サンプル: ローカル `piper-v8-dataset-backup/v9_listen_samples/`

### (履歴) v8 準備時点の記録 (2026-08-02)

> ✅ 本節は当時の計画のスナップショット。v8 本走以降 v11 まで実走済みで、節内の「本走待ち」「残 TODO」等は全て過去形。commit ハッシュは 2026-08-25 の dev リベースにより非到達 (`backup/pre-rebase-dev-20260825` に退避)。

> KsponSpeech (AI-Hub research-only) は除外確定し、 v8 は public + 商用利用可の open-model として公開する方針 (過去の piper-plus 事前学習モデル同様)。 7-lang 規模: ~3,790 speakers / ~346k utts。 詳細は下記「2026-08-02 更新」。

**進捗 (2026-07-09 セッション終了時点)**:
- ✅ **v8 dataset 完成 (6-lang スナップショット)**: 321,391 utts / 3,578 speakers / 6 lang (`/data/piper/dataset-multilingual-6lang-v8/`)
- ✅ **韓国語 (ko) 拡張 ランディング**: parser 3 種 (Zeroth / KsponSpeech / CV ko) + `export_common_voice_ko.py` + `LANGUAGE_ID_MAP` を 8-lang extended (ko=7) に切替 (commit `963c4c49`)。 G2P/contract/id_maps は既に 7 ランタイム全てで 8-lang extended 版で pin 済のため、 コード側は data pipeline のみで完遂。 7-lang 目標: ~420k utts / ~5,100 speakers (→ 2026-08-02 KsponSpeech 除外確定で **~346k utts / ~3,790 speakers** に縮小)
- ✅ **scratch NaN blocker 解消**: bf16 cuFFT bug fix (`3dcabd57`) + KL 発散防止 3 段 (`1a86aa55` + `563f8361` + `1f625a42`)
- ✅ **前処理高速化 4 施策 (§3.11)**: impl1 hf_transfer (`5b2f53c4`、 raw DL 3-5x) + impl2 KsponSpeech `.pcm` 直読 (`c2f59ec0`、 ETRI WAV 変換 3-4h 消去 — KsponSpeech 除外確定後は出番なし) + impl3 parquet FLAC 直保存 (`e0fa0d04`、 LibriTTS-R/CML export 2-6x) + impl4 moe-speech-plus `--parallel` default ON (`b8539de4`、 選抜 12-16x)。 GPU 検証不要な低リスク版のみ、 GPU resample (#3) は SNR 検証必要のため v9 送り。 **前処理 wall-clock 12-18h → 7-10h (7-lang) / 6-9h (6-lang)**
- ✅ **28 commits ランディング**: 5 施策 + KL fix + bucketing 実験 + T3/T6/T-npy 他 8 施策 + ko 拡張 + 前処理 4 施策 + docs
- ✅ **実測 -23% throughput**: 14.0 → 10.74 sec/step (bf16 real config、 batch=64)
- ⏸ **本走待ち**: 4x A100 SXM4 DDP + batch=128 で 6-lang 9-11 日 / ~$672-1,120、 7-lang 12-15 日 / ~$1,050-1,530 見込 (§3.10) (→ 2026-08-02 KsponSpeech 除外 + 40GB 案で **7-9 日 / ~$600-750** に更新、 下記)

**次セッションでの起動**:
- 全手順: [`docs/handoff/zero-shot-v8-2026-07-09.md`](docs/handoff/zero-shot-v8-2026-07-09.md)
- CLI 最終版: [design doc §3.7](docs/design/zero-shot-v8-dataset-scaling-plan.md#37-全-smoke-test-完了--最終見積-2026-07-09-セッション終了時点)
- ko 追加コスト分析: [design doc §3.10](docs/design/zero-shot-v8-dataset-scaling-plan.md#310-v8-に韓国語-ko-追加--追加コスト見積-2026-07-09)
- ko 追加後の前処理: `prepare_multilingual_dataset.py --ko-zeroth ... --ko-cv ...` (§6.5。 `--ko-ksponspeech` は除外確定により使わない。 CV ko の UTMOS フィルタは `piper_train.tools.score_utmos` の per-clip tsv を `export_common_voice_ko --utmos-tsv` に渡す — 渡さないと黙って無効化される)

**2026-08-02 更新 (dev v2.0 リベース + 本走方針確定)**:
- ✅ **公開方針確定**: v8 は public + 商用利用可の open-model として公開 (KsponSpeech 除外により全データソースのライセンスが両立)。 ko は Zeroth-Korean (CC BY 4.0、 openslr.org/40、 ~181 spk / ~22.2k utts) + Common Voice ko (CC0、 UTMOS≥2.5 + ≥20clips + cap60 で ~30-50 spk / ~3k utts) のみ
- ✅ **UTMOS スコアラ追加**: `piper_train.tools.score_utmos` (SpeechMOS utmos22_strong、 commit `1eb2a3d0`)
- ✅ **インスタンス承認済**: 4x A100 SXM4 40GB $3.43/hr (storage 1.7TB 込、 vast.ai。 オファーは流動的でレンタル時に再検索)。 batch=32/GPU の VRAM 40GB は未検証 → smoke を VRAM gate とし、 溢れたら batch=24 に下げるか 80GB ($7.68/hr) に乗換
- ✅ **smoke 自動 go 基準承認済**: sec/step ≤ 8.5 かつ non-finite skip ≤ 3% かつ VRAM 40GB 内 → 報告を待たず本走 launch
- ✅ **開始ブロッカー解消**: HF token (gated moe-speech-plus read / private repo write) + WANDB キー検証済。 ckpt 退避 repo `ayousanz/piper-plus-zero-shot-multi-6lang-v8` (private) 作成済
- ⏳ **本走見積 (7-lang、 40GB 案)**: **7-9 日 / ~$600-750** (7-8 sec/step 達成前提、 10.74 のままなら +30%)
- 🔜 **残 TODO (本走前)**: onstart 自動レジューム script + HF ckpt epoch ごと自動 upload script が未作成 / ko データパイプラインは実データ未検証 (synthetic unit test のみ) → instance で小規模先行検証 / 評価用話者 holdout はコード機構なし → dataset.jsonl 構築後に post-filter (ja: moe-speech-plus 学習除外 ~10 名・男性含む、 ko: Zeroth 学習除外 5-10 名)

**実測で不採用が確定した施策**:
- `--compile`: torch 2.11 + triton の kernel compile crash
- `--precomputed-mel`: 学習は GPU-bound で -6.5% 遅い
- `--enable-length-bucketing`: +34% 逆効果

---

## 現在の状態

### 学習済みモデル (6言語マルチリンガル)

> 本表は開発・研究用の状態を示します。user / 外部参照向けの HF 配布カタログ (ダウンロードリンク + zero-shot variants 含む) は [`docs/guides/development/pretrained-models.md`](docs/guides/development/pretrained-models.md) を参照してください。

| モデル | 学習基盤 | 状態 | パス |
|-------|--------|------|------|
| **6lang base (HiFi-GAN)** | 75 epoch (v1.11 系) | 完了 (2026-03-16) | `/data/piper/output-multilingual-6lang/` |
| **6lang base MB-iSTFT** | 75 epoch スクラッチ | 完了 (2026-04-16) | `/data/piper/output-multilingual-6lang-mb-istft/multilingual-6lang-mb-istft-scratch-75epoch.onnx` |
| **Zero-Shot base zs-v1** | v7 ep32 / step216326、6言語・173音素・571話者・CAM++ 192次元 | revision `3620ed788667cb76f08bd6cf2db8152c1f4c8bd1` で一般公開。公開 PyPI 2.0.0 consumer の推論・短いFTを機能確認済み。後続 source 6-runtime public-base CI (run `38189966578`) も成功 | [HF releases/zs-v1](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)。品質改善・人手試聴合格とは別 |
| **つくよみちゃん 6lang-v2** | 6lang ベースから FT 500 epoch | 完了 (2026-03-16) | `/data/piper/output-tsukuyomi-finetune-6lang-v2/tsukuyomi-6lang-v2-fixed.onnx` |
| **つくよみちゃん MB-iSTFT** | 6lang MB-iSTFT ベースから FT 500 epoch | 完了 (2026-05-02) | `/data/piper/output-tsukuyomi-mb-istft-finetune/tsukuyomi-mb-istft-500epoch.onnx` |
| **つくよみちゃん Zero-Shot FT** | v7 ep32 zero-shot ベースから FT 500 epoch | public `releases/zs-v1` を機能確認済み。実験公開であり全言語・品質承認ではない (2026-10-15) | `/data/piper/eval-tsukuyomi-zs-ft/tsukuyomi-ft-epoch499-zs.onnx` (研究時 SECS 0.7749)。公開先は [publication record](docs/design/tsukuyomi-publication-ready-2026-10-12.md) |
| **CSS10 JA 6lang** | 6lang ベースから 50 epoch | 完了 (2026-03-16) | `test/models/multilingual-test-medium.onnx` |

### データセット

| データセット | 発話数 | 話者数 | シンボル | パス |
|-------------|-------|-------|---------|------|
| `dataset-multilingual-6lang-filtered` (legacy root) | **508,187** | 571 | 173 | `/data/piper/dataset-multilingual-6lang-filtered/` |
| `dataset-multilingual-6lang-filtered-new` (v7 research) | **497,519** | 571 | 173 | `/data/piper/dataset-multilingual-6lang-filtered-new/` |
| `dataset-tsukuyomi-finetune-6lang` | 100 | 1 | 173 | `/data/piper/dataset-tsukuyomi-finetune-6lang/` |

**6lang 内訳:** ja 60,148 (20話者, MOE-Speech) / en 74,912 (310, LibriTTS-R) / zh 63,223 (142, AISHELL-3) / es 168,374 (63, CML-TTS) / fr 107,464 (28, CML-TTS) / pt 34,066 (8, CML-TTS)。言語コード: ja=0, en=1, zh=2, es=3, fr=4, pt=5。

**前処理:** `src/python/piper_train/tools/prepare_multilingual_dataset.py`

---

## 開発環境セットアップ

clone 直後 1 回だけ実行 (commit 時の lint drift / format drift を CI 待ち前に検出):

```bash
pip install pre-commit  # または: uvx pre-commit
pre-commit install      # .git/hooks/pre-commit を生成
```

これで `git commit` 時に ruff (check + format) と PUA consistency が自動実行され、
drift があれば commit がブロックされます (auto-fix も適用)。手動全件確認は
`pre-commit run --all-files`。

**Pre-push 段階 (opt-in、推奨):**

```bash
pre-commit install --hook-type pre-push   # .git/hooks/pre-push を追加生成
```

`git push` 直前に 4 つの contract gate (loanword / PUA / language parity /
CHANGELOG unreleased) を full-repo で実行 (~20-30 秒)。`SKIP=...` で commit
時に gate を bypass した場合でも push 前に drift を検出できる。bypass は
`git push --no-verify`。

> **Why:** PR #401 で ruff format 漏れが 2 度起きた (commits 5d9c60e6 / 8dc19e3b)。
> CI 検出 (~12 秒) → 修正 → commit → push の cycle of shame を断つため、
> ローカル commit 時点で format drift を fail-fast。CI 側にも
> `.github/workflows/pre-commit.yml` で同じ hook を gate 化済み (install 忘れ
> しても PR 時に検出)。

> **テスト閾値を緩める時のルール (2026-08 PQMF 事故より):** テストの数値基準
> (SNR / 許容誤差等) を実測に合わせて緩める前に、**参照実装または第一原理との
> 比較を必須**とする。緩和には assert 行 (または直上) に
> `# threshold-relaxed: <根拠>` を書くこと — pre-commit gate
> `test-threshold-relaxation` (`scripts/check_test_threshold_relaxation.py`)
> が根拠なしの緩和 diff を block する。「理論限界」「NN が補償する」という
> 合理化で受け入れ基準 -90dB → 5dB に緩め、バグを 15 ヶ月制度化した事例:
> [docs/design/zero-shot-noise-root-cause-pqmf.md §4](docs/design/zero-shot-noise-root-cause-pqmf.md)。

> **ruff version pin:** `.pre-commit-config.yaml` の `rev: vX` と
> `.github/workflows/python-lint.yml` の `pip install ruff==X`、加えて
> `pyproject.toml` の 3 dependency group エントリ (合計 5 箇所) は同期必須。
> drift = local-clean / CI-fail mismatch (PR #401 の根本原因の一つ)。
> `scripts/check_ruff_version_sync.py` + `ruff-version-sync.yml` で
> 5 箇所一致を CI gate (本 gate がなければ Dependabot uv-workspace PR が
> pyproject.toml だけ bump → drift → 後追い PR が発生する)。
> `ci.yml` は PR #462 で ruff job を削除済み (python-lint.yml と重複) のため
> pin サイトではない。 site 一覧に載る場所が pin を失った場合は gate が
> 落ちる (`EXPECTED_PIN_COUNT`) — 以前は無言で skip され、 pin が消えた
> ときに限って gate が緑になっていた。

### ローカルテスト実行 (特に macOS)

各ランタイムを CI と同条件でローカル実行する際の注意点 (macOS で検証済み):

- **Python**: `uv sync --extra dev` で pytest-cov 等を入れてから `uv run --no-sync pytest <dir> --no-cov`。bare `uv sync` は plugin を入れず pytest.ini の `addopts=--cov` で usage error (exit 4) になる。
- **Rust**: per-crate (`cargo test -p piper-plus` 等) で実行。`cargo test --workspace` は piper-plus-python (pyo3 auto-initialize) を含み、macOS の framework Python (`/usr/bin/python3`) では `@rpath` 解決失敗で SIGABRT。全 crate を回すなら `cargo test --workspace --exclude piper-plus-python --exclude piper-plus-wasm` (python は maturin / wasm は wasm-pack で別途テスト)。
- **Go**: `src/go` と `src/go/phonemize` は別 go.mod。両方で `go test ./...` する。
- **npm (openjtalk-web)**: `npm install "@piper-plus/g2p@file:../g2p"` でローカル g2p をリンク (registry 版は古いと isSsml 等の root export を欠く)。生成された file: リンクの lockfile は commit しない (lockfile-size gate)。
- **C++**: `cmake -B build -DBUILD_TESTS=ON && cmake --build build -j && ctest --test-dir build` (ORT/OpenJTalk は cmake が自動 DL、sudo 不要)。
- **Swift**: release 用 `Package.swift` は未リリース xcframework を参照するため `swift test` が 404。CI と同じ manifest swap か tag リリース後に実行する。

---

## 学習テンプレート

> 6lang ベース学習は完了済み。新規 FT を行う際は Template B を使う。

### Template A: 事前学習 (Multi-speaker pretraining)

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
    --dataset-dir <DATASET_DIR> \
    --prosody-dim 16 \
    --accelerator gpu --devices 4 --precision bf16-mixed \
    --max_epochs <EPOCHS> --batch-size 20 --samples-per-speaker 2 \
    --checkpoint-epochs 5 --quality medium \
    --base_lr 2e-4 --disable_auto_lr_scaling \
    --ema-decay 0.9995 --max-phoneme-ids 400 \
    --audio-log-epochs 5 \
    --default_root_dir <OUTPUT_DIR> > training.log 2>&1 &
```

### Template B: シングルスピーカー ファインチューニング

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
    --dataset-dir <FINETUNE_DATASET> \
    --prosody-dim 16 \
    --accelerator gpu --devices 1 --precision bf16-mixed \
    --max_epochs 500 --batch-size 4 --samples-per-speaker 4 \
    --checkpoint-epochs 50 --quality medium \
    --base_lr 2e-5 --disable_auto_lr_scaling \
    --ema-decay 0.9995 --max-phoneme-ids 400 \
    --val-every-n-epochs 50 --audio-log-epochs 50 \
    --resume-from-multispeaker-checkpoint <BASE_CHECKPOINT> \
    --default_root_dir <OUTPUT_DIR> > training.log 2>&1 &
```

### A vs B 主要差分

B (FT) は A から `--devices 1`、`--base_lr 2e-5` (1/10 で catastrophic forgetting 防止)、`--batch-size 4`、`--max_epochs 500`、`--freeze-dp` 自動有効、`--audio-log-epochs 50` (Validation 頻度に合わせ) を変更。HiFi-GAN ckpt からの resume/FT は v1.12.0 で明示エラー (MB-iSTFT base から再 FT)。

### Precision の選び方 (Issue #527 / DR-008 適用後)

- **`--precision bf16-mixed`** (default、 Template A/B canonical) — Ada 6000 / RTX 5090 で BF16 native Tensor Core を活用、 numerical stable (FP16 より loss spike しにくい、 loss scaling 不要)。 TF32 enable (DR-007) と直交、 両方の恩恵を受ける
- `--precision 16-mixed` (旧 default、 legacy) — T4 等 sm_75 以下で BF16 native 非対応の場合、 ただし VITS 推論用途中心
- `--precision 32-true` (legacy V100 互換) — 数値再現性最優先 (`torch.use_deterministic_algorithms(True)` 併用時)、 通常学習では非推奨

> **過去 ckpt resume 非サポート (Issue #527 / DR-006):** v2.0 では torch 2.11 + cu128 環境で旧 ckpt (torch 2.2 製) の resume を保証しない。 継続学習が必要なユーザは v1.12 Docker image tag を継続利用 (registry 長期保持)。 新規学習は from scratch、 もしくは torch 2.11 で生成した base からの FT のみ対応。

---

## 実装済み機能

### Decoder & 生成

- **MB-iSTFT-VITS2 Decoder** (`vits/mb_istft.py`, `vits/stft_onnx.py`) — HiFi-GAN を完全置換、CPU Decoder 単体で **2.21x 高速化** (HiFi-GAN 168.2ms → MB-iSTFT 76.2ms / 100 phoneme p50、PR #320 内部 A/B microbench)。End-to-end の Latency P50 は README.md の Benchmark 表 (Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs で **27ms**) を canonical 値とする (測定環境・テスト長が異なるため別値)。`upsample_rates=(4,4)` + iSTFT(4x) + PQMF(4x) = 256x。出力形状 `[B, 1, T]` 維持で C#/Rust/Go/WASM/C++ ランタイム変更不要。CLI: `--c-sub-stft` (sub-band STFT loss 係数; hparams `sub_stft_{fft,hop,win}_sizes` は config-only)。Issue #268, PR #320。
- **WavLM Discriminator** (`vits/models.py:WavLMDiscriminator`) — 学習時のみ知覚品質判別。GPU +1-2GB。CLI: `--no-wavlm`, `--wavlm-every-n-steps`, `--c-wavlm`。**T4 (VRAM 16GB)** では `--no-wavlm` 推奨 (VRAM 制約)。 **Ada 6000 (48GB) / RTX 5090 (32GB)** では WavLM 利用可、 Template default も WavLM 有効。
- **prosody_features (A1/A2/A3)** (`vits/models.py`) — OpenJTalk 由来の韻律情報を DP 入力に活用。CLI: `--prosody-dim 16` (デフォルト)。
- **EMA + stochastic** — ONNX エクスポート時に EMA 自動適用 (チェックポイントに state あれば)。`--no-stochastic` で deterministic。

### 学習補助

- **Duration Predictor 凍結** (`vits/lightning.py:configure_optimizers`) — CLI `--freeze-dp` で DP 凍結。`--resume-from-multispeaker-checkpoint` 使用時は自動有効。テスト: `src/python/tests/test_freeze_dp.py`。
- **転移学習** (`__main__.py:load_multispeaker_checkpoint`) — CLI `--resume-from-multispeaker-checkpoint` で emb_g 除去 + emb_lang 補正 + freeze-dp を一括実行。HiFi-GAN ckpt は明示エラー。
- **言語グループ均等サンプリング** (`vits/dataset.py:SpeakerBalancedBatchSampler`) — 話者比 ≥ 3:1 で自動有効化。CLI: `--language-balanced-sampling`。
- **学習高速化** — Validation 頻度削減、DataLoader 最適化 (num_workers=2, pin_memory)、DDP `find_unused_parameters=True`。CLI: `--val-every-n-epochs`, `--limit-val-batches`, `--num-workers`, `--no-pin-memory`。
- **WandB Audio Logging** (`vits/lightning.py:on_validation_epoch_end`) — Validation 時に音声サンプルアップロード。CLI: `--audio-log-epochs`, `--num-test-examples`。
- **エネルギー VAD 高速キャッシュ** (`norm_audio/__init__.py`) — Silero ONNX VAD を numpy エネルギー VAD に置換、~25x 高速化 (~390ms → ~8ms/file)。
- **Super-MAS Triton-GPU MAS accelerator** (`vits/monotonic_align/__init__.py`) — arXiv:2409.07704 (Park et al., 2024)。 CUDA tensor + `super_monotonic_align` package 利用可能時に Triton kernel に dispatch、 19-72x 高速化 (報告値)。 既存 Cython は CPU / package 未導入 / `PIPER_PLUS_DISABLE_SUPER_MAS=1` 時のフォールバックとして温存。 推論経路への影響ゼロ (学習時 `SynthesizerTrn.forward` 内 1 箇所のみ呼び出し)。 Opt-in install: `pip install "piper-train[super-mas]"` (PyPI 非配布、 git+https のみ)。 algorithmic equivalence (upstream は bit-identical を明示保証しないが `max_neg_val` edge case 修正済)。 **実行時 parity 自己検証**: 環境依存の silent 破損 (2026-08 v8 事故、 py3.12 + 当該 triton で壊れたアラインメントを無エラー返却 → KL 発散 + DP 崩壊で 80ep 全損) を遮断するため、 最初の 3 dispatch を Cython 参照と IoU 比較 (< 0.90 で永続 Cython fallback)。 加えて raw KL の cap 1e4 連続 300 step 貼り付きで学習を abort (`PIPER_PLUS_KL_CAP_ABORT_STEPS`、 design doc §3.13)。

### ONNX エクスポート

- **FP16 デフォルト** (`export_onnx.py`) — モデルサイズ ~50% 削減。CLI: `--no-fp16` で無効化。
- **emb_lang 自動統一** (`export_onnx.py:should_unify_emb_lang`) — シングルスピーカー多言語モデルで自動有効化、声質統一。CLI: `--unify-emb-lang` / `--no-unify-emb-lang` (auto), `--unify-emb-lang-source N`。テスト: `src/python/tests/test_export_onnx.py`。
- **Speaker Embedding 入力パス** (`vits/models.py:infer`, `export_onnx.py`) — `speaker_embedding` テンソルで声質指定、speaker_id と排他。CLI: `--speaker-embedding`, `--reference-audio`, `--speaker-encoder-model`。テスト: `src/python/tests/test_speaker_embedding.py`。

### Voice Cloning

- **Speaker Encoder (ECAPA-TDNN)** (`src/python/piper_train/speaker_encoder/`) — 256 次元 L2 正規化 embedding。テスト: `test/test_speaker_encoder.py` (legacy 位置、その他は `src/python/tests/` 配下)。
- **ランタイム別 voice cloning** — Rust/Go/C#/WASM は `--reference-audio` と `--speaker-encoder-model` から embedding を生成でき、各 runtime は `speaker_embedding` 入力にも対応。C++ は pre-computed `--speaker-embedding` の入力のみ実装し、`--reference-audio` / ECAPA-TDNN 推論と C API の speaker encoder は未実装 (stub)。CLI フラグと対応範囲は runtime ごとの help を確認する。

### G2P (8言語)

`MultilingualPhonemizer` が `UnicodeLanguageDetector` で言語自動検出、各言語 Phonemizer に委譲。

| 言語 | コード | 実装 | 依存 |
|------|--------|------|------|
| 日本語 | ja | JapanesePhonemizer | pyopenjtalk-plus |
| 英語 | en | EnglishPhonemizer | g2p-en (Apache-2.0) |
| 中国語 | zh | ChinesePhonemizer | pypinyin (MIT) |
| 韓国語 | ko | KoreanPhonemizer | g2pk2 (Apache-2.0, optional) |
| ES/PT/FR/SV | es/pt(=pt-BR)/pt-PT/fr/sv | 各 Phonemizer | 規則ベース (依存なし) |

> **PT BR/EU 切替:** `pt` と `pt-BR` は Brazilian Portuguese (BR、 後方互換のため `pt` は BR alias を維持)、 `pt-PT`/`pt-pt` は European Portuguese (EU、 全 8 ランタイム実装)。 `PortuguesePhonemizer(dialect=Dialect.BR | Dialect.EU)` で同一クラス内 dialect 切替。 EU は BR との 5 主要差分 (t/d palatalisation / final-e / final-s / coda-l / r-realization) を post-processing で表現。 IPA 専用 codepoint `ɨ` (中央母音) と `ɫ` (velarised lateral) を PUA contract に追加。 仕様: `docs/spec/pt-dialect-contract.toml`。

> **学習済みモデルは 6 言語 (sv/ko 未含有)、コードは 8 言語対応。**
> **v8 モデルでも ko 対応**: 進行中の v8 (`feat/zero-shot-v8-dataset-scaling`) では Zeroth-Korean + Common Voice ko を追加し **7 lang (ja/en/zh/es/fr/pt/ko)** で学習予定 (KsponSpeech は research-only ライセンスのため 2026-08-02 に除外確定 — v8 は public/商用可の open-model 方針)。 `LANGUAGE_ID_MAP` は `extended_language_id_map` (`ko=7`、 `sv=6` 予約) に切替済、 `_KOREAN_PHONEMES` (IPA インベントリ) も `id_maps.py` に組み込み済で、 学習前の追加作業は data pipeline (parser + CV ko exporter + `piper_train.tools.score_utmos`) のみ完遂 (commit `963c4c49`)。 詳細: [design doc §3.10 / §6.5](docs/design/zero-shot-v8-dataset-scaling-plan.md#310-v8-に韓国語-ko-追加--追加コスト見積-2026-07-09)。

**実装:** `src/python/g2p/piper_plus_g2p/{multilingual,japanese,english,chinese,korean,spanish,portuguese,french,swedish}.py` (学習側) / `src/python_run/piper_plus/phonemize/` (ランタイム側)。
**ABC + レジストリ:** `g2p/piper_plus_g2p/{base,registry}.py`。

### G2P 詳細機能 (日本語)

- **疑問詞マーカー拡張** (`japanese.py:_get_question_type`) — `?!` 強調 / `?.` 平叙 / `?~` 確認 (Issue #204)。
- **文脈依存 N バリアント** (`japanese.py:_apply_n_phoneme_rules`) — 「ん」を後続音で 4 種に分類: N_m / N_n / N_ng / N_uvular (Issue #207)。

### G2P 詳細機能 (中国語)

- **ZH-EN 混在ピンイン化** (`chinese.py:phonemize_embedded_english`) — 中国語に隣接する英単語 (acronym/loanword) を米国英語ではなく Mandarin pinyin で発音。`MultilingualPhonemizer` が `[zh,en,zh]`/`[zh,en]`/`[en,zh]` パターンを自動検出してディスパッチ。辞書 (canonical source): `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json` (acronyms 66 / loanwords 40 / letter_fallback 26 (A-Z))。カスタム上書きは `ChinesePhonemizer(zh_en_loanword_dict_paths=...)`。**全 10 mirror 同期** (Python canonical + Python runtime / Rust 2 crate / Go / C# / WASM / C++ / Kotlin Android / Swift G2P)。CI gate `ZH-EN Loanword Sync Gate / json-sync` が mirror + fixture の byte-for-byte 一致を強制 (`scripts/check_loanword_consistency.py`、`/check-loanword` skill)。Forward-compat loader: 全ランタイムで `schema_version: 2` の未来フィールド受理を pinning。Issue #384, [docs/reference/zh-en-loanword/README.md](docs/reference/zh-en-loanword/README.md)。

### G2P 詳細機能 (スウェーデン語)

- **単語単位 言語判定 (per-word LID)** (`multilingual.py` / `UnicodeLanguageDetector`) — `å`/`ä`/`ö` を含む sv 語 (例: `så`/`och`/`för`/`är`) の英語誤判定を修正 (Issue #539、#297 で実装 → #300 抽出で Python/Rust から脱落した回帰を復旧)。**保守的ポリシー**: strong indicator = `å`/`Å` (`strong_chars`) または 46 語の function-word リスト完全一致のみ。`ä`/`ö` 単独は独語/フィンランド語/借用語と共有のため weak (NOT strong_chars)。辞書 (canonical source): `src/python/g2p/piper_plus_g2p/data/sv_function_words.json`。**全ランタイム同期** (Python canonical + Python runtime / Rust 2 crate / Go / C# / WASM / C++ = 7 データミラー)。CI gate `Swedish LID Sync Gate / json-sync` が ZH-EN loanword gate と同型で 7 データミラー + 6 fixture matrix ミラーの byte-for-byte 一致を強制 (`scripts/check_swedish_lid_consistency.py` + `docs/spec/swedish-lid-mirrors.toml`)。Forward-compat loader: `schema_version: 2` の未来フィールド受理を pinning。[docs/reference/swedish-lid/README.md](docs/reference/swedish-lid/README.md)。

### ランタイム共通機能

- **CPU 推論最適化 (Tier 1-2)** — 4 言語実装で ORT セッション設定統一、Warmup 2 回 (100 phonemes、scales=[0.667,1.0,0.8])、`.opt.onnx`+`.ok` キャッシュ、JA 音素化 LRU キャッシュ (Python のみ)。仕様: `docs/spec/ort-session-contract.toml`。CLI: `--no-warmup`。env: `PIPER_PLUS_DISABLE_WARMUP`, `PIPER_PLUS_DISABLE_CACHE`, `PIPER_PLUS_INTRA_THREADS`, `PIPER_PLUS_G2P_PARALLELISM` (G2P 文単位並列度、`=1` で逐次の旧挙動。Issue #383 / PR #403)。
- **短テキスト合成品質改善 (Strategy A/B/C)** — 全 6 ランタイム (Python/Rust/C#/Go/WASM/C++) 並列実装。A: Silence Padding + Post-trim、B: Dynamic Scales、C: SSML `<break>` 自動挿入 (SSML 実装ランタイムでのみ)。仕様: `docs/spec/short-text-contract.toml`。
- **ストリーミング文単位分割** — 終止符 `.`/`!`/`?`/`。`/`！`/`？`/`．` で分割し文ごとに音素化・推論・yield。SSML は単一ユニット。Python: `src/python_run/piper_plus/text_splitter.py`、Rust: `piper-core/src/streaming.rs`、他言語: 同等実装。仕様: `docs/spec/text-splitter-contract.toml`。**Breaking (v1.12.0):** Python `PiperVoice.phonemize()` が単一要素から複数要素へ (詳細: マイグレーションガイド)。
- **SSML 基本サポート** (Python/Rust/C#/Go/WASM/C++ の 6 ランタイム + G2P-only npm 解析 API) — `<speak>`, `<break>`, `<prosody rate>` を W3C サブセットで実装。実装: `g2p/piper_plus_g2p/ssml.py`, `piper-plus-g2p/src/ssml.rs` (Rust canonical), `PiperPlus.Core/Ssml/SsmlParser.cs`, `go/piperplus/ssml/parser.go`, `wasm/g2p/src/ssml.js` (npm `@piper-plus/g2p`), `src/cpp/ssml.{hpp,cpp}` (CLI `--ssml` 経由、C API 非エクスポート)。 piper-core は `piper-plus-g2p::ssml` を re-export (API 互換維持)。 piper-wasm は同パーサーを `isSsml` / `parseSsml` で WASM expose (TTS 統合は openjtalk-web の `synthesizeSsml` 側で iterate して silence 挿入 + length_scale 切替)。
- **Phoneme Timing 出力** — 仕様 `docs/spec/phoneme-timing-contract.toml` の `(hop_length / sample_rate) × 1000` と fixture parity を各実装が共有する。出力形式と公開面は runtime ごとに異なり、Python HTTP は JSON/TSV、C# CLI は JSON/TSV、Rust/Go/C++ CLI は JSON/TSV/SRT、WASM は `AudioResult.timing` と formatter API を提供する。WASM streaming/SSML、C++ SSML、C# の未配線 formatter には timing 制限がある。Python: `piper_plus.timing`、`PiperVoice.synthesize_with_timing()`、HTTP `/api/phoneme-timing`。WASM: `AudioResult.timing` (deep frozen)。byte parity の範囲と例外は仕様および golden fixture を参照する。

### ランタイム別パッケージ

| ランタイム | パッケージ | バージョン | テスト | パス |
|-----------|----------|----------|-------|------|
| Python (PyPI) | `piper-plus` | 2.0.2 (VERSION 経由 dynamic) | pytest 多数 | `src/python_run/piper_plus/` |
| C# (NuGet) | `PiperPlus.Core` / `PiperPlus.Cli` | 0.5.1 | CI / `dotnet test` 実測 | `src/csharp/PiperPlus.{Core,Cli}/` (TFM `net10.0`) |
| Rust (crates.io) | `piper-plus` / `piper-plus-cli` | 0.5.2 | 多数 | `src/rust/piper-{core,cli,python,wasm}/` |
| Go (Go module) | `github.com/ayutaz/piper-plus/src/go` | tag-based | CI / `go test ./...` 実測 | `src/go/piperplus/`, `src/go/cmd/piper-plus/` |
| JS/WASM (npm) | `piper-plus` | 0.8.1 | CI / `npm run test:npm-package:all` 実測 | `src/wasm/openjtalk-web/`, `src/rust/piper-wasm/` |
| C API | `libpiper_plus` | shared lib | C/Dart/Godot サンプル | `src/cpp/piper_plus.{h,c_api.cpp}`, `cmake/PiperPlusShared.cmake` |
| iOS xcframework + SPM | `piper-plus` (Swift Package) | 2.0.2 | release-shared-lib CI | `Package.swift`, `Sources/PiperPlus/`, `cmake/PrivacyInfo.xcprivacy` |
| **Kotlin/Android G2P (Maven Central)** | `io.github.ayutaz:piper-plus-g2p-android` | 1.0.1 | L1〜L5 (kotlin-g2p-ci.yml) | `android/piper-plus-g2p/` |
| iOS / macOS Swift G2P (SPM) | `PiperPlusG2P` (Swift product, 別 xcframework `-apple-`) | 2.0.2 | XCTest (CI) + `examples/swift-g2p/HelloG2P` CLI | `Sources/PiperPlusG2P/`, `Tests/PiperPlusG2PTests/`, `examples/swift-g2p/`, `Package.swift` (Issue #387) |
| 独立 G2P | `piper-plus-g2p` (Py/Rust)、`@piper-plus/g2p` (npm)、`src/go/phonemize` (Go)、`io.github.ayutaz:piper-plus-g2p-android` (Kotlin) | 同上 | — | `src/{python/g2p,rust/piper-plus-g2p,wasm/g2p,go/phonemize}/`、`android/piper-plus-g2p/` |

**主な追加機能 (ソースブランチの対応):** モデル名自動解決 (`--model tsukuyomi` でエイリアス + 自動 DL)、カスタム辞書 (JSON v1/v2 / TSV)、`[[ phoneme ]]` インライン音素記法 (C#/Python)、`--sentence-silence` / `--phoneme-silence` 制御、`--list-models` 言語フィルタ。`base` / `zero-shot-base-zs-v1` alias は Python 2.0.2 に収録され、旧 2.0.0 / 2.0.1 にはないため、公開 package の catalog は [`docs/guides/development/pretrained-models.md`](docs/guides/development/pretrained-models.md) を確認する。

### サーバー / Docker / 統合

- **OpenAI 互換 TTS API** (`docker/python-inference/inference.py`) — FastAPI ベース、`/v1/audio/speech`、`/v1/models`、`/v1/audio/speech/languages`、`/health`、`/api/phoneme-timing`。テスト: `test_openai_api.py`。
- **WebUI (Gradio)** (`docker/webui/app.py`) — 6lang モデル対応。CI: `webui-test.yml`。ドキュメント: `docs/features/webui.md`。
- **Wyoming Docker + HA 統合** (`docker/wyoming/`) — Home Assistant 連携。ガイド: `docs/guides/integration/home-assistant.md`。
- **MOS ベンチマーク** (`tools/benchmark/`) — サンプル生成、PESQ/STOI 計算、調査フォーム生成。ドキュメント: `docs/benchmark-mos.md`。
- **iOS/Android ビルド CI** (`release-shared-lib.yml`, `cmake/ios.toolchain.cmake`) — libpiper_plus を iOS arm64 / Android (arm64-v8a/armeabi-v7a/x86_64) でクロスコンパイル。iOS は xcframework (device + simulator universal) として配信、`Package.swift` 経由で SPM 利用可能。Apple-embedded プラットフォーム検出は `PIPER_APPLE_EMBEDDED` 変数で集約 (CMakeLists.txt)、OpenJTalk 関数は `src/cpp/openjtalk_ios_stub.c` で stub 化。詳細: `docs/guides/platform/ios-integration.md`、`docs/reference/ios-shared-lib.md`。
- **モデル投稿ガイド** — `CONTRIBUTING_MODELS.md` + GitHub Issue テンプレート (`.github/ISSUE_TEMPLATE/model-{request,submission}.yml`)。

---

## 主要ファイル索引

### Python (学習側)

| 用途 | パス |
|------|------|
| 学習スクリプト | `src/python/piper_train/__main__.py` |
| VITS 実装 | `src/python/piper_train/vits/` (`models.py`, `lightning.py`, `mb_istft.py`, `stft_onnx.py`, `stft_loss.py`) |
| ONNX エクスポート | `src/python/piper_train/export_onnx.py` |
| 推論スクリプト | `src/python/piper_train/infer_onnx.py` |
| ORT セッション管理 | `src/python/piper_train/ort_utils.py` |
| Speaker Encoder | `src/python/piper_train/speaker_encoder/` |
| データセット前処理 | `src/python/piper_train/tools/{prepare_multilingual_dataset,add_prosody_features,prepare_bilingual_dataset}.py` |

### Python (ランタイム側 + G2P)

| 用途 | パス |
|------|------|
| Voice / 音素化 | `src/python_run/piper_plus/{voice,timing,text_splitter}.py`, `src/python_run/piper_plus/phonemize/` |
| HTTP サーバー | `src/python_run/piper_plus/http_server.py` (FastAPI) |
| G2P パッケージ | `src/python/g2p/piper_plus_g2p/` (基底: `base.py`, レジストリ: `registry.py`) |

### 横断的な仕様 / ドキュメント

| 用途 | パス |
|------|------|
| ORT セッション仕様 | `docs/spec/ort-session-contract.toml` |
| 短テキスト戦略仕様 | `docs/spec/short-text-contract.toml` |
| テキスト分割仕様 | `docs/spec/text-splitter-contract.toml` |
| Phoneme Timing 仕様 | `docs/spec/phoneme-timing-contract.toml` |
| Audio Parity 仕様 | `docs/spec/audio-parity-contract.toml` |
| ORT バージョン表 | `docs/reference/ort-versions.md` |
| マイグレーションガイド | `docs/migration/README.md` (index)、最新: `docs/migration/v1.12-to-v2.0.md` |

### 各言語ランタイム

| ランタイム | エントリ | テスト |
|-----------|---------|-------|
| C# | `src/csharp/PiperPlus.sln` | `src/csharp/PiperPlus.Core.Tests/` |
| Rust | `src/rust/Cargo.toml` (workspace) | `src/rust/piper-core/tests/` |
| Go | `src/go/cmd/piper-plus/` | `src/go/piperplus/`, `src/go/phonemize/` |
| WASM/npm | `src/wasm/openjtalk-web/src/index.js` | `src/wasm/openjtalk-web/test/js/` |
| C API | `src/cpp/piper_plus.h`, `piper_plus_c_api.cpp` | `src/cpp/tests/test_c_api*.cpp` |

---

## 基本コマンド

### ONNX エクスポート

```bash
# 推奨 (EMA + stochastic + FP16 + emb_lang 自動統一)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
    /path/to/checkpoint.ckpt /path/to/output.onnx
```

| オプション | 既定 | 説明 |
|-----------|------|------|
| `--no-stochastic` | - | deterministic (デバッグ用) |
| `--no-fp16` | - | FP16 変換を無効化 |
| `--unify-emb-lang` / `--no-unify-emb-lang` | auto | emb_lang 自動統一 (シングルスピーカー多言語で自動有効) |
| `--unify-emb-lang-source N` | 0 | emb_lang 統一のソース言語 index |
| `--simplify` | - | ONNX simplification 適用 |
| `--debug` | - | デバッグログ |

### 推論

```bash
# テキスト直接 (6lang multilingual)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
    --model <model.onnx> --config <config.json> --output-dir <out> \
    --text "こんにちは" --language ja-en-zh-es-fr-pt --speaker-id 0 --noise-scale 0.667

# Voice Cloning (参照音声から)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
    --model <model.onnx> --config <config.json> --output-dir <out> \
    --text "こんにちは" \
    --reference-audio <ref.wav> --speaker-encoder-model <encoder.onnx> \
    --language ja-en-zh-es-fr-pt
```

`--language` の言語コード順は任意 (内部で canonical key に正規化)。

**JSONL 入力 (phoneme_ids 直接指定):**

```bash
cat test.jsonl | uv run python -m piper_train.infer_onnx --model <model.onnx> --output-dir <out>
# 1 行 1 発話: {"phoneme_ids": [...], "speaker_id": 0, "prosody_features": [{"a1": -2, ...}]}
```

---

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| 推論音声が「ピー」音 | DP 学習失敗。`--samples-per-speaker` を使う / `--disable_auto_lr_scaling` / `--base_lr 1e-4` |
| GPU OOM | `NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1` / batch_size と samples_per_speaker を下げる / 異なる batch size からの resume を避ける |
| 学習速度が遅い (Ada/Blackwell) | TF32 enabled 確認 (`torch.backends.cuda.matmul.allow_tf32 == True`、 DR-007 で default ON) / `--precision bf16-mixed` 使用 (Template default、 DR-008) / `--compile` 試行 (Triton 3.x autotune、 warm 後 +5-10%) / `nsys profile` で bottleneck 分析 |
| 学習速度が遅い (T4、 VRAM 16GB) | VRAM 制約を確認、 batch_size 8-12 に絞る / `--no-wavlm` で VRAM 1-2GB 節約 / 6lang base 規模なら Ada 6000 / RTX 5090 移行検討 |
| ゾンビ GPU プロセス | `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` で残存 PID 確認、 `kill` で解放 |
| ONNX 変換エラー | `CUDA_VISIBLE_DEVICES=""` で CPU モード |
| HiFi-GAN ckpt resume 失敗 | v1.12.0 で `Generator` 削除。旧 v1.12/v1.13 系は legacy root の `piper-plus-base/model.ckpt` から再 FT。v2.0 系は、実験用 Zero-Shot/FT base `releases/zs-v1/base.ckpt` (revision `3620ed788667cb76f08bd6cf2db8152c1f4c8bd1`) を使う。詳細: マイグレーションガイド |
| DDP で NCCL collective timeout (30 分) | **まず「1 rank だけ死んでいないか」を疑う** — rank の例外死は ALLREDUCE timeout に偽装される。単一 GPU + 同一 config で走らせ素の例外を出す。過去例: .env の CRLF 混入で rank0 の wandb login が例外死 (2026-08) |
| zero-shot 合成が「がびがび」(5-9kHz ノイズ) | **v9 で修正済み** (PQMF 変調位相項 `±(-1)^k·π/4` を `mb_istft.py` に実装)。v9 以前の ckpt には残存。**別層の A3 (1-3kHz 調波間ノイズ) は未根治** — v11 carrier head で構造保証を実証済み、実用は v11b 完走待ち。UTMOS/HNR はこのノイズに全盲 — 帯域スペクトル検査 (`/publish-model` フェーズ 3.5) + `piper_train.tools.measure_comb_hnr` で確認。詳細: [PQMF 根本原因](docs/design/zero-shot-noise-root-cause-pqmf.md) / [v10b 残存ノイズ診断](docs/design/zero-shot-v10b-residual-noise-diagnosis.md) |

---

## 外部リソース

| リソース | URL |
|----------|-----|
| 6lang ベース ckpt (legacy root、v1.12/v1.13 系) | `ayousanz/piper-plus-base/model.ckpt` (HF) |
| Zero-Shot/FT base `zs-v1` (v2.0 系、実験用) | [`releases/zs-v1/base.ckpt`](https://huggingface.co/ayousanz/piper-plus-base/resolve/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1/base.ckpt) |
| つくよみちゃん `zs-v1` (public, 実験公開) | [`releases/zs-v1/tsukuyomi.onnx`](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1/tsukuyomi.onnx) + [publication record](docs/design/tsukuyomi-publication-ready-2026-10-12.md) |
| つくよみちゃん legacy ONNX | `ayousanz/piper-plus-tsukuyomi-chan` (HF root files; package aliases remain legacy) |
| CSS10 JA ONNX | `ayousanz/piper-plus-css10-ja-6lang` (HF) |
| 20話者データセット | `ayousanz/moe-speech-20speakers-ljspeech` (HF) |
| パッケージレジストリ | PyPI / NuGet / crates.io / npm — それぞれ `piper-plus` または `PiperPlus.*` で検索 |

---

## Automation (skill / hook / pre-commit)

開発作業の繰り返しを skill / pre-commit / pre-push gate に落とし込んでいる。 詳細仕様は [.claude/README.md](.claude/README.md)。 主要 skill 一覧:

| skill | 用途 |
|-------|------|
| `/create-pr` | push → 構造化 PR 本文 (pull_request_template.md 準拠) → CI 監視ループ → review thread 返信+resolve まで 1 skill で完結 (skill 間 handoff なし、 工程の取りこぼし防止)。 **`gh pr create` 直接実行は禁止** — 構造化フローを通すため。 hook `.claude/hooks/guard-bash.sh` で block 済み |
| `/watch-pr <PR>` / `/watch-ci-patterns` | CI 監視、 failure を flake/drift/env/test bug に分類 |
| `/reply-review <PR>` | unresolved review thread への返信 + resolve |
| `/check-review-backlog` | open PR の review backlog 集計 |
| `/precheck` / `/check-pr-ready` / `/run-tests` | scope 自動判定で local CI equivalent を実行 |
| `/commit` / `/sync-docs` | コミット前 ドキュメント整合性 + 構造化メッセージ |
| `/check-loanword` / `/check-pua` / `/check-runtime-parity` / `/check-cross-runtime` / `/check-new-runtime-asset` | cross-runtime 同期検査 |
| `/check-preprocess-env` | 学習前処理 (dataset 構築) 環境の事前検証 (g2p inventory / NLTK data / audio_norm cache 形式 / parquet 依存) |
| `/add-language <code>` / `/review-language <code>` | 新言語追加と 10 エージェント並列レビュー (skill ではなく `.claude/commands/` の slash command) |
| `/release-prep` / `/prepare-release` | リリース確認 (read-mostly) と bump 適用案 |
| `/publish-model` | 学習 ckpt → export + sanity + bench + HF upload chain |
| `/remote-train-ops` | vast.ai 等リモート GPU instance の学習運用標準手順 (レンタル/デプロイ/監視/停止)。実測 6 事故クラス (無言死/監視不達/pin 不整合/pkill 自己マッチ/遅い box/幽霊起動) の再発防止 |
| `/eval-zs` | zero-shot SECS 評価の標準手順 (cross-utt + dual-encoder + Goodhart 検知 + 4 点判定)。SECS 評価・モデル比較は本 skill 経由必須 |
| `/bump-deps` | ORT/openjtalk/ruff の cross-runtime canonical sync 更新 |
| `/skill-health` | skill / hook 自身の health check (frontmatter / script 参照 / trigger 衝突) |

pre-commit / pre-push gate は `.pre-commit-config.yaml` に集約 (95+ hook、 contract gate 30+、 cross-language formatter 6 言語)。 主要 gate の一覧と trigger 条件は [.claude/README.md](.claude/README.md) の「Pre-commit / pre-push gates」節を参照。

---

## アーカイブ: バイリンガル版 (v2/v3/v4) の履歴

v2/v3/v4 は 6lang に置き換え済み。詳細・旧データセットパス・つくよみちゃん FT 履歴 (v3→v4→6lang-v2 の段階的改善、`emb_lang` コピーや `--freeze-dp` の learnings) は git 履歴 (`git log --grep="bilingual\\|v[234]"`) または `CHANGELOG-archive.md` を参照。
