# Zero-shot工程2〜3の詳細実装・TDD計画

作成: 2026-10-10。開始HEAD: `13a847c7`。
状態: 工程2A/2Bは`c7cbbbb9`で実装・必須hook完了、関連3ファイル57 passed。
工程2Cは`3ea95490`で実装・必須hook完了、関連15ファイル348 passed。
工程3A/3Bと統合の実装・CPU完了条件を充足。関連4ファイル72 passed。
回帰はtrain/export側349 passed・8 skipped・1 deselected、runtime側155 passed。
追加で、同じ実Synthesizerの既存wrapperによるONNX exportと3backend生成を2件で確認した。
工程3本体は`b1194f65`、隔離gate補完は`14930282`でcommit・必須hook完了（95 passed）。
追加のuv/CUDA対応は関連5ファイル99 passed。実小型モデルのTorch処理はGPUで検証した。
全体方針は[改善計画](zero-shot-recovery-and-improvement-plan-2026-10-09.md)。
工程1のCPU検証結果は保持し、工程2A→2B→2C→3A→3B→統合の順に進める。
工程0の実データ/成果物固定と、工程4以降のモデル品質比較・GPU学習は別工程。

## 現在地と次工程

工程2〜3の機能実装は完了。次は工程0の実データ/成果物固定を終えて工程4の品質比較へ進む。
有料GPU・追加学習は工程5/6として別途実行条件を決める。
操作方法とartifact契約は[推論評価仕様](../spec/zero-shot-inference-evaluation.md)。

固定参照とprosodyのinferへの接続、無参照caption、RNGとmodeの復元、
小型の実Synthesizerによるcheckpoint読込・音声生成、strict CERの集合・hash・ASR条件・
epoch判定、実WAV形式、異常終了時復元を含む4ファイルで72件成功した。
同じ実モデルの通常/compile形式checkpointからraw/既存EMA/ONNXを生成し、
抽出wrapper→loader→固定監視→prepare/generate CLI→strict CERの接続も確認した。
ASR stubによる結果はgateの機能検証であり、実モデルの明瞭度や品質を示さない。

57 passedの対象は`test_embedding_manifest_cache.py`、`test_extract_speaker_embedding.py`、
`test_embedding_validation.py`。工程2CはCLI/Voice/HTTP/loader、dataset parser/F0、
JSONL/timing、実ONNX fixtureを含む15ファイルで348 passed。
これらはfixtureによる機能検証であり、実encoderの品質、
実データ全量の再抽出、音声品質改善を確認した結果ではない。

## 1. 共通契約（2A）

### Embedding

- 1話者の入力は`[D]`またはruntimeで許容する`[1,D]`。任意shapeのflattenはしない。
- DはONNXのspeaker_embedding入力の固定次元を優先。動的graphは既存CAM++既定192。
  legacyの固定256次元graphを192次元へ変更しない。
- 数値・float32へ変換可能・全要素finite・L2 norm > 1e-8を必須とする。
- 有効なcaller/reference/cache vectorはfloat64でnormを計算してL2正規化しfloat32で返す。
  巨大値のoverflow、NaN/Inf、ゼロvector、複数話者batchを拒否する。
- 参照が無い場合だけ、従来のzero vectorとmask=0を使う。不正な明示入力をfallbackにしない。
- 正常なspeaker-IDモデルと参照なしfallback、ONNX入力名・shapeは維持する。
- validatorはruntimeに置き、training側も同じ関数をimportする。必要なpackage依存はuvで管理。

## 2. 抽出・manifest・cache（2B）

### Pathと成功条件

- dataset内の相対音声pathはdataset.jsonlの親directory基準。
- 出力は指定output_dirを優先。manifestにはdataset基準の相対path、別driveなら絶対pathを記録。
- 音声hashと設定identityでcache名を一意にし、別directoryの同名stemを衝突させない。
- ONNX出力のvalidation、atomic保存、保存後validationを終えてから成功entryへpathを付与する。
- 一部失敗はそのentryの無効pathを除去し、成功分だけ確定する。入力全件が失敗なら
  manifestを更新せず明示エラー。missing-onlyの早期returnも同じ契約。
- shardは安定した元entry indexで分ける。抽出shard中にmanifestを更新しない。
  全shardの保存結果を検査する最終passでmanifestを確定し、未完成entryを成功にしない。
- manifestは同directoryの一意tempからreplaceし、元manifestのbackupを保持する。

### Cache来歴

- metadata version、encoder model SHA256、入力音声SHA256、embedding SHA256、次元、
  source/target SR、resampler、fbank/CMVN version、chunk/pooling設定をsidecarへ記録する。
