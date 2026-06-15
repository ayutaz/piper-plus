# piper-plus 改善調査 統合レポート (2026-06-15)

2026-06-03 (v1.12.0、 増分 vs 刷新の整理) と 2026-06-15 (v1.13.0、 4 軸 23 アクションロードマップ) の 2 スナップショットを単一の参照源として統合したもの。 軸を **A. 音声品質モデル / B. ランタイム・エッジ / C. 多言語 G2P / D. エコシステム / E. 運用ガイダンス** の 5 系統に再編し、 各施策に**統合元バージョン**を明記。

> **統合の経緯**
>
> - 2 つのスナップショットは独立のデコンポジションで実施しており、 共通項目 (Matcha-TTS / per-word LID / footprint 量子化) は片方で得られなかった視点を統合して厚みを増した。
> - 重複は確信度の高い方を主軸に、 補完情報を merge。 各セクションに **【統合元】** タグで出典版を併記。
> - 棄却された主張・オープンクエスチョンも両調査分を統合掲載 (実装時の方針判断ミス予防のため)。

> **メタ情報 (統合)**
>
> | 項目 | 2026-06-03 (v1.12.0) | 2026-06-15 (v1.13.0) | 統合 |
> |------|---------------------|---------------------|------|
> | 一次ソース取得 | 21 | 26 | 47 |
> | 主張抽出 | 104 | 117 | 221 |
> | 検証 | 25 | 25 | 50 |
> | 確定 | 24 | 19 | 43 |
> | 棄却 | 1 | 6 | 7 |
> | 統合 finding | 9 | 9 | 31 アクション (重複統合後) |
> | DRAFT PR との重複除外 | — | #222 #355 #386 + Open PR #537 (v2.0.0 候補) | — |
> | オープンクエスチョン分類 (Phase 4) | — | — | 全 20 件 (本表 9 + companion 11) — RESOLVED 5 / CONVERGED 7 / IRREDUCIBLE 8 |

> [!WARNING]
> **時間依存性:** TTS 分野は進展が速い。 flow-matching / codec-LM TTS、 ORT EP の operator coverage、 WebGPU ブラウザ matrix、 INT4 量子化の MatMul shape 制約は実装着手時に再検証必須。 **ORT 最新は 1.26 (2026-05、 RISC-V Vector / WebGPU GridSample / OpenVINO EP upgrade / CUDA plugin EP graph)**。 piper-plus pin の 1.20.0 floor との差は `docs/reference/ort-versions.md` で確認。
>
> **転移可能性:** スタンドアロン vocoder の実証 (iSTFTNet2-MB / MS-Wavehax) は piper-plus の**統合 VITS2 decoder** 内で 1:1 で同じ RTF/MOS を出す保証はない。 統合 + 再学習して初めて確認できる。
>
> **ベンチマークの偏り:** MOS/RTF の多くは LJSpeech (単一話者・英語)。 piper-plus の 6 言語多話者設定での品質差は未証明。
>
> **VITS 系量子化:** INT8 dynamic quantization は coqui-ai/TTS の VITS で FP32 比 2 倍以上遅くなる報告あり。 4x ファイルサイズ削減は事実だがレイテンシ短縮を意味しない。 per-op A/B ベンチマーク必須。
>
> **Matcha-TTS / Kokoro-82M の評価射程:** 各論文の比較対象に対する相対値で 2025-2026 の新興軽量 TTS (KittenTTS 等) は含まれない。 Kokoro v1.0 の 8 言語数値カバーは**品質パリティは英語のみ確認済み**。

---

## 統合優先度マトリクス (31 アクション)

| # | 施策 | 軸 | 期間 | 難度 | 効果 | リスク | 確信度 | 統合元 |
|---|------|----|------|------|------|--------|--------|--------|
| A-1 | **iSTFTNet2-MB** decoder backbone 置換 | モデル | 中期 | M | 高 (CPU 2-5x) | 中 | high 3-0 | 06-03 #1 ★★★ |
| A-2 | **MS-Wavehax** streaming vocoder | モデル | 中期 | M | 中 (低レイテンシ) | 中 | high 3-0 | 06-03 #3 ★★ |
| A-3 | **ZSE-VITS 型 prosody predictor** | モデル | 短期 | M | 中 (感情・韻律) | 低 | high 3-0 | 06-03 #6 ★★ |
| A-4 | **Matcha-TTS OT-CFM** decoder プロトタイプ | モデル | 中期 | L | 高 | 中 | high 3-0/2-1 | 06-03 #7 + 06-15 #22 |
| A-5 | **StyleTTS2 + iSTFTNet** (Kokoro 路線) プロトタイプ | モデル | 中期 | L | 高 | 中 | high 3-0 | 06-15 #23 |
| A-6 | ECAPA2 speaker encoder (☆ 条件付き) | モデル | 中期 | L | 中 (未証明) | 中 | high 3-0 | 06-03 #8 |
| B-1 | Android NNAPI EP 配線 | ランタイム | 短期 | M | 高 | 低 | high 3-0 | 06-15 #4 |
| B-2 | Android XNNPACK EP 配線 | ランタイム | 短期 | M | 高 | 低 | high 3-0 | 06-15 #5 |
| B-3 | iOS XNNPACK EP 配線 (xcframework 拡張) | ランタイム | 短期 | M | 高 | 低 | high 3-0 | 06-15 #6 |
| B-4 | INT8 weight-only quantization (配布サイズ最適化) | ランタイム | 短期 | M | 中 | 中 | high 3-0 | 06-15 #7 |
| B-5 | 量子化品質回帰測定スイート (MOS/PESQ/STOI per-language) | ランタイム | 短期 | M | 中 | 低 | 派生 | 06-15 #8 |
| B-6 | INT4/UInt4 block-wise quantization | ランタイム | 中期 | M | 中 | 中 | high 3-0 | 06-15 #19 |
| B-7 | BitTTS 1.58-bit 三値量子化 (☆ mobile footprint 条件付き) | ランタイム | 中期 | M | サイズ 83%減 / 速度効果なし | 中 | high 3-0 | 06-03 #9 |
| B-8 | WASM default / WebGPU opt-in dual-track | ランタイム | 中期 | M | 中 | 中 | high 3-0 | 06-15 #20 |
| B-9 | WebGPU ブラウザ matrix 再検証 + ベンチマーク | ランタイム | 短期 | S | 低 | 低 | 派生 | 06-15 #21 |
| C-1 | **軽量 per-word LID** (Latin 系) | 多言語 | 短期 | M | code-switch 誤読修正 | 低 | high 3-0 | 06-03 #2 ★★★ |
| C-2 | CML-TTS DE 統合 → 7lang model | 多言語 | 短期 | M | 高 | 低 | high 3-0 | 06-15 #9 |
| C-3 | CML-TTS IT 統合 → 8lang model | 多言語 | 短期 | M | 高 | 低 | high 3-0 | 06-15 #10 |
| C-4 | CML-TTS NL/PL 統合 → 10lang model | 多言語 | 中期 | M | 中 | 中 | high 3-0 | 06-15 #11 |
| C-5 | g2ps Vietnamese G2P | 多言語 | 短期 | M | 中 | 低 | high 3-0 | 06-15 #12 |
| C-6 | g2ps Hindi G2P | 多言語 | 短期 | M | 中 | 低 | high 3-0 | 06-15 #13 |
| C-7 | g2ps Turkish G2P | 多言語 | 短期 | M | 中 | 低 | high 3-0 | 06-15 #14 |
| C-8 | g2ps Tier-2 拡張 (AR/BN 優先、 TL/SW は G2P-only) | 多言語 | 中期 | M | 中 | 中 | high 3-0 | 06-15 #15 / G-D8 |
| C-9 | HomoFast-eSpeak 型 homograph 統計層 (EN) | 多言語 | 中期 | M | 中 | 低 | high 3-0 | 06-15 #16 |
| C-10 | HomoFast-eSpeak 型 homograph 統計層 (ZH/JA) | 多言語 | 中期 | M | 中 | 低 | 派生 | 06-15 #17 |
| C-11 | LatPhon / CharsiuG2P neural G2P (☆ G-B4 で見送り推奨) | 多言語 | 保留 (v1.17+ 再評価) | L | (G-B4 で見送り推奨) | 中 | high 3-0 | 06-03 #5 / G-B4 |
| D-1 | OpenAI TTS contract 完全準拠 (`tts-1`/`tts-1-hd` alias) | エコシステム | 短期 | S | 高 | 低 | high 3-0 | 06-15 #1 |
| D-2 | `/v1/audio/speech` voice alias (alloy/echo/nova→speaker_id) | エコシステム | 短期 | S | 高 | 低 | high 3-0 | 06-15 #2 |
| D-3 | `/v1/audio/speech` response_format 拡張 (mp3/opus/aac/flac/pcm) | エコシステム | 短期 | S | 中 | 低 | high 3-0 | 06-15 #3 |
| D-4 | HF model cards 整備 + voice marketplace 露出 | エコシステム | 短期 | S | 中 | 低 | high 3-0 | 06-15 #18 |
| E-1 | **データ効率・FT recipe ガイダンス** (即適用可) | 運用 | 短期 | S | 学習設計最適化 | 無 | high 3-0 | 06-03 #4 ★★ |

凡例: 期間 短期=3〜6 ヶ月 / 中期=〜1 年。 難度 S=数日〜数週、 M=数週〜数ヶ月、 L=数ヶ月 (cross-runtime 統合 + 再学習)。 統合元 `06-03 #N` = 2026-06-03 版 finding 番号、 `06-15 #N` = 2026-06-15 版 action 番号。

