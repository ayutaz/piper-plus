# Cross-runtime audio parity fixtures

## phoneme_ids.jsonl

`docs/spec/audio-parity-contract.toml` の cross-runtime audio parity gate
(`scripts/audio_parity.py` + `.github/workflows/runtime-parity-deep.yml`) で
6 runtime (Python / Rust / Go / C# / C++ / WASM) に同一の入力を渡すための
canonical fixture。 G2P をバイパスして phoneme IDs を直接渡すので、 G2P
実装差 (loanword / SSML / 短文戦略 etc.) の影響を切り離して decoder /
後処理側の差分だけを計測できる。

1 行 1 utterance の JSONL。 各 field は `JsonlUtterance` 契約
(`src/rust/piper-core/src/input.rs` を canonical とし、各 parity runtime CLI
もこれに揃える):

| field | 型 | 役割 |
|-------|-----|------|
| `phoneme_ids` | `list[int]` | 必須。 BOS=1 / EOS=2 / PAD=0、 残りは model `phoneme_id_map` の整数 |
| `speaker_id` | `int?` | optional。 single-speaker model では省略 |
| `language_id` | `int?` | optional。 multilingual model では必須 (ja=0, en=1, zh=2, es=3, fr=4, pt=5) |
| `output_file` | `string?` | optional。 runtime が出力 WAV path を line ごとに上書きしたい場合 |

## 既存 fixture: `あいうえお` (ja)

`phoneme_ids.jsonl` は各 runtime の CLI smoke test が使う (Rust の
`test_cli_smoke.rs` など)。 parity の比較には使わない。

`[1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2]` は `test/models/multilingual-test-medium.onnx`
の `phoneme_id_map` で `^ a _ i _ u _ e _ o _ $` に相当する 12-ID 列。
`PhonemeType.MULTILINGUAL` の intersperse padding 慣例
(`src/python_run/piper_plus/voice.py:phonemes_to_ids`) を踏襲。

## deterministic_phoneme_ids.jsonl (runtime-parity-deep の入力)

`runtime-parity-deep.yml` が 6 runtime に渡す fixture。「こんにちは、今日は
いい天気ですね。」(ja、 `language_id = 0`) の 70 ID で、 短文対策の padding
(`docs/spec/short-text-contract.toml` の `min_phoneme_ids = 15`) がかからない
長さにしてある。 12 ID の `phoneme_ids.jsonl` では padding と、 その trim の
runtime 差が decoder の差に混ざっていた。

各 runtime は `noise_scale = noise_w = 0`、 `length_scale = 1`、 sentence
silence 0 で合成する (既定の noise は runtime ごとに乱数を引くので一致しない)。
期待するフレーム数は 46,592 (EOS 領域の trim 後)。 判定は
`docs/spec/audio-parity-contract.toml` を参照。

## zero_shot_phoneme_ids.jsonl + test_speaker.npy

Zero-shot TTS (v7 multi-6lang) の speaker-embedding 入力契約を検証する
fixture。`speaker_id` の代わりに `speaker_embedding` (192-dim float32、L2
正規化済み) を渡す形式を Python 側の parity fixture test が検証する。
`runtime-parity-deep.yml` の音声比較ジョブは `deterministic_phoneme_ids.jsonl` を使用し、
この zero-shot fixture を全 runtime に配布するジョブではない。

| field | 型 | 役割 |
|-------|-----|------|
| `phoneme_ids` | `list[int]` | 上記 contract と同じ |
| `language_id` | `int` | multilingual 必須 |
| `speaker_embedding` | `list[float]` (192) | CAM++ 出力相当、L2 正規化 (`‖v‖₂ = 1`) |

`test_speaker.npy` は決定論的 (`np.random.default_rng(seed=42)` → L2 正規化) で
生成された 192-dim float32 ベクトル。 実モデルに対する音声品質は保証せず、
あくまで decoder 入力に同じ tensor 形状を渡せるかを検査する shape / dtype
canonical fixture。`src/python_run/tests/test_zero_shot_parity_fixture.py` が
`test/models/zero-shot-test.onnx` と組み合わせて読み込み、
`scripts/audio_parity.py` の `--speaker-embedding` オプションは別途 contract
validation に使える。