- cache再利用にはmetadata一致、embedding hash一致、shape/finite/norm検査が必要。
  file名・存在・shapeだけで来歴不明の旧cacheを採用しない。
- 旧cacheは削除しない。dry-runでreuse/reextract/missing/legacy件数と対象entryを報告する。
  dry-runはONNX session作成、抽出、manifest/cache変更を行わない。
- model identityが取得できない呼出しはcacheを検証済みとして再利用しない。
- per-speakerのrelative pathも同じ基準。`--workers`は対応する値/経路を明示し、no-opを拒否する。
- chunked、padded、legacy per-utteranceの既存抽出方式を保ち、計算結果のvalidationを全経路へ接続。

## 3. 入力経路の統合（2C）

| 経路 | 接続点 | エラーと互換性 |
|---|---|---|
| inference CLI | npy、reference WAV、speaker ID lookup、JSONL utterance | graph Dを使い、明示不正入力で終了。無参照はmask=0 |
| Python Voice | ORT入力の組立て | 間違ったshape/finite/normをORT実行前にValueError |
| HTTP | list/base64 decode→validator | graph Dを使用。decode/validation失敗を400へ変換 |
| training loader | npy読込→validator→Torch tensor | dataset設定Dで検証し、path付きエラー |

CLI・HTTPの変換済みvectorとVoiceの再検証が一致することを確認する。
共通validatorを通さない暗黙reshapeやnan_to_numを増やさない。

## 4. 固定参照と推論条件の評価（3A）

- 固定test JSONLに`id`、text/phoneme IDs/language ID、speaker_embedding_pathまたは
  明示reference条件を記録。参照pathはmanifest基準で解決する。
- 固定参照の欠落/不正vectorは設定エラー。参照未指定の既存entryは「無参照」と明示。
- reconstruction validation lossは維持。音声監視/比較は`model_g.infer`を使い、
  GT F0/GT durationを渡さず、予測F0・予測duration・実参照embeddingで生成する。
- 共通の推論評価manifestを定義し、同じIDs/text/reference/scales/seedから
  Torch raw、既存EMA、ONNXの各backendを生成できるようにする。
- manifestにはreference/embedding/model/sourceのhashと生成条件を保存。
  WAV artifactごとのhash、backend、scales、seedを結果へ記録する。
- eval/no_gradを保証し、終了後のtrain/eval modeとRNGを復元。
  optimizer/EMA更新、DINO teacher/center、training clock/KL streakを変更しない。
- ONNX exportでは既存`build_infer_forward`を維持し、inferの手書き複製を作らない。
- WandB監視音声は正式品質gateと分け、無参照caption、raw出力と表示用音声の違いを明記。

## 5. Strict CER（3B）

- 既存の自由診断CLIを維持し、正式gateはstrict/pinned manifest modeを明示指定する。
- 期待clip ID集合と生成WAV集合、参照text集合が完全一致することをASR開始前に検査。
- duplicate ID、missing/extra WAV、参照欠損、正規化後の空text、3文未満を失敗にする。
- manifestでASR model/revision、language、normalization version、評価text/hashを固定。
  異なるCLI指定を黙って採用しない。manifest/hashと使用条件を結果JSONへ記録する。
- thresholdは既存契約のCER median ≤ 0.30。正式昇格はep40以降、最低3文。
  smoke/診断の高CERをtraining abort条件へ変えない。
- ASR失敗/不正結果は部分成功の正式gateにしない。failed clip一覧と非zero exitを返す。
- ASR stubは集合/集計/exitのテストだけに使い、明瞭度改善の証拠にはしない。

## 6. TDDの単位と証拠

各単位で新しい回帰テストの失敗を確認→実装→対象テスト→整形/hook→scoped commit。
Pythonの依存追加は`uv add`、実行は`uv run`で管理する。
Torchの推論・監視・export検証はGPUを使う。必要以上のfull modelやmodel downloadを回帰へ入れない。

| 単位 | 先に失敗させる項目 | 完了時の証拠 |
|---|---|---|
| 2A | NaN/Inf/zero、誤次元/複数row、巨大値、非数値 | validatorの192/256互換・L2・非破壊性 |
| 2B | missing-only/混在/全失敗、basename衝突、metadata/hash不一致、custom output、shard未完 | 全3抽出経路のfixture manifest監査、dry-run非変更、既存方式回帰 |
| 2C | 各経路の不正入力、mask=1 fallback、legacy256、HTTP不正base64 | CLI/Voice/HTTP/loaderの実wrapperテスト、正常旧入力回帰 |
| 3A | 固定参照の断線、GT依存、状態/RNG汚染、backend間の条件不一致 | inferへ非ゼロ参照が渡る、predicted条件、raw/EMA/ONNX manifest一致 |
| 3B | missing/extra/duplicate、n=1、ASR条件変更、空text、ASR失敗 | strict CLIのexit/JSON、最低3文とmedian gate、診断mode互換 |
| 統合 | 抽出→manifest→loader/runtime→推論評価→CERの接続漏れ | CPU fixtureの全経路と公開checkpoint/export契約gate |