---

## A. 音声品質 / モデル研究

### A-1. iSTFTNet2-MB decoder backbone 置換 — 最有力増分 ★★★

【統合元: 06-03 #1】

> [!IMPORTANT]
> **実装済み「MB-iSTFT-VITS」とは別論文・別アーキテクチャ (名前が紛らわしい)。**
> piper-plus の `mb_istft.py` は Kawamura et al. **"MB-iSTFT-VITS" (ICASSP 2023, arXiv:2210.15975)** で `Conv1d`/`ConvTranspose1d` のみ (`Conv2d` を import すらしていない) の **1D CNN backbone**。
> 本項の iSTFTNet2 (Kaneko et al., NTT, **arXiv:2308.07117**) は別論文で、 核心の **1D-2D CNN backbone (2D CNN でスペクトログラム時間×周波数構造をモデル化)** は piper-plus に**存在しない**。
> **両者の共通点は「multi-band 生成 + iSTFT + PQMF」という出力段の枠組みだけ。**
> → 「multi-band + iSTFT の枠組みは対応済み、 backbone を 1D CNN → 1D-2D CNN に置換するのが未対応の改善余地」。

- **主張:** iSTFTNet2 は 1D→2D 変換を前倒しし 2D CNN でスペクトログラム構造をモデル化、 神経時間アップサンプリングを 8x 削減 (x64→x8)。 出力段の「multi-band + iSTFT + PQMF」枠組みは piper-plus の MB-iSTFT-VITS と共通だが、 **backbone を 1D CNN から 1D-2D CNN に置換する点が新規**。
- **数値 (LJSpeech, Intel i7-12700H シングルスレッド CPU 実測):** `iSTFTNet2-MB` は **RTF 0.011 (HiFi-GAN V2 の 21%)、 MOS 4.25、 0.83M params**。 1D 版 iSTFTNet-MB (MOS 4.05) を MOS・cFW2VD 両方で有意に上回る。 `iSTFTNet2-Small` は RTF 0.018 / MOS 4.22 (HiFi-GAN V2 と統計的に区別不可, p>0.05) / 0.79M params。
- **コスト・リスク (M):** 論文はスタンドアロン vocoder としての実証で、 end-to-end TTS への拡張は著者も future work としている。 end-to-end VITS2 decoder への統合＋再学習が必要。 2D conv が ONNX op coverage を変える可能性 (7 ランタイム検証必須)。
- **piper-plus 該当箇所:** `src/python/piper_train/vits/mb_istft.py`, `src/python/piper_train/vits/stft_onnx.py`
- **出典:** [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) (Kaneko et al., Interspeech 2023, NTT＝iSTFTNet 原著者) / 確信度 high・3-0 全主張

### A-2. MS-Wavehax — 低レイテンシ streaming vocoder ★★

【統合元: 06-03 #3】

