# 商用利用できる音声データとデータ処理 OSS の調査 (2026-11-03)

> 付録: 2026-11-03 にサブエージェントが書いた調査報告を、本文を変えずに収めたもの (手元の作業用フォルダのパスだけ除いた)。要約と確認の状況は [../zero-shot-improvement-survey-2026-11-03.md](../zero-shot-improvement-survey-2026-11-03.md) にある。数値や論文の主張には、要約側で確かめられなかったと書いたものがある。


対象: piper-plus の zero-shot (話者の似せ方と音質) を良くするための追加データ。日本語を最優先。
条件: 重みを公開し、商用利用もできるモデルに使えること。非商用 (NC)・研究限定・「著作権法 30 条の 4 の利用に限る」型は対象外 (依頼文の条件)。帯域は 22.05 kHz 出力 (11 kHz まで) を満たすものが望ましい。

表記:
- **[一次]** = 配布元の公式ページ・データセットカード・論文本文で今回確認した。
- **[二次]** = 第三者の要約、検索結果の抜粋、過去の記憶。採用前に原文の確認が要る。
- **[過去]** = このリポジトリの過去の判定 (コミット・設計書)。今回は原文を確認し直していない。

---

## 0. 結論 (先に要点)

1. 日本語で今すぐ商用利用できる、話者が多いデータは **Common Voice ja (CC0)** と **Emilia-YODAS ja (CC BY 4.0)** の 2 つだけ。どちらも 2026-08-18 の Phase C-0 で「採用可」と判定済み (コミット `8caa758a`、`docs/design/zero-shot-v10b-quality-plan.md` §7)。ただし今もまだ学習に入れていない (v10b / v11 は v9 と同じ 300,443 発話のまま)。
2. **JVS・JSUT の無償版は商用利用できない**。公式ページは「非商用の研究と個人利用に限る」と書いており、「We welcome your commercial use」は東大 TLO を通した**有償の別契約**の案内。過去の調査で食い違っていた点は、この読み違いだったと確定した (今回の原文確認でも同じ結論)。
3. **Emilia のライセンスの食い違いは解消済み**。Emilia 本体 (101k h) は CC BY-NC 4.0 で使えない。Emilia-YODAS (114k h) は CC BY 4.0 で商用利用できる。管理者 (Amphion) は HF の議論で「YODAS 部分だけなら商用利用してよい」と書いている。ただし元になった YODAS (espnet) は CC BY 3.0 と表示しており、元の音声は YouTube 投稿者が自分で付けた CC 表示に頼っている。
4. 注意点: 現在の計画書 (`zero-shot-speaker-identity-plan-2026-10-29.md` §P3) には「非商用ライセンス (例: Emilia) は使わない」とある。これは **Emilia 本体の話で、Emilia-YODAS は含まない**。書き方があいまいなので、P3 に進む前に直すとよい。
5. 依頼文の条件とのずれ: 今使っている日本語の柱 **moe-speech-plus の元規約は「著作権法 30 条の 4 による利用のみ」** で、依頼文が対象外とした型にあたる。ただし同じ規約が「学習したモデルを公開するのは再配布とみなさない」とも明記しており、プロジェクトはこれを根拠に採用している (zs-v1 公開記録 L56)。ReazonSpeech は 30 条の 4 を理由の一つに除外したので、判断が一貫していない。ただし ReazonSpeech は 16 kHz なので、どちらにしても除外になる。ユーザーが判断を一本化するとよい (下の §5)。
6. 2025〜2026 年に出た新しい日本語コーパス (JIS など) は、調べた範囲では非商用ばかりで、使えるものは増えていない。

---

## 1. 過去の issue・PR・コミットで分かっていること