実データ全量のcache再抽出・checkpoint品質再評価は工程0/4/5として未実施を明記する。
この計画の完了は、工程2〜3の機能と回帰検証の成立であり、品質承認や公開ではない。

## 7. 完了条件と現在の証拠

| 要求 | 確認結果・主な証拠 |
|---|---|
| 2A: 共通vector契約、192/256互換、不正入力拒否 | `test_embedding_validation.py`。2A/2B checkpoint `c7cbbbb9` |
| 2B: 3抽出経路、来歴cache、path/manifest/atomic/shard/workers/dry-run | `test_embedding_manifest_cache.py`、`test_extract_speaker_embedding.py`。関連3ファイル57 passed |
| 2C: CLI/JSONL、Voice、HTTP、loaderと無参照mask | `3ea95490`。関連15ファイル348 passed、正常旧入力・実ONNX fixtureを含む |
| 3A: 固定参照/prosody、predicted infer、無参照caption、raw/表示音声の区別 | `test_inference_evaluation.py`と実Synthesizerを使う`test_evaluation_manifest.py` |
| 3A: mode/RNG、optimizer、DINO teacher/center、clock/KL状態を変更しない | 実VitsModelの監視前後state_dict/clock/RNG一致、optimizer非呼出し、異常終了時復元 |
| 3A: raw/既存EMA/ONNXの共通manifest・来歴・artifact hash | 実小型Synthesizerを`build_infer_forward`経由でexport。3backendの条件hash一致、EMA原重み復元、実ORT seed再生成 |
| 3B: 全期待ID/条件、ASR pin、minimum 3、既存epoch/CER gate | `test_strict_cer.py`のstrict/診断CLI、missing/extra/duplicate、不整合・ASR失敗は非zero exit |
| 統合: 抽出から推論評価/CER、checkpoint/export互換 | 実Synthesizerの通常/compile checkpoint経路、抽出→loader/監視→CLI→strict CER。既存checkpoint gateを含む回帰504 passed |

504件はtrain側21ファイル349件とruntime側5ファイル155件の別processでの結果。
8 skippedは既存の条件付きテスト、1 deselectedは工程1で確認済みの2-rank Glooテスト。
工程3ではそのDDPテストを再実行していない。full-model GPU/DDP/AMP確認は工程5に残す。
ローカルの空の旧`src/python/piper_plus` directoryによるnamespace探索競合は、
検証processの`PYTHONPATH`へ正式`src/python_run`を指定して回避した。保持対象は削除していない。

TDDでは参照断線・不正入力、ONNX先頭補助出力、epoch/seed/source来歴不足、
strict集合/条件不足、実WAV形式未検査、診断revision未反映の失敗を確認してから修正した。
encoder/frontendとASRのstubは接続・gateの証拠に限定する。

工程3本体は`b1194f65`で必須hook成功後にcommit済み。
最終監査で共有推論contextとCERの隔離gate対象漏れも失敗テストへ追加し、
trainingからCERのimport、CERからTorch/VITSのimportを検出する対象とtriggerを補完した。
この補完は`14930282`でcommit・必須hook完了。関連5ファイル95 passed。

### uv / CUDAの追加条件（2026-10-10）

- RTX 4070 Ti SUPER / Torch 2.11.0+cu128で、通常/compile形式の実小型モデルをCUDAへ配置し、
  固定参照監視・既存wrapperによるexport・raw/EMA生成を確認。ONNXはCPUで検証した。
- `generate --device cuda`はGPUがなければ失敗。実行deviceをreportへ記録する。
  GPU RNGは正常終了・例外時とも復元し、重みと混在train/eval flagを保持する。
- ASRのCUDA指定はmanifestへpinし、CLI不一致を初期化前に拒否する。
  初期化引数はmodule stubで検証。実ASRやencoderのdownload・品質評価は実施していない。
- 最終回帰は`uv run --no-sync python -m pytest`、offline設定で99 passed。
  504件の広いCPU回帰はCUDA対応前の結果で、GPUで全件を再実行した数ではない。
- `uv lock --check --offline`成功。CUDA Torch/SciPyは既存依存のため、今回の追加依存はない。
