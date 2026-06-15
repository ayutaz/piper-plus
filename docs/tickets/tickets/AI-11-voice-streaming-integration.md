# AI-11: voice.py に wavehax_model_path + streaming 閾値切替実装

## メタ情報

- ID: AI-11
- 親マイルストーン: [M4](../milestones/M4-mswavehax-dual-vocoder.md)
- 工数見積: 1 日
- 依存チケット: AI-10 (MS-Wavehax vocoder-only FT 30 epoch)
- 後続チケット: AI-13 (7 ランタイム smoke + pairwise SNR 検証)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 AI-11 / §4.3 A-2 MS-Wavehax dual vocoder / §3 Conflict Map (voice.py 行)](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

A-2 MS-Wavehax の **dual vocoder** を Python ランタイム (`PiperVoice`) から **streaming 閾値ベースで sibling 切替**できる API 層を整備する。 AI-10 で FT 完了した companion ONNX (`tsukuyomi.wavehax.onnx`) は ONNX I/O 不変 (入力 `phoneme_ids` / `input_lengths` / `scales` / `sid|speaker_embedding`、 出力 `[B, 1, T]` float32) で、 既存 `tsukuyomi.onnx` (acoustic + 1D MB-iSTFT) と独立 ONNX session として共存する。 本チケットはその 2 session を `PiperVoice` が 1 つの API 表面で持ち、 phoneme 数 (デフォルト 25) で session を切替えることで「短文 streaming = 軽量 wavehax / 長文・通常合成 = 既存 1D MB-iSTFT」 のルーティングを実現する。

計画 §4.3 で確定済みの設計制約は 4 点: (1) `voice.py` は optional named arg として `wavehax_model_path: Path | None = None` と `streaming_threshold_phonemes: int = 25` を追加し既存 ABI を完全互換維持、 (2) `synthesize_stream_raw` 内で `_split_sentences` 後に sentence ごとに phoneme 数を評価し閾値以下なら wavehax session に dispatch、 (3) `text_splitter.py` は **decoder-agnostic 維持**のため一切 touch しない (`text-splitter-contract.toml` も不変)、 (4) wavehax session が `None` の場合は既存挙動完全不変 (default behavior は AI-11 投入前と byte-for-byte 同一)。

このチケットは M4 dual vocoder の **Python 経路のクロージング**であり、 後続 AI-13 で Rust / Go / C# / WASM / C++ / C-API の 6 ランタイムに同等の `new_with_wavehax` / option pattern / optional named arg / 新 entry を伝播するための **canonical API shape を確定する役割**を持つ。 AI-13 が参照する 「Python での streaming 閾値切替がこう振る舞う」 という reference behavior を本チケットで JSON snapshot + pytest として記録し、 7 ランタイム同期の oracle にする。

## 実装内容の詳細

### 編集対象ファイル

- **`src/python_run/piper/voice.py`** (約 1170 LoC、 既存)
  - `class PiperVoice` (L534) に `wavehax_session: onnxruntime.InferenceSession | None = None` および `streaming_threshold_phonemes: int = 25` フィールド追加 (dataclass-style attribute)
  - `PiperVoice.load` (L538-569) に `wavehax_model_path: str | Path | None = None` と `streaming_threshold_phonemes: int = 25` の optional named arg を追加。 `wavehax_model_path` が指定された場合のみ 2 つ目の ORT session を `_shared_create_session_with_cache(wavehax_model_path, device="cpu")` または `_load_session_inline(wavehax_model_path, use_cuda=use_cuda)` で生成し warmup を実行
  - `synthesize_stream_raw` (L752-) の **既存 sentence 列挙ループ内**で、 sentence ごとの phoneme 数を `len(phonemes)` で取得し、 `self.wavehax_session is not None and len(phonemes) <= self.streaming_threshold_phonemes` なら wavehax 経路、 そうでなければ既存 `self.session` 経路に dispatch
  - 推論実体 `_stream_phonemes_to_audio` (内部 helper) を `_stream_phonemes_to_audio_with_session(session, ...)` に extract refactor し、 default session / wavehax session を引数で受ける形に変更 (内部 API のみ、 public surface は不変)

- **新規 helper モジュール (オプション):** `src/python_run/piper/_dual_vocoder.py` (~80 LoC)
  - `def select_session(phonemes: list[str], default_session, wavehax_session, threshold: int) -> tuple[onnxruntime.InferenceSession, str]` (戻り値 second は `"default"|"wavehax"` の telemetry tag)
  - `def warmup_dual_sessions(default_session, wavehax_session) -> None`
  - rationale: `voice.py` 本体の cognitive load 増加を避け、 dispatch logic を unit-test しやすい単独 module に切り出す

### 新規 CLI / 設定 default 値

- `PiperVoice.load(wavehax_model_path=None, streaming_threshold_phonemes=25, ...)` — `wavehax_model_path=None` で既存挙動完全不変 (default behavior 不変は G-1.9 後方互換 gate の要件)
- `streaming_threshold_phonemes=25` の根拠: 計画 §4.6 の Xeon E5-2650 v4 / 25 phoneme 英文 canonical baseline と一致。 25 以下 = 短文 streaming TTFB に wavehax の低オーバーヘッドが効く想定範囲
- env var: 任意で `PIPER_WAVEHAX_THRESHOLD` を override に追加 (実装は AI-13 で 7 runtime 横並びにすると簡単になるため AI-11 では追加せず、 引数経路に限定)

### 互換維持の制約 (G-1.9 後方互換 gate)

- `wavehax_model_path=None` (default) で `PiperVoice.load(...)` を呼んだ場合、 session は単一のままで `synthesize_stream_raw` の出力 PCM bytes は AI-11 投入前と byte-for-byte 同一
- `synthesize` (L705) や `synthesize_with_timing` (L1126) は変更しない (streaming 経路のみが dual vocoder の対象)
- `synthesize_ids_to_raw` (L1086) も変更しない (phoneme_ids 直接受領経路は decoder-agnostic を維持)
- `config` (`PiperConfig`) は変更しない — wavehax session は **同じ sample_rate / hop_length / num_speakers を前提**として AI-10 で export 済み (config 二重化は不要)

### PR #222 / PR #537 との conflict 回避策

計画 §3 Conflict Map の `voice.py` 行 (L88) は「vs PR #222 = LOW / vs PR #537 = NONE」 と確定済み。 本チケットの差分は以下の 2 点で衝突最小化を担保する:

- **PR #222 (Zero-shot TTS / sid → speaker_embedding[192]):** `wavehax_model_path` 引数追加は `load()` シグネチャの末尾 optional named arg として配置し、 `speaker_id` / `speaker_embedding` 関連の位置引数を変更しない。 `synthesize_stream_raw` 内部の dispatch logic は **session 切替のみ**で、 入力テンソル構築側 (PR #222 が改造する `phoneme_ids` / `scales` / `sid|speaker_embedding`) には触らない。 これにより PR #222 rebase 時の merge は import 追加 + load シグネチャ末尾追加の 2 hunk に局所化される
- **PR #537 (Python 3.13 / bf16-mixed / pytest 9):** プラットフォーム層なのでコード衝突なし。 ただし pytest 9 deprecation に当たらないよう、 新規 unit test は `pytest.fixture` の `name=` 明示や `autouse=False` 明示など計画 §7 R5 mitigation の 既存方針に従う
- **PR #222 ABI 二重同期回避:** 計画 §1.3 / §3 で確定済みの「7 ランタイム ABI 同期は PR #222 既存 diff に乗る形で 1 回完了」原則を Python 層でも保つ。 つまり AI-11 で確定する API shape (引数名 / default / 例外) は **AI-13 が 6 ランタイムに横並びで写し取る canonical 仕様**であり、 後続で API 名を変えない

### 疑似コード スケッチ (差分の骨格)

```python
# src/python_run/piper/voice.py

@dataclass
class PiperVoice:
    session: onnxruntime.InferenceSession
    config: PiperConfig
    wavehax_session: onnxruntime.InferenceSession | None = None
    streaming_threshold_phonemes: int = 25

    @staticmethod
    def load(
        model_path: str | Path,
        config_path: str | Path | None = None,
        use_cuda: bool = False,
        wavehax_model_path: str | Path | None = None,
        streaming_threshold_phonemes: int = 25,
    ) -> "PiperVoice":
        # ... existing default session load (unchanged) ...
        wavehax_session = None
        if wavehax_model_path is not None:
            if _HAS_SHARED_ORT_UTILS and not use_cuda:
                wavehax_session = _shared_create_session_with_cache(
                    wavehax_model_path, device="cpu"
                )
                _shared_warmup(wavehax_session)
            else:
                wavehax_session = _load_session_inline(
                    wavehax_model_path, use_cuda=use_cuda
                )
                _warmup_session(wavehax_session)
        return PiperVoice(
            config=PiperConfig.from_dict(config_dict),
            session=session,
            wavehax_session=wavehax_session,
            streaming_threshold_phonemes=streaming_threshold_phonemes,
        )

    def synthesize_stream_raw(self, text: str, ...) -> Iterable[bytes]:
        # ... existing _split_sentences / phonemize pipeline (unchanged) ...
        # NEW: per-sentence session selection inside the inner loop
        for phonemes in phoneme_stream:
            session, branch_tag = select_session(
                phonemes,
                default_session=self.session,
                wavehax_session=self.wavehax_session,
                threshold=self.streaming_threshold_phonemes,
            )
            yield self._infer_one(session, phonemes, ...)
```

## エージェントチームの役割と人数

| 役割 | 人数 | 責任範囲 |
|------|-----|---------|
| Python Runtime Lead | 1 | `voice.py` 編集、 dual session 管理、 後方互換維持、 PR #222 rebase 想定の API shape 確定。 必要スキル: Python type hints / onnxruntime / dataclass / 既存 `synthesize_stream_raw` の thread pool 構造把握 |
| Integration Tester | 1 | streaming 閾値切替の pytest 整備、 既存 single-session smoke の byte-for-byte 不変 verify、 JSON snapshot (AI-13 の 7 runtime oracle) 生成。 必要スキル: pytest / numpy SNR 計算 / ONNX session lifecycle |
| Runtime API Designer (cross-runtime liaison) | 1 | AI-13 で 6 ランタイムに伝播する API shape (引数名 / default / 例外形 / telemetry tag) の canonical 仕様を Python 側で先に固める。 必要スキル: Rust new_with_X / Go option pattern / C# optional named arg / C-API 新 entry の語彙対応表作成経験 |

合計 3 名。 Python 単独タスクだが「Python の振る舞いを 6 ランタイムが写経する」 性質上、 API designer を 1 名分けて確保し AI-13 の手戻りを抑える。

## 提供範囲 (Scope)

### 含むもの

- `src/python_run/piper/voice.py` の `PiperVoice.load` シグネチャ拡張 (`wavehax_model_path`, `streaming_threshold_phonemes`)
- `PiperVoice` dataclass フィールド追加 (`wavehax_session`, `streaming_threshold_phonemes`)
- `synthesize_stream_raw` 内の per-sentence session selection
- 内部 helper `_stream_phonemes_to_audio_with_session` への refactor (public API 表面は不変)
- 新規 `src/python_run/piper/_dual_vocoder.py` (select_session / warmup_dual_sessions helper)
- 新規 `src/python/tests/test_voice_dual_vocoder.py` (unit + integration test、 後述)
- streaming 閾値切替の JSON snapshot を `src/python/tests/data/dual_vocoder_dispatch_snapshot.json` に出力 (AI-13 の 7 ランタイム oracle)
- `PiperVoice.load` の docstring 更新 (新引数の意味、 default 挙動が完全不変であることを明記)

### 含まないもの (Out of Scope)

- 6 ランタイム (Rust / Go / C# / WASM / C++ / C-API) への伝播 — **AI-13 で対応**
- `tools/benchmark/` への wavehax variant 追加 — **AI-12 で対応** (M4 milestone 内で AI-12 から要求される実 benchmark 数値の取得は AI-12 担当)
- `audio-parity-contract.toml` への `[mswavehax]` section 追加 — **AI-14 で対応**
- `synthesize` (non-streaming) / `synthesize_with_timing` / `synthesize_ids_to_raw` 経路への dual vocoder 統合 — **PoC 範囲外** (streaming 経路に限定)
- env var `PIPER_WAVEHAX_THRESHOLD` のような override 経路 — AI-13 で 7 ランタイム横並び設計時に追加すると整合性が取りやすいため本チケットでは引数経路のみ
- `PiperConfig` への wavehax 関連設定追加 — companion ONNX 側 config も同一 sample_rate を前提に AI-10 で確定済み、 config 二重化は不要
- `streaming_threshold_phonemes` のチューニング (25 以外の値の根拠探索) — AI-12 benchmark 後に判断、 本チケットでは default = 25 で固定

## テスト項目

### Unit Tests

- **`src/python/tests/test_voice_dual_vocoder.py::test_select_session_below_threshold`**
  - assert: `len(phonemes) == 10`、 `threshold = 25` で wavehax session が選ばれる (`branch_tag == "wavehax"`)
  - mock: `default_session` / `wavehax_session` を `MagicMock(spec=onnxruntime.InferenceSession)` で差し替え
- **`src/python/tests/test_voice_dual_vocoder.py::test_select_session_above_threshold`**
  - assert: `len(phonemes) == 60`、 `threshold = 25` で default session が選ばれる (`branch_tag == "default"`)
- **`src/python/tests/test_voice_dual_vocoder.py::test_select_session_at_boundary`**
  - assert: `len(phonemes) == 25` (`<=` 比較なので) で wavehax 選択。 境界の semantics を ticket レベルで pin
- **`src/python/tests/test_voice_dual_vocoder.py::test_select_session_no_wavehax_falls_back`**
  - assert: `wavehax_session is None` なら phoneme 数によらず常に default session、 `branch_tag == "default"`
- **`src/python/tests/test_voice_dual_vocoder.py::test_load_without_wavehax_default_unchanged`**
  - assert: `PiperVoice.load(model_path, config_path)` (新引数省略) で生成した voice の `wavehax_session is None` かつ `streaming_threshold_phonemes == 25` (default value pin)、 既存 `session` 属性は単一 ORT session として存続
- **`src/python/tests/test_voice_dual_vocoder.py::test_load_with_wavehax_two_sessions`**
  - assert: `wavehax_model_path` 指定時に 2 つの session オブジェクトが生成され、 両方が `run()` callable
- **既存 `src/python/tests/test_voice.py` 等は touch しない** (G-1.9 後方互換 gate、 既存テストの byte-for-byte 不変を保つ)

### E2E Tests

- **`src/python/tests/test_voice_dual_vocoder.py::test_synthesize_stream_raw_byte_identical_without_wavehax`**
  - 既存 tsukuyomi 1D MB-iSTFT ONNX を default で load、 `wavehax_model_path` 指定なし
  - `synthesize_stream_raw("吾輩は猫である。")` の PCM bytes が AI-11 投入前 baseline と byte-for-byte 同一であることを `hashlib.sha256` で検証 (baseline hash は test data に固定値として置く)
- **`src/python/tests/test_voice_dual_vocoder.py::test_synthesize_stream_raw_with_wavehax_short_text_uses_wavehax`**
  - 短文 (phoneme 数 < 25 想定) で wavehax session の `run()` が呼ばれ、 default `session.run()` が呼ばれないことを `MagicMock.call_count` で検証
- **`src/python/tests/test_voice_dual_vocoder.py::test_synthesize_stream_raw_with_wavehax_long_text_falls_back_to_default`**
  - 長文 (3 文以上、 各 60 phoneme 以上) で default session のみが呼ばれることを assert
- **`src/python/tests/test_voice_dual_vocoder.py::test_synthesize_stream_raw_dispatch_snapshot_json`**
  - 5 種の代表入力 (短文 JA / 短文 EN / 長文 JA / 中文 mixed / SSML) で `(input_text, sentence_idx, phoneme_count, branch_tag)` のタプル列を JSON に出力し、 `src/python/tests/data/dual_vocoder_dispatch_snapshot.json` の baseline と一致 (AI-13 が 6 ランタイムでこの snapshot を写経する oracle)
- **streaming chunk 構造の不変性 E2E**
  - `sentence_silence=0.05` / `volume=1.0` で wavehax 経路と default 経路の chunk が同じ chunk 数を出すこと (silence の挿入は session 切替と独立)

### 受入基準 (Acceptance Criteria)

計画 §4.6 から引用 + 本チケット固有の機械検査:

- **既存挙動 byte-for-byte 不変:** `wavehax_model_path=None` の経路で `synthesize_stream_raw` の出力 PCM が AI-11 投入前と SHA-256 一致 (G-1.9 後方互換 gate)
- **dual session 切替が phoneme 数 25 を境に動作:** dispatch snapshot JSON で `branch_tag` 列が phoneme 数閾値と一致
- **wavehax 経路の出力 shape:** `[1, 1, T]` float32 (companion ONNX の I/O は AI-10 で確定済み、 本チケットは streaming integration のみ)
- **API shape pin:** `inspect.signature(PiperVoice.load)` のキーワード引数集合に `wavehax_model_path` / `streaming_threshold_phonemes` が含まれ、 既存引数の位置が不変
- **CPU RTF (Xeon E5-2650 v4 / 25 phoneme 英文):** 計画 §4.6 の **target 18ms (× 0.7)** に向けた measurement は AI-12 担当だが、 本チケットでは「wavehax 経路で `[1, 1, T]` 形状の chunk が確実に返り、 ORT session への dispatch 自体は overhead 5ms 以内」 を pytest で確認 (`time.perf_counter` で dispatch logic 単独計測)
- **既存 pytest 全 green:** `uv run --no-sync pytest src/python/tests --no-cov` で AI-11 投入前と同じ pass / fail 状況

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

計画 §7 から該当リスク + チケット固有:

- **R4 (companion ONNX 配布の ABI 破壊誤認):** `voice.py` の signature 変更が「ABI 破壊」と外部に映る恐れ。 mitigation = optional named arg として末尾に配置、 default `None` で既存挙動完全不変、 docstring と CHANGELOG (M4 完了時に AI 系統で集約) に明示
- **R6 (audio-parity baseline 誤書き換え):** 本チケットは benchmark 数値の baseline は触らないが、 dispatch snapshot JSON を test data に置くため、 baseline の意味で誤解されないようファイル名は `dual_vocoder_dispatch_snapshot.json` と明示 (audio-parity-contract.toml とは別物)
- **チケット固有: thread pool との相互作用:** `synthesize_stream_raw` は phoneme 数 25 以下の sentence でも G2P 並列実行 (PIPER_G2P_PARALLELISM > 1) する経路を持つ。 session 切替を per-sentence で行う場合、 future の完了順とは独立に session を選ぶ必要があるため、 dispatch logic は phoneme 結果取得時点で **同期的に判定**する設計とする
- **チケット固有: warmup の二重実行コスト:** dual session 化で warmup が 2 倍になる (~25ms × 2 ≈ 50ms TTFB ペナルティ)。 mitigation = warmup は load() 内の 1 度のみ、 streaming 経路内では絶対に warmup を走らせない (既存実装の `_warmup_session` を 2 session 分呼ぶだけ)
- **チケット固有: ORT cache (`.opt.onnx`) の名前衝突:** 既存 tsukuyomi.onnx と tsukuyomi.wavehax.onnx の cache file が同じ親 dir に並ぶため、 cache 命名規則 (`_shared_create_session_with_cache` 側) が ONNX path から派生していることを reviewer に明示確認 (既存実装はそのはずだが、 本チケットで test_load_with_wavehax_two_sessions の中で cache file が 2 つ生成されることを smoke 確認)

### レビュー項目 (チェックリスト)

- [ ] default decoder_type / default `wavehax_session=None` 不変 (G-1.9 後方互換 gate)
- [ ] `[mb_istft_1d]` audio parity 不変 (G-1.2 baseline 編集禁止) — 本チケットは contract toml を編集しない
- [ ] ONNX I/O 不変 (PR #222 二重同期回避) — 本チケットは companion ONNX も含めて I/O 形状を変更しない
- [ ] `text_splitter.py` は touch していない (`text-splitter-contract.toml` 不変、 decoder-agnostic 維持)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響は本チケット範囲外 (Python 推論側でしか発火しないため AI-16 で再 baseline 化)
- [ ] `PiperVoice.load` の引数追加は全て **末尾の optional named arg** であり、 既存呼出が壊れない
- [ ] `synthesize` / `synthesize_with_timing` / `synthesize_ids_to_raw` の挙動は完全不変 (streaming 経路のみが dual vocoder の対象)
- [ ] dispatch snapshot JSON が AI-13 で 6 ランタイムが写経できる形式 (sentence_idx / phoneme_count / branch_tag を含む) になっている
- [ ] `MagicMock(spec=...)` で session を mock する unit test と、 実 ONNX session で動かす integration test の境界が明確
- [ ] cache file (`.opt.onnx`) が default と wavehax で別名生成されることを確認
- [ ] warmup が load() 内 2 session 分のみで、 streaming hot path では走らない

## 一から作り直すとしたら (Ticket-level rethinking)

採用案は「`PiperVoice` 1 クラスに 2 session を持たせ、 `synthesize_stream_raw` 内で per-sentence dispatch」 だが、 代替案として **「`DualPiperVoice` ラッパクラス」** を新規に切る経路もあった。 ラッパは `default_voice: PiperVoice` と `wavehax_voice: PiperVoice` を内部に保持し、 streaming 時に sentence ごとにどちらかの `synthesize_stream_raw` に委譲する。 利点は (1) `PiperVoice` の単一責任を保てる、 (2) 後方互換が「ラッパを使わなければ何も変わらない」 で機械的に保証される、 (3) unit test の境界が clean。 欠点は (a) 6 ランタイムへの伝播時に「Python は wrapper だが Rust は new_with_wavehax で同一クラスに統合」 のような語彙ズレが生じ AI-13 の cross-runtime API 設計が複雑化する、 (b) 共有 G2P / warmup の dedup ロジックを wrapper に持たせる必要があり実装規模が膨らむ。 計画 §4.3 と M4 milestone Deliverable §の「`PiperVoice.__init__` に optional named arg」 と明示されている canonical 仕様に従い、 本チケットでは単一クラス方式を取った。

別の rethinking として **「TDD でなく integration-test 先行」** の道もあり得た。 採用案は unit test (mock session) → integration test (実 ONNX) → snapshot test の 3 段だが、 もし integration test (実 tsukuyomi + tsukuyomi.wavehax の実 ONNX で streaming 経路を 1 本通す) を最初に書いていれば、 dispatch boundary の inclusivity (`<=` か `<` か) や thread pool との相互作用 (G2P 完了順との独立性) のような細かい semantics を**実行時に強制発見**できた可能性がある。 一方で AI-10 完了時点での wavehax ONNX の重み品質に不確実性が残るため、 integration-first は「dispatch logic のバグか ONNX の問題か」 を切り分けにくいリスクがあり、 単体テストで dispatch logic を完全に pin してから ONNX に進む採用順が現実解と判断した。

3 つ目の rethinking として **「dual vocoder でなく adaptive single vocoder」** すなわち 「companion ONNX を `tsukuyomi.onnx` 自体に統合し、 内部の sub-graph 切替で短文/長文を分ける」 という選択肢もあった。 これは 7 ランタイム ABI 同期が 1 session で済むので AI-13 のコストが激減する利点があるが、 (1) ONNX I/O が `is_short` のような新 input を必要とし PR #222 と二重同期になる (R4 が顕在化)、 (2) `[mb_istft_1d]` baseline の audio parity が ONNX 内部分岐の影響で微小に変動する恐れ (G-1.2 違反)、 (3) MS-Wavehax の 0.332M params を MB-iSTFT に内包させると ckpt サイズが融合増加し配布戦略が複雑化、 という 3 つの理由で却下。 「枠組み流用 + 増築」 (M4 milestone 冒頭で宣言) という設計哲学に最も忠実な dual vocoder + companion ONNX 経路が採用案として残った。

## 後続タスクへの連絡事項

AI-13 (7 ランタイム smoke + pairwise SNR 検証) への引き渡し:

- **canonical API shape (Python 側で確定済み):**
  - `PiperVoice.load(model_path, config_path=None, use_cuda=False, wavehax_model_path=None, streaming_threshold_phonemes=25)`
  - 6 ランタイムでの対応語彙: Rust = `PiperVoice::new_with_wavehax(...)` / Go = `WithWavehaxOption(path, threshold)` / C# = `LoadAsync(modelPath, wavehaxModelPath: null, streamingThresholdPhonemes: 25)` / WASM = `new PiperVoice({modelPath, wavehaxModelPath, streamingThresholdPhonemes})` / C++ = `piper_load_with_wavehax(...)` / C-API = `piper_load_with_wavehax(piper_handle**, const char*, const char*, int)`
- **dispatch snapshot JSON path:** `src/python/tests/data/dual_vocoder_dispatch_snapshot.json` — 5 種代表入力 × `(sentence_idx, phoneme_count, branch_tag)` の表。 AI-13 で 6 ランタイムが同じ入力に対して同じ branch_tag 列を出すことを pairwise SNR と並ぶ判定基準として使う
- **境界 semantics:** `len(phonemes) <= streaming_threshold_phonemes` (`<=` で wavehax 選択)。 6 ランタイムで `<` と書くと境界 25 で 6/7 不一致が起きるため要注意
- **wavehax_model_path 暫定パス:** AI-10 で生成済みの `/data/piper/output-css10-ja-mswavehax-poc/wavehax.onnx`、 配布用は `tsukuyomi.wavehax.onnx` (companion)
- **default threshold 25:** 計画 §4.6 の Xeon E5-2650 v4 / 25 phoneme 英文 canonical baseline と整合。 AI-12 benchmark 後にチューニングする可能性があるが、 AI-13 では 25 で 6 ランタイム横並びを確定する
- **warmup pattern:** load() 内で default session と wavehax session の 2 つを warmup、 streaming hot path では絶対に warmup を走らせない (AI-13 でも同じ規律)
- **cache file 命名規則:** ONNX path から派生 (`<onnx_path>.opt.onnx` + `.ok` marker)、 default と wavehax は別名生成されることを smoke で確認済み
- **後方互換 gate:** `wavehax_model_path=None` の経路で出力 PCM が SHA-256 一致 (Python で baseline hash を `src/python/tests/data/voice_stream_baseline_sha256.txt` に固定値として置いた)。 6 ランタイムでも同等の不変性 gate を用意する
- **PR #222 rebase 時の留意:** `load()` 末尾の optional named arg なので 1-2 hunk で済む想定。 `synthesize_stream_raw` 内の dispatch logic は session 切替のみで、 PR #222 が触る `phoneme_ids` / `scales` / `sid|speaker_embedding` の入力テンソル構築には触らない

## 関連ドキュメント

- 親マイルストーン: [../milestones/M4-mswavehax-dual-vocoder.md](../milestones/M4-mswavehax-dual-vocoder.md)
- 親計画 §6 (AI-11) / §4.3 (A-2 設計) / §3 (Conflict Map voice.py 行): [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- Companion deep-dive (MS-Wavehax 構造詳細): [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 改善調査統合 (§A-2): [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- 既存 spec (本チケットで編集しないが整合性確認に参照):
  - [../../spec/text-splitter-contract.toml](../../spec/text-splitter-contract.toml) — decoder-agnostic 維持、 touch 禁止
  - [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml) — `[mb_istft_1d]` baseline 編集禁止 (G-1.2 gate)、 `[mswavehax]` section 追加は AI-14
  - [../../spec/ort-session-contract.toml](../../spec/ort-session-contract.toml) — warmup / cache 規律は dual session でも同一
- 既存実装の参照箇所:
  - `src/python_run/piper/voice.py` L534 (`class PiperVoice`) / L538-569 (`load`) / L752 (`synthesize_stream_raw`)
  - `src/python/piper_train/vits/models.py` L754 (AI-08 で `dec_wavehax` sibling 追加点、 ONNX export 経路の参照元)
- 関連 PR (merge 待ち):
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222)
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537)
- 論文 (MS-Wavehax):
  - [arXiv 2506.03554](https://arxiv.org/html/2506.03554) MS-Wavehax (Yoneyama et al., Interspeech 2025)
