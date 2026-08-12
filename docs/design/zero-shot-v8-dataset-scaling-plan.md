# Zero-Shot TTS v8 — 話者数スケーリング学習計画

> 作成日: 2026-07-07 / 最終更新: 2026-08-02 / **状態: 再開 — smoke test 待ち (開始ブロッカーなし、§4.5)**
> 2026-08-02: origin/dev (`2412e370`、v2.0 piper→piper_plus 改名込) へのリベース完了。
> **KsponSpeech は v8 から除外確定** (public + 商用利用可の open-model 方針、§6.5 冒頭) —
> ko は Zeroth-Korean + Common Voice ko のみ (7-lang 計 話者 ~3,790 / 発話 ~346k、§2)。
> インスタンスは **4x A100 SXM4 40GB $3.43/hr (storage 込) を承認済み** (§4.1)。smoke 自動 go 基準は §3.8。
> 前提: v7 multi-6lang zero-shot (epoch 32、SECS 既知 0.6619 / zero-shot 0.6879) の後継。
> コードは `dev` にマージ済み (PR #222 / #579)。学習は vast.ai レンタル GPU で実施予定。
> 関連: [`multi-6lang-zero-shot-v7-training-results.md`](multi-6lang-zero-shot-v7-training-results.md) /
> [`zero-shot-quality-improvement-plan.md`](zero-shot-quality-improvement-plan.md) (Tier 4 #19 話者数拡大の実行版) /
> [`../handoff/zero-shot-tts-handoff-2026-06-20.md`](../handoff/zero-shot-tts-handoff-2026-06-20.md)

---

## 1. 目的と根拠

**zero-shot 話者類似度は「発話数」ではなく「学習話者数 (話者空間の密度)」でスケールする。**
v7 は発話 497k と十分な一方、話者は 571 で、文献的に「不足」と指摘されるゾーンにある。

- ZMM-TTS (arXiv:2312.14398): 学習話者 546 名で、1,000〜2,500 話者の他システムに未知話者類似度で劣後と自己分析。v7 の 571 話者は同ゾーン
- USAT (arXiv:2404.18094) 等: seen/unseen ギャップは VCTK (~110話者) 学習より LibriTTS (1,000+話者) 学習で明確に縮小
- v7 自身の傍証: Tsukuyomi FT で 0.7749 到達 (= モデル容量は十分) に対し zero-shot は 0.6879。この差が話者空間の粗さ由来

**設計原則: 1 話者あたり発話を cap して予算を話者多様性に再配分し、話者数を 571 → ~3,300+ に増やす。**
発話総数は ~340k に縮むが、総 step 数は max_epochs 増 (§3.1) で v7 同等 (~216k steps) を確保する。
ja の数千話者級拡張 (gol-dataset) は v9 に段階を分ける (§7)。

アーキテクチャ上の好条件: zero-shot 構成は emb_g (話者テーブル) 廃止済みで、話者条件付けは
per-utterance CAM++ embedding → spk_proj 経由。**話者を何人増やしてもモデル構造・音素シンボル
(173、同一 6 言語) は不変。** 追加作業は per-utterance embedding 抽出のみ。

## 2. データセット構成 (v7 → v8 案)

| 言語 | v7 (発話/話者) | v8 案 (発話/話者) | 追加ソース | ライセンス |
|---|---|---|---|---|
| ja | 59,694 / 20 | ~55k / **473** | **moe-speech-plus** (全473話者、cap ~120 utt/spk) | moe-speech license (gated manual、学習済モデルの public 配布可 — 下の 2026-08-02 決定参照) |
| en | 64,698 / 310 | ~110k / **2,456** | LibriTTS-R **全話者** (cap ~50 utt/spk) | CC BY 4.0 |
| zh | 63,223 / 142 | ~70k / **218** | AISHELL-3 フィルタ緩和 (全話者) | Apache 2.0 |
| es | 168,374 / 63 | ~45k / **77** | CML-TTS **フィルタ緩和で corpus 全話者** (cap で発話縮小) | CC BY 4.0 |
| fr | 107,464 / 28 | ~35k / **45** | CML-TTS **フィルタ緩和で corpus 全話者** | CC BY 4.0 |
| pt | 34,066 / 8 | ~25k / **30 + CV 数百** | CML-TTS フィルタ緩和 + **Common Voice pt (品質フィルタ選別)** | CC BY 4.0 / CC0 |
| **ko (2026-07-09 追加 / 2026-08-02 縮小確定)** | — | ~25k / **~210** | **Zeroth-Korean** (openslr.org/40、~181 spk / ~22.2k utts) + **Common Voice ko** (UTMOS≥2.5 + ≥20 clips + cap 60 選別、~30-50 spk / ~3k utts)。KsponSpeech は除外 (§6.5 冒頭の 2026-08-02 決定) | CC BY 4.0 / CC0 |
| **計 (6-lang v8)** | **497,519 / 571** | **~321k / ~3,578** | | |
| **計 (7-lang v8 + ko)** | — | **~346k / ~3,790** (6-lang 321,391 utts + ko ~25k utts / 6-lang 3,578 spk + ko ~210 spk) | | |

> **決定 (2026-07-07)**: v8 の ja は moe-speech-plus のみとする (ユーザー決定)。
> gol-dataset (19,349 話者) は v9 拡張候補として §7 に退避 — 転写有無・品質・gated 承認の
> 未確認リスクを v8 のクリティカルパスから外し、473 話者での ja 参照 SECS 改善を先に実測する。
> es/fr/pt の話者は corpus 上限。縮小による es/fr 品質回帰は ep10 SECS で監視。
>
> **決定 (2026-07-09)**: **韓国語 (ko) を同一 v8 run で 7-lang 化**。 G2P は 7 ランタイム全てで
> 既に ready (`docs/spec/language-id-map-contract.toml` の `extended_language_id_map` で
> `ko=7` を pin 済、 `id_maps.py:_KOREAN_PHONEMES` も組み込み済) のため、 追加コストは
> **data pipeline (parser 3 種 + CV ko exporter) のみ**。 6-lang 計算量に対する増分は
> §3.10 に集約。 詳細な pipeline 実装は §6.5。
>
> **決定 (2026-08-02)**: **KsponSpeech (AI-Hub、research-only ライセンス) を v8 から除外**。
> v8 を過去の piper-plus 事前学習モデル同様 **public + 商用利用可の open-model として公開**
> する方針が確定したため (詳細は §6.5 冒頭の注記)。ko は Zeroth-Korean + Common Voice ko
> のみ (~210 spk / ~25k utts) となり、7-lang 合計は **話者 ~3,790 / 発話 ~346k** (上表反映済)。
> §2.4 / §3.10 / §6.5 内の KsponSpeech 前提の記述は歴史記録として保持。
> あわせて上表 ja のライセンス欄の旧表記「研究用途限定 (gated)」を訂正 — これは raw データ
> セットのアクセス条件 (gated manual) とモデル配布条件を混同した表記で、moe-speech を学習
> データに含む学習済みモデルの public + 商用利用可配布は、過去の piper-plus 事前学習モデル
> (6lang base / v7、いずれも MOE-Speech 系 ja データ含有) と同様に可能であり open-model
> 方針と両立する。research-only でモデル配布と両立しないのは KsponSpeech のみ (→ v8 除外済)。

### 2.1 ja ソース詳細

**[`ayousanz/moe-speech-plus`](https://huggingface.co/datasets/ayousanz/moe-speech-plus)** (gated manual、moe-speech license)

- MoeSpeech 473 キャラ / ~394k ファイル / ~622h に **anime-whisper + parakeet 二重転写 /
  speechMOS (UTMOS v2) / 感情ラベル** を付与済み → 品質フィルタが即座に可能。全話者採用
- ⚠️ 声質は若年女性に大きく偏る (ゲーム音声由来)。男性・年配参照の zero-shot は
  弱い可能性があり、ja 未知話者評価 (§5) で偏り込みの実測を行う

### 2.2 es/fr/pt の話者拡充 (2026-07-07 調査)

v7 は CML-TTS をフィルタで es 63 / fr 28 / pt 8 話者に削っていたが、**corpus 自体には
es 77 / fr 45 / pt 30 話者が存在** (CML-TTS 論文 Table 1)。まずフィルタ緩和で全話者を使う
(工数ほぼゼロ、v7 で削られた理由は前処理時に要確認)。それでも薄い言語の商用利用可能な追加候補:

| 候補 | es | fr | pt | ライセンス | 品質 / 注意点 |
|---|---|---|---|---|---|
| CML-TTS (採用: 緩和) | 77 spk / 279h | 45 spk / 260h | 30 spk / **23h** | CC BY 4.0 | 24kHz、TTS 向け設計 |
| MLS | +120 spk / 918h | +114 spk / 1,077h | +31 spk / 161h | CC BY 4.0 | ⚠️ **16kHz** (22.05kHz 学習に帯域不足)。LibriVox 由来で CML と話者重複 → dedup 必要 |
| **Common Voice** (pt は採用推奨) | ~550h validated / 数万 spk | 1,096h / 21,003 spk | 187h / **3,817 spk** | **CC0** | クラウドソース mic 品質 → UTMOS フィルタ + 話者あたり ≥20 clip 必須。48kHz mp3 で帯域は OK |
| VoxPopuli | 166h | 211h | (転写なし) | CC0 | 欧州議会音声 (残響あり)、v9 候補 |

**v8 方針 (決定 2026-07-07)**: ① CML-TTS フィルタ緩和 (es/fr/pt) は必須。
② **pt のみ Common Voice を追加** (コーパス 23h / 30 話者は 6 言語中唯一クリティカルに薄い。
CV pt から品質フィルタで +100〜300 話者を目標)。③ MLS は 16kHz 品質リスクがあるため
v8 では見送り (話者数がそれでも不足なら v9 で speaker-diversity 目的に cap 小で検討)。
④ CV es/fr・VoxPopuli・zh AISHELL-1 (+400 spk、Apache 2.0、16kHz) は v9 オプション。

### 2.3 選別フィルタ (ja)

1. duration 1.0–15.0s
2. speechMOS **フィルタなし (確定 2026-07-07、ユーザー決定: moe-speech は高品質のため
   不要)**。MOS は cap 120 の選抜順位付けにのみ使用 (発話数の多い話者では
   クリーンなクリップが優先される)。参考実測分布: ≥2.5 が 42.8% / ≥2.0 が 74.4%
3. 二重転写 (anime-whisper vs parakeet) の CER ≤ 0.15 (転写信頼性ガード、実測棄却率 ~8%)
4. 話者あたり発話 ≥ 20 (samples_per_speaker=4 サンプラー要件) / speechMOS 上位 cap 120

実装: `tools/prepare_moe_speech_plus.py` (zip 展開なしのストリーム選別)。出力はマージ済み
multi-speaker LJSpeech (`wavs/ + metadata.csv` 3 列 `filename|speaker|text`) で、
`piper_train.preprocess --dataset-format ljspeech` (multi-speaker 自動判定) に直結する。

### 2.4 選別フィルタ (ko) — 2026-07-09 追加

ko は 3 ソースを合算するため、 ソースごとに異なる品質特性を吸収するフィルタを併用する。
実装は `prepare_multilingual_dataset.py:parse_{zeroth_korean,kspon_speech,common_voice_ko}`
(既存 `parse_aishell3` / `parse_cml_tts` と同一シグネチャ) と
`export_common_voice_ko.py` (`export_common_voice_pt.py` ミラー、 UTMOS tsv 追加サポート)。

1. **duration**: 1.0–15.0s (全ソース共通、 既存 `cache_audio_parallel` に統一)
2. **話者あたり発話 ≥ 20** (samples_per_speaker=4 サンプラー要件、 全ソース共通)
3. **UTMOS フィルタ (Common Voice ko のみ)**: `≥ 2.5`。 クラウドソース mic 品質のため
   UTMOS tsv (`export_common_voice_ko --utmos-tsv ...` で作成) で足切り。
   実測通過は ~30 話者想定 (validated ~50 spk → UTMOS 通過 ~30 spk)
4. **KsponSpeech ETRI notation 除去** (`_clean_kspon_text`) — **⚠️ KsponSpeech は v8 では
   除外 (§6.5 冒頭の 2026-08-02 決定参照)。以下はコード残置分 (research 用途) の仕様**:
   - `(A)/(B)` 表記は **発音形 (B) を採用** (dual-form 前提の学習ノイズを除去)
   - `b//` / `l//` / `o//` / `n//` / `u//` の ETRI ノイズタグを削除
   - `+` (反復) / `*` (強調) / stray `/` を削除
   - **raw `.pcm` (16 kHz mono s16le) を直読** (§3.11 impl2、 commit `c2f59ec0`)。
     従来必要だった ETRI PCM→WAV 事前変換 (~3-4h wall) は `norm_audio._read_pcm16_mono`
     dispatcher (`.pcm` 拡張子で int16 → float32/32768 直変換) で不要化。
     既に WAV 化済のユーザは `audio_ext=".wav"` を渡せば従来経路も維持
5. **話者 ID の prefix**: sources 間でグローバルユニーク化のため
   `zeroth-<original_id>` / `kspon-<original_id>` / `cv-<original_id>` を parser 側で付与

speechMOS フィルタは KsponSpeech / Zeroth では **適用しない** (Zeroth は読み上げクリーン音源、
KsponSpeech は自然発話でノイズ含み → MOS フィルタは話者多様性を過度に削るため cap 60/spk
で分散を確保する方針)。 CV ko のみ UTMOS で品質下限を確保。

## 3. 学習方式: スクラッチ + smoke test

1. **smoke test**: v7 `epoch=32-step=216326.ckpt` から新データセットで 1 epoch warm-start。
   loss 有限性 / DINO 動作 (loss_dino ≠ 0 貼り付き) / NaN skip 率 (< 5%) / SECS 評価パスを検証
2. **本走**: from-scratch、**max_epochs 80** (発話数が v7 の 2/3 のため、総 step 数
   ~216k = v7 同等を epochs で確保)。話者分布が大きく変わるため旧 DINO center /
   Discriminator 状態を引きずらないスクラッチが素直。v7 の 5 修正
   (5cdfafb/34ad257/5e700d4/ba71e16/95e74cb) は dev 反映済みで序盤 NaN リスクは低い

### 3.1 学習コマンド (A100 80GB × 1 想定)

Template A (CLAUDE.md) ベース + zero-shot 系フラグは v7 再開コマンド準拠。 v7 (V100×4、`32-true`) から
A100 単一 GPU への移行に伴う **P0 最適化フラグ** をまとめて反映 (詳細は §3.2)。 主な差分:

```
--accelerator gpu --devices 1 --precision bf16-mixed
--batch-size 128 --samples-per-speaker 4        # 80GB、要 OOM 手前調整
--max_epochs 80 --checkpoint-epochs 2 --save-top-k 5   # 全 keep は 75GB で disk full → rolling
--base_lr 2e-4 --disable_auto_lr_scaling
--lr-scheduler cosine --lr-warmup-epochs 5 --lr-min 1e-5
--kl-annealing-epochs 10 --c-dino 0.5 --c-spk 1.0 --c-sub-stft 1.0
--spk-emb-noise-sigma 0.05 --max-phoneme-ids 400
--speaker-encoder-path <campplus.onnx>
--language-balanced-sampling                     # ja/en 話者比 >> pt 30 話者のため必須
--num-workers 8                                  # A100 host は 32 vCPU、v7 の 2 では GPU 待ち
--prefetch-factor 4                              # T2 (§3.6): pin_memory + prefetch=4 で H2D queue を warm 保持
--precomputed-mel                                # P1 (§3.6): 学習前に `python -m piper_train.tools.precompute_mel` を pre-run 必須
--val-every-n-epochs 5                           # SCL/DINO 込み val は G+D full forward、頻度低下
--compile --compile-mode reduce-overhead         # torch.compile (§3.5 でリベンチ後 default 維持)
--no-wavlm                                       # v7 継承 (VRAM 節約 & WavLM 経路 P0 未実装)
# --channels-last                                # T1 (§3.6): opt-in default OFF、 A/B 実測で -16% sec/step 見込みなら default 化検討
# --enable-length-bucketing / --no-compile-dynamic は §3.5 の 300 batch A/B で
# +34% の逆効果を実測、 v8 本走では **使わない** (Fix B [`a5fa6f2`] で再設計済み、 本走前に再 A/B)
```

**LANGUAGE_ID_MAP (7-lang extended、 §6.5 / §2 で ko 追加)**:
6-lang v8 は `{ja:0, en:1, zh:2, es:3, fr:4, pt:5}` の canonical map を使用していたが、
**ko 追加後は `docs/spec/language-id-map-contract.toml:extended_language_id_map`**
(`{ja:0, en:1, zh:2, es:3, fr:4, pt:5, sv:6, ko:7}`) に切替。 ja..pt indices は不変で、
`sv=6` は将来枠、 `ko=7` が今回投入。 CLI 側 (`--ko-zeroth / --ko-ksponspeech / --ko-cv`
を `prepare_multilingual_dataset.py` に渡す) で dataset.jsonl に `language_id=7`
の utts が入り、 `config.json` の `num_languages` は自動的に 7 になり `emb_lang`
テーブルサイズが 7 次元化 (§6.5)。 学習 CLI 自体は 6-lang と同一。

**削除したフラグ (v7 コマンドから)**:
- `--no-pin-memory` — v7 は V100×4 で CPU RAM 節約用。 単一 A100 では pageable copy が
  DMA を使えず 2-3x 遅くなるため **削除必須**
- `--precision 32-true` → `--precision bf16-mixed` — A100 は BF16 native Tensor Core
  (DR-008、Issue #527)
- `--gradient-clip-val 0` — 既定 1.0 を使う。 v7 は NCCL sync mismatch 回避のため 0 で回したが、
  単一 GPU では該当せず、 grad_clip=1.0 の安全網はコスト微小

### 3.2 P0 最適化の根拠と期待効果

2026-07-07 実施の高速化監査 (v7 CLI そのまま A100 実行 → 6-8h/epoch と想定)、 コード修正 2 件
+ CLI 変更で 3-4h/epoch へ短縮の見込み。 コード修正は既に main に commit 済み:

| 最適化 | 変更点 | 期待効果 | 反映方法 |
|---|---|---|---|
| TF32 matmul (torch 2.x canonical) | `torch.set_float32_matmul_precision('high')` を `__main__.py` に追加 | +1-3% | commit `81f88817` |
| mel debug print の GPU sync 削除 | `torch.min(y) < -1.0` / `torch.max(y) > 1.0` を `mel_processing.py` から削除 | +1-2% | commit `81f88817` |
| Super-MAS Triton kernel を docker に取り込み | `docker/python-train/Dockerfile` に `[super-mas]` extra 追加 | MAS block +3-10% | commit `168d22e2` |
| pin_memory 有効化 | `--no-pin-memory` を **付けない** | +5-10% (host→GPU DMA) | CLI 変更 |
| checkpoint rolling window | `--save-top-k 5` + `--checkpoint-epochs 2` | disk full 回避 (75GB → 5GB) + 保存 sync 5-10s/epoch 節約 | CLI 変更 |
| torch.compile | `--compile` | warmup 3-5 分後 +10-25% | CLI 変更 |
| Validation 頻度削減 | `--val-every-n-epochs 5` | -3-5%/epoch | CLI 変更 |
| DataLoader 並列度 | `--num-workers 8` | IO-bound 時 +5-15% | CLI 変更 |

**未反映 (v8 完走後の別 PR、v9 で検討)**:

- CAM++ SCL skip (`--speaker-encoder-path` を外す) — v8 は per-utterance embedding 100% 完備
  のため無駄計算だが、 mel-domain SCL fallback との品質差を A/B したい (v7 は CAM++ SCL 採用)
- WavLM feature の G/D 間キャッシュ + BF16 化 — 現行 `--no-wavlm` で回すため v8 では効果なし
- SDPA (`F.scaled_dot_product_attention`) 置換 — attention は極小規模 (n_layers=6, n_heads=2)
  で効果 3-8%、 relative bias 互換の検証が必要

**過去に検証済で不採用**:

- CAM++ `cudnn_conv_algo_search=EXHAUSTIVE` (revert `faafa13d`) — session 作成 15 分 hang
- CAM++ 真の GPU batched inference default 化 (`79cb9afb` は opt-in 維持) — cosine 0.27 破損
- `num_workers` 自動調整 (PR #164 で削除) — shared memory 枯渇
- V100 で `--precision 16-mixed` — backward 5x 遅い、必ず `32-true` (V100) / `bf16-mixed` (A100+)

### 3.3 Plan A 実装完了 (2026-07-09)

§3.2 の P0 最適化を土台に、 A100 単一 GPU での epoch 時間を追加で 20-35% 削減する
「Plan A: コード側の低リスク throughput 最適化」 4 件を feature branch にランディング済み。
すべて既存 API/学習契約を破壊せず、 CLI opt-in または DDP 内部フラグで有効化する形。

| # | commit | 変更 | 対象ファイル | 期待効果 |
|---|--------|------|-------------|---------|
| 1/4 | [`355f89eb`](https://github.com/ayutaz/piper-plus/commit/355f89ebee41b07b991de9f51a89aad30b6a6cb9) | MPD の y/y_hat を batch dim で concat して 12→6 kernel launch | `src/python/piper_train/vits/models.py` (+13/-7)、 `src/python/tests/test_d_batch_concat.py` (+152 新規) | **D backward +5-10%** (launch overhead 削減、 allclose atol=1e-5 で等価性検証済) |
| 2/4 | [`14847fe7`](https://github.com/ayutaz/piper-plus/commit/14847fe7962f379de86a07506bfc5f0aca08ec0a) | `DDPStrategy` に `static_graph=True` 追加 | `src/python/piper_train/__main__.py` (+7/-1)、 `src/python/tests/test_ddp_strategy.py` (+20/-5) | **multi-GPU throughput +5-8%** (VITS GAN 交互最適化の unused-param 集合が step ごとに固定 → iteration 1 の graph を再利用) |
| 3/4 | [`dbdef2d2`](https://github.com/ayutaz/piper-plus/commit/dbdef2d2cd6a849e2c29f992cf5f1073f32a18a2) | `SpeakerBalancedBatchSampler` に length_bucket opt-in | `src/python/piper_train/vits/dataset.py` (+66/-2)、 `src/python/piper_train/__main__.py` (+12)、 `src/python/piper_train/vits/lightning.py` (+6/-1)、 `src/python/tests/test_length_bucketing.py` (+276 新規) | **step time -30-40% (padding 削減による 1.4-1.6x)**。 `samples_per_speaker=4` contract は保持、 intra-speaker length spread が半減することを test で保証。 CLI: `--enable-length-bucketing` |
| 4/4 | [`15b33fd8`](https://github.com/ayutaz/piper-plus/commit/15b33fd8846714ff2c01bceb77e8a2e9b3153ed2) | torch.compile mode/dynamic を CLI 化 | `src/python/piper_train/__main__.py` (+37/-3) | **compile 再チューン +5-10%** (length_bucketing で shape 固定 → `--compile-mode=max-autotune` + `--no-compile-dynamic` で CUDA Graph capture 可能化)。 default は既存挙動 `reduce-overhead` + `dynamic=True` を維持 |

**Plan A の CLI 推奨組み合わせ** (§3.1 の学習コマンド末尾に反映済み):

```
--enable-length-bucketing        # 3/4: sampler 側の length bucketing 有効化
--compile                        # 4/4: torch.compile を有効化
--compile-mode reduce-overhead   # 4/4: default (安全側)。 shape が bucketing で完全固定なら max-autotune も可
--no-compile-dynamic             # 4/4: bucketing 前提 → dynamic 追跡を切って CUDA Graph capture を許可
```

> **`--compile-mode=max-autotune` の判断:** length_bucketing で phoneme_length が
> ソートされても、 batch 内で `max(len)` に padding される値は epoch を通じ複数 shape
> が出る (bucket 境界ごとの max)。 CUDA Graph capture (max-autotune) は shape 固定を
> 要求し、 mismatch のたびに recompile → 起動オーバーヘッド。 **v8 本走の初回は
> reduce-overhead で運用**、 profile で shape 分布が数種に収束していることを確認して
> から max-autotune を試す (別 PR)。

**Plan A / B / C の想定 wall-clock 比較** (§4.3 のコスト表を更新):

| Plan | 内容 | epoch 時間見込 | 本走 80ep 時間 | 本走 80ep コスト ($1.73/hr) |
|------|------|--------------|--------------|-----------------------------|
| baseline (P0 のみ、§3.1 の変更前 CLI 相当) | v7 flags + pin_memory + compile default | 1.5-1.7h | 5.0-5.7 日 | ~$208 |
| **Plan A (今回、bucketing + D concat + static_graph + compile 再チューン)** | 上記 + Plan A 4 件 | **1.0-1.2h** | **3.3-4.0 日** | **~$137-166** |
| Plan B (Plan A + WavLM cache / SDPA / SCL 見直し) | 未着手、 v8 完走後の別 PR | 0.9-1.1h | 3.0-3.7 日 | ~$125-153 |
| Plan C (Plan B + kernel fusion / FlashAttention 派生) | 検討中 | 0.8-1.0h | 2.7-3.3 日 | ~$112-137 |

Plan A 単独で **本走 3.3-4.0 日 / ~$137-166** に短縮、 前後 phase (DL/前処理/評価) を含めた
end-to-end で **~5-6 日 / ~$194** の見込み (§4.3 更新表参照)。

**未実装 (skip 理由あり):**

- **tmpfs preload** — 前処理済み ~400GB tarball を tmpfs に展開する IO 高速化案。
  vast.ai インスタンスの RAM (A100 SXM4 で ~128GB) では収まらず、 部分 preload の
  benefit は SSD read cache (kernel が自動処理) と重複するため **skip**。 必要な場合は
  vast.ai instance 起動時の onstart script で SSD → RAM cache 温めのみ実施 (数分)。
- **nsys observation (Nsight Systems によるプロファイリング)** — kernel-level bottleneck
  の実測。 実 GPU (A100) 上でしか意味を持たないため、 v8 本走開始時に取得 → Plan B 設計に
  フィードバックする方針 (別作業)。 ローカルの CI/dev マシンでは skip。

### 3.4 vast.ai A100 実測結果 (2026-07-09) + scratch NaN blocker 修正

Plan A 反映後の初 GPU 実行で 2 つのバグを発見し、 修正済 (両方 feature branch にコミット):

**Bug #1: cuFFT が BFloat16 で失敗** (commit [`3dcabd57`](https://github.com/ayutaz/piper-plus/commit/3dcabd57))
- `mel_spectrogram_torch` / `spectrogram_torch` の `torch.stft` が bf16-mixed autocast 下で
  `RuntimeError: cuFFT doesn't support tensor of type: BFloat16` を吐く。 v7 の `32-true`
  では発生せず、 A100 bf16-mixed 化で顕在化
- 修正: STFT 前に bf16/fp16 を fp32 に defensive upcast。 出力 dtype は L1 loss と揃う fp32

**Bug #2: scratch 初期化から KL loss = inf → 100% 全 batch skip** (commit [`1a86aa55`](https://github.com/ayutaz/piper-plus/commit/1a86aa55) + [`563f8361`](https://github.com/ayutaz/piper-plus/commit/563f8361))
- 診断: `_PIPER_DEBUG_LOSS` env-gated print で `loss_kl=inf` を特定。 さらに
  `_PIPER_KL_DEBUG` で `logs_p_min=-431.9 logs_p_max=521.9` (clamp 対象範囲を大きく超える)、
  `exp(-2 * logs_p)` が `((z_p - m_p) ** 2)` と積で fp32 max (3.4e38) を超えて inf 化
- 原因 1: `TextEncoder`/`PosteriorEncoder` projection が scratch init で `logs_p ~ -30` を
  出力可能。 `enc_p`/`enc_q` 直後で `logs_p, logs_q = clamp(-15, 15)` を追加
- 原因 2: 上記だけでは不十分。 line 991 の `logs_p = matmul(attn, logs_p)` で MAS 由来の
  attn が scratch 初期化時に non-one-hot となり pre-clamp の [-15, 15] を 30x 増幅。
  Super-MAS Triton dispatch や tie-breaking で複数の 1 が 1 行に立つ症状。 → MAS 拡張後
  にも `logs_p = clamp(-15, 15)`、 `m_p = clamp(-1000, 1000)` を追加
- 修正後: **Non-finite skip 0 件 / 40 batches** (それ以前は 40/40 で 100% skip)
- 副次: `loss_kl` の初期絶対値は依然 ~1e14 (KL divergence の理論値どおり scratch では大きい)、
  gradient_clip_val=1.0 でクリップされ optimizer step は健全。 v7 と同様 数 epoch で収束見込み
- 収束後は `|logs_p| < 5` が普通なので clamp は no-op、 model の表現力を損なわない

**bucketing A/B の実測** (--precision 32-true / 40 batches / batch_size=32、 KL fix 後):

| run | 設定 | wall-clock | sec/step | Non-finite |
|---|---|---|---|---|
| A | bucketing OFF | 433 sec | 10.8 | 0 |
| B | bucketing ON | 538 sec | 13.5 (**+24% 遅い**) | 0 |
| C | ON + nsys profile | 350 sec / 20 batches | 17.5 (nsys overhead 込) | 0 |

**bucketing 効果測定は 40 batch サンプルサイズでは不確定**:

- Run B の初回 batch shape (phoneme_max=181, audio_max=180k) は Run A (339 / 293k) より小、
  epoch 全体の compute total は同等でも batch ごとの分散が異なる
- cudnn.benchmark が異なる shape ごとに kernel 再選択、 40 batch 初期は選択オーバーヘッドが
  支配的で **bucketing の padding 削減メリットが埋もれる**
- **数百 batch 以降** で cudnn.benchmark キャッシュが steady state に達し、 理論通り
  padding 削減が sec/step 改善として現れる想定
- 現時点で bucketing の default OFF を維持、 v8 本走で 1 epoch (200+ batches) 走らせて
  epoch 平均で判断する方針

**nsys GPU 内訳 (Run C、 20 batches、 backward 含む)**:

| カテゴリ | 割合 | 備考 |
|---|---|---|
| cudnn nchw↔nhwc 変換 | 12.8% (9.6% + 3.2%) | memory layout 不整合。 channels_last 移行で削減余地 |
| CUDA memcpy H2D | 5.4% | データローダ側の入力転送 |
| CUDA memcpy D2H | 5.3% | loss log / checkpoint 用 |
| cutlass wgrad TF32 | 4.2% | backward の conv 勾配 |
| sm80_xmma fprop TF32 | 3.9% | forward の conv (計 15%+) |
| elementwise | 5.2% (2.7% + 2.5%) | 標準的な非線形 / broadcast |
| その他 (cutlass 各種、 reduction) | ~63% | discriminator / decoder / STFT |

- memcpy 合計 10.7% は tmpfs preload / mmap で削減可能 (§3.3 未実装項目参照)
- **nchw↔nhwc 変換 12.8% は無視できない**、 v8 完走後の Plan B で `torch.channels_last`
  移行を検討する価値あり

### 3.5 300 batch A/B 再測定 + real config 実測 (2026-07-09 追試)

前 §3.4 の 40 batch A/B は warmup 支配で判断保留としていたが、 **300 batch まで延長** して
cudnn.benchmark を steady state に持ち込んだ再測定を実施。 同時に **real config
(bf16-mixed + SCL + DINO + bucketing、 batch=64)** の 100 batch 実行で v8 学習の実効
sec/step を確定。 全 700 batches (Test 1 + 2A + 2B) を通して **Non-finite skip 0 件** で
§3.4 の KL fix が real config でも完全動作することを実証。

**測定結果**:

| Test | 設定 | wall-clock | sec/step | Non-finite |
|---|---|---|---|---|
| **Test 1** | bf16-mixed + SCL + DINO + bucketing、 batch=64、 `--compile` OFF、 100 batches | 1399 sec | **14.0** | 0/100 |
| **Test 2A** | 32-true simplified (SCL/DINO off)、 bucketing OFF、 batch=32、 300 batches | 1545 sec | **5.15** | 0/300 |
| **Test 2B** | 32-true simplified、 bucketing ON、 batch=32、 300 batches | 2069 sec | **6.90** (+34%) | 0/300 |

**Test 2 A/B からの重要な発見**:

- **bucketing は steady state でも 34% 遅い**。 40 batch (§3.4) では warmup 支配と判断していたが、
  300 batch でも改善せず「実装上の real regression」と確定
- **メカニズム (推定)**: `SpeakerBalancedBatchSampler` の length-bucket は per-speaker で
  phoneme_length 昇順ソート → batch は epoch を通じて **shortest → longest** の順で
  取り出される。 Test 2B batch 0 の audio_max=180k、 batch 50 の audio_max=281k、
  batch 250+ の audio_max はさらに大。 batch ごとに **cudnn.benchmark が異なる shape の
  kernel を再選択** し、 選択オーバーヘッドが累積
- 加えて **長い batches (後半) の compute が集中** し、 GPU の warm state が
  batch 単位の shape 変動で崩れる
- **結論: `--enable-length-bucketing` は default OFF 継続、 v8 本走で使用しない**。
  Plan A の 4 施策のうち bucketing (施策 #3) は撤回、 残り 3 施策 (D concat / static_graph /
  compile 再チューン) は維持

**v8 本走 wall-clock 見積 (Test 1 を出発点に更新)**:

Test 1 の 14.0 sec/step (bf16-mixed real config、 batch=64、 `--compile` OFF、
bucketing 有害と判明) を基準に、 各要素を分離して見積もる:

| 適用要素 | sec/step 影響 | 累積 sec/step |
|---|---|---|
| Test 1 baseline (bucketing ON、 `--compile` OFF) | — | 14.0 |
| bucketing OFF (Test 2B の発見) | -30-40% | 9-10 |
| batch=64 → batch=128 (A100 SXM4 80GB) | -20-30% | 6-8 |
| `--compile=reduce-overhead` (torch.compile) | -10-15% | 5-7 |
| Super-MAS Triton (docker `[super-mas]`、 §3.2) | -3-10% | **5-6** |

**80 epoch 見積 (v8 dataset 321,391 utts / batch 128 = 2,511 batches/epoch)**:

| GPU 構成 | 1 epoch | 80 epoch | コスト ($1.73/hr storage 込) |
|---|---|---|---|
| A100 SXM4 × 1 (batch=128) | 5.4 hr | **18 日** | ~$747 |
| **A100 SXM4 × 4 (DDP、 static_graph)** ⭐ | **1.6 hr** | **5.4 日** | ~$672 ($5.19/hr × 129 hr) |
| H100 SXM 80GB × 2 (batch=128) | 1.7 hr | 5.7 日 | ~$598 |

**§3.3 の "Plan A 3.3-4.0 日" は達成不可を実測で確定**:
- 主因: bucketing が -30-40% ではなく +34% (逆効果)
- 単一 A100 で 18 日は現実的でない → **Plan B (4x A100 DDP) を v8 本走の推奨構成に更新**
- H100 x 2 は最安だが v7 で検証済みの 4x A100 DDP パスに比べて未検証項目 (H100 native BF16、
  Multi-scale FiLM 数値安定) が多く、 v8 では避けて Plan C (別 PR) で検討

**§3.1 学習コマンドの更新**:
- `--enable-length-bucketing` を **削除**
- `--no-compile-dynamic` も削除 (bucketing 前提だったため意味なし)
- multi-GPU (`--devices 4`) で `--precision bf16-mixed` を継続

### 3.6 immediate 5 施策 + KL 発散防止 (2026-07-09 追加ランディング)

§3.5 の Test 1 実測 (14.0 sec/step、 real config、 batch=64、 bf16-mixed、 bucketing ON、
`--compile` OFF) を出発点に、 「A100 GPU idle と host 側 I/O ボトルネックの解消」 に絞った
**immediate 5 施策** (T1 / T2 / T5 / P1 / P2) を feature branch にランディング済み。 加えて
300 batch smoke で batch 31 以降 100% (262/300) の Non-finite skip が判明 → **KL clamp を
tighten する追加修正** ([`1f625a4`](https://github.com/ayutaz/piper-plus/commit/1f625a42))、
length_bucket を per-batch 単一 bin 抽出に再設計する **Fix B**
([`a5fa6f2`](https://github.com/ayutaz/piper-plus/commit/a5fa6f2b)) も併せて投入。

| # | 分類 | commit | 変更 | 期待効果 |
|---|------|--------|------|--------|
| T2 | throughput (I/O) | [`3fba827`](https://github.com/ayutaz/piper-plus/commit/3fba8275) | `Batch` dataclass に `pin_memory()` を追加 (plain dataclass は DataLoader の `pin_memory=True` で silently no-op だった) + train DataLoader の `prefetch_factor` default 2→4 (`--prefetch-factor` CLI 化) + `on_validation_epoch_end` の `.to(device)` を `non_blocking=True` 化 | **wall-clock -5-15%** (v8 で観測済の 「見えない non_blocking 同期化」 を実効化) |
| T1 | throughput (kernel layout) | [`597f589`](https://github.com/ayutaz/piper-plus/commit/597f589c) | `MultiPeriodDiscriminator` + `DiscriminatorP` に `use_channels_last` opt-in、 CLI `--channels-last` default OFF。 Conv2d weight + 1D→2D view 直後の activation を `torch.channels_last` に統一 | **sec/step -16% 目標** (§3.4 nsys で判明した nchw↔nhwc 変換 12.8% + Conv2d 8% = 20.8% overhead の削減余地)。 実測 A/B 後に default 化判断 |
| T5 | throughput (attention) | [`25c3263`](https://github.com/ayutaz/piper-plus/commit/25c32636) | SDPA backend priority を明示制御 (`flash` / `mem_efficient` ON、 `math` OFF、 torch 2.11+ で `cudnn` ON)、 起動 log に有効 backend を出力 | Ada 6000 / RTX 5090 (sm_89 / sm_120) で naive math fallback を防止、 **long-sequence で 2x、 net +1-3%** |
| P1 | I/O (dataset load) | [`5102404`](https://github.com/ayutaz/piper-plus/commit/51024040) | `piper_train.tools.precompute_mel` を新設 (fp16 `.npy` を pre-materialise、 atomic replace)、 `PiperDataset` に `precomputed_mel_dir` opt-in、 CLI `--precomputed-mel` | `torch.load(.spec.pt)` の pickle 経路を numpy path (`np.load → torch.from_numpy`) に置換で **DataLoader step 2-3x**、 80 epoch で **8-12h の I/O 節約** |
| P2 | I/O (preprocess) | [`d5960b2`](https://github.com/ayutaz/piper-plus/commit/d5960b2a) | `norm_audio.default_num_processes()` を新設 (`min(cpu_count//2, 32)`)、 `cache_audio` / `prepare_multilingual_dataset` / `prepare_bilingual_dataset` の worker 数 default を統一 + tqdm 進捗バー追加 | 64 vCPU host で `cpu_count()` fan-out すると soxr/torch per-worker state と NFS IOPS で thrash (実効 throughput -30%)。 default 30 worker 相当に固定して **前処理 wall-clock 短縮 + 進捗可視化** |
| — | bucketing 再設計 (Fix B) | [`a5fa6f2`](https://github.com/ayutaz/piper-plus/commit/a5fa6f2b) | `SpeakerBalancedBatchSampler` の length_bucket を per-batch 単一 bin 抽出に変更 (4 quantile bin、 language_group_balance / samples_per_speaker=4 contract 保持) | §3.5 で `+34%` 逆効果だった実装を廃案 → バッチ間 shape 差を bin 幅に閉じ込め cudnn.benchmark cache を再利用可能に。 opt-in default OFF は継続、 v8 本走前に再 A/B |
| — | KL 発散防止 | [`1f625a4`](https://github.com/ayutaz/piper-plus/commit/1f625a42) | `logs_p` / `logs_q` clamp を `[-15,15]` → `[-8,8]`、 `m_p` clamp を `[-1000,1000]` → `[-100,100]`、 loss_kl 出力を `1e4` で cap (`SynthesizerTrn.forward` / `infer` / `lightning.py` 3 箇所) | §3.4 の scratch KL inf fix でも 300 batch smoke で batch 31 以降に 100% (262/300) Non-finite skip 再発 → worst case `(z_p-m_p)^2 * exp(-2*logs_p) = 4e17` が fp32 overflow していたため。 clamp 5 桁 down + 出力 cap で **grad direction 安定化**、 `kl_weight=0.1` と `grad_clip=1.0` と多層防御。 収束後は `|logs_p| < 5` で cap は no-op、 表現力を損なわない |

**累積効果 (Test 1 14.0 sec/step 起点で分解、 batch=64 real config)**:

| 適用要素 | sec/step 影響 | 累積 sec/step |
|---|---|---|
| Test 1 baseline (bucketing ON、 `--compile` OFF、 bf16-mixed、 batch=64) | — | 14.0 |
| T2 pin_memory + prefetch=4 (H2D pipeline を実効化) | -5-15% | 12.0-13.3 |
| P1 precomputed_mel (DataLoader I/O を numpy path 化) | -10-15% | 10.4-12.0 |
| bucketing OFF (§3.5 の「+34% 逆効果」 実装を切って通常経路に戻す) | -20-25% | 8-9.6 |
| T5 SDPA flash/mem_efficient (naive math fallback を防止) | -1-3% | **8-9 (目標)** |
| T1 channels_last (opt-in、 A/B 後に default 化検討) | -10-16% | 7-8 (upside) |
| Fix B length-binned global sampling (再 A/B で amortize) | -10-20% | 6.5-8 (upside) |

**immediate 5 施策 の v8 本走目標**: Test 1 の 14.0 sec/step から **8-9 sec/step** への短縮
(-36-43%)。 T1 / Fix B が A/B で有効と判れば **6.5-8 sec/step** (-46-54%) の upside。
これに batch=64 → 128 (-20-30%) + `--compile` (-10-15%) + Super-MAS (-3-10%) の
§3.5 系列を重ねると、 A100 SXM4 x1 batch=128 で §3.5 と同じ **5-6 sec/step** に着地する
見込み (§4.3 コスト表参照)。

**KL 発散防止は wall-clock ではなく「学習継続そのものの成立条件」** で、 これがないと
scratch 初期化の v8 本走は 100% batch skip で epoch が進まず、 §3.5 で観測した 262/300
非有限 skip がそのまま 5-6 日級の running cost を焼失させる。 immediate 5 施策 と同じ
PR で必須で入れる。

| 項目 | 値 |
|---|---|
| 推奨インスタンス | **A100 SXM4 80GB × 1、32 vCPU、disk ≥ 1.7TB、回線 ≥ 7Gbps** (~$1.0–1.3/hr) |
| 代替 (安価) | RTX 5090 32GB (~$0.44/hr、batch ~48、wall-clock ~2倍) |
| 代替 (高速) | H100 SXM 80GB (~$2.2/hr、~2倍速) |
| disk 内訳 | 生データ ~550GB (moe-plus zips ~350GB 含) + audio cache ~350GB + ckpt (947MB × 80) + margin → **≥ 1.5TB** |
| epoch 時間見込み | baseline (P0 のみ) ~1.5–1.7h/ep / **Plan A 反映後 (§3.3) ~1.0–1.2h/ep** (340k 発話、A100 80GB。v7 実績 V100×4 8h53m/500k から換算) |

単一 GPU 構成とし、v7 で「CUDA illegal access」偽装の真因だった DDP/NCCL 系障害
(rank 間 NaN skip 不整合 → all_reduce mismatch → 30 分 timeout) のクラスを丸ごと回避する。

### 3.7 全 smoke test 完了 + 最終見積 (2026-07-09 セッション終了時点)

**smoke test マトリクス** — 全 300 batches、 bf16-mixed + SCL + DINO + real config、 batch=64:

| Test | 追加設定 | wall-clock | avg sec/step | Non-finite | 判定 |
|---|---|---|---|---|---|
| smoke1 | KL v1 (loose clamp)、 no 5 施策 | 3294 sec | 10.98 | 262/300 (87%) | 発散、 skip 支配で参考値 |
| **smoke2** | 5 施策 + KL v2 (tight clamp + cap) | **3221 sec** | **10.74** | **6/300 (2%)** | ✅ v8 本走 config 確定 |
| smoke3a | 上記 + `--compile` reduce-overhead | 198 sec で crash | — | — | ❌ torch inductor+triton 不動作 |
| smoke3b | 上記 + `--precomputed-mel` (no `--compile`) | 3439 sec | 11.46 | 6/300 (2%) | ❌ GPU-bound で -6.5% 遅い |

**Test 1 (§3.5、 KL v1 with bucketing ON、 100 batches) との比較**:
- Test 1: 14.0 sec/step (100% successful)
- smoke2: 10.74 sec/step (98% successful)
- **→ 実効 -23% throughput improvement**

**判明したこと**:

1. **v8 学習の必須ブロッカー解消** (最大の成果):
   - bf16 cuFFT bug (3dcabd57): mel STFT を bf16→fp32 defensive upcast
   - KL scratch 発散 (1a86aa55 + 563f8361 + 1f625a42): logs_p/m_p clamp と loss_kl cap の 3 段防御
   - **Non-finite skip 率: 100% → 2%** (v7 baseline 2.5% と同等)
2. **有効な 5 施策**:
   - T2 (Batch.pin_memory silent no-op 修正 + prefetch_factor=4): 最大寄与、 non_blocking H2D 実効化
   - T5 (SDPA backend 明示、 flash=True): 動作確認、 現状 attention 実装は SDPA 未使用のため将来投資
   - T1 (channels_last、 opt-in): Discriminator Conv2d のみ、 副作用ゼロ
   - P1 (precompute_mel tool): 321k utts を **85 秒** で完了、 前処理再現時のみメリット
   - P2 (VAD 並列化): preprocessing 側の runbook 化
3. **不採用が確定した施策**:
   - `--compile`: torch 2.11 + triton の kernel compile crash、 v8 では使わない
   - `--precomputed-mel`: 学習は GPU-bound、 .npy load overhead で +6.5% 遅い
   - `--enable-length-bucketing`: §3.5 で確認済 +34% 逆効果、 Fix B (`a5fa6f2b`) 未再検証
4. **設計予測との乖離**:
   - §3.3 Plan A 予測: "3.3-4.0 日 / 単一 A100"
   - 実測ベース現実値: **51 日 / 単一 A100** (Plan A 想定の 15 倍)、 **9-11 日 / 4x A100 DDP** (Plan A 想定の 3 倍)
   - Plan A の予測が過大だった主因: bucketing 効果 -30-40% が実際は +34% 逆効果、 `--compile` +10-25% が使えず

**batch size 探索実測 (2026-07-09 追加、 A100 SXM4 80GB × 1、 15 batches per size)**:

| batch | VRAM peak | avg sec/step (startup 込) | 推定 utts/sec | 判定 |
|---|---|---|---|---|
| 64 (smoke2 baseline) | ~40GB (50%) | 10.74 (300 batches 平均) | **5.96** | ✅ **最高 throughput** |
| 128 (中断) | 41.5GB (52%) | — | — | 動作確認のみ |
| 192 | 63GB (78%) | 43.06 | ~5.82 | ✅ VRAM 余裕 |
| 224 | **73GB (91.6%)** | 53.46 | ~5.15 | ⚠️ ギリギリ、 throughput 悪化 |
| **256** | — | crash | — | ❌ **OOM (segfault)** |

**意外な発見**: **batch を上げても utt/sec は改善せず** (むしろ悪化)。
- batch=64 が最高 5.96 utts/sec、 batch=224 は 5.15 utts/sec (-14%)
- 原因推測: attention の O(T²) スケール、 padding waste、 memory allocator 負荷、 cache pressure
- **VITS + zero-shot 学習は compute-bound、 batch を上げても forward/backward per-utt が増える**

**DDP スケーリングでは effective batch=128 (32/GPU × 4) が最適** — 単一 GPU での utt throughput 最良点を維持しつつ、 DDP で並列化。 batch=48/GPU × 4 (eff 192) も VRAM 余裕 (~15GB/GPU) だが utt throughput ロス見込み。

**v8 本走 wall-clock (実測ベース最終見積、 batch=32/GPU × 4x DDP 想定)**:

| 構成 | epoch 時間 | 80 epoch | コスト ($1.73/hr storage 込) |
|---|---|---|---|
| 単一 A100 SXM4 (batch=128) | 8-9 hr | 27-30 日 | ~$1,120 |
| **4x A100 SXM4 DDP + batch=128** ⭐ | **2.5-3 hr** | **9-11 日** | **~$1,120** ($5.19/hr × 240 hr) |
| 8x A100 SXM4 DDP + batch=192 | 1.5-2 hr | 5-6 日 | ~$1,600 |
| H100 SXM 80GB × 2 (未検証) | 1.7 hr | 5.7 日 | ~$600-700 |

> **2026-08-02 注記**: 上表のレート ($1.73/hr / $5.19/hr) は 2026-07 時点の市場価格で失効
> (§4.1 の 2026-08-02 市場注記参照)。現行の承認済み構成は **4x A100 SXM4 40GB $3.43/hr
> (storage 込)** で、本走見積は **7-9 日 / ~$600-750** (§4.3 の 2026-08-02 更新参照。§3.8 の
> 7-8 sec/step 達成前提、smoke2 実測 10.74 sec/step のままなら +30%)。

**v8 本走 CLI (実測反映最終版)**:

```bash
python -m piper_train \
  --dataset-dir /data/piper/dataset-multilingual-6lang-v8 \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision bf16-mixed \
  --max_epochs 80 --batch-size 32 --samples-per-speaker 4 \
  --checkpoint-epochs 2 --save-top-k 5 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 8 --prefetch-factor 4 --no-wavlm \
  --max-phoneme-ids 400 \
  --spk-emb-noise-sigma 0.05 --d-update-interval 1 \
  --lr-scheduler cosine --lr-warmup-epochs 5 --lr-min 1e-5 \
  --kl-annealing-epochs 10 \
  --c-dino 0.5 --c-spk 1.0 --c-sub-stft 1.0 \
  --gradient-clip-val 1.0 \
  --speaker-encoder-path /data/piper/models/campplus.onnx \
  --val-every-n-epochs 5 --audio-log-epochs 5 \
  --language-balanced-sampling \
  --channels-last \
  --default_root_dir /data/piper/output-zero-shot-multi-6lang-v8
# 除外フラグ (実測で不採用):
#   --compile           # torch inductor+triton crash
#   --precomputed-mel   # GPU-bound で効果なし
#   --enable-length-bucketing  # +34% 逆効果 (Fix B 未再検証)
```

> **2026-08-02 注記 (CLI 読み替え — 本走 launch 前に必読)**: 上の CLI は 6-lang
> スナップショット (`dataset-multilingual-6lang-v8`) 時点の記録。実際の本走 (ko 込み
> 7-lang、KsponSpeech 除外) では以下を読み替える:
>
> 1. `--dataset-dir` は 7-lang データセット構築後の
>    **`/data/piper/dataset-multilingual-7lang-v8/`** に読み替え
>    (`prepare_multilingual_dataset.py` に `--ko-zeroth` / `--ko-cv` を追加して構築、
>    config.json の dataset label は `multilingual-7lang` に自動切替 — §6.5)。
>    `--default_root_dir` と HF ckpt 退避 repo は作成済みの `multi-6lang-v8` 名を維持 (§4.4)
> 2. インスタンス/レートは §4.1 / §4.3 の 2026-08-02 注記の承認済み構成
>    **4x A100 SXM4 40GB $3.43/hr (本走 7-9 日 / ~$600-750)** に読み替え。
>    batch=32/GPU の VRAM は 40GB で未検証のため smoke を VRAM gate とし、
>    溢れたら `--batch-size 24` に下げるか 80GB ($7.68/hr) に乗換 (§3.8 の自動 go 基準)

### 3.8 残 findings 実装完了 (2026-07-09 追加ランディング)

§3.7 で v8 本走 config を確定した後、 review で未実装だった findings のうち
コード側で完遂できる 8 施策を追加実装 (commits `e12d0be8` / `fc59900c` /
`c0e4e0e3` / `7657a93c` / `e17d1f8e` / `cc7c20a6` / `3ced31a8` / `acdcca36`)。
GPU smoke test は次セッション (vast.ai instance destroy 済のため) で回すが、
各施策の期待効果は個別の bench / 契約テストで pin 済。

**学習経路 (5 施策)**:

| commit | 施策 | 内容 | 期待効果 |
|---|---|---|---|
| `c0e4e0e3` | **T3 SDPA fast path** | TextEncoder self-attention を `F.scaled_dot_product_attention` に切替 (opt-in `--attn-drop-rel-v`)。 relative-V 補正は drop、 v8 scratch 前提で許容 | **+2-5% throughput**、 activation memory **-60MB/batch** (A100 SXM4 real config) |
| `7657a93c` | **T6 hybrid precision** | `--disc-precision {inherit,bf16-mixed,32-true}` で D forward を bf16 に切替つつ SCL/DINO は fp32 維持 (belt-and-suspenders wrap) | **+5-10% throughput** (D forward が dominant conv workload、 A100 SXM4) |
| `fc59900c` | T1-ext channels_last MBiSTFT | Generator にも channels_last hparam を propagate (Conv1d のため実効 no-op、 対称性 + 将来 Conv2d 追加時の future-proofing) | 現時点 0%、 将来 Generator に Conv2d を追加した際に自動有効化 |
| `e17d1f8e` | **T-empty 除去** | training_step の 500-batch `torch.cuda.synchronize()` + `empty_cache()` flush を除去 (T4/V100 遺物、 A100 80GB + `expandable_segments:True` で不要) | **+2-3% throughput** (500 batch 毎の GPU 全停止除去) |
| `e12d0be8` | **T-npy audio_norm cache** | audio_norm cache を `.pt` (pickle) から `.npy` (raw numpy) に切替 (write 側のみ、 backward-compat 3 段リゾルバで既存 `.pt` は温存) | **+5-10% throughput** (DataLoader load 3-5x 高速化)、 disk usage **-10%** |

**前処理経路 (3 施策)**:

| commit | 施策 | 内容 | 期待効果 |
|---|---|---|---|
| `acdcca36` | **P3 zip parallel** | `prepare_moe_speech_plus.py` の 473 zip 展開を `multiprocessing.Pool(spawn)` で並列化 (opt-in `--parallel`、 `pool.imap(chunksize=1)` で順序 preserve、 serial と byte-for-byte 一致) | **30-45 分 → 3-5 分** (~12-16x、 32 vCPU) |
| `3ced31a8` | **P4 per-zip cache** | per-zip pre-filter 生 metadata を `_scan_cache/{zip_stem}.jsonl` に落とし、 `(zip_size, zip_mtime_ns)` で自動 invalidate。 `--min-mos` / `--max-cer` / `--cap` スイープを高速化 | 初回 3-4h → warm 再実行 **5 分スケール** |
| `cc7c20a6` | **P5 CAM++ default 化** | `extract_speaker_embedding.py` の fixed_frames=400 + chunked mean pooling + chunk_batch=128 を default 化 (旧 env var `PIPER_EMB_FIXED_FRAMES` 経由から CLI arg に昇格) | 500k utts で **9h → 45-60 分** (9-12x)、 v8 (~1M utts) では **18h → 90-120 分** |

**予測 wall-clock 更新** (5 学習経路施策の累積、 前処理は独立):

現行 baseline (§3.7 smoke2): **10.74 sec/step** @ A100 SXM4 batch=64

| 累積施策 | 期待 sec/step | 単一 A100 (80 epoch) | 4x A100 DDP (80 epoch) |
|---|---|---|---|
| §3.7 smoke2 (5 施策 + KL v2、 base) | 10.74 | 51 日 | 9-11 日 |
| + T-empty (+2-3%) | 10.4-10.5 | 49-50 日 | 8-10 日 |
| + T-npy (+5-10%) | 9.5-10.0 | 44-48 日 | 8-9 日 |
| + T3 SDPA (+2-5%) | 9.0-9.7 | 43-46 日 | 7-9 日 |
| **+ T6 hybrid precision (+5-10%)** | **8.1-9.2** | **38-44 日** | **6-8 日** |

**保守寄りの累積予測**: 現行 10.74 → **7-8 sec/step** (合算 +25-40% throughput、
掛算ではなく overlap するため保守側で見積)。

- **単一 A100 SXM4 80GB**: **51 日 → 30-38 日** (最良で 30 日)
- **4x A100 SXM4 DDP (batch=32/GPU × 4)**: **9-11 日 → 6-8 日** (最良で 6 日)
- **8x A100 SXM4 DDP or H100 SXM 80GB × 2**: 5-6 日 → **4-5 日**

**前処理 wall-clock 更新** (P3/P4/P5 累積、 v8 dataset 再構築時):

- moe-speech-plus prep: 30-45 分 → 3-5 分 (P3)、 スイープ再実行 3-4h → 5 分 (P4)
- CAM++ 抽出: 18h → 90-120 分 (P5)
- **全体**: §3.6 の 8-10h 見込 → **2-4h** に短縮 (moe-speech-plus + CAM++ が支配的)

**保守側 caveat**:

- T3 SDPA は attention 実装が SDPA 未使用の TextEncoder self-attention 部にのみ効く。
  full Generator/Decoder 経路への効果は次 nsys で確認。 activation memory -60MB は
  larger batch (128+) 化の余地に相当するが、 §3.7 で確認済 batch=64 が compute-bound
  最適点のため throughput 直接寄与は控えめ
- T6 hybrid precision は `--precision 32-true` 環境で最大効果 (D forward fp32 → bf16
  で -5-10%)。 現在の v8 本走 CLI は `--precision bf16-mixed` のため D forward は
  既に bf16、 追加効果は SCL/DINO が明示 fp32 wrap されて数値安定性が保証される点
  (belt-and-suspenders)。 32-true 併用時に本領発揮
- T-npy は既存 `.pt` cache 温存のため、 v8 dataset 再構築時に初めて効く
  (backward-compat: 既存 `.pt` は再処理せず read、 新規は `.npy`)

**GPU smoke test (次セッション)**:

vast.ai instance が destroy 済 (§3.7 直後) のため、 GPU 上の A/B 実測は次セッション。
smoke test 計画:

1. smoke2 baseline を rerun (10.74 sec/step 再現確認)
2. `--attn-drop-rel-v` + `--disc-precision bf16-mixed` を on にして 300 batch
3. audio_norm cache を `.npy` で pre-materialise (`ignore_cache=True` を短時間走らせる) → DataLoader load 時間の A/B
4. 合算で予測 7-8 sec/step 達成を確認、 未達なら nsys で bottleneck 再検証

**smoke 自動 go 基準 (2026-08-02 ユーザー承認)** — 4x A100 SXM4 40GB (§4.1) 上の smoke で
以下 3 条件を全て満たしたら、**報告を待たずに本走を launch** する運用:

1. **sec/step ≤ 8.5**
2. **Non-finite skip 率 ≤ 3%**
3. **VRAM が 40GB に収まる** — batch=32/GPU は 40GB で未検証のため smoke を VRAM gate とし、
   溢れたら batch=24 に下げるか 80GB 構成 ($7.68/hr、§4.1 の 2026-08-02 市場注記) に乗換

CI 側は 40+ 新規テスト (test_sdpa_attention / test_hybrid_precision /
test_no_empty_cache_flush / test_audio_norm_npy / test_channels_last 拡張 /
test_moe_speech_parallel / test_moe_speech_cache / test_extract_speaker_embedding)
で契約は pin 済、 backward-compat は byte-for-byte 一致テストで保証。

### 4.1 インスタンス選定基準 (長期稼働の安定性)

7 日級の連続稼働のため、価格最優先ではなく以下で絞り込む:

| 基準 | 閾値 | 理由 |
|---|---|---|
| `verified=true` | 必須 | vast 検証済みホスト |
| `reliability2` | > 0.995 | ホスト稼働実績 |
| **`duration`** | **≥ 21 日** | ホストの掲載継続コミット。9 日などは 7 日学習に対し危険 |
| 契約種別 | **on-demand** | interruptible (bid) は他ユーザーに横取りされ pause するため不可 |
| disk | ≥ 1.5TB | §4 冒頭の内訳 + margin |
| 上り回線 | ≥ 3Gbps | epoch ごとの ckpt HF upload + ~400GB B2 退避の所要時間に直結 |

2026-07-07 時点の検索では上記を満たす筆頭候補は
`A100 SXM4 / $1.281/hr / disk 2,878GB / reliability 0.9993 / duration 24日 / 上り 6.7Gbps` (US)。
**オファーは流動的なため、rent 時点で同条件で再検索して最良を取る。**

> **2026-08-02 市場注記 + 決定**: A100 **80GB** 系は **$7.68/hr に高騰** し、2026-07 時点の
> "$5.19/hr (4x 80GB)" 前提の見積は失効。**4x A100 SXM4 40GB $3.43/hr (storage 1.7TB 込) を
> 承認済み** — 2026-08-02 時点の筆頭 offer id=44347432 (Slovenia、128 vCPU、disk 1874GB、
> 上下 4.3-4.5Gbps、reliability 99.52%、duration 161 日)。オファーは流動的のためレンタル時に
> 再検索する。batch=32/GPU の VRAM は 40GB で未検証 → **smoke test を VRAM gate** とし、
> 溢れたら batch=24 に下げるか 80GB ($7.68/hr) に乗換 (§3.8 の smoke 自動 go 基準参照)。

### 4.2 課金モデル (on-demand)

- **秒単位の従量課金、最低契約期間なし**。rent → destroy まで秒割り、いつでも破棄可
- コストは 3 ストリーム: ① GPU 稼働 (running 中のみ) ② ストレージ (確保 GB、**stop 中も課金**)
  ③ 帯域 (ホストごとの GB 単価)
- `duration` はホスト側の提供コミットであり、renter 側の縛りではない
- prepay (reserved 化) は 1 か月分前払いで 20% 等の割引だが、7 日利用では前払い額 (~$920) に
  対し旨味がなく**不採用**。素の on-demand とする

### 4.3 フェーズとコスト見積り

実質レートは **GPU 単価 + ストレージ課金** で構成される (2026-07-07 筆頭候補 id=41832908:
GPU $1.313/hr + disk 1.5TB × $0.20/GB/月 = +$0.417/hr → **$1.73/hr**)。帯域課金は
DL 600GB + UL 500GB で ~$4 と無視できる。

**§3.5 (300 batch A/B 実測) + §3.6 (immediate 5 施策) 反映後の見込み**:
- **前処理**: P2 (`cache_audio` / `prepare_multilingual_dataset` の worker default 統一) + P1
  (precomputed_mel の pre-run 追加) で **~32h → ~8-10h** に短縮 (soxr/torch worker thrash
  解消 + mel を fp16 `.npy` に pre-materialise、 §3.6)
- **本走 sec/step**: Test 1 baseline 14.0 (batch=64 real config) → immediate 5 施策で
  **8-9 sec/step 目標** (§3.6 累積効果表)。 batch=64 → 128 + `--compile` + Super-MAS を
  重ねて A100 SXM4 x1 batch=128 では **5-6 sec/step / ~5.4 hr/ep** (§3.5)、
  A100 SXM4 x4 DDP + static_graph で **~1.6 hr/ep** (§3.5)

| フェーズ | 時間 | コスト ($1.73/hr、storage 込) |
|---|---|---|
| DL + 前処理 + embedding 抽出 (CV pt フィルタ含む) | **~8-10h** (P2+P1、 従来 ~32h から短縮) | **~$14-17** |
| smoke test (warm-start 1ep + 評価、 KL fix 込) | ~2h | ~$4 |
| 本走 80 epoch (A100 SXM4 x1 batch=128、 **~5.4 hr/ep、 §3.5**) | **~18 日** | **~$747** |
| 本走 80 epoch (**A100 SXM4 x4 DDP、 static_graph、 ~1.6 hr/ep、 §3.5 推奨**) | **~5.4 日** | **~$672** ($5.19/hr × 129h) |
| SECS 評価 + ONNX export + HF upload | ~4h | ~$7 |
| **計 (v8 想定、 4x DDP)** | **~6-7 日** | **~$700-720 (中央値 ~$710)** |
| 参考: 単一 A100 (batch=128)、 §3.6 未反映 (Test 1 14 sec/step のまま) | ~40+ 日 | ~$1,650+ |

> **2026-08-02 更新**: 上表のレート ($1.73/hr / $5.19/hr) は 2026-07 時点の市場価格で失効
> (§4.1 の 2026-08-02 市場注記参照)。承認済み構成 **4x A100 SXM4 40GB $3.43/hr (storage 込)**
> での現行見積は **本走 7-9 日 / ~$600-750** (§3.8 の 7-8 sec/step 達成前提。smoke2 実測
> 10.74 sec/step のままなら +30%)。KsponSpeech 除外 (§6.5 冒頭) 後の 7-lang は発話 ~346k で
> 6-lang 比 +8% に留まるため、6-lang 前提の本走時間見積とほぼ同水準に収まる。

### 4.4 障害耐性 (多層防御)

インスタンス安定性 (§4.1) に頼り切らず、ホスト消失を前提に損失を限定する:

| 層 | 対策 | 最悪ケースの損失 |
|---|---|---|
| 1 | on-demand 契約 (横取りなし) | — |
| 2 | `--checkpoint-epochs 1` + **epoch ごと HF private upload** (`ayousanz/piper-plus-zero-shot-multi-6lang-v8`、repo は作成済 2026-08-02。自動 upload script は未作成 → §4.5 残 TODO) | 1 epoch ≈ 2.5h ≈ $3 |
| 3 | onstart 自動レジューム: 起動時に HF から最新 ckpt を取得し `--resume_from_checkpoint` で継続 (piper_train 側は対応済み。onstart script 自体は未作成 → §4.5 残 TODO) | 復旧の手作業ゼロ化 |
| 4 | 前処理完了時点で処理済みデータ (~400GB tarball) を `vastai cloud copy` で **Backblaze B2 へ退避** ($6/TB/月) | 再前処理 ~1 日 (~$30) をスキップし別マシンで即再開 |

ストレージに関する制約 (2026-07-07 調査):

- **Network Volume はオファー 0 件で実質未提供** (CLI コマンドは存在)。マシンをまたぐ
  ネットワークディスクは当てにできない
- Local Volume は同一物理ホスト縛り + $0.13-0.40/GB/月と割高なため不採用
- 一時中断は destroy ではなく **stop** (同一マシンにデータ残存、ストレージ課金のみ。
  ただし stop 中に GPU を他ユーザーが借りると再開待ちになる)

### 4.5 運用上の注意 / 開始条件

- HF token はインスタンス env (`HF_TOKEN`) のみに置き、リポジトリ・ログに残さない
  (B2 退避を使う場合は B2 アプリケーションキーも同様)
- **開始ブロッカー: 解消済み (2026-08-02)** — HF token (gated moe-speech-plus read /
  private repo write) は検証済、WANDB キーも検証済。ckpt 退避 repo
  `ayousanz/piper-plus-zero-shot-multi-6lang-v8` (private) も作成済み
- vast.ai API キーはローカル `~/.config/vastai/vast_api_key` に設定済み
  (残高 $2,483.52、2026-08-02 時点。2026-07-07 時点は $1,351)
- **残 TODO (本走前)**:
  1. onstart 自動レジューム script (起動時に HF から最新 ckpt 取得 →
     `--resume_from_checkpoint`) — 未作成 (§4.4 層 3)
  2. HF への epoch ごと ckpt 自動 upload script — 未作成 (§4.4 層 2)
  3. ko データパイプラインは実データ未検証 (synthetic unit test のみ) →
     instance 上で小規模先行検証してから全量前処理に進む

### 3.9 T3/T6 検証 smoke A/B/C on synthetic data (2026-07-09 追試、 destroy 済 instance)

§3.8 の T3 (SDPA + relative-K) と T6 (Discriminator hybrid precision) の実装
correctness と performance 効果を測定するため、 vast.ai A100 SXM4 80GB (別 host、
$1.07/hr、 driver 595) を 2 時間 rent (~$7.35 消費) して synthetic dataset (2,000 utts /
100 speakers、 phoneme_max=80、 audio 2-5s、 fake CAM++ embedding) で smoke A/B/C を実施。

**修正した bug 2 件** (実装時に見逃していた回帰、 commit [`d6fc36a5`](https://github.com/ayutaz/piper-plus/commit/d6fc36a5)):

1. **`losses.py:240` の `mel_speaker_consistency_loss._to_mel` の STFT が bf16 で cuFFT crash**:
   `mel_processing.py` (commit 3dcabd57) と同型だが別 site、 defensive fp32 upcast を追加。
   SCL mel-domain fallback 経路で `--precision bf16-mixed + --c-spk 1.0` の組み合わせで
   torch.stft が呼ばれ、 wav の dtype が bf16 のまま cuFFT に渡されていた。
2. **T5 (25c32636) の `enable_math_sdp(False)` が T3 SDPA fast path を crash させる**:
   `--attn-drop-rel-v` で SDPA を呼ぶが、 additive rel-K bias attn_mask が flash/mem-efficient
   の path から fallback → math backend が呼ばれるが disabled で「Invalid backend」で crash。
   `enable_math_sdp(True)` に戻し、 priority は依然 flash/mem-efficient が先。

**smoke A/B/C 実測 (synthetic data、 100 batches each、 batch=64、 bf16-mixed real config)**:

| Config | 内容 | wall-clock | sec/step | Non-finite |
|---|---|---|---|---|
| A | baseline (no T3, no T6) | 101 sec | 1.01 | 0/100 |
| B | + T6 (`--disc-precision bf16-mixed`) | 108 sec | 1.08 (**+7%**) | 0/100 |
| C | + T6 + T3 (`--attn-drop-rel-v`) | 108 sec | 1.08 (**+7% vs A**) | 0/100 |

**解釈** (synthetic data の限界):

- **T3/T6 の実装は正しい** (crash なし、 Non-finite 0、 数値安定)
- 一方で **synthetic では T6/T3 が逆効果** (+7% slow) → **synthetic data の scale が実 v8 と異なる** ため実効測定にならなかった:
  1. sec/step の 80-90% が固定オーバーヘッド (Lightning init / EMA update / logging)
  2. phoneme_max=80 (real v8 は 100-400) → attention は O(T²)、 synthetic では SDPA 効果が exposure しない
  3. audio 2-5s (real は より長い) → Discriminator forward が小さく T6 の autocast context switch overhead が benefit を上回る
  4. 総じて 「synthetic では実効的な D forward + attention 部分が sec/step の 5-10% にすぎず、
     T3/T6 の +5-10% は net 0.25-1% で ノイズに埋もれる」

**結論**:

- T3/T6 の **quantitative speedup は real v8 data (T~200 attention、 5s audio × batch=64) でしか測定不能**
- 来月本走の 4x A100 DDP smoke2 相当 baseline (10.74 sec/step) を rerun して +5-10% 想定効果を実測する
- 現段階では **§3.8 の "T3/T6 で 30-38 日 → …"予測は synthetic では confirm できず、 保守寄りで確認は本走 smoke に委ねる**
- **implementation は動作、 crash なし、 数値安定** — 本走で有効化する準備は完了

### 3.10 v8 に韓国語 (ko) 追加 — 追加コスト見積 (2026-07-09)

> **⚠️ 2026-08-02 注記**: KsponSpeech は v8 から除外確定 (§6.5 冒頭の決定参照)。本節の
> kspon 前提の数値 (話者 ~5,100 / 発話 ~420k / 本走 12-15 日 / 増分 +$380-410 /
> research-only 配布制限 / AI-Hub 入手ルート) は **無効**。現行の確定見積は
> **4x A100 SXM4 40GB $3.43/hr で本走 7-9 日 / ~$600-750** (§4.1 / §4.3 の 2026-08-02
> 注記参照、§3.8 の 7-8 sec/step 達成前提)。以下は 7-lang 化を判断した当時の歴史記録。

§2.4 (フィルタ) / §6.5 (data pipeline 実装) の ko 拡張を **同一 v8 run に載せた場合の
インクリメンタルコスト**。 G2P / language-id contract / phoneme inventory は全て 8-lang
extended form で pin 済のため、 追加コストは data pipeline 実行 + 訓練時間の増分のみ。

**データ規模の増分** (§2 表と同期):

| 項目 | v8 (6-lang) | v8 + ko (7-lang) | 増分 |
|---|---|---|---|
| 話者数 | 3,578 | **~5,100** | **+~1,522 (+43%)** |
| 発話数 | 321,391 | **~420,000** | **+~99k (+31%)** |
| 追加 audio (soxr resample 後) | — | +~150-180 GB | ETRI PCM→WAV 変換 (~5-10GB) + Zeroth (~10GB) + CV ko (~2GB) |
| 追加 CAM++ embedding (192-dim npy) | — | +~76 MB | 99k × 768 B |

**時間・費用の増分** (§4.3 のフェーズ表を 7-lang case で展開):

| フェーズ | v8 (6-lang) | v8 + ko (7-lang) | 増分理由 |
|---|---|---|---|
| DL + 前処理 (P2 並列 VAD + P4 zip cache 込) | ~8-10h | **~12-16h** | ETRI PCM→WAV (~3-4h、 事前 batch) + KsponSpeech parse (~2h) + Zeroth + CV ko (~1h) |
| CAM++ 抽出 (P5 default 化後) | ~30 min | ~45 min | +99k utts × ~1M ops/utt |
| smoke test (warm-start 1ep + 評価) | ~2h | ~2.5h | +15% batch/epoch |
| **本走 80 epoch (4x A100 SXM4 DDP)** | **9-11 日** | **12-15 日** | 発話 +31% でほぼ線形 (batch/epoch ~3,300 → ~4,320) |
| SECS 評価 + ONNX export + HF upload | ~4h | ~5h | ko 未知話者評価セット新設 (§5) を追加 |
| **計 (v8 想定、 4x A100 SXM4 DDP、 $5.19/hr storage 込)** | **~9-11 日 / ~$672-1,120** | **~12-15 日 / ~$1,050-1,530** | **+3-4 日 / +~$380-410** |

**インスタンス選定への影響 (§4.1)**:

- disk: 1.5TB → **1.7-1.8TB** に増設 (raw ETRI PCM + Zeroth + CV ko の追加ソース分)
- duration: **≥ 25 日** に引き上げ (7-lang 本走 12-15 日 + 前処理 12-16h + 復旧 margin)
- 回線: 変更なし (≥ 3Gbps で ko 追加分 ~180GB のダウンロードも十分カバー)

**予算判断のマイルストーン**:

- 現状のユーザー予算 (v8 6-lang $672-1,120) から **+$400 前後** で 7-lang 化。
  v9 gol-dataset 拡張 ($1,500+ 想定) より低コストで話者多様性 +43% を得られる
- ko 追加のリスク: KsponSpeech は AI-Hub consent (**商用非公開**) のため、
  v8 モデル自体を **research use only** で HF private repo に限定して配布
  (Zeroth CC BY 4.0 + CV ko CC0 のみでの 7-lang 版は将来的に検討可)
- SECS 目標 (§5): ja 参照 zero-shot ≥ 0.72 に加えて **ko 参照 zero-shot ≥ 0.65**
  (話者数 ~1,700 は VCTK 級で、 en 参照ほどではないが zh 参照相当を期待)

**開始条件** (§4.5 追加):

- HF token: 変更なし (gated moe-speech-plus の read/write のみ)
- **KsponSpeech の入手ルート**: AI-Hub アカウント + ETRI consent 承認 (~1-2 週間)。
  raw PCM zip をローカル DL → ETRI 提供の PCM→WAV script (Python or C) で 16kHz WAV 化
  → vast.ai instance に rsync (~10GB、 20-30 分)
- Zeroth-Korean: openslr.org/40 の tar.gz を直 wget (認証不要)
- CV ko: `export_common_voice_ko.py` + UTMOS tsv 作成 (~30 分)

### 3.11 前処理高速化 4 施策実装完了 (2026-07-09 追加ランディング)

> **2026-08-02 注記**: 本節の 7-lang 規模 (~420k utts / ~5,100 spk) と impl2 (KsponSpeech
> `.pcm` 直読) の ko 分短縮効果は KsponSpeech 除外 (§6.5 冒頭) 前の前提。現行の 7-lang は
> **~346k utts / ~3,790 spk** (§2) で kspon 分の前処理がそのまま消えるため、下表の
> 「7-lang 計 7-10h」は上限側の歴史値 (実際は 6-lang 計 6-9h に Zeroth + CV ko ~1h 加算程度)。
> impl1/impl3/impl4 は kspon 非依存で現行も有効。

§3.10 で 7-lang 化 (~420k utts / ~5,100 spk) を確定した後、 前処理 wall-clock が
「12-18h (旧見積) / 10-14h (hf_transfer 単独反映)」で本走 launch までの待ち時間が
本走コスト (12-15 日) に対して非線形に痛かったため、 **GPU 検証不要 (backend swap /
CPU 読み方 / IO 経路の再設計のみ) の低リスク 4 施策** を feature branch にランディング。
GPU resample 施策 (#3) は SNR / 22.05kHz 帯域維持の GPU 検証が必要なため今回 deferred。

| # | 施策 | commit | 内容 | 期待効果 |
|---|------|--------|------|---------|
| impl1 (#1) | **hf_transfer + `HF_HUB_ENABLE_HF_TRANSFER=1`** | [`5b2f53c4`](https://github.com/ayutaz/piper-plus/commit/5b2f53c4) | `src/python/pyproject.toml` の train extras に `hf_transfer>=0.1.6` 追加、 `docker/python-train/Dockerfile` runtime stage に `ENV HF_HUB_ENABLE_HF_TRANSFER=1` 焼き込み、 handoff §2 に vast.ai bare-VM 用 export 手順を追記 | **raw DL 3-5h → 1-1.5h** (単スレッド hf_hub 40-80MB/s → Rust concurrent chunk 200-500MB/s、 3-5x)、 vast.ai の `inet_up ≥ 3Gbps` 帯域を使い切れるように |
| impl2 (#2) | **KsponSpeech `.pcm` 直読 (WAV 変換省略)** | [`c2f59ec0`](https://github.com/ayutaz/piper-plus/commit/c2f59ec0) | `norm_audio._read_pcm16_mono` (int16 → float32/32768、 s16 PCM spec 準拠) + `_read_audio_any` dispatcher を新設、 全 4 `cache_norm_audio*` entry point + `parse_kspon_speech` default `audio_ext` を `.pcm` に flip、 `test_pcm_read.py` で normalisation / 空 file / 大文字 `.PCM` / WAV passthrough を pin | **ETRI PCM→WAV pre-pass 3-4h → ~0** (raw PCM は既に int16 s16le で soundfile 経由 WAV の decode round-trip と等価、 IO-bound で parallel VAD に融合)。§2.4 の ko 追加分の主要 lever |
| impl3 (#4) | **parquet `audio.bytes` を FLAC 直保存 (double-decode 消去)** | [`e0fa0d04`](https://github.com/ayutaz/piper-plus/commit/e0fa0d04) | `export_libritts_r_from_parquet.py` / `export_cml_tts_from_parquet.py` に `--output-format {flac,wav}` (default flac) 追加、 FLAC magic (`fLaC`) 一致時は `write_bytes()` で zero-copy 保存 (旧: `sf.read` decode + `sf.write` WAV encode + downstream `sf.read` の 3 段 double-decode)、 duration は `sf.info()` headers-only 解析、 `prepare_bilingual_dataset.process_en_dataset` は `.flac` / `.wav` / 拡張子なし の 3 パターン受理で backward-compat | **LibriTTS-R export 30-60min → 5-10min (2-6x)**、 CML-TTS も 3 言語 (es/fr/pt) で同等 gain、 合計 **-50-100min** |
| impl4 (#5) | **`prepare_moe_speech_plus.py --parallel` default ON + chunksize=8** | [`b8539de4`](https://github.com/ayutaz/piper-plus/commit/b8539de4) | `--parallel` を `argparse.BooleanOptionalAction / default=True` に flip、 `Pool.imap` chunksize 1 → 8 (imap は chunksize に依らず input 順序 preserve、 byte-for-byte parity 契約は保持)、 CI / 小規模 dataset は `--no-parallel` で opt-out | **moe-speech 選抜 30-45min → 3-5min (12-16x)**、 呼び出し側 (v8 手順書) を触らずに丸ごと吸収 |

**未実装 (今回 deferred)**:

- **#3 GPU resample (soxr → torchaudio/CUDA)** — 22.05kHz upsample / 24kHz→22.05kHz downsample を
  GPU で実施すると parallel VAD 経路の CPU thrash を減らせる可能性があるが、
  **SNR / high-freq band 損失の GPU 検証が必要** (soxr MQ vs torchaudio kaiser_best の
  A/B と null-test) で v8 スケジュール外。 v9 で別 PR (GPU rented 時に実施)

**累積 wall-clock 見積の更新** (§3.10 / §4.3 のフェーズ表を上書き):

| 前処理カテゴリ | 旧見積 (2026-07-09 morning、 hf_transfer 未反映) | impl1-4 反映後 (今回) | 内訳 |
|---|---|---|---|
| 生データ DL | 3-5h | **1-1.5h** | impl1 hf_transfer 3-5x |
| LibriTTS-R + CML-TTS export | 60-120min | **10-20min** | impl3 FLAC 直保存 |
| moe-speech-plus 選抜 | 30-45min | **3-5min** | impl4 parallel default ON |
| KsponSpeech PCM→WAV 事前変換 (ko、 7-lang のみ) | 3-4h | **0** (parallel VAD に融合) | impl2 `.pcm` 直読 |
| prepare_multilingual_dataset (VAD / spec / soxr resample) | ~8h (P2 反映済) | ~5-6h (impl2 で ko WAV 変換分吸収済) | 変更なし |
| CAM++ per-utt embedding 抽出 | 30-45min (P5 default 化後) | 30-45min | 変更なし |
| **6-lang 計** | 12-15h | **6-9h** (**-40-50%**) | |
| **7-lang 計 (+ko)** | 15-18h | **7-10h** (**-45-55%**) | ko 分は impl2 でほぼ吸収 |

**累積効果**: 旧見積の 12-18h に対して **6-10h (中央値 8h)** に短縮。 §1 の 「話者多様性に予算を再配分」
原則を運用面 (待ち時間) でも実現、 本走 launch までの iteration cadence を大幅改善。 §4.3 の
フェーズ表の DL+前処理行を「~8-10h / ~$14-17」から **「~7-10h / ~$12-17」** に更新
(下振れの短縮効果、 上振れは ko 追加分)。

**検証**:

- impl1: `test_hf_transfer_env.py` (train extras の hf_transfer floor / Dockerfile ENV / env propagation / import guard、 4 test)
- impl2: `test_pcm_read.py` (normalisation contract + 空 file + `.PCM` case-insensitive + WAV passthrough) + `test_prepare_ko_datasets` の `.pcm` / `.wav` 両受理 (合計 38 test)
- impl3: `test_export_flac_direct.py` (FLAC magic 判定 / byte-for-byte zero-copy / wav mode backward-compat / detect_container priority、 12 test)
- impl4: `test_moe_speech_parallel.py` (default ON / `--no-parallel` opt-out / imap chunksize / byte-for-byte parity、 10 test)
- backward-compat: 既存 WAV / `.spec.pt` / serial exec の regression suite は全て PASS 継続

### 3.12 7-lang dataset 構築完了 + 4x DDP 実走 smoke — 通信律速の発見と中断判断 (2026-08-02/03)

vast.ai 4x A100 SXM4 **40GB** (contract 46527250、offer 44347432、$2.93/hr +
storage) で dataset 再構築 → smoke 実走を実施。**dataset は完成、学習は健全、
しかし DDP 通信律速で throughput が見積を大幅に下回り、ユーザー判断で
本走を一旦中断** (2026-08-03)。

**dataset 完成形 (HF 退避済み)**:

| 項目 | 値 |
|---|---|
| 総発話 / 話者 | **342,855 / 3,692** (holdout 除外後) |
| 言語内訳 (utts/spk) | ja 54,476/463・en 93,540/1,942・zh 88,035/218・es 21,698/115・fr 14,704/81・pt 47,736/749・ko 22,666/114 |
| es の 21.7k | cap 600/spk で 122k を意図的に削減した後の正しい値 (§2 の「~45k」目標は cap 適用を過大計上していた) |
| holdout | ja 10 話者 1,200 発話 (`holdout/`)。ko holdout は speaker prefix 正規化 (`ko_zeroth-*`) の関係で post-filter が 0 件 → **復元後に要再実行** |
| config | num_symbols=185 / **num_languages=8** (ko=7、sv=6 欠番のため max+1) / num_speakers=3,692 |
| CAM++ embedding | 342,855 個 (100%、GPU 抽出) |
| 退避先 | **HF public + gated-manual に全量保存 (2026-08-04 方針確定: private ストレージ上限回避)**: dataset フル (5×40GB split tar.gz + sha256 + essential 373MB) は dataset repo `ayousanz/piper-plus-multilingual-7lang-v8-dataset`、学習 ckpt (2ep ごと自動退避) は model repo `ayousanz/piper-plus-zero-shot-multi-7lang-v8`。ローカル控え `piper-v8-dataset-backup/` (essential のみ)。旧 private `…multi-6lang-v8` も public gated 化済み |

**再構築中に発見・修正した 7 バグ** (全て feature branch に push 済み、
「静かな成功」系は fail-fast gate + 契約テストで再発防止):

1. PyPI stale `piper-plus-g2p` (extended inventory 欠落 → ko/zh/ja が黙って欠損)
2. audio_norm `.npy` cache を読めない旧 `torch.load` リーダー ×5 箇所 (spec 全滅 / CAM++ 全滅)
3. NLTK data 未 DL (g2p-en が全発話 LookupError、str(e) 改行始まりで「空エラー」)
4. `num_languages=len(langs)` の欠番バグ (ko=7 が emb_lang 範囲外 → CUDA device assert)
5. DDP `static_graph=True` (Plan A) が GAN 交互最適化と非互換 → 撤回
6. hf CLI `--include` 複数パターン構文変更 (es データ 0 件で exit 0)
7. prosody 長さ不一致 2 発話で bilingual 全体 crash → skip 化

**smoke 実測 (300/100 batch、batch=32/GPU、T3+T6 on、SCL CPU)**:

| 構成 | sec/step | utts/s | 備考 |
|---|---|---|---|
| 単一 GPU (batch=32) | **~5.5** | 5.8 | 計算は健全 (80GB batch=64 の 10.74 の半分 = linear) |
| 4x DDP | **11.11** | 11.5 | Non-finite 0/300、VRAM peak 14.5GB/40GB |
| 4x DDP + P2P 有効 | ~12.2 | — | 効果なし |
| 4x DDP + NCCL_ALGO=Tree | crash | — | 不採用 |
| 4x DDP + 勾配 bf16 圧縮 (`PIPER_PLUS_DDP_BF16_COMPRESS=1`) | ~12.0 | — | 効果なし (opt-in として温存) |

**結論: DDP オーバーヘッド ~5.6 s/step (50%) の通信律速**。当該ホストは
SXM4 表記だが `nvidia-smi topo -m` で NVLink が見えず (仮想化で無効)、
GPU 2+2 が別 NUMA (SYS 跨ぎ) で all-reduce が最悪経路。env チューニングでは
解決しない物理制約。

**見積前提の崩れ (重要な学び)**:

- §3.7 の「4x DDP で 2.5-3h/epoch (9-11 日)」は単一 GPU 実測からの
  **linear scaling 仮定の外挿**で、DDP 通信を含まない。実測 8.3h/epoch
- vast.ai のオファー情報では **NVLink の有無を事前に判別できない**
  (SXM4 表記でも仮想化で無効の場合がある)。レンタル後 `nvidia-smi topo -m` で
  `NV#` リンクの確認が必須
- **80 epoch は v7 同等総 step の 1.72 倍** (v8 342,855 utts では v7 32ep 同等
  = 46 epoch)。50 epoch 前後が品質/コストのバランス点

**中断時点の選択肢 (実測ベース、2026-08-03)**:

| 案 | 工期 | GPU コスト |
|---|---|---|
| NVLink ありホスト (要ガチャ) + 50ep | ~10 日 | ~$700 (当初予算内) |
| 現ホスト級 + 50ep | ~17 日 | ~$1,410 |
| 現ホスト級 + 80ep | ~28 日 | ~$2,250 |

**復元手順 (再開時)**: essential tar (373MB) を展開して
`/data/piper/dataset-multilingual-7lang-v8/` に配置 → audio cache は
生データ DL + 前処理パイプライン (Stage A/B + C1-C4 の cache 部分、
~5h / ~$20) で再生成 (cache パスは sha256 ベースで決定的に一致)。
ko holdout の post-filter 再実行 (Zeroth 5-10 spk、speaker 名は
`ko_zeroth-<id>` 形式に注意) を忘れないこと。学習 launch は
`/root/v8_train.sh` 相当 (scratchpad `v8_train.sh`、自動 resume +
ckpt uploader 込み) を使用。

### 3.13 本走 v1 全損事故 — Super-MAS silent 破損の root cause と再発防止 (2026-08-05/07)

NVLink ありホスト (contract 46659524、4x A100 SXM4 40GB、$2.94/hr) で
2026-08-03 に launch した 80ep 本走 v1 は **「完走」したが SECS ≈ 0 のモデル全損**。
症状は学習開始直後からの KL 発散 (cap 1e4 貼り付き × kl_weight 0.1 = 表示値 1000) +
duration 教師崩壊 (loss_dur ≈ 0.006)。mel だけは減少し `non_finite_skip` も 0% の
ため、当時の監視 (skip 率 + 進行のみ) では健全に見えた。

**bisect (A〜E) による root cause 確定**:

| 実験 | 変更 | 結果 |
|---|---|---|
| A/B | T3/T6・GPU spec 経路の除去 | 発散継続 (シロ) |
| C | ja/en subset (多言語・データ量を除去) | 発散継続 (シロ) |
| D | C から `--language-balanced-sampling` / `--channels-last` を除去 | 発散継続 (シロ) |
| E | D + **`PIPER_PLUS_DISABLE_SUPER_MAS=1`** | **kl=1.088→0.942 / dur=1.726→1.820 と即正常化 — 犯人確定** |

**根因: Super-MAS Triton kernel の環境依存 silent 破損**。py3.12 + 当該 triton
環境で kernel はエラーなく実行されるが、壊れた MAS アラインメントを返す
(2026-07 の py3.13 環境では正常だった)。壊れたアラインメント → duration 教師が
無意味化 (loss_dur ≈ 0) + flow prior の整合が取れず KL 発散、という全症状を説明する。

**副産物として発見した実バグ**: GPU batch spec のフレーム切り出しが CPU 経路と
3 フレームずれていた (`42b2994c` で修正、`test_gpu_spec_frames` で pin)。

**rerun**: HF 上の不良 run 成果物 41 ファイルを削除 (自動レジュームが不良 ckpt を
拾い「max_epochs 到達済み」で即終了する事故を 1 回踏んだため) → from scratch で
2026-08-07 00:14 UTC に再 launch (Cython MAS 固定)。kl 1-2 台 / dur ~1.9 で健全。

**再発防止 (コード化済み、本 branch)**:

1. **Super-MAS 実行時 parity 自己検証** (`vits/monotonic_align/__init__.py`):
   最初の 3 dispatch で Cython 参照と IoU 比較 (閾値 0.90)。不一致なら ERROR log +
   プロセス内で永続 Cython fallback、当該 batch も参照 path で学習。健全環境の
   unit test では捕捉できない「環境依存 silent 破損」クラスを実行時に遮断する。
   coverage メトリクスでなく IoU なのは all-ones 汚染も検出するため。
   テスト: `test_super_mas_dispatch.py::TestRuntimeParityValidation`
2. **KL cap 貼り付き検知 + abort** (`vits/lightning.py:_update_kl_cap_guard`):
   raw KL (clamp 前) が cap 1e4 に **連続 300 step** 貼り付いたら RuntimeError で
   学習を落とす (50 step ごとに ERROR log)。cap は scratch 初期 ~100 batch のみ
   活性が正常で、連続貼り付き = KL 勾配ゼロの回復不能状態。
   `PIPER_PLUS_KL_CAP_ABORT_STEPS` で閾値変更 (0 で abort 無効化)。
   テスト: `test_kl_cap_guard.py`
3. **運用**: 学習健全性は「Non-finite skip 率」でなく **wandb の loss_kl / loss_dur
   実値**で判定する (正常: kl 1〜2 桁で推移、dur ~1.5-2、mel 減少)。Super-MAS を
   再有効化する場合は実データ 100 batch で loss_kl < 10 を確認すること

**コスト**: 全損 run ~$280 + bisect ~$30。rerun は ~$250-350 見込
(2026-08-09 UTC 完走予定)。

### 3.14 rerun 完走 + SECS 評価結果 (2026-08-09)

**rerun は 2026-08-09 06:10 UTC に 80 epoch 完走** (`max_epochs=80 reached`)。全期間
kl 1-2 台 / dur ~1.8-1.9 で発散なし、loss_mel 38 → 21.6。途中 2026-08-08 04:22 UTC に
vast.ai ホストの予告なき再起動で epoch 40 途中に中断したが、last.ckpt (epoch 39) から
自動レジュームで復旧 (損失 ~30 分)。以後の reboot は `/root/onstart.sh` の自動レジューム
追記で無人復旧する。実測ペース 35-44 min/epoch。rerun 実費 ~$160。

**SECS 評価 (`/root/v8_eval.py`、CAM++ cosine、参照 1 発話 → 合成 3 発話/話者)**:

| 区分 | ep59 | ep69 | **ep79 (final)** | GT 天井* | 達成率 (ep79) |
|---|---|---|---|---|---|
| zs_ja (holdout 10 spk) | 0.6535 | 0.6515 | **0.6493** | 0.7183 | **90%** |
| zs_ko (holdout 7 spk) | 0.4559 | 0.5055 | **0.4895** | 0.8514 | 57% |
| known (7 lang × 2 spk 中央値) | 0.4471 | 0.4440 | **0.4410** | 0.7911 | 56% |

*GT 天井 = 同一話者の原音同士の SECS (`/root/v8_gt_control.py`)。ja 天井が 0.72 と
低いのは moe-speech の演技幅による話者内変動。

**所見**:

- **SECS は ep59 で既にプラトー** (3 点の差は誤差範囲、上昇トレンドなし) —
  追加 epoch での改善余地はない。cosine LR も min 1e-5 到達済み
- zs_ja は GT 天井比 90% で実質良好。raw では目標 0.72 / v7 baseline 0.6879 に
  未達だが、v7 の数字は別データセット・別プロトコル測定で厳密比較不可
- zs_ko (57%) は ko データ量 (~25k utts / ~120 spk) の制約が素直に出た形。
  改善は v9 でのデータ拡充マター
- 全損 run (SECS ≈ 0.005) からの回復は完全で、Super-MAS 事故の影響は残っていない

**成果物 (HF `ayousanz/piper-plus-zero-shot-multi-7lang-v8`)**: 全 epoch ckpt
(2ep ごと) + `onnx/v8-zs-ep79.onnx` (40.6MB FP16) + `eval/eval_results_ep{59,69,79}.json`。
聴感確認用サンプル (zs_ja ×2 spk + zs_ko ×1 spk、synth 3 + 参照原音) はローカル
`piper-v8-dataset-backup/v8_listen_samples/`。

### 3.15 zero-shot 音質 (がびがび) / 類似度の原因調査 (2026-08-09、ローカル実測)

ユーザー聴感報告「zero-shot はがびがび + 参照に似ていない。FT モデルでは出ない」を受けた
切り分け調査。全て同一テキスト × 同一 holdout ja 参照 (`361eb7a2`) で UTMOS
(utmos22_strong) + SECS (CAM++) を実測。

**実測サマリ**:

| 対象 | UTMOS | SECS vs ref |
|---|---|---|
| 参照原音 (moe-speech) | 2.60 | — |
| v8 ep21 (FP16) | 1.27 | 0.65-0.70 |
| v8 ep41 (FP16) | 1.36 | 0.78-0.81 |
| v8 ep79 (FP16) | 1.43 | 0.77-0.78 |
| **v8 ep79 (FP32 export)** | **1.53** | 0.76-0.81 |
| v7 ep32 (FP16、同条件) | 1.80 | 0.778 |

**確定した事実**:

1. **がびがびは v8 固有でなく v7 でも存在** (v7 UTMOS 1.80 ≪ 参照 2.60、良好 TTS は 3.5+)
2. **参照 embedding の質はシロ**: 学習使用話者の embedding (単発話 / 50 発話 centroid)
   でも UTMOS 1.31-1.39 と改善せず → OOD 説を棄却。ノイズは decoder 側に焼き付き
3. **noise_scale もシロ** (0.2/0.4/0.667 で 1.36-1.44 フラット)
4. **UTMOS は epoch とともに単調上昇中** (1.27→1.36→1.43、プラトーなし) →
   decoder は学習不足で、学習を続ければ音質はまだ伸びる。一方 **SECS は ep41 で飽和**
5. **FP16 export が UTMOS を ~0.1-0.2 押し下げる** (ep79: FP32 1.53 vs FP16 1.43)
6. 類似度が伸びない機序: SCL は 8192 sample (0.37 秒) 切片への CAM++ cosine で
   学習時 cosine ~0.21 と勾配が実質無意味 (loss_spk v7 -19% / v8 横ばいで一致)。
   conditioning は `g = spk_proj + emb_lang` の単一グローバルベクトルで韻律転写機構なし
7. FT でがびがびが消えるのは decoder が単一話者に特化再学習されるため。
   multi-speaker base は 3,692 話者に容量が分散し 1 話者あたりの decoder 成熟が遅い
   (571 話者の v7 は ep32 で UTMOS 1.80 に到達 = 話者数と成熟速度のトレードオフ)

**解決策の選択肢** (§7 / quality-improvement-plan Tier 2-3 と接続):

- 即効: FP32 export 採用 (+0.1-0.2 UTMOS、75MB) / FT 運用 (実証済み: がびがび解消 + SECS 0.77)
- 学習追い焚き (v8.1): ep79 から WavLM discriminator ON + disc fp32 で +20-40ep resume
  (UTMOS 上昇トレンド継続中のため効果見込み、~$150-400)
- v9 根本策: SCL segment 延長 or full-utterance SCL / InfoNCE / 韻律転写 /
  話者数を quality-first に削減 (話者スケーリングは SECS を改善しなかった:
  v7 571spk 0.688 → v8 3,692spk 0.649)

### 3.16 v8.1 継続学習 — 微分可能 SCL (InfoNCE) + WavLM で両問題を大幅改善 (2026-08-10)

§3.15 の解決策を実装し、v8 ep79 から warm restart で 40 epoch の継続学習 (v8.1) を
完走 (2026-08-10 05:30 UTC、instance 47257713 = NVLink 実証済ホスト再レンタル、
実測 ~14.5 min/epoch、学習実費 ~$45)。

**v8.1 の構成変更 (v8 との差分)**:

| 変更 | 実装 |
|---|---|
| 微分可能 SCL | torch 版 CAM++ (`--speaker-encoder-torch-path`、3D-Speaker port、ONNX と parity cos=0.993)。**ONNX+no_grad で勾配ゼロだった SCL に初めて勾配が流れる** |
| InfoNCE 対比損失 | `--spk-loss-type infonce` (in-batch 話者判別、同一話者 false negative はマスク) |
| SCL 窓の延長 | `--segment-size 16384` (0.37s → 0.74s、CAM++ が安定する窓長) |
| 知覚品質 discriminator | WavLM ON (`--c-wavlm 0.5 --wavlm-every-n-steps 2`) + `--disc-precision 32-true` |
| warm restart | `--resume-weights-only` (epoch 0 / 新 optimizer / cosine 1e-4→1e-5、KL annealing なし) |

**結果 (v8 と同一プロトコル: holdout ja 10 + ko 7 spk、known 7 lang × 2 spk)**:

| 指標 | v8 ep79 | **v8.1 ep39** | 変化 | GT 天井 | 達成率 |
|---|---|---|---|---|---|
| **zs_ja SECS** | 0.6493 | **0.7117** | **+0.062** | 0.7183 | **99%** (実質天井到達) |
| **zs_ko SECS** | 0.4895 | **0.6461** | **+0.157** | 0.8514 | 76% |
| **known SECS** | 0.4410 | **0.6135** | **+0.173** | 0.7911 | 78% |
| **UTMOS (zs_ja 合成 30 wav)** | 1.43 | **2.014** | **+0.58** | 参照原音 2.60 | v7 (1.80) 超え |

- 学習中の loss_spk (InfoNCE): 1.23 → 0.60 と一貫下降 — **SCL が初めて学習された**
  (v7/v8 の cosine+no_grad 版は全期間ほぼ横ばいだった)。SECS の +0.06〜+0.17 は
  この効果が直接現れたもの
- UTMOS +0.58 は WavLM discriminator + disc fp32 の効果。v8 目標の「がびがび改善」
  に対する定量的裏付け
- kl/dur は全期間安定 (2.5-2.8 / 1.8)、発散なし、non-finite skip なし

**成果物 (HF 同 repo)**: `checkpoints-v8.1/` (2ep ごと 20 個) +
`onnx/v8.1-zs-ep39.onnx` (FP16 40.6MB) + `eval/eval_results_v8.1_ep39.json` +
`eval/utmos_v8.1_ep39_zsja.tsv` + `logs/v8_1_train_final.log`。
聴感サンプル: ローカル `piper-v8-dataset-backup/v81_listen_samples/`
(v8 と同一 3 話者、v8 版 `v8_listen_samples/` と直接聴き比べ可能)。

**セットアップで踏んだ罠 5 件** (hub 1.x pin / `--include` 複数指定 /
essential tar 展開順 / .env CRLF → NCCL timeout 偽装 / smoke 前提 DL 漏れ) は
メモリ `v8_zero_shot_scaling.md` に記録済み。

### 3.17 がびがびの根本原因特定 — PQMF 実装バグ (2026-08-10)

v8.1 でも聴感の「がびがび」が残ったため、信号分析 + 6 方向 deep research +
git 履歴調査で根本原因を特定した。**結論: `mb_istft.py` の PQMF がコサイン変調の
位相項 `(-1)^k·π/4` を欠いておりエイリアスキャンセルが機能していない**
(実測 roundtrip SNR: 帯域境界トーンで -1.6〜12dB、canonical 実装は 59-64dB)。
帯域境界 5512/8268Hz が症状の 5-9kHz を正確にブラケットし、症状 7 件すべてと整合。
single-speaker FT では decoder が話者専用のエイリアス事前補償を学習できるため
ノイズが消え、zero-shot では補償が汎化せず残留する — 「課題が残り続けた」機序。

プロセス上の原因: PR #320 (2026-05) で要求定義の受け入れ基準「PQMF 残存 -90dB」を、
バグ実装の実測値 (7-8dB) を「理論限界」と誤認して「SNR > 5dB」に緩和した
(goalpost moving)。詳細・検証実験・対策 (P0: PQMF canonical 修正 — ただし既存
ckpt と非互換のため v9 再学習 or decoder 再適応 FT が必要) は
[`zero-shot-noise-root-cause-pqmf.md`](zero-shot-noise-root-cause-pqmf.md) を参照。

### 3.18 v9: がびがび根治学習 — 完走・聴感で解消確認 (2026-08-10〜12)

§3.15-3.17 の根本原因調査を受けた対策学習。全記録は
[`zero-shot-noise-root-cause-pqmf.md`](zero-shot-noise-root-cause-pqmf.md)
(§5.5 検証実験 / §5.6 P1+データゲート / §5.7 本走結果) を canonical とする。要約:

- **P0 (コード)**: PQMF canonical 修正 (roundtrip 7.5→64dB、旧 ckpt は buffer
  復元で後方互換) / MRD (`--use-mrd`) / full-band MR-STFT (`--c-full-stft`) /
  がびがび専用指標 `measure_band_noise` / `--reinit-pqmf` + `--train-decoder-only`
- **P1 (検証)**: v8.1 からの再適応 FT は decoder-only 2ep も全パラメータ 8ep も
  指標不変 → **from scratch 確定**。訓練データの高域ノイズ床 (Zeroth fmax 中央値
  3.0kHz) も実測で確定
- **P1.5 (データゲート、案 Z)**: Zeroth 全除外 + hi_ratio/fmax999 ゲート →
  300,443 utts / 6 言語 (ko は sampler 崩壊回避のため完全除外、v10 で復活予定。
  **教訓: language-balanced sampling は最小言語の utts 数が epoch サイズを決める**)
- **P2 (本走)**: 50ep 完走 (~$140)。スペクトルで 4-9kHz 非構造ノイズ v8.1 比
  **-5〜-10dB + 倍音構造獲得**。聴感で「v8.1 より減った」をユーザー確認
  (2026-08-12)。ただし**根絶ではない** — OOD 参照 (§3.19) では残存がびがびが
  聴感で再報告された
- **トレードオフ**: zs_ja SECS 0.712 → 0.652 (-0.06)。追加学習で回収予定
- **新課題**: 韻律 (強弱) の平板さ — v8 系からの持ち越し。noise_scale 掃引で
  即時緩和を検証中、本格対応は v10
- 成果物: HF `checkpoints-v9/` + `onnx/v9-zs-ep49.onnx` + `v9-data/` (ゲート済み
  jsonl + 全量帯域 metrics) + `eval/eval_results_v9_ep49.json`

### 3.19 OOD 参照 (つくよみちゃん) zero-shot の実力測定 — SECS 測定方法の訂正 (2026-08-12)

> **canonical**: [`zero-shot-speaker-similarity-root-cause.md`](zero-shot-speaker-similarity-root-cause.md)
> (本節は要約。A/B 詳細・epoch 軌跡・機構仮説・再現方法は canonical 参照)

つくよみちゃんコーパス VOICEACTRESS100_094 (96kHz studio 録音、学習コーパス外)
を参照にした v9 zero-shot をユーザーが聴感評価 →「まだがびがび + 全然似ていない
(多少女性っぽい程度)」。当初報告した SECS 0.775 と矛盾したため分離調査を実施。

**測定方法の訂正 (最重要)**: 当初の 0.775 は「条件付けに使った同一発話」との
cosine だった。SCL (InfoNCE) は生成音声の CAM++ embedding を条件 embedding に
一致させるよう学習するため、**same-utterance SECS は話者が似ていなくても高く出る
(Goodhart)**。正直な測定は **cross-utterance** (参照とは別の同一話者発話との
cosine) が必須。以後の SECS 報告は全て cross-utterance とする。

**正直な測定値 (cross-utt、他 4 発話平均)**:

| 測定 | 値 |
|---|---|
| 同一話者 ceiling (094 vs 他 8 発話) | 0.8876 |
| 別話者 floor (094 vs holdout ja 女性 2 名) | 0.740 / 0.689 (ja 女性は CAM++ 空間で密集) |
| v9 zero-shot (単発話 emb) | **0.73** — floor すれすれ = 「多少女性っぽいだけ」と一致 |
| v9 zero-shot (20 発話平均 emb) | 0.765 (改善は僅か) |
| v8.1 zero-shot (単発話 / avg20) | 0.777 / 0.782 (v9 より上、holdout 退行 0.712→0.652 と整合) |

**容疑者の無罪確定 (4-way A/B、instance 上、同一 emb/テキスト/scales)**:
raw ckpt fp32 = 0.725 / EMA fp32 = 0.743 / ONNX fp32 = 0.759 / ONNX fp16 (配布物)
= 0.731 — **EMA・FP16・export graph はいずれも劣化要因ではない** (ONNX の方が
4-9kHz 帯域レベルは ~2dB 低い)。embedding 抽出も無罪 (つくよみ vs ko 男性 =
0.14 で判別正常、96kHz→16k 直行 vs 22.05k 経由 = cos 0.9999)。

**結論**: 「似ない」の根本原因は **v9 モデル自体の zero-shot 話者転写の弱さ**。
ceiling-floor で正規化すると v9 の identity 転写率は ~0.2、v8.1 でも ~0.4 に
とどまり、既知の SECS 課題が OOD 参照でより顕在化した形。がびがびも経路非依存の
モデル残存ノイズ (v9 で減ったが根絶ではない、ns=0.667 は 0.4 より高域が増える)。

**epoch 軌跡 (つくよみ cross-utt SECS、raw ckpt)**: ep23 = 0.672 → ep35 =
0.735 → ep49 = 0.725。**ep35 以降の 15 epoch で飽和** (v8.1 の 0.777 に届かず
plateau)。単純な追加学習 (同一 config 継続) では回収見込み薄と判断。退行の
主因候補は (i) MRD + full-band STFT がスペクトル忠実度に容量を割き話者条件付け
が相対的に弱まった loss バランス、(ii) 案 Z ゲートでの話者多様性減。

対策の優先順: (a) 継続学習するなら **c_spk / c_dino 強化のリバランス込み**で
(素の +20-30ep は飽和曲線の外挿上、効果が見込めない)、(b) 特定話者を確実に
似せる用途は従来どおり FT (プロダクト設計: FT 主、zero-shot 補完)、(c) v10 で
データ多様性 + 韻律とあわせて本格対応。

## 5. 成功基準と評価

| 指標 | v7 baseline | v8 目標 |
|---|---|---|
| SECS zero-shot (未知話者) | 0.6879 | **≥ 0.72** (ja 参照音声で特に改善を確認) |
| SECS 既知話者 | 0.6619 | ≥ 0.68 |
| ja 参照 zero-shot SECS | (未計測、弱いはず) | en と同水準 |
| Non-finite skip 率 | 2.5% | ≤ 5% |

評価は v7 の `compute_secs.py` 再現セット (HF `piper-plus-zero-shot-multi-6lang-v7` 同梱) を
v8 用に拡張し、**ja 未知話者の評価セットを新設** (moe-speech-plus の学習除外話者 ~10 名。
女性偏重の実測のため、可能なら男性キャラを意図的に含める)。

**評価用話者 holdout の運用 (2026-08-02 確定)**: 学習コードに holdout 機構はないため、
**dataset.jsonl 構築後の post-filter** で学習セットから除外する:

- **ja**: moe-speech-plus から ~10 名 (男性キャラ含む) を学習除外 → ja 未知話者評価セット
- **ko**: Zeroth-Korean から 5-10 名を学習除外 → **ko 未知話者評価セットを新設**。
  ko 学習話者は ~210 (KsponSpeech 除外後、§2) のため ko zero-shot 品質は限定的で、
  §3.10 の「ko 参照 zero-shot ≥ 0.65」目標 (kspon ~1,700 spk 前提) は適用しない —
  参考測定として記録し、ko データ拡充 (商用可ソース) は v9 課題 (§6.5)

## 6. オープン課題

- [ ] es/fr/pt 縮小の品質回帰監視 (ep10 SECS で判断、必要なら cap 緩和)
- [ ] batch=32/GPU × 4 (effective 128) の VRAM 実測 @ A100 40GB — smoke test を VRAM gate
  とし、溢れたら batch=24 に下げるか 80GB 構成に乗換 (§4.1 の 2026-08-02 注記)
- [ ] moe-speech-plus の speechMOS / CER フィルタ閾値の実分布確認 (通過率が想定を大きく
  外れたら cap・閾値を調整)
- [ ] v7 前処理で CML-TTS 話者が es 77→63 / fr 45→28 / pt 30→8 に削られた理由の特定
  (prepare_multilingual_dataset.py のフィルタ閾値) と緩和
- [ ] Common Voice pt の品質フィルタ通過率確認 (UTMOS + validated + ≥20 clips/spk で
  実際に何話者残るか。目標 +100〜300 話者)

## 6.5 Korean (ko) 追加 — 2026-07-09 追加ランディング

> **⚠️ 決定 (2026-08-02、ユーザー確定): KsponSpeech は v8 から除外。**
> v8 は過去の piper-plus 事前学習モデル同様 **public + 商用利用可の
> open-model として公開する**方針が確定し、KsponSpeech の AI-Hub ライセンス
> (research-only、モデル配布制限、raw 再ホスト禁止) と両立しないため。
> v8 の ko は **Zeroth-Korean (CC BY 4.0、~181 spk) + Common Voice ko
> (CC0、~30-50 spk)** のみで学習する (§3.10 の「Zeroth + CV ko のみでの
> 7-lang 版」オプションを本線に昇格)。ko 話者 ~210 のため ko zero-shot
> 品質は限定的 — ko データ拡充 (商用可ソース) は v9 課題。
> `--ko-ksponspeech` 経路と `parse_kspon_speech` はコード上残置 (research
> 用途の第三者利用は可能) だが、v8 公式 run では使わない。
> CV ko の UTMOS tsv は `piper_train.tools.score_utmos` (SpeechMOS utmos22_strong、
> 2026-08-02 追加) で生成する。

v8 のクリティカルパス (moe-speech-plus + LibriTTS-R + AISHELL-3 + CML-TTS の
6-lang 学習) は不変のまま、 **同一 v8 run 内で ko=7 も学習** する副次拡張。
G2P は 7 ランタイム全てで既に ready (`docs/spec/language-id-map-contract.toml:
extended_language_id_map`)、 id_maps.py の `_KOREAN_PHONEMES` も組み込み済のため、
今回追加した実装は **data pipeline (parser 3 種 + CV ko exporter)** に閉じている。

| ソース | ライセンス | 想定 spk | 想定 utts | prepare 引数 |
|---|---|---|---|---|
| **Zeroth-Korean** | CC BY 4.0 (openslr.org/40) | ~181 | ~22k (train_data_01 のみ) | `--ko-zeroth <dir>` |
| KsponSpeech (**v8 除外**、冒頭の 2026-08-02 決定) | AI-Hub consent (research use、 商用非公開) | (~2,000) | (cap=60/spk で ~120k) | `--ko-ksponspeech <dir> --ko-kspon-cap 60` (v8 公式 run では不使用) |
| **Common Voice ko** | CC0 | ~30-50 (UTMOS≥2.5 + ≥20 clips + cap 60) | ~3k | `--ko-cv <dir> --ko-cv-min-utmos 2.5` |
| **計 (v8 採用分 = Zeroth + CV ko)** | | **~210** | **~25k** | |

**成果物**:

- `parse_zeroth_korean` / `parse_kspon_speech` / `parse_common_voice_ko` を
  `prepare_multilingual_dataset.py` に追加 (既存 `parse_aishell3` / `parse_cml_tts`
  と同一シグネチャの `(entries, speaker_counts)` タプル返却)
- `export_common_voice_ko.py` を追加 (`export_common_voice_pt.py` のミラー、
  UTMOS tsv 追加サポート)
- `LANGUAGE_ID_MAP` / `ALL_LANGUAGES` を 8-lang extended 形式に拡張 (ko=7)
- 契約 `language-id-map-contract.toml` の python_train entry を
  `extended_language_id_map` / `extended_languages` に切り替え
- 全 mirror (Rust wasm / trained-form fixtures) は既存 8-lang 形式のまま無変更

**注意**:

- KsponSpeech は raw PCM 配布のため、 学習前に ETRI 提供 PCM→WAV スクリプトで
  16kHz WAV に変換する必要がある (parse 側の `audio_ext` default は `.wav`)。
  22.05kHz upsample は `cache_audio_parallel` (soxr MQ) で自動処理
- 話者 id は sources 間でグローバルユニークにするため、 parser 側で
  `zeroth-` / `kspon-` / `cv-` を prefix
- `--ko-splits` で 3 sources 共通の split override が可能 (Zeroth: `train_data_01`、
  KsponSpeech: `KsponSpeech_01`、 CV ko: `cv` が default)
- 学習は 6-lang 版 (現行 v8 CLI) と同じで、 `--ko-*` を追加するだけで
  自動的に 7-lang 化 (dataset label が `multilingual-7lang` に切替)。
  emb_lang テーブルサイズは config.json の `num_languages` から自動決定

## 7. v9 拡張パス (gol-dataset、v8 の結果を見て判断)

[`midralab/gol-dataset`](https://huggingface.co/datasets/midralab/gol-dataset):
7,405,094 発話 / **19,349 話者** / 10,654h (VN 音声、webdataset tar、~105GB、gated manual)。

- v8 (ja 473 話者) の ja 参照 SECS が en 参照に届かない場合、話者数が残りのレバー。
  gol で ja を数千話者級に拡張する
- emb_g なしアーキテクチャのため **v8 ckpt から warm-start で継続可能** (スクラッチ不要)
- 事前確認事項 (v9 開始時): ① metadata に転写が含まれるか (なければ anime-whisper で
  選別サブセットに付与、A100 で ~200k 発話 ≈ 6-9h) ② 品質分布 (UTMOS を選別サブセットに計算)
  ③ gated 承認とライセンス条件文面
