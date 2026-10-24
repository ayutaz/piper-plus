# ブラウザの中国語の文中にある数字を英語の数として読む (Issue #847)

## 経緯

ブラウザ向け npm `piper-plus` (`src/wasm/openjtalk-web`) で zh を含むモデルを使うと、中国語の文は Rust WASM の `MultilingualPhonemizer` (`src/rust/piper-wasm`) が音素にする。この音素化器は、中国語の文中の数字やラテン文字を英語の区間として切り出す。ところが Rust WASM の英語は辞書を持たず、1 文字ずつ並べるだけ (`PassthroughPhonemizer`) だった。そのため `123` は `1 2 3` になり、Python 学習側の読み (`one hundred twenty-three`) と合わなかった。

G2P の golden 照合 (`test-g2p-golden-parity.js`、runtime `wasm`) では、zh の `123` / `0` / `100` の 3 件を `known_divergences.json` に planned (#847) として記録していた。#848 で `@piper-plus/g2p` が CMU 辞書と g2p_en の正規化で英語を読むようになり、英語だけの文は直った。しかし中国語の文中の英語の区間は Rust WASM の中で処理されるので、この 3 件は残っていた。

## 原因

- `piper-wasm` は `piper-plus-g2p` を `default-features = false` で使い、`english` feature を有効にしていなかった。英語の音素化器 (`EnglishPhonemizer`) がビルドに入っていなかった。
- `EnglishPhonemizer` の作り方はファイルから辞書を読むものか、バイナリに辞書を埋め込むもの (`bundled-dicts`) だけだった。ブラウザにはファイルがなく、埋め込むと WASM が 3.7 MB 増える。

## 変更

2 つの案を比べた。

- 案 A: Rust WASM に `EnglishPhonemizer` を入れ、辞書は JS から渡す。
- 案 B: Rust WASM が切り出した英語の区間を JS の英語 G2P に戻す。

案 A を選んだ。理由は次のとおり。

- Rust / C++ / Swift と同じ Rust のコード (`MultilingualPhonemizer` と `EnglishPhonemizer`) で読むので、出力がこれらと一致する。
- 案 B では Rust から JS の関数を呼ぶ必要がある。しかし `Phonemizer` trait は `Send + Sync` を要求し、JS の関数はこれを満たさない。満たしたことにするには `unsafe` が要る。
- 辞書を WASM に埋め込まず、`@piper-plus/g2p` が同梱している辞書を渡すので、配布物は増えない。

変更点は次のとおり。

- `piper-plus-g2p`: `EnglishPhonemizer::from_json_bytes()` を足した。ファイルを読まずに、CMU 辞書の JSON バイト列から作る。`new_bundled()` もこれを使うようにした。
- `piper-wasm`:
  - `en` feature (`piper-plus-g2p/english`) を足し、`multilingual` と `multilingual-external` に含めた。
  - `setEnglishDictionary(bytes)` を足した。中国語の辞書を渡す `setChineseDictionary` と同じ形にした。
  - en は辞書を渡されるまで今までどおり 1 文字ずつ並べる。
- `openjtalk-web`:
  - `RustWasmAdapter.loadEnglishDictionary()` を足した。`@piper-plus/g2p` の `loadCmuDict()` が返す辞書を JSON にして、WASM に渡す。
  - 辞書を渡すのは、モデルに zh と en の両方があるときだけにした。そのときは JS の英語 G2P が同じ辞書をすでに読み込んでいるので、追加の取得はない。
  - 渡すのは初期化時ではなく、最初に zh を音素にするときにした。WASM のメモリが約 18 MB 増えるため、同じモデルで ja / en / es だけを使う人には負担させない。
  - `loadCmuDict` は名前を指定せず、モジュール全体として import した。npm で公開済みの `@piper-plus/g2p` 0.4.2 にはこの関数がなく、名前を指定して import すると、パッケージ全体が読み込めなくなるため。関数がないときは警告を出し、今までどおり 1 文字ずつ並べる。

## 結果

- golden 照合 (runtime `wasm`、347 件):
  - 変更前は zh の `0` と `100` の 2 件が不一致で失敗した。
  - 変更後はすべて通る。
- zh の `123` は `w ˈ ʌ n   h ˈ ʌ n d ɹ ə d   t w ˈ ɛ n t i ː θ ɹ ˈ i ː` になる。これは Rust のネイティブ版と一致する。Python との強勢の差は、cpp / rust / swift で accepted として記録している差と同じものである。`twenty-three` が CMU 辞書になく、Python はニューラル予測で読み、移植版は `twenty` と `three` をつなぐため。
- `known_divergences.json` からは #847 の 3 件を消した。zh `123` の accepted の項目には `wasm` を加えた。
- サイズとコスト (Node 24、このマシンでの実測):
  - `multilingual` の WASM は 60,185,334 → 60,240,967 バイトで、約 54 KB 増えた。wasm-build.yml の上限 64 MB 内に収まる。
  - npm の tarball は WASM 以外は変わらない。
  - 辞書を渡したとき、WASM のメモリが約 18 MB 増えた (60.1 MB → 78.4 MB)。
  - 時間は、JSON 化が約 0.1 秒、Rust での読み込みが 0.1〜0.5 秒かかった。

## 再発防止

- golden 照合 (`ci.yml` の `npm-package-tests`) は `src/rust/**` と `src/wasm/**` の変更で走る。zh の数字が 1 文字ずつに戻ると、zh `0` / `100` が不一致になって失敗する。CMU 辞書の canonical と npm の写しもこの範囲に入るので、パスの条件は追加していない。
- `piper-wasm`:
  - ネイティブのテストで、zh の `100` が golden どおりになることを確かめる。`wasm-build.yml` に `--features en` の実行と wasm32 の `cargo check` を足した。
  - wasm-bindgen のテストで、zh の `0` / `100` が golden どおりになることと、壊れた JSON がエラーコード付きで拒否されることを確かめる。後者は `rust-tests.yml` の `wasm-test` (`multilingual-external`) で走る。
- `piper-plus-g2p`: `from_json_bytes` のテストを足した。canonical の辞書を読めること、不正な JSON を拒否することを確かめる。
- `openjtalk-web`:
  - `test-rust-wasm-adapter.js` で、辞書の渡し方を確かめる。辞書を JSON のバイト列で 1 回渡すこと、setter がないビルドでは何もしないこと、`loadCmuDict` がないときや失敗したときは reject せずに警告することを確かめる。
  - `test-piper-plus-wasm-g2p.js` で、辞書を渡す時機を確かめる。zh と en があるモデルでは最初の zh の要求で 1 回だけ渡すこと、他の言語の要求や zh か en がないモデルでは渡さないことを確かめる。