| 対象 | 判定 | 根拠 (場所) |
|---|---|---|
| moe-speech-plus (ja、473 話者) | **採用** (v8 以降の ja の柱) | v8 計画 §1 の表、決定 2026-07-07「v8 の ja は moe-speech-plus のみ」。規約の扱いは `docs/design/zero-shot-base-zs-v1-release-2026-10-10.md` L56「学習済みモデルの公開を dataset 再配布から除外」 |
| LibriTTS-R / AISHELL-3 / CML-TTS | 採用 (v7 以来) | v8 前処理 `bb766234` |
| Common Voice pt | 採用 (v8、CC0、品質で選別) | v8 計画 §1 の表、`export_common_voice_pt.py` |
| KsponSpeech (ko) | **除外** (研究限定) | `8dc89d67`「public/商用可の公開方針確定」(2026-08-02) |
| Zeroth-Korean | **除外** (品質: 帯域の中央値 3.0 kHz) | `cb47021f` データゲート案 Z、v10b 計画 §7 |
| Common Voice ko | 補助のみ (validated 2.2 h) | v10b 計画 §7、`776c0227` (score_utmos で CV の UTMOS を計算) |
| Pansori-TEDxKR | 除外 (CC BY-NC-ND) | v10b 計画 §7 |
| JVS | **除外** (無償版は非商用。「商用可」は有償契約の案内の読み違い) | `8caa758a`、`docs/guides/training/training-guide.md` L902 |
| Emilia 本体 | 除外 (CC BY-NC 4.0) | `8caa758a` |
| **Emilia-YODAS ja / ko** | **採用可** (CC BY 4.0。帰属表示と品質ゲートが必須) | `8caa758a`。v11 ロードマップ L108「投入は v11 の結果待ち」で、まだ入れていない |
| **Common Voice ja** | **採用可** (CC0) | `8caa758a` (当時の値は validated 380 h / 7,859 voices) |
| ReazonSpeech | 除外 (16 kHz と 30 条の 4) | `zero-shot-v10-similarity-research.md` §4 C-1、v10 ロードマップ L228 |
| J-CHAT | 除外 (CC BY-NC) | 同上 |
| gol-dataset (ゲーム音声 19,349 話者) | v9 で拡張する候補だった → v10b で優先度を下げた | v8 計画 §7、v10b 計画 L530「同じドメインに話者を足しても改善しない」 |
| あみたろ ITA コーパス | FT 用の候補 (独自規約で商用可、AI 学習を明示的に許可、クレジット必須) | issue #305 (stale で close) |
| Hi-Fi TTS (en) | FT 用の候補 (CC BY 4.0) | issue #307 (stale で close) |

過去に決めた投入時の必須ゲート (v10b 計画 §7、`8caa758a`) は今も有効:
1. 案 Z の帯域ゲートを新しいデータにも同じく当てる。YODAS は低ビットレート AAC のため 11〜12 kHz で切れていることがあり、22.05 kHz の上限とぶつかる。
2. DNSMOS 3.0 以上で切る (Emilia-Large は 2.4 で切っており、低品質が混じる)。
3. 自動で付けた話者ラベルを後から絞り込む。話者あたりの発話数の下限と、embedding のまとまり具合で選ぶ (Emilia の話者 ID は区間ごとの話者分離の結果で、誤って合わさっていることがある)。

役割分担の原則 (同じ箇所): Web 由来 (YODAS) は**話者の幅を増やすため**、スタジオ品質 (moe-speech-plus) は**音質の手本**として使う。discriminator が「本物」とみなす音を汚さない。

**再提案しないもの**: JVS 無償版、JSUT 無償版、Emilia 本体、ReazonSpeech、J-CHAT、KsponSpeech、Zeroth-Korean、Pansori。gol-dataset は権利が不明なので、下の表でも NG とした。

---

## 2. データセット一覧

商用欄: OK = 重みを公開する商用モデルに使える / NG = 使えない / 不明 = 原文確認か交渉が要る。

### 2.1 日本語

