# P1 decoder 設計: 上の帯域のざらつきと話者の描き直しを直す (2026-10-29)

> 親計画: [zero-shot 話者再現「本人と分かる」計画](zero-shot-speaker-identity-plan-2026-10-29.md) の P1。
> 本書は P0 の測定 (計画書 §7.6〜7.9) で分かった decoder の問題を直す設計と、その候補を比べる手順を決める。
> GPU の追加費用はかけない (手元の RTX 4070 Ti SUPER で行う)。P2 で使う decoder を、本書の比較で選ぶ。

## 1. P0 で分かったこと (設計の前提)

| 番号 | 事実 | 出典 |
|---|---|---|
| F1 | 実録音を事後エンコーダー → decoder に通して戻すだけで、元の発話との類似度 (CAM++) は 0.62〜0.74 に落ちる。同じ人の別の発話どうしの類似度 (0.70〜0.87) より低い | 計画書 §7.6 |
| F2 | 上流 (prior・flow) を完璧にしても、正規化転写率は CAM++ で約 0.3 が上限 | §7.6 |
| F3 | decoder の話者の条件を別の話者に替えても、その話者に近づかない | §7.6 |
| F4 | 聞こえるガビガビは、乱数なしの合成 (comb-HNR 15 dB) でも、再構成でも出る。3000 Hz より上を切るとほぼ消える。ざらつきは band1 (2.8〜5.5 kHz) から始まる | §7.8, §7.9 |
| F5 | decoder の 4 帯域のうち、band2・band3 のエネルギーは実録音より 3〜28 dB 多い。実録音にはほとんど音がない高い帯域を、雑音で埋めている | §7.9 |
| F6 | 学習で動く PQMF 合成フィルタは大きくずれていて、往復の SNR は 7.6 dB (本来 70 dB)。ただし本来の形に戻しても良くならない。雑音は合成フィルタより前の、帯域ごとの信号に入っている。ずれたフィルタは、その雑音を抑える方向に学習していた | §7.9 |
| F7 | 雑音の指標: comb 超過も comb-HNR も聴感と合わない。2.8 kHz より上のエネルギーの、同じ声の実録音との差は、ここまでの聴感の判断とすべて矛盾しない | §7.7, §7.9 |
| F8 | 配布する TTS (enc_q を除く) は約 2,080 万パラメータで、FP16 で約 40 MB。制約いっぱい。decoder は約 160 万パラメータ (約 3 MB) しかない。最大の部品は flow (1,070 万) | 本書 §4 |

v10b の decoder の構成: MB-iSTFT (4 帯域、各帯域 iSTFT n_fft 16 / hop 4、upsample 4×4、PQMF 126 taps、合成フィルタは学習で動く)、resblock type 2、話者条件は入口の FiLM と各 upsample 段の FiLM。v11 の carrier head (調波の構造を構造的に保つ部品) は **band0 だけ**に入っていて、band1〜3 は従来の iSTFT のままだった (`mb_istft.py` の carrier head 分岐)。F4 のざらつきが始まる帯域は、v11 が手を付けなかった帯域にあたる。

損失と判別器 (v10b): mel L1 (80 bin、0〜11 kHz、係数 45)、帯域ごとの STFT 損失 (sub-band)、全帯域の STFT 損失、MPD (周期 2/3/5/7/11) + MSD、MRD (JCU、4096 の高解像度を含む)、WavLM 判別器 (16 kHz に落として判定するので、8 kHz より上は見えない)。

## 2. 原因の仮説

