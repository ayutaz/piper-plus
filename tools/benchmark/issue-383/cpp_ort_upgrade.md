# C++ ORT アップグレード検証レポート (Issue #383 follow-up)

## TL;DR

`fix(cpp): ONNX Runtime 1.17.0 → 1.20.0` (commit `37c7c72a`) に加え、test exe
ディレクトリに `onnxruntime.dll` を staging する POST_BUILD コマンドを追加して
SEH 0xc0000005 が解消した。**Phase 1 fork (`5e0597c5`) のレポートは誤診 — 真因は
`C:\Windows\System32\onnxruntime.dll` (Windows ML 同梱の古い ORT) を Windows DLL
loader が拾っていたこと**で、ORT のバージョンそのものではなかった。

## 検証環境

* Windows 11 / MSVC 2022 / CMake 3.28.1
* AMD Ryzen 9 5900X (24 threads)
* 検証コミット: `37c7c72a` (本検証用 patch を含む)

## 検出 / 解決の流れ

1. ORT 1.20.0 download / build 成功 (clean build 7m40s)
2. `ctest` 初回実行: 6/29 fail。エラーメッセージは
   `The given version [20] is not supported, only version 1 to 10 is supported in this build.`
3. `[14]` (1.17 時) → `[20]` (1.20 時) と数字が変化していたので「ORT のバージョン番号
   が ORT 内部で弾かれている」と推測。
4. `where.exe onnxruntime.dll` で `C:\Windows\System32\onnxruntime.dll` を発見。
   → Windows ML 同梱の古い ORT が DLL loader に拾われていた。
5. `cmake/Install.cmake` の `copy_dlls_to_target` は `piper` / `test_piper` には
   ORT DLL を staging するが、test サブディレクトリで個別に作る exe 群
   (`test_streaming.exe` 他、`src/cpp/tests/Release/`) は対象外だった。
6. `src/cpp/tests/CMakeLists.txt` の test loop に POST_BUILD で `onnxruntime.dll`
   と `onnxruntime_providers*.dll` を staging するコマンドを追加。
7. 再ビルド + `ctest` で **28/29 pass** に改善。

## ctest 結果 (修正後)

```text
97% tests passed, 1 tests failed out of 29
Total Test time (real) = 146.17 sec
```

* 全 29 test suite のうち 28 が pass
* `test_c_api_audio_regression` も pass (Phase 1 で SEH crash していた regression suite)
* 残り 1 件 (`test_c_api_integration`) で 4 個のサブテスト失敗:
  * `CApiIntegrationTest.IteratorVsOneShot`
  * `CApiIntegrationTest.IteratorVsOneShotParityWithCrossfade`
  * `CApiIntegrationTest.SingleSentenceNoCrossfadeEffect`
  * `CApiIntegrationTest.IteratorAlwaysProcessSamplesBeforeCheckingDone`

## 残課題 (本検証範囲外)

`CApiIntegrationTest.Iterator*` の 4 件失敗は **Phase 1 fork (`5e0597c5`) の
`synth_start` / `synth_next` Iterator 並列化** が one-shot path と非互換になった
ことが原因。fork は model-loading が SEH crash する状態でビルドしていたため、
Iterator path の挙動が事前に検証できていなかった。

ratio チェックの一例: `IteratorAlwaysProcessSamplesBeforeCheckingDone` で
`ratio=0.768` (期待 `>0.80`) → done フラグの判定タイミングで sample が
14592 個落ちている。Iterator が DONE chunk を見て早期終了する前に
sample を吸い切れていない可能性。

これは Issue #383 Phase 1 の bug であり、ORT バージョンとは無関係。別コミット
で修正する。

## 教訓

* Windows での DLL hell は `C:\Windows\System32\onnxruntime.dll` が地雷。
  Windows ML / Windows AI Platform の古い ORT が常駐するため、test
  binary には必ず ORT DLL を staging する。
* ORT のバージョン番号 [N] を含むエラーは ORT 自身ではなく
  「読み込まれた古い ORT が新しいモデル / 新しい ORT API を弾いた」可能性
  を疑うこと。

## 修正ファイル

* `src/cpp/tests/CMakeLists.txt` — test loop POST_BUILD で `onnxruntime.dll` /
  `onnxruntime_providers*.dll` を test exe ディレクトリに staging