| データ | ライセンス (原文の要点) | 出典 URL | 商用 | 帯域・規模・話者 | 確認 |
|---|---|---|---|---|---|
| **Common Voice ja 25.0** (2026-03) | CC0-1.0。配布元 Mozilla Data Collective (MDC) の利用規約で、(a) 話者を特定する試みの禁止 (§2(b)(viii) "determine, trace, match the identity of, or re-identify the individual contributor")、(b) MDC 以外の場所に置くことの禁止 (§2(b)(ix)、付録 1 項 8 "scraping, mirroring, or redistributing")。AI の学習を禁じる条項はない | https://datacollective.mozillafoundation.org/datasets/cmn2hm68r01n4mm071qux43yu 、規約 https://mozilladatacollective.com/terms | **OK** (音声を再配布しない、話者を特定しない) | 584,432 clips / 725.11 h (validated 371.92 h) / **7,813 話者**。mp3 で、多くは 48 kHz だが録音機材はまちまち | 規約は[一次]、件数は[二次] (データセットのページは JS で描画され本文を取れず、検索結果の抜粋で確認) |
| **Emilia-YODAS ja** | 論文 "We make the Emilia-YODAS publicly available under the CC-BY-4.0 license." カード "(licensed under `CC BY 4.0`)"。管理者 HarryHe (2025-03-06) "If you are using ONLY the Emilia-YODAS (under cc-by liscene) subset, then it should be fine for commercial use."、同 (2025-02-28) "you are free to use the Yodas subset under cc-by." | https://huggingface.co/datasets/amphion/Emilia-Dataset 、https://arxiv.org/abs/2501.15907 、https://huggingface.co/datasets/amphion/Emilia-Dataset/discussions/13 | **OK** (帰属表示が必須。下の注意を参照) | **1.1k h** (カードの表。v10b 計画は ~0.8k h と書いており食い違う)。24 kHz mp3。話者 ID は区間ごとの話者分離で付けたもの | [一次] |
| Emilia 本体 ja | "Users are permitted to use Emilia dataset only for non-commercial purposes under the CC BY-NC-4.0 license." | 同カード | NG | 1.7k h | [一次] |
| YODAS2 ja (上流、自分で処理する場合) | HF メタデータは cc-by-3.0。"We made sure that our dataset only consisted of videos with CC licenses during our downloading." 確認方法の説明はなく、削除依頼の窓口がある | https://huggingface.co/datasets/espnet/yodas2 | OK (CC BY 3.0。投稿者の自己申告に頼る) | 24 kHz。ja は yodas (16 kHz 版) の値で手動字幕 1,094 h + 自動字幕 2,930 h | [一次] |
| JVS | 音声は "Research by academic institutions / Non-commercial research … / Personal use" に限る。"Re-distribution is not permited"。商用は "We welcome your commercial use." として東大 TLO の連絡先を案内 (48 kHz/24 bit の高品質版あり) | https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_corpus | **無償版は NG** / 有償契約なら可能 | 100 話者 (プロ)、30 h、24 kHz (有償版 48 kHz)、スタジオ録音 | [一次] |
| JSUT | 同じ型 (音声は非商用の研究と個人利用に限る、再配布不可、商用は TLO) | https://sites.google.com/site/shinnosuketakamichi/publication/jsut | 無償版は NG | 女性 1 名、10 h、48 kHz | [一次] |
| JIS (アイドル話者、Interspeech 2025) | "License: CC BY-NC-ND 4.0 … restricted to non-commercial, basic research." | https://arxiv.org/html/2506.18296 | NG | — | [二次] (検索結果の抜粋) |
| JVNV (感情) | CC BY-SA 4.0 | https://sites.google.com/site/shinnosuketakamichi/research-topics/jvnv_corpus | 不明寄り (継承の条件が重みにも及ぶおそれ。§3) | 4 話者 (女 2 / 男 2)、3.94 h、48 kHz | [一次] |
| Hi-Fi-CAPTAIN (NICT) | CC BY-NC-SA 4.0 | https://ast-astrec.nict.go.jp/en/release/hi-fi-captain (今回は保守中) | NG | ja 女 1 / 男 1、48 kHz | [二次] (検索結果の抜粋) |
| J-CHAT | CC BY-NC | (過去の判定) | NG | — | [過去] |
| ReazonSpeech | CDLA-Sharing-1.0 + "YOU MUST AGREE THAT YOU WILL USE THE DATASET SOLELY FOR THE PURPOSE OF" 30 条の 4 | https://huggingface.co/datasets/reazon-research/reazonspeech | NG (16 kHz でもある) | 16 kHz | [一次] |
| JTubeSpeech | リポジトリは Apache-2.0 だが中身は YouTube 動画 ID の一覧だけ。音声の権利は個々の動画による | https://github.com/sarulab-speech/jtubespeech | NG (音声の権利が不明。16 kHz) | 保存先は `wav16k` | [一次] |
| **Kokoro Speech Dataset** | "This dataset is in the public domain in the USA … There are no restrictions on its use." (LibriVox + 青空文庫) | https://github.com/kaiidams/Kokoro-Speech-Dataset | **OK** | **1 話者**、~58.7 h、22.05 kHz (元は LibriVox の mp3) | [一次] |
| つくよみちゃんコーパス | 「個人・法人、営利・非営利、研究用・開発用を問わずご利用いただけます。」ソフトでは「ユーザーが目にする場所へのクレジット表記を必須」。コーパスから来た部分は規約に従わせる。政治・宗教などへの使用は禁止 | https://tyc.rei-yumesaki.net/material/corpus/ | OK (クレジットと用途の制限が下流に及ぶ) | 1 話者、100 文 (+α)、96 kHz 収録 | [一次] |
| あみたろ ITA コーパス | 独自規約。商用可、AI 学習を明示的に許可、クレジット必須、センシティブな作品は不可 (あみたろの声がモデルの 25% 以下なら用途の制限なし) | https://amitaro.net/voice/corpus-list/ita/ | OK (条件付き) | 1 話者 × 4 スタイル × 424 文 | [過去] (issue #305) |
| Lux Japanese Speech Corpus | cc-by-4.0 (HF のタグ) | https://huggingface.co/datasets/Lami/Lux-Japanese-Speech-Corpus | OK 見込み | 1 キャラクター、96 kHz | [二次] |
| その他の ITA コーパス読み上げ (ずんだもん等のキャラクター) | キャラクターごとの規約 (クレジット、用途の制限) | — | 個別に要確認 | 各 1 話者 | 未確認 |
| moe-speech (-plus) ※使用中 | 「このデータセット内のデータは、日本の著作権法…第三十条の四による利用のみが可能です」。同時に「機械学習モデルを作成した場合、そのモデルを公開することは再配布とみなしません」。音声は 1 つでも公開すると再配布にあたる | https://huggingface.co/spaces/litagin/moe-speech-license (raw/main/index.html) | 依頼文の基準では「30 条の 4 型」。プロジェクトの判断ではモデル公開は可 | 473 話者 (使用中) | [一次] |
| gol-dataset (ゲーム音声) | ライセンス表記なし。カード "Access approval is not a license; maintainers must document the lawful use and redistribution basis before downstream use." | https://huggingface.co/datasets/midralab/gol-dataset | **NG** (権利の根拠がない) | 19,382 話者、10.7k h、44.1 kHz | [一次] |
| 有償の市販コーパス (Nexdata、SpeechDataAI など) | 商用ライセンスを販売 | 各社 | 有償 | — | [二次] |

