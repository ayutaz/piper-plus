# Python ランタイムにスウェーデン語の音素化器を入れる (Issue #830)

## 問題

Python ランタイム (PyPI `piper-plus`、`src/python_run/piper_plus/phonemize/`) にはスウェーデン語の音素化器がなかった。`PiperVoice` の多言語の言語一覧は 6 言語で固定されており、sv の言語 ID でもラテン文字の既定が `en` になるため、sv の文は英語 G2P で読まれていた。学習側 (`piper_plus_g2p.SwedishPhonemizer`) の golden 51 件すべてとずれていた。他のランタイム (Rust / C++ / Go / C# / WASM) は sv を実装している。

## 変更

- `phonemize/swedish.py` (新規): 学習側 `swedish.py` の規則表と関数をそのまま移した。公開 API は `french.py` などと同じ形 (`phonemize_swedish(text)`、BOS/EOS 付き)。韻律と `Phonemizer` ABC は、ランタイムが音素トークンしか使わないため移していない。依存パッケージは増えない。
- `multilingual.py`: `_get_phonemize_func` に sv を足した。
- `voice.py`: 多言語の言語一覧を `_multilingual_languages()` に切り出し、モデルの `language_id_map` に `sv` があるときだけ `sv` を加える。sv を加えると単語単位の言語判定 (#539) が働き、"och" などをスウェーデン語として読むようになるため、sv を持たない公開中の 6 言語モデルでは従来の動作を変えない。

## 再発防止

- `src/python_run/tests/test_swedish_phonemization.py` (191 件) が、ランタイムの sv 音素化を学習側 `SwedishPhonemizer` と比べる (`sv_golden.json` 全件、多言語 golden の sv 51 件、規則ごとの手書きケース)。学習側の規則だけが変わると、このテストが失敗する。
- 同じテストが、ランタイムの区分けが出しうるすべての言語 (`_LATIN_SEGMENT_LANGUAGES`、`PiperVoice` が渡す言語、検出器が返す言語、`LANGUAGE_ID_MAP`) について `_get_phonemize_func` が音素化器を返すことを検査する。言語を足して音素化器を足し忘れると失敗する。
- `known_divergences.json` から python_run の sv 51 件を外した。golden 照合 (`test_g2p_golden_parity.py`) が sv の差を再び見つける。
- python-tests の CI は新しいテストを実行し、`sv_golden.json` の変更でも走る。

## 範囲外

- ko: `PiperVoice` は ko を言語一覧に入れず、`LANGUAGE_ID_MAP` にもないため、今回は扱わない。
- sv を持たないモデルでは、golden の生成条件 (常に 8 言語) と違い sv を言語一覧に入れない。上の理由による意図的な差である。
