# Cross-runtime audio parity fixtures

## phoneme_ids.jsonl

`docs/spec/audio-parity-contract.toml` の cross-runtime byte parity gate
(`scripts/audio_parity.py` + `.github/workflows/runtime-parity-deep.yml`) で
6 runtime (現状 Phase 1 = Python / Rust / Go / C#) に同一の入力を渡すための
canonical fixture。 G2P をバイパスして phoneme IDs を直接渡すので、 G2P
実装差 (loanword / SSML / 短文戦略 etc.) の影響を切り離して decoder /
後処理側の差分だけを計測できる。

1 行 1 utterance の JSONL。 各 field は `JsonlUtterance` 契約
(`src/rust/piper-core/src/input.rs` を canonical とし、 Go / C# / Python
runtime CLI もこれに揃える):

| field | 型 | 役割 |
|-------|-----|------|
| `phoneme_ids` | `list[int]` | 必須。 BOS=1 / EOS=2 / PAD=0、 残りは model `phoneme_id_map` の整数 |
| `speaker_id` | `int?` | optional。 single-speaker model では省略 |
| `language_id` | `int?` | optional。 multilingual model では必須 (ja=0, en=1, zh=2, es=3, fr=4, pt=5) |
| `output_file` | `string?` | optional。 runtime が出力 WAV path を line ごとに上書きしたい場合 |

## 既存 fixture: `あいうえお` (ja)

`[1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2]` は `test/models/multilingual-test-medium.onnx`
の `phoneme_id_map` で `^ a _ i _ u _ e _ o _ $` に相当する 12-ID 列。
`PhonemeType.MULTILINGUAL` の intersperse padding 慣例
(`src/python_run/piper/voice.py:phonemes_to_ids`) を踏襲。

## zero_shot_phoneme_ids.jsonl + test_speaker.npy

Zero-shot TTS (v7 multi-6lang) の cross-runtime parity 用 fixture。
`speaker_id` の代わりに `speaker_embedding` (192-dim float32、L2 正規化済み)
を渡すと各 runtime が同じ声質で合成できることを保証する gate の入力。

| field | 型 | 役割 |
|-------|-----|------|
| `phoneme_ids` | `list[int]` | 上記 contract と同じ |
| `language_id` | `int` | multilingual 必須 |
| `speaker_embedding` | `list[float]` (192) | CAM++ 出力相当、L2 正規化 (`‖v‖₂ = 1`) |

`test_speaker.npy` は決定論的 (`np.random.default_rng(seed=42)` → L2 正規化) で
生成された 192-dim float32 ベクトル。 実モデルに対する音声品質は保証せず、
あくまで「全 runtime が同じ tensor を decoder に流し込めるか」を検査する
shape / dtype canonical fixture。 `scripts/audio_parity.py --speaker-embedding`
が読み込んで各 runtime CLI に転送する。