### 2.2 多言語・他言語 (ja 以外の補強、ko の復活)

| データ | ライセンス | 出典 URL | 商用 | 帯域・規模 | 確認 |
|---|---|---|---|---|---|
| Emilia-YODAS (en 92.2k / de 5.6k / fr 7.4k / **ko 7.3k** / zh 0.3k h) | CC BY 4.0 (上と同じ) | 上と同じ | OK | 24 kHz。es / pt はない | [一次] |
| Common Voice (各言語) | CC0 + MDC 規約 | MDC | OK | 48 kHz mp3、録音はまちまち | [一次] (規約) |
| HiFiTTS-2 (NVIDIA、en) | "licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0)"。HF にはメタデータだけで、音声は LibriVox から自分で落とす | https://huggingface.co/datasets/nvidia/hifitts-2 | OK | ~36.7k h、~5k 話者、22 kHz 版 / 44 kHz 版、帯域の推定値付き | [一次] |
| Hi-Fi TTS (en) | CC BY 4.0 | https://www.openslr.org/109/ | OK | 10 話者、291.6 h、44.1 kHz | [一次] |
| GLOBE (en、多くの訛り) | cc0-1.0。Common Voice en を加工 (強調処理あり) | https://huggingface.co/datasets/MushanW/GLOBE | OK 見込み (CV を HF に置いていることと MDC 規約との関係は不明) | 23,519 話者、535 h、24 kHz | [一次] |
| MLS | CC BY 4.0 | https://www.openslr.org/94/ | OK だが **16 kHz** | en/de/nl/fr/es/it/pt/pl | ライセンスは[一次]、16 kHz は[二次] (論文) |
| LibriTTS-P | CC BY 4.0 (話者・スタイルの説明文だけ。音声は LibriTTS-R) | https://github.com/line/LibriTTS-P | OK | 話者の追加はない | [一次] |
| VoxBox | cc-by-nc-sa-4.0 (元のコーパスごとのライセンスも参照するよう記載) | https://huggingface.co/datasets/SparkAudio/voxbox | NG | en/zh のみ | [一次] |
| EARS | "released under CC-NC 4.0 International license" | https://github.com/facebookresearch/ears_dataset | NG | 107 話者、48 kHz | [一次] |
| Expresso | "distributed under the CC BY-NC 4.0 license" | https://speechbot.github.io/expresso/ | NG | 4 話者、48 kHz | [一次] |
| VCTK | ODC-By 1.0 (DNS-Challenge の記載) / CC BY 4.0 とも言われる | (DNS-Challenge の README) | OK 見込み | 110 話者、48 kHz | [二次] |