| 仮説 | 内容 | 合う事実 | まだ確かめていないこと |
|---|---|---|---|
| H1 帯域ごとの iSTFT が細かい構造を作れない | 各帯域の iSTFT は 16 点 (1 帯域 2.76 kHz を 9 bin、1 bin 約 345 Hz)。声の倍音の間隔 (100〜300 Hz) より bin が粗い。上の帯域で倍音を作るには、フレームごとの位相をきれいにつなぐ必要があり、それができないと雑音になる | F4, F5。iSTFT 系は高い帯域の倍音が弱いという指摘 (AF-Vocoder、Wavehax) | 帯域ごとに n_fft を大きくすると直るか |
| H2 損失と判別器が上の帯域のざらつきを見ていない | mel は高い帯域ほど bin が広く、bin の中の細かい構造を平均してしまう。WavLM 判別器は 8 kHz より上を見ない。上の帯域はエネルギーが小さく、損失への寄与も小さい | F4, F5 (v10b 残存ノイズ診断 M3「mel の平均化による感度不足」と同じ向き) | 帯域を分けて判定する判別器 (DAC 型の帯域分割 MRD) で直るか |
| H3 合成フィルタが動くことで、雑音を隠す方向に学習した | 合成フィルタが動けると、上流の雑音を直す代わりにフィルタで抑える道ができる (学習可能な部品が逃げ道になる例。既知の 4 例目) | F6 | 固定のフィルタで学習し直したときの雑音 |
| H4 decoder が小さすぎる | 160 万パラメータは、比較対象の vocoder (HiFi-GAN V1 1,380 万、Vocos 1,350 万、HiFTNet 1,770 万) の約 1/10。実録音の材料を忠実に描き直す力が足りない | F1, F3 | 同じ方式で大きくすると直るか |
| H5 学習データの高い帯域 | 複数のデータセットを混ぜて学習していて、高い帯域の雑音を含む録音があると、その平均的な質感を覚える | F5 (話者によらず高い帯域が多い) | 学習データの高い帯域の分布 |

仮説は互いに排他ではない。§5 の比較は、どの仮説が効いているかを切り分けられるように組む。

## 3. 他の decoder の調査 (2026-10 時点)

前回の調査 (WaveNeXt、iSTFTNet2、MS-Wavehax、`archive/feat/wavenext-decoder-ablation` の 01〜05 と `docs/research/decoder-upgrades-istftnet2-and-mswavehax.md`) は繰り返さない。今回は F4〜F6 (上の帯域の雑音) と F1・F3 (話者の描き直し) に効くかどうかで見直した。

| 方式 | 規模 | 速さ | 上の帯域の雑音への効き目 | 話者の描き直しへの効き目 | 本計画での扱い |
|---|---|---|---|---|---|
| MB-iSTFT (今の方式) | decoder 160 万 | 速い (基準) | 弱い (H1) | 弱い (F1) | 比較の基準 |
| HiFTNet (StyleTTS 2 の decoder、CosyVoice の HiFT) | 1,770 万 | GPU で HiFi-GAN 並み、CPU 値なし | 強い。F0 から作った正弦波の音源を時間周波数領域で入れる。音源を外すと品質が大きく落ちる (CMOS −1.116) | F0 と声の条件を同時に入れる形で、StyleTTS 2 / Kokoro は各 resblock に AdaIN で声の条件を入れている | 方式の参考。そのままでは大きすぎる |
| Wavehax (2024) / MS-Wavehax (2025) | 62 万 | CPU で HiFi-GAN の 4 倍速いが、Vocos の約 1/5 | 強い。高調波の音源 + 2D 畳み込みで複素スペクトルを作る。折り返し雑音が出ない設計 | 記述なし | 候補 (速度の確認が要る) |
| Vocos / WaveNeXt (全帯域 iSTFT、n_fft 1024 など) | 1,350 万 | 前回の実測で今の decoder の 1.24〜1.39 倍遅い | 周波数の分解能は高い (bin 約 21 Hz)。位相の扱いの弱さが指摘されている (2026 の Vocos 再検討論文) | 記述なし | 小型版を候補に残す |
| iSTFTNet2 (1D-2D) | 83 万 | 速い | 周波数方向を 2D で補う | 記述なし | 前回調査済み。候補から外さない |
| 帯域分割の判別器 (DAC 型 MRD)、調波の判別器 (2025、学習可能な三角フィルタ) | 学習時だけ | 推論に影響なし | 判別器に高い帯域を個別に見させる (H2 への直接の手当て) | — | 全候補に共通で入れる |
| AF-Vocoder (2025) | — | — | iSTFT 系は高い帯域の倍音が弱いと指摘し、周波数領域のフィルタで雑音を抑える | — | 参考 |

調査で分かった点:

