# Zero-Shot TTS v8 — 話者数スケーリング学習計画

> 作成日: 2026-07-07 / **状態: 確定 (実行待ち — ブロッカーは HF トークンのみ、§4.5)**
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
| ja | 59,694 / 20 | ~55k / **473** | **moe-speech-plus** (全473話者、cap ~120 utt/spk) | 研究用途限定 (gated) |
| en | 64,698 / 310 | ~110k / **2,456** | LibriTTS-R **全話者** (cap ~50 utt/spk) | CC BY 4.0 |
| zh | 63,223 / 142 | ~70k / **218** | AISHELL-3 フィルタ緩和 (全話者) | Apache 2.0 |
| es | 168,374 / 63 | ~45k / **77** | CML-TTS **フィルタ緩和で corpus 全話者** (cap で発話縮小) | CC BY 4.0 |
| fr | 107,464 / 28 | ~35k / **45** | CML-TTS **フィルタ緩和で corpus 全話者** | CC BY 4.0 |
| pt | 34,066 / 8 | ~25k / **30 + CV 数百** | CML-TTS フィルタ緩和 + **Common Voice pt (品質フィルタ選別)** | CC BY 4.0 / CC0 |
| **計** | **497,519 / 571** | **~340k / ~3,300+** | | |

> **決定 (2026-07-07)**: v8 の ja は moe-speech-plus のみとする (ユーザー決定)。
> gol-dataset (19,349 話者) は v9 拡張候補として §7 に退避 — 転写有無・品質・gated 承認の
> 未確認リスクを v8 のクリティカルパスから外し、473 話者での ja 参照 SECS 改善を先に実測する。
> es/fr/pt の話者は corpus 上限。縮小による es/fr 品質回帰は ep10 SECS で監視。

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
# +34% の逆効果を実測、 v8 本走では **使わない** (Fix B [`90f0a68`] で再設計済み、 本走前に再 A/B)
```

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
| TF32 matmul (torch 2.x canonical) | `torch.set_float32_matmul_precision('high')` を `__main__.py` に追加 | +1-3% | commit `56116cca` |
| mel debug print の GPU sync 削除 | `torch.min(y) < -1.0` / `torch.max(y) > 1.0` を `mel_processing.py` から削除 | +1-2% | commit `56116cca` |
| Super-MAS Triton kernel を docker に取り込み | `docker/python-train/Dockerfile` に `[super-mas]` extra 追加 | MAS block +3-10% | commit `ddb76289` |
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

- CAM++ `cudnn_conv_algo_search=EXHAUSTIVE` (revert `530d68ce`) — session 作成 15 分 hang
- CAM++ 真の GPU batched inference default 化 (`320e9568` は opt-in 維持) — cosine 0.27 破損
- `num_workers` 自動調整 (PR #164 で削除) — shared memory 枯渇
- V100 で `--precision 16-mixed` — backward 5x 遅い、必ず `32-true` (V100) / `bf16-mixed` (A100+)

### 3.3 Plan A 実装完了 (2026-07-09)

§3.2 の P0 最適化を土台に、 A100 単一 GPU での epoch 時間を追加で 20-35% 削減する
「Plan A: コード側の低リスク throughput 最適化」 4 件を feature branch にランディング済み。
すべて既存 API/学習契約を破壊せず、 CLI opt-in または DDP 内部フラグで有効化する形。

| # | commit | 変更 | 対象ファイル | 期待効果 |
|---|--------|------|-------------|---------|
| 1/4 | [`161ed1b9`](https://github.com/ayutaz/piper-plus/commit/161ed1b9ff118f60addbfeb624b4018c52bf40de) | MPD の y/y_hat を batch dim で concat して 12→6 kernel launch | `src/python/piper_train/vits/models.py` (+13/-7)、 `src/python/tests/test_d_batch_concat.py` (+152 新規) | **D backward +5-10%** (launch overhead 削減、 allclose atol=1e-5 で等価性検証済) |
| 2/4 | [`37ea0158`](https://github.com/ayutaz/piper-plus/commit/37ea015884d68729d33c92f651c0774e1e3245ff) | `DDPStrategy` に `static_graph=True` 追加 | `src/python/piper_train/__main__.py` (+7/-1)、 `src/python/tests/test_ddp_strategy.py` (+20/-5) | **multi-GPU throughput +5-8%** (VITS GAN 交互最適化の unused-param 集合が step ごとに固定 → iteration 1 の graph を再利用) |
| 3/4 | [`1bfd64ac`](https://github.com/ayutaz/piper-plus/commit/1bfd64ac5c26c05baa7302ba274113013fd8365d) | `SpeakerBalancedBatchSampler` に length_bucket opt-in | `src/python/piper_train/vits/dataset.py` (+66/-2)、 `src/python/piper_train/__main__.py` (+12)、 `src/python/piper_train/vits/lightning.py` (+6/-1)、 `src/python/tests/test_length_bucketing.py` (+276 新規) | **step time -30-40% (padding 削減による 1.4-1.6x)**。 `samples_per_speaker=4` contract は保持、 intra-speaker length spread が半減することを test で保証。 CLI: `--enable-length-bucketing` |
| 4/4 | [`fe65f60b`](https://github.com/ayutaz/piper-plus/commit/fe65f60b18402cc6d19158a9691de549f191f6af) | torch.compile mode/dynamic を CLI 化 | `src/python/piper_train/__main__.py` (+37/-3) | **compile 再チューン +5-10%** (length_bucketing で shape 固定 → `--compile-mode=max-autotune` + `--no-compile-dynamic` で CUDA Graph capture 可能化)。 default は既存挙動 `reduce-overhead` + `dynamic=True` を維持 |

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

**Bug #1: cuFFT が BFloat16 で失敗** (commit [`11ff71fc`](https://github.com/ayutaz/piper-plus/commit/11ff71fc))
- `mel_spectrogram_torch` / `spectrogram_torch` の `torch.stft` が bf16-mixed autocast 下で
  `RuntimeError: cuFFT doesn't support tensor of type: BFloat16` を吐く。 v7 の `32-true`
  では発生せず、 A100 bf16-mixed 化で顕在化
