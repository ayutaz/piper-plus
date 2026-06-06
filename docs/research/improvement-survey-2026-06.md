# piper-plus 改善調査レポート (2026-06)

先行研究・最新論文 (2023-2025) を用いて piper-plus を改善できる点を網羅的に調査したスナップショット。
増分改善 (現行 VITS2 / MB-iSTFT 基盤を維持) と大規模刷新 (別モデルファミリー導入) を区別し、
効果・コスト・リスク・piper-plus コンセプト (OSS / ONNX / CPU・on-device 軽量 / 7 ランタイム parity) との整合を付与する。

> **調査メタ情報**
>
> - **調査日:** 2026-06-03
> - **対象バージョン:** v1.12.0 (`dev`)
> - **手法:** deep-research harness — 5 アングルに分解 → 21 一次ソース取得 → 104 主張抽出 →
>   上位 25 を 3 票の敵対的検証 (2/3 反証で棄却) → **24 確定 / 1 棄却** → 9 件に統合
> - **ソース品質:** 生き残った finding は全て査読付き一次ソース (Interspeech / ICASSP / ASRU / ACL) または公式リポジトリ。blog/marketing 主張は不採用。

> [!WARNING]
> **時間依存性:** TTS 分野は進展が速く、本レポートのソースは 2022-2025 年のもの。
> flow-matching / codec-LM TTS は特に流動的 (F5-TTS は既に高速化追随論文あり)。
> **転移可能性:** 最強の増分候補 (iSTFTNet2-MB / MS-Wavehax) は **スタンドアロン vocoder としての実証**であり、
> piper-plus の **統合 VITS2 decoder** 内での RTF/MOS は統合＋再学習して初めて確認できる。1:1 で転移する保証はない。
> **ベンチマークの偏り:** MOS/RTF の多くは LJSpeech (単一話者・英語)。piper-plus の 6 言語・多話者設定での品質差は未証明。

---

## 優先度マトリクス

| # | 施策 | 区分 | 効果 | コスト | リスク | 確信度 | 推奨度 |
|---|------|------|------|--------|--------|--------|--------|
| 1 | **iSTFTNet2-MB** decoder | 増分 | CPU 2〜5x 高速・MOS 同等↑ | 中 | 中 | high (3-0) | ★★★ |
| 2 | **軽量 per-word LID** (音素化前) | 増分 (G2P) | code-switch 誤読修正 | 中 | 低 | high (3-0) | ★★★ |
| 3 | **MS-Wavehax** streaming vocoder | 増分 | 低レイテンシ最速・極小 | 中 | 中 | high (3-0) | ★★ |
| 4 | データ効率ガイダンス (FT recipe) | 運用 | 学習設計の最適化 | 無 | 無 | high (3-0) | ★★ (即適用可) |
| 5 | **LatPhon / CharsiuG2P** 神経 G2P | 増分 (G2P) | 精度↑＋新言語 onboarding | 中〜高 | 中 | high (3-0) | ★★ |
| 6 | prosody predictor (ZSE-VITS 型) | 増分 | 感情・韻律制御の追加 | 中 | 低 | high (3-0) | ★★ |
| 7 | **Matcha-TTS** (flow matching) | 刷新 | 品質上限↑ (有意差未証明) | 大 | 高 | high (3-0/2-1) | ★ (実験的) |
| 8 | **ECAPA2** speaker encoder | 増分だが contract 変更 | 話者表現↑ (未証明) | 大 | 中 | high (3-0) | ☆ |
| 9 | **BitTTS** 1.58-bit 量子化 | footprint 専用 | サイズ 83%減・**速度効果なし** | 低中 | 中 | high (3-0) | ☆ (mobile 配布時のみ) |
| — | F5-TTS (DiT diffusion) | 刷新 | off-concept | 大 | 高 | high (3-0) | 非推奨 (方向性参考) |

推奨度凡例: ★★★ 最優先候補 / ★★ 有力 / ★ 実験的 / ☆ 条件付き

---

## 増分改善 — 現行 VITS2 / MB-iSTFT 基盤を維持して組み込める

### 1. iSTFTNet2-MB decoder — 最有力 ★★★