- 上の帯域の雑音に強い方式は、いずれも**倍音の音源 (F0 から作った正弦波) を外から入れている** (HiFTNet、Wavehax、VISinger2 系、NSF)。v11 の carrier head も同じ考え方で、band0 では comb-HNR 14.6 dB と効果を確かめている。今回の雑音は、その音源が入っていない band1〜3 にある。
- 話者の描き直しでは、StyleTTS 2 / Kokoro の decoder が各 resblock に AdaIN で声の条件を入れている。v11 の診断 (D-3) でも、decoder の中解像度の段 (s1) が話者の情報を最も運ぶと出ていて、同じ方向。
- F0 に頼る方式は、F0 の推定の精度が品質を左右する (HiFTNet の公式実装の注意書き、計画書 §7 の F0 推定の比較)。TTS では F0 を予測する必要があり、既存の `--use-f0-path` (S-2 の F0 予測) を使える。

## 4. 制約と予算の配り直し

| 項目 | 今 (v10b) | 制約 |
|---|---|---|
| 配布する TTS のパラメータ | 約 2,080 万 (FP16 約 40 MB) | FP16 40 MB 以内 |
| うち decoder | 約 160 万 | — |
| うち flow | 1,070 万 | — |
| CPU p50 | 基準 | 悪化 +10% 以内 |

decoder を大きくする場合は、ほかの部品から分ける必要がある。第一の候補は flow。v11 の診断 (D-6) では、推論時に flow が話者の音色を運ぶ寄与はほぼゼロだった (ただし、prior から事後分布への写像としての役割はある)。flow を小さくするかどうかは P2 で決める。本書の比較では、decoder の候補ごとにパラメータ数を記録し、40 MB に収めるために flow をどれだけ削る必要があるかを併記する。enc_q は配布物に入らないので、大きくしても制約に響かない。

## 5. 比較の手順: decoder だけを学習して比べる

F1・F4 は、どちらも**再構成** (実録音 → 事後エンコーダー → decoder) で測れる。そこで、v10b の事後エンコーダー (enc_q) を固定し、decoder だけを学習して候補を比べる。prior・flow・duration を学習し直さないので、手元の GPU で短時間で回せる。合成 (TTS) の品質は P2 で確かめる。

### 5.1 共通の条件

- 入力: v10b ep79 の enc_q (固定、EMA) が実録音から作る z (乱数あり、学習時と同じ)。話者の条件は CAM++ embedding (既存の spk_proj を固定して使う)。
- 学習データ: 評価に使う開発群・最終群の話者を含まない、商用利用可の録音 (moe-speech-plus の別話者と、v9 のゲート済みデータの一部)。具体的な話者と発話は、学習前に仕様 JSON で固定する。
- 評価: 開発群 6 声 (学習に入れない) の再構成。発話は計画書 §7.6 と同じ各 10 本。
- 同じ学習ステップ数で比べる。各候補は seed 2 つ以上。
- 合成フィルタはすべて固定 (H3 を除くため)。判別器には、全候補に帯域分割の MRD を足す (H2 への共通の手当て)。

### 5.2 候補

| 記号 | 内容 | 確かめる仮説 | decoder の規模の目安 |
|---|---|---|---|
| D0 | 今の decoder の重みから始め、合成フィルタを固定し、帯域分割 MRD を足して学習し直す | H2, H3 | 160 万 |
| D1 | D0 と同じ構成を最初から学習 | D0 との差で、初期値の影響を見る | 160 万 |
| D2 | 帯域ごとの iSTFT の n_fft を 16 → 32 または 64 にする | H1 | 160 万 + 出力層 |
| D3 | 倍音の音源を全 4 帯域に入れる (v11 carrier head を band1〜3 に広げる。F0 は実録音から pyin で取る。TTS では F0 予測を使う) | H1 (音源で補う) | 200 万前後 |
| D4 | D0 の resblock を AdaIN (声の条件を各 resblock に入れる) にし、幅を広げる | H4、F1・F3 | 400〜600 万 |
| D5 | 小型の全帯域 iSTFT (Vocos 型、dim 256、6 層前後) | H1 (周波数の分解能) | 300〜400 万 |

D0〜D2 は実装が小さく、先に回す。D3〜D5 は D0〜D2 の結果を見てから、効いた仮説に合わせて選ぶ。H5 (学習データ) は、学習データの 2.8 kHz より上のエネルギーの分布を測って別に確かめる (GPU 不要)。