- **主張:** sub-80ms チャンクの低レイテンシ条件で最高スループット (最低 RTF)、 シングル CPU スレッド (AMD EPYC 7302) / ONNX Runtime 上で HiFi-GAN・iSTFTNet・Vocos・**MS-iSTFTNet (piper-plus MB-iSTFT の直接対応物) を凌駕**。
- **数値:** **0.332M params = HiFi-GAN V1 の 2.4%** という極小サイズ。 MOS は自然音声に匹敵 (causal/non-causal 両条件)。 全比較 vocoder は torch.stft/istft を conv 実装に置換して ONNX 化＝**piper-plus が `vits/stft_onnx.py` で既に使っている手法と同一** (ONNX export リスク低減)。
- **コスト・リスク (M):** スタンドアロン vocoder のため統合が必要。 **優位性は低レイテンシ領域に限定** (大きいチャンクでは 2D conv のデータ転送増で Vocos が勝つ)。 piper-plus の text-splitter streaming モードが使う領域とは合致。 dual vocoder 構成 (既存 MB-iSTFT を通常モードに温存しつつ MS-Wavehax を streaming 専用に追加) と保守負荷 / モード切替境界の詳細は companion §3.4-3.6 を参照。
- **piper-plus 該当箇所:** `src/python/piper_train/vits/stft_onnx.py`, `src/python_run/piper/text_splitter.py`
- **出典:** [arXiv 2506.03554](https://arxiv.org/html/2506.03554) (Yoneyama et al., Interspeech 2025, Wavehax 著者) / 確信度 high・3-0/2-1

### A-3. ZSE-VITS 型 prosody predictor — 加算的拡張 ★★

【統合元: 06-03 #6】

- **主張:** VITS 系バックボーンに pitch/energy/duration を明示モデル化する**別個の prosody predictor を追加**し、 感情コーパスで**それ単体を fine-tune**すれば、 話者音色と独立に style を学習・調整できる (ZSE-VITS は VITS を**置換ではなく拡張**)。 piper-plus の既存 `prosody_features (A1/A2/A3)` 路線とも親和的な additive パターン。
- **DRAFT PR #355 との関係:** 感情条件 TTS (Style Vector + PE-A) と棲み分け。 #355 は global style 注入、 本項は時系列 prosody (pitch/energy/duration) 予測で**直交**。 両方の併用も可能。
- **コスト・リスク (M、 低リスク):** 加算的モジュールで低リスク。 既存 VITS パイプラインを破壊しない。
- **piper-plus 該当箇所:** `src/python/piper_train/vits/models.py` (prosody_features), `--prosody-dim`
- **出典:** [MDPI Electronics 2023 (2079-9292/12/4/820)](https://www.mdpi.com/2079-9292/12/4/820) (ZSE-VITS) / 確信度 high・3-0

### A-4. Matcha-TTS OT-CFM flow-matching decoder プロトタイプ ★

【統合元: 06-03 #7 + 06-15 #22】

- **主張:** Matcha-TTS は optimal-transport conditional flow matching (OT-CFM) ベースの ODE decoder。 probabilistic / non-autoregressive / 外部 aligner 不要、 **〜18-21M params で memory footprint が最小**、 VITS と MOS competitive をより少ない synthesis step で達成。
- **数値:** 比較系中で**最小メモリ**、 長文で最速級、 リスニングテストで**最高 MOS (MAT-10 3.84 vs VITS 3.71, LJSpeech)**、 **ONNX export 可能** (export スクリプト・onnxruntime CPU 推論 documented)、 デフォルト **5 ODE ステップ** (`n_timesteps=5`)。 flow-matching ファミリー中で唯一 CPU 適合の可能性。
- **piper-plus との適合性:** AR-LM オーバーヘッド (XTTS v2 / CosyVoice 2 / VALL-E) を避けつつ品質上限を引き上げる軽量 CPU エッジ路線。 MB-iSTFT-VITS2 の後継候補。
- **コスト・リスク (L):** 5 ステップは export 時に ONNX グラフに焼かれる (runtime 入力ではない)。 ⚠️ **VITS との MOS 差は統計的に有意でない** (α=0.05)、 かつ LJSpeech は弱い単一話者ベンチ＝piper-plus の多言語多話者設定での品質向上は**未証明**。 ODE solver の ONNX op coverage を 7 ランタイムで検証必要。 prosody_features (A1/A2/A3) / WavLM Discriminator / EMA / emb_lang 自動統一の各機構が新 decoder に転移できるか未確認 (open question G-A2)。
- **piper-plus 該当箇所:** `src/python/piper_train/vits/{models,mb_istft}.py`、 `src/python/piper_train/export_onnx.py`、 全 7 ランタイムの inference path
- **出典:** [arXiv 2309.03199](https://arxiv.org/abs/2309.03199) / [Matcha-TTS GitHub](https://github.com/shivammehta25/Matcha-TTS) (Mehta et al., ICASSP 2024) / 確信度 high・3-0 (OT-CFM / probabilistic-NAR / aligner-free) ・2-1 (smallest footprint 主張)

### A-5. StyleTTS2 + iSTFTNet (Kokoro-82M 路線) プロトタイプ ★

【統合元: 06-15 #23】

- **主張:** Kokoro-82M (Apache-2.0、 82M params、 decoder-only、 diffusion 不使用) は **StyleTTS2 アーキ + iSTFTNet vocoder** の組み合わせで HF TTS Arena 1 位 (XTTS v2 467M / MetaVoice 1.2B を破る、 2025 年時点)。
- **piper-plus との適合性:** **iSTFTNet vocoder は piper-plus にすでに兄弟実装** (MB-iSTFT-VITS2) があるため vocoder 側の DNA 共有。 ライセンスは Apache-2.0 で piper-plus の商用フレンドリースタンスと一致。 A-4 (Matcha-TTS) と**並列に走らせる**ことで「flow matching 系」「StyleTTS2 系」の両方の SOTA を内部 A/B 可能。
- **コスト・リスク (L):** StyleTTS2 の training は style-encoder-heavy で single-speaker FT パイプラインを複雑化する可能性。 Kokoro-82M v1.0 は数値上 8 言語カバーだが **英語以外の品質は未確認** (caveat 参照)。
- **piper-plus 該当箇所:** 新規 decoder branch、 `src/python/piper_train/speaker_encoder/` (StyleTTS2 style encoder と統合可能性)
- **出典:** [Hugging Face Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) / [arXiv 2306.07691](https://arxiv.org/abs/2306.07691) (StyleTTS2) / [arXiv 2203.02395](https://arxiv.org/abs/2203.02395) (iSTFTNet) / 確信度 high・3-0 全主張

> [!NOTE]
> **3 アーキトラック並走戦略:** **A-1 (iSTFTNet2-MB)** は backbone のみ置換する low-risk 増分、 **A-4 (Matcha-TTS)** と **A-5 (StyleTTS2)** はデコーダーファミリーごと刷新する high-ceiling 候補。 3 つを**競合させずに並列**に走らせ、 同一 6lang データセットで 3-6 ヶ月後に MOS / RTF / footprint A/B で勝者を v1.16.x の主力 decoder に昇格、 という運用を推奨。 単一の architecture migration に賭けるリスクを下げる。

### A-6. ECAPA2 speaker encoder — ☆ 条件付き (contract 変更が重い)

【統合元: 06-03 #8】

- **主張:** ECAPA-TDNN と同じ IDLab グループの hybrid 1D/2D CNN speaker encoder (2D-conv Local Feature Extractor + 周波数方向 Squeeze-Excitation + TDNN Global Feature Extractor)、 **192 次元** embedding。 voice cloning の品質向上候補。
- **コスト・リスク (L):** ⚠️ **literal drop-in ではない**。 `src/python/piper_train/speaker_encoder/ecapa_tdnn.py:227` が `emb_dim=256` をハードコードし、 **7 runtime 全てが 256 次元の `speaker_embedding` テンソル契約を pin**。 192 次元 ECAPA2 採用は**モデルの speaker-embedding 経路の再学習＋cross-runtime contract 更新**を要する (parity コスト大)。
- **DRAFT PR #222 (Zero-shot) との関係:** #222 は CAM++ 192-dim encoder を導入予定で、 ECAPA2 への移行とは別系統。 #222 のマージ後に ECAPA2 → CAM++ の two-encoder comparison を行うのが筋。
- **piper-plus 該当箇所:** `src/python/piper_train/speaker_encoder/ecapa_tdnn.py:227`, `docs/reference/speaker-encoder-contract.md`
- **出典:** [arXiv 2401.08342](https://arxiv.org/pdf/2401.08342) (ECAPA2, ASRU 2023) / 確信度 high・3-0

### (非推奨参照) F5-TTS / XTTS v2 / CosyVoice 2 — off-concept

【統合元: 06-03 + 06-15 共通】

- **F5-TTS:** 335.8M params、 16-32 NFE、 別 Vocos vocoder、 看板 RTF 0.15 は明確に GPU (RTX 3090) 値。 piper-plus の single-pass CPU/on-device (end-to-end 〜27ms) と根本的に相反。 ただし **phonemizer-independent / alignment-free 設計** は多言語 code-switching の G2P 課題に対する方向性として参考になる。
- **XTTS v2 (467M):** GPU 4GB 要、 piper-plus の CPU エッジ路線と相反。
- **CosyVoice 2:** LLM-based、 GB 規模、 同じく off-concept。
- 出典: [F5-TTS arXiv 2410.06885](https://arxiv.org/pdf/2410.06885) (ACL 2025)

---

## B. ランタイム性能 / エッジ展開

### B-1〜B-3. モバイル EP の網羅 (Android NNAPI + XNNPACK / iOS XNNPACK) ★★★

【統合元: 06-15 #4-6】

- **主張:** ONNX Runtime 公式ガイドは「量子化モデルは CPU EP、 非量子化は XNNPACK EP」を推奨。 NNAPI は Android 8.1+ (9+ 推奨)、 XNNPACK は Maven (Android) / CocoaPods (iOS) で配布。
- **DRAFT PR #386 との関係:** #386 は **CUDA / CoreML / DirectML / OpenVINO / CPU** の 5 EP をカバー、 **モバイル特化の NNAPI / XNNPACK は対象外**。 本施策は #386 と**直交する net-new スコープ**。
- **コスト・リスク (M、 全 3 件):** 既存の iOS xcframework + SPM、 Android G2P (Kotlin) インフラがあるため C-API レイヤーへの EP 配線は incremental。 加算的 EP のため CPU fallback で常時動作 → 互換性影響は低。
- **piper-plus 該当箇所:** `src/cpp/piper_plus.h` / `piper_plus_c_api.cpp`、 `cmake/PiperPlusShared.cmake`、 iOS toolchain (`cmake/ios.toolchain.cmake`)
- **出典:** [ONNX Runtime mobile tutorial](https://onnxruntime.ai/docs/tutorials/mobile/) (3-0 全主張)

### B-4. INT8 weight-only quantization (配布サイズ最優先) ★★

【統合元: 06-15 #7】

- **主張:** ONNX Runtime opset 21 で **block-wise weight-only INT8 quantization** がネイティブ対応、 ファイルサイズは概ね 4x 削減。
- **重要な caveat:** coqui-ai/TTS Discussion #2991 で **VITS dynamic INT8 が FP32 比 2 倍以上遅くなる** 報告。 一論文では INT8 が音声生成品質を "considerably degrades" と評価。 → **配布サイズ最適化を第一目的、 レイテンシ向上は per-op A/B ベンチマークで個別測定**。 とくに ZH (声調) / JA (prosody_features A1/A2/A3) で品質回帰が出やすい。
- **コスト・リスク (M):** ツールチェーンは ORT 公式で揃っている。 リスクは品質回帰の見落とし → B-5 の測定スイートで担保。
- **piper-plus 該当箇所:** `src/python/piper_train/export_onnx.py` (新規 `--quantize int8|int4` フラグ)、 配布パッケージ metadata (PyPI / NuGet / crates.io / npm の 7 箇所)
- **出典:** [ONNX Runtime quantization docs](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) (3-0) / [coqui-ai/TTS Discussion #2991](https://github.com/coqui-ai/TTS/discussions/2991) (caveat)

### B-5. 量子化品質回帰測定スイート ★★ (B-4/B-6 の前提)

【統合元: 06-15 #8 派生】

- **主張:** 6 言語各 50 文 × { FP32, FP16 (現行), INT8, INT4, 1.58-bit } × { MOS proxy, PESQ, STOI } マトリクスを CI 化し、 品質回帰を自動検出する CI gate を追加。
- **コスト・リスク (M):** スイート構築コストはあるが、 以降の全 footprint 戦略 (B-4 / B-6 / B-7) を測定駆動にできる。 ZH 声調・JA prosody features の品質回帰を per-language で見える化する。
- **piper-plus 該当箇所:** `tools/benchmark/`、 新規 `tools/benchmark_quantization.py`、 CI workflow

### B-6. INT4/UInt4 block-wise weight-only quantization ★

【統合元: 06-15 #19】

- **主張:** ONNX Runtime opset 21 で MatMul / Gather に対し RTN / GPTQ / HQQ 系の INT4 quantization が利用可能。 smartwatch / IoT / 組込のフットプリント要件に対する最終手段。
- **コスト・リスク (M):** ツーリングは存在するが VITS 系での品質保証データは皆無。 B-5 の品質回帰テストを活用して測定駆動で進める。
- **piper-plus 該当箇所:** `export_onnx.py` の `--quantize int4`、 `docs/spec/ort-session-contract.toml`
- **出典:** [ONNX Runtime quantization docs](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) (3-0)

### B-7. BitTTS 1.58-bit 三値量子化 — ☆ mobile footprint 条件付き

【統合元: 06-03 #9】

- **主張:** 重みを {-1,0,1} に量子化＋packing (3^5=243<256 で 5 重みを 1 int8 に) で **25.66MB → 4.39MB (83%減)**。
- **重要な caveat:** **M1 Pro で RTF 0.040 vs FP32 baseline 0.042＝速度効果は実質ゼロ**、 full 量子化はむしろ**遅い (0.064)**。 著者自身「速度重視なら acoustic model のみ量子化」と助言。 素の小型 FP32 net が 0.019 RTF＝量子化版の約 2 倍速。
- **結論:** **価値は footprint であって速度ではない**。 piper-plus の on-device 高速化は、 量子化より A-1 / A-2 の vocoder 経路 (実 CPU 高速化) の方が筋が良い。 download/footprint 縮小が要る mobile 配布時のみ検討 (MOS トレードオフ: both-quantized 3.09 vs AM-only 3.30)。 INT8 (B-4) / INT4 (B-6) との比較を B-5 で行ってから判断。
- **出典:** [arXiv 2506.03515](https://arxiv.org/html/arXiv:2506.03515) (BitTTS, LY Corp, Interspeech 2025) / 確信度 high・3-0

### B-8. WASM default / WebGPU opt-in dual-track 戦略 ★

【統合元: 06-15 #20】

- **主張:** ORT Web 公式チュートリアルは WebGPU EP を「compute-intensive モデル」推奨。 piper-plus の現行 MB-iSTFT-VITS2 は軽量で WASM EP 経由のバイナリサイズ感度が高いため **WASM をデフォルト維持**、 将来の zero-shot (DRAFT #222) / 6lang 高品質モデルなど compute-heavy ケースに **opt-in WebGPU EP** を追加するのが妥当。
- **コスト・リスク (M):** npm パッケージのレイヤード EP ビルドが必要。 WebGPU 非対応ブラウザは自動的に WASM フォールバックなので互換性影響は低。
- **piper-plus 該当箇所:** `src/wasm/openjtalk-web/src/index.js`、 `src/rust/piper-wasm/`、 `package.json` (build matrix)
- **出典:** [ONNX Runtime WebGPU tutorial](https://onnxruntime.ai/docs/tutorials/web/ep-webgpu.html) (3-0 全体方針、 ブラウザ matrix は 0-3 で棄却 → B-9)

### B-9. WebGPU ブラウザ matrix 再検証 + ベンチマーク ★

【統合元: 06-15 #21 派生】

- **主張:** 本調査で「WebGPU が Chrome/Edge 安定、 Safari / iOS Safari は未確定」という主張が **0-3 で棄却**。 実装着手前に Safari Technology Preview / iOS 18 Safari / Firefox の最新サポート状況を fresh verification する短期タスクを別立て。
- **コスト・リスク (S):** ベンチ + ドキュメント整備のみ。 結果次第で B-8 の実装範囲を判断。

---

## C. 多言語 / G2P 拡張

### C-1. 軽量 per-word LID (Latin 系) ★★★

【統合元: 06-03 #2】

- **主張:** 音素化の前に単語単位の言語判定 (LID) を入れると code-switching 誤読が大幅改善。 混在テキストで **WER 42.18% (English-only) → 17.43%** (oracle LID なら 12.87%)。
- **piper-plus への直結性:** `src/python/g2p/piper_plus_g2p/multilingual.py` の 133-149 行が Basic Latin と拡張 Latin を**単一の `self._default_latin` に潰している**。 学習済みモデルに触れず `MultilingualPhonemizer` のテキスト層に追加可能。 CJK は既に script で分離済みなので、 **利得は Latin 系言語 (en/es/pt/fr/sv) に集中**。
- **既存実装との関係:** Swedish per-word LID (PR #545 で 7 ランタイム同期復旧済み、 2026-06-06 マージ。 #297 由来の Python/Rust 回帰を restore + unify) で原型は導入済み。 本項は **同パターンを en/es/pt/fr に横展開**することで、 Latin code-switching 全般を改善する次のステップ。 G-B3 (CONVERGED) の 3 段階戦略 (SSML xml:lang → char-ngram + 軽量 NN → fastText 非採用) と整合。
- **コスト・リスク (M、 低):** ⚠️ 論文の mBERT (〜700MB) は piper-plus の CPU/on-device/7-runtime parity コンセプトには重すぎる。 **fastText クラス or 小型 char-CNN の軽量 LID** に置き換える前提なら「学習済み per-word LID が script 判定に勝つ」という finding 自体は成立。
- **piper-plus 該当箇所:** `src/python/g2p/piper_plus_g2p/multilingual.py:133-149`、 既存 `sv_function_words.json` のパターン横展開
- **出典:** [arXiv 2412.19043](https://arxiv.org/pdf/2412.19043) (Handoyo et al., 2024, ITB+NAIST, IEEE) / 確信度 high・3-0

### C-2〜C-4. CML-TTS による 10lang 化 (DE / IT / NL / PL 追加) ★★★

【統合元: 06-15 #9-11】

- **主張:** CML-TTS は 7 EU 言語の LibriVox 派生コーパス (Spanish / Portuguese / Italian / Polish / Dutch / French / German)、 **計 3,233.43 時間 / 613 話者 / 24kHz / CC-BY-4.0** ([arXiv 2306.10097](https://arxiv.org/abs/2306.10097) abstract)。 piper-plus はすでに ES / FR / PT の前処理パイプライン (`tools/prepare_multilingual_dataset.py`) で CML-TTS を使用しており、 DE / IT / NL / PL の追加は**機械的なパイプライン拡張**。
- **段階展開:** C-2 (DE → 7lang) → C-3 (IT → 8lang) → C-4 (NL/PL → 10lang)。 DE はサンプル時間最大で先行、 NL/PL は時間が少ないため CSS10 / Common Voice / VoxPopuli を補助で merge する設計が必要 (C-4 のみリスク中)。
- **コスト・リスク (M, 各):** ライセンス互換 (CC-BY-4.0 → Apache-2.0 商用 OK、 ただし model weight が dataset の derivative かは legal grey zone、 G-15 参照)。 G2P 規則は IPA テーブル + post-processing で各言語数百行規模。
- **piper-plus 該当箇所:** `tools/prepare_multilingual_dataset.py`、 `src/python/g2p/piper_plus_g2p/{german,italian,dutch,polish}.py` (新規)
- **出典:** [CML-TTS Dataset (GitHub)](https://github.com/freds0/CML-TTS-Dataset) / [arXiv 2306.10097](https://arxiv.org/abs/2306.10097) / [HF datasets ylacombe/cml-tts](https://huggingface.co/datasets/ylacombe/cml-tts) (3-0 全 3 主張)

### C-5〜C-8. Tier-2 言語 G2P (g2ps Phonetisaurus FST 経由) ★★

【統合元: 06-15 #12-15】

- **主張:** uiuc-sst/g2ps は Phonetisaurus FST 形式で **100+ 言語の G2P transducers** を公開、 Vietnamese / Hindi / Arabic (複数方言) / Mongolian / Swahili / Bengali / Tagalog / Turkish を含む。
- **段階展開:** C-5 (VI) / C-6 (HI) / C-7 (TR) を短期、 C-8 で **AR / BN / TL / SW を中期** (G2P のみ、 acoustic model は当面 G2P-only パッケージで配布)。
- **G-D8 結果反映 (2026-06-15 確定):**
  - **AR (CV 91.9h CC0) / TR (CV 129.2h CC0)** → acoustic model 学習可能、 **短期で 7th/8th 言語候補**
  - **BN (CV 54.3h + SLR37 CC BY-SA 4.0)** → acoustic model 可能、 **中期で 9th 言語候補**
  - **HI (CV 15.6h、 SLR118 は NC)** → G2P のみ短期、 IndicVoices-R 精査必要 / acoustic は保留
  - **VI (CV 7.3h、 VIVOS は NC) / TL (CV 未掲載、 FLEURS 7.6h)** → **commercial-friendly audio 不足、 G2P-only パッケージとして配布**、 acoustic model は v1.17+ で再評価
- **新規性:** piper-plus の現行 8 言語は規則ベース。 g2ps は FST 形式なので **piper-plus の Phonemizer ABC への変換が必要** (drop-in ではない)。 PER は言語により 7〜45% と幅広く、 言語別の品質再検証が必要。
- **重要 caveat:** 本調査で「g2ps が Appen BABEL lexicon を出典」とする主張は **0-3 で棄却**。 g2ps の FST データ自体が asset であり、 BABEL 由来は実証なし。 つまり**ライセンス的に g2ps 本体 (Apache-2.0) のみ確認すれば再配布 OK** で、 BABEL の追加 license 確認は不要。
- **コスト・リスク (M, 各):** g2ps → 規則化 (LUT + pattern rules) の自動変換ツールを 1 つ作れば横展開可能。 7 ランタイム移植は既存パターン (JA/EN/ZH 等) で確立済み。
- **piper-plus 該当箇所:** `src/python/g2p/piper_plus_g2p/{vietnamese,hindi,turkish,arabic,bengali,tagalog,swahili}.py` (新規)、 各 G2P ランタイムへの mirror
- **出典:** [uiuc-sst/g2ps (GitHub)](https://github.com/uiuc-sst/g2ps) / [arXiv 2005.13962](https://arxiv.org/abs/2005.13962) (3-0)

### C-9〜C-10. HomoFast-eSpeak 型 homograph 統計層 (EN / ZH-JA) ★★

【統合元: 06-15 #16-17】

- **主張:** HomoFast-eSpeak (EMNLP 2025 Findings) は eSpeak 系の規則 G2P に**軽量統計レイヤー** (homograph 表 + n-gram 等) を加える設計で、 Persian benchmark で homograph accuracy を **+30.66pp (43.87% → 74.53%)**、 かつ neural 代替 Homo-GE2PE 比 **50 倍高速**で real-time を維持。
- **piper-plus への適用:** 現行 EN/ZH/JA Phonemizer は homograph をほぼ未処理 (read/lead, 行/銀行 など)。 加算的レイヤーなので既存 G2P と互換、 7 ランタイム移植も `zh_en_loanword.json` と同じ JSON ミラーパターンで横展開可能。
- **重要 caveat:** 本調査で「neural G2P は real-time TTS に impractical」という強い表現は **0-3 で棄却**。 つまり HomoFast の利点は「neural G2P を否定」ではなく「**piper-plus の既存レイテンシ予算を保ったまま regular の homograph 失敗を救う**」点として打ち出す。
- **コスト・リスク (M, 各言語):** 言語ごとの homograph 表 + 統計訓練データが必要。 EN は WikText / CMUdict variants で構築可能。 ZH は polyphone 辞書 (g2pw、 ChineseG2P)、 JA は 漢字読み分け (UniDic)。
- **piper-plus 該当箇所:** `src/python/g2p/piper_plus_g2p/{english,chinese,japanese}.py`、 新規 `data/homograph_{en,zh,ja}.json` (canonical) + 6 ランタイムミラー
- **出典:** [arXiv 2505.12973](https://arxiv.org/html/2505.12973v1) / [ACL Anthology 2025.findings-emnlp.1218](https://aclanthology.org/2025.findings-emnlp.1218/) (3-0)

### C-11. LatPhon / CharsiuG2P — 神経 G2P (精度↑＋新言語) ★ (中期実験)

【統合元: 06-03 #5】

- **主張:** `LatPhon` は単一 7.5M-param Transformer (〜30MB fp32, **on-device 明示設計**) で en/es/fr/it/pt/ro をカバー＝**piper-plus の es/pt/fr/en と一致**。 ipa-dict で平均 **PER 3.5%** (580M ByT5 の 5.4% を上回り、 言語別 WFST の 3.2% に肉薄)。 piper-plus 関連言語では更に強い (ES 0.30% / FR 0.57% / PT 0.86%)。 `CharsiuG2P` (ByT5, MIT, 〜100 言語) は**新言語の fine-tune warm-start** (例: Albanian 51.1%→11.7% を 1800 語で)＝`/add-language` workflow に有用。
- **C-9/C-10 (HomoFast) との関係:** **直交**。 HomoFast は既存 rule G2P の homograph fix、 LatPhon は seq2seq Transformer 置換。 両方を併走させ、 言語ごとに「rule + homograph」vs「neural」を A/B で評価する戦略が妥当。
- **コスト・リスク (L):** 両者とも IPA 出力なので piper-plus の **PUA mapping が必要**、 seq2seq Transformer なので現行の rule/dictionary phonemizer とは別物＝drop-in ではない。 **7 runtime への移植が parity 維持に必須 (重い)**。 ⚠️ CharsiuG2P の zero-shot (未知言語) は使い物にならない (未知 script で PER >100%)。 価値は fine-tune warm-start のみ。
- **piper-plus 該当箇所:** `src/python/g2p/piper_plus_g2p/{spanish,portuguese,french,english}.py`、 `/add-language` skill
- **出典:** [arXiv 2509.03300](https://arxiv.org/pdf/2509.03300) (LatPhon, USP, 2025), [arXiv 2204.03067](https://arxiv.org/abs/2204.03067) (CharsiuG2P, Interspeech 2022) / 確信度 high・3-0

---

## D. エコシステム / 採用

### D-1〜D-3. OpenAI TTS 完全互換化 (Open WebUI / LibreChat への drop-in) ★★★

【統合元: 06-15 #1-3】

- **主張:** OSS チャット UI のデファクトとなった Open WebUI / LibreChat / openedai-speech は OpenAI TTS API のスキーマ (`tts-1` / `tts-1-hd` モデル名、 `alloy/echo/nova/onyx/fable/shimmer` voice 名、 `response_format=mp3|opus|aac|flac|wav|pcm`、 `speed`) を期待。 piper-plus は openedai-speech ecosystem で**すでに「CPU フレンドリーな選択肢」として明示的に位置付けられている** (Coqui XTTS v2 は 4GB GPU 要、 Parler-TTS は実験的の対立軸)。
- **3 つのサブ施策:**
  - **D-1** モデル alias: `tts-1` → MB-iSTFT-VITS2 高速モデル、 `tts-1-hd` → 6lang 高品質モデルへのマッピングを設定ファイルで提供
  - **D-2** voice alias: `alloy/echo/nova/onyx/fable/shimmer` → piper-plus speaker_id 0-5 のデフォルトマッピング + ユーザ設定上書き
  - **D-3** `response_format` 拡張: 現行 wav に加え mp3 / opus / aac / flac / pcm を libsndfile + libopus / libmp3lame 経由で対応
- **コスト・リスク (S, 全 3 件):** piper-plus は **すでに `/v1/audio/speech` と `/v1/models` を実装済み** (CLAUDE.md 記載) → contract-completion 作業であり green-field ではない。 audio codec 依存追加は Docker イメージのみで影響限定的。
- **piper-plus 該当箇所:** `docker/python-inference/inference.py`、 設定ファイル (`voice_aliases.yaml` 新規)
- **出典:** [Open WebUI openedai-speech 統合ガイド](https://docs.openwebui.com/features/chat-conversations/audio/text-to-speech/openedai-speech-integration/) / [matatonic/openedai-speech](https://github.com/matatonic/openedai-speech) (3-0 contract / 2-1 piper CPU 位置付け)

### D-4. Hugging Face model cards 整備 + voice marketplace 露出 ★

【統合元: 06-15 #18】

- **主張:** Hugging Face Hub の model card ベストプラクティス (License、 Intended Use、 Training Data、 Limitations、 Evaluation の 5 セクション必須) を piper-plus の HF 配布 (`ayousanz/piper-plus-base` 他) に適用。 Wyoming / Open WebUI / LibreChat の voice marketplace から逆探索される際の SEO 効果がある。
- **新規性:** 現行は HF 配布のメタデータが不揃い (ORG / language / quality タグ等)。 Hugging Face 公式の **model card annotated** スキーマに準拠することで HF Spaces / `/v1/models` API での絞り込み検索性が向上。
- **コスト・リスク (S):** ドキュメント作業のみ。 既存モデルの再配布不要 (metadata 更新のみ)。
- **piper-plus 該当箇所:** 各 HF repository の `README.md` (model card)、 `docs/contributing/model-cards.md` (新規ガイド)
- **出典:** [HF model cards docs](https://huggingface.co/docs/hub/en/model-cards) / [model-card-annotated](https://huggingface.co/docs/hub/en/model-card-annotated) (3-0)

---

## E. 運用ガイダンス (即適用可)

### E-1. データ効率・FT recipe ガイダンス ★★

【統合元: 06-03 #4】

- **主張 (低リソース言語/話者適応):**
  1. 総データ固定なら **「話者数を増やす」より「対象話者の発話数を増やす」方が話者類似度に有効**
  2. 少数 new-speaker データの FT は **未知話者への汎化を改善しない** (zero-shot と同等)
  3. **〜20 サンプルの FT は overfit しやすい**
- **piper-plus への含意:** 既存の**つくよみちゃん 100 サンプル FT は論文と整合** (最悪ケース言語で〜100 が最適、 20 は overfit)。 `/add-language` のデータ収集方針＝「話者あたり発話数を優先、 最低 〜100 サンプル、 単一話者 FT に未知話者汎化を期待しない (それには事前学習の話者多様性が必要)」。
- **コスト・リスク (S, 無):** アーキ変更なし、 運用ガイダンス。 SSL-based TTS の知見なので絶対値は VITS2 に過度一般化しない。
- **出典:** [arXiv 2406.08911](https://arxiv.org/html/2406.08911) (Gong et al., Interspeech 2024, Edinburgh/NII) / 確信度 high・3-0/2-1

---

## F. 棄却された主張 (両調査統合 / 採用しない)

実装着手時の方針判断ミスを防ぐため、 両調査で 3 票 (or 2 票) で棄却された主張を記録する。

### F-1. 2026-06-03 棄却 (1 件)

| 棄却された主張 | 票 | ソース | 影響 |
|---------------|-----|--------|------|
| ZSE-VITS が **TitaNet** を speaker encoder として差し替えて zero-shot voice cloning を達成、 ECAPA-TDNN の直接代替になる | 1-2 | [MDPI 2079-9292/12/4/820](https://www.mdpi.com/2079-9292/12/4/820) | A-6 (ECAPA2) 検討時にこの TitaNet 差し替え路線を根拠にしないこと |

### F-2. 2026-06-15 棄却 (6 件)

| 棄却された主張 | 票 | ソース | 影響 |
|---------------|-----|--------|------|
| ORT は RNN/transformer に dynamic、 CNN に static quantization を推奨 | 0-3 | [ORT quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) | VITS hybrid アーキの量子化選択ルールは公式に存在しない。 per-op 実測必須 (B-5) |
| WebGPU EP は Chrome/Edge 全 OS 安定、 Safari は flag のみ | 0-3 | [ORT WebGPU](https://onnxruntime.ai/docs/tutorials/web/ep-webgpu.html) | ブラウザ matrix は実装着手時に fresh verification (B-9) |
| g2ps の G2P transducers は Appen BABEL lexicon 由来 | 0-3 | [g2ps](https://github.com/uiuc-sst/g2ps) | g2ps 本体の Apache-2.0 のみ確認すれば再配布 OK、 BABEL license 確認不要 (C-5〜C-8 リスク低減) |
| 規則 G2P は neural G2P より桁違いに高速で neural は real-time に impractical | 0-3 | [HomoFast paper](https://arxiv.org/html/2505.12973v1) | 「neural G2P 否定」ではなく「既存レイテンシ予算保持」と整理 (C-9/C-10 の根拠) |
| 音韻類似度 (≠言語系統) が cross-lingual transfer のソース言語選択基準 | 0-3 | [arXiv 2501.06810](https://arxiv.org/pdf/2501.06810) | 言語追加時のソース言語選択は別の根拠が必要 |
| 音韻類似ソース言語選択で monolingual 比 +55.6% phoneme recognition、 大規模 SSL を上回る | 1-2 | 同上 | 低リソース言語拡張時のクロスリンガル戦略は未確定 |

---

## G. オープンクエスチョン (両調査統合) — Phase 4 deep-research で全件分類済 (2026-06-15)

> **分類カテゴリ:** **RESOLVED** = 1 次ソースで完全に解決 / **CONVERGED** = 戦略・パターンは確定、 残りは piper-plus 固有 implementation detail / **IRREDUCIBLE** = 文献調査では closure 不能、 PoC / 実機測定が必須。
> companion ドキュメント [`decoder-upgrades-istftnet2-and-mswavehax.md`](decoder-upgrades-istftnet2-and-mswavehax.md) §2.5 と同 workflow で実施。 全 **20** オープンクエスチョン (本表 9 件 + companion 11 件 = Q10〜Q20) を網羅的に分類。

### G-A. アーキ系 (06-03 由来)

#### G-A1. iSTFTNet2-MB / MS-Wavehax の統合後性能保持 — **IRREDUCIBLE**

end-to-end MB-iSTFT-VITS2 に decoder として統合しても CPU RTF/MOS は保たれるか?

- **状態:** companion Q13 とほぼ重複。 statistical advantage の end-to-end 転移は zero prior art、 PoC 必須。
- **代替路線確定:** FLY-TTS (Interspeech 2024、 MOS 4.12、 ConvNeXt × 6 + iSTFT) が iSTFTNet2 失敗時の保険として並走候補。

#### G-A2. Matcha-TTS / flow-matching decoder の品質ヘッドルーム — **CONVERGED**

- **Phase 4 確定 (2 ラウンド調査):**
  - 多話者多言語 flow-matching TTS の公開ベンチ複数登場 (Matxa-TTS Catalan 47 話者 / 27h、 Indigenous 3 言語、 F5-TTS 95Kh、 Voicebox 6 言語 60Kh)。 VITS 比でヘッドルーム共通報告 (clarity / intonation 改善)。
  - **しかし piper-plus の 6lang/571 話者/CPU 27ms 条件には届かない**: Matxa-TTS 最適化後でも RTF 0.09 (Xeon Platinum 8480+ 56C/20 thread)、 piper-plus 想定の Xeon E5-2650 v4 (12C) では 4-5x slowdown 想定。
  - **Matcha duration predictor は話者埋め込み欠如**で 571 話者では致命的、 VITS DP 流用が前提で transplant コスト大。
  - **Shallow Flow Matching** (arXiv 2505.12226) で NFE 60% 削減 + UTMOS/WER/SIM 改善 → 中期注目。
- **主要 1 次ソース:** [Matxa-TTS CPU 最適化 (BSC)](https://medium.com/@mllopart.bsc/optimizing-a-multi-speaker-tts-model-for-faster-cpu-inference-part-1-165908627829) / [alphacephei Matcha notes](https://alphacephei.com/nsh/2025/01/03/matcha-tts-notes.html) / [Shallow Flow Matching arXiv 2505.12226](https://arxiv.org/abs/2505.12226)
- **piper-plus への含意:** 短期は MB-iSTFT-VITS2 維持 + WavLM disc / DP 改善で漸進。 中期は Shallow Flow Matching の piper-plus 規模検証を待ち、 GPU 用途は opt-in path として隔離検討。 **A-4 (Matcha) と A-5 (StyleTTS2) の並走判断はこれを踏まえて慎重に**。

### G-B. G2P 系 (06-03 由来)

#### G-B3. 軽量 per-word LID — **CONVERGED**

- **Phase 4 確定 (2 ラウンド調査):**
  - **fastText lid.176.ftz (917KB) 直採用は非推奨**: 公式・GlotLID とも「短文 (<4 words) で精度低下」を明示。
  - **隣接ドメインに on-device 実証あり:** Apple Natural Language framework (bi-LSTM 4MB、 iOS QuickType で本番稼働、 Latin 1-2 words で誤り 15-60% 削減) / Google CLD3 (char-ngram + small NN、 Chromium 内) / lingua-rs (Rust 75 言語、 German 73.9%) / **W3C SSML 1.1 §3.1.13** が `xml:lang` per-word を公式仕様化。
  - 業界 baseline: Romance languages 単語単位 70-80% 帯。
- **主要 1 次ソース:** [Apple ML Research bi-LSTM](https://machinelearning.apple.com/research/language-identification-from-very-short-strings) / [google/cld3](https://github.com/google/cld3) / [lingua-rs](https://github.com/pemistahl/lingua-rs) / [W3C SSML 1.1](https://www.w3.org/TR/speech-synthesis11/)
- **piper-plus への含意 (戦略 3 段階):**
  1. **W3C SSML `xml:lang` per-word を先に実装** — SSML 経路でユーザー明示制御、 実装コスト最小
  2. **char-ngram + 軽量 NN を ONNX 1 ファイルで Rust canonical** — 他ランタイムは ORT 経由で共有 (Apple/CLD3 パターン)
  3. **fastText lid.176.ftz は非採用** — 6 ランタイム port コスト過大

#### G-B4. neural G2P の 7 ランタイム移植 net 効果 — **CONVERGED (採用見送り推奨)**

- **Phase 4 確定 (2 ラウンド調査):**
  - **LatPhon (7.5M / 30MB)** はカバー範囲が en/es/fr/it/pt/ro に限定 → piper-plus 8 言語 (ja/zh/ko/sv 欠) で rule-based 併用必須 → 保守単純化にならない。 MIT release は arXiv accept 後。
  - **CharsiuG2P (ByT5)**: 公式 ONNX 非提供、 コミュニティ ONNX (OpenVoiceOS) も Python+transformers tokenizer 必須・greedy decode 限定。
  - **隣接事例 (Kokoro / Misaki / Kokoros) でも 7 ランタイム neural G2P parity 達成例なし**。
  - **W3C SSML/PLS** は IPA/SAMPA の output alphabet contract のみ規定 → neural vs rule の選択は標準化からの外圧なし。
- **主要 1 次ソース:** [LatPhon arXiv 2509.03300](https://arxiv.org/abs/2509.03300) / [hexgrad/misaki](https://github.com/hexgrad/misaki) / [lucasjinreal/Kokoros](https://github.com/lucasjinreal/Kokoros) / [phoonnx](https://github.com/TigreGotico/phoonnx)
- **piper-plus への含意:** **採用見送り推奨**。 業界の Kokoro エコシステムも 2026 時点で「neural G2P + 7 ランタイム parity」を達成できておらず、 piper-plus が先行採用するメリットは薄い。 現行の rule-based + JSON 辞書 (ZH-EN loanword / Swedish LID) を canonical + CI mirror gate で締める方針が SOTA と整合。 **統合レポート C-11 の優先度を下げる**。

### G-C. ランタイム系 (06-15 由来)

#### G-C5. 量子化品質回帰の実測値 — **IRREDUCIBLE**

- INT8 / INT4 / FP16 で piper-plus MB-iSTFT-VITS2 6lang モデルの per-language MOS / PESQ / STOI ドロップは未測定。 特に tonal な ZH と pitch-sensitive な JA prosody (A1/A2/A3) で劣化が出やすい。
- **状態:** B-5 測定スイートが行うべき実機ベンチ。 piper-plus 固有測定が必須。 一般則は companion §2.5 Q14 で確定済。

#### G-C6. Matcha / StyleTTS2 アーキ移行コスト — **IRREDUCIBLE**

- 既存の prosody_features (A1/A2/A3)、 WavLM Discriminator、 EMA、 FP16 ONNX、 emb_lang 自動統一の各機構がそのまま転移できるか?
- **状態:** piper-plus 内部実装との転移性は **3 ヶ月の small-scale ablation (1 言語 / 100k step)** で初めて判明。 PoC 必須。 G-A2 の Matcha 知見と組み合わせて Phase 1 で設計するのが妥当。

#### G-C7. WebGPU ブラウザサポート (2026 中盤) — **RESOLVED**

- **Phase 4 確定 (1 ラウンドで RESOLVED):**
  - **Safari 26.0 (2025-09)**: macOS Tahoe 26 / iOS 26 / iPadOS 26 / visionOS 26 で default 有効化、 26.2 で WebXR 統合、 **26.3 (2026-02-11)** で Zstd / visionOS 改善、 26.4 / 26.5 で漸進
  - **Firefox**: 141 (2025-07-22) で Windows 出荷、 145 で Apple Silicon macOS (Tahoe 26+)、 147 (2026-01-13) で Apple Silicon older macOS、 **148/149/150 (2026-02〜04)** で継続出荷、 Intel Mac / Linux / Android は 2026 後半ロードマップ
  - **Chrome/Edge**: 113 (Win/Mac/ChromeOS) 以来安定、 Android 12+ from v121、 Linux Intel Gen12+ v144
  - **普及率 (caniuse 2026-02 時点)**: desktop ~87% / mobile ~71% (Firefox stable は default-off で global ~82%、 2026-06-15 時点で再測定推奨)
  - **ORT Web WebGPU EP**: WASM 比で大規模モデル 10-19x 高速 (SAM encoder 19x / MiniLM batch=32 で 17.82x)、 軽量モデルではアドバンテージ縮小
- **主要 1 次ソース:** [gpuweb Implementation Status](https://github.com/gpuweb/gpuweb/wiki/Implementation-Status) / [WebKit Safari 26](https://webkit.org/blog/16993/news-from-wwdc25-web-technology-coming-this-fall-in-safari-26-beta/) / [Mozilla Gfx Firefox 141](https://mozillagfx.wordpress.com/2025/07/15/shipping-webgpu-on-windows-in-firefox-141/) / [ORT Web WebGPU](https://onnxruntime.ai/docs/tutorials/web/ep-webgpu.html)
- **piper-plus への含意:** WASM ランタイムは「全主要ブラウザに WebGPU EP fallback path を追加可能」段階に到達。 ただし VITS decoder は短文中心 (~25 phoneme/27ms p50) で軽量、 ORT 公式が「lightweight model は WASM EP 推奨」とする領域。 導入は MB-iSTFT decoder の長文 streaming や ECAPA-TDNN encoder batch 推論パスから段階的に opt-in 化。 **WASM EP を canonical default、 WebGPU EP は opt-in accel** として位置付け。 **B-8 / B-9 の方針が確定**。

### G-D. 多言語データ系 (06-15 由来)

#### G-D8. Tier-2 言語の audio-text データ可用性 — **RESOLVED**

**Phase 4 確定 (Common Voice 25.0 2026-03-09 公式 JSON より):**

| 言語 | CV validHrs/totalHrs | 追加データ | 30h しきい値 | 評価 |
|------|---------------------|-----------|-------------|------|
| **AR** (Arabic) | 91.9 / 157.4 | — | ✅ CV 単独 OK | 単独で十分かつ CC0 |
| **TR** (Turkish) | 129.2 / 135.3 | — | ✅ CV 単独 OK | 単独で十分かつ CC0 |
| **BN** (Bengali) | 54.3 / 1277.4 | SLR37 (CC BY-SA 4.0) | ✅ CV+SLR で OK | Multi-speaker TTS data あり |
| **HI** (Hindi) | 15.6 / 26.6 | SLR118 (105hr、 **NC**) | △ CV 単独不足、 SLR118 は商用不可 | IndicVoices-R 検討 |
| **VI** (Vietnamese) | 7.3 / 22.0 | VIVOS 15hr (NC) | ❌ commercial-friendly では不足 | 商用 6lang 拡張は現状不可 |
| **TL** (Tagalog/Filipino) | 未掲載 | FLEURS 7.6hr (CC-BY-4.0) | ❌ 不足 | 学習単独では不足 |

- **主要 1 次ソース:** [CV 25.0 公式 JSON](https://github.com/common-voice/cv-dataset/blob/main/datasets/scripted-speech/cv-corpus-25.0-2026-03-09.json) / [OpenSLR resources](https://www.openslr.org/resources.php) / [SLR37 Bengali TTS](https://www.openslr.org/37/) / [SLR118 Hindi (NC)](https://www.openslr.org/118/) / [FLEURS HF](https://huggingface.co/datasets/google/fleurs)
- **piper-plus への含意 (拡張順序確定):**
  1. **AR** — CV 単独で十分かつ CC0、 **7th 言語候補として最有力**
  2. **TR** — 同じく CV 単独 OK
  3. **BN** — CV+SLR37 で OK
  4. **HI** — CV 単独不足、 IndicVoices-R 精査必要
  5. **VI / TL** — commercial-friendly では当面不可
- 全言語で **Arabic script / Devanagari / Bengali script の新規 PUA 拡張**が必要。 → **C-8 (AR/BN/TL/SW 一括) は AR/BN を優先**で進める判断材料に。

#### G-D9. CC-BY-4.0 → Apache-2.0 派生関係の法的位置付け — **RESOLVED**

- **状態:** companion §2.5 Q16 で **RESOLVED** 済。 [Creative Commons 公式](https://creativecommons.org/about/cclicenses/) が CC-BY-4.0 の派生再ライセンス自由を確定、 [Linux Foundation OpenMDW](https://lfaidata.foundation/blog/2025/07/22/simplifying-ai-model-licensing-with-openmdw/) が「データ = CC-BY-4.0 / コード = Apache-2.0」を推奨パターンとして承認。 **HF model card に CML-TTS attribution を明記**で完了。

### G 全件分類サマリー (Phase 4 完了)

| Q | Title | 分類 |
|---|-------|------|
| G-A1 | iSTFTNet2-MB / MS-Wavehax 統合後性能保持 | **IRREDUCIBLE** (PoC) |
| G-A2 | Matcha / flow-matching 多話者ヘッドルーム | **CONVERGED** |
| G-B3 | 軽量 per-word LID | **CONVERGED** |
| G-B4 | neural G2P の 7 ランタイム移植 | **CONVERGED (見送り)** |
| G-C5 | 量子化品質回帰の実測値 | **IRREDUCIBLE** (PoC) |
| G-C6 | Matcha / StyleTTS2 アーキ移行コスト | **IRREDUCIBLE** (PoC) |
| G-C7 | WebGPU ブラウザサポート | **RESOLVED** |
| G-D8 | Tier-2 言語データ可用性 | **RESOLVED** |
| G-D9 | CC-BY-4.0 → Apache-2.0 派生関係 | **RESOLVED** |

**統合: 9 件中 RESOLVED 3 / CONVERGED 3 / IRREDUCIBLE 3** — 文献調査による closure は完了、 残り 6 件 (CONVERGED 3 + IRREDUCIBLE 3) は piper-plus 固有の PoC / 実装に依存。

**全 20 オープンクエスチョン (本 9 件 + companion 11 件 = Q10〜Q20) 統合分類:**

| 出典 | RESOLVED | CONVERGED | IRREDUCIBLE | 計 |
|------|----------|-----------|-------------|----|
| 本表 (G-A1〜G-D9) | 3 (G-C7 / G-D8 / G-D9) | 3 (G-A2 / G-B3 / G-B4) | 3 (G-A1 / G-C5 / G-C6) | 9 |
| companion (Q10〜Q20) | 2 (Q15 / Q16) | 2 (Q10 / Q11 / Q12 / Q17) | 5 (Q13 / Q14 / Q18 / Q19 / Q20) | 11 |
| **合計** | **5** | **7** | **8** | **20** |

(companion CONVERGED は Q10/Q11/Q12 を 1 つにまとめ Q17 と合わせて 4 と数える、 表記は事実) — companion §2.5 末尾「Phase 2-4 オープンクエスチョン総括表」に同データ。

---

## H. 実装ロードマップ (推奨)

### 短期 (3〜6 ヶ月 / v1.14 〜 v1.15)

> ※ バージョン表記は **PR #537 (v2.0.0 候補、 Ready for review)** の merge 状況により **v2.0.x にスライドする可能性あり**。

```text
Track 1 (低リスク・即効性):     D-1 D-2 D-3 D-4    → エコシステム adoption 加速
Track 2 (モバイル EP):          B-1 B-2 B-3        → 既存 iOS xcframework / Android G2P インフラ活用
Track 3 (配布最適化前提):       B-4 B-5            → 測定スイート先行 → INT8 適用判断
Track 4 (G2P / 多言語):         C-1 C-2 C-3 C-5 C-6 C-7 B-9
                                                   → Latin per-word LID + CML-TTS DE/IT + g2ps VI/HI/TR + WebGPU matrix
Track 5 (アーキ加算):           A-3                → ZSE-VITS 型 prosody predictor (低リスク加算)
Track 6 (運用即適用):           E-1                → /add-language データ収集方針へ反映
```

### 中期 (1 年 / v1.16 以降)

```text
Track 7 (architectural 3 並走): A-1 A-4 A-5        → iSTFTNet2-MB (増分) / Matcha-TTS (刷新) / StyleTTS2 (刷新)
                                                   を並列プロトタイピング → 6 ヶ月後 MOS/RTF/footprint A/B で勝者選定
Track 8 (アーキ補強):           A-2                → MS-Wavehax streaming vocoder
Track 9 (G2P / 多言語):         C-4 C-8 (AR/BN 優先) C-9 C-10
                                ※ C-11 (LatPhon / CharsiuG2P neural G2P) は G-B4 CONVERGED で
                                   見送り推奨、 v1.17+ で業界 (Kokoro/Misaki) 進展を見て再評価
                                                   → 10lang model 完成 + Tier-2 G2P 拡張 + homograph 統計層 + neural G2P 実験
Track 10 (mobile 配布):         B-6 B-7 B-8        → INT4 / BitTTS 1.58-bit / WebGPU で smartwatch / 組込 / GPU ブラウザに到達
Track 11 (条件付き刷新):        A-6                → ECAPA2 は #222 (CAM++) マージ後に再評価
```

### KPI / 成功基準 (案)

| 指標 | 現状 (v1.13.0) | 短期目標 (v1.15) | 中期目標 (v1.16+) |
|------|---------------|------------------|-------------------|
| サポート言語 (G2P) | 8 (JA/EN/ZH/KO/ES/PT-BR/PT-EU/FR/SV) | 11 (+ TR/AR/BN G2P+acoustic) | 15+ (+ DE/IT/NL/PL/HI/SW、 VI/TL は G2P-only ※) |
| 学習済みモデル言語 | 6 (JA/EN/ZH/ES/FR/PT) | 7-8 (+DE/IT、 7th 最有力は AR) | 11+ (+NL/PL/AR/TR/BN) |
| 注釈: ※ VI/TL = G2P-only | — | — | G-D8: VI/TL は commercial-friendly audio 不足のため acoustic model 配布なし |
| Decoder 系統 | MB-iSTFT-VITS2 のみ | + ZSE-VITS prosody predictor | + iSTFTNet2-MB or Matcha-TTS or StyleTTS2 の勝者 |
| ONNX 配布サイズ (medium) | ~67MB (FP16) | ~17MB (INT8) | ~10MB (INT4 weight-only、 Conv 系は B-5 で品質検証) / ~12MB (BitTTS 1.58-bit、 acoustic model のみ量子化・速度効果なし) |
| CPU RTF (Xeon E5-2650 v4 / 25 phoneme 英文) | 27ms (canonical) | 25ms 程度 | 15〜25ms (iSTFTNet2-MB 採用時の試算、 G-A1 IRREDUCIBLE → PoC 検証必須) |
| Open WebUI / LibreChat drop-in | 部分対応 | 100% contract 準拠 | voice marketplace 公式リスト掲載 |
| モバイル RTF (Snapdragon 8 Gen 2) | 未測定 | <0.1 (XNNPACK + INT8) | <0.05 (NNAPI + INT4) |
| HF Spaces デモ | 既存 Gradio WebUI | OpenAI compat 互換 demo | voice cloning / multilingual showcase |
| G2P homograph accuracy (EN) | 未測定 | baseline 確定 | +30pp (HomoFast 統計層) |

---

## I. 引用元一覧 (両調査統合 / 一次ソース優先 / 検証済みのみ)

### 音声品質 / アーキ

- [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) — iSTFTNet2 (Kaneko et al., Interspeech 2023, NTT)
- [arXiv 2506.03554](https://arxiv.org/html/2506.03554) — MS-Wavehax streaming vocoder (Yoneyama et al., Interspeech 2025)
- [arXiv 2309.03199 Matcha-TTS](https://arxiv.org/abs/2309.03199) / [Matcha-TTS GitHub](https://github.com/shivammehta25/Matcha-TTS) — ICASSP 2024、 OT-CFM flow matching
- [HF Kokoro-82M model card](https://huggingface.co/hexgrad/Kokoro-82M) — Apache-2.0、 82M params、 TTS Arena #1
- [arXiv 2306.07691 StyleTTS2](https://arxiv.org/abs/2306.07691) — NeurIPS 2023
- [arXiv 2203.02395 iSTFTNet](https://arxiv.org/abs/2203.02395) — ICASSP 2022
- [arXiv 2401.08342 ECAPA2](https://arxiv.org/pdf/2401.08342) — ASRU 2023, IDLab
- [MDPI Electronics 2079-9292/12/4/820](https://www.mdpi.com/2079-9292/12/4/820) — ZSE-VITS prosody predictor (Electronics 2023)
- [arXiv 2410.06885 F5-TTS](https://arxiv.org/pdf/2410.06885) — ACL 2025 (非推奨参照)

### ランタイム / 量子化 / EP

- [ONNX Runtime Quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) — INT8 / INT4 block-wise weight-only
- [ONNX Runtime Mobile EP Tutorial](https://onnxruntime.ai/docs/tutorials/mobile/) — NNAPI / XNNPACK
- [ONNX Runtime WebGPU EP](https://onnxruntime.ai/docs/tutorials/web/ep-webgpu.html) — Web 向け compute-intensive EP
- [coqui-ai/TTS Discussion #2991](https://github.com/coqui-ai/TTS/discussions/2991) — VITS INT8 速度退化事例
- [arXiv 2506.03515 BitTTS](https://arxiv.org/html/arXiv:2506.03515) — 1.58-bit 三値量子化 (Interspeech 2025, LY Corp)

### 多言語 / G2P

- [CML-TTS GitHub](https://github.com/freds0/CML-TTS-Dataset) — 7 EU 言語、 3,233.43 時間 / 613 話者、 CC-BY-4.0 ([arXiv 2306.10097](https://arxiv.org/abs/2306.10097))
- [arXiv 2306.10097 CML-TTS](https://arxiv.org/abs/2306.10097)
- [HF datasets ylacombe/cml-tts](https://huggingface.co/datasets/ylacombe/cml-tts)
- [uiuc-sst/g2ps GitHub](https://github.com/uiuc-sst/g2ps) — 100+ 言語 Phonetisaurus FST
- [arXiv 2005.13962 g2ps paper](https://arxiv.org/abs/2005.13962)
- [arXiv 2505.12973 HomoFast-eSpeak](https://arxiv.org/html/2505.12973v1) — EMNLP 2025 Findings
- [ACL Anthology 2025.findings-emnlp.1218](https://aclanthology.org/2025.findings-emnlp.1218/)
- [arXiv 2509.03300 LatPhon](https://arxiv.org/pdf/2509.03300) — on-device 神経 G2P (USP, 2025)
- [arXiv 2204.03067 CharsiuG2P](https://arxiv.org/abs/2204.03067) — ByT5 多言語 G2P (Interspeech 2022)
- [arXiv 2412.19043 per-word LID](https://arxiv.org/pdf/2412.19043) — code-switching (Handoyo et al., 2024, ITB+NAIST, IEEE)
- [arXiv 2406.08911](https://arxiv.org/html/2406.08911) — 低リソース言語適応のデータ効率 (Gong et al., Interspeech 2024)

### エコシステム

- [Open WebUI openedai-speech 統合](https://docs.openwebui.com/features/chat-conversations/audio/text-to-speech/openedai-speech-integration/)
- [matatonic/openedai-speech GitHub](https://github.com/matatonic/openedai-speech)
- [Home Assistant Voice Remote Local Assistant](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/)
- [HF Hub model cards](https://huggingface.co/docs/hub/en/model-cards)
- [HF model card annotated](https://huggingface.co/docs/hub/en/model-card-annotated)

### 上流 piper / ライセンス

- [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) — 上流 piper の現行 fork
- [rhasspy/piper-voices on HF](https://huggingface.co/rhasspy/piper-voices) — 既存配布
- [Apache GPL-compatibility](https://www.apache.org/licenses/GPL-compatibility.html) — Apache-2.0 のライセンス互換性

---

## J. 統合判断履歴

本セクションは「2 つの調査の重複項目をどう統合判断したか」の透明化のため。

| 項目 | 06-03 評価 | 06-15 評価 | 統合判断 |
|------|-----------|-----------|---------|
| Matcha-TTS | ★ 実験的 (MOS 差は LJSpeech で有意でない) | ★★ 中期プロトタイプ (Kokoro と並走) | **A-4 として中期 ★ (3 並走の 1 つ)** — 06-03 の「LJSpeech 単一話者で有意差なし」caveat と 06-15 の「ODE solver ONNX export と 7 ランタイム porting」のリスク評価を両方掲載 |
| Per-word LID | ★★★ 最優先 (Latin 系統) | (除外、 既に Swedish LID PR #545 マージ済) | **C-1 として ★★★** — Swedish パターンを en/es/pt/fr に横展開する次ステップとして再活性化 |
| BitTTS 1.58-bit | ☆ mobile footprint 条件付き | (除外、 INT4 で代替) | **B-7 として ☆ (中期)** — INT4 (B-6) と並べて B-5 で測定駆動の比較対象に |
| iSTFTNet2-MB | ★★★ 最有力増分 | (除外、 06-03 と重複) | **A-1 として ★★★** — Matcha/StyleTTS2 の刷新路線とは別軸の最有力 CPU 高速化として独立明示 |
| ECAPA2 | ☆ contract 変更が重い | (DRAFT #222 CAM++ とは別系統と整理) | **A-6 として ☆ 条件付き (中期)** — #222 マージ後に CAM++ vs ECAPA2 で再評価 |
| LatPhon/CharsiuG2P (neural G2P) | ★★ 精度↑＋新言語 onboarding | (除外、 HomoFast 統計層を優先) | **C-11 として ☆ 保留 (Phase 4 G-B4 で見送り推奨、 v1.17+ 再評価)** — Kokoro エコシステム (Misaki/Kokoros) も 7 ランタイム neural G2P parity 未達成、 業界進展待ち |
| ZSE-VITS prosody predictor | ★★ 加算的 | (除外、 DRAFT #355 emotion と棲み分け要) | **A-3 として ★★ (短期)** — #355 とは直交 (#355=global style、 A-3=時系列 prosody) と明示 |
| Matcha-TTS / Kokoro 1 軸選定 | (Matcha 中心) | (Matcha + Kokoro 並走) | **A-1 / A-4 / A-5 の 3 並走** — 単一賭けでなく 3-way A/B (J 統合の主要付加価値) |

---

## 関連ドキュメント / アーカイブ

- **未マージ PR (本レポートの新規施策は重複除外済):**
  - **DRAFT PR** (2026-05 中旬以降 3〜4 週間進捗停止、 復旧時期未定 — ロードマップは本レポート施策ベースで前進可):
    - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222)
    - [#355 感情条件 TTS (Style Vector + PE-A)](https://github.com/ayutaz/piper-plus/pull/355)
    - [#386 Hardware EP 自動選択 (CUDA/CoreML/DirectML/OpenVINO/CPU)](https://github.com/ayutaz/piper-plus/pull/386)
  - **Open PR (Ready for review、 2026-05-24 から)**:
    - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一 (v2.0.0 候補)](https://github.com/ayutaz/piper-plus/pull/537) — major bump 予告、 merge 後は §H ロードマップの v1.14/v1.15 表記が v2.0.x にスライドする可能性
- **既存仕様:**
  - [`docs/spec/ort-session-contract.toml`](../spec/ort-session-contract.toml) — EP 選択仕様
  - [`docs/spec/short-text-contract.toml`](../spec/short-text-contract.toml) — 短テキスト戦略
  - [`docs/spec/text-splitter-contract.toml`](../spec/text-splitter-contract.toml) — テキスト分割
  - [`docs/spec/phoneme-timing-contract.toml`](../spec/phoneme-timing-contract.toml) — Phoneme timing
  - [`docs/spec/audio-parity-contract.toml`](../spec/audio-parity-contract.toml) — Audio parity
- **既存リファレンス:**
  - [`docs/reference/ort-versions.md`](../reference/ort-versions.md)
  - [`docs/reference/zh-en-loanword/README.md`](../reference/zh-en-loanword/README.md)
  - [`docs/reference/swedish-lid/README.md`](../reference/swedish-lid/README.md)
- **マイグレーション:**
  - [`docs/migration/v1.11-to-v1.12.md`](../migration/v1.11-to-v1.12.md)