---

## 3. 食い違いと判断

### 3.1 Emilia / Emilia-YODAS
- Amphion のカード: Emilia 本体は "only for non-commercial purposes under the CC BY-NC-4.0"、Emilia-YODAS は "CC BY 4.0"。HF のメタデータタグは `cc-by-4.0` (本体の NC と合わない)。
- アクセス規約 (gated) の文: "shall use the Emilia dataset under the CC-BY-NC license"。管理者は 2025-02-28 に「YODAS 部分は cc-by で使ってよい」とプロンプトを直したと書いている。
- Amphion の別の管理者 (yuantuo666、2025-04-13) は「商用なら No、Emilia は CC-BY-NC」と答えている。ただしこれは Emilia 全体についての回答と読める。
- 上流の YODAS / YODAS2 (espnet) は **cc-by-3.0**。
- **どれを正とするか**: 権利者が出している論文本文とカード本文、管理者の明言 (YODAS 部分だけなら商用可) を正とし、「Emilia-YODAS = CC BY 4.0、商用可」と判断する。ただし音声そのものは YouTube 投稿者の CC BY 3.0 を元にしている。帰属表示は「Emilia-YODAS (Amphion, CC BY 4.0)、元は YODAS2 (espnet, CC BY 3.0) の YouTube 動画」とモデルカードにデータセット単位で書くのが安全 ([二次]: CC の公式見解は「AI の学習では、データセットへのリンクで帰属表示になりうる」)。
- 過去の設計書が書いていた「KRAFTON README の逆の表記」は、`8caa758a` で行の取り違えと判断済み。今回も KRAFTON 側の文書は見つからず、確かめ直せなかった。
- 残るリスク: (1) YouTube の CC 表示は投稿者の自己申告で、テレビやアニメの無断転載が混じりうる。(2) gated のアクセス規約は今も NC の文を含む可能性があり、同意した文面を保存しておく。(3) 注釈やタイムスタンプが別ライセンスになっている派生データがある ([二次])。

### 3.2 JVS
- 過去の調査の「商用可」は、公式ページの "We welcome your commercial use." と TLO の連絡先を、無償版の許可と読み違えたもの。無償版の音声は非商用に限ることが原文で確定した ([一次]、`8caa758a` と同じ結論)。
- 使えるのは**有償の商用ライセンス**だけ。プロ 100 話者・スタジオ録音・48 kHz で、つくよみと録音条件が近い唯一の多話者日本語コーパス。費用は不明 (問い合わせが要る)。