> [!IMPORTANT]
> **実装済みの「MB-iSTFT-VITS」とは別論文・別アーキテクチャ (名前が紛らわしいので要注意)。**
> piper-plus の `mb_istft.py` は Kawamura et al. **"MB-iSTFT-VITS" (ICASSP 2023, arXiv:2210.15975)** を実装し、
> `Conv1d`/`ConvTranspose1d` のみ (**`Conv2d` を import すらしていない**) の **1D CNN backbone**。
> 本項の iSTFTNet2 (Kaneko et al., NTT, **arXiv:2308.07117**) は別論文で、核心の
> **1D-2D CNN backbone (2D CNN でスペクトログラム時間×周波数構造をモデル化)** は piper-plus に**存在しない**。
> **両者の共通点は「multi-band 生成 + iSTFT + PQMF」という出力段の枠組みだけ。**
> → 「multi-band + iSTFT の枠組みは対応済み、backbone を 1D CNN → 1D-2D CNN に置換するのが未対応の改善余地」。

- **主張:** iSTFTNet2 は 1D→2D 変換を前倒しし 2D CNN でスペクトログラム構造をモデル化、神経時間アップサンプリングを 8x 削減 (x64→x8)。出力段の「multi-band + iSTFT + PQMF」枠組みは piper-plus の MB-iSTFT-VITS と共通だが、**backbone を 1D CNN から 1D-2D CNN に置換する点が新規** (= 既存実装の言い換えではなく、未対応の改善)。
- **数値 (LJSpeech, Intel i7-12700H シングルスレッド CPU 実測):** `iSTFTNet2-MB` は **RTF 0.011 (HiFi-GAN V2 の 21%)、MOS 4.25、0.83M params**。1D 版 iSTFTNet-MB (MOS 4.05) を MOS・cFW2VD 両方で有意に上回る。`iSTFTNet2-Small` は RTF 0.018 / MOS 4.22 (HiFi-GAN V2 と統計的に区別不可, p>0.05) / 0.79M params。
- **効果:** piper-plus の MB-iSTFT-VITS と**出力段の枠組み (multi-band + iSTFT + PQMF) を共有**する近縁手法 (`src/python/piper_train/vits/mb_istft.py`: `upsample_rates=(4,4)` + iSTFT(4x) + PQMF(4x)) で、backbone を 1D-2D CNN に置換することで同等以上の品質のまま大きな CPU 高速化が見込める。
- **コスト・リスク (中):** 論文はスタンドアロン vocoder としての実証で、end-to-end TTS への拡張は著者も future work としている。end-to-end VITS2 decoder への統合＋再学習が必要。2D conv が ONNX op coverage を変える可能性。
- **piper-plus 該当箇所:** `src/python/piper_train/vits/mb_istft.py`, `src/python/piper_train/vits/stft_onnx.py`
- **出典:** [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) (Kaneko et al., Interspeech 2023, NTT＝iSTFTNet 原著者) / 確信度 high・**3-0 全会一致 (4 主張統合)**

### 2. 軽量 per-word LID を音素化前に挿入 — ★★★

