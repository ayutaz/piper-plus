# Python speaker embedding入力契約

適用: Python Voice、HTTP、`piper_train.infer_onnx`、training dataset loader。
共通実装は`piper_plus.embedding.validate_embedding`。

## 値と次元

- 明示参照は1話者の実数vector。全要素finite、L2 norm > 1e-8を必須とする。
  NaN、Inf、ゼロvector、複素数、誤次元、複数rowは推論前に拒否する。
- runtimeは`[D]`または`[1,D]`を許容する。保存済みtraining cacheは`[D]`を要求する。
- 固定Dを宣言するONNX graphはそのDを使う。固定192/256次元の互換性を維持し、
  動的graphは従来のCAM++既定192次元を使う。
- float64でoverflowを避けてL2正規化し、contiguous float32を返す。
  callerのarrayと元npyは変更しない。旧来の未正規化入力も有効なら正規化する。
- training loaderは`spk_embed_dim`設定を検査次元へ渡す。
  この検証機能はモデル内部のprojection次元を変更するものではない。

## 参照なしと明示不正入力

参照未指定/Noneの場合だけ、ONNXへ`[1,D]`のzero vectorを渡す。
graphに` speaker_embedding_mask `入力がある場合は`[1,1]`のint64で、
参照なしは0、有効な明示参照は1を渡す。maskを宣言しないgraphにはmaskを追加しない。
明示的なゼロvectorや破損fileを参照なしへ置き換えない。

## 経路ごとの処理

| 経路 | 入力/優先順位 | 不正入力 |
|---|---|---|
| Voice | `speaker_embedding`引数 | ORT synthesis前にValueError |
| HTTP `/`、`/api/phoneme-timing` | JSON list、base64 float32 bytes | decode・shape・値の不正は400 |
| inference CLI | npy → reference WAV抽出 → speaker IDのnpy lookup | 非zero終了 |
| inference JSONL | entryのinline vector → entryのnpy path → CLI既定参照 | 非zero終了 |
| training loader | manifestのnpy path | pathを含むValueError |

JSONLの`speaker_embedding_path`は`--dataset-dir`基準で解決する。
未指定なら現在directory基準。training manifestの相対pathはmanifestの親directory基準。
JSONL entryの参照はCLI既定参照を上書きする。

## 検証範囲

CPUテストで実CLI/Voice/HTTP/loaderのwrapperとONNX fixtureを検証する。
数値入力・経路・互換性の成立と、話者類似/自然さの品質評価は別の判定とする。