### 5.3 測るもの

| 指標 | 内容 | 目安 |
|---|---|---|
| 上の帯域のずれ | 2.8 kHz より上を 500 Hz ごとに分け、エネルギーの割合を同じ声の実録音と比べた差の平均 (上下どちらのずれも数える) | 今の decoder の値から下がるか。基準値は D0 の学習前の値 |
| 再構成の話者の保ち方 | 再構成 ↔ 同じ話者の別の実発話 の CAM++ / ECAPA 類似度を、元の発話 ↔ 別の実発話 の類似度で割った比 | 今は 0.78〜0.89。1.0 に近いほど、decoder で話者が失われていない |
| 聴感 | 伏せた A/B: 今の decoder の再構成と、候補の再構成のどちらがざらつくか (20 組) | 雑音の差が大きくなれば聞き分けられるはず (P0 では差が小さく聞き分けられなかった) |
| 規模と速さ | decoder 単体の ONNX (FP16) のパラメータ数と、CPU での時間 (ORT の契約に沿ったスレッド設定) | 全体で 40 MB と +10% に収まる見込みがあるか |

判定の閾値は、D0 の学習前の値 (今の v10b の decoder) を測ってから、学習を始める前に本書に追記して固定する。評価用の指標は学習の損失に使わない。

### 5.4 手順

1. 道具: decoder だけを学習する道具 (enc_q と spk_proj を固定し、z と波形の組で decoder と判別器を学習する)。帯域分割 MRD。上の帯域のずれを測る評価の道具。いずれもテストを先に書く。
2. 学習データの仕様 JSON と、学習データの高い帯域の分布の測定 (H5)。
3. 基準値の測定 (v10b の decoder のまま、§5.3 のすべて)。閾値を本書に追記する。
4. D0・D1・D2 を手元の GPU で学習し、比べる。
5. 結果で D3〜D5 のどれに進むかを決め、同じ手順で比べる。
6. 勝った構成で P2 (TTS 全体の学習、計画書の予算 $300) に進む。

## 6. 調べた資料

- [HiFTNet: harmonic-plus-noise filter + iSTFT (arXiv 2309.09493)](https://ar5iv.labs.arxiv.org/html/2309.09493)、[公式実装](https://github.com/yl4579/HiFTNet)
- [Wavehax: aliasing-free neural waveform synthesis (arXiv 2411.06807)](https://arxiv.org/html/2411.06807v2)
- [Comparative analysis of fast neural vocoders, MS-Vocos / MS-Wavehax (arXiv 2506.03554)](https://arxiv.org/pdf/2506.03554)
- [AF-Vocoder: artifact-free neural vocoder (Interspeech 2025)](https://www.isca-archive.org/interspeech_2025/chen25q_interspeech.pdf)
- [Aliasing-free neural audio synthesis (arXiv 2512.20211)](https://arxiv.org/abs/2512.20211)
- [A universal harmonic discriminator for GAN vocoders (arXiv 2512.03486)](https://arxiv.org/abs/2512.03486)
- [Revisiting Vocos: phasiness in time-frequency neural vocoding (arXiv 2607.24323)](https://arxiv.org/abs/2607.24323)
- [SCNet: subband condition network (arXiv 2609.10025、Interspeech 2026)](https://arxiv.org/abs/2609.10025)
- [iSTFTNet2 (arXiv 2308.07117)](https://arxiv.org/pdf/2308.07117)
- [Learning neural vocoder from range-null space decomposition (IJCAI 2025)](https://ijcai.org/proceedings/2025/0904.pdf)
- [MB-iSTFT-VITS (arXiv 2210.15975)](https://arxiv.org/pdf/2210.15975)
- [Kokoro-82M (StyleTTS 2 + iSTFTNet decoder)](https://huggingface.co/hexgrad/Kokoro-82M)
- [CosyVoice の HiFT 生成器の設定 (n_fft 16 / hop 4、NSF 8 倍音)](https://huggingface.co/OpenMOSS-Team/MOSS-Speech-Codec/blob/main/flow/config.yaml)
- [VISinger2 系の正弦波音源 decoder を VITS に使った例 (arXiv 2307.04630)](https://arxiv.org/pdf/2307.04630)
