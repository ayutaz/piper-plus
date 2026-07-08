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
--val-every-n-epochs 5                           # SCL/DINO 込み val は G+D full forward、頻度低下
--compile --compile-mode reduce-overhead         # torch.compile (Plan A で mode/dynamic を CLI 化)
--no-compile-dynamic                             # length_bucketing で shape 固定化 → CUDA Graph capture 有効化
--enable-length-bucketing                        # 話者スロット内で phoneme_length ソート、padding 削減 (Plan A 実装 3/4)
--no-wavlm                                       # v7 継承 (VRAM 節約 & WavLM 経路 P0 未実装)
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

## 4. vast.ai 実行計画

| 項目 | 値 |
|---|---|
| 推奨インスタンス | **A100 SXM4 80GB × 1、32 vCPU、disk ≥ 1.7TB、回線 ≥ 7Gbps** (~$1.0–1.3/hr) |
| 代替 (安価) | RTX 5090 32GB (~$0.44/hr、batch ~48、wall-clock ~2倍) |
| 代替 (高速) | H100 SXM 80GB (~$2.2/hr、~2倍速) |
| disk 内訳 | 生データ ~550GB (moe-plus zips ~350GB 含) + audio cache ~350GB + ckpt (947MB × 80) + margin → **≥ 1.5TB** |
| epoch 時間見込み | baseline (P0 のみ) ~1.5–1.7h/ep / **Plan A 反映後 (§3.3) ~1.0–1.2h/ep** (340k 発話、A100 80GB。v7 実績 V100×4 8h53m/500k から換算) |

単一 GPU 構成とし、v7 で「CUDA illegal access」偽装の真因だった DDP/NCCL 系障害
(rank 間 NaN skip 不整合 → all_reduce mismatch → 30 分 timeout) のクラスを丸ごと回避する。

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

**Plan A (§3.3、2026-07-09 実装完了) 反映後の見込み** — bucketing + D concat +
static_graph + compile 再チューン で epoch 時間 1.5-1.7h → **1.0-1.2h** に短縮:

| フェーズ | 時間 | コスト ($1.73/hr、storage 込) |
|---|---|---|
| DL + 前処理 + embedding 抽出 (CV pt フィルタ含む) | ~1–1.5 日 | ~$42–62 |
| smoke test (warm-start 1ep + 評価) | ~2h | ~$4 |
| 本走 80 epoch (**~1.1h/ep、Plan A**) | **~3.3–4.0 日** | **~$137–166** |
| SECS 評価 + ONNX export + HF upload | ~4h | ~$7 |
| **計 (Plan A、v8 想定)** | **~5–6 日** | **~$190–239 (中央値 ~$194)** |
| 参考: baseline (Plan A 未反映) | ~6.5–7 日 | ~$265–285 |

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