- 修正: STFT 前に bf16/fp16 を fp32 に defensive upcast。 出力 dtype は L1 loss と揃う fp32

**Bug #2: scratch 初期化から KL loss = inf → 100% 全 batch skip** (commit [`d37ccda2`](https://github.com/ayutaz/piper-plus/commit/d37ccda2) + [`61aabe27`](https://github.com/ayutaz/piper-plus/commit/61aabe27))
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
tighten する追加修正** ([`45060ad`](https://github.com/ayutaz/piper-plus/commit/45060adc))、
length_bucket を per-batch 単一 bin 抽出に再設計する **Fix B**
([`90f0a68`](https://github.com/ayutaz/piper-plus/commit/90f0a68c)) も併せて投入。

| # | 分類 | commit | 変更 | 期待効果 |
|---|------|--------|------|--------|
| T2 | throughput (I/O) | [`8dc1571`](https://github.com/ayutaz/piper-plus/commit/8dc15711) | `Batch` dataclass に `pin_memory()` を追加 (plain dataclass は DataLoader の `pin_memory=True` で silently no-op だった) + train DataLoader の `prefetch_factor` default 2→4 (`--prefetch-factor` CLI 化) + `on_validation_epoch_end` の `.to(device)` を `non_blocking=True` 化 | **wall-clock -5-15%** (v8 で観測済の 「見えない non_blocking 同期化」 を実効化) |
| T1 | throughput (kernel layout) | [`bdd4f9e`](https://github.com/ayutaz/piper-plus/commit/bdd4f9e9) | `MultiPeriodDiscriminator` + `DiscriminatorP` に `use_channels_last` opt-in、 CLI `--channels-last` default OFF。 Conv2d weight + 1D→2D view 直後の activation を `torch.channels_last` に統一 | **sec/step -16% 目標** (§3.4 nsys で判明した nchw↔nhwc 変換 12.8% + Conv2d 8% = 20.8% overhead の削減余地)。 実測 A/B 後に default 化判断 |
| T5 | throughput (attention) | [`fa24218`](https://github.com/ayutaz/piper-plus/commit/fa24218f) | SDPA backend priority を明示制御 (`flash` / `mem_efficient` ON、 `math` OFF、 torch 2.11+ で `cudnn` ON)、 起動 log に有効 backend を出力 | Ada 6000 / RTX 5090 (sm_89 / sm_120) で naive math fallback を防止、 **long-sequence で 2x、 net +1-3%** |
| P1 | I/O (dataset load) | [`597c5cc`](https://github.com/ayutaz/piper-plus/commit/597c5ccf) | `piper_train.tools.precompute_mel` を新設 (fp16 `.npy` を pre-materialise、 atomic replace)、 `PiperDataset` に `precomputed_mel_dir` opt-in、 CLI `--precomputed-mel` | `torch.load(.spec.pt)` の pickle 経路を numpy path (`np.load → torch.from_numpy`) に置換で **DataLoader step 2-3x**、 80 epoch で **8-12h の I/O 節約** |
| P2 | I/O (preprocess) | [`4ca0bab`](https://github.com/ayutaz/piper-plus/commit/4ca0babd) | `norm_audio.default_num_processes()` を新設 (`min(cpu_count//2, 32)`)、 `cache_audio` / `prepare_multilingual_dataset` / `prepare_bilingual_dataset` の worker 数 default を統一 + tqdm 進捗バー追加 | 64 vCPU host で `cpu_count()` fan-out すると soxr/torch per-worker state と NFS IOPS で thrash (実効 throughput -30%)。 default 30 worker 相当に固定して **前処理 wall-clock 短縮 + 進捗可視化** |
| — | bucketing 再設計 (Fix B) | [`90f0a68`](https://github.com/ayutaz/piper-plus/commit/90f0a68c) | `SpeakerBalancedBatchSampler` の length_bucket を per-batch 単一 bin 抽出に変更 (4 quantile bin、 language_group_balance / samples_per_speaker=4 contract 保持) | §3.5 で `+34%` 逆効果だった実装を廃案 → バッチ間 shape 差を bin 幅に閉じ込め cudnn.benchmark cache を再利用可能に。 opt-in default OFF は継続、 v8 本走前に再 A/B |
| — | KL 発散防止 | [`45060ad`](https://github.com/ayutaz/piper-plus/commit/45060adc) | `logs_p` / `logs_q` clamp を `[-15,15]` → `[-8,8]`、 `m_p` clamp を `[-1000,1000]` → `[-100,100]`、 loss_kl 出力を `1e4` で cap (`SynthesizerTrn.forward` / `infer` / `lightning.py` 3 箇所) | §3.4 の scratch KL inf fix でも 300 batch smoke で batch 31 以降に 100% (262/300) Non-finite skip 再発 → worst case `(z_p-m_p)^2 * exp(-2*logs_p) = 4e17` が fp32 overflow していたため。 clamp 5 桁 down + 出力 cap で **grad direction 安定化**、 `kl_weight=0.1` と `grad_clip=1.0` と多層防御。 収束後は `|logs_p| < 5` で cap は no-op、 表現力を損なわない |

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
   - bf16 cuFFT bug (11ff71fc): mel STFT を bf16→fp32 defensive upcast
   - KL scratch 発散 (d37ccda2 + 61aabe27 + 45060adc): logs_p/m_p clamp と loss_kl cap の 3 段防御
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
   - `--enable-length-bucketing`: §3.5 で確認済 +34% 逆効果、 Fix B (`90f0a68c`) 未再検証
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

### 4.4 障害耐性 (多層防御)

インスタンス安定性 (§4.1) に頼り切らず、ホスト消失を前提に損失を限定する:

| 層 | 対策 | 最悪ケースの損失 |
|---|---|---|
| 1 | on-demand 契約 (横取りなし) | — |
| 2 | `--checkpoint-epochs 1` + **epoch ごと HF private upload** (`ayousanz/piper-plus-zero-shot-multi-6lang-v8` 新設) | 1 epoch ≈ 2.5h ≈ $3 |
| 3 | onstart 自動レジューム: 起動時に HF から最新 ckpt を取得し `--resume_from_checkpoint` で継続 (piper_train 対応済み) | 復旧の手作業ゼロ化 |
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
- **開始ブロッカー**: ① ユーザーの HF token (gated dataset read + private repo read/write)
  ② gated dataset (gol / moe-speech-plus) のアクセス承認がユーザー HF アカウントで済んでいること
- vast.ai API キーはローカル `~/.config/vastai/vast_api_key` に設定済み (2026-07-07、残高 $1,351)

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

## 6. オープン課題

- [ ] es/fr/pt 縮小の品質回帰監視 (ep10 SECS で判断、必要なら cap 緩和)
- [ ] batch 128 での VRAM 実測 (OOM なら 96 に落とす)
- [ ] moe-speech-plus の speechMOS / CER フィルタ閾値の実分布確認 (通過率が想定を大きく
  外れたら cap・閾値を調整)
- [ ] v7 前処理で CML-TTS 話者が es 77→63 / fr 45→28 / pt 30→8 に削られた理由の特定
  (prepare_multilingual_dataset.py のフィルタ閾値) と緩和
- [ ] Common Voice pt の品質フィルタ通過率確認 (UTMOS + validated + ≥20 clips/spk で
  実際に何話者残るか。目標 +100〜300 話者)

## 7. v9 拡張パス (gol-dataset、v8 の結果を見て判断)

[`midralab/gol-dataset`](https://huggingface.co/datasets/midralab/gol-dataset):
7,405,094 発話 / **19,349 話者** / 10,654h (VN 音声、webdataset tar、~105GB、gated manual)。

- v8 (ja 473 話者) の ja 参照 SECS が en 参照に届かない場合、話者数が残りのレバー。
  gol で ja を数千話者級に拡張する
- emb_g なしアーキテクチャのため **v8 ckpt から warm-start で継続可能** (スクラッチ不要)
- 事前確認事項 (v9 開始時): ① metadata に転写が含まれるか (なければ anime-whisper で
  選別サブセットに付与、A100 で ~200k 発話 ≈ 6-9h) ② 品質分布 (UTMOS を選別サブセットに計算)
  ③ gated 承認とライセンス条件文面