- **主張:** 音素化の前に単語単位の言語判定 (LID) を入れると code-switching 誤読が大幅改善。混在テキストで **WER 42.18% (English-only) → 17.43%** (oracle LID なら 12.87%)。
- **piper-plus への直結性:** `src/python/g2p/piper_plus_g2p/multilingual.py` の 133-149 行が Basic Latin と拡張 Latin を**単一の `self._default_latin` に潰している** (調査エージェントが実コードで確認)。学習済みモデルに触れず `MultilingualPhonemizer` のテキスト層に追加可能。CJK は既に script で分離済みなので、**利得は Latin 系言語 (en/es/pt/fr/sv) に集中**。
- **コスト・リスク (低):** ⚠️ 論文の mBERT (〜700MB) は piper-plus の CPU/on-device/7-runtime parity コンセプトには重すぎる。**fastText クラス or 小型 char-CNN の軽量 LID に置き換える前提**なら「学習済み per-word LID が script 判定に勝つ」という finding 自体は成立。
- **piper-plus 該当箇所:** `src/python/g2p/piper_plus_g2p/multilingual.py:133-149`
- **出典:** [arXiv 2412.19043](https://arxiv.org/pdf/2412.19043) (Handoyo et al., 2024, ITB+NAIST, IEEE) / 確信度 high・3-0 (実装コスト注記のみ 2-1)

### 3. MS-Wavehax — 低レイテンシ streaming vocoder ★★

- **主張:** **sub-80ms チャンクの低レイテンシ条件で最高スループット (最低 RTF)**、シングル CPU スレッド (AMD EPYC 7302) / ONNX Runtime 上で HiFi-GAN・iSTFTNet・Vocos・**MS-iSTFTNet (piper-plus MB-iSTFT の直接対応物) を凌駕**。
- **数値:** **0.332M params = HiFi-GAN V1 の 2.4%** という極小サイズ。MOS は自然音声に匹敵 (causal/non-causal 両条件)。全比較 vocoder は torch.stft/istft を conv 実装に置換して ONNX 化＝**piper-plus が `vits/stft_onnx.py` で既に使っている手法と同一** (ONNX export リスク低減)。
- **コスト・リスク (中):** スタンドアロン vocoder のため統合が必要。**優位性は低レイテンシ領域に限定** (大きいチャンクでは 2D conv のデータ転送増で Vocos が勝つ)。piper-plus の text-splitter streaming モードが使う領域とは合致。
- **piper-plus 該当箇所:** `src/python/piper_train/vits/stft_onnx.py`, `src/python_run/piper/text_splitter.py`
- **出典:** [arXiv 2506.03554](https://arxiv.org/html/2506.03554) (Yoneyama et al., Interspeech 2025, Wavehax 著者) / 確信度 high・3-0/2-1

### 4. データ効率・FT recipe ガイダンス — 即適用可 ★★

- **主張 (低リソース言語/話者適応):**
  1. 総データ固定なら **「話者数を増やす」より「対象話者の発話数を増やす」方が話者類似度に有効**
  2. 少数 new-speaker データの FT は **未知話者への汎化を改善しない** (zero-shot と同等)
  3. **〜20 サンプルの FT は overfit しやすい**
- **piper-plus への含意:** 既存の**つくよみちゃん 100 サンプル FT は論文と整合** (最悪ケース言語で〜100 が最適、20 は overfit)。`/add-language` のデータ収集方針＝「話者あたり発話数を優先、最低 〜100 サンプル、単一話者 FT に未知話者汎化を期待しない (それには事前学習の話者多様性が必要)」。
- **コスト・リスク (無):** アーキ変更なし、運用ガイダンス。SSL-based TTS の知見なので絶対値は VITS2 に過度一般化しない。
- **出典:** [arXiv 2406.08911](https://arxiv.org/html/2406.08911) (Gong et al., Interspeech 2024, Edinburgh/NII) / 確信度 high・3-0/2-1

### 5. LatPhon / CharsiuG2P — 神経 G2P (精度↑＋新言語) ★★

- **主張:** `LatPhon` は単一 7.5M-param Transformer (〜30MB fp32, **on-device 明示設計**) で en/es/fr/it/pt/ro をカバー＝**piper-plus の es/pt/fr/en と一致**。ipa-dict で平均 **PER 3.5%** (580M ByT5 の 5.4% を上回り、言語別 WFST の 3.2% に肉薄)。piper-plus 関連言語では更に強い (ES 0.30% / FR 0.57% / PT 0.86%)。`CharsiuG2P` (ByT5, MIT, 〜100 言語) は**新言語の fine-tune warm-start** (例: Albanian 51.1%→11.7% を 1800 語で)＝`/add-language` workflow に有用。
- **コスト・リスク (中〜高):** 両者とも IPA 出力なので piper-plus の **PUA mapping が必要**、seq2seq Transformer なので現行の rule/dictionary phonemizer とは別物＝drop-in ではない。**7 runtime への移植が parity 維持に必須 (重い)**。⚠️ CharsiuG2P の zero-shot (未知言語) は使い物にならない (未知 script で PER >100%)。価値は fine-tune warm-start のみ。
- **piper-plus 該当箇所:** `src/python/g2p/piper_plus_g2p/{spanish,portuguese,french,english}.py`、`/add-language` skill
- **出典:** [arXiv 2509.03300](https://arxiv.org/pdf/2509.03300) (LatPhon, USP, 2025), [arXiv 2204.03067](https://arxiv.org/abs/2204.03067) (CharsiuG2P, Interspeech 2022) / 確信度 high・3-0

### 6. prosody predictor で感情・韻律制御を modular 追加 ★★

- **主張:** VITS 系バックボーンに、pitch/energy/duration を明示モデル化する**別個の prosody predictor を追加**し、感情コーパスで**それ単体を fine-tune**すれば、話者音色と独立に style を学習・調整できる (ZSE-VITS は VITS を**置換ではなく拡張**)。piper-plus の既存 `prosody_features (A1/A2/A3)` 路線とも親和的な additive パターン。
- **コスト・リスク (低):** 加算的モジュールで低リスク。
- **piper-plus 該当箇所:** `src/python/piper_train/vits/models.py` (prosody_features), `--prosody-dim`
- **出典:** [MDPI Electronics 2023 (2079-9292/12/4/820)](https://www.mdpi.com/2079-9292/12/4/820) (ZSE-VITS) / 確信度 high・3-0

---

## 大規模刷新 — 別モデルファミリー (コンセプトとの整合を要検討)

### 7. Matcha-TTS (flow matching) — ★ (実験的位置づけ)

- **主張:** OT-CFM (optimal-transport conditional flow matching) で非自己回帰 ODE decoder を学習。**比較系中で最小メモリ**、長文で最速級、リスニングテストで**最高 MOS (MAT-10 3.84 vs VITS 3.71, LJSpeech)**、**ONNX export 可能** (export スクリプト・onnxruntime CPU 推論 documented)、デフォルト **5 ODE ステップ** (`n_timesteps=5`)。flow-matching ファミリー中で唯一 CPU 適合の可能性。
- **コスト・リスク (高・一部 off-concept):** piper-plus の single-pass 条件付き VAE を**反復 ODE decoder + 別 vocoder に置換**＝7 runtime 全再実装 (非常に大)。5 ステップは export 時に ONNX グラフに焼かれる (runtime 入力ではない)。⚠️ **VITS との MOS 差は統計的に有意でない** (α=0.05)、かつ LJSpeech は弱い単一話者ベンチ＝piper-plus の多言語多話者設定での品質向上は**未証明**。
- **出典:** [github.com/shivammehta25/Matcha-TTS](https://github.com/shivammehta25/Matcha-TTS) (+ arXiv 2309.03199, ICASSP 2024) / 確信度 high・3-0/2-1

### 8. ECAPA2 speaker encoder — ☆ (contract 変更が重い)

- **主張:** ECAPA-TDNN と同じ IDLab グループの hybrid 1D/2D CNN speaker encoder (2D-conv Local Feature Extractor + 周波数方向 Squeeze-Excitation + TDNN Global Feature Extractor)、**192 次元** embedding。voice cloning の品質向上候補。
- **コスト・リスク (中):** ⚠️ **literal drop-in ではない**。`src/python/piper_train/speaker_encoder/ecapa_tdnn.py:227` が `emb_dim=256` をハードコードし、**7 runtime 全てが 256 次元の `speaker_embedding` テンソル契約を pin**。192 次元 ECAPA2 採用は**モデルの speaker-embedding 経路の再学習＋cross-runtime contract 更新**を要する (parity コスト大)。
- **piper-plus 該当箇所:** `src/python/piper_train/speaker_encoder/ecapa_tdnn.py:227`, `docs/reference/speaker-encoder-contract.md`
- **出典:** [arXiv 2401.08342](https://arxiv.org/pdf/2401.08342) (ECAPA2, ASRU 2023) / 確信度 high・3-0

### F5-TTS (DiT diffusion) — 非推奨 (方向性の参考のみ)

- **335.8M params、16-32 NFE、別 Vocos vocoder、看板 RTF 0.15 は明確に GPU (RTX 3090) 値**。piper-plus の single-pass CPU/on-device (end-to-end 〜27ms) と根本的に相反。ただし **phonemizer-independent / alignment-free 設計** (duration model・text encoder・音素アライメント不要、生 char + filler token で speech 長に padding して denoise) は、多言語 code-switching の G2P 課題に対する方向性として興味深い。
- **出典:** [arXiv 2410.06885](https://arxiv.org/pdf/2410.06885) (ACL 2025) / 確信度 high・3-0

---

## footprint 専用 — 速度には効かない

### 9. BitTTS 1.58-bit 三値量子化 — ☆ (mobile 配布時のみ)

- **主張:** 重みを {-1,0,1} に量子化＋packing (3^5=243<256 で 5 重みを 1 int8 に) で **25.66MB → 4.39MB (83%減)**。だが **M1 Pro で RTF 0.040 vs FP32 baseline 0.042＝速度効果は実質ゼロ**、full 量子化はむしろ**遅い (0.064)**。著者自身「速度重視なら acoustic model のみ量子化」と助言。素の小型 FP32 net が 0.019 RTF＝量子化版の約 2 倍速。
- **結論:** **価値は footprint であって速度ではない**。piper-plus の on-device 高速化は、量子化より **iSTFTNet2/MS-Wavehax の vocoder 経路 (実 CPU 高速化) の方が筋が良い**。download/footprint 縮小が要る mobile 配布時のみ検討 (MOS トレードオフ: both-quantized 3.09 vs AM-only 3.30)。
- **出典:** [arXiv 2506.03515](https://arxiv.org/html/arXiv:2506.03515) (BitTTS, LY Corp, Interspeech 2025) / 確信度 high・3-0

---

## 重要な注意点 (caveats)

1. **転移可能性が最大の不確実性:** 最強の増分候補 2 件 (iSTFTNet2-MB / MS-Wavehax) は **スタンドアロン mel→waveform vocoder としての実証**で、end-to-end VITS2 decoder の中ではない。piper-plus の MB-iSTFT は**統合された VITS2 decoder** なので、報告 RTF/MOS は**統合＋再学習して初めて確認でき、1:1 で転移するとは限らない** (iSTFTNet2 著者も end-to-end TTS を future work と明記)。
2. **ベンチマークの偏り:** MOS/RTF の多くが **LJSpeech (単一話者・英語)**。piper-plus は 6 言語・多話者なので、特に Matcha-TTS vs VITS の品質差 (有意でなかった) は**実設定で未証明**。RTF も CPU ハード依存 (i7-12700H / EPYC 7302 / M1 Pro) で、piper-plus の canonical な Xeon E5-2650 v4 ベンチとは直接比較不可。
3. **7-runtime parity コストが論文では過小評価:** G2P・decoder のどの変更も **7 runtime (Python/C#/Rust/Go/JS-WASM/C++/CLI) 全てに複製**しないと cross-runtime parity が崩れる。これが全ての増分 G2P/neural-model 提案の実コストを論文の印象より大きくする。

### 棄却された主張 (1 件)

| 主張 | 投票 | ソース |
|------|------|--------|
| ZSE-VITS が **TitaNet** を speaker encoder として差し替えて zero-shot voice cloning を達成、ECAPA-TDNN の直接代替になる | **1-2 で棄却** | [MDPI 2079-9292/12/4/820](https://www.mdpi.com/2079-9292/12/4/820) |

ECAPA2 への置き換え検討時はこの TitaNet 差し替え路線を根拠にしないこと。

---

## 推奨アクション (次の一手)

証拠の強さ × コンセプト適合 × コストで並べると:

1. **まず PoC すべき:** piper-plus の MB-iSTFT-VITS decoder の **backbone を iSTFTNet2 の 1D-2D CNN に置換**する実験 (最大の CPU 高速化、出力段の multi-band+iSTFT 枠組みは共通なので移行しやすい)。判断基準は注意点 1 の「統合後も RTF/MOS が保たれるか」「2D conv が 7 runtime で ONNX op gap なく動くか」。
2. **低リスク即効:** 軽量 per-word LID (fastText/char-CNN) を `MultilingualPhonemizer` に追加し、Latin 系 code-switching 誤読を修正。学習済みモデル不要。
3. **今すぐ運用に反映:** データ効率ガイダンス (#4) を `/add-language` のデータ収集方針へ。
4. **中期実験:** Matcha-TTS は「置換」ではなく **並行ブランチで品質ヘッドルームを測る実験**として (有意差が出るかを多話者で検証してから判断)。

---

## オープンな疑問 (要追加検証)

1. iSTFTNet2-MB・MS-Wavehax の CPU RTF/MOS は、piper-plus の end-to-end MB-iSTFT-VITS2 に **decoder として統合**しても (スタンドアロン vocoder としてではなく) 保たれるか? 2D-conv / caching op は 7 runtime 全てで op-coverage gap なく ONNX export・実行可能か?
2. mBERT の code-switching WER 利得をほぼ回収しつつ ONNX export・7-runtime parity を保てる**最軽量の学習済み per-word LID** (fastText / 小型 char-CNN) は何か? piper-plus の実ワークロードで Latin-on-Latin code-switching は実際どの程度発生し、コストを正当化するか?
3. piper-plus の rule-based es/pt/fr + g2p-en phonemizer を単一 30MB 神経モデル (LatPhon) に置換すると、7 runtime が現在 rule/library phonemizer に依存している状況で cross-runtime 保守負荷は**正味で減るか増えるか** (Transformer + IPA→PUA mapping のホスト要)?
4. piper-plus の 6 言語多話者 VITS2 に flow-matching decoder (Matcha-TTS 型 OT-CFM) で**測定可能な音質ヘッドルーム**はあるか? Matcha-vs-VITS の MOS 差は単一話者 LJSpeech で有意でなかった＝大規模刷新は品質で正当化されるのか future-proofing だけか?

---

## 出典一覧

検証で生き残った finding の一次ソース (全て primary)。

| ソース | 内容 | アングル |
|--------|------|----------|
| [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) | iSTFTNet2 / iSTFTNet2-MB (Interspeech 2023, NTT) | アーキ・音質 |
| [arXiv 2506.03554](https://arxiv.org/html/2506.03554) | MS-Wavehax streaming vocoder (Interspeech 2025) | CPU 効率・iSTFT vocoder |
| [arXiv 2410.06885](https://arxiv.org/pdf/2410.06885) | F5-TTS (DiT flow-matching, ACL 2025) | アーキ・音質 |
| [github.com/shivammehta25/Matcha-TTS](https://github.com/shivammehta25/Matcha-TTS) | Matcha-TTS (OT-CFM, ICASSP 2024 / arXiv 2309.03199) | アーキ・音質 |
| [arXiv 2506.03515](https://arxiv.org/html/arXiv:2506.03515) | BitTTS 1.58-bit 量子化 (Interspeech 2025, LY Corp) | CPU 効率 |
| [arXiv 2509.03300](https://arxiv.org/pdf/2509.03300) | LatPhon (on-device 神経 G2P, USP, 2025) | 多言語・G2P |
| [arXiv 2204.03067](https://arxiv.org/abs/2204.03067) | CharsiuG2P (ByT5 多言語 G2P, Interspeech 2022) | 多言語・G2P |
| [arXiv 2412.19043](https://arxiv.org/pdf/2412.19043) | per-word LID for code-switching (2024, ITB+NAIST) | 多言語・G2P |
| [arXiv 2406.08911](https://arxiv.org/html/2406.08911) | 低リソース言語適応のデータ効率 (Interspeech 2024) | 学習・データ効率 |
| [MDPI 2079-9292/12/4/820](https://www.mdpi.com/2079-9292/12/4/820) | ZSE-VITS (prosody predictor, Electronics 2023) | 音声クローン・韻律 |
| [arXiv 2401.08342](https://arxiv.org/pdf/2401.08342) | ECAPA2 speaker encoder (ASRU 2023, IDLab) | 音声クローン・韻律 |

> **補足:** 検証統計 = 5 アングル / 21 ソース取得 / 104 主張抽出 / 25 検証 / 24 確定 / 1 棄却 / 9 件に統合。
> 本レポートは調査時点のスナップショットであり、実装判断の前に各一次ソースの再確認を推奨する。
