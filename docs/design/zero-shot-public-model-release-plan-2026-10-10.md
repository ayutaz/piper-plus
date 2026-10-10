# Zero-Shotモデルの一般公開計画

作成: 2026-10-10。状態: 計画作成。学習・アップロード・公開切替は未実施。
実行状況は[zs-v1配布・検証記録](zero-shot-base-zs-v1-release-2026-10-10.md)を参照。
計画ブランチ: `docs/zero-shot-public-model-release-plan-20261010`。
起点dev: `421d06678b6ea760dcddb00c235df8f476628866`。
研究ブランチの保存点: `4a8ed100`（`feat/zero-shot-v8-dataset-scaling`）。

## 1. 目的と公開先

参照音声から話者を指定できるベースモデルを
[`ayousanz/piper-plus-base`](https://huggingface.co/ayousanz/piper-plus-base)へ、
採用した同じベースcheckpointをつくよみちゃんで追加学習したモデルを
[`ayousanz/piper-plus-tsukuyomi-chan`](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)へ
gateなしで公開する。gate付きリポジトリはユーザー自身の研究データ保存用とする。

完了は、両公開先に成果物があるだけではなく、未認証の利用者が取得・検証し、
公開済みパッケージから音声を生成できることまで確認して判定する。
ベースのZero-Shot品質とつくよみちゃんFT品質は別々に判定する。

本計画の作成で有料GPU利用や学習を開始しない。公開先の指定は確定済み。
学習の費用・上限を具体化し、実行条件を確定してからVast.aiで進める。
人手試聴を必要な評価工程として残し、機械指標だけで品質承認を作らない。

### 1.1 既存学習済みベースの先行公開（ユーザー意図に合わせた優先順）

ユーザーの意図は、追加学習とZero-Shot推論の両方ができる既存の学習済みベースを公開し、
そのベースを追加学習して声を事前に似せたつくよみちゃんモデルを公開すること。
ベースの再学習・v11b/v12の品質改善研究を一般公開の必須前提にしない。

既存v7にはZero-Shot推論用ONNXとsingle-speaker FT用checkpointがあり、
つくよみちゃん500 epoch FTの実績もある。これは保存点のhandoffで確認した過去の実績で、
本計画作成時の再実行結果ではない。公開するベース世代・checkpointはまだ未選定。
「追加学習・Zero-Shotの機能が成立している」と「今後の品質改善目標を全て満たす」を分ける。

まず次の公開経路を進める。

| 順 | 作業 | 完了条件 |
|---|---|---|
| R0 | 既存v7および後続の学習済み候補から公開checkpointを選び、対応するONNX/config/encoderを特定 | 来歴とhash、追加学習・Zero-Shotの対応世代が揃う。異なる世代を混ぜない |
| R1 | 公開済みv2.0.x環境で実参照による推論と短いFT→export→生成を確認 | 両用途の実動作、公開できる重み・encoderの取得方法、品質特性と既知の制約が確認できる |
| R2 | ベースの配布一式を整形して`piper-plus-base`へ先行公開 | checkpoint/ONNX/config/encoder取得手順/model card/hashが揃い、未認証consumerで生成できる |
| R3 | 同じ採用ベース由来のつくよみちゃんFTを公開 | 既存FTが採用ベースと一致し検証を通れば再利用。別世代ならFTを実施して`piper-plus-tsukuyomi-chan`へ公開 |

既知の音声品質上の制約は試聴資料とモデルカードへ明示する。
改善目標未達を改善済みと表現せず、基準版の公開と品質改善版の選定を別々に記録する。
R1で必要なコード修正が見つかった場合だけdev起点のPRを作る。
研究ブランチの170コミット全ての統合や、学習dataset全量の回収を既存モデル配布の前提にしない。
§4〜6のP系工程は品質改善が必要な場合の別工程とし、R系公開経路へ一律に挿入しない。

## 2. 現状と根拠

### 2.1 一般公開モデル（2026-10-10ライブ確認）

| 対象 | 公開revision / 最終更新 | 確認結果 |
|---|---|---|
| ベース | `ce006e5da7851fdc469887026eeb3f2175e7e080` / 2026-06-13 | gateなし。`model.ckpt`と`config.json`。epoch 74 / step 500034、6言語・173音素。`state_dict`に`spk_proj`なし |
| つくよみちゃん | `36b59c825c36bd386b8960cf3f604382f52f2a87` / 2026-06-13 | gateなし。`tsukuyomi-chan-6lang-fp16.onnx`と`config.json`。旧256次元`speaker_embedding`入力とmaskによる条件切替あり |

SHA256:

- ベースcheckpoint: `83c079abc50575eeb837e1d21e98aefafb23981b9f2cbee247cbcd222df6216b`。
- つくよみちゃんONNX: `5289e9b6eaf21080803b7fe1c4dc85b5491d4c216121207a41df18dd5f68e5d7`。

ベースはrevision固定で取得してHF APIのLFS hashと照合し、`weights_only=True`で
メタデータ・tensor shapeを確認した。つくよみちゃんは同じhashのローカルcacheから
ONNX入出力と条件分岐を確認した。音声生成・品質評価は今回の調査では再実行していない。
旧256次元入力の存在は、現研究の192次元CAM++方式で学習・品質検証済みという意味ではない。
ローカルの別`model.ckpt`は公開版とhashが異なるため、名前だけで公開版と扱わない。

一次情報: [ベースAPI](https://huggingface.co/api/models/ayousanz/piper-plus-base?blobs=true)、
[つくよみちゃんAPI](https://huggingface.co/api/models/ayousanz/piper-plus-tsukuyomi-chan?blobs=true)。

### 2.2 実装・研究成果

研究ブランチは保存点でdevより170コミット先行し、保存点を含む12コミットが
確認済みremote head `4b641dd4`より後にある。この件数は本計画作成時のsnapshot。
工程1〜3の修正は研究ブランチにあり、devへの統合と実モデルの品質改善を区別する。

| 対象 | 状態 |
|---|---|
| 更新周期・KL・EMA・旧checkpoint互換 | 工程1実装済み。実GPU/full-model smokeはこれから |
| embedding/cache・参照入力検証 | 工程2実装・関連検証済み |
| 固定推論評価・strict CER・評価指標の学習経路からの隔離 | 工程3実装・関連検証済み |
| artifact/data固定・修正後の同条件品質比較 | 工程0/4の計画・所在確認段階。正式比較未完了 |
| v10b ep79 | 過去評価では明瞭だがノイズ残存。再評価baseline候補 |
| v11 | 過去の本走はep29で停止。ep9/19は明瞭さ不足。公開候補として採用済みではない |
| 修正後の再学習・つくよみちゃんFT・新モデル一般公開 | 未実施 |

研究ブランチの根拠は`git show 4a8ed100:<path>`で参照できる。

- `docs/design/zero-shot-recovery-and-improvement-plan-2026-10-09.md`
- `docs/design/zero-shot-stage0-4-tdd-plan-2026-10-10.md`
- `docs/design/zero-shot-v11-roadmap.md`
- `docs/spec/zs-eval-contract.md`
- `.claude/skills/remote-train-ops/SKILL.md`

これらは本計画のdev起点ブランチには未統合のものを含む。
旧計画の価格・期間やテスト件数を今回の実測・再検証結果として使わない。

## 3. 成果物と配布仕様

モデル世代はソフトウェアの`v2.0.0`と分け、初回公開名を仮に`zs-v1`とする。
命名・実ファイル名はP1で固定し、モデルカード・catalog・hash manifestで一致させる。
学習epoch番号だけをモデルの品質承認名にしない。

| 公開先 | 配布するもの |
|---|---|
| ベース `releases/zs-v1/` | 追加学習用checkpoint、Zero-Shot推論ONNXと対応config、hash一覧、モデルカード、学習recipe・来歴、集計評価、利用条件、取得・推論・FT手順 |
| つくよみちゃん `releases/zs-v1/` | FT用checkpoint、推論ONNXと対応config、必要な既定話者条件、hash一覧、採用ベースのrevision/hash、FT recipe・来歴、集計評価、公開サンプル、利用条件・手順 |
| ベース側のencoder関連配布 | 192次元encoderと前処理仕様、またはgateなしの公式配布先をrevision/hash固定で取得する手順 |

encoder重みの再配布可否・来歴を確認し、再配布できる場合はベースの同世代配下へ同梱する。
公式取得案内にする場合も、未認証環境で取得でき、必要な次元・前処理が一致することを確認する。
一般利用者が研究保存用gateへアクセスしないと動かない構成を配布しない。

checkpointはFT用に必要な構造・重み・設定・採用EMA情報を保持する。
不要なoptimizer/training状態とローカルpathは精査し、除去後に実FTで利用できることを検証する。
除去して「元runの完全resume用」とは案内しない。完全resume用は研究保存側で保持する。
学習dataset全量・cache・診断ログを一般向け配布へ自動的に含めない。

つくよみちゃんFTの通常利用では参照WAVを要求せず、つくよみちゃんの声で生成できることを目標にする。
Zero-Shot構造を保持する場合、既定の話者条件を重みに固定するか、公開可能な既定embeddingを
配布してruntimeが読むかをP1で決める。無参照のゼロベクトルを良質な既定声と仮定しない。
追加学習後にも未知話者への転写を提供する場合は別途検証し、未確認の能力をモデルカードへ書かない。

## 4. 品質改善が必要な場合の工程・依存関係・完了条件

依存は`P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7`。
P0の権利/入力確認とdev統合設計、P1の配布仕様とruntime調査は互いに独立な作業を先行できる。
P2は既存改善計画の工程0/4、P3/4は工程5に対応し、v12系列入力は公開に必須の依存にしない。
既存構造で品質を満たせない場合だけ、別の研究計画として再設計する。

| 工程 | 作業 | 成果物 / 次工程へ進む条件 |
|---|---|---|
| P0 現物固定・dev統合設計 | 公開旧版、研究ckpt/ONNX、encoder、データ、参照・評価集合、source/lockをhash固定。データ利用条件を監査。研究差分の依存表を作る | artifact/data manifest、再抽出範囲、不足一覧、公開可能な学習入力、PR分割表。比較入力が揃う |
| P1 最小コード統合・配布契約 | 候補モデルに必要な研究修正・評価契約をdev起点のfeature branchへ移植。192次元入力、無参照時、FT既定話者、export・catalog仕様を固定 | 必要なPR/CIが通り、実行sourceが固定できる。旧モデル互換と新モデル実行条件が明確 |
| P2 既存候補の同条件再評価 | v10b ep79をbaseline候補、v11 ep9/19を診断系列としてraw/EMA/現行exportを比較。参照抽出方式も比較 | hash付きJSON/WAV/試聴資料、baseline、学習要否の判定、学習recipe・計測計画 |
| P3 Vast.ai小規模smoke | 認証・料金を確認。GPU/時間/費用上限を確定して100〜300 batchから測る。更新・AMP・保存/再開・export・回収・停止を検証 | 正しい更新数・勾配・resume・回収、実測速度/VRAM/費用、再学習の上限と停止条件 |
| P4 ベース選定・必要な再学習 | P2で合格済み候補があれば再学習を省く。必要なら修正後基準runを先に実行し、結果に応じて一因子比較 | 固定評価と人手試聴に合格したベース、採用raw/EMA、source/recipe/data/hash、公開候補一式 |
| P5 つくよみちゃんFT | 採用ベースから追加学習。データsplit・既定話者条件・言語条件を固定。旧公開つくよみちゃんを比較対象にする | 読み・類似・自然さ・ノイズの独立評価、通常の参照なし推論、FT checkpoint/ONNX/config |
| P6 公開前consumer検証 | 配布形へ整形し、全宣言runtimeで取得・推論、ベースから小規模FTを実行。互換・性能・license・model card・hashを照合 | バージョン別のconsumer結果表、同梱物一覧、upload dry-run、公開対象commit/fileの確定 |
| P7 HF公開・案内切替 | 同じ2リポジトリの世代別パスへ公開。未認証で再取得・hash照合・推論。catalog/docsを新世代へ切替 | 両公開repoと取得経路がgateなし。公開後のconsumer検証成功。旧版取得方法とrollbackが確認済み |

P系の品質改善版を作る場合も、一般向けの公開順はベース、つくよみちゃんFTとする。
ベースの公開準備が終わったらFT完了を待たず先行公開できる。
その間は新世代FTを「未公開」と表示し、両方完了と報告しない。

## 5. 品質・技術検証

### ベース

- 学習・holdout・参照・cross評価のspeaker/path/content hash重複を監査する。
- 参照に使った全発話をcross-utterance評価から除外する。複数参照の除外漏れをTDDで防ぐ。
- CAM++と学習に使わないheld-out encoderでSECS、ceiling/floor、normalized transfer、
  same/cross gap、Goodhart/above-ceiling flagを報告する。
- strict CERは指定ASR/revision/device/正規化を固定。既存契約のmedian≤0.30、固定3文以上、
  ep40以降の昇格条件を維持する。条件違いの結果を同じ改善量として並べない。
- band/comb/comb-HNR/F0/energy/話速と人手試聴を併用する。
  音響・類似の閾値と停止条件は移植する評価契約から読み、実験前にrun manifestへ固定する。
- `[1,192]`話者入力、FP16≤40MB、同一pin機でCPU p50増加≤10%という既存研究予算を維持する。
  別構造のv12で予算変更が必要なら契約改定と別比較を先に行う。
- 公開言語は採用model/data/configに合わせる。G2Pの8言語対応をmodelの8言語品質へ転用しない。
  公開を宣言する全言語で実生成し、日本語の詳細評価と他言語の検証範囲を明示する。

### つくよみちゃん

- 評価発話をFT学習から外す方針を固定する。既存100発話をすべて学習に使ったモデルとの
  比較ではsplit差を明記し、学習データ上の類似だけで汎化を主張しない。
- ベースの未知話者評価、FT後のつくよみちゃん再現、旧公開固定声の品質を別々に報告する。
- 推奨パラメータは新モデルの実生成から決める。旧モデルの`length_scale=1.5`等を無検証でコピーしない。
- 読み・類似・自然さ・ノイズを人手で別欄に記録する。ASR一致を試聴合格として扱わない。

### 配布・runtime

- raw/EMAは固定条件で比較して採用し、未収束checkpointへEMAを機械的に適用しない。
- exportは[ONNX export契約](../spec/onnx-export-contract.toml)に従いchecker・shape検証を通す。
  source統合後の契約を固定し、古いpublish skillのCLI例・license値をそのまま流用しない。
- 現在のtraining sourceと実際に公開済みのv2.0.0 consumerで互換を確認する。
  開発版修正が必須なら対応パッケージをPR/CI経由で公開して最低バージョンを明示する。
  検証を通せず「v2.0.0対応」とは表示しない。
- Python/C++/Rust/C#/Go/WASMは最低限、モデルloadだけでなくWAV生成まで確認する。
  ベースでは実参照と明示embedding、FTでは参照なしの通常経路をそれぞれ通す。
  参照抽出を提供しないruntimeは共通encoderで抽出した正しいembedding入力を検証する。
- CUDA/CPU、WASMブラウザ、宣言するOS/archの結果を分け、stubやQEMU結果を実機結果にしない。
  大型build/DDP/多runtime検証は対応CIへ寄せ、CPU性能計測は固定環境で行う。
- ベースの公開FT用checkpointから短いFT→export→生成を実行し、利用手順の成立を確認する。
- [モデルhash manifest](../spec/model-sha256-manifest.toml)、model catalogと各runtimeの鏡、
  migration案内、model card、公開ファイル名・revisionを同じ変更単位で整合させる。

## 6. GitHubでの作業単位

ユーザー指定: 現在ブランチの差分をコミットしてからdevへ切替え、新しいbranchで作業する。
本計画では既存文書2件を`4a8ed100`に保存してからdevへ切り替えた。
研究モデル・データ・cache・評価ログは保持する。branch切替でignore対象が変わってもcommitしない。

P0で170コミットの依存を調べ、必要な構造・修正・テスト・仕様・hookを組として移植する。
最新のバグ修正だけを、必要な生成器構造がないdevへ無条件cherry-pickしない。
研究branchの全変更を一括でrelease用PRへ混ぜない。

| PR単位案 | 主な対象 | 検証 |
|---|---|---|
| A 監査・評価基盤 | manifest、cache/参照の検証、CER/dual-encoder/音響評価、関連契約 | 異常fixture→修正→関連回帰、実入力audit |
| B 採用生成器・学習修正 | 選定構造、周期/KL/EMA、checkpoint互換、export共有経路 | strict load、実更新/resume、raw/EMA/ONNX、GPU smoke |
| C 配布・consumer対応 | FT既定話者、encoder取得、catalog/resolution/hash、upload/取得検証 | 旧256/新192の入力、無参照FT、未認証取得、実consumer |
| D 公開案内 | model guide、README、migration、モデルカード生成、集計結果・サンプル参照 | revision/hash/言語/最低version一致、リンク、通常利用手順 |

順番と粒度は依存監査で確定する。相互依存が強ければさらに分割または組み替える。
各PRはdevから作ったbranchでTDD、`uv add`/`uv run`、必須hook、scoped commitを行う。
dev/mainへ直接pushしない。CI成功とmergeの承認を区別する。
本計画作成ではpush・PR作成・mergeを行わない。

## 7. 公開切替とrollback

初回は既存rootの`model.ckpt`、`config.json`、既存ONNXを保持し、世代別パスへ追加する。
新モデル用configは同じ世代に置き、旧ONNXに新configを組み合わせない。
新世代を取得してconsumer検証を通してから、新catalogの既定参照を切り替える。
旧consumerには従来のrootが残り、更新consumerは新世代を明示取得する。

HFのmodel/config/checkpoint/model card/checksumはrepo内で一つのcommitとして公開する。
既存upload scriptが全成果物に対応していない場合は、P6までに対応を実装・検証する。
一つのHF commitはrepo内の整合性を保つものであり、2repo/GitHub間の同時切替は保証しない。
公開revisionとsource/catalog commitの対応表を残し、各公開段階の成功・未完了を記録する。

旧版は上記revision/hashで再取得できる状態を維持する。
問題発生時はcatalogを旧版参照へ戻し、新世代の推奨を取り下げる。
hash不一致、encoder取得失敗、config/次元不一致、通常経路の生成失敗を公開失敗として扱い、
他repoの公開や既定参照の切替を進めず、原因と残作業を記録する。

## 8. 計算資源と実施見込み

P0〜P2は有料GPUレンタルを必要としない範囲から開始できる。
実モデルのTorch処理はCUDA、ONNXのCPU検証はCPUで実施する。
Vast.aiは最後の認証確認が401/Invalid user keyであり、復旧確認が必要。
認証待ちでも入力監査・dev統合・baseline準備を進められる。

P3前にGPU種類/台数、VRAM/disk、smoke batch上限、GPU時間/総費用上限、
storage/transfer/保持費用、回収先、異常停止条件を具体化する。
現在価格と実測速度から本走見積りを出す。過去の「80ep約何ドル」を確定予算にしない。
smoke・本走・FT・公開前検証の費用を別々に記録する。
監視はrun開始を区別し、停止理由を中央logへ保存してから停止、成果物を稼働中から回収する。
停止後のactual/intended状態とstorage費用を確認し、品質watchdog停止を無条件resumeしない。

日付・総額はP0の不足量とP3の速度が確定してから設定する。
短期の最初の到達点は「P0/P1の入力・依存・配布仕様確定」、次が「P2の実品質baseline」。
これらが揃う前に新モデルの公開日を確約しない。

## 9. 最初に実行する作業

1. R0として既存学習済みベースとFTの対応を棚卸しし、公開するcheckpoint世代を決める。
2. R1として公開済み環境でZero-Shot推論と短いFTを実行し、必要な修正・配布物を絞る。
3. encoderの公開取得方法と世代別のファイル名を固定し、R2のベース先行公開を準備する。
4. R3として採用ベース由来のつくよみちゃんFTを確認・準備する。
5. 品質改善研究を実施する場合はP0〜P系工程を別run/別計画として進める。

本文の全工程はこれからの計画。過去の実装成功・品質記録を今回の工程完了に振り替えない。