### 3.3 CC BY-SA (継承) は重みに及ぶか
- CC の公式見解 (https://creativecommons.org/using-cc-licensed-works-for-ai-training-2/): "If AI models or outputs are based on ShareAlike content and they will be shared publicly, following the ShareAlike condition would require AI developers to use the same CC license as the original works." ただし重みが「翻案物」にあたるかどうかは書いていない ([一次])。
- 判断: SA のデータ (JVNV、JVS/JSUT のタグ類) を学習に入れると、重みも CC BY-SA にしなければならない、と言われる可能性が残る。今の重みのライセンスと合わないなら避ける。音声は少ないので、避けても失うものは小さい。
- NC について CC は「学習中の複製から学習済みモデルの共有まで、どの段階も営利目的であってはならない」としている → NC は全部除外で正しい。

### 3.4 Common Voice の配布元が変わった
- 2025-10 以降、Common Voice は Mozilla Data Collective からだけ配布されている。音声の CC0 は変わらないが、MDC の規約で「話者を特定しない」「MDC 以外の場所に置かない」が加わった。学習と重みの公開は問題ない。ただし**加工した clip を HF に上げて共有しない**こと (v8 の HF データ保存の運用と食い違わないよう注意)。

---

## 4. データ処理に使える OSS (重みのライセンス)

| 用途 | ツール | コード / 重みのライセンス | 確認 | 注意 |
|---|---|---|---|---|
| 雑音除去 (48 kHz) | DeepFilterNet | コードは MIT/Apache-2.0。同梱の重みはライセンスの記載なし | [一次] | 48 kHz の wav だけ。重みの扱いは要確認 |
| 修復 (雑音除去 + 帯域拡張、44.1 kHz) | Resemble Enhance | コード MIT、HF の重みも MIT 表記 | [一次] | 強くかけると声質が変わり、話者の似せ方の学習に悪影響のおそれ |
| 修復 (Miipher 相当) | Sidon (東大 猿渡研) | コード MIT、**Sidon v0.1 の重みは MIT**、DialogueSidon は CC BY-NC 4.0 | [一次] | 学習データは書かれていない |
| 帯域拡張 | AudioSR | コード MIT、重みの記載なし | [一次] (重みは不明) | 生成型なので高域の作り物が入る → 学習の正解には使わない方がよい |
| 帯域拡張 | AP-BWE | MIT | [二次] | 同上 |
| 声と背景音の分離 | Demucs / UVR 系 | MIT (Demucs) | [二次] | Emilia-Pipe は UVR-MDX を使う |
| 話者分離 | pyannote speaker-diarization-community-1 | "released under the CC-BY-4.0 license" (gated、連絡先の共有が要る) | [一次] | Emilia は 3.1 (MIT、[二次]) を使用 |
| 話者の embedding とまとめ | 3D-Speaker CAM++ | Apache-2.0 (zs-v1 に同梱済み) | [過去] | 動画をまたいで同じ話者をまとめる処理に使える |
| 日本語 ASR | Whisper large-v3 | MIT | [二次] | |
| 日本語 ASR | kotoba-whisper v2.2 | apache-2.0。話者分離 (pyannote) と句読点付けを内蔵 | [一次] | ReazonSpeech で学習したモデル (§5 参照) |
| 日本語 ASR | NVIDIA parakeet-tdt_ctc-0.6b-ja | "covered by the CC-BY-4.0" 。JSUT の CER 6.4% | [一次] | 学習データは ReazonSpeech v2.0 |
| 品質スコア | UTMOS22 (SpeechMOS) / UTMOSv2 | MIT (UTMOSv2 はリポジトリが MIT、重みの記載なし) | [一次]/[過去] | v8 で `score_utmos.py` に導入済み |
| 品質スコア | DNSMOS | リポジトリのコードは MIT。モデル単体のライセンスの記載なし | [一次] | v10b のゲートで使う予定 |
| 品質スコア | Meta Audiobox Aesthetics | CC BY 4.0 (一部 MIT) | [一次] | 制作品質 (PQ) の軸が音質ゲートに使える |
| 品質スコア | NISQA | コード MIT、**重みは CC BY-NC-SA 4.0** | [一次] | 選別に使うだけでもライセンス上は避けた方が安全 |
| VAD | Silero VAD | MIT | [二次] | |

注意: 修復・帯域拡張の出力を**学習の正解音声**にすると、作り物の高域や声質の変化をモデルが覚える (過去の PQMF 事故やゲームの教訓と同じ構造)。使うのは選別や話者 embedding の計算だけにとどめ、正解には元の音声を使うか、使う場合は帯域ゲートと試聴で検査することを勧める。

---

## 5. ユーザーが判断すること

- **30 条の 4 の扱いを一本化する**: moe-speech は「30 条の 4 のみ」だが、モデルの公開は再配布ではないと明記している → 採用中。ReazonSpeech も「30 条の 4 のみ」で、こちらはモデルについての明記がない → 除外。「モデル公開を規約が明示的に認めているかどうか」で線を引けば一貫する。依頼文の「30 条の 4 型は対象外」を厳密に当てはめると、moe-speech も外れる。
- **ReazonSpeech で学習した ASR (kotoba-whisper、parakeet-ja) を、ラベル付けの道具として使ってよいか**: 道具の重みは Apache-2.0 / CC BY 4.0 なので、ライセンス上は使える。気になるなら Whisper large-v3 (MIT) を使う。

---

## 6. 日本語の話者・録音条件を広げる候補 (順位付き)

前提: 現在の計画では、P3 (データ拡充) は「P2 で学習除外話者は改善したのに、つくよみ (別の録音条件) が改善しなかった」場合だけ行う。順位はその場合を想定している。

| 順位 | 候補 | 得られるもの | 見込み規模 (ゲート後、推測) | リスク |
|---|---|---|---|---|
| 1 | **Common Voice ja 25.0** | 男性・年配・家庭の録音環境など、moe-speech にない幅。話者ラベルは本物 (client_id) | UTMOS ≥2.5、20 clips 以上、話者あたり 60 まで、の既存条件で **数百話者 / 数十 h** (CV ko と pt の実績からの推測) | 低品質の clip が多い。話者あたりの clip が少ない。mp3 の圧縮。帯域ゲートで大きく減る可能性。MDC 規約 (再配布不可) |
| 2 | **Emilia-YODAS ja** | 話者の幅が最も大きい (配信・講演・動画)。v10b 計画では「話者空間を広げて、対比・敵対損失の手がかりを増やす」役割と定義 | 1.1k h → DNSMOS ≥3.0 と帯域ゲートで**数百 h、自動ラベルで数千話者**と見込む (根拠は弱い、要実測) | 話者 ID が区間ごとの分離の結果 (動画をまたいで同じ人がまとまらない。誤って合わさることもある) → cross-utt の正例の定義を直撃する。CAM++ でまとめ直すことが必須。11〜12 kHz で切れている音、BGM、転載動画。帰属表示の義務 |
| 2′ | (代わりの案) YODAS2 ja を自分で処理する | 2 より大きく (手動字幕 ~1.1k h + 自動字幕 ~2.9k h)、処理の手順を自分で決められる | 2 の 2〜3 倍 | 前処理の費用 (GPU で ASR・話者分離・修復)。CC BY 3.0 の帰属表示。権利のリスクは 2 と同じ |
| 3 | **JVS の有償ライセンス** (東大 TLO) | プロ 100 話者のスタジオ録音で、つくよみと録音条件が最も近い。男女が半々 | 100 話者 / 30 h (48 kHz) | 費用が不明で、交渉が要る。契約の範囲 (重みの公開を含むか) を必ず書面にする。評価の holdout に使うなら学習には入れない |
| 4 | Kokoro (パブリックドメイン) | オーディオブックの朗読という録音条件 | 1 話者 / 58.7 h | 話者の幅は増えない。LibriVox の mp3 由来 |
| 5 | 1 話者の商用可コーパス (あみたろ、Lux など) | 評価用に別の録音条件の声を増やす | 各 1 話者 | 学習より **評価の holdout** (つくよみ以外の録音条件の参照) に向く。クレジットと用途の条件が下流に及ぶ |

組み合わせの提案: P3 に進むなら、まず **1 (CV ja) だけ**を入れた試験と、**1+2** の試験を比べる (単一変数の原則)。2 を入れる前に、案 Z の帯域ゲート、DNSMOS、話者のまとめ直しを、数十時間のサンプルで先に実測して、残る量を確かめる (GPU なしで CPU で回せる部分は手元で)。

他言語: ko を戻すなら Emilia-YODAS ko (7.3k h) が唯一の大規模な候補 (v10b 計画の結論と同じ)。en の音質の手本を増やすなら HiFiTTS-2 (CC BY 4.0、~5k 話者、帯域の推定値付き) が最も有望。

---

## 7. 今回確認できなかったこと

- Common Voice ja 25.0 の男女・年代の内訳と実際の帯域 (データセットのページが JS で描画されるため本文を取れなかった)。
- Emilia-YODAS ja の話者数、DNSMOS の分布、帯域の分布 (データをダウンロードしないと分からない)。
- KRAFTON README の現物。
- DeepFilterNet・UTMOSv2・DNSMOS・AudioSR の重みについての明示的なライセンス表記。
- Hi-Fi-CAPTAIN のページ (保守中)。
- JVS の商用ライセンスの費用と条件。
- Coco-Nut、CPJD など、他の Takamichi 研究室のコーパスの規約 (時間の都合で省略。多くは同じ非商用の型と予想)。
